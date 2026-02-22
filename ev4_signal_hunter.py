#!/usr/bin/env python3
import os
import time
import json
import zmq
try:
    from cereal import messaging
except ImportError:
    print("Error: cereal/messaging not found. Please run this script on the Openpilot device.")
    exit(1)

def main():
    print("==================================================")
    print("      EV4 Signal Hunter (Raw CAN Logger)          ")
    print("==================================================")
    print("\n[목적] 누락된 EV4 신호(안전벨트, 도어, 깜빡이, 기어 등)를")
    print("찾기 위해 C-CAN 및 E-CAN 통신의 모든 원시 데이터를 기록합니다.\n")

    output_file = f"/tmp/ev4_signal_hunt_{int(time.time())}.jsonl"
    print(f"로그 저장 위치: {output_file}")
    print("종료하려면 언제든지 Ctrl+C를 누르세요.\n")

    input("👉 시작하려면 엔터를 누르세요...")

    print("\n[기록 중...] 지금부터 테스트 행동을 정확한 초 단위로 메모해주세요!")

    # Connect to the openpilot raw CAN socket
    context = zmq.Context()
    sm = messaging.SubMaster(['can'])

    start_time = time.time()
    msg_count = 0

    try:
        with open(output_file, 'w') as f:
            while True:
                sm.update(0)
                if sm.updated['can']:
                    current_time = time.time() - start_time

                    for msg in sm['can']:
                        # Save bus, address, and raw data bytes
                        log_entry = {
                            "time": round(current_time, 3),
                            "bus": msg.src,
                            "address": msg.address,
                            "data": msg.dat.hex()
                        }
                        f.write(json.dumps(log_entry) + '\n')
                        msg_count += 1

                        if msg_count % 5000 == 0:
                            print(f"  -> {msg_count}개의 메시지 수집됨... (진행 시간: {round(current_time, 1)}초)", end='\r')

                time.sleep(0.01) # 100Hz 루프

    except KeyboardInterrupt:
        print(f"\n\n🛑 기록 종료! 총 {msg_count}개의 메시지가 저장되었습니다.")
        print(f"저장된 파일: {output_file}")
        print("\n이 스크립트를 종료하고, 해당 jsonl 파일과 시간별 행동 메모를")
        print("PC로 복사한 후 분석을 진행해 주세요.")

if __name__ == "__main__":
    main()
