'''
Run a Stick program from the Mac and watch its print() output in your terminal.

  >>> Runs on the Mac, with the M5StickS3 plugged into USB. <<<

Saves the copy-to-the-board-and-open-Thonny round trip: point it at any
stick_*.py file and it runs there while the output comes back here. Ctrl-C
stops the program on the board as well as here.

    python3 mac_run_on_stick.py stick_read_card.py
    python3 mac_run_on_stick.py stick_tap_to_drive.py

In VS Code you can just press Run. The Run button passes no arguments, so with
none this runs EXAMPLE below -- change that line to pick a different one.

The program runs from the Mac's copy of the file, so edit, re-run, and you are
testing what you just typed. The libraries it imports -- picolib, lego_card,
stick_ui -- do have to be on the board already:

    import pico_lelib; pico_lelib.install()

Nothing is written to the board here, and no main.py is involved, so the Stick
goes back to doing whatever it did before the moment the program stops.
'''

import os
import sys

# lelib.py and pico_lelib.py live in the repo root, two levels up.
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..')))

import pico_lelib

# ── which example to run ──────────────────────────────────────────────────
# Used when no filename is given on the command line, which is what happens
# when you press Run in VS Code. Change this to run a different one.
EXAMPLE = 'stick_read_card.py'


def run_on_stick(path, port=None):
    '''Run a local file on the board, streaming its output to the terminal.'''
    with open(path) as handle:
        source = handle.read()

    # ensure_server=False: this needs the bare REPL, not the JSON server.
    link = pico_lelib.PicoLink(port=port, ensure_server=False)
    print('running {} on {} ({})'.format(
        os.path.basename(path), link.port, link.description))
    print('-' * 60)
    try:
        link.run_source(source)
    finally:
        print('-' * 60)
        link.close()


def find_example(name):
    '''The file to run, looked up next to this script if need be.

    VS Code runs from the workspace root rather than this folder, so a bare
    name like "stick_read_card.py" has to be resolved relative to this file
    as well as to wherever you happen to be.
    '''
    if os.path.exists(name):
        return name
    beside = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
    if os.path.exists(beside):
        return beside
    return None


def main(argv):
    if argv and argv[0] in ('-h', '--help'):
        print(__doc__.strip())
        return 0
    if len(argv) > 1:
        print('One file at a time, please. Got: {}'.format(' '.join(argv)))
        return 1

    # No argument means the VS Code Run button, so fall back to EXAMPLE.
    name = argv[0] if argv else EXAMPLE
    path = find_example(name)
    if path is None:
        here = os.path.dirname(os.path.abspath(__file__))
        available = sorted(f for f in os.listdir(here) if f.startswith('stick_'))
        print('No such file: {}'.format(name))
        print('Stick examples here: {}'.format(', '.join(available) or 'none'))
        return 1

    try:
        run_on_stick(path)
    except pico_lelib.PicoNotConnected as e:
        print('NOT CONNECTED\n{}'.format(e))
        return 1
    except pico_lelib.PicoNotReady as e:
        print('BOARD NOT USABLE\n{}'.format(e))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
