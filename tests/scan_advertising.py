'''
Live table of BLE advertisements from nearby LEGO Education devices,
refreshed in place — one row per address, always showing that device's
latest manufacturer data / service data. This is what fires the instant a
LEGO Education card is tapped against a hub/sensor, since the card
color+serial is broadcast in the advertisement (not something you need a
GATT connection to read). Rows are marked '*' for a few seconds after
their payload changes, so tapping a new card is easy to spot.

By default only devices carrying LEGO's signature are shown: manufacturer
company ID 0x0397, or the FD02 service UUID (some tech elements broadcast
the card state as service data instead of manufacturer data — both are
decoded into the LEGO Card column). Pass --all to see every BLE device in
range instead, in which case a secondary noise filter kicks in — matched by
name substring (NOISY_NAME_SUBSTRINGS), company ID (NOISY_COMPANY_IDS),
service UUID (NOISY_SERVICE_UUIDS), or exact address (NOISY_ADDRESSES) — to
keep out known-irrelevant traffic (Apple continuity beacons, etc).

Usage:
    python scan_advertising.py
    python scan_advertising.py --name Move     # only devices whose name contains this
    python scan_advertising.py --all           # show every BLE device, not just LEGO ones
    python scan_advertising.py --all --include-noisy # ...including the noisy list

Ctrl+C to stop.

Note on "extended advertising": bleak (and the OS BLE stacks it wraps —
CoreBluetooth on macOS, BlueZ on Linux, WinRT on Windows) hands you the
merged advertisement + scan-response payload, not the raw HCI PDU, so
there's no portable way to tell whether a given packet arrived as a legacy
or BLE5 extended-advertising PDU. If you need that level of detail you'd
want a dedicated sniffer (e.g. an nRF52840 dongle running Nordic's BLE
Sniffer firmware + Wireshark, or `btmon`/`hcidump` on Linux). What this
script *does* give you is every advertisement's contents in real time,
which is what changes when a card is tapped.
'''

import argparse
import asyncio
import sys
import time

from bleak import BleakScanner
from legoeducation.basic_ble import LEGO_COMPANY_ID, SERVICE_UUID
from legoeducation.color_map import _firmware_to_app, LEGO_COLOR_NAME_MAP

SERVICE_UUID_LOWER = SERVICE_UUID.lower()
BLE_BASE_UUID_SUFFIX = '-0000-1000-8000-00805f9b34fb'

NOISY_NAME_SUBSTRINGS = [
    'apple', 'rivian', 'violin', 'bose', 'airpods', 'n0', 'nk', 'buerginbase',
]
# BLE manufacturer company IDs to filter out (never LEGO's 0x0397).
# 0x004c is Apple's registered ID; 0x00e0/0x0969/0x0334 are other vendors
# observed flooding the table (not identified further, just excluded).
NOISY_COMPANY_IDS = {0x004c, 0x00e0, 0x0969, 0x0334}
# Service UUIDs / service-data UUIDs seen on devices with no manufacturer
# data at all (so the company-ID filter above can't catch them).
NOISY_SERVICE_UUIDS = {
    '0000feaf-0000-1000-8000-00805f9b34fb',
    '0000fe9f-0000-1000-8000-00805f9b34fb',
}
# Specific device addresses to silence outright, for one-offs that don't
# fit a name/company/service pattern (paste more as you spot them).
NOISY_ADDRESSES = {'B785B3F1-346E-82A2-F99B-4EA65E6FA09C'}
CHANGED_HIGHLIGHT_SECONDS = 3.0
REFRESH_INTERVAL = 0.5
STALE_AFTER_SECONDS = 10.0


