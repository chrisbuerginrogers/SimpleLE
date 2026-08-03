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

BLACK is tested too even though the App has no such colour: firmware 0 is
BLACK and translates to App "No color". So a black brick and an empty
sensor both end up as No color, and the only way to tell them apart is the
raw byte. Those two targets are therefore checked strictly against the
wire byte rather than the translated code.

Usage:
    python verify_colors.py                       # everything
    python verify_colors.py --only orange,black,teal
    python verify_colors.py --only 4,8,10         # App codes also work
    python verify_colors.py --settle 4            # sample longer per colour

For each target it prompts, waits for Enter, then samples for a couple of
seconds and takes the most common byte 5 — a single advertisement can land
mid-transition, so the modal value over a window is steadier than one
reading. Anything that doesn't come back clean offers an immediate
re-measure, so a fumbled brick doesn't cost you a rerun.

Press 's' then Enter to skip a colour you don't have a brick for; a
skipped row is honest, a guessed one isn't.

Hold the brick flat against the sensor face and keep the distance the same
across colours.
'''

import argparse
import asyncio
import csv
import sys
from collections import Counter, namedtuple

from bleak import BleakScanner
from legoeducation.color_map import (_APP_TO_FIRMWARE, _firmware_to_app,
                                     LEGO_COLOR_NAME_MAP, LEGO_COLOR_NOCOLOR)
from legoeducation.rpc_message import LEGO_COLOR_BLACK as _FW_BLACK

from adv_capture import extract_payloads
from scan_advertising import DEVICE_TYPE_COLOR_SENSOR, _signed_byte, is_lego

DEFAULT_SETTLE = 2.5
MIN_PAYLOAD = 6
COLOR_BYTE = 5

# key          — what --only matches on
# label        — shown in prompts and the report
# expected_raw — the byte we expect on the wire
# expected_app — the App code it should translate to
# strict       — compare the raw byte, not the translated code. Needed where
#                two targets share an App code (No color and Black both map
#                to App 0, so the translation can't tell them apart).
# hint         — extra guidance when the name alone is ambiguous
Target = namedtuple('Target', 'key label expected_raw expected_app strict hint')

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


def build_targets():
    targets = []
    for app_code in sorted(LEGO_COLOR_NAME_MAP):
        name = app_name(app_code)
        targets.append(Target(name.lower(), name, expected_wire_byte(app_code),
                              app_code, app_code == LEGO_COLOR_NOCOLOR,
                              HINTS.get(app_code)))
        if app_code == LEGO_COLOR_NOCOLOR:
            targets.append(Target(
                'black', 'BLACK', _FW_BLACK & 0xff, LEGO_COLOR_NOCOLOR, True,
                'a black brick. The App has no BLACK — firmware 0 maps to '
                'No color, so only the raw byte separates them'))
    return targets


def select_targets(targets, only):
    '''--only accepts names (orange,black,teal) or App codes (4,8,10).
    Numbers never select BLACK, since it has no App code of its own.'''
    if not only:
        return targets, []
    wanted = [w.strip().lower() for w in only.split(',') if w.strip()]
    chosen, unknown = [], []
    for want in wanted:
        if want.isdigit():
            match = [t for t in targets if t.key != 'black'
                     and t.expected_app == int(want)]
        else:
            match = [t for t in targets if t.key == want]
        if match:
            chosen.extend(m for m in match if m not in chosen)
        else:
            unknown.append(want)
    return chosen, unknown


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


def verdict_for(target, samples):
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

    if target.strict:
        # No color and Black share App code 0, so the translated value can't
        # distinguish them — only the wire byte can.
        if raw == target.expected_raw:
            return raw, seen_app, 'ok', stability
        sibling = 'BLACK' if target.key != 'black' else 'No color'
        if seen_app == target.expected_app:
            return raw, seen_app, 'MISMATCH', (
                f"read 0x{raw:02x}, which is the {sibling} code — the sensor "
                f"may not distinguish the two. {stability}")
        return raw, seen_app, 'MISMATCH', f"read {app_name(seen_app)} — {stability}"

    if seen_app == target.expected_app:
        note = stability
        if target.expected_raw is not None and raw != target.expected_raw:
            note = (f"maps correctly but via 0x{raw:02x}, not the expected "
                    f"0x{target.expected_raw:02x} — {stability}")
        return raw, seen_app, 'ok', note
    return raw, seen_app, 'MISMATCH', f"read {app_name(seen_app)} — {stability}"


def result_row(target, raw, seen_app, verdict, note):
    return {'target': target.label,
            'app_code': '' if target.key == 'black' else target.expected_app,
            'expected_raw': (f"0x{target.expected_raw:02x}"
                             if target.expected_raw is not None else ''),
            'raw': f"0x{raw:02x}" if raw is not None else '',
            'seen_app': '' if seen_app is None else seen_app,
            'verdict': verdict, 'note': note}


async def measure_target(sampler, target, settle):
    '''Measure once, and offer a re-measure whenever it doesn't come back
    clean — a fumbled brick shouldn't cost a whole rerun.'''
    while True:
        print(f"\n       measuring {settle:.1f}s, hold it steady...")
        samples = await sampler.measure(settle)
        raw, seen_app, verdict, note = verdict_for(target, samples)
        raw_text = f"0x{raw:02x}" if raw is not None else '--'
        mark = {'ok': 'OK ', 'MISMATCH': '!! ', 'NO DATA': '?? '}[verdict]
        print(f"       {mark} byte 5 = {raw_text}   {note}")
        if verdict == 'ok':
            print()
            return raw, seen_app, verdict, note
        again = await _ainput("       [Enter] accept  [r] re-measure > ")
        if not again.strip().lower().startswith('r'):
            print()
            return raw, seen_app, verdict, note


