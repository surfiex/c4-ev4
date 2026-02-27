#!/usr/bin/env python3
import zmq
import json
import time
import os
import argparse
from datetime import datetime

# Openpilot messaging interface (minimal implementation for standalone script)
import cereal.messaging as messaging


def main():
  parser = argparse.ArgumentParser(description="EV4 CAN Data Collector")
  parser.add_argument('--duration', type=int, default=60, help='Duration to record in seconds (default: 60)')
  parser.add_argument('--output', type=str, default='/data/ev4_can_capture.jsonl', help='Output file path')
  args = parser.parse_args()

  print(f"Starting EV4 CAN Collector for {args.duration} seconds...")
  print(f"Output will be saved to: {args.output}")

  # Subscribe to to CAN messages
  sm = messaging.SubMaster(['can'])

  start_time = time.monotonic()
  msg_count = 0

  with open(args.output, 'w') as f:
    while time.monotonic() - start_time < args.duration:
      sm.update(100)  # 100ms timeout

      if sm.updated['can']:
        current_time = time.time()

        # Process each CAN message in the packet
        for msg in sm['can']:
          bus = msg.src
          address = msg.address
          dat = bytes(msg.dat).hex()

          # We only care about main buses (0: ECAN/ACAN, 1: ECAN/ADAS, 2: CAM)
          if bus < 4:
            log_entry = {"t": current_time, "bus": bus, "addr": address, "data": dat}
            f.write(json.dumps(log_entry) + '\n')
            msg_count += 1

      # Print progress every second
      elapsed = time.monotonic() - start_time
      if int(elapsed * 10) % 10 == 0:
        print(f"Captured {msg_count} messages in {int(elapsed)}s...", end='\r')

  print(f"\nFinished! Captured a total of {msg_count} CAN messages.")
  print(f"Please download {args.output} to your PC for analysis.")


if __name__ == "__main__":
  main()
