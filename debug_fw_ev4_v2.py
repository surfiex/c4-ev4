#!/usr/bin/env python3
import time
import binascii
from collections import namedtuple
from panda import Panda
from opendbc.car.structs import CarParams

# Define CanData locally
CanData = namedtuple('CanData', ['address', 'dat', 'src'])

def debug_fw_simple():
  pandas = Panda.list()
  if not pandas:
    print("No Panda found.")
    return

  panda = Panda(pandas[0])
  print(f"Panda connected. Serial: {panda.get_serial()[0]}")

  # ELM327 safety often blocks queries, use allOutput
  panda.set_safety_mode(CarParams.SafetyModel.allOutput)
  panda.can_reset_communications()

  for bus in [0, 1]:
    panda.set_can_speed_kbps(bus, 500)
    panda.set_can_data_speed_kbps(bus, 2000)
    panda.set_canfd_non_iso(bus, False)

  time.sleep(1)

  # Target ECUs: Camera(7C4), Radar(7D0), ADAS(7B7), EPS(7D4), HVAC(7B3)
  addrs = [0x7c4, 0x7d0, 0x7b7, 0x7d4, 0x7b3]

  # Common DIDs
  dids = [
    (b'\x22\xf1\x00', "F100 Long ID"),
    (b'\x22\xf1\x91', "F191 SW Version"),
    (b'\x22\xf1\x88', "F188 Part Number"),
  ]

  print("\nStarting manual one-by-one query...")
  for bus in [0, 1]:
    print(f"\n--- Checking Bus {bus} ---")
    for addr in addrs:
      for did_bytes, did_name in dids:
        # Construct ISO-TP Single Frame request
        # [DLC, Service, DID_High, DID_Low]
        # Length 3, Service 0x22, DID
        msg = [3, did_bytes[0], did_bytes[1], did_bytes[2], 0, 0, 0, 0]

        print(f"Querying 0x{addr:X} for {did_name} on Bus {bus}...", end=" ", flush=True)

        panda.can_clear(bus)
        panda.can_send(addr, bytes(msg), bus)

        # Wait for response
        found = False
        start_time = time.monotonic()
        while time.monotonic() - start_time < 0.5:
          msgs = panda.can_recv()
          for msg in msgs:
            if len(msg) == 4:
              rx_addr, _, rx_dat, rx_bus = msg
            else:
              rx_addr, rx_dat, rx_bus = msg

            if rx_bus == bus and rx_addr == (addr + 8):
                # Potential response
                print(f"\n    MATCH: 0x{rx_addr:X} response: {rx_dat.hex()}")
                found = True
                break
          if found: break
          time.sleep(0.01)

        if not found:
            print("No response")

  print("\nDone. If all say 'No response', please confirm if the ignition is ON.")

if __name__ == "__main__":
  debug_fw_simple()
