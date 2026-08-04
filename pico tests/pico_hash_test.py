'''
Card-hash validation test (Pico W / Pico 2 W, MicroPython).

Broadcasts a controller beacon with the CORRECT card colour + serial but the
WRONG card-hash bytes (byte2 / byte7), driving the motor full forward. Tells us
whether the motor validates the hash:

  * motor still spins  -> hash is NOT checked (only colour+serial matter)
  * motor ignores it   -> hash IS checked (spoofing needs the right byte2/7)

  >>> Runs ON the Pico W, not the Mac. Copy as main.py and run. <<<

Procedure:
  1. Set USE_CORRECT_HASH = True, run -> confirm the motor spins (control test).
  2. Set USE_CORRECT_HASH = False, run -> does it still spin with wrong hash?
'''

import bluetooth
import time

# ── card: correct colour + serial for the group ──────────────────────
CARD_COLOR = 0x02          # purple
CARD_SERIAL = 1126

# Correct card-hash for #1126 is byte2=0xf3, byte7=0x48.
USE_CORRECT_HASH = False   # False = broadcast WRONG hash (the actual test)
WRONG_BYTE2 = 0x00         # deliberately wrong (correct: 0xf3)
WRONG_BYTE7 = 0x00         # deliberately wrong (correct: 0x48)

# Drive command: low nibble is the signed speed. 0x03 = full forward,
# 0x0d = full reverse, 0x00 = stop. Both sticks so the motor gets full effect.
DRIVE = 0x03

# ── fixed beacon fields ───────────────────────────────────────────────
TYPE_TAG = 0x03            # controller
BYTE8 = 0x80               # controllers broadcast 0x80 here
SERVICE_UUID16 = 0xFD02
ADV_INTERVAL_US = 100_000
STEP_MS = 40
COUNTER_STEP = 0x00B300


def _beacon(counter):
    b2 = 0xf3 if USE_CORRECT_HASH else WRONG_BYTE2
    b7 = 0x48 if USE_CORRECT_HASH else WRONG_BYTE7
    svc = bytes([
        TYPE_TAG, CARD_COLOR, b2,
        CARD_SERIAL & 0xFF, (CARD_SERIAL >> 8) & 0xFF,
        DRIVE, DRIVE,          # b5 = RIGHT, b6 = LEFT (both full forward)
        b7, BYTE8,
        (counter >> 16) & 0xFF, (counter >> 8) & 0xFF, counter & 0xFF,
    ])
    sd = bytes([0x16, SERVICE_UUID16 & 0xFF, (SERVICE_UUID16 >> 8) & 0xFF]) + svc
    flags = bytes([0x02, 0x01, 0x06])
    return flags + bytes([len(sd)]) + sd


def main():
    ble = bluetooth.BLE()
    ble.active(True)
    print("Broadcasting card #{} with {} hash (b2={:#04x} b7={:#04x}), drive=0x{:02x}".format(
        CARD_SERIAL,
        "CORRECT" if USE_CORRECT_HASH else "WRONG",
        0xf3 if USE_CORRECT_HASH else WRONG_BYTE2,
        0x48 if USE_CORRECT_HASH else WRONG_BYTE7,
        DRIVE))
    print("Watch the motor: spins = hash ignored, still = hash validated.")

    counter = 0
    try:
        while True:
            ble.gap_advertise(None)
            ble.gap_advertise(ADV_INTERVAL_US, adv_data=_beacon(counter), connectable=False)
            counter = (counter + COUNTER_STEP) & 0xFFFFFF
            time.sleep_ms(STEP_MS)
    finally:
        ble.gap_advertise(None)
        ble.active(False)
        print("Stopped.")


main()
