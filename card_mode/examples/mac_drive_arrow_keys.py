'''
Drive any double motor tapped with a purple card, using the arrow keys.

  >>> Runs on the Mac, with the M5StickS3 (or a Pico W) plugged into USB. <<<

Hold Up/Down to drive forward/reverse, Left/Right to spin in place, and hold
two at once (e.g. Up+Right) to curve -- the same throttle/steer mix
MOTOR_BROADCAST_RECIPE.md describes for a from-scratch sender:

    left  = throttle + steer
    right = throttle - steer

Release the keys and the motor stops within DECAY_MS: a terminal only tells
us when a key goes down, never when it comes up, so "still held" here means
"an event for it arrived recently." q or Ctrl-C quits.

── USE_V04 ────────────────────────────────────────────────────────────────
Drives over device type 0x04 by default -- continuous per-wheel speed,
confirmed live against a real Double Motor (see ../Card_mode.md, "A second
device type, byte0 = 0x04: confirmed"), rather than 0x03's 7 discrete
speeds. If your motors are mounted the other way around from this rig,
picolib.Motor.set_tank_v04 negates the wrong wheel and steering will feel
backwards -- flip which side it negates there. Set USE_V04 = False to use
the 0x03 controller-style beacon instead.

── The card's tokens ────────────────────────────────────────────────────
You do not need the physical card in your hand -- only its color, serial,
and the b2/b7 tokens a motor validates. CARD_SERIAL/B2/B7 below are
PURPLE #6055's, already cracked in Card_mode.md (RFID UID
04:B1:C8:82:87:1F:90). For a different card, get its tokens with:

    python3 ../card_hash.py <its RFID UID>          # tap it once, compute
    python3 -c "import cardlib; print(cardlib.find_cards())"   # or read serial off the air

and set CARD_SERIAL/B2/B7 to match -- or pass b2=None, b7=None to connect()
below to scan the air for them instead (needs a controller or color sensor
carrying that card switched on and nearby; the motor itself never
advertises).

First time only, and again any time picolib.py/pico_server.py change:
    import pico_lelib; pico_lelib.install()
'''

import os
import select
import sys
import termios
import time
import tty

# lelib.py and pico_lelib.py live in the repo root, two levels up.
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..')))

import pico_lelib

# ── your card ─────────────────────────────────────────────────────────────
CARD_COLOR = 6           # le.LEGO_COLOR_PURPLE; see lelib.md for the numbers
CARD_SERIAL = 6055       # PURPLE #6055 -- set this to your purple card's serial
B2 = 0xdb                # that card's tokens, from Card_mode.md / card_hash.py
B7 = 0x2c                # set both to None to scan the air for them instead

USE_V04 = True             # continuous speed, confirmed -- see the docstring above

SPEED = 70                # -100..100, throttle/steer magnitude at full deflection

# A terminal never reports key-up, only discrete keypresses -- including
# macOS's own auto-repeat. Holding a key sends one escape sequence, THEN A
# GAP while macOS waits out its own "Delay Until Repeat" setting (System
# Settings > Keyboard) before the repeat stream starts, then a steady stream
# every ~30-50ms. DECAY_MS has to outlast that gap, or the motor sees the
# hold as "released" partway through and stops until the repeats catch up --
# a mid-hold pause, not a bug in the drive logic. 700ms clears most default
# and even slow keyboard settings; it costs a similar lag on genuine release.
# If your Mac's repeat delay is fast, you can lower this for a snappier stop.
DECAY_MS = 700
POLL_S = 0.05              # how often to check for a decayed key

# Arrow keys arrive as a 3-byte escape sequence in a raw terminal.
_ARROWS = {'\x1b[A': 'up', '\x1b[B': 'down', '\x1b[C': 'right', '\x1b[D': 'left'}


class _RawTerminal(object):
    '''cbreak mode: keys arrive immediately, unechoed, no Enter needed.'''

    def __enter__(self):
        self.fd = sys.stdin.fileno()
        self.old = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)
        return self

    def __exit__(self, *exc_info):
        termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old)


def _read_keys(timeout):
    '''Names ('up'/'down'/'left'/'right'/'quit') seen on stdin within timeout.'''
    keys = []
    if not select.select([sys.stdin], [], [], timeout)[0]:
        return keys
    data = os.read(sys.stdin.fileno(), 32).decode(errors='ignore')
    i = 0
    while i < len(data):
        for seq, name in _ARROWS.items():
            if data.startswith(seq, i):
                keys.append(name)
                i += len(seq)
                break
        else:
            if data[i] == 'q':
                keys.append('quit')
            i += 1
    return keys


def main():
    if not pico_lelib.check_pico():
        return

    motor = pico_lelib.doubleMotor()
    print('looking for card {}/{}...'.format(CARD_COLOR, CARD_SERIAL))
    motor.connect(CARD_SERIAL, card_color=CARD_COLOR, b2=B2, b7=B7)
    print('connected ({}). Arrow keys to drive, q to quit.'.format(
        'device type 0x04, continuous' if USE_V04 else 'device type 0x03, 7-step'))

    last_seen = {'up': 0.0, 'down': 0.0, 'left': 0.0, 'right': 0.0}
    sent = (None, None)

    try:
        with _RawTerminal():
            while True:
                now = time.time()
                for name in _read_keys(POLL_S):
                    if name == 'quit':
                        return
                    last_seen[name] = now

                held = {n for n, t in last_seen.items() if now - t < DECAY_MS / 1000.0}
                throttle = (1 if 'up' in held else 0) - (1 if 'down' in held else 0)
                steer = (1 if 'right' in held else 0) - (1 if 'left' in held else 0)
                left = max(-100, min(100, (throttle + steer) * SPEED))
                right = max(-100, min(100, (throttle - steer) * SPEED))

                if (left, right) != sent:
                    if USE_V04:
                        motor.tank_v04(left, right)
                    else:
                        motor.tank(left, right)
                    sent = (left, right)
    finally:
        motor.stop()
        pico_lelib.close_link()
        print('\nstopped')


main()
