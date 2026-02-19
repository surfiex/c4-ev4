#!/usr/bin/env python3
import sys
import os
import collections

# Known IDs for Kia EV4 (Partial list for labeling)
KNOWN_IDS = {
    (0, 272): "LKAS_ALT (Steering)",
    (0, 866): "LKAS_ALT_OLD (Status)",
    (0, 357): "SPAS (Park Assist)",
    (0, 1056): "SCC_CONTROL",
    (0, 1057): "LFA_ICON", # Maybe?
    (1, 362): "CAM_0x16a (Lane Info)",
    (1, 272): "LKAS_ALT (Rx from Bus 0?)",
    (1, 1056): "SCC_CONTROL (Rx)",
}

def analyze_log(log_file):
    print(f"Full Analysis of {log_file}...")

    # Key: (bus, addr) -> {count, unique_data_count, last_data, changes, first_byte_stats}
    msgs = collections.defaultdict(lambda: {
        'count': 0,
        'data': set(),
        'last_data': None,
        'change_count': 0
    })

    start_time = None
    last_time = None
    line_count = 0

    try:
        with open(log_file, 'r') as f:
            header = f.readline()
            for line in f:
                line_count += 1
                try:
                    t_str, bus_str, addr_str, data_hex = line.strip().split(',')
                    t = float(t_str)
                    bus = int(bus_str)
                    addr = int(addr_str)
                except ValueError:
                    continue

                if start_time is None: start_time = t
                last_time = t

                key = (bus, addr)
                m = msgs[key]
                m['count'] += 1

                if m['last_data'] != data_hex:
                    m['change_count'] += 1
                    if len(m['data']) < 10: # Store first 10 unique values
                        m['data'].add(data_hex)
                    m['last_data'] = data_hex

    except FileNotFoundError:
        print("Log file not found.")
        return

    duration = last_time - start_time if last_time and start_time else 0
    if duration == 0: duration = 1 # Prevent div by zero

    print(f"Duration: {duration:.2f}s, Total Messages: {line_count}")
    print("="*100)
    print(f"{'Bus':<4} {'ID (Dec)':<8} {'ID (Hex)':<8} {'Name (Guess)':<25} {'Freq(Hz)':<10} {'Count':<8} {'Status':<10} {'Payload (First 16 chars)'}")
    print("-" * 100)

    for key in sorted(msgs.keys()):
        bus, addr = key
        m = msgs[key]
        freq = m['count'] / duration
        name = KNOWN_IDS.get(key, "")

        status = "STATIC"
        if m['change_count'] > 0:
            if m['change_count'] == m['count']:
                status = "NOISY"
            elif freq > 0 and m['change_count'] > m['count'] * 0.9:
                status = "DYNAMIC"
            else:
                status = "ACTIVE"

        # Simple Counter Detection? (Too complex for simple script, skipping)

        payload_preview = m['last_data'][:16] + "..." if m['last_data'] else ""

        print(f"{bus:<4} {addr:<8} {hex(addr):<8} {name:<25} {freq:<10.1f} {m['count']:<8} {status:<10} {payload_preview}")

    print("="*100)
    print("Analysis Complete.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        # Auto-find latest csv
        files = [f for f in os.listdir('/data') if f.startswith('ev4_log_') and f.endswith('.csv')]
        if not files:
            print("No log files found in /data. Usage: python3 analyze_ev4_full.py <logfile>")
            sys.exit(1)
        latest_file = max([os.path.join('/data', f) for f in files], key=os.path.getmtime)
        analyze_log(latest_file)
    else:
        analyze_log(sys.argv[1])
