#!/usr/bin/env python3
"""
EV4 Full Diagnostic Collector v2.0 (Passive Mode)
===================================================
오픈파일럿 실행 중 백그라운드에서 자동으로 6개 영역 데이터를 수집합니다.
사용자 조작 없이 주행하면 신호 변화를 자동 감지하여 기록합니다.

사용법:
  1. 오픈파일럿 실행 후 새 tmux 창에서:
     python3 /data/openpilot/ev4_full_diag.py
  2. 그냥 주행하세요. Ctrl+C로 종료하면 리포트가 저장됩니다.
  3. 결과: /data/ev4_diag_report.txt

※ 최소 2~3분 주행 권장 (다양한 신호 변화 캡처)
"""

import time
import sys
import os
import subprocess
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, '/data/openpilot')
os.environ['PYTHONPATH'] = '/data/openpilot'

REPORT_PATH = "/data/ev4_diag_report.txt"
SIGNAL_LOG_PATH = "/data/ev4_signal_log.csv"

report = []
signal_log = []


def log(msg=""):
  report.append(msg)


def plog(msg=""):
  print(msg)
  report.append(msg)


def section(title):
  plog(f"\n{'=' * 60}")
  plog(f"  {title}")
  plog(f"{'=' * 60}")


def save_report():
  with open(REPORT_PATH, 'w') as f:
    f.write('\n'.join(report))
  if signal_log:
    with open(SIGNAL_LOG_PATH, 'w') as f:
      f.write(
        "time,door,belt,gear,gas,brake,speed_kmh,angle,torque,eps_torque,"
        "steer_fault,cruise_avail,cruise_en,cruise_speed,steer_pressed,"
        "left_blink,right_blink,standstill\n"
      )
      for row in signal_log:
        f.write(','.join(str(v) for v in row) + '\n')
  print(f"\n✅ Report:     {REPORT_PATH}")
  print(f"✅ Signal CSV: {SIGNAL_LOG_PATH}")


# ─────────────────────────────────────────────
# 1. FW Fingerprinting
# ─────────────────────────────────────────────
def collect_fw_versions():
  section("1. FW FINGERPRINTING")
  try:
    result = subprocess.run(['python3', '/data/openpilot/selfdrive/debug/car/fw_versions.py'], capture_output=True, text=True, timeout=30)
    for line in (result.stdout or '').strip().split('\n'):
      log(f"  {line}")
    for line in (result.stderr or '').strip().split('\n')[:15]:
      log(f"  [err] {line}")
  except subprocess.TimeoutExpired:
    log("  ⚠️ fw_versions.py timeout (30s)")
  except Exception as e:
    log(f"  ❌ {e}")


# ─────────────────────────────────────────────
# 2. SCC Bus + 3. CAN Survey (combined)
# ─────────────────────────────────────────────
def collect_can_info():
  section("2. SCC BUS + 3. CAN BUS SURVEY")
  try:
    import cereal.messaging as messaging

    sm = messaging.SubMaster(['can'])
    buses = {i: set() for i in range(8)}
    msg_sizes = {}
    scc_buses = defaultdict(int)
    t0 = time.time()

    plog("  Scanning CAN bus for 5s...")
    while time.time() - t0 < 5:
      sm.update(100)
      if sm.updated['can']:
        for msg in sm['can']:
          buses[msg.src].add(msg.address)
          msg_sizes[(msg.src, msg.address)] = len(msg.dat)
          if msg.address == 0x1A0:
            scc_buses[msg.src] += 1

    # SCC
    log("\n  --- SCC_CONTROL (0x1A0) ---")
    if scc_buses:
      for bus, cnt in sorted(scc_buses.items()):
        log(f"  Bus {bus}: {cnt} msgs")
      if 2 in scc_buses:
        log("  → CANFD_CAMERA_SCC = CORRECT")
      elif 1 in scc_buses:
        log("  → CANFD_CAMERA_SCC should be FALSE")
    else:
      log("  NOT FOUND")

    # Bus summary
    for bus in range(3):
      addrs = sorted(buses[bus])
      log(f"\n  Bus {bus}: {len(addrs)} messages")
      for i in range(0, len(addrs), 10):
        chunk = addrs[i : i + 10]
        log(f"    {', '.join(f'0x{a:03X}({msg_sizes.get((bus, a), 0)}B)' for a in chunk)}")

    # Key messages
    log("\n  --- Key Messages ---")
    keys = {
      "LKAS_ALT": 0x110,
      "SCC_CONTROL": 0x1A0,
      "CRUISE_BTN_ALT": 0x1AA,
      "ACCEL": 0x035,
      "TCS": 0x175,
      "WHEEL_SPD": 0x0A0,
      "MDPS": 0x0EA,
      "GEAR": 0x130,
      "BODY1": 0x3D0,
      "BODY2": 0x3D3,
      "LFA_BTN": 0x360,
      "LFA": 0x12A,
    }
    for name, addr in keys.items():
      found = [b for b in range(3) if addr in buses[b]]
      log(f"    {name}(0x{addr:03X}): {'Bus ' + str(found) if found else 'MISSING'}")

  except Exception as e:
    log(f"  ❌ {e}")


