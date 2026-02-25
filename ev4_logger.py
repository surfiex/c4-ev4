#!/usr/bin/env python3
import os
import time
import signal
import json
import csv
import threading
from cereal import messaging

class EV4Logger:
  def __init__(self):
    self.keep_running = True
    self.marker = ""
    self.last_carstate = None

    # Initialize Openpilot messaging
    self.can_sock = messaging.sub_sock('can', conflate=False)
    self.state_sock = messaging.sub_sock('carState', conflate=True)

    timestamp = int(time.time())
    self.log_path_csv = f"/data/ev4_drive_log_{timestamp}.csv"
    self.log_path_jsonl = f"/data/ev4_raw_can_{timestamp}.jsonl"

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
    threading.Thread(target=self.input_thread, daemon=True).start()

    print("="*50)
    print(f"KIA EV4 DRIVE LOGGER (100Hz)")
    print(f"CSV: {self.log_path_csv}")
    print(f"JSONL: {self.log_path_jsonl}")
    print("="*50)

    with open(self.log_path_csv, "w", newline='') as csvfile, \
         open(self.log_path_jsonl, "w") as jsonlfile:

      writer = csv.writer(csvfile)
      writer.writerow(["Time", "Bus", "Address", "Data", "Marker", "vEgo", "SteerAngle", "Gas", "Brake"])

      count = 0
      try:
        while self.keep_running:
          # 1. Update CarState (Non-blocking)
          state = messaging.recv_one_or_none(self.state_sock)
          if state is not None:
            self.last_carstate = state.carState

          # 2. Drain CAN messages
          can_msgs = messaging.drain_sock(self.can_sock, wait_for_one=False)

          for msg in can_msgs:
            for c in msg.can:
                # Parsed values from CarState
                vego = self.last_carstate.vEgo if self.last_carstate else 0
                steer_a = self.last_carstate.steeringAngleDeg if self.last_carstate else 0
                gas = self.last_carstate.gasPressed if self.last_carstate else False
                brake = self.last_carstate.brakePressed if self.last_carstate else False

                # 1. Log to CSV (Parsed + Meta)
                writer.writerow([
                  msg.logMonoTime,
                  c.src,
                  c.address,
                  c.dat.hex(),
                  self.marker,
                  f"{vego:.2f}",
                  f"{steer_a:.2f}",
                  int(gas),
                  int(brake)
                ])

                # 2. Log to JSONL (Raw)
                json.dump({"t": msg.logMonoTime, "b": c.src, "a": c.address, "d": c.dat.hex()}, jsonlfile)
                jsonlfile.write("\n")

                count += 1

          if count % 10000 == 0 and count > 0:
            csvfile.flush()
            jsonlfile.flush()
            v_kph = (self.last_carstate.vEgo * 3.6) if self.last_carstate else 0
            print(f"\r[Logging] Msgs: {count:>7} | vEgo: {v_kph:>5.1f} km/h | Marker: {self.marker or 'None'}", end="")

          time.sleep(0.01) # ~100Hz loop

      except KeyboardInterrupt:
        pass
      except Exception as e:
        print(f"\nError: {e}")

    print(f"\nSaved {count} messages.")

if __name__ == "__main__":
  logger = EV4Logger()
  logger.run()
