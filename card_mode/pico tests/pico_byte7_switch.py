'''
Interactive byte-7 switcher (Pico W / Pico 2 W, MicroPython).

Broadcasts a valid controller beacon (card #1126, driving the motor forward)
and lets you type a new value for byte 7 on the fly, to see what — if anything —
it changes. Each entry broadcasts a ~2 s burst (counter ticking) so the motor
has time to react, then prompts again.

  >>> Runs ON the Pico W, not the Mac. Copy as main.py and run. <<<

At the prompt type a byte value 0–255 (decimal) or 0x.. (hex); 'q' to quit.
'''

import bluetooth
import time

# ── valid beacon (everything except byte 7) ───────────────────────────
CARD_COLOR = 0x02          # purple
CARD_SERIAL = 1126
BYTE2 = 0xf3               # card hash (not validated, but use the real one)
DRIVE = 0x03               # low nibble command: 0x03 fwd, 0x0d rev, 0x00 stop
BYTE8 = 0x80

TYPE_TAG = 0x03            # controller
SERVICE_UUID16 = 0xFD02
ADV_INTERVAL_US = 100_000
STEP_MS = 40
BURST = 50                 # packets per entry (~2 s at STEP_MS)
COUNTER_STEP = 0x00B300


def _beacon(byte7, counter):
    svc = bytes([
        TYPE_TAG, CARD_COLOR, BYTE2,
        CARD_SERIAL & 0xFF, (CARD_SERIAL >> 8) & 0xFF,
        DRIVE, DRIVE,
        byte7 & 0xFF, BYTE8,
        (counter >> 16) & 0xFF, (counter >> 8) & 0xFF, counter & 0xFF,
    ])
    sd = bytes([0x16, SERVICE_UUID16 & 0xFF, (SERVICE_UUID16 >> 8) & 0xFF]) + svc
    flags = bytes([0x02, 0x01, 0x06])
    return flags + bytes([len(sd)]) + sd


def main():
    ble = bluetooth.BLE()
    ble.active(True)
    counter = 0
    print("byte7 switcher — type 0-255 or 0x.., 'q' to quit.")
    try:
        while True:
            s = input("byte7 = ").strip()
            if s.lower() in ("q", "quit", "exit"):
                break
            try:
                b7 = int(s, 0) & 0xFF          # accepts 72 or 0x48
            except ValueError:
                print("  ? enter a number like 72 or 0x48")
                continue
            print("  broadcasting byte7=0x{:02x} for ~2s...".format(b7))
            for _ in range(BURST):
                ble.gap_advertise(None)
                ble.gap_advertise(ADV_INTERVAL_US, adv_data=_beacon(b7, counter),
                                  connectable=False)
                counter = (counter + COUNTER_STEP) & 0xFFFFFF
                time.sleep_ms(STEP_MS)
    finally:
        ble.gap_advertise(None)
        ble.active(False)
        print("Stopped.")


main()
