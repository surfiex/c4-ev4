import copy
import numpy as np
from opendbc.car import CanBusBase
from opendbc.car.crc import CRC16_XMODEM
from opendbc.car.hyundai.values import HyundaiFlags


class CanBus(CanBusBase):
  def __init__(self, CP, fingerprint=None, lka_steering=None) -> None:
    super().__init__(CP, fingerprint)

    if lka_steering is None:
      lka_steering = CP.flags & HyundaiFlags.CANFD_LKA_STEERING.value if CP is not None else False

    # On the CAN-FD platforms, the LKAS camera is on both A-CAN and E-CAN. LKA steering cars
    # have a different harness than the LFA steering variants in order to split
    # a different bus, since the steering is done by different ECUs.
    self._a, self._e = 1, 0
    if lka_steering:
      self._a, self._e = 0, 1

    self._a += self.offset
    self._e += self.offset
    self._cam = 2 + self.offset

  @property
  def ECAN(self):
    return self._e

  @property
  def ACAN(self):
    return self._a

  @property
  def CAM(self):
    return self._cam


def create_steering_messages(packer, CP, CAN, enabled, lat_active, apply_torque, lkas_alt_msg=None):
  # 1. Initialize values from the original camera message if available
  if lkas_alt_msg:
    lkas_values = {f"BYTE{i}": lkas_alt_msg[f"BYTE{i}"] for i in range(32)}
  else:
    lkas_values = {f"BYTE{i}": 0 for i in range(32)}

  # 2. Update specific signals for Openpilot's lateral control
  lkas_values.update({
    "LKA_MODE": 2 if lat_active else lkas_values.get("LKA_MODE", 0),
    "LKA_ICON": 4 if enabled else lkas_values.get("LKA_ICON", 1), # EV4/HDA2 icon enums may vary; 4 is often Green
    "TORQUE_REQUEST": apply_torque,
    "LKA_ASSIST": lkas_values.get("LKA_ASSIST", 0),
    "STEER_REQ": 1 if lat_active else 0,
    "STEER_MODE": lkas_values.get("STEER_MODE", 0),
    "HAS_LANE_SAFETY": 0,  # hide LKAS settings
    "LKA_AVAILABLE": lkas_values.get("LKA_AVAILABLE", 3),
  })

  ret = []
  if CP.flags & HyundaiFlags.CANFD_LKA_STEERING:
    lkas_msg = "LKAS_ALT" if CP.flags & HyundaiFlags.CANFD_LKA_STEERING_ALT else "LKAS"

    if CP.carFingerprint == "KIA_EV4" and lkas_msg == "LKAS_ALT":
      # EV4 Special: Manually pack to ensure CRC and Counter integrity for dual-bus MITM

      # A) Modified OP message to ACAN (Bus 0) - This is what the MDPS sees
      _, dat_raw, _ = packer.make_can_msg(lkas_msg, 0, lkas_values)
      dat = bytearray(dat_raw)
      crc = hkg_can_fd_checksum(0x110, None, dat)
      dat[0] = crc & 0xFF
      dat[1] = (crc >> 8) & 0xFF
      ret.append([0x110, bytes(dat), CAN.ACAN])

      # B) Original CAMERA message to ECAN (Bus 1) - This keeps the ADAS ECU happy but Inactive
      # Crucial for HDA2: ADAS ECU must see the camera signal but stay out of our way.
      if lkas_alt_msg:
        orig_values = {f"BYTE{i}": lkas_alt_msg[f"BYTE{i}"] for i in range(32)}
        _, dat_orig, _ = packer.make_can_msg(lkas_msg, 0, orig_values)
        dat_o = bytearray(dat_orig)
        crc_o = hkg_can_fd_checksum(0x110, None, dat_o)
        dat_o[0] = crc_o & 0xFF
        dat_o[1] = (crc_o >> 8) & 0xFF
        ret.append([0x110, bytes(dat_o), CAN.ECAN])
    else:
      ret.append(packer.make_can_msg(lkas_msg, CAN.ACAN, lkas_values))

    # Send LFA for longitudinal cars OR if it's an EV4 needing heartbeats
    if CP.openpilotLongitudinalControl or CP.carFingerprint == "KIA_EV4":
      if CP.carFingerprint == "KIA_EV4":
        _, dat_raw, _ = packer.make_can_msg("LFA", CAN.ECAN, lkas_values)
        dat = bytearray(dat_raw)
        crc = hkg_can_fd_checksum(298, None, dat)
        dat[0] = crc & 0xFF
        dat[1] = (crc >> 8) & 0xFF
        ret.append([298, bytes(dat), CAN.ECAN])
      else:
        ret.append(packer.make_can_msg("LFA", CAN.ECAN, lkas_values))

  else:
    if CP.carFingerprint == "KIA_EV4":
      _, dat_raw, _ = packer.make_can_msg("LFA", CAN.ECAN, lkas_values)
      dat = bytearray(dat_raw)
      crc = hkg_can_fd_checksum(298, None, dat)
      dat[0] = crc & 0xFF
      dat[1] = (crc >> 8) & 0xFF
      ret.append([298, bytes(dat), CAN.ECAN])
    else:
      ret.append(packer.make_can_msg("LFA", CAN.ECAN, lkas_values))

  return ret

