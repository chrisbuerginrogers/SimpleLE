'''
Drive a motor from the Stick, using a card whose numbers you already know.

  >>> Runs ON the M5StickS3, not the Mac. <<<
  Needs on the Stick: m5/, picolib.py, stick_ui.py

No cable, no Mac, no pairing: the Stick broadcasts the beacon a LEGO controller
sends, and any motor tapped with this card obeys it. The screen shows the card
in its own color and what the motor is being told to do.

Fill in the four numbers below, then run. Where to get them:

  color, serial    printed on the card, or tap it with stick_read_card.py
  b2, b7           the card's tokens. The motor checks these and ignores a
                   beacon that has them wrong, and they cannot be worked out
                   from the color and serial. Read them with
                   ../watch_service_data.py on the Mac, with a
                   controller or color sensor carrying this card switched on:
                   take bytes 2 and 7 of the FD02 payload.

If the motor does nothing, the tokens are the first thing to check.
'''

import picolib
import stick_ui

# ── your card ─────────────────────────────────────────────────────────────
CARD_COLOR = picolib.PURPLE      # RED, YELLOW, BLUE, TEAL, GREEN, PURPLE, ...
CARD_SERIAL = 6055

# Read off the air from card PURPLE #6055 -- the same pair came from both a
# color sensor and a controller carrying it, which is what "per card, not per
# device" means. A different card needs its own pair; the motor silently
# ignores a beacon whose tokens are wrong.
CARD_B2 = 0xDB
CARD_B7 = 0x2C

# ── what to do ────────────────────────────────────────────────────────────
SPEED = 70          # -100..100, rounded to the seven steps a stick can send
SECONDS = 3


def main():
    ui = stick_ui.UI()
    card = picolib.Card(color=CARD_COLOR, serial=CARD_SERIAL,
                        b2=CARD_B2, b7=CARD_B7)
    ui.card(CARD_COLOR, CARD_SERIAL)
    motor = picolib.Motor(card)
    print('broadcasting as', card)

    try:
        sent = motor.set_speed(SPEED)
        ui.status('FORWARD {}'.format(sent))
        print('forward at', sent)
        motor.drive(SECONDS)

        sent = motor.set_speed(-SPEED)
        ui.status('BACK {}'.format(sent))
        print('back at', sent)
        motor.drive(SECONDS)

        # Two sticks, so a Double Motor can spin on the spot.
        ui.status('SPIN')
        print('spin')
        motor.set_tank(100, -100)
        motor.drive(SECONDS)
    finally:
        motor.close()
        ui.status('stopped')
        ui.close()
        print('stopped')


main()
