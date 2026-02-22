#!/usr/bin/env python3
import os
import time
import json
import curses
from collections import defaultdict

try:
    import zmq
    from cereal import messaging
except ImportError:
    print("Error: cereal/messaging not found. Please run this script on the Openpilot device.")
    exit(1)

ACTIONS = [
    ("BASELINE", "준비 완료! 5초간 아무것도 만지지 마세요 (노이즈 필터링용)", 5),
    ("LEFT_BLINKER", "왼쪽 깜빡이(L)를 켜고 5초 기다리세요", 5),
    ("BLINKER_OFF", "깜빡이를 끄고 3초 기다리세요", 3),
    ("RIGHT_BLINKER", "오른쪽 깜빡이(R)를 켜고 5초 기다리세요", 5),
    ("BLINKER_OFF2", "깜빡이를 끄고 3초 기다리세요", 3),
    ("DRIVER_DOOR", "운전석 문을 여세요. 5초 기다리세요", 5),
    ("DOOR_CLOSE", "운전석 문을 닫으세요. 3초 기다리세요", 3),
    ("SEATBELT", "안전벨트를 매세요. 5초 기다리세요", 5),
    ("SEATBELT_OFF", "안전벨트를 푸세요. 3초 기다리세요", 3),
    ("BRAKE", "브레이크를 꾹 밟으세요. 5초 기다리세요", 5),
    ("BRAKE_OFF", "브레이크를 떼세요. 3초 기다리세요", 3),
    ("GEAR_P_TO_R", "기어를 P에서 R로 바꾸고 5초 기다리세요", 5),
    ("GEAR_R_TO_N", "기어를 R에서 N으로 바꾸고 5초 기다리세요", 5),
    ("GEAR_N_TO_D", "기어를 N에서 D로 바꾸고 10초 기다리세요", 10),
    ("GEAR_D_TO_P", "기어를 다시 P로 바꾸세요", 5),
]

def main():
    print("==================================================")
    print("      EV4 Interactive Signal Hunter v1.0         ")
    print("==================================================")
    print("\n[목적] 안내에 따라 특정 행동을 수행하여,")
    print("누락된 신호(기어, 도어, 깜빡이 등)의 정확한 위치를 찾습니다.\n")

    log_filename = f"ev4_signal_hunt_{int(time.time())}.jsonl"
    output_file = f"/tmp/{log_filename}"

    print(f"로그 저장 위치: {output_file}")
    input("\n👉 시작하려면 차량의 시동을 'IG ON' 상태로 두고 엔터를 누르세요...")

    context = zmq.Context()
    sm = messaging.SubMaster(['can'])

    log_data = []
    start_time = time.time()

    print("\n[테스트 시작! 안내에 따라 행동해주세요]")

    try:
        with open(output_file, 'w') as f:
            for action_id, instruction, duration in ACTIONS:
                print(f"\n▶ [{action_id}] {instruction}")
                action_start = time.time() - start_time

                # Mark the event in the log
                event_mark = {"event": action_id, "time": round(action_start, 3)}
                f.write(json.dumps(event_mark) + '\n')

                # Collect data for the duration
                end_tick = time.time() + duration
                while time.time() < end_tick:
                    sm.update(10)
                    if sm.updated['can']:
                        curr = time.time() - start_time
                        for msg in sm['can']:
                            if msg.src in [0, 1]: # Focus on main buses
                                log_entry = {
                                    "time": round(curr, 3),
                                    "bus": msg.src,
                                    "address": msg.address,
                                    "data": msg.dat.hex()
                                }
                                f.write(json.dumps(log_entry) + '\n')
                    time.sleep(0.01)

                print(f"✅ 완료 ({duration}초 경과)")

    except KeyboardInterrupt:
        print("\n\n🛑 사용자에 의해 중단되었습니다.")

    print(f"\n🎉 모든 테스트 완료!")
    print(f"파일을 PC로 복사하세요: {output_file}")
    print("\n다음 단계: python3 analyze_signal_hunt.py " + log_filename)

if __name__ == "__main__":
    main()
