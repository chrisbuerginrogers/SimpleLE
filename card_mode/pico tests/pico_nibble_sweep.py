'''
Nibble sweep for the fake controller (Pico W / Pico 2 W, MicroPython). Holds
the beacon fixed except payload bytes 5 & 6, and steps ONE nibble of them
(both bytes together) through 0..F, so you can see which 4 bits actually drive
the motor.

  >>> Runs ON the Pico W, not the Mac. Copy as main.py and run. <<<

SWEEP = "high": b5 = b6 = 0x0F, 0x1F, 0x2F, ... 0xFF   (varies the top nibble;
                this is the "0F to FF" sweep — low nibble held at 0xF)
SWEEP = "low" : b5 = b6 = 0x00, 0x01, 0x02, ... 0x0F   (varies the bottom
                nibble; high nibble held at 0x0)

Prediction from earlier data: the motor's command is a nibble-SWAP of the byte,
so the *low* nibble is the dominant/coarse part. Expect "low" to sweep the
motor through its full range, and "high" to barely move it. This sweep settles
which is which. Each step prints the byte and how scan_advertising.py decodes it.
'''

import bluetooth
import time

# ── card: match your motor ────────────────────────────────────────────
CARD_COLOR = 0x02          # 0x02 = purple
CARD_SERIAL = 6044

SWEEP = "high"             # "high" (your 0x0F..0xFF request) or "low"
STEP_MS = 500              # dwell per level (only 16 levels, so slower = easier to watch)
LOOP = True

# ── fixed beacon constants ────────────────────────────────────────────
TYPE_TAG = 0x02
BYTE2 = 0xf3
FIXED_78 = b'\x48\x80'
SERVICE_UUID16 = 0xFD02
ADV_INTERVAL_US = 100_000
COUNTER_STEP = 0x00B300


def _s8(x):
    return x - 256 if x >= 128 else x


def _decode(b5, b6):
    left = _s8(((b6 & 0x0F) << 4) | (b5 >> 4))
    right = _s8(((b5 & 0x0F) << 4) | (b6 >> 4))
    return left, right


def _byte_for(n):
    '''Map sweep index n (0..15) to the byte value used for b5 and b6.'''
    if SWEEP == "high":
        return (n << 4) | 0x0F     # 0x0F, 0x1F, ... 0xFF
    return n                        # 0x00, 0x01, ... 0x0F


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
    print("Sweeping the {} nibble of bytes 5 & 6 as card 0x{:02x}#{}".format(
        SWEEP, CARD_COLOR, CARD_SERIAL))

    counter = 0
    try:
        while True:
            for n in range(16):
                b5 = b6 = _byte_for(n)
                ble.gap_advertise(None)
                ble.gap_advertise(ADV_INTERVAL_US, adv_data=_beacon(b5, b6, counter),
                                  connectable=False)
                counter = (counter + COUNTER_STEP) & 0xFFFFFF
                left, right = _decode(b5, b6)
                print("b5=b6=0x{:02x}   decode L:{:+4d} R:{:+4d}".format(b5, left, right))
                time.sleep_ms(STEP_MS)
            if not LOOP:
                break
    finally:
        ble.gap_advertise(None)
        ble.active(False)
        print("Stopped.")


main()