# ─────────────────────────────────────────────
# 5. Engagement Status
# ─────────────────────────────────────────────
def collect_engagement():
  section("5. ENGAGEMENT STATUS")
  try:
    import cereal.messaging as messaging

    sm = messaging.SubMaster(['selfdriveState', 'carState', 'carParams'])
    sm.update(1000)

    if sm.valid['carParams']:
      cp = sm['carParams']
      log("  --- CarParams ---")
      log(f"    fingerprint: {cp.carFingerprint}")
      log(f"    opLongCtrl: {cp.openpilotLongitudinalControl}")
      log(f"    pcmCruise: {cp.pcmCruise}")
      log(f"    dashcamOnly: {cp.dashcamOnly}")
      log(f"    safetyModel: {cp.safetyConfigs[0].safetyModel if cp.safetyConfigs else 'N/A'}")
      log(f"    safetyParam: {cp.safetyConfigs[-1].safetyParam if cp.safetyConfigs else 'N/A'}")
      log(f"    flags: {cp.flags}")
      log(f"    steerRatio: {cp.steerRatio}  mass: {cp.mass}  wb: {cp.wheelbase}")

    if sm.valid['selfdriveState']:
      ss = sm['selfdriveState']
      log(f"\n  --- SelfdriveState ---")
      log(f"    state: {ss.state}  enabled: {ss.enabled}")
      log(f"    alert: {ss.alertText1} / {ss.alertText2}")

    if sm.valid['carState']:
      cs = sm['carState']
      log(f"\n  --- carState ---")
      log(f"    canValid: {cs.canValid}  speed: {cs.vEgo * 3.6:.1f}km/h")
      log(f"    cruise: avail={cs.cruiseState.available} en={cs.cruiseState.enabled}")
      log(f"    door:{cs.doorOpen} belt:{cs.seatbeltUnlatched} gear:{cs.gearShifter}")
  except Exception as e:
    log(f"  ❌ {e}")


