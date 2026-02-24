#!/usr/bin/env python3
import sys
import csv
import collections

# Time window in nanoseconds (e.g., 2 seconds = 2e9)
WINDOW_NS = 2 * 1e9

def analyze_log(file_path, target_id=None, marker_filter=None):
  print(f"--- Analyzing Log: {file_path} ---")
  if target_id: print(f"Target ID: {target_id}")
  if marker_filter: print(f"Marker Filter: {marker_filter}")
  print("-" * 30)

  msg_history = collections.defaultdict(lambda: None)
  marker_timestamps = []

  # Step 1: Find all marker timestamps
  with open(file_path, "r") as f:
    reader = csv.DictReader(f)
    last_marker = ""
    for row in reader:
      marker = row["Marker"]
      if marker and marker != last_marker:
        if marker_filter is None or marker_filter in marker:
            marker_timestamps.append((int(row["Time"]), marker))
        last_marker = marker

  print(f"Found {len(marker_timestamps)} marker events.")

  # Step 2: Extract data around markers
  for ts, marker_name in marker_timestamps:
    print(f"\n[EVENT] Marker: {marker_name} at {ts}")
    print("-" * 50)

    with open(file_path, "r") as f:
      reader = csv.DictReader(f)
      for row in reader:
        row_ts = int(row["Time"])
        # Only process data within the window around the marker
        if abs(row_ts - ts) < WINDOW_NS:
          addr = int(row["Address"])
          if target_id and addr != target_id:
            continue

          data = row["Data"]
          prev_data = msg_history[addr]

          if prev_data and prev_data != data:
            b1 = bin(int(prev_data, 16))[2:].zfill(len(data)*4)
            b2 = bin(int(data, 16))[2:].zfill(len(data)*4)

            diff_bits = [f"B{i}:{bit1}->{bit2}" for i, (bit1, bit2) in enumerate(zip(b1, b2)) if bit1 != bit2]

            if diff_bits:
              rel_time = (row_ts - ts) / 1e6 # ms
              print(f"[{rel_time:+.2f}ms] ID:{addr} | {prev_data}->{data} | Bits: {', '.join(diff_bits)}")

          msg_history[addr] = data

if __name__ == "__main__":
  if len(sys.argv) < 2:
    print("Usage: python3 ev4_signal_hunter.py <log_file.csv> [target_id] [marker_filter]")
    sys.exit(1)

  target_id = int(sys.argv[2]) if len(sys.argv) > 2 else None
  marker_f = sys.argv[3] if len(sys.argv) > 3 else None

  analyze_log(sys.argv[1], target_id, marker_f)
