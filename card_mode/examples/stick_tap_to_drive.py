'''
Start up, wait for a card tap, then drive that card's motor.

  >>> Runs ON the M5StickS3, not the Mac. <<<
  Needs on the Stick: m5/, picolib.py, lego_card.py, stick_ui.py

Tap a card on the RFID reader and the Stick reads its color and serial straight
off the card, then broadcasts as that card so the motor tapped with the same
card drives. The screen turns the card's color and shows which card is driving.
Lift the card and it stops, but the screen keeps showing it -- that is the card
whose details are in use.

── The one thing the card does not carry ─────────────────────────────────
A motor also checks two bytes of the beacon, b2 and b7, and ignores a beacon
that has them wrong. Those are not stored on the card -- they differ per card
across every card sampled -- so each card needs registering in TOKENS below
once. Tap an unregistered card and this prints a line ready to paste in.

To find a card's tokens: run ../watch_service_data.py on the Mac
with a controller or color sensor carrying that card switched on, and take
bytes 2 and 7 of the FD02 payload.
'''

from time import sleep_ms

import lego_card
import picolib
import stick_ui

# ── card tokens, keyed by (color, serial) ─────────────────────────────────
# The color and serial come off the card itself; only these two bytes have to
# be looked up. Tap an unknown card to have its key printed for you.
TOKENS = {
    (picolib.PURPLE, 6055): dict(b2=0xF3, b7=0x48),
}

SPEED = 70          # -100..100, rounded to the seven steps a stick can send


def main():
    ui = stick_ui.UI()
    ui.looking('TAP A CARD')
    print('tap a card on the reader')

    rfid = lego_card.open_reader()
    motor = None
    driving = None

    try:
        while True:
            try:
                found = lego_card.read_card(rfid)
            except lego_card.CardReadFailed as e:
                # A failed read says nothing about the card; try it again.
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
            print()
            print('{} #{}  (UID {})'.format(
                name, serial, ''.join('%02X' % b for b in uid)))

            tokens = TOKENS.get(key)
            if tokens is None:
                ui.problem('NEED TOKENS', '{} {}'.format(name, serial))
                print('not registered. Add this to TOKENS:')
                print('    (picolib.{}, {}): dict(b2=0x??, b7=0x??),'.format(
                    name, serial))
                rfid.halt()
                sleep_ms(1500)
                continue

            if motor is not None:
                motor.stop()
                motor.close()

            card = picolib.Card(color=color, serial=serial, **tokens)
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