# ─────────────────────────────────────────────
# 4+6. Continuous Signal Monitor (Passive)
# ─────────────────────────────────────────────
def monitor_signals():
  section("4+6. PASSIVE SIGNAL MONITOR (Ctrl+C to stop)")
  plog("  Auto-detecting signal changes during driving...")
  plog("  Logging to CSV every 0.5s, change events highlighted.\n")

  import cereal.messaging as messaging

  sm = messaging.SubMaster(['carState', 'selfdriveState'])

  prev = {}
  change_log = []
  start = time.time()
  sample_count = 0
  engage_events = []

  # Stats
  max_speed = 0
  max_angle = 0
  max_torque = 0
  fault_count = 0
  gear_seen = set()
  door_changes = 0
  belt_changes = 0
  cruise_toggles = 0
  engage_count = 0

  try:
    while True:
      sm.update(100)
      if not sm.updated['carState']:
        continue

      cs = sm['carState']
      now = round(time.time() - start, 2)
      sample_count += 1

      cur = {
        'door': cs.doorOpen,
        'belt': cs.seatbeltUnlatched,
        'gear': str(cs.gearShifter),
        'gas': cs.gasPressed,
        'brake': cs.brakePressed,
        'cruise_avail': cs.cruiseState.available,
        'cruise_en': cs.cruiseState.enabled,
        'steer_pressed': cs.steeringPressed,
        'standstill': cs.standstill,
      }

      speed = cs.vEgo * 3.6
      angle = cs.steeringAngleDeg
      torque = cs.steeringTorque
      eps = cs.steeringTorqueEps
      fault = cs.steerFaultTemporary

      # Track stats
      max_speed = max(max_speed, speed)
      max_angle = max(max_angle, abs(angle))
      max_torque = max(max_torque, abs(torque))
      if fault:
        fault_count += 1
      gear_seen.add(cur['gear'])

      # Detect changes
      if prev:
        changes = [k for k in cur if cur[k] != prev[k]]
        if changes:
          for k in changes:
            if k == 'door':
              door_changes += 1
            elif k == 'belt':
              belt_changes += 1
            elif k == 'cruise_avail':
              cruise_toggles += 1
            elif k == 'cruise_en' and cur[k]:
              engage_count += 1
          change_str = ', '.join(f"{k}:{prev[k]}→{cur[k]}" for k in changes)
          event = f"  [{now:7.1f}s] ⚡ {change_str} | spd:{speed:.0f}km/h"
          change_log.append(event)
          print(event)

      prev = cur.copy()

      # CSV log (every ~0.5s = every 5th sample at ~10Hz)
      if sample_count % 5 == 0:
        # Selfdrived state
        ss_state = ""
        ss_enabled = ""
        if sm.valid['selfdriveState']:
          ss = sm['selfdriveState']
          ss_state = str(ss.state)
          ss_enabled = str(ss.enabled)

        signal_log.append(
          [
            now,
            int(cs.doorOpen),
            int(cs.seatbeltUnlatched),
            cur['gear'],
            int(cs.gasPressed),
            int(cs.brakePressed),
            round(speed, 1),
            round(angle, 1),
            round(torque, 0),
            round(eps, 0),
            int(fault),
            int(cs.cruiseState.available),
            int(cs.cruiseState.enabled),
            round(cs.cruiseState.speed * 3.6, 0),
            int(cs.steeringPressed),
            int(cs.leftBlinker),
            int(cs.rightBlinker),
            int(cs.standstill),
          ]
        )

      # Live status (every 2s)
      if sample_count % 20 == 0:
        ss_str = ""
        if sm.valid['selfdriveState']:
          ss = sm['selfdriveState']
          ss_str = f" | SD:{ss.state}"
        print(
          f"\r  [{now:7.1f}s] D:{int(cs.doorOpen)} B:{int(cs.seatbeltUnlatched)} "
          f"G:{cur['gear'][:5]} Spd:{speed:5.1f} Ang:{angle:6.1f} "
          f"Cr:{int(cs.cruiseState.available)}/{int(cs.cruiseState.enabled)}"
          f"{ss_str}     ",
          end='',
          flush=True,
        )

  except KeyboardInterrupt:
    duration = time.time() - start
    print(f"\n\n  ⏹️  Stopped after {duration:.0f}s ({sample_count} samples)")

  # Write summary
  section("SIGNAL MONITOR SUMMARY")
  log(f"  Duration: {time.time() - start:.0f}s")
  log(f"  Samples: {sample_count}")
  log(f"  CSV rows: {len(signal_log)}")
  log(f"  Max speed: {max_speed:.1f} km/h")
  log(f"  Max |angle|: {max_angle:.1f}°")
  log(f"  Max |torque|: {max_torque:.0f}")
  log(f"  SteerFault frames: {fault_count}")
  log(f"  Gears seen: {gear_seen}")
  log(f"  Door changes: {door_changes}")
  log(f"  Belt changes: {belt_changes}")
  log(f"  Cruise toggles: {cruise_toggles}")
  log(f"  Engage count: {engage_count}")

  if change_log:
    log(f"\n  --- All Signal Changes ({len(change_log)} events) ---")
    for ev in change_log:
      log(ev)


# ═════════════════════════════════════════════
def main():
  plog(f"EV4 Full Diagnostic Collector v2.0 (Passive)")
  plog(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
  plog(f"Reports: {REPORT_PATH}, {SIGNAL_LOG_PATH}")

  print("\n" + "=" * 60)
  print("  EV4 Diagnostic v2.0 — 주행만 하세요!")
  print("  자동 감지 모드: 모든 신호 변화를 자동 기록합니다")
  print("  종료: Ctrl+C")
  print("=" * 60 + "\n")

  # Phase 1: Quick auto-collect
  print("📡 자동 수집 중...")
  collect_fw_versions()
  collect_can_info()
  collect_engagement()

  # Phase 2: Continuous passive monitor
  print("\n🚗 패시브 모니터 시작 — 이제 주행하세요!")
  print("   신호 변화가 감지되면 자동으로 표시됩니다.\n")
  monitor_signals()

  save_report()


if __name__ == "__main__":
  main()
