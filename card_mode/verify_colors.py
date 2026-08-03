'''
Walk every LEGO colour past the color sensor and verify what byte 5 of the
FD02 service data actually reports for each one.

Byte 5 is the sensor's live detected colour, readable straight from the
advertisement with no GATT connection (see Card_mode.md). Only five values
have actually been observed against a known target — NONE, PURPLE, GREEN,
RED and WHITE. Every other code in the table is assumed from
`legoeducation/rpc_message.py` rather than measured. This script measures
them.

There are two numbering schemes in play and this script deliberately keeps
them apart:

  - the byte on the wire is a **firmware** colour code
    (NONE=-1, BLACK=0, MAGENTA=1, PURPLE=2, BLUE=3, AZURE=4, TURQUOISE=5,
     GREEN=6, YELLOW=7, ORANGE=8, RED=9, WHITE=10)
  - what `lelib.colorSensor.detect_color()` hands back is the **App**
    code (0 No color, 1 Red, 2 Yellow, 3 Blue, 4 Teal, 5 Green, 6 Purple,
    7 White, 8 Magenta, 9 Orange, 10 Azure)

They collide confusingly — App 2 is Yellow, firmware 2 is Purple. So the
raw byte is recorded alongside the translated App code, which means this
verifies `_firmware_to_app()` itself rather than trusting it.

Usage:
    python verify_colors.py
    python verify_colors.py --settle 4        # sample longer per colour
    python verify_colors.py --out mycolors.csv

For each colour it prompts, waits for Enter, then samples for a couple of
seconds and takes the most common byte 5 — a single advertisement can land
mid-transition, so the modal value over a window is steadier than one
reading. Press 's' then Enter to skip a colour you don't have a brick for;
a skipped row is honest, a guessed one isn't.

Hold the brick flat against the sensor face and keep the distance the same
across colours.
'''

import argparse
import asyncio
import csv
import sys
from collections import Counter

from bleak import BleakScanner
from legoeducation.color_map import (_APP_TO_FIRMWARE, _firmware_to_app,
                                     LEGO_COLOR_NAME_MAP)

from adv_capture import extract_payloads
from scan_advertising import DEVICE_TYPE_COLOR_SENSOR, _signed_byte, is_lego

DEFAULT_SETTLE = 2.5
MIN_PAYLOAD = 6
COLOR_BYTE = 5

# Extra guidance where the App name alone is ambiguous or the target is
# awkward to present.
HINTS = {
    0: 'nothing in front of the sensor — take everything away',
    4: 'teal / turquoise',
    10: 'azure — the pale sky blue, not the darker blue',
}


def app_name(app_code):
    return LEGO_COLOR_NAME_MAP.get(app_code, str(app_code)).replace('LEGO_COLOR_', '')


def expected_wire_byte(app_code):
    '''What byte 5 should read if the firmware table is right. Firmware
    NONE is -1, which goes on the wire as 0xff.'''
    firmware = _APP_TO_FIRMWARE.get(app_code)
    if firmware is None:
        return None
    return firmware & 0xff


async def _ainput(prompt):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: input(prompt))


class Sampler:
    '''Locks onto the first color sensor it sees and, while armed,
    collects byte 5 from every advertisement that device sends.'''

    def __init__(self, serial=None, color=None):
        self.serial = serial
        self.color = color.upper() if color else None
        self.address = None
        self.card = None
        self.armed = False
        self.samples = []

    def _matches(self, payload):
        if payload[0] != DEVICE_TYPE_COLOR_SENSOR:
            return False
        if self.serial is not None and (payload[3] | (payload[4] << 8)) != self.serial:
            return False
        if self.color is not None and app_name(_firmware_to_app(payload[1])) != self.color:
            return False
        return True

    def on_advertisement(self, device, adv):
        if not is_lego(adv):
            return
        payload, _, _, _ = extract_payloads(adv)
        if payload is None or len(payload) < MIN_PAYLOAD:
            return

        if self.address is None:
            if not self._matches(payload):
                return
            self.address = device.address
            serial = payload[3] | (payload[4] << 8)
            self.card = f"{app_name(_firmware_to_app(payload[1]))}#{serial}"
        elif device.address != self.address:
            return

        if self.armed:
            self.samples.append(payload[COLOR_BYTE])

    async def measure(self, settle):
        self.samples = []
        self.armed = True
        await asyncio.sleep(settle)
        self.armed = False
        return list(self.samples)


def verdict_for(app_code, samples):
    '''Returns (raw_byte, seen_app, verdict, note).'''
    if not samples:
        return None, None, 'NO DATA', 'no advertisements arrived'

    counts = Counter(samples)
    raw, hits = counts.most_common(1)[0]
    seen_app = _firmware_to_app(_signed_byte(raw))
    stability = f"{hits}/{len(samples)} packets"
    if len(counts) > 1:
        others = ' '.join(f"0x{v:02x}x{n}" for v, n in counts.most_common()[1:])
        stability += f", also saw {others}"

    expected_raw = expected_wire_byte(app_code)
    if seen_app == app_code:
        note = stability
        if expected_raw is not None and raw != expected_raw:
            note = (f"maps correctly but via 0x{raw:02x}, not the expected "
                    f"0x{expected_raw:02x} — {stability}")
        return raw, seen_app, 'ok', note
    return raw, seen_app, 'MISMATCH', f"read {app_name(seen_app)} — {stability}"


