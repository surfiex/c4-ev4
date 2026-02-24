# -*- coding: utf-8 -*-
"""
EV4 Signal Finder v3 - Multi-file cross-validation with CSV export.

Usage:
  python ev4_find_signals.py log1.csv log2.csv log3.csv
  python ev4_find_signals.py ev4_re_log_*.csv --output results.csv

Outputs:
  - Console: Summary of all signal candidates
  - results.csv: Full structured results for every candidate signal
"""
import csv, binascii, sys, os, glob, json
from collections import defaultdict

def stream_analyze(filepath):
    """Single-pass streaming analysis. Returns per-addr per-byte stats."""
    byte_vals = defaultdict(lambda: defaultdict(set))
    byte_trans = defaultdict(lambda: defaultdict(int))
    byte_prev = defaultdict(lambda: defaultdict(lambda: -1))
    addr_count = defaultdict(int)
    addr_bus = defaultdict(set)
    addr_datalen = {}
    row_count = 0

    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            row_count += 1
            try:
                addr = int(row['Address'])
                bus = row['Bus']
                data = binascii.unhexlify(row['Data'])
            except:
                continue
            addr_count[addr] += 1
            addr_bus[addr].add(bus)
            if addr not in addr_datalen:
                addr_datalen[addr] = len(data)
            for bi in range(len(data)):
                v = data[bi]
                byte_vals[addr][bi].add(v)
                prev = byte_prev[addr][bi]
                if prev != -1 and prev != v:
                    byte_trans[addr][bi] += 1
                byte_prev[addr][bi] = v
            if row_count % 1000000 == 0:
                sys.stderr.write("  %d rows...\n" % row_count)

    sys.stderr.write("  %s: %d rows, %d IDs\n" % (os.path.basename(filepath), row_count, len(addr_count)))
    return byte_vals, byte_trans, addr_count, addr_bus, addr_datalen

def find_candidates(byte_vals, byte_trans, addr_count, addr_bus):
    """Extract all signal candidates from analysis results."""
    candidates = []

    # --- ISLA (ID 506) ---
    speed_set = {30, 40, 50, 60, 70, 80, 90, 100, 110, 120}
    if 506 in byte_vals:
        for bi in sorted(byte_vals[506].keys()):
            vals = sorted(byte_vals[506][bi])
            hits = set(vals) & speed_set
            trans = byte_trans[506][bi]
            if hits:
                candidates.append({
                    'category': 'ISLA_SPEED', 'id': 506, 'byte': bi,
                    'values': vals, 'transitions': trans,
                    'bus': ','.join(sorted(addr_bus[506])),
                    'confidence': 'HIGH', 'note': 'Speed values: %s' % sorted(hits)
                })
            elif len(vals) > 1 and len(vals) < 30 and bi >= 3:
                candidates.append({
                    'category': 'ISLA_OTHER', 'id': 506, 'byte': bi,
                    'values': vals[:15], 'transitions': trans,
                    'bus': ','.join(sorted(addr_bus[506])),
                    'confidence': 'LOW', 'note': '%d unique values' % len(vals)
                })

    # --- REGEN PADDLE ---
    for addr in sorted(byte_vals.keys()):
        if addr_count[addr] < 100: continue
        for bi in sorted(byte_vals[addr].keys()):
            if bi < 3: continue
            vals = sorted(byte_vals[addr][bi])
            trans = byte_trans[addr][bi]
            if 3 <= len(vals) <= 6 and max(vals) <= 10 and min(vals) == 0 and 2 <= trans <= 200:
                candidates.append({
                    'category': 'REGEN', 'id': addr, 'byte': bi,
                    'values': vals, 'transitions': trans,
                    'bus': ','.join(sorted(addr_bus[addr])),
                    'confidence': 'HIGH' if len(vals) == 4 else 'MEDIUM',
                    'note': '%d regen levels' % len(vals)
                })

    # --- LANE DETECTION (CAM 0x362/363/364) ---
    for cam_id in [866, 867, 868]:
        if cam_id not in byte_vals: continue
        for bi in sorted(byte_vals[cam_id].keys()):
            if bi < 3: continue
            vals = sorted(byte_vals[cam_id][bi])
            trans = byte_trans[cam_id][bi]
            if 2 <= len(vals) <= 10 and max(vals) <= 15 and trans > 5:
                candidates.append({
                    'category': 'LANE', 'id': cam_id, 'byte': bi,
                    'values': vals, 'transitions': trans,
                    'bus': ','.join(sorted(addr_bus[cam_id])),
                    'confidence': 'HIGH' if len(vals) <= 4 else 'MEDIUM',
                    'note': 'Lane type enum candidate'
                })

    # --- HOD (Hands-On Detection) ---
    for addr in sorted(byte_vals.keys()):
        if addr_count[addr] < 1000: continue
        for bi in sorted(byte_vals[addr].keys()):
            if bi < 3: continue
            vals = sorted(byte_vals[addr][bi])
            trans = byte_trans[addr][bi]
            if len(vals) == 1 and vals[0] in [1, 2, 3, 4, 5]:
                candidates.append({
                    'category': 'HOD_CONSTANT', 'id': addr, 'byte': bi,
                    'values': vals, 'transitions': 0,
                    'bus': ','.join(sorted(addr_bus[addr])),
                    'confidence': 'LOW',
                    'note': 'Constant %d (grip?)' % vals[0]
                })
            elif 2 <= len(vals) <= 4 and max(vals) <= 5 and min(vals) >= 0 and trans > 0:
                candidates.append({
                    'category': 'HOD_TOGGLE', 'id': addr, 'byte': bi,
                    'values': vals, 'transitions': trans,
                    'bus': ','.join(sorted(addr_bus[addr])),
                    'confidence': 'MEDIUM',
                    'note': 'HOD-like enum, %d trans' % trans
                })

    return candidates

