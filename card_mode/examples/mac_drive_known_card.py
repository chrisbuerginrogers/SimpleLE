'''
Drive a motor in lelib syntax, written on the Mac, broadcast by the Stick.

  >>> Runs on the Mac, with the M5StickS3 plugged into USB. <<<

Your code stays on the Mac; each command goes down the cable to the Stick,
which does the transmitting (a Mac cannot transmit a BLE advertisement).

You do not have to look up the card's b2/b7 tokens here -- connect() scans for
them, which the Mac can do and the Stick cannot. That does mean a controller or
color sensor carrying this card has to be switched on and nearby.

First time only:
    import pico_lelib; pico_lelib.install()
'''

import os
import sys

# lelib.py and pico_lelib.py live in the repo root, two levels up.
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..')))

import pico_lelib

# ── your card ─────────────────────────────────────────────────────────────
# These have to match a real card or connect() will find nothing. To see which
# cards are actually broadcasting:  python3 -c "import lelib; print(lelib.find_cards())"
CARD_SERIAL = 6055
CARD_COLOR = 6           # le.LEGO_COLOR_PURPLE; see lelib.md for the numbers


def main():
    if not pico_lelib.check_pico():
        return

    motor = pico_lelib.doubleMotor()
    print('looking for card {}/{}...'.format(CARD_COLOR, CARD_SERIAL))
    motor.connect(CARD_SERIAL, card_color=CARD_COLOR)
    print('connected')

    try:
        print('forward at', motor.set_speed(70))
        motor.run_time(3000)

        print('back at', motor.set_speed(-70))
        motor.run_time(3000)

        print('spin', motor.tank(100, -100))
        motor.run_time(3000)
    finally:
        motor.stop()
        pico_lelib.close_link()
        print('stopped')


main()
