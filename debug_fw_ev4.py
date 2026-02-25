#!/usr/bin/env python3
import time
import binascii
from collections import namedtuple
from panda import Panda
from opendbc.car.structs import CarParams
from opendbc.car.isotp_parallel_query import IsoTpParallelQuery

# Define CanData locally to ensure compatibility
CanData = namedtuple('CanData', ['address', 'dat', 'src'])

def debug_fw_queries():
  pandas = Panda.list()
  if not pandas:
    print("No Panda found. Please ensure your Comma device or Panda is connected.")
    return

  print(f"Found {len(pandas)} Panda(s). Using the first one.")
  panda = Panda(pandas[0])

  # Set up for EV4 (CAN-FD)
  # We use allOutput to ensure we can send queries
  panda.set_safety_mode(CarParams.SafetyModel.allOutput)
  panda.can_reset_communications()

  # EV4 uses 500kbps / 2000kbps CAN-FD on Bus 0 and Bus 1
  for bus in [0, 1]:
    panda.set_can_speed_kbps(bus, 500)
    panda.set_can_data_speed_kbps(bus, 2000)
    panda.set_canfd_non_iso(bus, False)
    panda.can_clear(bus)

  time.sleep(1)

  print("="*50)
  print("KIA EV4 FIRMWARE DEBUGGER")
  print("This script will query ECUs for identification strings.")
  print("="*50)

  def can_send(msgs):
    panda_msgs = [[m.address, m.dat, m.src] for m in msgs]
    panda.can_send_many(panda_msgs, fd=True)

  def can_recv(wait_for_one=False):
    ret = []
    msgs = panda.can_recv()
    for m in msgs:
      if len(m) == 4:
        ret.append(CanData(m[0], m[2], m[3]))
      elif len(m) == 3:
        ret.append(CanData(m[0], m[1], m[2]))
    return [ret] if ret else []

  # Addresses of interest for EV4
  # 0x7C4: Camera, 0x7D0: Radar, 0x7D4: EPS, 0x7B3: HVAC, 0x7B7: Gateway/ADAS
  addrs = [0x7c4, 0x7d0, 0x7d4, 0x7b3, 0x7b7, 0x730, 0x7e4, 0x7e0]

  # DIDs to attempt
  # 0xF100 (Long Description), 0xF191 (SW Version), 0xF188 (Part Number), 0x0100 (Common for CAN-FD)
  dids = [
    (b'\x22\xf1\x00', "F100 (Long ID)"),
    (b'\x22\xf1\x91', "F191 (SW Version)"),
    (b'\x22\xf1\x88', "F188 (Part Number)"),
    (b'\x22\x01\x00', "0100 (Platform Info)")
  ]

  for req_bytes, req_name in dids:
    print(f"\n[QUERY] {req_name}...")
    for bus in [0, 1]:
      print(f"  Bus {bus}:")
      try:
        query = IsoTpParallelQuery(can_send, can_recv, bus, addrs, [req_bytes], [b'\x62'+req_bytes[1:]])
        responses = query.get_data(1.5)
        if not responses:
          print(f"    No ECUs responded on Bus {bus}")
        for addr, response in responses.items():
            if response:
                try:
                    text = response.decode('ascii', errors='ignore').strip()
                    hex_val = binascii.hexlify(response).decode()
                    print(f"    0x{addr:03X} -> Hex: {hex_val}")
                    print(f"    0x{addr:03X} -> Raw: {text}")
                except:
                    print(f"    0x{addr:03X} -> Hex: {binascii.hexlify(response).decode()}")
      except Exception as e:
        print(f"    Query Error on Bus {bus}: {e}")

  print("\n" + "="*50)
  print("Debug Complete. If you see 'CT1...' or '99211...' please copy those lines.")
  print("="*50)

if __name__ == "__main__":
  debug_fw_queries()
