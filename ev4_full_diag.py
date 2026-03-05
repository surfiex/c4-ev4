#!/usr/bin/env python3
"""
EV4 Full Diagnostic Collector v2.1 (Ultra-Passive Mode)
=========================================================
오픈파일럿 주행 중 백그라운드에서 모든 데이터를 자동 수집합니다.
Ctrl+C 또는 프로세스 종료 시 반드시 파일을 저장하도록 개선되었습니다.

사용법:
  1. 오픈파일럿 실행 후 새 tmux 창에서:
     python3 /data/openpilot/ev4_full_diag.py
  2. 기어 조작, 주행, 문/벨트 등 마음껏 테스트하세요.
  3. 완료 후 Ctrl+C 누르면 저장됩니다.

결과 위치:
  - 리포트: /data/ev4_diag_report.txt
  - 신호로그: /data/ev4_signal_log.csv
"""

import time
import sys
import os
import signal
import subprocess
from datetime import datetime
from collections import defaultdict

# Openpilot paths
sys.path.insert(0, '/data/openpilot')
os.environ['PYTHONPATH'] = '/data/openpilot'

try:
  import cereal.messaging as messaging
  from opendbc.car.structs import CarParams
except ImportError as e:
  print(f"❌ Error: Openpilot libraries not found. Run this from /data/openpilot. ({e})")
  # We still want to try running Phase 1 (FW) if possible
  messaging = None

REPORT_PATH = "/data/ev4_diag_report.txt"
SIGNAL_LOG_PATH = "/data/ev4_signal_log.csv"

report = []
signal_log = []
running = True


def signal_handler(sig, frame):
  global running
  print(f"\n⏹️ Termination signal received ({sig}). Saving data...")
  running = False


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def log(msg=""):
  report.append(msg)


def plog(msg=""):
  print(msg)
  report.append(msg)


def section(title):
  plog(f"\n{'=' * 60}")
  plog(f"  {title}")
  plog(f"{'=' * 60}")


def save_all():
  print("\n💾 Finalizing and saving files...")
  # Save Report
  try:
    with open(REPORT_PATH, 'w') as f:
      f.write('\n'.join(report))
    print(f"✅ Report saved to: {REPORT_PATH}")
  except Exception as e:
    print(f"❌ Failed to save report: {e}")

  # Save CSV
  try:
    with open(SIGNAL_LOG_PATH, 'w') as f:
      f.write(
        "time,door,belt,gear,gas,brake,speed_kmh,angle,torque,eps_torque,"
        "steer_fault,cruise_avail,cruise_en,cruise_speed,steer_pressed,"
        "left_blink,right_blink,standstill\n"
      )
      for row in signal_log:
        f.write(','.join(str(v) for v in row) + '\n')
    print(f"✅ Signal CSV saved to: {SIGNAL_LOG_PATH} ({len(signal_log)} rows)")
  except Exception as e:
    print(f"❌ Failed to save CSV: {e}")


# ─────────────────────────────────────────────
# Phase 1: Static Data
# ─────────────────────────────────────────────
def collect_fw_versions():
  section("1. FW FINGERPRINTING")
  try:
    result = subprocess.run(['python3', '/data/openpilot/selfdrive/debug/car/fw_versions.py'], capture_output=True, text=True, timeout=30)
    for line in (result.stdout or '').strip().split('\n'):
      log(f"  {line}")
    if result.stderr:
      log(f"  [stderr] {result.stderr.strip()[:100]}")
  except Exception as e:
    log(f"  ❌ FW collection failed: {e}")


def collect_can_info():
  section("2. SCC BUS + 3. CAN BUS SURVEY")
  if not messaging:
    plog("  ❌ Messaging not available, skipping.")
    return

  try:
    sm = messaging.SubMaster(['can'])
    buses = {i: set() for i in range(4)}
    msg_sizes = {}
    scc_buses = defaultdict(int)
    t0 = time.time()

    plog("  Scanning CAN bus for 5s...")
    while time.time() - t0 < 5 and running:
      sm.update(100)
      if sm.updated['can']:
        for msg in sm['can']:
          if msg.src < 4:
            buses[msg.src].add(msg.address)
            msg_sizes[(msg.src, msg.address)] = len(msg.dat)
            if msg.address == 0x1A0:
              scc_buses[msg.src] += 1
      else:
        # Avoid tight loop if no data
        time.sleep(0.1)

    log("\n  --- SCC_CONTROL (0x1A0) ---")
    if scc_buses:
      for bus, cnt in sorted(scc_buses.items()):
        log(f"  Bus {bus}: {cnt} msgs")
    else:
      log("  NOT FOUND")

    for bus in range(3):
      addrs = sorted(buses[bus])
      log(f"\n  Bus {bus}: {len(addrs)} messages")
      if addrs:
        for i in range(0, len(addrs), 10):
          chunk = addrs[i : i + 10]
          log(f"    {', '.join(f'0x{a:03X}({msg_sizes.get((bus, a), 0)}B)' for a in chunk)}")

    log("\n  --- Key Message Check ---")
    keys = {"LKAS_ALT": 0x110, "SCC": 0x1A0, "CRUISE_BTN": 0x1AA, "BODY1": 0x3D0, "LFA_BTN": 0x360}
    for name, addr in keys.items():
      found = [b for b in range(3) if addr in buses[b]]
      log(f"    {name}: {'Bus ' + str(found) if found else 'MISSING'}")

  except Exception as e:
    log(f"  ❌ CAN survey failed: {e}")


