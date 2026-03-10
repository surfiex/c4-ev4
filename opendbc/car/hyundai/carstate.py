from collections import deque
import copy
import math

from opendbc.can import CANDefine, CANParser
from opendbc.car import Bus, create_button_events, structs
from opendbc.car.common.conversions import Conversions as CV
from opendbc.car.hyundai.hyundaicanfd import CanBus
from opendbc.car.hyundai.values import HyundaiFlags, CAR, DBC, Buttons, CarControllerParams
from opendbc.car.interfaces import CarStateBase

ButtonType = structs.CarState.ButtonEvent.Type

PREV_BUTTON_SAMPLES = 8
CLUSTER_SAMPLE_RATE = 20  # frames
STANDSTILL_THRESHOLD = 12 * 0.03125

# Cancel button can sometimes be ACC pause/resume button, main button can also enable on some cars
ENABLE_BUTTONS = (Buttons.RES_ACCEL, Buttons.SET_DECEL, Buttons.CANCEL)
BUTTONS_DICT = {Buttons.RES_ACCEL: ButtonType.accelCruise, Buttons.SET_DECEL: ButtonType.decelCruise,
                Buttons.GAP_DIST: ButtonType.gapAdjustCruise, Buttons.CANCEL: ButtonType.cancel}

BUTTONS_DICT_EV4 = {Buttons.RES_ACCEL: ButtonType.decelCruise, Buttons.SET_DECEL: ButtonType.accelCruise,
                    Buttons.GAP_DIST: ButtonType.gapAdjustCruise, Buttons.CANCEL: ButtonType.cancel}


