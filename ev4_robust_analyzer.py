#!/usr/bin/env python3
import json
import sys
from collections import defaultdict, Counter

def robust_analyze(file_path):
    print(f"ROBUST ANALYZING: {file_path}")

    bus_ids = defaultdict(Counter)
    total_lines = 0
    errors = 0

    with open(file_path, "r", errors='ignore') as f:
        for line in f:
            total_lines += 1
            try:
                # Clean the line - sometimes there's trailing garbage
                trimmed = line.strip()
                if not trimmed: continue

                # Try to find the JSON start
                start = trimmed.find('{')
                if start == -1: continue
                trimmed = trimmed[start:]

                # Try to find the JSON end (last brace)
                end = trimmed.rfind('}')
                if end == -1: continue
                trimmed = trimmed[:end+1]

                m = json.loads(trimmed)
                src = m.get("src")
                addr = m.get("address")
                if src is not None and addr is not None:
                    bus_ids[src][addr] += 1
            except Exception:
                errors += 1
                continue

            if total_lines % 1000000 == 0:
                print(f"Processed {total_lines} lines...")

    print(f"\nScan Complete. Total lines: {total_lines}, Errors: {errors}")

    for src in sorted(bus_ids.keys()):
        print(f"\n[BUS Source: {src}]")
        print(f"Found {len(bus_ids[src])} unique IDs")
        # Print all IDs in range 800-1000 (likely candidates for DMC/Radar)
        candidates = [addr for addr in bus_ids[src] if 800 <= addr <= 1000]
        if candidates:
            print("Candidate IDs (800-1000):")
            for addr in sorted(candidates):
                cnt = bus_ids[src][addr]
                # estimate hz if we know total time
                print(f"  0x{addr:03x} ({addr:<5}) : {cnt} hits")

        print("Top 10 IDs:")
        for addr, cnt in bus_ids[src].most_common(10):
            print(f"  0x{addr:03x} ({addr:<5}) : {cnt} hits")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python ev4_robust_analyzer.py <file.jsonl>")
    else:
        robust_analyze(sys.argv[1])