def _decode_card_bytes(payload, color_index):
    '''card_serial is always payload[3] | (payload[4] << 8) little-endian —
    confirmed both in legoeducation's own manufacturer-data decoder and here.

    card_color's position shifts depending on the carrier:
    - manufacturer data: [product_group, product_device, color, serial_lo, serial_hi]
      (color at index 2) — this is legoeducation's own documented layout.
    - FD02 service data: observed as [?, color, ?, serial_lo, serial_hi, ...]
      (color at index 1) — inferred empirically: index 1 matched the firmware
      LEGO_COLOR_PURPLE code (2) exactly while the serial at [3:5] matched the
      known card serial, across two independent devices. Not from LEGO docs,
      so treat as a working hypothesis, not a spec.
    '''
    if len(payload) <= max(color_index, 4):
        return f"partial({payload.hex()})"
    card_color = _firmware_to_app(payload[color_index])
    card_serial = payload[3] | (payload[4] << 8)
    color_name = LEGO_COLOR_NAME_MAP.get(card_color, str(card_color)).replace('LEGO_COLOR_', '')
    return f"{color_name}#{card_serial}"


def decode_lego_card(manufacturer_data, service_data):
    lego_bytes = (manufacturer_data or {}).get(LEGO_COMPANY_ID)
    if lego_bytes is not None:
        return _decode_card_bytes(lego_bytes, color_index=2)
    for uuid, payload in (service_data or {}).items():
        if uuid.lower() == SERVICE_UUID_LOWER:
            return _decode_card_bytes(payload, color_index=1)
    return ''


def _signed_byte(b):
    return b - 256 if b >= 128 else b


def decode_controller_axes(service_data):
    '''FD02 service-data bytes 5 (right stick) and 6 (left stick), signed
    8-bit, resting at 0. Inferred from a single capture session (push one
    stick out and back, then the other, and match which byte spiked when)
    — not documented by LEGO, so treat as a working hypothesis that may
    need revisiting once we see full-deflection values.'''
    for uuid, payload in (service_data or {}).items():
        if uuid.lower() == SERVICE_UUID_LOWER and len(payload) >= 7:
            return f"L:{_signed_byte(payload[6]):+d} R:{_signed_byte(payload[5]):+d}"
    return ''


def short_uuid(uuid_str):
    '''Collapse the 128-bit Bluetooth base UUID form down to its 16-bit
    hex so it doesn't eat the whole column width, e.g.
    "0000fd02-0000-1000-8000-00805f9b34fb" -> "0xfd02".'''
    s = uuid_str.lower()
    if s.startswith('0000') and s.endswith(BLE_BASE_UUID_SUFFIX):
        return '0x' + s[4:8]
    return s


def fmt_hex_map(data, key_fmt=str):
    if not data:
        return ''
    return ' '.join(f"{key_fmt(k)}:{v.hex()}" for k, v in data.items())


def is_noisy_name(name):
    if not name:
        return False
    lname = name.lower()
    return any(s in lname for s in NOISY_NAME_SUBSTRINGS)


def is_noisy_company(manufacturer_data):
    return any(company_id in NOISY_COMPANY_IDS for company_id in (manufacturer_data or {}))


def is_noisy_service(adv):
    uuids = {u.lower() for u in (adv.service_uuids or [])}
    uuids.update(u.lower() for u in (adv.service_data or {}))
    return not uuids.isdisjoint(NOISY_SERVICE_UUIDS)


def is_noisy_address(address):
    return address is not None and address.upper() in NOISY_ADDRESSES


def is_lego(adv):
    '''True if this advertisement carries LEGO's signature either way it
    might show up: company ID 0x0397 in manufacturer data, or the FD02
    service UUID in service_uuids / service_data.'''
    if LEGO_COMPANY_ID in (adv.manufacturer_data or {}):
        return True
    uuids = {u.lower() for u in (adv.service_uuids or [])}
    uuids.update(u.lower() for u in (adv.service_data or {}))
    return SERVICE_UUID_LOWER in uuids


