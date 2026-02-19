#!/usr/bin/env python3
import sys
import os

def analyze_log(log_file):
    print(f"Analyzing {log_file}...")

    # Trackers
    msgs = {}

    # Steering candidates
    candidates = [866, 272, 362]

    line_count = 0
    start_time = None
    last_time = None

    try:
        with open(log_file, 'r') as f:
            header = f.readline() # Skip header

            for line in f:
                line_count += 1
                parts = line.strip().split(',')
                if len(parts) < 4:
                    continue

                t = float(parts[0])
                if start_time is None: start_time = t
                last_time = t

                bus = int(parts[1])
                addr = int(parts[2])
                data = parts[3]

                key = (bus, addr)
                if key not in msgs:
                    msgs[key] = {'count': 0, 'data': set(), 'last_data': data}

                msgs[key]['count'] += 1
                msgs[key]['last_data'] = data
                if len(msgs[key]['data']) < 5: # Keep first few unique values
                    msgs[key]['data'].add(data)

    except FileNotFoundError:
        print("Log file not found.")
        return

    duration = last_time - start_time
    print(f"Duration: {duration:.2f}s, Total Messages: {line_count}")
    print("="*60)
    print(f"{'Bus':<4} {'ID (Dec)':<10} {'ID (Hex)':<10} {'Freq (Hz)':<10} {'Count':<10} {'Last Data'}")
    print("-" * 60)

    # Sort by ID
    for key in sorted(msgs.keys()):
        bus, addr = key
        count = msgs[key]['count']
        freq = count / duration
        last_d = msgs[key]['last_data']

        # Highlight our candidates
        prefix = ">> " if addr in candidates else "   "

        # Filter: Only show candidates or high-frequency bus 1 (likely steering)
        # OR just show everything if not too many?
        # Let's show candidates + anything on Bus 0/1 that looks like LKA (around 50hz or 100hz)

        show = addr in candidates
        show |= (freq > 40 and freq < 110) # 50Hz or 100Hz messages

        if show:
            print(f"{prefix}{bus:<4} {addr:<10} {hex(addr):<10} {freq:<10.2f} {count:<10} {last_d}")
            if addr in candidates:
                print(f"      Unique Data Samples: {list(msgs[key]['data'])[:5]}")

    print("="*60)
    print("Analysis Complete.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        # Auto-find latest csv
        files = [f for f in os.listdir('/data') if f.startswith('ev4_log_') and f.endswith('.csv')]
        if not files:
            print("No log files found in /data. Usage: python3 analyze_ev4_log.py <logfile>")
            sys.exit(1)
        # Sort by mtime
        latest_file = max([os.path.join('/data', f) for f in files], key=os.path.getmtime)
        analyze_log(latest_file)
    else:
        analyze_log(sys.argv[1])
