#!/usr/bin/env python3
import json
import sys

def hypo_speed(file_path):
    print(f"HYPOTHESIZING SPEED IN: {file_path}")

    with open(file_path, "r") as f:
        last_wheel = 0
        for i, line in enumerate(f):
            try:
                m = json.loads(line)
                addr = m["address"]
                data = bytes.fromhex(m["data"])

                if addr == 160:
                    val = data[8] + ((data[9] & 0x3F) << 8)
                    last_wheel = val * 0.03125
                elif addr == 866:
                    if len(data) >= 21:
                        b12 = data[12]
                        b20 = data[20]
                        print(f"TS:{m['t']:.2f} | Wheel:{last_wheel:5.1f} | 866_B12:{b12:3d} | 866_B20:{b20:3d}")
                        count += 1

            except: continue
            if i > 2500000: break

if __name__ == "__main__":
    hypo_speed(sys.argv[1])
