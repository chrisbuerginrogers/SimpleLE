'''
Shared capture engine for reverse-engineering LEGO Education BLE
advertisement payloads.

This module doesn't run on its own. `capture_controller.py` and
`capture_colorsensor.py` import it and supply a list of Segments — a
scripted sequence of "do this physical thing, hold it, we record". The
engine handles device discovery, prompting, timed recording, and writing
one CSV row per advertisement received. `analyze_payload.py` reads that
CSV back.

Design rules, which matter more than the code:
  - Always log the FULL payload, never a pre-decoded field. The decode is
    the hypothesis under test — baking it into the capture begs the
    question.
  - Log payload length. A device may append fields when an input goes
    active, and a length change is itself a finding.
  - Label segments automatically. Hand-annotating a scrolling hex log is
    where this kind of work goes wrong.
  - Repeat every segment (3x by default) so reproducible changes can be
    told apart from noise.
  - Always capture a `baseline` segment with nothing touched. Bytes that
    move during baseline are counters/CRC and get excluded from analysis.

CSV schema:
    wall, t, label, rep, address, rssi, carrier, length, hex,
    svc_hex, mfg_hex, b0 ... b23
'''

import argparse
import asyncio
import csv
import sys
import time
from collections import namedtuple
from datetime import datetime

from bleak import BleakScanner
from legoeducation.basic_ble import LEGO_COMPANY_ID, SERVICE_UUID

# Single-source the decoder from scan_advertising so there's one place to
# fix when the layout hypothesis changes. Same directory, so a plain
# import works whenever these scripts are run as scripts.
from scan_advertising import decode_lego_card, is_lego

SERVICE_UUID_LOWER = SERVICE_UUID.lower()
MAX_PAYLOAD_COLUMNS = 24
DISCOVERY_SECONDS = 6.0
SPARSE_PACKET_WARNING = 5

# label       — short slug, becomes the CSV group key (keep it greppable)
# instruction — what the human physically does
# hold        — seconds to record, None = use the --hold default
Segment = namedtuple('Segment', 'label instruction hold')


def segment(label, instruction, hold=None):
    return Segment(label, instruction, hold)


def extract_payloads(adv):
    '''Return (chosen_payload, carrier, svc_hex, mfg_hex).

    FD02 service data wins when both are present, since that's the carrier
    the LEGO Education tech elements actually use, but the other one is
    still recorded so nothing is lost if that assumption turns out wrong.
    '''
    svc = None
    for uuid, payload in (adv.service_data or {}).items():
        if uuid.lower() == SERVICE_UUID_LOWER:
            svc = bytes(payload)
            break
    mfg = (adv.manufacturer_data or {}).get(LEGO_COMPANY_ID)
    mfg = bytes(mfg) if mfg is not None else None

    svc_hex = svc.hex() if svc is not None else ''
    mfg_hex = mfg.hex() if mfg is not None else ''
    if svc is not None:
        return svc, 'fd02', svc_hex, mfg_hex
    if mfg is not None:
        return mfg, 'mfg', svc_hex, mfg_hex
    return None, '', svc_hex, mfg_hex


async def _ainput(prompt):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: input(prompt))


# ── discovery ────────────────────────────────────────────────────────

async def discover(seconds, name_filter):
    found = {}

    def on_advertisement(device, adv):
        if not is_lego(adv):
            return
        if name_filter and (not device.name or name_filter.lower() not in device.name.lower()):
            return
        payload, carrier, _, _ = extract_payloads(adv)
        if payload is None:
            return
        found[device.address] = {
            'name': device.name or '',
            'rssi': adv.rssi,
            'card': decode_lego_card(adv.manufacturer_data, adv.service_data),
            'carrier': carrier,
            'hex': payload.hex(),
        }

    print(f"Scanning {seconds:.0f}s for LEGO devices...")
    async with BleakScanner(detection_callback=on_advertisement):
        await asyncio.sleep(seconds)
    return found


async def choose_device(found):
    if not found:
        print("No LEGO devices found. Is the device powered on and in range?")
        return None
    items = sorted(found.items())
    print()
    for i, (addr, d) in enumerate(items, 1):
        print(f"  [{i}] {d['card'] or '(no card)':<14} {addr}  rssi={d['rssi']:<5} "
              f"{d['carrier']}:{d['hex']}")
    print()
    if len(items) == 1:
        print(f"Only one device — using {items[0][0]}")
        return items[0][0]
    while True:
        answer = (await _ainput("Which device? [number] ")).strip()
        if answer.isdigit() and 1 <= int(answer) <= len(items):
            return items[int(answer) - 1][0]
        print("Enter one of the numbers above.")


# ── capture ──────────────────────────────────────────────────────────

