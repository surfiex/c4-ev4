#!/usr/bin/env python3
import time
from cereal import messaging

def debug_carstate():
    print("Waiting for carState and carParams...")
    params_sock = messaging.sub_sock('carParams', conflate=True)
    state_sock = messaging.sub_sock('carState', conflate=True)

    CP = None
    while CP is None:
        msg = messaging.recv_one_or_none(params_sock)
        if msg is not None:
            CP = msg.carParams
            print(f"\n[CarParams Detected]")
            print(f"  Fingerprint: {CP.carFingerprint}")
            print(f"  Flags: {CP.flags}")
            print(f"  Longitudinal Control: {CP.openpilotLongitudinalControl}")
        time.sleep(0.1)

    print("\n" + "="*60)
    print(f"{'Time':>10} | {'Gear':>7} | {'Gas':>5} | {'Brake':>5} | {'Avail':>5} | {'Fault':>5} | {'Standstill':>10}")
    print("-"*60)

    try:
        while True:
            msg = messaging.recv_one_or_none(state_sock)
            if msg is not None:
                cs = msg.carState
                gear = str(cs.gearShifter)
                gas = "YES" if cs.gasPressed else "no"
                brake = "YES" if cs.brakePressed else "no"
                avail = "YES" if cs.cruiseState.available else "no"
                fault = "YES" if cs.accFaulted else "no"
                standstill = "YES" if cs.standstill else "no"

                t = time.strftime("%H:%M:%S")
                print(f"{t:>10} | {gear:>7} | {gas:>5} | {brake:>5} | {avail:>5} | {fault:>5} | {standstill:>10}", end="\r")
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nExit.")

if __name__ == "__main__":
    debug_carstate()
