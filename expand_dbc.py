import sys
import os

dbc_path = 'opendbc/dbc/KIA_EV4_v19.dbc'
if not os.path.exists(dbc_path):
  print(f"Error: {dbc_path} not found")
  sys.exit(1)

with open(dbc_path, 'r', encoding='latin-1') as f:
  lines = f.readlines()

# All IDs seen on Bus 2 (Camera Bus) in the fingerprint with CORRECT lengths
ids_to_expand = {
  256: 24,  # ACCELERATOR_BRAKE_ALT (0x100) - Fingerprint says 24
  272: 32,  # LKAS_ALT (0x110)
  352: 16,  # ADRV_0x160 (0x160)
  357: 16,  # ADRV_0x165 - Fingerprint says 16
  437: 32,  # CAMERA_0x1b5 - Not on B2? But we'll keep as 32 if seen
  474: 16,  # ADRV_0x1da (0x1da)
  490: 32,  # ADRV_0x1ea (0x1ea)
  506: 32,  # ISLA
  512: 16,  # ADRV_0x200 (0x200)
  698: 32,  # IFS_0x2ba
  752: 8,  # 0x2f0
  811: 32,  # ADRV_0x32b (0x32b)
  813: 32,  # ADRV_0x32d (0x32d)
  816: 32,  # ADRV_0x330 (0x330)
  837: 16,  # ADRV_0x345 (0x345)
  864: 32,  # LFA_BUTTON (0x360)
  865: 32,  # 0x361
  866: 32,  # CAM_0x362
  867: 32,  # CAM_0x363
  868: 32,  # CAM_0x364
  896: 24,  # ADRV_0x380
  905: 24,  # ADRV_0x389
  917: 32,  # 0x395
  928: 32,  # 0x3a0
  976: 32,  # EV4_BODY_1 (0x3d0)
  977: 32,  # 0x3d1
  978: 32,  # 0x3d2
  979: 32,  # EV4_BODY_2 (0x3d3)
  980: 32,  # 0x3d4
  1280: 16,  # 0x500
  81: 16,   # ADRV_0x51 (0x51)
}

# HBA/ISLA range 0x230-0x248 (560-584)
for i in range(560, 585):
  if i == 560:
    ids_to_expand[i] = 16
  else:
    ids_to_expand[i] = 32

# Radar Tracks 933-964
for i in range(933, 965):
  ids_to_expand[i] = 24

# Steering signals to restore
lkas_alt_signals = """ SG_ LKA_MODE : 24|4@1+ (1,0) [0|15] "" XXX
 SG_ LKA_ICON : 28|4@1+ (1,0) [0|15] "" XXX
 SG_ TORQUE_REQUEST : 32|11@1- (1,0) [-1024|1023] "" XXX
 SG_ LKA_ASSIST : 43|1@1+ (1,0) [0|1] "" XXX
 SG_ STEER_REQ : 44|1@1+ (1,0) [0|1] "" XXX
 SG_ STEER_MODE : 45|3@1+ (1,0) [0|7] "" XXX
 SG_ HAS_LANE_SAFETY : 48|1@1+ (1,0) [0|1] "" XXX
 SG_ LKA_AVAILABLE : 27|2@1+ (1,0) [0|3] "" XXX
 SG_ CHECKSUM : 0|16@1+ (1,0) [0|65535] "" XXX
 SG_ COUNTER : 16|8@1+ (1,0) [0|255] "" XXX
"""

# BODY and BUTTON signals to restore
extra_signals = {
  864: """ SG_ LEFT_BLINKER : 0|8@1+ (1,0) [0|255] "" XXX
 SG_ RIGHT_BLINKER : 8|8@1+ (1,0) [0|255] "" XXX
 SG_ LFA_BTN : 16|1@1+ (1,0) [0|1] "" XXX
""",
  976: """ SG_ DRIVER_SEATBELT : 0|1@1+ (1,0) [0|1] "" XXX
 SG_ SPEED_REF_1 : 8|16@1+ (0.01,0) [0|655.35] "" XXX
""",
  979: """ SG_ DOOR_OPEN_ANY : 0|1@1+ (1,0) [0|1] "" XXX
""",
}

existing_names = {}
for line in lines:
  if line.startswith('BO_ '):
    parts = line.split()
    if len(parts) >= 3:
      msg_id = int(parts[1].strip(':'))
      existing_names[msg_id] = parts[2].strip(':')

new_lines = []
skip_signals = False
processed_ids = set()

for line in lines:
  if line.startswith('BO_ '):
    skip_signals = False
    parts = line.split()
    if len(parts) >= 2:
      try:
        msg_id = int(parts[1].strip(':'))
        if msg_id in ids_to_expand:
          length = ids_to_expand[msg_id]
          name = existing_names.get(msg_id, f"ID{msg_id}")
          new_lines.append(f"BO_ {msg_id} {name}: {length} XXX\n")
          if msg_id == 272:
            new_lines.append(lkas_alt_signals)
          if msg_id in extra_signals:
            new_lines.append(extra_signals[msg_id])
          for i in range(length):
            # Bit overlap prevention logic
            if msg_id == 976 and i in [0, 1, 2]:
              continue
            if msg_id == 979 and i == 0:
              continue
            if msg_id == 864 and i in [0, 1, 2]:
              continue  # Added 2 for LFA_BTN

            new_lines.append(f' SG_ BYTE{i} : {i * 8}|8@1+ (1,0) [0|255] "" XXX\n')
          skip_signals = True
          processed_ids.add(msg_id)
          continue
      except:
        pass
  if skip_signals and line.strip().startswith('SG_ '):
    continue
  new_lines.append(line)

for msg_id, length in ids_to_expand.items():
  if msg_id not in processed_ids:
    name = existing_names.get(msg_id, f"ID{msg_id}")
    new_lines.append(f"\nBO_ {msg_id} {name}: {length} XXX\n")
    if msg_id == 272:
      new_lines.append(lkas_alt_signals)
    if msg_id in extra_signals:
      new_lines.append(extra_signals[msg_id])
    for i in range(length):
      if msg_id == 976 and i in [0, 1, 2]:
        continue
      if msg_id == 979 and i == 0:
        continue
      if msg_id == 864 and i in [0, 1, 2]:
        continue
      new_lines.append(f' SG_ BYTE{i} : {i * 8}|8@1+ (1,0) [0|255] "" XXX\n')

with open(dbc_path, 'w', encoding='latin-1') as f:
  f.writelines(new_lines)
print(f"DBC expanded with restored signals for {len(extra_signals)} IDs (including SPEED_REF_1 and LFA_BTN).")
