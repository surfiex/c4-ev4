#!/usr/bin/env python3
"""
EV4 Full Diagnostic Collector v1.0
===================================
6개 영역의 데이터를 한번에 수집하여 /tmp/ev4_diag_report.txt 에 저장합니다.

사용법:
  1. 차량 시동을 켠 상태에서 실행
  2. python3 /data/openpilot/ev4_full_diag.py
  3. 지시에 따라 도어/벨트/기어/페달 조작
  4. 결과는 /tmp/ev4_diag_report.txt 에 저장됨

※ 오픈파일럿이 실행 중인 상태에서 실행하세요 (tmux a 후 새 창에서)
"""

import time
import json
import sys
import os
import subprocess
from datetime import datetime

sys.path.insert(0, '/data/openpilot')
os.environ['PYTHONPATH'] = '/data/openpilot'

REPORT_PATH = "/tmp/ev4_diag_report.txt"
DURATION_CAN_SCAN = 5  # CAN bus scan duration (seconds)
DURATION_SIGNAL = 15  # Signal monitoring duration (seconds)
DURATION_STEERING = 10  # Steering monitoring duration (seconds)

report_lines = []


def log(msg=""):
  print(msg)
  report_lines.append(msg)


def section(title):
  log(f"\n{'=' * 60}")
  log(f"  {title}")
  log(f"{'=' * 60}")


def save_report():
  with open(REPORT_PATH, 'w') as f:
    f.write('\n'.join(report_lines))
  print(f"\n✅ Report saved to {REPORT_PATH}")
  print(f"   scp comma@<ip>:{REPORT_PATH} .")


# ─────────────────────────────────────────────
# 1. FW Fingerprinting
# ─────────────────────────────────────────────
def collect_fw_versions():
  section("1. FW FINGERPRINTING (ECU Firmware Versions)")
  try:
    result = subprocess.run(['python3', '/data/openpilot/selfdrive/debug/car/fw_versions.py'], capture_output=True, text=True, timeout=30)
    if result.stdout:
      log("[stdout]")
      for line in result.stdout.strip().split('\n'):
        log(f"  {line}")
    if result.stderr:
      log("[stderr]")
      for line in result.stderr.strip().split('\n')[:20]:
        log(f"  {line}")
  except subprocess.TimeoutExpired:
    log("⚠️  fw_versions.py timed out (30s). Gateway may be blocking UDS.")
  except Exception as e:
    log(f"❌ Error: {e}")
    log("Trying alternative method...")
    try:
      from opendbc.car.fw_versions import get_fw_versions

      log("  (alternative method not available in this context)")
    except:
      log("  (alternative method failed)")


# ─────────────────────────────────────────────
# 2. SCC Bus Identification
# ─────────────────────────────────────────────
def collect_scc_bus():
  section("2. SCC BUS IDENTIFICATION")
  try:
    import cereal.messaging as messaging

    sm = messaging.SubMaster(['can'])
    scc_found = {}
    t0 = time.time()
    log(f"Scanning for SCC_CONTROL (0x1A0) for {DURATION_CAN_SCAN}s...")
    while time.time() - t0 < DURATION_CAN_SCAN:
      sm.update(100)
      if sm.updated['can']:
        for msg in sm['can']:
          if msg.address == 0x1A0:  # SCC_CONTROL
            bus = msg.src
            scc_found[bus] = scc_found.get(bus, 0) + 1

    if scc_found:
      for bus, count in sorted(scc_found.items()):
        log(f"  ✅ SCC_CONTROL found on Bus {bus} ({count} msgs)")
      # Determine if CANFD_CAMERA_SCC flag is correct
      if 2 in scc_found:
        log("  → CANFD_CAMERA_SCC=True is CORRECT (SCC on camera bus)")
      elif 1 in scc_found:
        log("  → CANFD_CAMERA_SCC should be FALSE (SCC on ECAN bus)")
      else:
        log(f"  → SCC on unusual bus: {list(scc_found.keys())}")
    else:
      log("  ⚠️  SCC_CONTROL (0x1A0) NOT found on any bus")
      log("  → This may be normal if ADAS ECU is not forwarding SCC")
  except Exception as e:
    log(f"❌ Error: {e}")


