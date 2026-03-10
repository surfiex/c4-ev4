import sys
import os
import re

dbc_path = 'opendbc/dbc/KIA_EV4_v19.dbc'
if not os.path.exists(dbc_path):
  print(f"Error: {dbc_path} not found")
  sys.exit(1)

with open(dbc_path, 'r', encoding='latin-1') as f:
  lines = f.readlines()

# All IDs seen on Bus 2 (Camera Bus) and Bus 1 (ADAS Bus)
# Mapping: msg_id -> (length, name)
ids_to_expand = {
  53: (32, "ACCELERATOR"),
  64: (32, "GEAR_ALT"),
  69: (24, "GEAR"),
  81: (16, "ADRV_0x51"),
  160: (24, "WHEEL_SPEEDS"),
  234: (32, "MDPS"),
  256: (24, "ACCELERATOR_BRAKE_ALT"),
  272: (32, "LKAS_ALT"),
  293: (32, "STEERING_SENSORS"),
  298: (32, "LFA"),
  304: (32, "GEAR_SHIFTER"),
  352: (16, "ADRV_0x160"),
  357: (16, "ADRV_0x165"),
  373: (16, "TCS"),
  416: (32, "SCC_CONTROL"),
  426: (16, "CRUISE_BUTTONS_ALT"),
  437: (32, "CAMERA_0x1b5"),
  442: (24, "BLINDSPOTS_REAR_CORNERS"),
  474: (16, "ADRV_0x1da"),
  480: (32, "LFAHDA_CLUSTER"),
  490: (32, "ADRV_0x1ea"),
  506: (32, "ISLA"),
  512: (16, "ADRV_0x200"),
  698: (32, "IFS_0x2ba"),
  752: (8, "ID752"),
  811: (32, "ADRV_0x32b"),
  813: (32, "ADRV_0x32d"),
  816: (32, "ADRV_0x330"),
  837: (16, "ADRV_0x345"),
  864: (32, "LFA_BUTTON"),
  865: (32, "ID865"),
  866: (32, "CAM_0x362"),
  867: (32, "CAM_0x363"),
  868: (32, "CAM_0x364"),
  896: (24, "ADRV_0x380"),
  905: (24, "ADRV_0x389"),
  917: (32, "ID917"),
  928: (32, "ID928"),
  976: (32, "EV4_BODY_1"),
  977: (32, "ID977"),
  978: (32, "ID978"),
  979: (32, "EV4_BODY_2"),
  980: (32, "ID980"),
  1041: (8, "DOORS_SEATBELTS"),
  1280: (16, "ID1280"),
}

# Add HBA/RADAR range (560-584)
for i in range(560, 585):
  name = "RADAR_0x240" if i == 576 else f"HBA_0x{i:03x}"
  ids_to_expand[i] = (16 if i == 560 else 32, name)

# Add Radar Tracks (933-964)
for i in range(933, 965):
  ids_to_expand[i] = (24, f"RADAR_TRACK_{i}")

