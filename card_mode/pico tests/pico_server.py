'''
pico_server — runs on the microcontroller and does what the Mac tells it to.

  >>> Runs ON the board (Pico W or ESP32 with BLE), NOT on the Mac. <<<

The Mac drives this over USB serial with pico_lelib.py. It speaks one JSON
object per line in each direction:

    {"cmd": "ping"}                          -> {"ok": true, "id": "pico_lelib", ...}
    {"cmd": "card", "color": 6, "serial": 1126, "b2": 243, "b7": 72}
    {"cmd": "run", "speed": 45}              -> {"ok": true, "speed": 33}
    {"cmd": "tank", "left": 100, "right": 0} -> {"ok": true, "left": 100, "right": 0}
    {"cmd": "tank_v04", "left": 100, "right": 0}  -- continuous speed, see picolib.py
    {"cmd": "run_time", "speed": 50, "seconds": 2}
    {"cmd": "stop"}
    {"cmd": "status"}

Between commands it keeps re-broadcasting the current beacon, because a motor
that stops hearing fresh packets gives up. That is why this is a server loop
and not a one-shot script.

Install: copy this and picolib.py to the board, then run this file. pico_lelib
on the Mac can do both for you -- see pico_lelib.install().

Nothing here may print anything that is not a JSON reply: stdout IS the
protocol, and stray output would corrupt it.
'''

import json
import select
import sys

import picolib

PROTOCOL_ID = 'pico_lelib'
PROTOCOL_VERSION = 1

# How long to wait for a command before topping up the broadcast instead.
IDLE_POLL_MS = 40


class Server(object):
    def __init__(self):
        self.card = None
        self.motor = None
        self.broadcasting = False

    # ── commands ──────────────────────────────────────────────────────
    def do_ping(self, msg):
        return {'id': PROTOCOL_ID, 'version': PROTOCOL_VERSION,
                'ready': self.motor is not None}

    def do_card(self, msg):
        '''Adopt a card. Any previous broadcast stops first.'''
        if self.motor is not None:
            self._quiet()
            self.motor.close()
            self.motor = None
        self.card = picolib.Card(color=msg['color'], serial=msg['serial'],
                                 b2=msg['b2'], b7=msg['b7'])
        self.motor = picolib.Motor(self.card)
        self._quiet()
        return {'color': self.card.color, 'serial': self.card.serial}

    def do_run(self, msg):
        motor = self._require_card()
        speed = motor.set_speed(msg['speed'])
        self.broadcasting = True
        return {'speed': speed}

    def do_tank(self, msg):
        motor = self._require_card()
        left, right = motor.set_tank(msg['left'], msg['right'])
        self.broadcasting = True
        return {'left': left, 'right': right}

    def do_tank_v04(self, msg):
        '''Continuous per-wheel speed under device type 0x04 -- see picolib.Motor.set_tank_v04.'''
        motor = self._require_card()
        left, right = motor.set_tank_v04(msg['left'], msg['right'])
        self.broadcasting = True
        return {'left': left, 'right': right}

    def do_run_time(self, msg):
        motor = self._require_card()
        speed = motor.set_speed(msg['speed'])
        self.broadcasting = True
        motor.drive(msg['seconds'])
        self._quiet()
        return {'speed': speed, 'seconds': msg['seconds']}

    def do_stop(self, msg):
        self._require_card()
        self._quiet()
        return {}

    def do_status(self, msg):
        return {'card': repr(self.card) if self.card else None,
                'broadcasting': self.broadcasting}

    # ── plumbing ──────────────────────────────────────────────────────
    def _require_card(self):
        if self.motor is None:
            raise ValueError('no card set; send the "card" command first')
        return self.motor

    def _quiet(self):
        if self.motor is not None:
            self.motor.stop()
        self.broadcasting = False

    def handle(self, line):
        try:
            msg = json.loads(line)
            handler = getattr(self, 'do_' + msg['cmd'], None)
            if handler is None:
                raise ValueError('unknown command {}'.format(msg.get('cmd')))
            reply = handler(msg)
            reply['ok'] = True
        except Exception as e:
            reply = {'ok': False, 'error': '{}: {}'.format(type(e).__name__, e)}
        return reply

    def serve(self):
        poller = select.poll()
        poller.register(sys.stdin, select.POLLIN)
        while True:
            if poller.poll(IDLE_POLL_MS):
                line = sys.stdin.readline()
                if not line:
                    continue
                line = line.strip()
                if not line:
                    continue
                print(json.dumps(self.handle(line)))
            elif self.broadcasting:
                # Idle: keep the current beacon fresh so the motor keeps going.
                self.motor.refresh()


def main():
    try:
        Server().serve()
    except KeyboardInterrupt:
        pass


main()
