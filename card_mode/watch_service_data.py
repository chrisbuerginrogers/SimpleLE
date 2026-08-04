'''
Watch one LEGO device's FD02 service data and report every byte that
changes, as it changes.

Where `scan_advertising.py` shows you the current state of everything in
range, this locks onto a single card and prints an event log: one line per
byte that moved, with what it moved from, what it moved to, and what that
means. Nothing prints while nothing changes, so you can leave it running
and wave things at the sensor.

Every event shows the full service-data payload, with carets under the
bytes that moved, so a change is always anchored to the whole packet:

    11:52:06.153  02 09 de 6d 04 09 00 75 7e | 3c 22 9e
                                    ^^
                  b5  0xff -> 0x09   DETECTS NOCOLOR -> RED

The `|` marks where the churn bytes start. Bytes 9-11 change on every
single advertisement (counters and what looks like a CRC), so they're
excluded from change detection by default — otherwise every packet would
be an "event" and the real changes would be buried. They're still printed,
just not treated as news. --all-bytes makes them count as changes too.

--raw adds the previous payload above the new one for direct comparison,
and --every prints the payload for every advertisement rather than only
when something moves.

Defaults target the RED#1133 color sensor. Note that a card serial is NOT
unique on its own — RED#1126, YELLOW#1126 and PURPLE#1126 all exist — so
the match is on colour AND serial.

    python watch_service_data.py
    python watch_service_data.py --serial 1126 --color PURPLE
    python watch_service_data.py --serial 1133 --color RED --all-bytes
    python watch_service_data.py --serial 1133 --color RED --raw

Ctrl+C to stop; prints a per-byte change tally on the way out.
'''

import argparse
import asyncio
import sys
import time
from collections import Counter
from datetime import datetime

from bleak import BleakScanner
from legoeducation.color_map import _firmware_to_app, LEGO_COLOR_NAME_MAP

from adv_capture import extract_payloads
from scan_advertising import (DEVICE_TYPE_COLOR_SENSOR, DEVICE_TYPE_CONTROLLER,
                              _signed_byte, is_lego)

# Counter / CRC bytes: these move on every advertisement regardless of
# what the hardware is doing, so treating them as events is just noise.
CHURN_BYTES = {9, 10, 11}

DEVICE_TYPE_NAMES = {DEVICE_TYPE_COLOR_SENSOR: 'color sensor',
                     DEVICE_TYPE_CONTROLLER: 'controller'}


def color_name(firmware_code):
    app = _firmware_to_app(firmware_code)
    return LEGO_COLOR_NAME_MAP.get(app, str(app)).replace('LEGO_COLOR_', '')


def describe(index, value, device_type):
    '''Reading of one byte as (label, value_text). Split in two so a change
    can print as "DETECTS NOCOLOR -> RED" rather than repeating the label on
    both sides. value_text is '' for bytes whose meaning doesn't vary.
    See Card_mode.md for where each of these came from.'''
    if index == 0:
        return 'device type', DEVICE_TYPE_NAMES.get(value, f'unknown 0x{value:02x}')
    if index == 1:
        return 'card colour', color_name(value)
    if index in (2, 7):
        return 'card token', ''
    if index in (3, 4):
        return 'card serial', ''
    if index == 5:
        if device_type == DEVICE_TYPE_COLOR_SENSOR:
            return 'DETECTS', color_name(_signed_byte(value))
        if device_type == DEVICE_TYPE_CONTROLLER:
            return 'right stick', f'{_signed_byte(value):+d}'
    if index == 6 and device_type == DEVICE_TYPE_CONTROLLER:
        return 'left stick', f'{_signed_byte(value):+d}'
    if index == 8:
        return 'battery?', ''
    if index in CHURN_BYTES:
        return 'counter/CRC', ''
    return '', ''


def describe_static(index, value, device_type):
    label, text = describe(index, value, device_type)
    return f"{label} {text}".strip()


def describe_change(index, old, new, device_type):
    old_label, old_text = describe(index, old, device_type)
    new_label, new_text = describe(index, new, device_type)
    if old_label == new_label:
        if old_text and new_text and old_text != new_text:
            return f"{old_label} {old_text} -> {new_text}"
        return old_label
    return f"{describe_static(index, old, device_type)} -> " \
           f"{describe_static(index, new, device_type)}"


def format_payload(payload):
    '''Spaced hex with a divider before the churn bytes, so the stable
    part of the packet reads as a unit and the counters stay visually
    separate.'''
    parts = []
    for i, value in enumerate(payload):
        if i == min(CHURN_BYTES):
            parts.append('|')
        parts.append(f'{value:02x}')
    return ' '.join(parts)


def format_marker(length, changed):
    '''Caret line that lines up under format_payload().'''
    parts = []
    for i in range(length):
        if i == min(CHURN_BYTES):
            parts.append(' ')
        parts.append('^^' if i in changed else '  ')
    return ' '.join(parts).rstrip()