# Custom signal definitions
extra_signals = {
  272: """ SG_ LKA_MODE : 24|4@1+ (1,0) [0|15] "" XXX
 SG_ LKA_ICON : 28|4@1+ (1,0) [0|15] "" XXX
 SG_ TORQUE_REQUEST : 32|11@1- (1,0) [-1024|1023] "" XXX
 SG_ LKA_ASSIST : 43|1@1+ (1,0) [0|1] "" XXX
 SG_ STEER_REQ : 44|1@1+ (1,0) [0|1] "" XXX
 SG_ STEER_MODE : 45|3@1+ (1,0) [0|7] "" XXX
 SG_ HAS_LANE_SAFETY : 48|1@1+ (1,0) [0|1] "" XXX
 SG_ LKA_AVAILABLE : 27|2@1+ (1,0) [0|3] "" XXX
 SG_ CHECKSUM : 0|16@1+ (1,0) [0|65535] "" XXX
 SG_ COUNTER : 16|8@1+ (1,0) [0|255] "" XXX
""",
  298: """ SG_ LKA_MODE : 24|4@1+ (1,0) [0|15] "" XXX
 SG_ LKA_ICON : 28|4@1+ (1,0) [0|15] "" XXX
 SG_ TORQUE_REQUEST : 32|11@1- (1,0) [-1024|1023] "" XXX
 SG_ LKA_ASSIST : 43|1@1+ (1,0) [0|1] "" XXX
 SG_ STEER_REQ : 44|1@1+ (1,0) [0|1] "" XXX
 SG_ STEER_MODE : 45|3@1+ (1,0) [0|7] "" XXX
 SG_ HAS_LANE_SAFETY : 48|1@1+ (1,0) [0|1] "" XXX
 SG_ LKA_AVAILABLE : 27|2@1+ (1,0) [0|3] "" XXX
 SG_ CHECKSUM : 0|16@1+ (1,0) [0|65535] "" XXX
 SG_ COUNTER : 16|8@1+ (1,0) [0|255] "" XXX
""",
  480: """ SG_ HDA_ICON : 24|2@1+ (1,0) [0|3] "" XXX
 SG_ LFA_ICON : 28|2@1+ (1,0) [0|3] "" XXX
 SG_ CHECKSUM : 0|16@1+ (1,0) [0|65535] "" XXX
 SG_ COUNTER : 16|8@1+ (1,0) [0|255] "" XXX
""",
  416: """ SG_ ACCMode : 68|3@1+ (1,0) [0|7] "" XXX
 SG_ CRUISE_STANDSTILL : 76|1@1+ (1,0) [0|1] "" XXX
 SG_ VSetDis : 103|8@0+ (1,0) [0|255] "" XXX
 SG_ aReqValue : 128|11@1+ (0.01,-10.23) [-10.23|10.24] "m/s^2" XXX
 SG_ aReqRaw : 140|11@1+ (0.01,-10.23) [-10.23|10.24] "m/s^2" XXX
 SG_ CHECKSUM : 0|16@1+ (1,0) [0|65535] "" XXX
 SG_ COUNTER : 16|8@1+ (1,0) [0|255] "" XXX
""",
  864: """ SG_ LEFT_BLINKER : 0|8@1+ (1,0) [0|255] "" XXX
 SG_ RIGHT_BLINKER : 8|8@1+ (1,0) [0|255] "" XXX
 SG_ LFA_BTN : 16|1@1+ (1,0) [0|1] "" XXX
""",
  976: """ SG_ DRIVER_SEATBELT : 0|1@1+ (1,0) [0|1] "" XXX
 SG_ SPEED_REF_1 : 8|16@1+ (0.01,0) [0|655.35] "" XXX
""",
  979: """ SG_ DOOR_OPEN_ANY : 0|1@1+ (1,0) [0|1] "" XXX
""",
  53: """ SG_ ACCELERATOR_PEDAL : 40|8@1+ (1,0) [0|255] "" XXX
 SG_ GEAR : 192|3@1+ (1,0) [0|7] "" XXX
 SG_ CHECKSUM : 0|16@1+ (1,0) [0|65535] "" XXX
 SG_ COUNTER : 16|8@1+ (1,0) [0|255] "" XXX
""",
  304: """ SG_ PARK_BUTTON : 32|2@1+ (1,0) [0|3] "" XXX
 SG_ KNOB_POSITION : 40|3@1+ (1,0) [0|3] "" XXX
 SG_ GEAR : 64|3@1+ (1,0) [0|7] "" XXX
 SG_ CHECKSUM : 0|16@1+ (1,0) [0|65535] "" XXX
 SG_ COUNTER : 16|8@1+ (1,0) [0|255] "" XXX
""",
  64: """ SG_ GEAR : 32|3@1+ (1,0) [0|7] "" XXX
 SG_ CHECKSUM : 0|16@1+ (1,0) [0|65535] "" XXX
 SG_ COUNTER : 16|8@1+ (1,0) [0|255] "" XXX
""",
  69: """ SG_ GEAR : 8|3@1+ (1,0) [0|7] "" XXX
""",
  426: """ SG_ DISTANCE_UNIT : 30|1@1+ (1,0) [0|1] "" XXX
 SG_ CRUISE_BUTTONS : 36|3@1+ (1,0) [0|4] "" XXX
 SG_ LDA_BTN : 39|1@1+ (1,0) [0|1] "" XXX
 SG_ CHECKSUM : 0|16@1+ (1,0) [0|65535] "" XXX
 SG_ COUNTER : 16|8@1+ (1,0) [0|255] "" XXX
""",
}

