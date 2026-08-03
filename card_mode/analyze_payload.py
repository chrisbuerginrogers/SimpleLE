'''
Per-byte differencing for advertisement captures produced by
`capture_controller.py` / `capture_colorsensor.py`.

The method is simple and it's the whole point of capturing with labels:
compare each byte's distribution under a stimulus against its distribution
during `baseline`. Bytes that move only when you did something are the
payload; bytes that move constantly while you sat still are counters or a
CRC; bytes that never move are identity.

Reports produced:
  1. Byte classification — static / volatile / responsive
  2. Modal value per segment for the responsive bytes
  3. Scale test — max magnitude under full deflection, which decides
     signed-byte vs. packed-nibble encoding
  4. Nibble view — for testing the packed-4-bit hypothesis directly
  5. Deadzone — smallest non-zero magnitude, and which small values never
     appear
  6. Payload length changes per segment

Usage:
    python analyze_payload.py capture_controller.csv
    python analyze_payload.py capture_controller.csv --bytes 5,6,7,8

Compare mode — the Protocol C1 test. Pass several captures taken under
different receiver conditions and it reports, per segment and per byte,
whether the broadcast bytes are identical across them:

    python analyze_payload.py ctrl_no_motor.csv ctrl_single.csv ctrl_double.csv

Identical values mean the controller broadcasts its own state regardless
of what's listening, so the motor does the interpreting. Values that shift
with the receiver mean the controller is tailoring its output.
'''

import argparse
import csv
import sys
from collections import Counter, OrderedDict

MAX_PAYLOAD_COLUMNS = 24
# A byte that takes more than this many values while nothing is being
# touched is a counter or a checksum, not state.
BASELINE_NOISE_TOLERANCE = 2
DEFAULT_BASELINE_PREFIXES = ('baseline', 'idle', 'center')


def signed(b):
    return b - 256 if b >= 128 else b


def signed_nibble(n):
    return n - 16 if n >= 8 else n


# ── loading ──────────────────────────────────────────────────────────

def load(path):
    with open(path, newline='') as f:
        rows = list(csv.DictReader(f))
    if not rows:
        sys.exit(f"{path}: no rows")
    return rows


def get_byte(row, i):
    v = row.get(f'b{i}', '')
    if v == '' or v is None:
        return None
    return int(v)


def present_bytes(rows):
    '''Byte indexes that have a value in at least one packet.'''
    return [i for i in range(MAX_PAYLOAD_COLUMNS)
            if any(get_byte(r, i) is not None for r in rows)]


def group_by_label(rows):
    groups = OrderedDict()
    for row in rows:
        groups.setdefault(row['label'], []).append(row)
    return groups


def values(rows, i):
    return [v for v in (get_byte(r, i) for r in rows) if v is not None]


def modal(rows, i):
    vals = values(rows, i)
    if not vals:
        return None, 0, True
    counts = Counter(vals)
    top, _ = counts.most_common(1)[0]
    return top, len(counts), len(counts) == 1


# ── classification ───────────────────────────────────────────────────

def classify(rows, groups, indexes, baseline_prefixes):
    baseline_rows = [r for label, rs in groups.items()
                     if label.startswith(baseline_prefixes) for r in rs]

    static, volatile, responsive = [], [], []
    for i in indexes:
        distinct_all = len(set(values(rows, i)))
        distinct_base = len(set(values(baseline_rows, i))) if baseline_rows else 0
        if distinct_all <= 1:
            static.append(i)
        elif distinct_base > BASELINE_NOISE_TOLERANCE:
            volatile.append(i)
        else:
            responsive.append(i)
    return static, volatile, responsive, baseline_rows


# ── printing ─────────────────────────────────────────────────────────

def header(title):
    print(f"\n{title}\n{'-' * len(title)}")


def print_table(col_labels, row_labels, cells):
    widths = [max(len(str(row_labels[r])) for r in range(len(row_labels)))]
    widths[0] = max(widths[0], len('segment'))
    for c, name in enumerate(col_labels):
        w = max(len(name), *(len(cells[r][c]) for r in range(len(cells)))) if cells else len(name)
        widths.append(w)

    print('  ' + 'segment'.ljust(widths[0]) + '  '
          + '  '.join(name.rjust(widths[c + 1]) for c, name in enumerate(col_labels)))
    for r, label in enumerate(row_labels):
        print('  ' + str(label).ljust(widths[0]) + '  '
              + '  '.join(cells[r][c].rjust(widths[c + 1]) for c in range(len(col_labels))))


def report_classification(rows, static, volatile, responsive):
    header('1. BYTE CLASSIFICATION')
    if static:
        parts = []
        for i in static:
            v = values(rows, i)[0]
            parts.append(f"b{i}=0x{v:02x}")
        print(f"  static (identical in every packet) — identity/type fields:")
        print(f"    {' '.join(parts)}")
    if volatile:
        print(f"  volatile during baseline — counters / CRC, excluded from analysis:")
        print(f"    {' '.join(f'b{i}' for i in volatile)}")
    if responsive:
        print(f"  RESPONSIVE — stable at rest, but change somewhere:")
        print(f"    {' '.join(f'b{i}' for i in responsive)}")
    else:
        print("  RESPONSIVE: none.")
        print("  No byte was stable at rest yet varied elsewhere. Either the")
        print("  stimulus isn't reaching the advertisement, or the payload is")
        print("  obfuscated against the rolling counter — try XOR-ing the")
        print("  candidate bytes with the counter byte before giving up.")


