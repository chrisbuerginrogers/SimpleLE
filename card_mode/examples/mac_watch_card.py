'''
Watch everything broadcasting under one card, live.

  >>> Runs on the Mac. No Stick, no cable, no pairing. <<<

A card names a group rather than a single device, so a color sensor and a
controller tapped with the same card both show up here. Nothing is connected
to, so this does not use up either device's one connection slot -- you can
watch a controller while it is busy driving a motor.

Run it, then wave things in front of the color sensor and push the sticks.

By default it finds whatever card is advertising and watches that, so there is
nothing to fill in. Set CARD_SERIAL below only if more than one card is in the
room and you want a particular one.
'''

import os
import sys

# lelib.py and pico_lelib.py live in the repo root, two levels up.
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..')))

import time

import lelib

# ── which card to watch ───────────────────────────────────────────────────
# None means "whatever is out there", which is the usual case and saves
# getting the numbers wrong. Serials are handed out per color, so if you do
# set these, set both: RED#1126 and BLUE#1126 are different cards.
CARD_SERIAL = None       # e.g. 6055
CARD_COLOR = None        # e.g. 6 for purple; see lelib.md for the numbers

COLOR_NAMES = {0: 'No color', 1: 'Red', 2: 'Yellow', 3: 'Blue', 4: 'Teal',
               5: 'Green', 6: 'Purple', 7: 'White', 8: 'Magenta', 9: 'Orange',
               10: 'Azure'}


def card_name(color, serial):
    return '{} #{}'.format(COLOR_NAMES.get(color, color), serial)


def pick_card():
    '''The card to watch: the one configured, or whatever is advertising.

    Looking first is what turns "nothing happens" into a useful message. A
    watch that shows nothing is nearly always a card number matching nothing
    on the air, rather than a device that is switched off.
    '''
    print('listening for cards...')
    cards = lelib.find_cards(timeout=5.0)

    if not cards:
        print('Nothing is broadcasting at all. Check the devices are switched '
              'on, and that a card has been tapped on them.')
        return None, None

    for card in cards:
        print('  {}  ({})'.format(
            card_name(card['color'], card['serial']), card['device']))

    if CARD_SERIAL is None:
        first = cards[0]
        return first['serial'], first['color']

    for card in cards:
        if card['serial'] == CARD_SERIAL and CARD_COLOR in (None, card['color']):
            return CARD_SERIAL, CARD_COLOR

    print('\nNone of those is {} -- watching for it anyway, but nothing will '
          'appear until it does.'.format(card_name(CARD_COLOR, CARD_SERIAL)))
    return CARD_SERIAL, CARD_COLOR


def main():
    serial, color = pick_card()
    if serial is None:
        return

    print('\nwatching {} -- Ctrl-C to stop\n'.format(card_name(color, serial)))
    while True:
        reading = lelib.read_sensor(serial, color, timeout=1.0)

        if reading['color'] is None:
            sensor = 'no sensor heard'
        else:
            sensor = COLOR_NAMES.get(reading['color'], '?')

        if reading['controller'] is None:
            sticks = 'no controller heard'
        else:
            left, right = reading['controller']
            sticks = 'L {:+d}  R {:+d}'.format(left, right)

        print('{:<16}  {}'.format(sensor, sticks))
        time.sleep(0.1)


try:
    main()
except KeyboardInterrupt:
    print('\nstopped')