class CarState(CarStateBase):
  def __init__(self, CP):
    super().__init__(CP)
    self.pt_bus = CanBus(CP).ECAN if CP.flags & HyundaiFlags.CANFD else Bus.pt
    can_define = CANDefine(DBC[CP.carFingerprint][self.pt_bus])

    self.cruise_buttons: deque = deque([Buttons.NONE] * PREV_BUTTON_SAMPLES, maxlen=PREV_BUTTON_SAMPLES)
    self.main_buttons: deque = deque([Buttons.NONE] * PREV_BUTTON_SAMPLES, maxlen=PREV_BUTTON_SAMPLES)
    self.lda_button = 0

    self.gear_msg_canfd = "ACCELERATOR" if CP.flags & HyundaiFlags.EV else \
                          "GEAR_ALT" if CP.flags & HyundaiFlags.CANFD_ALT_GEARS else \
                          "GEAR_ALT_2" if CP.flags & HyundaiFlags.CANFD_ALT_GEARS_2 else \
                          "GEAR_SHIFTER"
    if CP.flags & HyundaiFlags.CANFD:
      self.shifter_values = can_define.dv[self.gear_msg_canfd]["GEAR"]
    elif CP.flags & (HyundaiFlags.HYBRID | HyundaiFlags.EV):
      self.shifter_values = can_define.dv["ELECT_GEAR"]["Elect_Gear_Shifter"]
    elif self.CP.flags & HyundaiFlags.CLUSTER_GEARS:
      self.shifter_values = can_define.dv["CLU15"]["CF_Clu_Gear"]
    elif self.CP.flags & HyundaiFlags.TCU_GEARS:
      self.shifter_values = can_define.dv["TCU12"]["CUR_GR"]
    elif CP.flags & HyundaiFlags.FCEV:
      self.shifter_values = can_define.dv["EMS20"]["HYDROGEN_GEAR_SHIFTER"]
    else:
      self.shifter_values = can_define.dv["LVR12"]["CF_Lvr_Gear"]

    self.accelerator_msg_canfd = "ACCELERATOR" if CP.flags & HyundaiFlags.EV else \
                                 "ACCELERATOR_ALT" if CP.flags & HyundaiFlags.HYBRID else \
                                 "ACCELERATOR_BRAKE_ALT"
    self.cruise_btns_msg_canfd = "CRUISE_BUTTONS_ALT" if CP.flags & HyundaiFlags.CANFD_ALT_BUTTONS else \
                                 "CRUISE_BUTTONS"
    self.is_metric = False
    self.buttons_counter = 0
    self.lkas_alt_msg = {}
    self.cruise_info = {}

    # On some cars, CLU15->CF_Clu_VehicleSpeed can oscillate faster than the dash updates. Sample at 5 Hz
    self.cluster_speed = 0
    self.cluster_speed_counter = CLUSTER_SAMPLE_RATE

    self.params = CarControllerParams(CP)

  def recent_button_interaction(self) -> bool:
    # On some newer model years, the CANCEL button acts as a pause/resume button based on the PCM state
    # To avoid re-engaging when openpilot cancels, check user engagement intention via buttons
    # Main button also can trigger an engagement on these cars
    return any(btn in ENABLE_BUTTONS for btn in self.cruise_buttons) or any(self.main_buttons)

  def update(self, can_parsers) -> structs.CarState:
    cp = can_parsers[Bus.pt]
    cp_cam = can_parsers[Bus.cam]

    if self.CP.flags & HyundaiFlags.CANFD:
      return self.update_canfd(can_parsers)

    ret = structs.CarState()
    cp_cruise = cp_cam if self.CP.flags & HyundaiFlags.CAMERA_SCC else cp
    self.is_metric = cp.vl["CLU11"]["CF_Clu_SPEED_UNIT"] == 0
    speed_conv = CV.KPH_TO_MS if self.is_metric else CV.MPH_TO_MS

    ret.doorOpen = any([cp.vl["CGW1"]["CF_Gway_DrvDrSw"], cp.vl["CGW1"]["CF_Gway_AstDrSw"],
                        cp.vl["CGW2"]["CF_Gway_RLDrSw"], cp.vl["CGW2"]["CF_Gway_RRDrSw"]])

    ret.seatbeltUnlatched = cp.vl["CGW1"]["CF_Gway_DrvSeatBeltSw"] == 0

    self.parse_wheel_speeds(ret,
      cp.vl["WHL_SPD11"]["WHL_SPD_FL"],
      cp.vl["WHL_SPD11"]["WHL_SPD_FR"],
      cp.vl["WHL_SPD11"]["WHL_SPD_RL"],
      cp.vl["WHL_SPD11"]["WHL_SPD_RR"],
    )
    ret.standstill = cp.vl["WHL_SPD11"]["WHL_SPD_FL"] <= STANDSTILL_THRESHOLD and cp.vl["WHL_SPD11"]["WHL_SPD_RR"] <= STANDSTILL_THRESHOLD

    self.cluster_speed_counter += 1
    if self.cluster_speed_counter > CLUSTER_SAMPLE_RATE:
      self.cluster_speed = cp.vl["CLU15"]["CF_Clu_VehicleSpeed"]
      self.cluster_speed_counter = 0

      # Mimic how dash converts to imperial.
      # Sorento is the only platform where CF_Clu_VehicleSpeed is already imperial when not is_metric
      # TODO: CGW_USM1->CF_Gway_DrLockSoundRValue may describe this
      if not self.is_metric and self.CP.carFingerprint not in (CAR.KIA_SORENTO,):
        self.cluster_speed = math.floor(self.cluster_speed * CV.KPH_TO_MPH + CV.KPH_TO_MPH)

    ret.vEgoCluster = self.cluster_speed * speed_conv

    ret.steeringAngleDeg = cp.vl["SAS11"]["SAS_Angle"]
    ret.steeringRateDeg = cp.vl["SAS11"]["SAS_Speed"]
    ret.leftBlinker, ret.rightBlinker = self.update_blinker_from_lamp(
      50, cp.vl["CGW1"]["CF_Gway_TurnSigLh"], cp.vl["CGW1"]["CF_Gway_TurnSigRh"])
    ret.steeringTorque = cp.vl["MDPS12"]["CR_Mdps_StrColTq"]
    ret.steeringTorqueEps = cp.vl["MDPS12"]["CR_Mdps_OutTq"]
    ret.steeringPressed = self.update_steering_pressed(abs(ret.steeringTorque) > self.params.STEER_THRESHOLD, 5)
    ret.steerFaultTemporary = cp.vl["MDPS12"]["CF_Mdps_ToiUnavail"] != 0 or cp.vl["MDPS12"]["CF_Mdps_ToiFlt"] != 0

    # cruise state
    if self.CP.openpilotLongitudinalControl:
      # These are not used for engage/disengage since openpilot keeps track of state using the buttons
      ret.cruiseState.available = cp.vl["TCS13"]["ACCEnable"] == 0
      ret.cruiseState.enabled = cp.vl["TCS13"]["ACC_REQ"] == 1
      ret.cruiseState.standstill = False
      ret.cruiseState.nonAdaptive = False
    else:
      ret.cruiseState.available = cp_cruise.vl["SCC11"]["MainMode_ACC"] == 1
      ret.cruiseState.enabled = cp_cruise.vl["SCC12"]["ACCMode"] != 0
      ret.cruiseState.standstill = cp_cruise.vl["SCC11"]["SCCInfoDisplay"] == 4.
      ret.cruiseState.nonAdaptive = cp_cruise.vl["SCC11"]["SCCInfoDisplay"] == 2.  # Shows 'Cruise Control' on dash
      ret.cruiseState.speed = cp_cruise.vl["SCC11"]["VSetDis"] * speed_conv

    # TODO: Find brake pressure
    ret.brake = 0
    ret.brakePressed = cp.vl["TCS13"]["DriverOverride"] == 2  # 2 includes regen braking by user on HEV/EV
    ret.brakeHoldActive = cp.vl["TCS15"]["AVH_LAMP"] == 2  # 0 OFF, 1 ERROR, 2 ACTIVE, 3 READY
    ret.parkingBrake = cp.vl["TCS13"]["PBRAKE_ACT"] == 1
    ret.espDisabled = cp.vl["TCS11"]["TCS_PAS"] == 1
    ret.espActive = cp.vl["TCS11"]["ABS_ACT"] == 1
    ret.accFaulted = cp.vl["TCS13"]["ACCEnable"] != 0  # 0 ACC CONTROL ENABLED, 1-3 ACC CONTROL DISABLED

    if self.CP.flags & (HyundaiFlags.HYBRID | HyundaiFlags.EV | HyundaiFlags.FCEV):
      if self.CP.flags & HyundaiFlags.FCEV:
        ret.gasPressed = cp.vl["FCEV_ACCELERATOR"]["ACCELERATOR_PEDAL"] > 0
      elif self.CP.flags & HyundaiFlags.HYBRID:
        ret.gasPressed = cp.vl["E_EMS11"]["CR_Vcu_AccPedDep_Pos"] > 0
      else:
        ret.gasPressed = cp.vl["E_EMS11"]["Accel_Pedal_Pos"] > 0
    else:
      ret.gasPressed = bool(cp.vl["EMS16"]["CF_Ems_AclAct"])

    # Gear Selection via Cluster - For those Kia/Hyundai which are not fully discovered, we can use the Cluster Indicator for Gear Selection,
    # as this seems to be standard over all cars, but is not the preferred method.
    if self.CP.flags & (HyundaiFlags.HYBRID | HyundaiFlags.EV):
      gear = cp.vl["ELECT_GEAR"]["Elect_Gear_Shifter"]
    elif self.CP.flags & HyundaiFlags.FCEV:
      gear = cp.vl["EMS20"]["HYDROGEN_GEAR_SHIFTER"]
    elif self.CP.flags & HyundaiFlags.CLUSTER_GEARS:
      gear = cp.vl["CLU15"]["CF_Clu_Gear"]
    elif self.CP.flags & HyundaiFlags.TCU_GEARS:
      gear = cp.vl["TCU12"]["CUR_GR"]
    else:
      gear = cp.vl["LVR12"]["CF_Lvr_Gear"]

    ret.gearShifter = self.parse_gear_shifter(self.shifter_values.get(gear))

    if not self.CP.openpilotLongitudinalControl or self.CP.flags & HyundaiFlags.CAMERA_SCC:
      aeb_src = "FCA11" if self.CP.flags & HyundaiFlags.USE_FCA.value else "SCC12"
      aeb_sig = "FCA_CmdAct" if self.CP.flags & HyundaiFlags.USE_FCA.value else "AEB_CmdAct"
      aeb_warning = cp_cruise.vl[aeb_src]["CF_VSM_Warn"] != 0
      scc_warning = cp_cruise.vl["SCC12"]["TakeOverReq"] == 1  # sometimes only SCC system shows an FCW
      aeb_braking = cp_cruise.vl[aeb_src]["CF_VSM_DecCmdAct"] != 0 or cp_cruise.vl[aeb_src][aeb_sig] != 0
      ret.stockFcw = (aeb_warning or scc_warning) and not aeb_braking
      ret.stockAeb = aeb_warning and aeb_braking

    if self.CP.enableBsm:
      ret.leftBlindspot = cp.vl["LCA11"]["CF_Lca_IndLeft"] != 0
      ret.rightBlindspot = cp.vl["LCA11"]["CF_Lca_IndRight"] != 0

    # save the entire LKAS11 and CLU11
    self.lkas11 = copy.copy(cp_cam.vl["LKAS11"])
    self.clu11 = copy.copy(cp.vl["CLU11"])
    self.steer_state = cp.vl["MDPS12"]["CF_Mdps_ToiActive"]  # 0 NOT ACTIVE, 1 ACTIVE
    prev_cruise_buttons = self.cruise_buttons[-1]
    prev_main_buttons = self.main_buttons[-1]
    prev_lda_button = self.lda_button
    self.cruise_buttons.extend(cp.vl_all["CLU11"]["CF_Clu_CruiseSwState"])
    self.main_buttons.extend(cp.vl_all["CLU11"]["CF_Clu_CruiseSwMain"])
    if self.CP.flags & HyundaiFlags.HAS_LDA_BUTTON:
      self.lda_button = cp.vl["BCM_PO_11"]["LDA_BTN"]

    btn_dict = BUTTONS_DICT_EV4 if self.CP.carFingerprint == CAR.KIA_EV4 else BUTTONS_DICT
    ret.buttonEvents = [*create_button_events(self.cruise_buttons[-1], prev_cruise_buttons, btn_dict),
                        *create_button_events(self.main_buttons[-1], prev_main_buttons, {1: ButtonType.mainCruise}),
                        *create_button_events(self.lda_button, prev_lda_button, {1: ButtonType.lkas})]

    ret.blockPcmEnable = not self.recent_button_interaction()

    # low speed steer alert hysteresis logic (only for cars with steer cut off above 10 m/s)
    if ret.vEgo < (self.CP.minSteerSpeed + 2.) and self.CP.minSteerSpeed > 10.:
      self.low_speed_alert = True
    if ret.vEgo > (self.CP.minSteerSpeed + 4.):
      self.low_speed_alert = False
    ret.lowSpeedAlert = self.low_speed_alert

    return ret

  def update_canfd(self, can_parsers) -> structs.CarState:
    cp = can_parsers[self.pt_bus]
    cp_cam = can_parsers[Bus.cam]
    cp_acan = can_parsers[Bus.pt]

    ret = structs.CarState()

    self.is_metric = cp.vl["CRUISE_BUTTONS_ALT"]["DISTANCE_UNIT"] != 1
    speed_factor = CV.KPH_TO_MS if self.is_metric else CV.MPH_TO_MS

    if self.CP.carFingerprint == CAR.KIA_EV4:
      ret.gasPressed = cp.vl["ACCELERATOR"]["ACCELERATOR_PEDAL"] > 1e-5
      # EV4 Body CAN signals for door/seatbelt are not mapped correctly yet.
      # Force them to False to allow engagement.
      ret.doorOpen = False
      ret.seatbeltUnlatched = False
      ret.leftBlinker = cp_cam.vl["LFA_BUTTON"]["LEFT_BLINKER"] == 0x2A
      ret.rightBlinker = cp_cam.vl["LFA_BUTTON"]["RIGHT_BLINKER"] == 0x2C
      gear = cp.vl["ACCELERATOR"]["GEAR"]
    else:
      if self.CP.flags & (HyundaiFlags.EV | HyundaiFlags.HYBRID):
        ret.gasPressed = cp.vl[self.accelerator_msg_canfd]["ACCELERATOR_PEDAL"] > 1e-5
      else:
        ret.gasPressed = bool(cp.vl[self.accelerator_msg_canfd]["ACCELERATOR_PEDAL_PRESSED"])
      ret.doorOpen = any([cp_cam.vl["LFA_BUTTON"]["DOOR_OPEN"] if "LFA_BUTTON" in cp_cam.vl else False]) # Default
      ret.seatbeltUnlatched = False # Default
      gear = cp.vl[self.accelerator_msg_canfd]["GEAR"]

    ret.gearShifter = self.parse_gear_shifter(self.shifter_values.get(gear))

    # TODO: figure out positions
    self.parse_wheel_speeds(ret,
      cp.vl["WHEEL_SPEEDS"]["WHL_SpdFLVal"],
      cp.vl["WHEEL_SPEEDS"]["WHL_SpdFRVal"],
      cp.vl["WHEEL_SPEEDS"]["WHL_SpdRLVal"],
      cp.vl["WHEEL_SPEEDS"]["WHL_SpdRRVal"],
    )
    ret.standstill = cp.vl["WHEEL_SPEEDS"]["WHL_SpdFLVal"] <= STANDSTILL_THRESHOLD and cp.vl["WHEEL_SPEEDS"]["WHL_SpdFRVal"] <= STANDSTILL_THRESHOLD and \
                     cp.vl["WHEEL_SPEEDS"]["WHL_SpdRLVal"] <= STANDSTILL_THRESHOLD and cp.vl["WHEEL_SPEEDS"]["WHL_SpdRRVal"] <= STANDSTILL_THRESHOLD

    ret.steeringRateDeg = cp.vl["STEERING_SENSORS"]["STEERING_RATE"]
    ret.steeringAngleDeg = cp.vl["STEERING_SENSORS"]["STEERING_ANGLE"]
    ret.steeringTorque = cp.vl["MDPS"]["STEERING_COL_TORQUE"]
    ret.steeringTorqueEps = cp.vl["MDPS"]["STEERING_OUT_TORQUE"]
    ret.steeringPressed = self.update_steering_pressed(abs(ret.steeringTorque) > self.params.STEER_THRESHOLD, 5)

    if self.CP.carFingerprint == CAR.KIA_EV4:
      ret.vEgoCluster = ret.vEgo

    ret.steerFaultTemporary = cp.vl["MDPS"]["LKA_FAULT"] != 0

    # Physical brake pedal only (ignores auto-regenerative braking)
    ret.brakePressed = cp.vl["TCS"]["DriverBraking"] == 1

    # TODO: alt signal usage may be described by cp.vl['BLINKERS']['USE_ALT_LAMP']
    left_blinker_sig, right_blinker_sig = "LEFT_LAMP", "RIGHT_LAMP"
    if self.CP.carFingerprint != CAR.KIA_EV4:
      if self.CP.carFingerprint == CAR.HYUNDAI_KONA_EV_2ND_GEN:
        left_blinker_sig, right_blinker_sig = "LEFT_LAMP_ALT", "RIGHT_LAMP_ALT"
      ret.leftBlinker, ret.rightBlinker = self.update_blinker_from_lamp(50, cp.vl["BLINKERS"][left_blinker_sig],
                                                                        cp.vl["BLINKERS"][right_blinker_sig])
    if self.CP.enableBsm:
      ret.leftBlindspot = cp.vl["BLINDSPOTS_REAR_CORNERS"]["FL_INDICATOR"] != 0
      ret.rightBlindspot = cp.vl["BLINDSPOTS_REAR_CORNERS"]["FR_INDICATOR"] != 0

    # cruise state
    # CAN FD cars enable on main button press, set available if no TCS faults preventing engagement
    if self.CP.carFingerprint == CAR.KIA_EV4:
      ret.cruiseState.available = cp.vl["TCS"].get("ACCEnable", 0) in (0, 2)
    else:
      ret.cruiseState.available = cp.vl["TCS"].get("ACCEnable", 0) == 0
    
    if self.CP.openpilotLongitudinalControl:
      # These are not used for engage/disengage since openpilot keeps track of state using the buttons
      ret.cruiseState.enabled = cp.vl["TCS"]["ACC_REQ"] == 1
      ret.cruiseState.standstill = False
    else:
      cp_cruise_info = cp_cam if self.CP.flags & HyundaiFlags.CANFD_CAMERA_SCC else cp
      scc_control = cp_cruise_info.vl["SCC_CONTROL"]
      ret.cruiseState.enabled = scc_control.get("ACCMode", 0) in (1, 2)
      ret.cruiseState.standstill = scc_control.get("CRUISE_STANDSTILL", 0) == 1
      ret.cruiseState.speed = scc_control.get("VSetDis", 0) * speed_factor
      self.cruise_info = copy.copy(scc_control)

    # Manual Speed Limit Assist is a feature that replaces non-adaptive cruise control on EV CAN FD platforms.
    # It limits the vehicle speed, overridable by pressing the accelerator past a certain point.
    # The car will brake, but does not respect positive acceleration commands in this mode
    # TODO: find this message on ICE & HYBRID cars + cruise control signals (if exists)
    if self.CP.flags & HyundaiFlags.EV:
      ret.cruiseState.nonAdaptive = cp.vl["MANUAL_SPEED_LIMIT_ASSIST"]["MSLA_ENABLED"] == 1

    prev_cruise_buttons = self.cruise_buttons[-1]
    prev_main_buttons = self.main_buttons[-1]
    prev_lda_button = self.lda_button
    self.cruise_buttons.extend(cp.vl_all[self.cruise_btns_msg_canfd]["CRUISE_BUTTONS"])
    self.main_buttons.extend(cp.vl_all[self.cruise_btns_msg_canfd]["ADAPTIVE_CRUISE_MAIN_BTN"])
    if self.CP.carFingerprint == CAR.KIA_EV4:
      self.lda_button = cp_cam.vl["LFA_BUTTON"]["LFA_BTN"] or cp.vl["CRUISE_BUTTONS_ALT"]["LDA_BTN"]
    elif self.CP.flags & HyundaiFlags.CANFD_ALT_BUTTONS:
      self.lda_button = cp.vl[self.cruise_btns_msg_canfd]["LDA_BTN"]
    else:
      self.lda_button = cp.vl[self.cruise_btns_msg_canfd]["LDA_BTN"]
    self.buttons_counter = cp.vl[self.cruise_btns_msg_canfd].get("COUNTER", cp.vl[self.cruise_btns_msg_canfd].get("COUNTER_T", 0))

    if self.CP.carFingerprint == CAR.KIA_EV4:
      ret.accFaulted = cp.vl["TCS"]["ACCEnable"] not in (0, 2)
    else:
      ret.accFaulted = cp.vl["TCS"]["ACCEnable"] != 0  # 0 ACC CONTROL ENABLED, 1-3 ACC CONTROL DISABLED

    if self.CP.flags & HyundaiFlags.CANFD_LKA_STEERING:
      # EV4: Capture full LKAS_ALT for true MITM
      if self.CP.carFingerprint == CAR.KIA_EV4:
        self.lkas_alt_msg = copy.copy(cp_cam.vl["LKAS_ALT"])

      self.lfa_block_msg = copy.copy(cp_cam.vl["CAM_0x362"] if self.CP.flags & HyundaiFlags.CANFD_LKA_STEERING_ALT
                                          else cp_cam.vl["CAM_0x2a4"])

    # HDA2 Forwarding: Save messages from camera bus to be forwarded to car bus (Bus 0) and ECAN (Bus 1)
    # AND messages from car bus to be forwarded to camera bus (Bus 2)
    # Using vl_all to ensure we forward every message exactly as received without duplicates
    self.hda2_forward_msgs = []
    self.car_to_cam_forward_msgs = []

    # Include all ADRV/HDA2 IDs found on Bus 2 (Camera Bus) that need to be forwarded to Bus 1 (ECAN)
    # PRUNED: Removed ONLY IDs spoofed in hyundaicanfd.py:create_adrv_messages_ev4 (81, 352, 474, 490, 512, 811, 813, 816, 837)
    forward_ids = [282, 298, 357, 416, 437, 480, 506, 698, 752, 866, 867, 868, 896, 905, 917, 928] + \
                  list(range(560, 585)) + list(range(933, 965))
    for addr in forward_ids:
      msg_name = None
      if addr == 282: msg_name = "FR_CMR_01_10ms"
      elif addr == 298: msg_name = "LFA"
      elif addr == 357: msg_name = "ADRV_0x165"
      elif addr == 416: msg_name = "SCC_CONTROL"
      elif addr == 437: msg_name = "CAMERA_0x1b5"
      elif addr == 480: msg_name = "LFAHDA_CLUSTER"
      elif addr == 506: msg_name = "ISLA"
      elif addr == 698: msg_name = "IFS_0x2ba"
      elif addr == 752: msg_name = "ID752"
      elif addr == 866: msg_name = "CAM_0x362"
      elif addr == 867: msg_name = "CAM_0x363"
      elif addr == 868: msg_name = "CAM_0x364"
      elif addr == 896: msg_name = "ADRV_0x380"
      elif addr == 905: msg_name = "ADRV_0x389"
      elif addr == 917: msg_name = "ID917"
      elif addr == 928: msg_name = "ID928"
      elif 560 <= addr <= 584:
        msg_name = "RADAR_0x240" if addr == 576 else f"HBA_0x{addr:03x}"
      elif 933 <= addr <= 964: msg_name = f"RADAR_TRACK_{addr}"

      if msg_name and msg_name in cp_cam.vl_all:
        vl_all_msg = cp_cam.vl_all[msg_name]
        sigs = list(vl_all_msg.keys())
        if sigs:
          for i in range(len(vl_all_msg[sigs[0]])):
            self.hda2_forward_msgs.append((msg_name, {s: vl_all_msg[s][i] for s in sigs}))

    # Car -> Camera Bus
    car_to_cam_ids = [53, 160, 234, 293, 304, 373, 426, 1041]
    for addr in car_to_cam_ids:
      msg_name = None
      if addr == 53: msg_name = "ACCELERATOR"
      elif addr == 160: msg_name = "WHEEL_SPEEDS"
      elif addr == 234: msg_name = "MDPS"
      elif addr == 293: msg_name = "STEERING_SENSORS"
      elif addr == 304: msg_name = "GEAR_SHIFTER"
      elif addr == 373: msg_name = "TCS"
      elif addr == 426: msg_name = "CRUISE_BUTTONS_ALT"
      elif addr == 1041: msg_name = "DOORS_SEATBELTS"

      # DOORS_SEATBELTS is on ACAN (Bus 0), others on ECAN (Bus 1)
      source_cp = cp_acan if addr in [1041] else cp

      if msg_name and msg_name in source_cp.vl_all:
        vl_all_msg = source_cp.vl_all[msg_name]
        sigs = list(vl_all_msg.keys())
        if sigs:
          for i in range(len(vl_all_msg[sigs[0]])):
            self.car_to_cam_forward_msgs.append((msg_name, {s: vl_all_msg[s][i] for s in sigs}))

    btn_dict = BUTTONS_DICT_EV4 if self.CP.carFingerprint == CAR.KIA_EV4 else BUTTONS_DICT
    lda_btn_type = ButtonType.lkas
    ret.buttonEvents = [*create_button_events(self.cruise_buttons[-1], prev_cruise_buttons, btn_dict),
                        *create_button_events(self.main_buttons[-1], prev_main_buttons, {1: ButtonType.mainCruise}),
                        *create_button_events(self.lda_button, prev_lda_button, {1: lda_btn_type})]

    if self.CP.carFingerprint == CAR.KIA_EV4:
      ret.blockPcmEnable = False
    else:
      ret.blockPcmEnable = not self.recent_button_interaction()

    if self.CP.carFingerprint == CAR.KIA_EV4:
      # Suppress "Door Open", "Seatbelt Unlatched", and "Gear not in Drive" alerts when not in cruise mode
      # This prevents annoying alerts while parked or idling.
      if not ret.cruiseState.available and ret.vEgo < 0.1:
        ret.doorOpen = False
        ret.seatbeltUnlatched = False
        if ret.gearShifter == structs.CarState.GearShifter.park:
          ret.gearShifter = structs.CarState.GearShifter.drive

    return ret

  def get_can_parsers_canfd(self, CP):
    msgs = [
      ("TCS", 100),
      ("WHEEL_SPEEDS", 100),
      ("MDPS", 100),
      ("CRUISE_BUTTONS_ALT", 50),
      ("BLINDSPOTS_REAR_CORNERS", float('nan')),
      ("SCC_CONTROL", 50),
      ("MANUAL_SPEED_LIMIT_ASSIST", float('nan')),
      ("LFAHDA_CLUSTER", 5),
    ]

    if CP.carFingerprint == CAR.KIA_EV4:
      msgs += [
        ("ACCELERATOR", 100),
        ("STEERING_SENSORS", 100),
        ("LFA_BUTTON", float('nan')),
        ("RADAR_TRACK_939", float('nan')),
      ]
    else:
      msgs += [
        ("ACCELERATOR", 100),
        ("STEERING_SENSORS", 100),
        ("DOORS_SEATBELTS", float('nan')),
        ("BLINKERS", float('nan')),
      ]
    if not (CP.flags & HyundaiFlags.CANFD_ALT_BUTTONS):
      # TODO: this can be removed once we add dynamic support to vl_all
      msgs += [
        # this message is 50Hz but the ECU frequently stops transmitting for ~0.5s
        ("CRUISE_BUTTONS", 1),
      ]
    pt_parser = CANParser(DBC[CP.carFingerprint][self.pt_bus], msgs, CanBus(CP).ECAN)

    cam_msgs = [
      ("CAM_0x362", float('nan')),
      ("CAM_0x363", float('nan')),
      ("CAM_0x364", float('nan')),
      ("CAM_0x2a4", float('nan')),
      ("ADRV_0x51", float('nan')),
      ("LFA", float('nan')),
      ("ADRV_0x160", float('nan')),
      ("SCC_CONTROL", float('nan')),
      ("LFAHDA_CLUSTER", float('nan')),
      ("ISLA", float('nan')),
      ("ACCELERATOR_BRAKE_ALT", float('nan')),
      ("FR_CMR_01_10ms", float('nan')),
      ("CAMERA_0x1b5", float('nan')),
      ("IFS_0x2ba", float('nan')),
      ("ID752", float('nan')),
      ("ID917", float('nan')),
      ("ID928", float('nan')),
      ("ID977", float('nan')),
      ("ID978", float('nan')),
      ("ID980", float('nan')),
      ("ID1280", float('nan')),
      ("LKAS_ALT", float('nan')),
    ]
    # HBA/ISLA etc
    for addr in range(560, 585):
        msg_name = "RADAR_0x240" if addr == 576 else f"HBA_0x{addr:03x}"
        cam_msgs.append((msg_name, float('nan')))

    if CP.carFingerprint == CAR.KIA_EV4:
      cam_msgs.append(("LFA_BUTTON", float('nan')))
      cam_msgs.append(("ID865", float('nan')))
    for addr in range(933, 965):
      cam_msgs.append((f"RADAR_TRACK_{addr}", float('nan')))

    a_msgs = []
    if CP.carFingerprint == CAR.KIA_EV4:
      a_msgs += [
        ("DOORS_SEATBELTS", float('nan')),
      ]

    a_parser = CANParser(DBC[CP.carFingerprint][self.pt_bus], a_msgs, CanBus(CP).ACAN)

    return {
      Bus.pt: a_parser,
      Bus.radar: a_parser,
      self.pt_bus: pt_parser,
      Bus.cam: CANParser(DBC[CP.carFingerprint][self.pt_bus], cam_msgs, CanBus(CP).CAM),
    }

  def get_can_parsers(self, CP):
    if CP.flags & HyundaiFlags.CANFD:
      return self.get_can_parsers_canfd(CP)

    return {
      Bus.pt: CANParser(DBC[CP.carFingerprint][Bus.pt], [], 0),
      Bus.cam: CANParser(DBC[CP.carFingerprint][Bus.pt], [], 2),
    }
