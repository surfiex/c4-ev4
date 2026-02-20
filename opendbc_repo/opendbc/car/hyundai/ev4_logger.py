#!/usr/bin/env python3
import time
import csv
import os
import cereal.messaging as messaging
from openpilot.common.realtime import Ratekeeper
import json

def main():
  sm = messaging.SubMaster(['carState', 'carControl', 'can'])

  log_path = '/tmp/ev4_drive_log.csv'
  raw_log_path = '/tmp/ev4_raw_can.jsonl'
  print(f"EV4 Logger started.\n - State log: {log_path}\n - Raw CAN log: {raw_log_path}")
  print("Press Ctrl+C to stop logging.")

  try:
    with open(log_path, 'w', newline='') as f_csv, open(raw_log_path, 'w') as f_raw:
      writer = csv.writer(f_csv)
      writer.writerow([
        'time',
        'v_ego_raw',
        'steering_angle',
        't_driver',
        't_actuator',
        'gas_pressed',
        'brake_pressed',
        'cruise_enabled',
        'main_button',
        'cruise_buttons',
        'lda_button',
        'driver_steering_pressed'
      ])

      while True:
        # Blocking update, wait for messages
        sm.update()

        if sm.updated['carState']:
          cs = sm['carState']

          v_ego_raw = cs.vEgoRaw # m/s
          angle = cs.steeringAngleDeg
          t_driver = cs.steeringTorque
          t_actuator = cs.steeringTorqueEps
          gas = cs.gasPressed
          brake = cs.brakePressed

          cruise_enabled = cs.cruiseState.enabled

          # Extract buttons
          cruise_btns = 0
          main_btn = 0
          lda_btn = 0

          for ev in cs.buttonEvents:
            if ev.type == getattr(cs.buttonEvents.Type, 'cancel', 4):
              cruise_btns = ev.type
            elif ev.type == getattr(cs.buttonEvents.Type, 'lkas', 0):
              lda_btn = ev.pressed
            elif ev.type == getattr(cs.buttonEvents.Type, 'mainCruise', 0):
              main_btn = ev.pressed

          driver_steer = cs.steeringPressed

          writer.writerow([
            time.time(),
            f"{v_ego_raw:.2f}",
            f"{angle:.2f}",
            f"{t_driver:.2f}",
            f"{t_actuator:.2f}",
            gas,
            brake,
            cruise_enabled,
            main_btn,
            cruise_btns,
            lda_btn,
            driver_steer
          ])

          if sm.frame % 100 == 0:
            f_csv.flush()
            f_raw.flush()

          if sm.frame % 100 == 0:
            print(f"[{sm.frame}] Speed:{v_ego_raw*3.6:.1f} km/h | AccEn:{cruise_enabled} | Steer:{driver_steer} | CS:{os.path.getsize(log_path)/1024:.0f}KB | CAN:{os.path.getsize(raw_log_path)/1024/1024:.1f}MB", end='\r', flush=True)

        if sm.updated['can']:
          for msg in sm['can']:
            # Log all raw CAN messages in JSONL format for future DBC analysis
            record = {
                't': time.time(),
                'src': msg.src,
                'bus': msg.src,  # Openpilot CAN message 'src' maps to the Panda bus number (0 for E-CAN/PT, 1 for C-CAN/Camera, etc.)
                'address': msg.address,
                'data': msg.dat.hex()
            }
            f_raw.write(json.dumps(record) + "\n")

  except KeyboardInterrupt:
    print("\nLogging stopped by user.")
  except Exception as e:
    print(f"\nError during logging: {e}")

if __name__ == "__main__":
  main()
