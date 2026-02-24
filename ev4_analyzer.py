#!/usr/bin/env python3
"""
EV4 CAN Signal Analyzer v2.0 — Production-grade signal hunting tool
Designed for analyzing millions of CAN frames from Kia EV4 logs.

Usage:
  python ev4_analyzer.py <log.csv> [--id 234] [--scenario hod|lane|regen|isla]
  python ev4_analyzer.py <log.csv> --full-scan
  python ev4_analyzer.py <log.csv> --correlate 234,293
  python ev4_analyzer.py <log.csv> --transition-hunt --bus 1

Capabilities:
  1. Full Bus Scan: Profile every CAN ID (count, frequency, byte entropy)
  2. Bit Transition Analysis: Find bits that toggle between states
  3. Value Tracking: Track multi-bit signal values over time
  4. Cross-ID Correlation: Find signals that change together
  5. Scenario-based Hunting: Guided analysis for specific targets (HOD, lane, regen, ISLA)
"""

import sys
import csv
import os
import json
import binascii
import argparse
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Set

# ─── Data Structures ────────────────────────────────────────────────

@dataclass
class SignalProfile:
    """Per-bit statistics for a CAN message."""
    ones: int = 0
    zeros: int = 0
    transitions: int = 0  # number of 0->1 or 1->0 changes
    last_value: int = -1

@dataclass
class MessageProfile:
    """Per-CAN-ID statistics."""
    count: int = 0
    first_ts: int = 0
    last_ts: int = 0
    buses: Set[str] = field(default_factory=set)
    data_len: int = 0
    bit_profiles: Dict[int, SignalProfile] = field(default_factory=dict)
    byte_min: Dict[int, int] = field(default_factory=dict)
    byte_max: Dict[int, int] = field(default_factory=dict)
    byte_unique: Dict[int, Set[int]] = field(default_factory=dict)

    @property
    def freq_hz(self):
        dt = (self.last_ts - self.first_ts)
        if dt <= 0: return 0
        return self.count / (dt / 1e9)

# ─── Core Analyzer ──────────────────────────────────────────────────

