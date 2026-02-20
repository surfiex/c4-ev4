#!/usr/bin/env python3
import time
import csv
import os
import cereal.messaging as messaging
from openpilot.common.realtime import Ratekeeper

def main():
  sm = messaging.SubMaster(['carState', 'carControl'])

  log_path = '/tmp/ev4_drive_log.csv'
  print(f"EV4 Logger started. Saving to {log_path}...")
  print("Press Ctrl+C to stop logging.")

  try:
    with open(log_path, 'w', newline='') as f:
      writer = csv.writer(f)
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

      rk = Ratekeeper(20)

      while True:
        sm.update(0) # Non-blocking update to ensuring we drain the queue

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
            f.flush()

          if sm.frame % 20 == 0:
            print(f"[{sm.frame}] Speed:{v_ego_raw*3.6:.1f} km/h | AccEn:{cruise_enabled} | Steer:{driver_steer} | Size:{os.path.getsize(log_path)/1024:.1f} KB", end='\r', flush=True)

        rk.keep_time()

  except KeyboardInterrupt:
    print("\nLogging stopped by user.")
  except Exception as e:
    print(f"\nError during logging: {e}")

if __name__ == "__main__":
  main()
