#!/usr/bin/env python3
import time
import signal
import sys
from cereal import messaging

# IDs to log (Essential for LFA/Steering debugging)
LOG_IDS = [
  866,  # LKAS_ALT / CAM_0x362 (Steering command from camera)
  272,  # LKAS_ALT_OLD (Old steering ID)
  362,  # Decimal 362 (0x16A) just in case
]

keep_running = True

def signal_handler(sig, frame):
    global keep_running
    print('\nValid stop signal received. Finishing up...')
    keep_running = False

def main():
    global keep_running
    signal.signal(signal.SIGINT, signal_handler)

    start_time = int(time.time())
    log_file = f"/data/ev4_log_{start_time}.csv"

    print("="*40)
    print(f"Starting EV4 CAN Logger...")
    print(f"LOG FILE: {log_file}")
    print("="*40)
    print("Press CTRL+C to stop logging and save.")
    print("Logging started...")

    # Connect to CAN socket
    can_sock = messaging.sub_sock('can', conflate=False)

    count = 0
    with open(log_file, "w") as f:
        f.write("Time,Bus,Address,Data\n")

        try:
            while keep_running:
                # Drain all messages
                msgs = messaging.drain_sock(can_sock, wait_for_one=True)
                for m in msgs:
                    for c in m.can:
                        # Check if address is in our list OR log all if list is empty
                        if c.address in LOG_IDS:
                            # Write to file
                            line = f"{m.logMonoTime},{c.src},{c.address},{c.dat.hex()}\n"
                            f.write(line)
                            count += 1
                            if count % 10 == 0:
                                f.flush() # Flush every 10 messages to be safe

        except Exception as e:
            print(f"\nError: {e}")

    print(f"\nDone! Captured {count} relevant messages.")
    print(f"File saved to: {log_file}")

if __name__ == "__main__":
    main()