class Capture:
    def __init__(self, address):
        self.address = address
        self.label = None
        self.rep = 0
        self.rows = []
        self.segment_count = 0
        self.t0 = time.monotonic()

    def on_advertisement(self, device, adv):
        if device.address != self.address or self.label is None:
            return
        payload, carrier, svc_hex, mfg_hex = extract_payloads(adv)
        if payload is None:
            return
        row = {
            'wall': datetime.now().isoformat(timespec='milliseconds'),
            't': f"{time.monotonic() - self.t0:.3f}",
            'label': self.label,
            'rep': self.rep,
            'address': device.address,
            'rssi': adv.rssi,
            'carrier': carrier,
            'length': len(payload),
            'hex': payload.hex(),
            'svc_hex': svc_hex,
            'mfg_hex': mfg_hex,
        }
        for i in range(MAX_PAYLOAD_COLUMNS):
            row[f'b{i}'] = payload[i] if i < len(payload) else ''
        self.rows.append(row)
        self.segment_count += 1

    def start(self, label, rep):
        self.label = label
        self.rep = rep
        self.segment_count = 0

    def stop(self):
        self.label = None
        return self.segment_count


async def countdown(seconds=3):
    for n in range(seconds, 0, -1):
        sys.stdout.write(f"\r   starting in {n}... ")
        sys.stdout.flush()
        await asyncio.sleep(1.0)
    sys.stdout.write("\r   RECORDING       \n")
    sys.stdout.flush()


async def record(cap, label, rep, hold):
    cap.start(label, rep)
    elapsed = 0.0
    while elapsed < hold:
        await asyncio.sleep(0.25)
        elapsed += 0.25
        sys.stdout.write(f"\r   {elapsed:4.1f}/{hold:.1f}s   {cap.segment_count} packets   ")
        sys.stdout.flush()
    n = cap.stop()
    sys.stdout.write(f"\r   done: {n} packets in {hold:.1f}s" + ' ' * 20 + "\n")
    sys.stdout.flush()
    if n < SPARSE_PACKET_WARNING:
        print(f"   !! only {n} packets — move closer, or raise --hold. "
              f"macOS coalesces advertisements, so expect roughly 2-10/sec.")
    return n


async def run_segments(cap, segments, reps, hold, gap, manual):
    total = len(segments) * reps
    done = 0
    for rep in range(1, reps + 1):
        print(f"\n{'=' * 68}\n  REPETITION {rep} of {reps}\n{'=' * 68}")
        for seg in segments:
            done += 1
            print(f"\n[{done}/{total}] {seg.label}")
            print(f"   {seg.instruction}")
            if manual:
                await _ainput("   press Enter when you're in position... ")
            else:
                await countdown(3)
            await record(cap, seg.label, rep, seg.hold or hold)
            if gap > 0:
                print(f"   release / return to neutral ({gap:.0f}s)")
                await asyncio.sleep(gap)


def write_csv(rows, path):
    fields = (['wall', 't', 'label', 'rep', 'address', 'rssi', 'carrier',
               'length', 'hex', 'svc_hex', 'mfg_hex']
              + [f'b{i}' for i in range(MAX_PAYLOAD_COLUMNS)])
    with open(path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


# ── entry point used by the protocol scripts ─────────────────────────

async def _run(args, segments):
    address = args.address
    if address is None:
        found = await discover(args.discover, args.name)
        address = await choose_device(found)
        if address is None:
            return 1

    cap = Capture(address)
    print(f"\nCapturing from {address}")
    print(f"{len(segments)} segments x {args.reps} reps, {args.hold:.0f}s each "
          f"-> {args.out}")

    async with BleakScanner(detection_callback=cap.on_advertisement):
        try:
            await run_segments(cap, segments, args.reps, args.hold, args.gap, args.manual)
        except KeyboardInterrupt:
            print("\nInterrupted — writing what we have.")

    if not cap.rows:
        print("\nNo packets captured. Nothing written.")
        return 1
    write_csv(cap.rows, args.out)
    labels = {}
    for row in cap.rows:
        labels[row['label']] = labels.get(row['label'], 0) + 1
    print(f"\nWrote {len(cap.rows)} rows to {args.out}")
    for label, n in labels.items():
        flag = '  <-- thin' if n < SPARSE_PACKET_WARNING * args.reps else ''
        print(f"   {label:<24} {n}{flag}")
    print(f"\nNext: python analyze_payload.py {args.out}")
    return 0


def main(protocol_name, segments, default_out):
    parser = argparse.ArgumentParser(
        description=f"Guided advertisement capture: {protocol_name}")
    parser.add_argument('--out', default=default_out, help='CSV output path')
    parser.add_argument('--address', default=None,
                        help='Skip discovery and capture from this address')
    parser.add_argument('--name', default=None,
                        help='Only offer devices whose name contains this substring')
    parser.add_argument('--reps', type=int, default=3,
                        help='Repetitions of the whole segment list (default 3)')
    parser.add_argument('--hold', type=float, default=5.0,
                        help='Seconds to record per segment (default 5)')
    parser.add_argument('--gap', type=float, default=2.0,
                        help='Seconds between segments (default 2)')
    parser.add_argument('--discover', type=float, default=DISCOVERY_SECONDS,
                        help=f'Discovery scan length (default {DISCOVERY_SECONDS:.0f}s)')
    parser.add_argument('--manual', action='store_true',
                        help='Wait for Enter before each segment instead of counting down')
    args = parser.parse_args()

    try:
        return asyncio.run(_run(args, segments))
    except KeyboardInterrupt:
        print("\nStopped.")
        return 1