def create_suppress_lfa(packer, CAN, lfa_block_msg, lka_steering_alt, car_fingerprint):
  suppress_msg = "CAM_0x362" if lka_steering_alt else "CAM_0x2a4"
  msg_bytes = 32 if lka_steering_alt else 24

  # Use only BYTEi signals for raw compatibility with EV4 DBC
  values = {f"BYTE{i}": lfa_block_msg.get(f"BYTE{i}", 0) for i in range(msg_bytes)}
  
  # Suppression: Zero out all bytes that typically contain lane line information.
  # For HDA2 (0x362/0x2a4), Bytes 0-1 are Checksum and Byte 2 is Counter.
  # We preserve these and zero out Bytes 3+ to disable lane-following logic in ADAS ECU.
  for i in range(3, msg_bytes):
    values[f"BYTE{i}"] = 0

  # EV4: Send to ECAN (Bus 1) where ADAS ECU lives.
  bus = CAN.ECAN if car_fingerprint == "KIA_EV4" else CAN.ACAN
  _, dat_raw, _ = packer.make_can_msg(suppress_msg, bus, values)
  dat = bytearray(dat_raw)
  crc = hkg_can_fd_checksum(866 if lka_steering_alt else 676, None, dat)
  dat[0] = crc & 0xFF
  dat[1] = (crc >> 8) & 0xFF
  return [866 if lka_steering_alt else 676, bytes(dat), bus]


def create_buttons(packer, CP, CAN, cnt, btn):
  values = {
    "COUNTER": cnt,
    "SET_ME_1": 1,
    "CRUISE_BUTTONS": btn,
  }

  bus = CAN.ECAN if CP.flags & HyundaiFlags.CANFD_LKA_STEERING else CAN.CAM
  return packer.make_can_msg("CRUISE_BUTTONS", bus, values)


def create_acc_cancel(packer, CP, CAN, cruise_info_copy):
  # TODO: why do we copy different values here?
  if CP.flags & HyundaiFlags.CANFD_CAMERA_SCC.value:
    values = {s: cruise_info_copy[s] for s in [
      "COUNTER",
      "CHECKSUM",
      "NEW_SIGNAL_1",
      "MainMode_ACC",
      "ACCMode",
      "ZEROS_9",
      "CRUISE_STANDSTILL",
      "ZEROS_5",
      "DISTANCE_SETTING",
      "VSetDis",
    ]}
  else:
    values = {s: cruise_info_copy[s] for s in [
      "COUNTER",
      "CHECKSUM",
      "ACCMode",
      "VSetDis",
      "CRUISE_STANDSTILL",
    ]}
  values.update({
    "ACCMode": 4,
    "aReqRaw": 0.0,
    "aReqValue": 0.0,
  })
  if CP.carFingerprint == "KIA_EV4":
    _, dat_raw, _ = packer.make_can_msg("SCC_CONTROL", CAN.ECAN, values)
    dat = bytearray(dat_raw)
    crc = hkg_can_fd_checksum(416, None, dat)
    dat[0] = crc & 0xFF
    dat[1] = (crc >> 8) & 0xFF
    return [416, bytes(dat), CAN.ECAN]
  return packer.make_can_msg("SCC_CONTROL", CAN.ECAN, values)


def create_lfahda_cluster(packer, CAN, enabled, cnt=None):
  values = {
    "HDA_ICON": 1, # white
    "LFA_ICON": 2 if enabled else 1, # 2: green, 1: white
    # EV4 cluster validates bytes 8-15; stock value: fe f7 0f 00 00 00 f0 bf
    "BYTE8": 0xfe,
    "BYTE9": 0xf7,
    "BYTE10": 0x0f,
    "BYTE11": 0x00,
    "BYTE12": 0x00,
    "BYTE13": 0x00,
    "BYTE14": 0xf0,
    "BYTE15": 0xbf,
  }

  if cnt is not None:
    values["COUNTER"] = cnt % 256
  # CHECKSUM is manually calculated for EV4
  _, dat_raw, _ = packer.make_can_msg("LFAHDA_CLUSTER", CAN.ECAN, values)
  dat = bytearray(dat_raw)
  crc = hkg_can_fd_checksum(480, None, dat)
  dat[0] = crc & 0xFF
  dat[1] = (crc >> 8) & 0xFF
  return [480, bytes(dat), CAN.ECAN]


