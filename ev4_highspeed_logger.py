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

import threading

class HighSpeedLogger:
  def __init__(self):
    self.keep_running = True
    self.marker = ""
    self.last_carstate = None
    self.v_raw = 0.0
    self.v_clu_raw = 0.0

    # Initialize Openpilot messaging
    self.can_sock = messaging.sub_sock('can', conflate=False)
    self.state_sock = messaging.sub_sock('carState', conflate=True)

    timestamp = int(time.time())
    self.log_path = f"/data/ev4_re_log_{timestamp}.csv"

  def input_thread(self):
    print("Commands: Type text and press Enter to set a MARKER. Type 'clear' to reset.")
    while self.keep_running:
      try:
        user_input = input().strip()
        if user_input.lower() == 'clear':
          self.marker = ""
          print(">>> Marker Cleared")
        else:
          self.marker = user_input
          print(f">>> Marker Set: {self.marker}")
      except EOFError:
        break

  def signal_handler(self, sig, frame):
    print("\n[Logger] Stopping...")
    self.keep_running = False

  def run(self):
    signal.signal(signal.SIGINT, self.signal_handler)

    # Start input thread
    threading.Thread(target=self.input_thread, daemon=True).start()

    print("="*50)
    print(f"KIA EV4 HIGH-SPEED RE LOGGER")
    print(f"Saving to: {self.log_path}")
    print("="*50)

    with open(self.log_path, "w", newline='') as csvfile:
      writer = csv.writer(csvfile)
      writer.writerow(["Time", "Bus", "Address", "Data", "Marker", "vEgo", "vClu", "Gas", "Brake", "SteerAngle", "SteerTorque"])

      count = 0
      try:
        while self.keep_running:
          # 1. Update CarState
          state = messaging.recv_one_or_none(self.state_sock)
          if state is not None:
            self.last_carstate = state.carState

          # 2. Drain CAN messages
          can_msgs = messaging.drain_sock(self.can_sock, wait_for_one=False)

          for msg in can_msgs:
            for c in msg.can:
                # Raw speed parsing for real-time verification
                if c.address == 160 and c.src == 1:
                    try:
                        d = c.dat
                        v_fl = (d[8] + ((d[9] & 0x3F) << 8)) * 0.03125
                        v_fr = (d[10] + ((d[11] & 0x3F) << 8)) * 0.03125
                        self.v_raw = (v_fl + v_fr) / 2.0
                    except:
                        pass

                if c.address == 506 and c.src == 1:
                    try:
                        d = c.dat
                        self.v_clu_raw = d[5] # Candidate cluster speed from ISLA
                    except:
                        pass

                # Log ALL buses to catch anything unexpected
                vego = self.last_carstate.vEgo if self.last_carstate else 0
                vclu = self.last_carstate.vEgoCluster if self.last_carstate else 0
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
                  f"{vclu:.2f}",
                  int(gas),
                  int(brake),
                  f"{steer_a:.2f}",
                  f"{steer_t:.2f}"
                ])
                count += 1

          if count % 10000 == 0 and count > 0:
            csvfile.flush()
            v_ego = self.last_carstate.vEgo * 3.6 if self.last_carstate else 0
            v_clu = self.last_carstate.vEgoCluster * 3.6 if self.last_carstate else 0
            print(f"\r[Capturing] Msgs: {count:>7} | vWheel: {v_ego:>5.1f} (Raw:{self.v_raw:>5.1f}) | vClu: {v_clu:>5.1f} (Raw:{self.v_clu_raw:>5.1f}) | Marker: {self.marker or 'None'}", end="")

          time.sleep(0.001)

      except KeyboardInterrupt:
        pass
      except Exception as e:
        print(f"\nError: {e}")

    print(f"\nSaved {count} messages to {self.log_path}")

if __name__ == "__main__":
  logger = HighSpeedLogger()
  logger.run()
