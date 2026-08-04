'''
Raw byte-sweep diagnostic for the fake controller (Pico W / Pico 2 W,
MicroPython). Holds the whole beacon fixed EXCEPT payload bytes 5 and 6, and
walks them together 0x00 -> 0xFF, +1 every STEP_MS. Lets you watch how the
motor responds across the entire byte range, with no assumptions about the
stick encoding.

  >>> Runs ON the Pico W, not the Mac. Copy as main.py and run. <<<

Set CARD_COLOR / CARD_SERIAL to match your motor's card (read it off the Mac
with scan_advertising.py -> "LEGO Card" column). Beacon layout:

    03  cc  f3  sl sh   b5 b6   48 80   k2 k1 k0
                        ^^^^^  <- these two are swept 0x00..0xFF together

Each step prints the byte value and, for reference, how scan_advertising.py
would decode it (L/R). One full 0x00..0xFF pass takes 256 * STEP_MS.
'''

import bluetooth
import time

# ── card: match your motor ────────────────────────────────────────────
CARD_COLOR = 0x02          # 0x02 = purple
CARD_SERIAL = 1126

STEP_MS = 200              # dwell on each byte value

# ── fixed beacon constants ────────────────────────────────────────────
TYPE_TAG = 0x03
BYTE2 = 0xf3
FIXED_78 = b'\x48\x80'
SERVICE_UUID16 = 0xFD02
ADV_INTERVAL_US = 100_000
COUNTER_STEP = 0x00B300


def _s8(x):
    return x - 256 if x >= 128 else x


def _decode(b5, b6):
    '''What scan_advertising.py would report (interleaved-nibble model).'''
    left = _s8(((b6 & 0x0F) << 4) | (b5 >> 4))
    right = _s8(((b5 & 0x0F) << 4) | (b6 >> 4))
    return left, right


def _beacon(b5, b6, counter):
    svc_payload = bytes([
        TYPE_TAG, CARD_COLOR, BYTE2,
        CARD_SERIAL & 0xFF, (CARD_SERIAL >> 8) & 0xFF,
        b5, b6,
    ]) + FIXED_78 + bytes([
        (counter >> 16) & 0xFF, (counter >> 8) & 0xFF, counter & 0xFF,
    ])
    sd = bytes([0x16, SERVICE_UUID16 & 0xFF, (SERVICE_UUID16 >> 8) & 0xFF]) + svc_payload
    flags = bytes([0x02, 0x01, 0x06])
    return flags + bytes([len(sd)]) + sd


def main():
    ble = bluetooth.BLE()
    ble.active(True)
    print("Sweeping bytes 5 & 6 (0x00..0xFF, +1 every {} ms) as card 0x{:02x}#{}".format(
        STEP_MS, CARD_COLOR, CARD_SERIAL))

    counter = 0
    try:
        while True:
            for v in range(256):
                b5 = b6 = v
                ble.gap_advertise(None)
                ble.gap_advertise(ADV_INTERVAL_US, adv_data=_beacon(b5, b6, counter),
                                  connectable=False)
                counter = (counter + COUNTER_STEP) & 0xFFFFFF
                left, right = _decode(b5, b6)
                print("b5=b6=0x{:02x} ({:3d})   decode L:{:+4d} R:{:+4d}".format(
                    v, v, left, right))
                time.sleep_ms(STEP_MS)
    finally:
        ble.gap_advertise(None)
        ble.active(False)
        print("Stopped.")


main()
