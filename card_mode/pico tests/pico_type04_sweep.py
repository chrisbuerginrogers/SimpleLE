'''
Diagnostic: raw byte-sweep of device type 0x04, "double motor drive," which
takes b5/b6 as a direct signed-8 per-wheel speed instead of the 0x03
controller's 7-state low-nibble encoding.

  >>> Runs ON the Pico W / Pico 2 W (MicroPython), not the Mac. <<<

CONFIRMED, live, 2026-08-08 against a real Double Motor -- see
../Card_mode.md, "A second device type, byte0 = 0x04: confirmed". This file
predates that confirmation and is kept as a raw diagnostic (same shape as
pico_raw_sweep.py's sweep of 0x03), not the way to drive a motor day to day
-- use picolib.Motor.set_tank_v04() / pico_lelib.doubleMotor.tank_v04() for
that; they handle the mirror-image sign flip this sweep doesn't.

Sends b5 = b6 = v and walks v 0x00 -> 0xFF, +1 every STEP_MS. Since it sends
the same raw value to both wheels with no sign flip, expect it to look like
a turn rather than straight-line motion on a mirror-mounted rig (see
Card_mode.md) -- that's expected, not a regression.

Set CARD_COLOR / CARD_SERIAL to match your motor's card and B2 / B7 to that
card's tokens (card_hash.py UID, or read off a sender with
../watch_service_data.py) -- 0x04, like 0x03, still needs the right hash or
the motor ignores the beacon regardless of what b5/b6 say.
'''

import bluetooth
import time

# ── card: match your motor ────────────────────────────────────────────
CARD_COLOR = 0x02          # 0x02 = purple
CARD_SERIAL = 1126
B2 = 0xf3                  # card token -- get with card_hash.py or watch_service_data.py
B7 = 0x48                  # ditto

STEP_MS = 200               # dwell on each byte value

# ── beacon constants ─────────────────────────────────────────────────
TYPE_TAG = 0x04             # the claimed "double motor drive" type
BYTE8 = 0x80                # constant, per the 0x03 layout
SERVICE_UUID16 = 0xFD02
ADV_INTERVAL_US = 100_000
COUNTER_STEP = 0x00B300


def _s8(x):
    return x - 256 if x >= 128 else x


def _beacon(b5, b6, counter):
    svc_payload = bytes([
        TYPE_TAG, CARD_COLOR, B2,
        CARD_SERIAL & 0xFF, (CARD_SERIAL >> 8) & 0xFF,
        b5, b6, B7, BYTE8,
        (counter >> 16) & 0xFF, (counter >> 8) & 0xFF, counter & 0xFF,
    ])
    sd = bytes([0x16, SERVICE_UUID16 & 0xFF, (SERVICE_UUID16 >> 8) & 0xFF]) + svc_payload
    flags = bytes([0x02, 0x01, 0x06])
    return flags + bytes([len(sd)]) + sd


def main():
    ble = bluetooth.BLE()
    ble.active(True)
    print("Sweeping type-0x04 b5=b6 0x00..0xFF, +1 every {} ms, as card 0x{:02x}#{}".format(
        STEP_MS, CARD_COLOR, CARD_SERIAL))
    print("Watch the motor. Ctrl-C to stop.")

    counter = 0
    try:
        while True:
            for v in range(256):
                b5 = b6 = v
                ble.gap_advertise(None)
                ble.gap_advertise(ADV_INTERVAL_US, adv_data=_beacon(b5, b6, counter),
                                  connectable=False)
                counter = (counter + COUNTER_STEP) & 0xFFFFFF
                print("b5=b6=0x{:02x} ({:4d})  as signed-8: {:+4d}".format(
                    v, v, _s8(v)))
                time.sleep_ms(STEP_MS)
    finally:
        ble.gap_advertise(None)
        ble.active(False)
        print("Stopped.")


main()