async def run(sampler, targets, settle):
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

    for target in targets:
        label = target.label + (f"  ({target.hint})" if target.hint else '')
        expected_text = (f"expect byte 0x{target.expected_raw:02x}"
                         if target.expected_raw is not None else '')
        answer = await _ainput(f"  {label}\n       {expected_text}\n"
                               f"       Enter to measure > ")
        if answer.strip().lower().startswith('s'):
            results.append(result_row(target, None, None, 'skipped', ''))
            print("\n       skipped\n")
            continue
        raw, seen_app, verdict, note = await measure_target(sampler, target, settle)
        results.append(result_row(target, raw, seen_app, verdict, note))
    return results


def report(results):
    print('=' * 74)
    print('  Target      Expected  Got   Maps to        Verdict')
    print('  ' + '-' * 70)
    for r in results:
        maps = app_name(r['seen_app']) if r['seen_app'] != '' else ''
        print(f"  {r['target']:<11} {r['expected_raw']:>8}  {r['raw'] or '--':>4}   "
              f"{maps:<14} {r['verdict']}")

    measured = [r for r in results if r['verdict'] in ('ok', 'MISMATCH')]
    good = [r for r in measured if r['verdict'] == 'ok']
    bad = [r for r in measured if r['verdict'] == 'MISMATCH']
    skipped = [r for r in results if r['verdict'] == 'skipped']
    print()
    print(f"  {len(good)}/{len(measured)} measured targets decoded correctly"
          + (f", {len(skipped)} skipped" if skipped else ''))
    if bad:
        print("\n  Mismatches — these contradict the firmware table:")
        for r in bad:
            print(f"    {r['target']}: {r['note']}")
    print('=' * 74)


def write_csv(results, path):
    fields = ['target', 'app_code', 'expected_raw', 'raw', 'seen_app', 'verdict', 'note']
    with open(path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)


async def _main(args):
    targets, unknown = select_targets(build_targets(), args.only)
    if unknown:
        print(f"Don't know these colours: {', '.join(unknown)}")
        print(f"Valid names: {', '.join(t.key for t in build_targets())}")
        return 1
    if not targets:
        print("Nothing selected.")
        return 1

    sampler = Sampler(args.serial, args.color)
    results = []
    async with BleakScanner(detection_callback=sampler.on_advertisement):
        try:
            results = await run(sampler, targets, args.settle)
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
                        help='Test only these targets, by name (orange,black,teal) '
                             'or App code (4,8,10). Numbers never select black.')
    parser.add_argument('--out', default='color_verify.csv', help='CSV output path')
    args = parser.parse_args()
    try:
        return asyncio.run(_main(args))
    except KeyboardInterrupt:
        print("\nStopped.")
        return 1


if __name__ == '__main__':
    sys.exit(main())
