#!/usr/bin/env python3
import os
import subprocess
import time
try:
    from panda import Panda
    import cereal.messaging as messaging
except ImportError:
    print("Error: openpilot environment not found.")
    exit(1)

def check_process(name):
    try:
        out = subprocess.check_output(["ps", "aux"], encoding='utf-8')
        return name in out
    except:
        return False

def main():
    print("--- CAN Diagnostic Tool ---")

    # 1. Check processes
    is_pandad = check_process("pandad")
    is_manager = check_process("manager")
    print(f"Pandad running: {is_pandad}")
    print(f"Manager running: {is_manager}")

    # 2. Check Panda hardware
    print("\n--- Panda Hardware Check ---")
    try:
        serials = Panda.list()
        print(f"Panda Serials: {serials}")
        if len(serials) > 0:
            if not is_pandad:
                print("Trying to read directly from Panda...")
                p = Panda(serials[0])
                p.set_safety_mode(Panda.SAFETY_ALLOUTPUT) # Just for testing
                start = time.time()
                msgs = 0
                while time.time() - start < 2:
                    can_recv = p.can_recv()
                    msgs += len(can_recv)
                print(f"Direct Panda Read: {msgs} messages in 2 seconds.")
                p.close()
            else:
                print("Pandad is occupying the Panda. Cannot read directly.")
        else:
            print("No Panda found!")
    except Exception as e:
        print(f"Panda Check Error: {e}")

    # 3. Check ZMQ Messaging
    print("\n--- ZMQ Connectivity Check ---")
    try:
        sm = messaging.SubMaster(['can'])
        print("Waiting 3 seconds for ZMQ 'can' messages...")
        start = time.time()
        msgs = 0
        while time.time() - start < 3:
            sm.update(100)
            if sm.updated['can']:
                msgs += len(sm['can'])
        print(f"ZMQ 'can' messages: {msgs} received.")
    except Exception as e:
        print(f"ZMQ Check Error: {e}")

    print("\n--- Summary ---")
    if is_pandad and msgs > 0:
        print("✅ System looks OK. Signal hunt SHOULD work.")
    elif is_pandad and msgs == 0:
        print("❌ Pandad is running but NO messages on ZMQ. Check car ignition/connection.")
    elif not is_pandad and len(serials) > 0:
        print("⚠️ Pandad NOT running. Please run ./launch_openpilot.sh first.")
    else:
        print("❌ Critical Error: No Panda or no data.")

if __name__ == "__main__":
    main()
