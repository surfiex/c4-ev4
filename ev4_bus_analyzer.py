#!/usr/bin/env python3
import json
import sys
from collections import defaultdict, Counter

def analyze_buses(file_path):
    print(f"ANALYZING BUSES IN: {file_path}")

    bus_map = defaultdict(Counter)

    with open(file_path, "r") as f:
        for i, line in enumerate(f):
            try:
                m = json.loads(line)
                src = m["src"]
                addr = m["address"]
                bus_map[src][addr] += 1
            except: continue

            if i % 1000000 == 0 and i > 0:
                 print(f"Processed {i} lines...")

    for src, ids in bus_map.items():
        print(f"\n[BUS Source: {src}]")
        print(f"Total Unique IDs: {len(ids)}")
        print("Top IDs:")
        for addr, count in ids.most_common(10):
            print(f"  0x{addr:03x} ({addr:<5}) : {count} hits")

if __name__ == "__main__":
    analyze_buses(sys.argv[1])