def make_callback(name_filter, include_noisy, lego_only, devices):
    def on_advertisement(device, adv):
        if lego_only and not is_lego(adv):
            return
        if not include_noisy and (
            is_noisy_name(device.name)
            or is_noisy_company(adv.manufacturer_data)
            or is_noisy_service(adv)
            or is_noisy_address(device.address)
        ):
            return
        if name_filter and (not device.name or name_filter.lower() not in device.name.lower()):
            return

        now = time.monotonic()
        mfg = fmt_hex_map(adv.manufacturer_data, key_fmt=lambda k: f"{k:#06x}")
        svc = fmt_hex_map(adv.service_data, key_fmt=short_uuid)
        lego_card = decode_lego_card(adv.manufacturer_data, adv.service_data)
        ctrl_axes = decode_controller_axes(adv.service_data)

        prev = devices.get(device.address)
        # Compare on the decoded fields when we have them — LEGO's trailing
        # bytes (beyond color+serial+axes) appear to rotate on every single
        # advertisement, so comparing the raw payload would mark '*' almost
        # permanently instead of only on a real card tap / stick movement.
        if lego_card or ctrl_axes:
            unchanged = prev and prev['lego_card'] == lego_card and prev['ctrl_axes'] == ctrl_axes
        else:
            unchanged = prev and prev['mfg_data'] == mfg and prev['service_data'] == svc
        changed_at = prev['changed_at'] if unchanged else now
        first_seen = prev['first_seen'] if prev else now

        devices[device.address] = {
            'name': device.name or '',
            'rssi': adv.rssi,
            'lego_card': lego_card,
            'ctrl_axes': ctrl_axes,
            'mfg_data': mfg,
            'service_data': svc,
            'updated_at': now,
            'changed_at': changed_at,
            'first_seen': first_seen,
        }

    return on_advertisement


def render_table(devices):
    now = time.monotonic()
    headers = ['', 'Address', 'Name', 'RSSI', 'LEGO Card', 'L/R Axes', 'Mfg Data', 'Service Data', 'Age(s)', 'Seen(s)']
    rows = []
    for addr, d in sorted(devices.items()):
        recently_changed = (now - d['changed_at']) < CHANGED_HIGHLIGHT_SECONDS
        rows.append([
            '*' if recently_changed else '',
            addr,
            d['name'][:20],
            str(d['rssi']),
            d['lego_card'],
            d['ctrl_axes'],
            d['mfg_data'][:60],
            d['service_data'][:60],
            f"{now - d['updated_at']:.1f}",
            f"{now - d['first_seen']:.0f}",
        ])

    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt_row(cells):
        return '  '.join(cell.ljust(widths[i]) for i, cell in enumerate(cells))

    lines = [fmt_row(headers), '  '.join('-' * w for w in widths)]
    lines.extend(fmt_row(row) for row in rows)
    lines.append('')
    lines.append(
        f"* = payload changed in the last {CHANGED_HIGHLIGHT_SECONDS:.0f}s   |   "
        f"rows drop after {STALE_AFTER_SECONDS:.0f}s of silence   |   {len(rows)} devices   |   Ctrl+C to stop"
    )

    sys.stdout.write('\033[2J\033[H')
    sys.stdout.write('\n'.join(lines) + '\n')
    sys.stdout.flush()


def prune_stale(devices):
    now = time.monotonic()
    stale = [addr for addr, d in devices.items() if now - d['updated_at'] > STALE_AFTER_SECONDS]
    for addr in stale:
        del devices[addr]


async def render_loop(devices):
    while True:
        prune_stale(devices)
        render_table(devices)
        await asyncio.sleep(REFRESH_INTERVAL)


async def main(name_filter, include_noisy, lego_only):
    devices = {}
    async with BleakScanner(detection_callback=make_callback(name_filter, include_noisy, lego_only, devices)):
        await render_loop(devices)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name', default=None, help='Only show devices whose advertised name contains this substring')
    parser.add_argument('--include-noisy', action='store_true', help='Also show the Apple/etc. noisy-list devices')
    parser.add_argument('--all', action='store_true', help='Show every BLE device, not just ones carrying the LEGO signature')
    args = parser.parse_args()

    try:
        asyncio.run(main(args.name, args.include_noisy, lego_only=not args.all))
    except KeyboardInterrupt:
        print("\nStopped.")