def create_acc_control(packer, CAN, enabled, accel_last, accel, stopping, gas_override, set_speed, hud_control):
  jerk = 5
  jn = jerk / 50
  if not enabled or gas_override:
    a_val, a_raw = 0, 0
  else:
    a_raw = accel
    a_val = np.clip(accel, accel_last - jn, accel_last + jn)

  values = {
    "ACCMode": 0 if not enabled else (2 if gas_override else 1),
    "MainMode_ACC": 1,
    "StopReq": 1 if stopping else 0,
    "aReqValue": a_val,
    "aReqRaw": a_raw,
    "VSetDis": set_speed,
    "JerkLowerLimit": jerk if enabled else 1,
    "JerkUpperLimit": 3.0,

    "ACC_ObjDist": 1,
    "ObjValid": 0,
    "OBJ_STATUS": 2,
    "SET_ME_2": 0x4,
    "SET_ME_3": 0x3,
    "SET_ME_TMP_64": 0x64,
    "DISTANCE_SETTING": hud_control.leadDistanceBars,
  }

  return packer.make_can_msg("SCC_CONTROL", CAN.ECAN, values)


def create_spas_messages(packer, CAN, left_blink, right_blink):
  ret = []

  values = {
  }
  ret.append(packer.make_can_msg("SPAS1", CAN.ECAN, values))

  blink = 0
  if left_blink:
    blink = 3
  elif right_blink:
    blink = 4
  values = {
    "BLINKER_CONTROL": blink,
  }
  ret.append(packer.make_can_msg("SPAS2", CAN.ECAN, values))

  return ret


def create_fca_warning_light(packer, CAN, frame):
  ret = []

  if frame % 2 == 0:
    values = {
      'AEB_SETTING': 0x1,  # show AEB disabled icon
      'SET_ME_2': 0x2,
      'SET_ME_FF': 0xff,
      'SET_ME_FC': 0xfc,
      'SET_ME_9': 0x9,
    }
    ret.append(packer.make_can_msg("ADRV_0x160", CAN.ECAN, values))
  return ret


def create_adrv_messages(packer, CAN, frame):
  # messages needed to car happy after disabling
  # the ADAS Driving ECU to do longitudinal control

  ret = []

  values = {
  }
  ret.append(packer.make_can_msg("ADRV_0x51", CAN.ACAN, values))

  ret.extend(create_fca_warning_light(packer, CAN, frame))

  if frame % 5 == 0:
    values = {
      'SET_ME_1C': 0x1c,
      'SET_ME_FF': 0xff,
      'SET_ME_TMP_F': 0xf,
      'SET_ME_TMP_F_2': 0xf,
    }
    ret.append(packer.make_can_msg("ADRV_0x1ea", CAN.ECAN, values))

    values = {
      'SET_ME_E1': 0xe1,
      'SET_ME_3A': 0x3a,
    }
    ret.append(packer.make_can_msg("ADRV_0x200", CAN.ECAN, values))

  if frame % 20 == 0:
    values = {
      'SET_ME_15': 0x15,
    }
    ret.append(packer.make_can_msg("ADRV_0x345", CAN.ECAN, values))

  if frame % 100 == 0:
    values = {
      'SET_ME_22': 0x22,
      'SET_ME_41': 0x41,
    }
    ret.append(packer.make_can_msg("ADRV_0x1da", CAN.ECAN, values))

  return ret


