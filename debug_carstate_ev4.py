#!/usr/bin/env python3
import time
import os
import sys

# Ensure we can import openpilot modules
sys.path.append("/data/openpilot")

from cereal import messaging
from common.params import Params

def debug_carstate():
    print("Initializing KIA EV4 Diagnostic Tool...")
    params = Params()

    # 1. Get CarParams
    CP = None
    cp_bytes = params.get("CarParams", block=False)
    if cp_bytes:
        from cereal import car
        CP = car.CarParams.from_bytes(cp_bytes)
        print(f"\n[CarParams Found in Params]")
    else:
        print("Waiting 5s for carParams message...")
        params_sock = messaging.sub_sock('carParams', conflate=True)
        start_time = time.time()
        while CP is None and time.time() - start_time < 5:
            msg = messaging.recv_one_or_none(params_sock)
            if msg is not None:
                CP = msg.carParams
                print(f"\n[CarParams Detected via Message]")
            time.sleep(0.1)

    if CP:
        print(f"  Fingerprint: {CP.carFingerprint}")
        print(f"  Flags: {CP.flags}")
    else:
        print("!! Warning: carParams not found. Is 'card' running?")

    # 2. Monitor carState
    print("\nConnecting to carState...")
    sm = messaging.SubMaster(['carState'])

    print("\n" + "="*75)
    print(f"{'Time':>10} | {'Gear':>7} | {'Gas':>5} | {'Brake':>5} | {'Avail':>5} | {'Fault':>5} | {'Standstill':>10}")
    print("-"*75)

    try:
        last_print = 0
        while True:
            sm.update(100)
            if sm.updated['carState']:
                cs = sm['carState']
                gear = str(cs.gearShifter)
                gas = "YES" if cs.gasPressed else "no"
                brake = "YES" if cs.brakePressed else "no"
                avail = "YES" if cs.cruiseState.available else "no"
                fault = "YES" if cs.accFaulted else "no"
                standstill = "YES" if cs.standstill else "no"

                t = time.strftime("%H:%M:%S")
                # Frequency control for display
                if time.time() - last_print > 0.1:
                    print(f"{t:>10} | {gear:>7} | {gas:>5} | {brake:>5} | {avail:>5} | {fault:>5} | {standstill:>10}", end="\r")
                    last_print = time.time()
            else:
                if time.time() - last_print > 2.0:
                    print(f"\rWaiting for carState messages... (Make sure openpilot is running)", end="")
                    last_print = time.time()
    except KeyboardInterrupt:
        print("\nExit.")

if __name__ == "__main__":
    debug_carstate()
