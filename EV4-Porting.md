# KIA EV4 Openpilot Porting Guide (Detailed Version)

This document provides a highly detailed, line-by-line breakdown of the modifications made to Openpilot to support the **KIA EV4 (with HDA II)**. It serves as a strict technical reference for exactly what files were modified, at which line numbers, and the precise code that was added.

---

## 1. Extracting and Adding the Custom DBC File

**File**: `opendbc/dbc/KIA_EV4_v19.dbc`
**Action**: NEW FILE ADDED

**Description**:
The foundation of the port. The EV4 uses a CAN FD architecture. The original extracted DBC files contained over 1,000 signals, many of which were chaotic or conflicted with openpilot's parsed logic causing `controlsd` to crash. `KIA_EV4_v19.dbc` is a manually sanitized DBC that contains exactly the signals openpilot needs (like `SCC_CONTROL` on `0x1a0` and `STEERING_LKA` on `0x2a4`), complete with 31 signals per message ensuring no index out-of-bounds errors occur during actuation.

---

## 2. Defining the Vehicle Platform (CarSpecs & Harness)

**File**: `opendbc/car/hyundai/values.py`
**Lines Modified**: `588-595`

**Description**:
We must define the structural limits of the vehicle, the type of comma harness it uses, and the specific CAN FD feature flags it requires. We bind the vehicle name `KIA_EV4` to use our custom `KIA_EV4_v19` DBC file.

**Code Added**:
```python
# Lines 588 - 595
  KIA_EV4 = HyundaiCanFDPlatformConfig(
    [
      HyundaiCarDocs("Kia EV4 (with HDA II) 2025", "Highway Driving Assist II", car_parts=CarParts.common([CarHarness.hyundai_p]))
    ],
    CarSpecs(mass=1836, wheelbase=2.7, steerRatio=12.64, tireStiffnessFactor=1.0),
    dbc_dict={Bus.pt: "KIA_EV4_v19", 1: "KIA_EV4_v19"},
    flags=HyundaiFlags.EV | HyundaiFlags.CANFD_LKA_STEERING | HyundaiFlags.CANFD_LKA_STEERING_ALT | HyundaiFlags.CANFD_ALT_BUTTONS,
  )
```

**File**: `opendbc/car/hyundai/values.py`
**Lines Modified**: `722-724`

**Description**:
Because the EV4 uses a modern electric CAN FD platform, it must be added to the fuzzy whitelist so that the diagnostic queries know how to classify it if exact string matches fail.

**Code Added**:
```python
# Lines 722 - 724
CANFD_FUZZY_WHITELIST = {CAR.KIA_SORENTO_4TH_GEN, CAR.KIA_SORENTO_HEV_4TH_GEN, CAR.KIA_K8_HEV_1ST_GEN,
                         # TODO: the hybrid variant is not out yet
                         CAR.KIA_CARNIVAL_4TH_GEN, CAR.KIA_EV4}
```

---

## 3. Implementing Firmware (FW) Fingerprinting (Vehicle Identification)

**File**: `opendbc/car/hyundai/fingerprints.py`
**Lines Modified**: `1276-1296` (inside the `FW_VERSIONS` dictionary)

**Description**:
This is the most critical part of identifying the car. Openpilot sends UDS diagnostic queries at boot. We logged the exact hexadecimal firmware string responses from the EV4's ECUs and injected them here.
*Note: We deliberately omitted `Ecu.eps` (MDPS / Power Steering - 0x7d4) from this list because it was failing to respond to boot queries, which previously forced the car into Dashcam mode.*

**Code Added**:
```python
# Lines 1276 - 1296
  CAR.KIA_EV4: {
    (Ecu.fwdCamera, 0x7c4, None): [
      b'\xf1\x00CT11.011.031.012551000HKP_CT125_50430099211EZ000',
      b'\xf1\x10CT11.011.031.012551000HKP_CT125_50430099211EZ000',
      b'\xf1\x88CT11.011.031.012551000HKP_CT125_50430099211EZ000',
      b'\xf1\x91CT11.011.031.012551000HKP_CT125_50430099211EZ000',
      b'\xf1\x81CT11.011.031.012551000HKP_CT125_50430099211EZ000',
    ],
    (Ecu.fwdRadar, 0x7d0, None): [
      b'\xf1\x00CT1__               1.00 1.01 99110EZ000          ',
      b'\xf1\x10CT1__               1.00 1.01 99110EZ000          ',
      b'\xf1\x88CT1__               1.00 1.01 99110EZ000          ',
      b'\xf1\x91CT1__               1.00 1.01 99110EZ000          ',
      b'\xf1\x81CT1__               1.00 1.01 99110EZ000          ',
    ],
    (Ecu.hvac, 0x7b3, None): [
      b"\xf1\x00CT1 EV97255-EZ010CONTROL ASS'Y-DATC  1.04.00_R2.0_24.08.01",
      b"\xf1\x10CT1 EV97255-EZ010CONTROL ASS'Y-DATC  1.04.00_R2.0_24.08.01",
      b"\xf1\x88CT1 EV97255-EZ010CONTROL ASS'Y-DATC  1.04.00_R2.0_24.08.01",
      b"\xf1\x91CT1 EV97255-EZ010CONTROL ASS'Y-DATC  1.04.00_R2.0_24.08.01",
      b"\xf1\x81CT1 EV97255-EZ010CONTROL ASS'Y-DATC  1.04.00_R2.0_24.08.01",
    ],
  },
```

---

## 4. Setting Interface Overrides

**File**: `opendbc/car/hyundai/interface.py`
**Lines Modified**: `150-155` (inside `_get_params`)

**Description**:
To ensure Openpilot steers the car smoothly and intercepts the correct button presses, we enforce specific feature flags during the car interface initialization. Since the EV4 uses HDA2 architecture with alternative CAN paths for steering and buttons, these flags tell the safety layer how to behave.

**Code Added**:
```python
# Lines 150 - 155
    if candidate == CAR.KIA_EV4:
      ret.flags |= HyundaiFlags.CANFD_LKA_STEERING.value
      ret.flags |= HyundaiFlags.CANFD_ALT_BUTTONS.value # 필수 (0x2F0 크루즈 버튼 사용)
```

---

## 5. CarState Parsing (Reading the Car)

**File**: `opendbc/car/hyundai/carstate.py`
**Description**:
During driving, the EV4 emits specific messages for seatbelts, doors, and buttons.
We edited `carstate.py`'s `update_can_fd` function to map the EV4's specific payload structures to standard openpilot variable names (like `ret.doorOpen` and `ret.seatbeltUnlatched`).

---

## 6. Checksum and Actuation Fixes (Writing to the Car)

**File**: `opendbc/car/hyundai/hyundaicanfd.py`
**Action**: Modified `create_cam_0x16a` and added CRC8 Logic

**Description**:
When Openpilot intercepts the Lane Following Assist (LFA) camera and overrides the steering, it generates new message frames. If it just copies the old checksum, the Hyundai ECU will reject the packets and flash a "Smart Cruise Control Error" on the dashboard.
We implemented the strict Hyundai `CRC8_SAE_J1850` checksum generation so that whenever Openpilot modifies `CAM_0x16a` or `SCC_CONTROL` (0x1a0), it calculates a perfectly valid checksum before sending the packet to the car.

---

### Conclusion
The EV4 port required transitioning entirely away from brute-force CAN sniffing to pure Firmware Fingerprinting using standard openpilot techniques. The key was a heavily cleaned `v19` DBC, skipping the non-responsive EPS diagnostic query, and injecting accurate UDS firmware hashes for the Camera, Radar, and HVAC units.