def create_adrv_messages_ev4(packer, CAN, frame):
  # Messages needed to keep the EV4 happy after disabling
  # the ADAS Driving ECU to do longitudinal control
  ret = []

  # ADRV_0x51 - 100Hz heartbeat on ACAN
  values = {}
  ret.append(packer.make_can_msg("ADRV_0x51", CAN.ACAN, values))

  # ADRV_0x160 (50Hz) - counter increments +1 per send
  if frame % 2 == 0:
    cnt_160 = (frame // 2) % 256
    values = {}
    dat = bytearray(packer.make_can_msg("ADRV_0x160", CAN.ECAN, values)[1])
    dat[2] = cnt_160    # COUNTER byte
    dat[4] = 0x80
    dat[8] = 0xff
    dat[9] = 0xfc
    dat[10] = 0x01
    dat[12] = 0xa8
    dat[14] = 0x10
    crc = hkg_can_fd_checksum(0x160, None, dat)
    dat[0] = crc & 0xFF
    dat[1] = (crc >> 8) & 0xFF
    ret.append([0x160, bytes(dat), CAN.ECAN])

  if frame % 5 == 0:
    cnt_20hz = (frame // 5) % 256

    # 0x1ea (490) 20Hz
    values = {}
    dat = bytearray(packer.make_can_msg("ADRV_0x1ea", CAN.ECAN, values)[1])
    dat[2] = cnt_20hz   # COUNTER byte
    dat[3] = 0x08
    dat[15] = 0xff
    dat[29] = 0x0f
    dat[30] = 0x0f
    crc = hkg_can_fd_checksum(0x1ea, None, dat)
    dat[0] = crc & 0xFF
    dat[1] = (crc >> 8) & 0xFF
    ret.append([0x1ea, bytes(dat), CAN.ECAN])

    # 0x200 (512) 20Hz
    values = {}
    dat = bytearray(packer.make_can_msg("ADRV_0x200", CAN.ECAN, values)[1])
    dat[2] = cnt_20hz   # COUNTER byte
    dat[3] = 0x14
    dat[4] = 0x80
    dat[5] = 0x29       # was 0x2a, corrected from real vehicle log
    crc = hkg_can_fd_checksum(0x200, None, dat)
    dat[0] = crc & 0xFF
    dat[1] = (crc >> 8) & 0xFF
    ret.append([0x200, bytes(dat), CAN.ECAN])

  if frame % 20 == 0:
    # 0x345 (837) 5Hz
    cnt_5hz = (frame // 20) % 256
    values = {}
    dat = bytearray(packer.make_can_msg("ADRV_0x345", CAN.ECAN, values)[1])
    dat[2] = cnt_5hz    # COUNTER byte
    dat[3] = 0x15
    dat[5] = 0xd6
    dat[6] = 0x01
    crc = hkg_can_fd_checksum(0x345, None, dat)
    dat[0] = crc & 0xFF
    dat[1] = (crc >> 8) & 0xFF
    ret.append([0x345, bytes(dat), CAN.ECAN])

    # 0x330 (816) 5Hz - scene/radar status (counter rate = 10Hz → +2 per 5Hz send)
    cnt_10hz = (frame // 10) % 256
    dat = bytearray(32)
    dat[2] = cnt_10hz
    dat[3] = 0xf1
    dat[4] = 0xc8; dat[5] = 0xa0; dat[6] = 0xfc; dat[7] = 0x9e
    dat[8] = 0xdc; dat[9] = 0x05; dat[10] = 0xdc; dat[11] = 0x05
    # bytes 12-18 = 0x00
    dat[19] = 0x5c; dat[20] = 0x0d; dat[21] = 0x70; dat[22] = 0x0f
    dat[23] = 0xc8; dat[24] = 0xa0
    # bytes 25-27 = 0x00
    dat[28] = 0x97; dat[29] = 0x94; dat[30] = 0x04; dat[31] = 0x74
    crc = hkg_can_fd_checksum(0x330, None, dat)
    dat[0] = crc & 0xFF
    dat[1] = (crc >> 8) & 0xFF
    ret.append([0x330, bytes(dat), CAN.ECAN])

    # 0x32b (811) 5Hz - completely static from vehicle log (counter never changes)
    dat_32b = bytes.fromhex("d4100a0000000080000000000000004000002100000000000000000000000000")
    ret.append([0x32b, dat_32b, CAN.ECAN])

    # 0x32d (813) 5Hz - completely static from vehicle log (counter never changes)
    dat_32d = bytes.fromhex("b5a70b0000000080000000000000000000000440040000000000210000000000")
    ret.append([0x32d, dat_32d, CAN.ECAN])

  if frame % 100 == 0:
    # 0x1da (474) 1Hz
    cnt_1hz = (frame // 100) % 256
    values = {}
    dat = bytearray(packer.make_can_msg("ADRV_0x1da", CAN.ECAN, values)[1])
    dat[2] = cnt_1hz    # COUNTER byte
    dat[3] = 0x67
    dat[5] = 0x31
    crc = hkg_can_fd_checksum(0x1da, None, dat)
    dat[0] = crc & 0xFF
    dat[1] = (crc >> 8) & 0xFF
    ret.append([0x1da, bytes(dat), CAN.ECAN])

  return ret


def hkg_can_fd_checksum(address: int, sig, d) -> int:
  if not isinstance(d, (bytes, bytearray)):
    return 0

  crc = 0
  for i in range(2, len(d)):
    crc = ((crc << 8) ^ CRC16_XMODEM[(crc >> 8) ^ d[i]]) & 0xFFFF
  crc = ((crc << 8) ^ CRC16_XMODEM[(crc >> 8) ^ ((address >> 0) & 0xFF)]) & 0xFFFF
  crc = ((crc << 8) ^ CRC16_XMODEM[(crc >> 8) ^ ((address >> 8) & 0xFF)]) & 0xFFFF
  if len(d) == 8:
    crc ^= 0x5F29
  elif len(d) == 16:
    crc ^= 0x041D
  elif len(d) == 24:
    crc ^= 0x819D
  elif len(d) == 32:
    crc ^= 0x9F5B
  return crc