def cross_validate(all_candidates):
    """Cross-validate candidates across multiple log files.
    A candidate is 'confirmed' if it appears in ALL logs with similar values.
    """
    # Group by (category, id, byte)
    grouped = defaultdict(list)
    for file_idx, cands in enumerate(all_candidates):
        for c in cands:
            key = (c['category'], c['id'], c['byte'])
            grouped[key].append((file_idx, c))

    n_files = len(all_candidates)
    confirmed = []
    for key, entries in sorted(grouped.items()):
        files_seen = set(e[0] for e in entries)
        cat, addr, byte_idx = key
        if len(files_seen) == n_files:
            # Check if values are consistent
            all_vals = [set(e[1]['values']) for e in entries]
            union = set()
            for v in all_vals: union |= v
            total_trans = sum(e[1]['transitions'] for e in entries)
            best = entries[0][1].copy()
            best['values'] = sorted(union)
            best['transitions'] = total_trans
            best['files_matched'] = len(files_seen)
            best['total_files'] = n_files
            best['cross_validated'] = True
            if best['confidence'] != 'HIGH':
                best['confidence'] = 'HIGH' if len(files_seen) == n_files else best['confidence']
            confirmed.append(best)
        else:
            best = entries[0][1].copy()
            best['files_matched'] = len(files_seen)
            best['total_files'] = n_files
            best['cross_validated'] = False
            confirmed.append(best)

    return confirmed

def save_csv(candidates, output_path):
    """Save candidates to CSV."""
    if not candidates:
        print("No candidates to save")
        return
    fields = ['category', 'confidence', 'cross_validated', 'files_matched', 'total_files',
              'id', 'byte', 'values', 'transitions', 'bus', 'note']
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for c in sorted(candidates, key=lambda x: (x['category'], x['id'], x['byte'])):
            row = c.copy()
            row['values'] = str(row['values'])
            row['id'] = '0x%03x (%d)' % (row['id'], row['id'])
            writer.writerow(row)
    print("Saved %d candidates to %s" % (len(candidates), output_path))

def print_summary(candidates):
    """Print human-readable summary."""
    by_cat = defaultdict(list)
    for c in candidates:
        by_cat[c['category']].append(c)

    category_names = {
        'ISLA_SPEED': '1. ISLA (Speed Limit)',
        'ISLA_OTHER': '1. ISLA (Other)',
        'REGEN': '2. Regen Paddle',
        'LANE': '3. Lane Detection',
        'HOD_CONSTANT': '4. HOD (Constant Grip)',
        'HOD_TOGGLE': '4. HOD (Toggle)',
    }

    print("\n" + "=" * 70)
    print("  SIGNAL CANDIDATE SUMMARY")
    print("=" * 70)

    for cat_key in ['ISLA_SPEED', 'REGEN', 'LANE', 'HOD_TOGGLE', 'HOD_CONSTANT', 'ISLA_OTHER']:
        if cat_key not in by_cat: continue
        cands = by_cat[cat_key]
        high = [c for c in cands if c.get('cross_validated', False)]
        print("\n  --- %s (%d candidates, %d cross-validated) ---" % (
            category_names.get(cat_key, cat_key), len(cands), len(high)))
        for c in sorted(cands, key=lambda x: (-1 if x.get('cross_validated') else 0, x['id'])):
            xv = " [CONFIRMED]" if c.get('cross_validated') else ""
            print("    ID %d (0x%03x) B%d: vals=%s trans=%d bus=%s %s%s" % (
                c['id'], c['id'], c['byte'], c['values'], c['transitions'],
                c['bus'], c.get('note', ''), xv))

def main():
    args = sys.argv[1:]
    output_path = 'ev4_signal_results.csv'

    # Parse --output flag
    if '--output' in args:
        idx = args.index('--output')
        output_path = args[idx + 1]
        args = args[:idx] + args[idx+2:]

    # Expand globs for Windows
    files = []
    for a in args:
        expanded = glob.glob(a)
        if expanded:
            files.extend(expanded)
        else:
            files.append(a)

    if not files:
        print("Usage: python ev4_find_signals.py log1.csv [log2.csv ...] [--output results.csv]")
        sys.exit(1)

    print("Analyzing %d log file(s)..." % len(files))
    all_candidates = []
    for filepath in files:
        print("\n--- %s ---" % os.path.basename(filepath))
        byte_vals, byte_trans, addr_count, addr_bus, _ = stream_analyze(filepath)
        cands = find_candidates(byte_vals, byte_trans, addr_count, addr_bus)
        all_candidates.append(cands)
        print("  Found %d raw candidates" % len(cands))

    if len(files) > 1:
        print("\nCross-validating across %d files..." % len(files))
        final = cross_validate(all_candidates)
    else:
        final = all_candidates[0]
        for c in final:
            c['files_matched'] = 1
            c['total_files'] = 1
            c['cross_validated'] = True

    print_summary(final)
    save_csv(final, output_path)

if __name__ == '__main__':
    main()
