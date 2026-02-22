import json
import os
import sys
from collections import defaultdict

def hex_to_bin_str(hex_val, length_bytes):
    try:
        val = int(hex_val, 16)
        return f"{val:0{length_bytes * 8}b}"
    except Exception:
        return ""

def generate_bit_report(log_file):
    print(f"Analyzing log file: {log_file}")

    message_states = {}
    events = []

    if not os.path.exists(log_file):
        print(f"Error: {log_file} not found.")
        return

    line_count = 0
    with open(log_file, 'r') as f:
        for line in f:
            if not line.strip(): continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            if 'event' in data:
                events.append(data)
                continue

            t = data['time']
            bus = data['bus']
            addr = data['address']
            hex_data = data['data']

            byte_len = len(hex_data) // 2
            bin_data = hex_to_bin_str(hex_data, byte_len)

            if not bin_data:
                continue

            if bus not in message_states:
                message_states[bus] = {}

            if addr not in message_states[bus]:
                message_states[bus][addr] = {
                    'last_data': bin_data,
                    'flips': {} # bit_idx: [(time, value)]
                }
            else:
                last = message_states[bus][addr]['last_data']
                min_len = min(len(bin_data), len(last))

                for i in range(min_len):
                    if bin_data[i] != last[i]:
                        if i not in message_states[bus][addr]['flips']:
                            message_states[bus][addr]['flips'][i] = []
                        message_states[bus][addr]['flips'][i].append((t, int(bin_data[i])))

                message_states[bus][addr]['last_data'] = bin_data

            line_count += 1
            if line_count % 50000 == 0:
                print(f"Processed {line_count} messages...", end='\r')

    print(f"\nFinished parsing {line_count} messages. Found {len(events)} events.")

    # Analyze correlation
    print("\n[Correlation Analysis results]")
    print("-" * 80)

    for i in range(len(events)):
        start_t = events[i]['time']
        end_t = events[i+1]['time'] if i+1 < len(events) else 999999
        event_name = events[i]['event']

        if "_OFF" in event_name or "BASELINE" in event_name or "CLOSE" in event_name:
            continue

        print(f"\n▶ Action: {event_name} (starts at {start_t}s)")

        candidates = []
        for bus, addrs in message_states.items():
            for addr, info in addrs.items():
                for bit_idx, flips in info['flips'].items():
                    # Check if this bit flipped within the 1-second window after the action started
                    # and didn't flip like crazy before
                    action_flips = [f for f in flips if start_t <= f[0] <= start_t + 2.0]
                    if action_flips:
                        # Baseline check: did it flip in the 0.5s BEFORE the action?
                        pre_flips = [f for f in flips if start_t - 0.5 <= f[0] < start_t]
                        if not pre_flips:
                             candidates.append({
                                 'bus': bus,
                                 'id': addr,
                                 'bit': bit_idx,
                                 'val': action_flips[0][1]
                             })

        if not candidates:
            print("  (No unique bit flips found for this action)")
        else:
            for c in candidates:
                print(f"  [Potential Match] Bus: {c['bus']}, ID: 0x{c['id']:03X}, Bit: {c['bit']} (Value -> {c['val']})")

if __name__ == "__main__":
    log_file = sys.argv[1] if len(sys.argv) > 1 else ""
    if not log_file:
        print("Usage: python3 analyze_signal_hunt.py <your_log.jsonl>")
    else:
        generate_bit_report(log_file)