def collect_engagement_params():
  section("5. ENGAGEMENT & PARAMS")
  if not messaging:
    return
  try:
    sm = messaging.SubMaster(['selfdriveState', 'carState', 'carParams'])
    sm.update(2000)

    if sm.valid['carParams']:
      cp = sm['carParams']
      log(f"  Fingerprint: {cp.carFingerprint}")
      log(f"  Longitudinal: {cp.openpilotLongitudinalControl}")
      log(f"  Flags: {cp.flags}")
      if cp.safetyConfigs:
        log(f"  Safety Model: {cp.safetyConfigs[0].safetyModel} (Param: {cp.safetyConfigs[0].safetyParam})")

    if sm.valid['carState']:
      cs = sm['carState']
      log(f"  canValid: {cs.canValid}, Gear: {cs.gearShifter}")
  except Exception as e:
    log(f"  ❌ Params collection failed: {e}")


# ─────────────────────────────────────────────
# Phase 2: Signal Monitor
# ─────────────────────────────────────────────
def monitor_loop():
  section("4+6. SIGNAL MONITOR (PASSIVE)")
  if not messaging:
    plog("  ❌ Messaging not available, exiting monitor.")
    return

  plog("  Started passive monitoring... Just drive or operate the car.")
  plog("  Every 0.5s data will be queued for CSV. State changes will be printed.\n")

  sm = messaging.SubMaster(['carState', 'selfdriveState'])
  start_time = time.time()
  prev_state = None
  sample_count = 0

  # Stats
  max_speed = 0
  max_angle = 0

  while running:
    sm.update(100)
    if not sm.updated['carState']:
      if not sm.valid['carState']:
        # If carState is not being published, warn user
        sys.stdout.write("\r  ⚠️ Waiting for carState updates... (Is Openpilot running?)")
        sys.stdout.flush()
        time.sleep(0.5)
      continue

    cs = sm['carState']
    sample_count += 1
    now = time.time() - start_time

    cur_state = {
      'door': cs.doorOpen,
      'belt': cs.seatbeltUnlatched,
      'gear': str(cs.gearShifter),
      'gas': cs.gasPressed,
      'brake': cs.brakePressed,
      'cruise_avail': cs.cruiseState.available,
      'cruise_en': cs.cruiseState.enabled,
    }

    # Detect and print changes
    if prev_state:
      diff = [k for k in cur_state if cur_state[k] != prev_state[k]]
      if diff:
        change_desc = ", ".join([f"{k}:{prev_state[k]}->{cur_state[k]}" for k in diff])
        event = f"  [{now:7.2f}s] ⚡ {change_desc} (@ {cs.vEgo * 3.6:.1f} km/h)"
        print(event)
        log(event)

    prev_state = cur_state.copy()
    max_speed = max(max_speed, cs.vEgo * 3.6)
    max_angle = max(max_angle, abs(cs.steeringAngleDeg))

    # Add to log every 500ms (at ~10-20Hz base freq)
    if sample_count % 5 == 0:
      signal_log.append(
        [
          round(now, 2),
          int(cs.doorOpen),
          int(cs.seatbeltUnlatched),
          cur_state['gear'],
          int(cs.gasPressed),
          int(cs.brakePressed),
          round(cs.vEgo * 3.6, 1),
          round(cs.steeringAngleDeg, 1),
          round(cs.steeringTorque, 0),
          round(cs.steeringTorqueEps, 0),
          int(cs.steerFaultTemporary),
          int(cs.cruiseState.available),
          int(cs.cruiseState.enabled),
          round(cs.cruiseState.speed * 3.6, 0),
          int(cs.steeringPressed),
          int(cs.leftBlinker),
          int(cs.rightBlinker),
          int(cs.standstill),
        ]
      )

    # Status line every 1s
    if sample_count % 10 == 0:
      sys.stdout.write(f"\r  [{now:6.0f}s] Spd:{cs.vEgo * 3.6:5.1f} Ang:{cs.steeringAngleDeg:6.1f} | Samples:{sample_count} CSV:{len(signal_log)}    ")
      sys.stdout.flush()

  log(f"\nSignal Monitor Stats:\n  Max speed: {max_speed:.1f} km/h\n  Max angle: {max_angle:.1f}°\n  Total Samples: {sample_count}")


# ═════════════════════════════════════════════
def main():
  plog(f"EV4 Full Diagnostic v2.1 (Date: {datetime.now().strftime('%m-%d %H:%M')})")
  plog(f"Saving to /data/... (Ctrl+C to finish)")

  try:
    collect_fw_versions()
    collect_can_info()
    collect_engagement_params()

    if running:
      monitor_loop()

  except Exception as e:
    plog(f"\n❌ Unexpected error: {e}")
  finally:
    # Always try to save
    save_all()


if __name__ == "__main__":
  main()
