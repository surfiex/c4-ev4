#!/usr/bin/env python3
import os
import sys
import time
import signal
import json
import csv
from cereal import messaging

# Target Buses for EV4
BUS_RADAR_CHASSIS = 0
BUS_CAMERA_ECAN = 1

class HighSpeedLogger:
  def __init__(self):
    self.keep_running = True
    self.marker = ""
    self.last_carstate = None

    # Initialize Openpilot messaging
    self.can_sock = messaging.sub_sock('can', conflate=False)
    self.state_sock = messaging.sub_sock('carState', conflate=True)

    timestamp = int(time.time())
    self.log_path = f"/data/ev4_re_log_{timestamp}.csv"

  def signal_handler(self, sig, frame):
    print("\n[Logger] Stopping...")
    self.keep_running = False

  def run(self):
    signal.signal(signal.SIGINT, self.signal_handler)

    print("="*50)
    print(f"KIA EV4 HIGH-SPEED RE LOGGER")
    print(f"Saving to: {self.log_path}")
    print("Commands: Type text and press Enter to set a MARKER.")
    print("="*50)

    with open(self.log_path, "w", newline='') as csvfile:
      writer = csv.writer(csvfile)
      writer.writerow(["Time", "Bus", "Address", "Data", "Marker", "vEgo", "Gas", "Brake", "SteerAngle", "SteerTorque"])

      count = 0
      try:
        while self.keep_running:
          # 1. Update CarState (Ground Truth)
          state = messaging.recv_one_or_none(self.state_sock)
          if state is not None:
            self.last_carstate = state.carState

          # 2. Drain CAN messages
          can_msgs = messaging.drain_sock(self.can_sock, wait_for_one=False)

          for msg in can_msgs:
            for c in msg.can:
              if c.src in [BUS_RADAR_CHASSIS, BUS_CAMERA_ECAN]:
                # Collect relevant context
                vego = self.last_carstate.vEgo if self.last_carstate else 0
                gas = self.last_carstate.gasPressed if self.last_carstate else False
                brake = self.last_carstate.brakePressed if self.last_carstate else False
                steer_a = self.last_carstate.steeringAngleDeg if self.last_carstate else 0
                steer_t = self.last_carstate.steeringTorque if self.last_carstate else 0

                writer.writerow([
                  msg.logMonoTime,
                  c.src,
                  c.address,
                  c.dat.hex(),
                  self.marker,
                  f"{vego:.2f}",
                  int(gas),
                  int(brake),
                  f"{steer_a:.2f}",
                  f"{steer_t:.2f}"
                ])
                count += 1

          # 3. Handle markers without blocking (non-ideal in single thread, but okay for CLI)
          # Note: Real-time marker input usually needs a separate thread or non-blocking read
          # For now, we rely on high-frequency loops.

          if count % 2000 == 0:
            csvfile.flush()
            print(f"\rCaptured {count} messages... (Marker: {self.marker or 'None'})", end="")

      except KeyboardInterrupt:
        pass
      except Exception as e:
        print(f"\nError: {e}")

    print(f"\nSaved {count} messages to {self.log_path}")

if __name__ == "__main__":
  logger = HighSpeedLogger()
  logger.run()
