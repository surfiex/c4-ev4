#!/usr/bin/env python3
import json
import sys
import math
from collections import defaultdict

def full_scan(file_path):
    print(f"FULL SCAN (No Numpy) IN: {file_path}")

    # Reference: ID 160 (Wheel Speed FL)
    ref_ts = []
    ref_vals = []

    messages = []
    is_csv = file_path.endswith(".csv")

    with open(file_path, "r") as f:
        if is_csv:
            import csv
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                try:
                    m = {
                        "t": int(row["Time"]) / 1e9, # Convert ns to s if needed, but wheel speed logic expects match
                        "address": int(row["Address"]),
                        "data": row["Data"]
                    }
                    messages.append(m)
                except: continue
                if i > 100000: break
        else:
            for i, line in enumerate(f):
                try:
                    m = json.loads(line)
                    messages.append(m)
                except: continue
                if i > 100000: break

    # Build reference speed trace
    for m in messages:
        if m["address"] == 160:
            data = bytes.fromhex(m["data"])
            if len(data) >= 10:
                val = data[8] + ((data[9] & 0x3F) << 8)
                speed = val * 0.03125
                ref_ts.append(m["t"])
                ref_vals.append(speed)

    if not ref_vals:
        print("Error: Reference speed (ID 160) not found.")
        return

    print(f"Ref trace: {len(ref_vals)} pts. Range: {min(ref_vals):.2f}-{max(ref_vals):.2f}")

    # For every message, we want to correlate internal signals with the interpolated ref speed
    # To keep it simple, we'll look at Byte changes.

    candidates = defaultdict(list)
    for m in messages:
        addr = m["address"]
        if addr == 160: continue
        try:
            data = bytes.fromhex(m["data"])
        except: continue

        for b_idx in range(len(data)):
            candidates[(addr, b_idx)].append((m["t"], data[b_idx]))

        # Also check 16-bit (Little Endian)
        for b_idx in range(len(data) - 1):
            val16 = data[b_idx] | (data[b_idx+1] << 8)
            candidates[(addr, b_idx, "LE")].append((m["t"], val16))

    results = []

    for key, trace in candidates.items():
        if len(trace) < 100: continue

        vals = [v for ts, v in trace]
        v_min, v_max = min(vals), max(vals)
        if v_max - v_min < 5: continue

        # Correlation helper (Spearman-like rank or just trend matching)
        # We'll use simple interpolation and Pearson
        score = 0
        checks = 0

        # Downsample to match ref_ts roughly
        for ct, cv in trace[::2]:
            # Find nearest ref speed (naive search for now)
            # Find index of t in ref_ts
            found = False
            for j in range(len(ref_ts)-1):
                if ref_ts[j] <= ct <= ref_ts[j+1]:
                    ref_v = ref_vals[j]
                    checks += 1
                    # Basic direction check for correlation
                    # We compare against the start of the trace
                    if (cv - vals[0]) * (ref_v - ref_vals[0]) > 0:
                        score += 1
                    elif (cv - vals[0]) * (ref_v - ref_vals[0]) < 0:
                        score -= 1
                    found = True
                    break
            if found and checks > 200: break

        if checks > 50:
            match_rate = score / checks
            if abs(match_rate) > 0.7:
                results.append((key, match_rate, v_min, v_max))

    results.sort(key=lambda x: abs(x[1]), reverse=True)

    print("\n[Top Candidate Signals]")
    print(f"{'Key':<20} | {'Match':<6} | {'Range':<10}")
    print("-" * 45)
    for key, match, vmin, vmax in results[:25]:
        print(f"{str(key):<20} | {match:>6.2f} | {vmin:>3}-{vmax:<3}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 ev4_full_scan_hunter.py <log_file.jsonl>")
        sys.exit(1)
    full_scan(sys.argv[1])