async def run(sampler, colors, settle):
    results = []
    print("Waiting for a color sensor...")
    waited = 0.0
    while sampler.address is None:
        await asyncio.sleep(0.3)
        waited += 0.3
        if abs(waited - 8.0) < 0.15:
            print("  ...still nothing. This needs a colour sensor specifically "
                  "(device type 0x02);\n  a controller won't do. Is it powered "
                  "on and in range?")
    print(f"Locked on {sampler.card} at {sampler.address}\n")
    print("Hold each brick flat against the sensor, same distance every time.")
    print("Enter to measure, 's' + Enter to skip.\n")

    for app_code in colors:
        name = app_name(app_code)
        hint = HINTS.get(app_code)
        label = f"{name}" + (f"  ({hint})" if hint else '')
        expected_raw = expected_wire_byte(app_code)
        expected_text = f"expect byte 0x{expected_raw:02x}" if expected_raw is not None else ''

        answer = await _ainput(f"  [{app_code:2d}] {label:<48} {expected_text}\n"
                               f"       Enter to measure > ")
        if answer.strip().lower().startswith('s'):
            results.append({'app_code': app_code, 'name': name, 'raw': '',
                            'seen_app': '', 'verdict': 'skipped', 'note': ''})
            print("\n       skipped\n")
            continue

        # input() leaves the cursor on the prompt line, so break the line
        # before reporting — and say something during the sampling wait.
        print(f"\n       measuring {settle:.1f}s, hold it steady...")
        samples = await sampler.measure(settle)
        raw, seen_app, verdict, note = verdict_for(app_code, samples)
        raw_text = f"0x{raw:02x}" if raw is not None else '--'
        mark = {'ok': 'OK ', 'MISMATCH': '!! ', 'NO DATA': '?? '}[verdict]
        print(f"       {mark} byte 5 = {raw_text}   {note}\n")
        results.append({'app_code': app_code, 'name': name, 'raw': raw_text,
                        'seen_app': '' if seen_app is None else seen_app,
                        'verdict': verdict, 'note': note})
    return results


def report(results):
    print('=' * 72)
    print('  App  Name       Expected  Got   Maps to        Verdict')
    print('  ' + '-' * 68)
    for r in results:
        expected_raw = expected_wire_byte(r['app_code'])
        exp = f"0x{expected_raw:02x}" if expected_raw is not None else '--'
        maps = app_name(r['seen_app']) if r['seen_app'] != '' else ''
        print(f"  {r['app_code']:>3}  {r['name']:<10} {exp:>8}  {r['raw']:>4}   "
              f"{maps:<14} {r['verdict']}")

    measured = [r for r in results if r['verdict'] in ('ok', 'MISMATCH')]
    good = [r for r in measured if r['verdict'] == 'ok']
    bad = [r for r in measured if r['verdict'] == 'MISMATCH']
    skipped = [r for r in results if r['verdict'] == 'skipped']
    print()
    print(f"  {len(good)}/{len(measured)} measured colours decoded correctly"
          + (f", {len(skipped)} skipped" if skipped else ''))
    if bad:
        print("\n  Mismatches — these break the firmware->App table:")
        for r in bad:
            print(f"    {r['name']}: {r['note']}")
    print('=' * 72)


def write_csv(results, path):
    fields = ['app_code', 'name', 'raw', 'seen_app', 'verdict', 'note']
    with open(path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)


async def _main(args):
    colors = sorted(LEGO_COLOR_NAME_MAP)
    if args.only:
        wanted = {int(c) for c in args.only.split(',')}
        colors = [c for c in colors if c in wanted]

    sampler = Sampler(args.serial, args.color)
    results = []
    async with BleakScanner(detection_callback=sampler.on_advertisement):
        try:
            results = await run(sampler, colors, args.settle)
        except (KeyboardInterrupt, EOFError):
            print("\nInterrupted.")
    if not results:
        return 1
    report(results)
    write_csv(results, args.out)
    print(f"\nWrote {args.out}")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--settle', type=float, default=DEFAULT_SETTLE,
                        help=f'Seconds to sample per colour (default {DEFAULT_SETTLE})')
    parser.add_argument('--serial', type=int, default=None,
                        help='Only use the sensor carrying this card serial')
    parser.add_argument('--color', default=None,
                        help='Only use the sensor carrying a card of this colour')
    parser.add_argument('--only', default=None,
                        help='Test only these App colour codes, e.g. 4,8,10')
    parser.add_argument('--out', default='color_verify.csv', help='CSV output path')
    args = parser.parse_args()
    try:
        return asyncio.run(_main(args))
    except KeyboardInterrupt:
        print("\nStopped.")
        return 1


if __name__ == '__main__':
    sys.exit(main())