# ─────────────────────────────────────────────
# 3. CAN Bus Message Survey
# ─────────────────────────────────────────────
def collect_can_survey():
  section("3. CAN BUS MESSAGE SURVEY (Forwarding Verification)")
  try:
    import cereal.messaging as messaging

    sm = messaging.SubMaster(['can'])
    buses = {i: set() for i in range(8)}
    msg_sizes = {}
    t0 = time.time()
    log(f"Scanning all buses for {DURATION_CAN_SCAN}s...")
    while time.time() - t0 < DURATION_CAN_SCAN:
      sm.update(100)
      if sm.updated['can']:
        for msg in sm['can']:
          buses[msg.src].add(msg.address)
          key = (msg.src, msg.address)
          if key not in msg_sizes:
            msg_sizes[key] = len(msg.dat)

    for bus in range(3):
      addrs = sorted(buses[bus])
      log(f"\n  Bus {bus}: {len(addrs)} unique messages")
      if addrs:
        # Show in groups
        for i in range(0, len(addrs), 10):
          chunk = addrs[i : i + 10]
          log(f"    {', '.join(f'0x{a:03X}({msg_sizes.get((bus, a), 0)}B)' for a in chunk)}")

    # Key message presence check
    log("\n  --- Key Message Presence ---")
    key_msgs = {
      "LKAS_ALT (0x110)": 0x110,
      "SCC_CONTROL (0x1A0)": 0x1A0,
      "CRUISE_BUTTONS_ALT (0x1AA)": 0x1AA,
      "ACCELERATOR (0x035)": 0x035,
      "TCS (0x175)": 0x175,
      "WHEEL_SPEEDS (0x0A0)": 0x0A0,
      "MDPS (0x0EA)": 0x0EA,
      "GEAR_SHIFTER (0x130)": 0x130,
      "EV4_BODY_1 (0x3D0)": 0x3D0,
      "EV4_BODY_2 (0x3D3)": 0x3D3,
      "LFA_BUTTON (0x360)": 0x360,
      "LFA (0x12A)": 0x12A,
    }
    for name, addr in key_msgs.items():
      found_on = [b for b in range(3) if addr in buses[b]]
      status = f"Bus {found_on}" if found_on else "NOT FOUND"
      log(f"    {name}: {status}")

  except Exception as e:
    log(f"❌ Error: {e}")


# ─────────────────────────────────────────────
# 4. Signal Correctness (carState)
# ─────────────────────────────────────────────
def collect_signals():
  section("4. SIGNAL CORRECTNESS (carState Monitoring)")
  log(">>> 지금부터 15초간 신호를 기록합니다.")
  log(">>> 이 시간 동안 다음 동작을 순서대로 해주세요:")
  log(">>>   1. 문 열기 → 닫기 (3초)")
  log(">>>   2. 안전벨트 해제 → 체결 (3초)")
  log(">>>   3. P → D → R → N → P (5초)")
  log(">>>   4. 가속페달 살짝 밟기 → 놓기 (2초)")
  log(">>>   5. 브레이크 밟기 → 놓기 (2초)")
  print("\n⏳ 3초 후 시작합니다...")
  time.sleep(3)
  print("🔴 기록 시작!")

  try:
    import cereal.messaging as messaging

    sm = messaging.SubMaster(['carState'])
    t0 = time.time()
    samples = []
    while time.time() - t0 < DURATION_SIGNAL:
      sm.update(100)
      if sm.updated['carState']:
        cs = sm['carState']
        elapsed = time.time() - t0
        sample = {
          't': round(elapsed, 2),
          'door': cs.doorOpen,
          'belt': cs.seatbeltUnlatched,
          'gear': str(cs.gearShifter),
          'gas': cs.gasPressed,
          'brake': cs.brakePressed,
          'speed': round(cs.vEgo * 3.6, 1),
          'angle': round(cs.steeringAngleDeg, 1),
          'torque': round(cs.steeringTorque, 0),
          'cruise_avail': cs.cruiseState.available,
          'cruise_en': cs.cruiseState.enabled,
        }
        samples.append(sample)
        # Print live
        print(
          f"\r  [{elapsed:5.1f}s] D:{int(cs.doorOpen)} B:{int(cs.seatbeltUnlatched)} "
          f"G:{cs.gearShifter} Gas:{int(cs.gasPressed)} Brk:{int(cs.brakePressed)} "
          f"Spd:{cs.vEgo * 3.6:5.1f} Cruise:{int(cs.cruiseState.available)}/{int(cs.cruiseState.enabled)}",
          end='',
        )

    print("\n🟢 기록 완료!")

    # Summarize changes
    log(f"\n  Total samples: {len(samples)}")
    if samples:
      log(f"\n  --- Signal Change Log ---")
      prev = None
      for s in samples:
        if prev is None or any(s[k] != prev[k] for k in ['door', 'belt', 'gear', 'gas', 'brake', 'cruise_avail', 'cruise_en']):
          log(
            f"  [{s['t']:5.1f}s] Door:{s['door']} Belt:{s['belt']} Gear:{s['gear']} "
            f"Gas:{s['gas']} Brake:{s['brake']} CruiseAvail:{s['cruise_avail']} CruiseEn:{s['cruise_en']} Spd:{s['speed']}km/h"
          )
        prev = s

  except Exception as e:
    log(f"❌ Error: {e}")