def format_ruler(length):
    parts = []
    for i in range(length):
        if i == min(CHURN_BYTES):
            parts.append(' ')
        parts.append(f'{i:2d}')
    return ' '.join(parts)


class Watcher:
    def __init__(self, serial, color, watched_bytes, show_raw, show_every=False):
        self.serial = serial
        self.color = color.upper() if color else None
        self.watched = watched_bytes
        self.show_raw = show_raw
        self.show_every = show_every
        self.previous = None
        self.address = None
        self.packets = 0
        self.changes = Counter()
        self.last_change = None
        self.started = time.monotonic()

    def matches(self, payload):
        if (payload[3] | (payload[4] << 8)) != self.serial:
            return False
        return self.color is None or color_name(payload[1]) == self.color

    def on_advertisement(self, device, adv):
        if not is_lego(adv):
            return
        payload, _, _, _ = extract_payloads(adv)
        if payload is None or len(payload) < 9 or not self.matches(payload):
            return

        self.packets += 1
        device_type = payload[0]
        now = datetime.now().strftime('%H:%M:%S.%f')[:-3]

        if self.previous is None:
            self.address = device.address
            kind = DEVICE_TYPE_NAMES.get(device_type, f'0x{device_type:02x}')
            print(f"Locked on {color_name(payload[1])}#{self.serial} ({kind}) "
                  f"at {device.address}")
            print(f"  byte   {format_ruler(len(payload))}")
            print(f"  hex    {format_payload(payload)}")
            for i in sorted(self.watched):
                if i < len(payload):
                    meaning = describe_static(i, payload[i], device_type)
                    print(f"    b{i:<2} 0x{payload[i]:02x}   {meaning}")
            print(f"\nWatching bytes {sorted(self.watched)} — "
                  f"nothing prints until something moves.\n")
            self.previous = payload
            return

        changed = [i for i in sorted(self.watched)
                   if i < len(payload) and i < len(self.previous)
                   and self.previous[i] != payload[i]]
        length_changed = len(payload) != len(self.previous)

        if changed or length_changed or self.show_every:
            if length_changed:
                print(f"{now}  LENGTH {len(self.previous)} -> {len(payload)}   "
                      f"the device added or dropped a field")
            # Full packet first, so every event is anchored to the whole
            # payload rather than just the byte that moved.
            if self.show_raw or length_changed:
                print(f"{now}  was  {format_payload(self.previous)}")
                print(f"{' ' * len(now)}  now  {format_payload(payload)}")
            else:
                print(f"{now}  {format_payload(payload)}")
            if changed:
                marker = format_marker(len(payload), set(changed))
                indent = ' ' * (len(now) + (7 if (self.show_raw or length_changed) else 2))
                print(f"{indent}{marker}")
            for i in changed:
                self.changes[i] += 1
                old, new = self.previous[i], payload[i]
                meaning = describe_change(i, old, new, device_type)
                print(f"{' ' * len(now)}  b{i:<2} 0x{old:02x} -> 0x{new:02x}   {meaning}")

        self.previous = payload

    def summary(self):
        elapsed = time.monotonic() - self.started
        print(f"\n{self.packets} packets over {elapsed:.0f}s")
        if not self.changes:
            print("No byte ever changed.")
            return
        print("Changes per byte:")
        for i, n in sorted(self.changes.items()):
            print(f"  b{i:<2} {n:4d}")


async def run(watcher):
    async with BleakScanner(detection_callback=watcher.on_advertisement):
        while True:
            await asyncio.sleep(0.5)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--serial', type=int, default=1133, help='Card serial (default 1133)')
    parser.add_argument('--color', default='RED',
                        help="Card colour, since serials aren't unique (default RED). "
                             "Pass ANY to match on serial alone.")
    parser.add_argument('--all-bytes', action='store_true',
                        help='Also report the counter/CRC bytes 9-11')
    parser.add_argument('--bytes', default=None,
                        help='Watch only these byte indexes, e.g. 5,6')
    parser.add_argument('--raw', action='store_true',
                        help='Show the previous payload alongside the new one on each change')
    parser.add_argument('--every', action='store_true',
                        help='Print the full payload for every advertisement, not just changes')
    args = parser.parse_args()

    if args.bytes:
        watched = {int(b) for b in args.bytes.split(',')}
    else:
        watched = set(range(12)) if args.all_bytes else set(range(12)) - CHURN_BYTES

    color = None if args.color.upper() == 'ANY' else args.color
    watcher = Watcher(args.serial, color, watched, args.raw, args.every)
    print(f"Looking for {args.color.upper()}#{args.serial}... "
          f"(is it powered on and in range?)")
    try:
        asyncio.run(run(watcher))
    except KeyboardInterrupt:
        pass
    watcher.summary()
    return 0


if __name__ == '__main__':
    sys.exit(main())
