#!/usr/bin/env python3
import time
import csv
import os
from cereal import car
import cereal.messaging as messaging
from openpilot.common.realtime import Ratekeeper

def main():
  # Create a SubMaster to listen to relevant services
  # carState: contains all sensor and state data (speed, steering, buttons, etc.)
  # carControl: contains commands sent to the car (actuators)
  sm = messaging.SubMaster(['carState', 'carControl'])

  log_path = '/tmp/ev4_drive_log.csv'
  print(f"EV4 Logger started. Saving to {log_path}...")
  print("Press Ctrl+C to stop logging.")

  try:
    with open(log_path, 'w', newline='') as f:
      writer = csv.writer(f)
      # Header
      writer.writerow([
        'time',
        'v_ego',
        'steering_angle',
        't_driver',
        't_actuator',
        'gas_pressed',
        'brake_pressed',
        'acc_enabled',
        'acc_available',
        'lka_icon',
        'lka_active',
        'steer_fault',
        'standstill',
        'v_set_dis'
      ])

      # Log at 20Hz
      rk = Ratekeeper(20)

      while True:
        # Update submaster (waits for new messages appropriately or times out)
        sm.update()

        # Only log if we have received a carState message recently
        if sm.updated['carState']:
          cs = sm['carState']

          # Extract data safely
          v_ego = cs.vEgo
          angle = cs.steeringAngleDeg
          t_driver = cs.steeringTorque
          t_actuator = cs.steeringTorqueEps
          gas = cs.gasPressed
          brake = cs.brakePressed

          acc_enabled = cs.cruiseState.enabled
          acc_available = cs.cruiseState.available
          standstill = cs.cruiseState.standstill
          v_set = cs.cruiseState.speed

          # LKA status (might be in carState alerts or specific fields)
          lka_active = cs.steeringPressed # Proxy or check actual active bit if available in generic CS
          # Note: lka_icon is not generic in carState, but we can look for steeringState
          steer_fault = cs.steerFaultTemporary

          writer.writerow([
            time.time(),
            f"{v_ego:.2f}",
            f"{angle:.2f}",
            f"{t_driver:.2f}",
            f"{t_actuator:.2f}",
            gas,
            brake,
            acc_enabled,
            acc_available,
            0, # LKA Icon generic not easily avail, skipping for now
            lka_active,
            steer_fault,
            standstill,
            f"{v_set:.2f}"
          ])

          # Flush occasionally to ensure data is saved if crash
          if sm.frame % 100 == 0:
            f.flush()

        rk.keep_time()

  except KeyboardInterrupt:
    print("\nLogging stopped by user.")
  except Exception as e:
    print(f"\nError during logging: {e}")

if __name__ == "__main__":
  main()