# ─────────────────────────────────────────────
# 5. Engagement Status
# ─────────────────────────────────────────────
def collect_engagement():
  section("5. ENGAGEMENT STATUS")
  try:
    import cereal.messaging as messaging

    sm = messaging.SubMaster(['selfdriveState', 'carState', 'controlsState', 'carParams'])
    sm.update(1000)

    # CarParams
    if sm.valid['carParams']:
      cp = sm['carParams']
      log("  --- CarParams ---")
      log(f"    carFingerprint: {cp.carFingerprint}")
      log(f"    openpilotLongitudinalControl: {cp.openpilotLongitudinalControl}")
      log(f"    pcmCruise: {cp.pcmCruise}")
      log(f"    dashcamOnly: {cp.dashcamOnly}")
      log(f"    safetyModel: {cp.safetyConfigs[0].safetyModel if cp.safetyConfigs else 'N/A'}")
      log(f"    safetyParam: {cp.safetyConfigs[-1].safetyParam if cp.safetyConfigs else 'N/A'}")
      log(f"    flags: {cp.flags}")
      log(f"    brand: {cp.brand}")
      log(f"    steerRatio: {cp.steerRatio}")
      log(f"    mass: {cp.mass}")
      log(f"    wheelbase: {cp.wheelbase}")
    else:
      log("  ⚠️  carParams not valid")

    # SelfdriveState
    if sm.valid['selfdriveState']:
      ss = sm['selfdriveState']
      log("\n  --- SelfdriveState ---")
      log(f"    state: {ss.state}")
      log(f"    enabled: {ss.enabled}")
      log(f"    alertText1: {ss.alertText1}")
      log(f"    alertText2: {ss.alertText2}")
      log(f"    alertType: {ss.alertType}")
    else:
      log("  ⚠️  selfdriveState not valid")

    # carState summary
    if sm.valid['carState']:
      cs = sm['carState']
      log("\n  --- carState Snapshot ---")
      log(f"    canValid: {cs.canValid}")
      log(f"    vEgo: {cs.vEgo * 3.6:.1f} km/h")
      log(f"    cruiseState.available: {cs.cruiseState.available}")
      log(f"    cruiseState.enabled: {cs.cruiseState.enabled}")
      log(f"    cruiseState.speed: {cs.cruiseState.speed * 3.6:.1f} km/h")
      log(f"    doorOpen: {cs.doorOpen}")
      log(f"    seatbeltUnlatched: {cs.seatbeltUnlatched}")
      log(f"    gearShifter: {cs.gearShifter}")

  except Exception as e:
    log(f"❌ Error: {e}")


# ─────────────────────────────────────────────
# 6. Steering Response
# ─────────────────────────────────────────────
def collect_steering():
  section("6. STEERING RESPONSE")
  log(f"Monitoring steering signals for {DURATION_STEERING}s...")
  log(">>> 가능하다면 핸들을 좌우로 천천히 돌려보세요.")
  try:
    import cereal.messaging as messaging

    sm = messaging.SubMaster(['carState'])
    t0 = time.time()
    min_angle = 999
    max_angle = -999
    min_torque = 999
    max_torque = -999
    fault_count = 0
    samples = 0

    while time.time() - t0 < DURATION_STEERING:
      sm.update(100)
      if sm.updated['carState']:
        cs = sm['carState']
        samples += 1
        angle = cs.steeringAngleDeg
        torque = cs.steeringTorque
        eps_torque = cs.steeringTorqueEps
        fault = cs.steerFaultTemporary

        min_angle = min(min_angle, angle)
        max_angle = max(max_angle, angle)
        min_torque = min(min_torque, torque)
        max_torque = max(max_torque, torque)
        if fault:
          fault_count += 1

        print(f"\r  Angle:{angle:7.1f}° Torque:{torque:6.0f} EPS:{eps_torque:6.0f} Fault:{int(fault)}", end='')

    print()
    log(f"  Samples: {samples}")
    log(f"  Angle range: {min_angle:.1f}° ~ {max_angle:.1f}°")
    log(f"  Torque range: {min_torque:.0f} ~ {max_torque:.0f}")
    log(f"  SteerFault count: {fault_count}/{samples}")

  except Exception as e:
    log(f"❌ Error: {e}")


# ═════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════
def main():
  log(f"EV4 Full Diagnostic Collector v1.0")
  log(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
  log(f"Report: {REPORT_PATH}")

  print("\n" + "=" * 60)
  print("  EV4 Full Diagnostic Collector v1.0")
  print("  6개 영역 데이터를 한번에 수집합니다")
  print("=" * 60)
  print("\n⚠️  오픈파일럿이 실행 중인 상태에서 실행하세요!")
  print("⚠️  차량 시동이 켜져 있어야 합니다!\n")
  input("준비되셨으면 Enter를 누르세요...")

  # Phase 1: Passive collection (no user action needed)
  print("\n📡 Phase 1: 자동 수집 (조작 불필요)")
  collect_fw_versions()
  collect_scc_bus()
  collect_can_survey()
  collect_engagement()

  # Phase 2: Active collection (user actions needed)
  print("\n🎮 Phase 2: 사용자 조작 필요")
  collect_signals()
  collect_steering()

  # Summary
  section("DIAGNOSTIC COMPLETE")
  log(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
  log(f"Total report lines: {len(report_lines)}")

  save_report()


if __name__ == "__main__":
  main()
