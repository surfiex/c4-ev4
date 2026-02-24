#!/usr/bin/env python3
import sys
import csv
import collections

def analyze_log(file_path, target_id=None, marker_filter=None):
  print(f"--- Analyzing Log: {file_path} ---")
  if target_id: print(f"Target ID: {target_id}")
  if marker_filter: print(f"Marker Filter: {marker_filter}")
  print("-" * 30)

  msg_history = collections.defaultdict(lambda: None)
  events = []

  with open(file_path, "r") as f:
    reader = csv.DictReader(f)
    for row in reader:
      addr = int(row["Address"])
      if target_id and addr != target_id:
        continue

      marker = row["Marker"]
      if marker_filter and marker_filter not in marker:
        continue

      data = row["Data"]
      timestamp = row["Time"]

      # Detect Bit Flips
      prev_data = msg_history[addr]
      if prev_data and prev_data != data:
        # Convert to bit strings for detailed diff
        b1 = bin(int(prev_data, 16))[2:].zfill(len(data)*4)
        b2 = bin(int(data, 16))[2:].zfill(len(data)*4)

        diff_bits = []
        for i, (bit1, bit2) in enumerate(zip(b1, b2)):
          if bit1 != bit2:
            diff_bits.append(f"Bit {i}: {bit1}->{bit2}")

        if diff_bits:
          print(f"[{timestamp}] ID: {addr} | Marker: {marker or 'None'}")
          print(f"  Prev: 0x{prev_data}")
          print(f"  Curr: 0x{data}")
          print(f"  Changes: {', '.join(diff_bits)}")
          print(f"  State: vEgo={row['vEgo']}, G:{row['Gas']}, B:{row['Brake']}, S:{row['SteerAngle']}")
          print("-" * 10)

      msg_history[addr] = data

if __name__ == "__main__":
  if len(sys.argv) < 2:
    print("Usage: python3 ev4_signal_hunter.py <log_file.csv> [target_id] [marker_filter]")
    sys.exit(1)

  target_id = int(sys.argv[2]) if len(sys.argv) > 2 else None
  marker_f = sys.argv[3] if len(sys.argv) > 3 else None

  analyze_log(sys.argv[1], target_id, marker_f)
