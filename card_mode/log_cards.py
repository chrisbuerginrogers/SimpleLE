'''
Tap-through logger for LEGO Education cards.

Bytes 2 and 7 of the FD02 service data are card-derived and deterministic
— the same card produces the same pair on any device — but they are not a
sequential ID and not a CRC-8 of the visible fields. Cracking them needs
a decent sample of known cards, and scanning them one at a time is slow.

So: leave this running, tap cards against a sensor/hub one after another,
and it records each distinct card exactly once. Every new card prints a
row immediately, so you can see it registered before reaching for the
next one. Ctrl+C writes the CSV.

    python log_cards.py
    python log_cards.py --out cards.csv

Cards are keyed by (color, serial), so re-tapping one you've already done
is harmless — it just won't add a duplicate row. Note the key really does
need both halves: a PURPLE#1126 and a YELLOW#1126 both exist, and they
carry completely different b2/b7. The serial alone is not unique.

If a card's bytes ever disagree with what was recorded earlier for that
same (color, serial), it's flagged loudly, because that would break the
"deterministic per card" finding the whole analysis rests on.
'''

import argparse
import asyncio
import csv
import sys

from bleak import BleakScanner
from legoeducation.color_map import _firmware_to_app, LEGO_COLOR_NAME_MAP

from adv_capture import extract_payloads
from scan_advertising import is_lego

MIN_PAYLOAD = 8


def color_name(firmware_code):
    app = _firmware_to_app(firmware_code)
    return LEGO_COLOR_NAME_MAP.get(app, str(app)).replace('LEGO_COLOR_', '')


def make_callback(cards, conflicts):
    def on_advertisement(device, adv):
        if not is_lego(adv):
            return
        payload, _, _, _ = extract_payloads(adv)
        if payload is None or len(payload) < MIN_PAYLOAD:
            return

        serial = payload[3] | (payload[4] << 8)
        record = {
            'serial': serial,
            'color_fw': payload[1],
            'color': color_name(payload[1]),
            'b1': payload[1],
            'b2': payload[2],
            'b3': payload[3],
            'b4': payload[4],
            'b7': payload[7],
            'device_type': payload[0],
        }

        # Serial alone does NOT identify a card — a PURPLE#1126 and a
        # YELLOW#1126 both exist, with entirely different b2/b7. The key is
        # the (color, serial) pair.
        key = (payload[1], serial)
        known = cards.get(key)
        if known is None:
            cards[key] = record
            print(f"  [{len(cards):2d}] {record['color']:<8} #{serial:<6} "
                  f"b1=0x{record['b1']:02x}  b2=0x{record['b2']:02x}  "
                  f"b3,b4={record['b3']:02x} {record['b4']:02x}  "
                  f"b7=0x{record['b7']:02x}")
            return

        # Same color AND serial but different derived bytes — that would
        # break the determinism the whole analysis rests on, so shout.
        differing = [k for k in ('b2', 'b7') if known[k] != record[k]]
        if differing and key not in conflicts:
            conflicts.add(key)
            print(f"  !! {record['color']}#{serial} disagrees with the earlier "
                  f"reading on {','.join(differing)}: "
                  + '  '.join(f"{k} 0x{known[k]:02x} -> 0x{record[k]:02x}" for k in differing))
            print(f"     Card bytes are supposed to be deterministic. Worth "
                  f"chasing before trusting the analysis.")

    return on_advertisement


async def run(cards, conflicts):
    '''cards/conflicts are owned by the caller and mutated in place, so a
    Ctrl+C partway through still leaves everything collected so far.'''
    print("Tap cards one at a time. Each new card prints a row. Ctrl+C when done.\n")
    async with BleakScanner(detection_callback=make_callback(cards, conflicts)):
        while True:
            await asyncio.sleep(0.5)


def write_csv(cards, path):
    fields = ['serial', 'color', 'color_fw', 'b1', 'b2', 'b3', 'b4', 'b7', 'device_type']
    with open(path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for key in sorted(cards, key=lambda k: (k[1], k[0])):
            writer.writerow({f: cards[key][f] for f in fields})


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', default='cards.csv', help='CSV output path')
    args = parser.parse_args()

    cards, conflicts = {}, set()
    try:
        asyncio.run(run(cards, conflicts))
    except KeyboardInterrupt:
        pass

    if not cards:
        print("\nNo cards seen.")
        return 1
    write_csv(cards, args.out)
    print(f"\nWrote {len(cards)} card(s) to {args.out}")
    if conflicts:
        print(f"  {len(conflicts)} card(s) gave inconsistent bytes: {sorted(conflicts)}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
