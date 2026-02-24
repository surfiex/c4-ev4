#!/usr/bin/env python3
import json
import sys
from collections import Counter

def analyze_freq(file_path):
    print(f"Analyzing ID frequencies in: {file_path}")

    with open(file_path, "r") as f:
        lines = []
        for _ in range(100000):
            try:
                line = f.readline()
                if not line: break
                lines.append(json.loads(line))
            except: continue

    if not lines: return

    duration = lines[-1]["t"] - lines[0]["t"]
    print(f"Duration of sample: {duration:.2f}s")

    counter = Counter([l["address"] for l in lines])

    print(f"\n{'ID (hex)':<15} | {'Count':<8} | {'Freq (Hz)':<10}")
    print("-" * 40)
    for addr, count in counter.most_common(30):
        freq = count / duration
        print(f"0x{addr:03x} ({addr:<5}) | {count:<8} | {freq:>8.1f} Hz")

if __name__ == "__main__":
    analyze_freq(sys.argv[1])
