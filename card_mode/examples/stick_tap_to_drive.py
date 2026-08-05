'''
Start up, wait for a card tap, then drive that card's motor.

  >>> Runs ON the M5StickS3, not the Mac. <<<
  Needs on the Stick: m5/ (2026-08 or later), picolib.py, lego_card.py, stick_ui.py

Tap a card on the RFID reader and the Stick reads its color and serial straight
off the card, then broadcasts as that card so the motor tapped with the same
card drives. The screen turns the card's color and shows which card is driving.
Lift the card and it stops, but the screen keeps showing it -- that is the card
whose details are in use.

── The two bytes the card does not store ─────────────────────────────────
A motor also checks bytes 2 and 7 of the beacon and ignores one that has them
wrong. They are not written on the card, but they are computable from it:
they are a CRC-16 of the card's RFID UID, so lego_card.card_hash(uid) gets
them from the same tap that gave us the color and serial.

This used to be a lookup table you filled in by hand, one line per card, read
off the air with ../watch_service_data.py. Any card works now, first tap, with
nothing registered in advance.
'''

from time import sleep_ms

import lego_card
import picolib
import stick_ui
from m5.m5_rfid import RFID, ReadError

SPEED = 70          # -100..100, rounded to the seven steps a stick can send


def main():
    ui = stick_ui.UI()
    ui.looking('TAP A CARD')
    print('tap a card on the reader')

    rfid = RFID()
    motor = None
    driving = None

    try:
        while True:
            try:
                found = lego_card.read_card(rfid)
            except ReadError as e:
                # A failed read says nothing about the card, and the driver
                # already retried it three times; go round again.
                print('read failed ({}), will retry'.format(e))
                rfid.halt()
                sleep_ms(150)
                continue
            except lego_card.NotALegoCard as e:
                print('not a LEGO card: {}'.format(e))
                ui.problem('NOT A CARD', str(e)[:20])
                rfid.halt()
                sleep_ms(1000)
                continue

            if found is None:
                # Card lifted off: stop driving, but leave it on screen.
                if motor is not None:
                    motor.stop()
                    motor.close()
                    motor = None
                    driving = None
                    ui.status('lift -- stopped')
                    print('card removed, stopped')
                sleep_ms(150)
                continue

            uid, (color, serial) = found
            key = (color, serial)

            if key == driving:
                # Same card still there: keep the beacon fresh, or the motor
                # decides nobody is talking to it any more.
                motor.refresh()
                sleep_ms(40)
                continue

            name = stick_ui.color_name(color)
            b2, b7 = lego_card.card_hash(uid)
            print()
            print('{} #{}  (UID {})  b2=0x{:02X} b7=0x{:02X}'.format(
                name, serial, ''.join('%02X' % b for b in uid), b2, b7))

            if motor is not None:
                motor.stop()
                motor.close()

            card = picolib.Card(color=color, serial=serial, b2=b2, b7=b7)
            motor = picolib.Motor(card)
            driving = key
            sent = motor.set_speed(SPEED)
            ui.card(color, serial)
            ui.status('DRIVING {}'.format(sent))
            print('broadcasting as {} at speed {}'.format(card, sent))
    finally:
        if motor is not None:
            motor.close()
        ui.close()
        print('stopped')


main()
