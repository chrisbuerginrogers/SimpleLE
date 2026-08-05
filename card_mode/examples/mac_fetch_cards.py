'''
Install the card logger on the Stick, and fetch the cards it has logged.

  >>> Runs on the Mac, with the M5StickS3 plugged into USB. <<<

    python3 mac_fetch_cards.py            # copy card_taps.csv here
    python3 mac_fetch_cards.py --install  # put stick_log_cards.py on as main.py

--install is the one-off setup: it copies the board libraries over and then
installs stick_log_cards.py as main.py, so the Stick starts logging on its own
whenever it is switched on -- no laptop, no cable, tap cards anywhere.

With no arguments it just copies the log back, to card_mode/card_taps.csv next
to the older cards.csv. The file on the Stick is left alone, so fetching twice
is safe and the Stick keeps skipping cards it already has.

Each row is one card: its RFID UID, its color and serial, and all twelve bytes
of the FD02 service data broadcast under it. That pairing is what the open
b2/b7 question in ../CLAUDE.md needs -- see stick_log_cards.py for how to tap.
'''

import os
import sys

# pico_lelib.py lives in the repo root, two levels up.
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..')))

import pico_lelib

HERE = os.path.dirname(os.path.abspath(__file__))

BOARD_LOG = 'card_taps.csv'
LOGGER = os.path.join(HERE, 'stick_log_cards.py')

#: Alongside cards.csv, which is the same kind of data from the earlier
#: over-the-air-only harvest.
LOCAL_COPY = os.path.abspath(os.path.join(HERE, '..', BOARD_LOG))


def install():
    '''Put the libraries and the logger on the Stick.'''
    pico_lelib.install()
    pico_lelib.install_main(LOGGER)
    print()
    print('Unplug the Stick and start tapping. Fetching later does not stop '
          'it -- the board is restarted on the way out.')
    return 0


def fetch():
    '''Copy the log off the Stick and say what is in it.'''
    try:
        data = pico_lelib.fetch_file(BOARD_LOG, LOCAL_COPY)
    except FileNotFoundError as e:
        print('NOTHING LOGGED YET\n{}'.format(e))
        return 1

    rows = [line for line in data.decode().splitlines()
            if line.strip() and not line.startswith('n,')]
    print('{} card(s) -> {}'.format(len(rows), LOCAL_COPY))

    # The colors, so a glance says whether the sample is broad enough to be
    # worth attacking the hash with.
    counts = {}
    for row in rows:
        fields = row.split(',')
        if len(fields) > 2:
            counts[fields[2]] = counts.get(fields[2], 0) + 1
    for color in sorted(counts):
        print('  {:<8} {}'.format(color, counts[color]))
    return 0


def main(argv):
    if argv and argv[0] in ('-h', '--help'):
        print(__doc__.strip())
        return 0
    try:
        if argv and argv[0] == '--install':
            return install()
        if argv:
            print('Unknown option {}. Use --install, or no arguments to '
                  'fetch.'.format(argv[0]))
            return 1
        return fetch()
    except pico_lelib.PicoNotConnected as e:
        print('NOT CONNECTED\n{}'.format(e))
        return 1
    except pico_lelib.PicoNotReady as e:
        print('BOARD NOT USABLE\n{}'.format(e))
        return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