class CANAnalyzer:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.profiles: Dict[int, MessageProfile] = {}
        self.total_rows = 0
        self._loaded = False

    def load(self, target_ids: Optional[List[int]] = None, target_bus: Optional[str] = None):
        """Single-pass load: read the entire CSV once and build all profiles."""
        print(f"[*] Loading {self.filepath} ...")
        self.profiles.clear()
        self.total_rows = 0

        with open(self.filepath, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                self.total_rows += 1
                addr_str = row.get('Address', '')
                bus = row.get('Bus', '')
                data_hex = row.get('Data', '')
                ts_str = row.get('Time', '0')

                if not addr_str or not data_hex:
                    continue

                try:
                    addr = int(addr_str)
                    ts = int(ts_str)
                except ValueError:
                    continue

                if target_ids and addr not in target_ids:
                    continue
                if target_bus and bus != target_bus:
                    continue

                try:
                    data_bytes = binascii.unhexlify(data_hex)
                except (ValueError, binascii.Error):
                    continue

                # Get or create profile
                if addr not in self.profiles:
                    p = MessageProfile()
                    p.first_ts = ts
                    p.data_len = len(data_bytes)
                    self.profiles[addr] = p
                p = self.profiles[addr]
                p.count += 1
                p.last_ts = ts
                p.buses.add(bus)

                # Per-byte stats
                for byte_idx in range(len(data_bytes)):
                    bval = data_bytes[byte_idx]
                    if byte_idx not in p.byte_min:
                        p.byte_min[byte_idx] = bval
                        p.byte_max[byte_idx] = bval
                        p.byte_unique[byte_idx] = set()
                    p.byte_min[byte_idx] = min(p.byte_min[byte_idx], bval)
                    p.byte_max[byte_idx] = max(p.byte_max[byte_idx], bval)
                    p.byte_unique[byte_idx].add(bval)

                    # Per-bit stats
                    for bit_idx in range(8):
                        global_bit = byte_idx * 8 + bit_idx
                        bit_val = (bval >> bit_idx) & 1

                        if global_bit not in p.bit_profiles:
                            p.bit_profiles[global_bit] = SignalProfile()
                        bp = p.bit_profiles[global_bit]

                        if bit_val == 1:
                            bp.ones += 1
                        else:
                            bp.zeros += 1

                        if bp.last_value != -1 and bp.last_value != bit_val:
                            bp.transitions += 1
                        bp.last_value = bit_val

                if self.total_rows % 500000 == 0:
                    print(f"  ... {self.total_rows:,} rows processed")

        self._loaded = True
        n_ids = len(self.profiles)
        print(f"[+] Done: {self.total_rows:,} rows, {n_ids} unique CAN IDs")
        return self

    # ─── Analysis Commands ──────────────────────────────────────────

    def full_scan(self):
        """Print a summary of every CAN ID found."""
        if not self._loaded:
            self.load()

        print(f"\n{'='*80}")
        print(f"  FULL BUS SCAN — {len(self.profiles)} CAN IDs")
        print(f"{'='*80}")
        print(f"{'ID':>6} {'Hex':>6} {'Bus':>6} {'Count':>8} {'Hz':>8} {'Bytes':>5} {'Toggling Bits':>14} {'Static Bits':>11}")
        print(f"{'-'*6:>6} {'-'*6:>6} {'-'*6:>6} {'-'*8:>8} {'-'*8:>8} {'-'*5:>5} {'-'*14:>14} {'-'*11:>11}")

        for addr in sorted(self.profiles.keys()):
            p = self.profiles[addr]
            toggling = sum(1 for bp in p.bit_profiles.values()
                          if bp.ones > 0 and bp.zeros > 0 and bp.transitions > 10)
            static_ones = sum(1 for bp in p.bit_profiles.values()
                             if bp.ones > 0 and bp.zeros == 0)
            buses = ','.join(sorted(p.buses))
            print(f"{addr:>6} {addr:>5x} {buses:>6} {p.count:>8,} {p.freq_hz:>7.1f} {p.data_len:>5} {toggling:>14} {static_ones:>11}")

    def analyze_id(self, target_id: int):
        """Deep analysis of a single CAN ID: per-byte and per-bit breakdown."""
        if not self._loaded:
            self.load(target_ids=[target_id])

        if target_id not in self.profiles:
            print(f"[!] ID {target_id} not found in log")
            return

        p = self.profiles[target_id]
        print(f"\n{'='*80}")
        print(f"  DEEP ANALYSIS — ID {target_id} (0x{target_id:03x})")
        print(f"  Messages: {p.count:,} | Freq: {p.freq_hz:.1f} Hz | Buses: {','.join(sorted(p.buses))}")
        print(f"{'='*80}")

        # Byte-level summary
        print(f"\n--- Byte-Level Summary ---")
        print(f"{'Byte':>4} {'Min':>5} {'Max':>5} {'Unique':>6} {'Range':>20} {'Classification':>20}")
        for byte_idx in sorted(p.byte_min.keys()):
            bmin = p.byte_min[byte_idx]
            bmax = p.byte_max[byte_idx]
            uniq = len(p.byte_unique[byte_idx])
            rng = f"0x{bmin:02x}..0x{bmax:02x}"

            if uniq == 1:
                cls = "CONSTANT"
            elif uniq == 2:
                vals = sorted(p.byte_unique[byte_idx])
                if vals == [0, 1]:
                    cls = "BOOLEAN"
                else:
                    cls = f"TOGGLE ({vals[0]},{vals[1]})"
            elif uniq <= 8:
                cls = f"ENUM ({uniq} vals)"
            elif bmax - bmin < 256:
                cls = f"COUNTER/VALUE"
            else:
                cls = "FULL RANGE"
            print(f"{byte_idx:>4} {bmin:>5} {bmax:>5} {uniq:>6} {rng:>20} {cls:>20}")

        # Bit-level: only show interesting bits
        print(f"\n--- Interesting Bits (toggling or always-1) ---")
        print(f"{'Bit':>4} {'Byte.bit':>8} {'Ones':>8} {'Zeros':>8} {'Trans':>8} {'Type':>15}")
        for bit_idx in sorted(p.bit_profiles.keys()):
            bp = p.bit_profiles[bit_idx]
            byte_num = bit_idx // 8
            bit_in_byte = bit_idx % 8

            if bp.ones > 0 and bp.zeros > 0 and bp.transitions > 5:
                bit_type = "TOGGLING"
            elif bp.ones > 0 and bp.zeros == 0:
                bit_type = "ALWAYS 1"
            elif bp.ones == 0 and bp.zeros > 0:
                continue  # always 0, skip
            else:
                continue  # no data

            if bit_type == "TOGGLING" or bit_type == "ALWAYS 1":
                pct = bp.ones / (bp.ones + bp.zeros) * 100
                print(f"{bit_idx:>4} {byte_num:>3}.{bit_in_byte:<4} {bp.ones:>8,} {bp.zeros:>8,} {bp.transitions:>8,} {bit_type:>15} ({pct:.1f}% high)")

    def transition_hunt(self, min_transitions: int = 3, max_transitions: int = 100):
        """Find bits across ALL IDs that toggle a specific number of times.
        Perfect for finding boolean flags like HOD touch, brake, buttons.
        Low transition count = rare event (brake pedal, button press).
        """
        if not self._loaded:
            self.load()

        print(f"\n{'='*80}")
        print(f"  TRANSITION HUNT — Looking for bits with {min_transitions}-{max_transitions} state changes")
        print(f"{'='*80}")
        print(f"{'ID':>6} {'Hex':>5} {'Bit':>4} {'Byte.bit':>8} {'Trans':>6} {'Ones%':>6} {'Bus':>4}")

        results = []
        for addr in sorted(self.profiles.keys()):
            p = self.profiles[addr]
            for bit_idx in sorted(p.bit_profiles.keys()):
                bp = p.bit_profiles[bit_idx]
                if min_transitions <= bp.transitions <= max_transitions and bp.ones > 0 and bp.zeros > 0:
                    byte_num = bit_idx // 8
                    bit_in_byte = bit_idx % 8
                    pct = bp.ones / (bp.ones + bp.zeros) * 100
                    buses = ','.join(sorted(p.buses))
                    results.append((addr, bit_idx, byte_num, bit_in_byte, bp.transitions, pct, buses))

        results.sort(key=lambda x: x[4])  # sort by transition count
        for addr, bit_idx, byte_num, bit_in_byte, trans, pct, buses in results:
            print(f"{addr:>6} {addr:>4x} {bit_idx:>4} {byte_num:>3}.{bit_in_byte:<4} {trans:>6} {pct:>5.1f}% {buses:>4}")

        print(f"\nTotal: {len(results)} candidate signals found")

    def correlate(self, id_a: int, id_b: int):
        """Find bits in id_a and id_b that transition at similar times.
        Requires re-reading the file to get temporal data.
        """
        print(f"\n[*] Correlating ID {id_a} (0x{id_a:03x}) with ID {id_b} (0x{id_b:03x})...")

        # Collect timestamped bit states for both IDs
        states_a: Dict[int, List[Tuple[int, int]]] = defaultdict(list)
        states_b: Dict[int, List[Tuple[int, int]]] = defaultdict(list)
        prev_a: Dict[int, int] = {}
        prev_b: Dict[int, int] = {}

        with open(self.filepath, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                addr_str = row.get('Address', '')
                data_hex = row.get('Data', '')
                ts_str = row.get('Time', '0')
                if not addr_str or not data_hex: continue
                try:
                    addr = int(addr_str)
                    ts = int(ts_str)
                    data_bytes = binascii.unhexlify(data_hex)
                except: continue

                target_states = None
                prev_states = None
                if addr == id_a:
                    target_states = states_a
                    prev_states = prev_a
                elif addr == id_b:
                    target_states = states_b
                    prev_states = prev_b
                else:
                    continue

                for byte_idx in range(len(data_bytes)):
                    for bit_idx in range(8):
                        global_bit = byte_idx * 8 + bit_idx
                        val = (data_bytes[byte_idx] >> bit_idx) & 1
                        if global_bit in prev_states and prev_states[global_bit] != val:
                            target_states[global_bit].append((ts, val))
                        prev_states[global_bit] = val

        # Find bits with close temporal correlation
        WINDOW = 100_000_000  # 100ms
        print(f"\n{'Bit_A':>6} {'Bit_B':>6} {'Corr%':>6} {'A_trans':>8} {'B_trans':>8}")
        for bit_a, events_a in sorted(states_a.items()):
            if len(events_a) < 2: continue
            for bit_b, events_b in sorted(states_b.items()):
                if len(events_b) < 2: continue
                # Count how many transitions in A have a matching transition in B within WINDOW
                matches = 0
                b_idx = 0
                for ts_a, _ in events_a:
                    while b_idx < len(events_b) and events_b[b_idx][0] < ts_a - WINDOW:
                        b_idx += 1
                    if b_idx < len(events_b) and abs(events_b[b_idx][0] - ts_a) <= WINDOW:
                        matches += 1
                corr = matches / len(events_a) * 100 if events_a else 0
                if corr > 50:
                    ba, bia = bit_a // 8, bit_a % 8
                    bb, bib = bit_b // 8, bit_b % 8
                    print(f"  {bit_a:>3} ({ba}.{bia}) <-> {bit_b:>3} ({bb}.{bib})   {corr:>5.1f}%   {len(events_a):>8}   {len(events_b):>8}")

    def export_timeseries(self, target_id: int, output_path: str):
        """Export a specific CAN ID's byte values as a time-series CSV for graphing."""
        print(f"[*] Exporting ID {target_id} time-series to {output_path} ...")
        count = 0
        with open(self.filepath, 'r') as fin, open(output_path, 'w', newline='') as fout:
            reader = csv.DictReader(fin)
            # Determine max bytes from first match
            header_written = False
            for row in reader:
                if row.get('Address', '') != str(target_id): continue
                data_hex = row.get('Data', '')
                ts = row.get('Time', '0')
                bus = row.get('Bus', '')
                try:
                    data_bytes = binascii.unhexlify(data_hex)
                except: continue

                if not header_written:
                    cols = ['Time', 'Bus'] + [f'B{i}' for i in range(len(data_bytes))]
                    writer = csv.writer(fout)
                    writer.writerow(cols)
                    header_written = True

                writer.writerow([ts, bus] + [b for b in data_bytes])
                count += 1

        print(f"[+] Exported {count:,} rows")


# ─── CLI ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='EV4 CAN Signal Analyzer v2.0')
    parser.add_argument('logfile', help='Path to CSV log file')
    parser.add_argument('--full-scan', action='store_true', help='Profile all CAN IDs')
    parser.add_argument('--id', type=int, help='Deep-analyze a specific CAN ID')
    parser.add_argument('--transition-hunt', action='store_true', help='Find rare toggle bits')
    parser.add_argument('--min-trans', type=int, default=2, help='Min transitions for hunt (default: 2)')
    parser.add_argument('--max-trans', type=int, default=50, help='Max transitions for hunt (default: 50)')
    parser.add_argument('--correlate', help='Correlate two IDs, e.g. "234,293"')
    parser.add_argument('--export', type=int, help='Export CAN ID as time-series CSV')
    parser.add_argument('--bus', help='Filter by bus number')
    parser.add_argument('--out', default='ev4_export.csv', help='Output file for export')

    args = parser.parse_args()

    analyzer = CANAnalyzer(args.logfile)

    if args.full_scan:
        analyzer.load(target_bus=args.bus)
        analyzer.full_scan()

    elif args.id is not None:
        analyzer.load(target_ids=[args.id], target_bus=args.bus)
        analyzer.analyze_id(args.id)

    elif args.transition_hunt:
        analyzer.load(target_bus=args.bus)
        analyzer.transition_hunt(args.min_trans, args.max_trans)

    elif args.correlate:
        parts = args.correlate.split(',')
        id_a, id_b = int(parts[0]), int(parts[1])
        analyzer.correlate(id_a, id_b)

    elif args.export is not None:
        analyzer.export_timeseries(args.export, args.out)

    else:
        # Default: full scan
        analyzer.load(target_bus=args.bus)
        analyzer.full_scan()

if __name__ == '__main__':
    main()