# Parse existing BO_ blocks into a unique dictionary to prevent duplicates
messages = {}
current_msg_id = None
header_lines = [] # Pre-BO_ lines

i = 0
while i < len(lines):
  line = lines[i]
  if line.startswith('BO_ '):
    parts = line.split()
    if len(parts) >= 2:
      try:
        current_msg_id = int(parts[1].strip(':'))
        if current_msg_id not in messages:
            messages[current_msg_id] = [line]
            i += 1
            while i < len(lines) and (not lines[i].strip() or lines[i].startswith(' ') or lines[i].startswith('SG_ ')):
              if lines[i].strip() or lines[i].startswith(' ') or lines[i].startswith('SG_ '):
                 messages[current_msg_id].append(lines[i])
              i += 1
            continue
        else:
            # Duplicate section found for current_msg_id. SKIP IT completely.
            i += 1
            while i < len(lines) and (not lines[i].strip() or lines[i].startswith(' ') or lines[i].startswith('SG_ ')):
              i += 1
            continue
      except ValueError:
        pass
  elif not messages:
    header_lines.append(line)
  i += 1

# Process expansions - Override existing or Add new
for msg_id, (length, name) in ids_to_expand.items():
  msg_lines = [f"BO_ {msg_id} {name}: {length} XXX\n"]
  if msg_id in extra_signals:
    msg_lines.append(extra_signals[msg_id])
  
  # Add generic BYTE signals while avoiding overlaps
  for b in range(length):
    if msg_id == 272 and b in [0, 1, 2, 3, 4, 5, 6]: continue
    if msg_id == 298 and b in [0, 1, 2, 3, 4, 5, 6]: continue
    if msg_id == 480 and b in [0, 1, 2, 3]: continue
    if msg_id == 416 and b in [0, 1, 2, 8, 9, 12, 16, 17, 18, 19, 20]: continue
    if msg_id == 864 and b in [0, 1, 2]: continue
    if msg_id == 976 and b in [0, 1, 2]: continue
    if msg_id == 979 and b in [0]: continue
    if msg_id == 53 and b in [0, 1, 2, 5, 24]: continue
    if msg_id == 304 and b in [0, 1, 2, 4, 5, 8]: continue
    if msg_id == 64 and b in [0, 1, 2, 4]: continue
    if msg_id == 69 and b in [0, 1]: continue
    if msg_id == 426 and b in [0, 1, 2, 3, 4, 5]: continue
    msg_lines.append(f' SG_ BYTE{b} : {b * 8}|8@1+ (1,0) [0|255] "" XXX\n')
  
  messages[msg_id] = msg_lines

# Write back
with open(dbc_path, 'w', encoding='latin-1') as f:
  f.writelines(header_lines)
  for msg_id in sorted(messages.keys()):
    f.writelines(messages[msg_id])
    f.write('\n')
  
  # Add value tables (VAL_)
  # Gear mappings: 1:P, 2:R, 3:N, 4:D
  f.write('VAL_ 53 GEAR 1 "P" 2 "R" 3 "N" 4 "D" ;\n')
  f.write('VAL_ 304 GEAR 1 "P" 2 "R" 3 "N" 4 "D" ;\n')
  f.write('VAL_ 64 GEAR 1 "P" 2 "R" 3 "N" 4 "D" ;\n')
  f.write('VAL_ 69 GEAR 1 "P" 2 "R" 3 "N" 4 "D" ;\n')

print(f"DBC cleaned and expanded. Total unique messages: {len(messages)}")