def report_modal(groups, responsive):
    if not responsive:
        return
    header('2. MODAL VALUE PER SEGMENT  (hex/signed, * = varied within segment)')
    col_labels = [f"b{i}" for i in responsive] + ['n']
    row_labels, cells = [], []
    for label, rs in groups.items():
        row_labels.append(label)
        cell_row = []
        for i in responsive:
            top, distinct, stable = modal(rs, i)
            if top is None:
                cell_row.append('-')
            else:
                cell_row.append(f"{top:02x}/{signed(top):+d}" + ('' if stable else '*'))
        cell_row.append(str(len(rs)))
        cells.append(cell_row)
    print_table(col_labels, row_labels, cells)


def report_scale(groups, responsive, keyword='full'):
    header(f"3. SCALE TEST  (segments containing '{keyword}')")
    full_rows = [r for label, rs in groups.items() if keyword in label for r in rs]
    if not full_rows:
        print(f"  No segment label contains '{keyword}' — capture the")
        print(f"  full-deflection segments, they're what decides the encoding.")
        return
    for i in responsive:
        vals = [abs(signed(v)) for v in values(full_rows, i)]
        if not vals:
            continue
        peak = max(vals)
        if peak <= 7:
            verdict = "<= 7: PACKED 4-BIT NIBBLES — this byte carries TWO fields"
        elif 90 <= peak <= 105:
            verdict = "~100: NORMALIZED PERCENTAGE — a speed command, not a raw position"
        elif peak >= 110:
            verdict = ">= 110: full signed-byte range — position-like, not a percentage"
        else:
            verdict = "inconclusive — push harder, or the max is device-specific (raw-ish)"
        print(f"  b{i}  peak |signed| = {peak:3d}   {verdict}")


def report_nibbles(rows, groups, responsive):
    if not responsive:
        return
    header('4. NIBBLE VIEW  (high/low as signed 4-bit)')
    both_nonzero = {}
    for i in responsive:
        vals = values(rows, i)
        both = sum(1 for v in vals if (v >> 4) and (v & 0xf))
        both_nonzero[i] = (both, len(vals))

    col_labels = [f"b{i}" for i in responsive]
    row_labels, cells = [], []
    for label, rs in groups.items():
        row_labels.append(label)
        cell_row = []
        for i in responsive:
            top, _, _ = modal(rs, i)
            if top is None:
                cell_row.append('-')
            else:
                cell_row.append(f"{signed_nibble(top >> 4):+d}|{signed_nibble(top & 0xf):+d}")
        cells.append(cell_row)
    print_table(col_labels, row_labels, cells)
    print()
    for i in responsive:
        both, total = both_nonzero[i]
        if both:
            print(f"  b{i}: {both}/{total} packets have BOTH nibbles non-zero "
                  f"-> consistent with two packed fields")
        else:
            print(f"  b{i}: no packet ever has both nibbles non-zero "
                  f"-> either a plain signed byte, or the two fields were "
                  f"never exercised together (check the both_* segments ran)")


def report_deadzone(rows, responsive):
    if not responsive:
        return
    header('5. DEADZONE / RESOLUTION')
    for i in responsive:
        mags = sorted({abs(signed(v)) for v in values(rows, i)})
        nonzero = [m for m in mags if m]
        if not nonzero:
            print(f"  b{i}: always zero")
            continue
        missing = [m for m in range(1, min(nonzero)) if m not in mags]
        note = ''
        if missing:
            note = (f"   <-- skips {','.join(map(str, missing))}: "
                    f"deadzone applied on the device")
        print(f"  b{i}: smallest non-zero |value| = {min(nonzero)}{note}")
        print(f"       magnitudes seen: {mags}")


def report_lengths(groups):
    header('6. PAYLOAD LENGTH')
    lengths = {}
    for label, rs in groups.items():
        lengths[label] = sorted({int(r['length']) for r in rs})
    all_lengths = sorted({n for v in lengths.values() for n in v})
    if len(all_lengths) == 1:
        print(f"  constant at {all_lengths[0]} bytes in every segment")
        return
    print("  LENGTH VARIES — the device appends fields when an input goes active:")
    for label, v in lengths.items():
        if len(v) > 1 or v != [all_lengths[0]]:
            print(f"    {label:<24} {v}")


# ── compare mode (Protocol C1) ───────────────────────────────────────

