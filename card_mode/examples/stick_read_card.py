'''
Tap a LEGO connection card and see what it is, on the screen and out loud.

  >>> Runs ON the M5StickS3, not the Mac. <<<
  Needs on the Stick: m5/ (2026-08 or later), lego_card.py, stick_ui.py

The screen says LOOKING until the first card arrives, then turns the card's own
color and shows the color name and serial. It beeps once when a card is read,
and buzzes low for a tag that is not a LEGO card.

Lift the card off and the screen keeps showing it -- that card's color and
serial are the ones you are about to use, so they stay readable until the next
tap replaces them.

The color and serial are read straight off the card. From a purple #6055:

    page 4  4C334730 000217A7 00000000 FFEEDDCC
            "L3G0"      ^^ ^^^^-- 0x17A7 = 6055
                        +-------- 0x02 = firmware PURPLE

The raw pages behind that decode are printed to the console too, in case you
want to see them. What is NOT on the card is the b2/b7 tokens a motor
validates -- see stick_tap_to_drive.py for where those come from.
'''

from time import sleep_ms

import lego_card
import stick_ui
from m5.m5_rfid import RFID, ReadError, DEFAULT_KEY


def as_hex(data):
    return ''.join('{:02X}'.format(b) for b in data)


def dump(rfid):
    '''The raw pages, to the console -- the evidence behind the decode.

    Shows what None and ReadError each mean now that the driver tells them
    apart: None is the tag refusing this command for good, ReadError is a
    read that fell over and stops the dump because the tag has likely gone.
    '''
    if rfid.sak == 0x00:
        for page in range(0, 45, 4):
            try:
                data = rfid.read_pages(page)
            except ReadError as e:
                print('  page {:2d}  read failed ({})'.format(page, e))
                break
            if data is None:
                break               # not a tag type that serves 0x30
            print('  page {:2d}  {}'.format(page, as_hex(data)))
    else:
        for block in range(0, 16):
            try:
                data = rfid.read_block(block, DEFAULT_KEY)
            except ReadError as e:
                print('  block {:2d}  read failed ({})'.format(block, e))
                continue
            print('  block {:2d}  {}'.format(
                block, 'locked' if data is None else as_hex(data)))


def main():
    ui = stick_ui.UI()
    ui.looking()
    print('tap a card on the reader')

    rfid = RFID()
    last_uid = None

    try:
        while True:
            uid = rfid.read_uid()

            if uid is None:
                # Field empty, so the same card coming back counts as a fresh
                # tap rather than being ignored as a repeat. The screen keeps
                # showing the last card read.
                last_uid = None
                sleep_ms(150)
                continue

            if uid == last_uid:
                rfid.halt()
                sleep_ms(150)
                continue
            last_uid = uid

            print()
            print('UID  {}'.format(as_hex(uid)))
            print('SAK  {:#04x}  {}'.format(rfid.sak, rfid.card_type()))

            try:
                color, serial = lego_card.read_card_data(rfid)
            except ReadError as e:
                # The read fell over, which says nothing about the card, and
                # the driver already retried it three times. Forget the UID so
                # the next pass tries again instead of writing it off as a
                # repeat.
                print('read failed ({}), will retry'.format(e))
                last_uid = None
                rfid.halt()
                sleep_ms(150)
                continue
            except lego_card.NotALegoCard as e:
                print('not a LEGO card: {}'.format(e))
                ui.problem('NOT A CARD', str(e)[:20])
                rfid.halt()
                continue

            print('CARD {} #{}   (App color {})'.format(
                stick_ui.color_name(color), serial, color))
            ui.card(color, serial)

            try:
                dump(rfid)
            except Exception as e:
                print('  could not read the data pages: {}'.format(e))
            rfid.halt()
    finally:
        ui.close()


main()
