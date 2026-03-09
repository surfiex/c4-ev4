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

    # Get CarParams
    cp_bytes = params.get("CarParams", block=False)
    if cp_bytes:
        from cereal import car
        CP = car.CarParams.from_bytes(cp_bytes)
        print(f"\n[CarParams Found]")
    else:
        print("Waiting for CarParams...")
        time.sleep(1.0)

    # Monitor carState and raw CAN
    print("\nConnecting to carState and can...")
    sm = messaging.SubMaster(['carState', 'can'])

    print("\n" + "="*85)
    print(f"{'Time':>8} | {'Gear':>6} | {'Brk':>3} | {'Avail':>5} | {'0x110':>5} | {'Btn_Raw':>7} | {'Main_Raw':>8} | {'Signals'}")
    print("-"*85)

    try:
        last_print = 0
        raw_btn = -1
        raw_main = -1
        tcs_acc_enable = -1
        lkas_alt_seen = False

        while True:
            sm.update(100)

            for msg in sm['can']:
                if msg.address == 272: # 0x110 (LKAS_ALT)
                    lkas_alt_seen = True

                if msg.src == 1: # Bus 1
                    if msg.address == 426: # 0x1AA (CRUISE_BUTTONS_ALT)
                        dat = msg.dat
                        if len(dat) >= 5:
                            raw_main = (dat[4] >> 2) & 0x1
                            raw_btn = (dat[4] >> 4) & 0x7
                    elif msg.address == 373: # 0x175 (TCS)
                        dat = msg.dat
                        if len(dat) >= 9:
                            tcs_acc_enable = (dat[8] >> 3) & 0x3

            if sm.updated['carState']:
                cs = sm['carState']
                gear = str(cs.gearShifter)
                brake = "YES" if cs.brakePressed else "no"
                avail = "YES" if cs.cruiseState.available else "no"

                t = time.strftime("%H:%M:%S")
                if time.time() - last_print > 0.05:
                    status_110 = "OK" if lkas_alt_seen else "MISS"
                    signals = f"ACCEnable={tcs_acc_enable}"
                    print(f"{t:>8} | {gear:>6} | {brake:>3} | {avail:>5} | {status_110:>5} | {raw_btn:>7} | {raw_main:>8} | {signals}  ", end="\r")
                    last_print = time.time()

    except KeyboardInterrupt:
        print("\nExit.")

if __name__ == "__main__":
    debug_carstate()