def report_compare(paths):
    loaded = [(p, group_by_label(load(p))) for p in paths]
    all_rows = [r for _, g in loaded for rs in g.values() for r in rs]
    indexes = present_bytes(all_rows)
    groups_merged = group_by_label(all_rows)
    _, _, responsive, _ = classify(all_rows, groups_merged, indexes,
                                   DEFAULT_BASELINE_PREFIXES)

    header('COMPARE MODE — does the broadcast depend on the receiver?')
    print(f"  files: {', '.join(paths)}")
    print(f"  comparing responsive bytes: {' '.join(f'b{i}' for i in responsive)}")

    shared = [label for label in loaded[0][1]
              if all(label in g for _, g in loaded)]
    if not shared:
        print("\n  No segment labels in common — were these captured with the "
              "same script?")
        return

    differing = []
    col_labels = [f"b{i}" for i in responsive]
    row_labels, cells = [], []
    for label in shared:
        for path, groups in loaded:
            row_labels.append(f"{label} [{path}]")
            cell_row = []
            for i in responsive:
                top, _, _ = modal(groups[label], i)
                cell_row.append('-' if top is None else f"{top:02x}/{signed(top):+d}")
            cells.append(cell_row)
        per_file = [[modal(g[label], i)[0] for i in responsive] for _, g in loaded]
        if any(vals != per_file[0] for vals in per_file[1:]):
            differing.append(label)
    print()
    print_table(col_labels, row_labels, cells)

    print()
    if differing:
        print("  VERDICT: bytes DIFFER by receiver in these segments:")
        for label in differing:
            print(f"    {label}")
        print("  The controller is tailoring its output to what's listening —")
        print("  it is computing something receiver-specific, not just")
        print("  reporting its own stick state.")
    else:
        print("  VERDICT: identical across all receiver conditions.")
        print("  The controller broadcasts its own state regardless of what's")
        print("  listening, so the interpretation happens on the motor side.")


# ── main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('csv', nargs='+', help='Capture CSV(s). Two or more enables compare mode.')
    parser.add_argument('--bytes', default=None,
                        help='Force which byte indexes to treat as responsive, e.g. 5,6')
    parser.add_argument('--baseline', default=','.join(DEFAULT_BASELINE_PREFIXES),
                        help='Comma-separated label prefixes treated as "nothing touched"')
    parser.add_argument('--scale-keyword', default='full',
                        help="Segment-label substring marking full deflection (default 'full')")
    parser.add_argument('--split-byte', type=int, default=None,
                        help='Run the whole report separately per distinct value of '
                             'this byte. Use when a byte looks like a message type '
                             '(b0 is the known candidate).')
    args = parser.parse_args()

    if len(args.csv) > 1:
        report_compare(args.csv)
        return 0

    path = args.csv[0]
    rows = load(path)
    print(f"{path}: {len(rows)} packets, "
          f"{len(group_by_label(rows))} segments, "
          f"{len(present_bytes(rows))} byte positions")

    if args.split_byte is not None:
        i = args.split_byte
        kinds = sorted({v for v in values(rows, i)})
        print(f"\nSplitting on b{i}: {len(kinds)} distinct value(s) "
              f"{[f'0x{v:02x}' for v in kinds]}")
        for v in kinds:
            subset = [r for r in rows if get_byte(r, i) == v]
            print(f"\n{'#' * 68}\n#  b{i} == 0x{v:02x}   ({len(subset)} packets)\n{'#' * 68}")
            run_reports(subset, args)
        return 0

    run_reports(rows, args)
    warn_if_split_needed(rows)
    return 0


def warn_if_split_needed(rows):
    '''Byte 0 looks like a device/product type: 0x02 was observed on a color
    sensor and 0x03 on a controller. A capture is locked to one address, so
    b0 should be constant throughout. If it isn't, either it doubles as a
    message type — meaning later bytes change meaning under it, and averaging
    across values would smear the result — or the address got reused
    mid-capture. Either way, don't silently mix them.'''
    for i in (0,):
        kinds = sorted({v for v in values(rows, i)})
        if len(kinds) > 1:
            print(f"\n  !! b{i} took {len(kinds)} values "
                  f"{[f'0x{v:02x}' for v in kinds]} within a single-device capture. "
                  f"b0 is the device-type byte and should be constant here, so it "
                  f"may also encode a message type with later bytes shifting meaning.")
            print(f"     Re-run with --split-byte {i} to analyze each value separately.")


def run_reports(rows, args):
    groups = group_by_label(rows)
    indexes = present_bytes(rows)
    baseline_prefixes = tuple(p.strip() for p in args.baseline.split(',') if p.strip())

    static, volatile, responsive, baseline_rows = classify(
        rows, groups, indexes, baseline_prefixes)
    if args.bytes:
        responsive = [int(b) for b in args.bytes.split(',')]

    if not baseline_rows:
        print(f"  !! no segment matched baseline prefixes {baseline_prefixes} — "
              f"counter bytes can't be excluded, so expect noise below.")

    report_classification(rows, static, volatile, responsive)
    report_modal(groups, responsive)
    report_scale(groups, responsive, args.scale_keyword)
    report_nibbles(rows, groups, responsive)
    report_deadzone(rows, responsive)
    report_lengths(groups)


if __name__ == '__main__':
    sys.exit(main())
