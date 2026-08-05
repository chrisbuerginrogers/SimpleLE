'''
pico_lelib — write lelib-style Python on your Mac, have a microcontroller do
the radio.

    from pico_lelib import doubleMotor

    motor = doubleMotor()
    motor.connect(6055, card_color=le.LEGO_COLOR_PURPLE)
    motor.set_speed(45)
    motor.run()
    motor.stop()

Why this exists: motors can be driven with no connection and no pairing, by
broadcasting the beacon a controller sends. macOS cannot transmit a custom BLE
advertisement at all, so the broadcast has to come from a microcontroller.
This library keeps the lelib syntax on the Mac and ships each command down the
USB serial cable to the board, which does the broadcasting.

    Mac                            board (MicroPython)
    ---                            -------------------
    pico_lelib.py --- serial --->  pico_server.py -> picolib.py -> BLE

Despite the name it is not Pico-specific: any MicroPython board with a BLE
radio works. Tested on an ESP32-S3; a Pico W uses the same MicroPython API.

── First run ────────────────────────────────────────────────────────────────
    import pico_lelib
    pico_lelib.install()      # copy the two board files over (once)
    pico_lelib.check_pico()   # confirm it is all working

check_pico() distinguishes the three things that go wrong: no board plugged in,
a board that is not running the server, and a board that is ready.

After install(), nothing else is needed -- connecting starts the server over
the board's REPL each time. No main.py is written, so the board still does
whatever it did before when you power it up on its own.

── What is here, and what cannot be ─────────────────────────────────────────
The broadcast carries two joystick positions, each with seven steps, and
nothing else. There is no acknowledgement and no feedback, so anything in
lelib that depends on the motor reporting back is impossible this way and is
deliberately absent rather than faked:

    spin(), move_steps(), turn_left(), turn_right()   need rotation feedback
    set_speed_left/right()                           no per-side speed setting
    on_button_press(), set_update_rate()             need a GATT connection

Use lelib for those -- it connects properly and can do all of it.

Reading is the other way round: the Mac can already listen, so colorSensor and
controller here read the air directly through cardlib.read_sensor() and never
involve the board at all.
'''

import json
import sys
import os
import time

import serial
from serial.tools import list_ports

import cardlib
from legoeducation.color_map import _firmware_to_app

# USB vendor IDs of boards that might be running MicroPython. A board is only
# a candidate if it matches -- this is what stops us talking to a Bluetooth
# serial port or a debug console.
BOARD_VENDOR_IDS = {
    0x2E8A: 'Raspberry Pi (Pico)',
    0x303A: 'Espressif (ESP32)',
    0x10C4: 'Silicon Labs CP210x',
    0x1A86: 'WCH CH340',
    0x0403: 'FTDI',
}

PROTOCOL_ID = 'pico_lelib'
PROTOCOL_VERSION = 1

SERIAL_BAUD = 115200
REPLY_TIMEOUT = 5.0
TOKEN_SCAN_TIMEOUT = 6.0

#: Everything install() puts on the board: what pico_lelib itself needs, plus
#: what the stick_*.py examples need so one install covers both.
BOARD_FILES = ('picolib.py', 'pico_server.py', 'lego_card.py', 'stick_ui.py')

#: The subset the serial protocol actually depends on. start_server() checks
#: only these, so a board missing the example libraries still works here.
SERVER_FILES = ('picolib.py', 'pico_server.py')
_BOARD_SOURCE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 'card_mode', 'pico tests')


class PicoNotConnected(Exception):
    '''No board could be found on any serial port.'''


class PicoNotReady(Exception):
    '''A board is plugged in but is not running the server.'''


class CardNotFound(Exception):
    '''The card's tokens could not be read off the air.'''


# ── finding the board ────────────────────────────────────────────────────

def find_board():
    '''(port, description) of the first likely board. Raises PicoNotConnected.'''
    for port in list_ports.comports():
        if port.vid in BOARD_VENDOR_IDS:
            return port.device, '{} ({})'.format(
                port.product or port.description, BOARD_VENDOR_IDS[port.vid])
    seen = ['{} [{}]'.format(p.device, hex(p.vid) if p.vid else 'no vid')
            for p in list_ports.comports()]
    raise PicoNotConnected(
        'No microcontroller found on any serial port.\n'
        'Plug the board in with a DATA cable -- charge-only cables power the '
        'board but carry no serial.\n'
        'Serial ports seen right now: {}'.format(', '.join(seen) or 'none'))


# ── serial link ──────────────────────────────────────────────────────────

class PicoLink(object):
    '''One serial conversation with the board.

    Speaks two protocols over the same wire: MicroPython's raw REPL, used to
    install files and start the server, and then JSON lines once the server is
    running.
    '''

    def __init__(self, port=None, autostart=True, ensure_server=True,
                 timeout=REPLY_TIMEOUT):
        if port is None:
            port, self.description = find_board()
        else:
            self.description = 'port given explicitly'
        self.port = port
        self.timeout = timeout
        self._buf = b''
        try:
            self._serial = serial.Serial(port, SERIAL_BAUD, timeout=0.2)
        except serial.SerialException as e:
            raise PicoNotReady(
                'Found a board at {} but could not open it: {}\n'
                'Another program is probably holding the port -- close Thonny, '
                'the Arduino IDE, or any open serial monitor.'.format(port, e))
        time.sleep(0.3)
        self._serial.reset_input_buffer()

        # install() needs a link before the server exists, so it opts out.
        if ensure_server and not self._server_answers():
            if not autostart:
                raise PicoNotReady(
                    'The board at {} is not running pico_server.py.\n'
                    'Call pico_lelib.start_server(), or construct PicoLink '
                    'with autostart=True.'.format(port))
            self.start_server()

    # ── low-level reading ─────────────────────────────────────────────
    def _read_until(self, token, timeout):
        '''Read up to and including token, keeping anything past it buffered.'''
        deadline = time.time() + timeout
        while True:
            idx = self._buf.find(token)
            if idx != -1:
                end = idx + len(token)
                out, self._buf = self._buf[:end], self._buf[end:]
                return out
            if time.time() > deadline:
                raise TimeoutError('no {!r} within {:.1f}s'.format(token, timeout))
            self._buf += self._serial.read(self._serial.in_waiting or 1)

    def _read_line(self, timeout):
        return self._read_until(b'\n', timeout)

    # ── raw REPL (MicroPython's own control channel) ───────────────────
    def _enter_raw_repl(self):
        '''Interrupt whatever is running and get a raw REPL prompt.

        Note this stops any program already running on the board.
        '''
        self._serial.write(b'\r\x03\x03')      # Ctrl-C twice
        time.sleep(0.2)
        self._serial.reset_input_buffer()
        self._buf = b''
        self._serial.write(b'\r\x01')          # Ctrl-A
        try:
            self._read_until(b'raw REPL; CTRL-B to exit\r\n>', timeout=3.0)
        except TimeoutError:
            raise PicoNotReady(
                'The board at {} ({}) did not respond as a MicroPython board.\n'
                'It may be running other firmware (Arduino, CircuitPython) or '
                'may not be a MicroPython board at all.'.format(
                    self.port, self.description))

    def _exec_raw(self, code, timeout=10.0):
        '''Run code via the raw REPL and return (stdout, stderr).'''
        self._serial.write(code.encode() + b'\x04')
        self._read_until(b'OK', timeout)
        out = self._read_until(b'\x04', timeout)[:-1]
        err = self._read_until(b'\x04', timeout)[:-1]
        self._read_until(b'>', timeout)
        return out.decode(errors='replace'), err.decode(errors='replace')

    def _exit_raw_repl(self):
        self._serial.write(b'\r\x02')
        time.sleep(0.1)

    # ── the JSON protocol ─────────────────────────────────────────────
    def _server_answers(self):
        '''True if pico_server.py is already running and speaking JSON.'''
        try:
            reply = self.command('ping', timeout=1.5)
        except Exception:
            return False
        return reply.get('id') == PROTOCOL_ID

    def command(self, cmd, timeout=None, **params):
        '''Send one command and return its reply dict.'''
        params['cmd'] = cmd
        self._serial.write((json.dumps(params) + '\r\n').encode())
        self._serial.flush()

        deadline = time.time() + (timeout or self.timeout)
        while time.time() < deadline:
            try:
                raw = self._read_line(timeout=max(0.1, deadline - time.time()))
            except TimeoutError:
                break
            try:
                reply = json.loads(raw.decode().strip())
            except (ValueError, UnicodeDecodeError):
                continue          # REPL echo or a traceback, not our protocol
            if not isinstance(reply, dict) or 'ok' not in reply:
                continue
            if not reply['ok']:
                raise RuntimeError('board refused {!r}: {}'.format(
                    cmd, reply.get('error', 'no reason given')))
            return reply

        raise PicoNotReady(
            'The board at {} did not reply to {!r} in time.'.format(self.port, cmd))

    # ── setup ─────────────────────────────────────────────────────────
    def install(self):
        '''Copy picolib.py and pico_server.py onto the board.'''
        self._enter_raw_repl()
        copied = []
        for name in BOARD_FILES:
            source = os.path.join(_BOARD_SOURCE_DIR, name)
            with open(source, 'rb') as handle:
                data = handle.read()
            self._exec_raw('f = open({!r}, "wb")'.format(name))
            for i in range(0, len(data), 256):
                self._exec_raw('f.write({!r})'.format(data[i:i + 256]))
            self._exec_raw('f.close()')
            out, err = self._exec_raw(
                'import os; print(os.stat({!r})[6])'.format(name))
            if err.strip():
                raise PicoNotReady('Could not write {} to the board: {}'.format(
                    name, err.strip()))
            written = int(out.strip())
            if written != len(data):
                raise PicoNotReady(
                    '{} copied badly: {} bytes on the board, {} expected.'.format(
                        name, written, len(data)))
            copied.append((name, written))
        self._exit_raw_repl()
        return copied

    def start_server(self):
        '''Start pico_server.py on the board over the raw REPL.

        The server is started rather than installed as main.py, so the board
        goes back to its normal behavior next time you power it up alone.
        '''
        self._enter_raw_repl()
        out, err = self._exec_raw('import os; print(os.listdir())')
        missing = [f for f in SERVER_FILES if repr(f)[1:-1] not in out]
        if missing:
            raise PicoNotReady(
                'The board at {} is missing {}.\n'
                'Run pico_lelib.install() once to copy the board files over.'.format(
                    self.port, ' and '.join(missing)))

        # Executing this never returns -- from here the board's stdout is the
        # JSON protocol, so we only wait for the raw REPL's "OK" acknowledgement.
        self._serial.write(b'exec(open("pico_server.py").read())\x04')
        try:
            self._read_until(b'OK', timeout=5.0)
        except TimeoutError:
            raise PicoNotReady(
                'The board at {} did not start pico_server.py.'.format(self.port))

        if not self._server_answers():
            raise PicoNotReady(
                'pico_server.py started on the board at {} but is not '
                'answering. Re-run pico_lelib.install() -- picolib.py on the '
                'board may be out of date.'.format(self.port))

    def run_source(self, source, on_output=None):
        '''Run source on the board, streaming its print() output back.

        Blocks until the program ends or Ctrl-C. Anything the board prints is
        passed to on_output a chunk at a time (default: straight to stdout).

        Used for running the stick_*.py examples from the Mac. It bypasses the
        JSON server entirely -- the board's stdout is the program's output, not
        a protocol -- so do not mix this with command() on the same link.
        '''
        if on_output is None:
            def on_output(text):
                sys.stdout.write(text)
                sys.stdout.flush()

        self._enter_raw_repl()
        self._serial.write(source.encode() + b'\x04')
        self._read_until(b'OK', timeout=10.0)

        pending = self._buf
        self._buf = b''
        try:
            while True:
                if pending:
                    chunk, pending = pending, b''
                else:
                    chunk = self._serial.read(self._serial.in_waiting or 1)
                if not chunk:
                    continue
                # The board marks the end of the program with \x04, then sends
                # any traceback, another \x04, and the raw-REPL prompt.
                if b'\x04' in chunk:
                    head, _, tail = chunk.partition(b'\x04')
                    on_output(head.decode(errors='replace'))
                    trailer = tail + self._serial.read(self._serial.in_waiting or 0)
                    trailer = trailer.replace(b'\x04', b'').replace(b'>', b'', 1)
                    if trailer.strip():
                        on_output('\n' + trailer.decode(errors='replace').strip() + '\n')
                    return
                on_output(chunk.decode(errors='replace'))
        except KeyboardInterrupt:
            # Ctrl-C on the Mac should stop the program on the board too.
            self._serial.write(b'\r\x03\x03')
            time.sleep(0.3)
            self._serial.read(self._serial.in_waiting or 0)
            on_output('\n[stopped]\n')

    def close(self):
        try:
            self._serial.write(b'\r\x03\x03')     # stop the server
            self._serial.close()
        except Exception:
            pass


_link = None


def get_link():
    '''The shared connection to the board, opening it on first use.'''
    global _link
    if _link is None:
        _link = PicoLink()
    return _link


def close_link():
    '''Stop the server and close the serial connection.'''
    global _link
    if _link is not None:
        _link.close()
        _link = None


def install(port=None):
    '''Copy the board files over. Run this once per board. Prints what it did.

    This writes two files to the board and nothing else -- no main.py, so the
    board behaves exactly as before when you power it up on its own.
    '''
    close_link()
    link = PicoLink(port=port, ensure_server=False)
    print('Found {} at {}'.format(link.description, link.port))
    try:
        for name, size in link.install():
            print('  copied {} ({} bytes)'.format(name, size))
    finally:
        link.close()
    print('Done. Now call pico_lelib.check_pico().')


def start_server(port=None):
    '''Start the server on the board, without doing anything else.'''
    close_link()
    link = PicoLink(port=port)
    print('pico_server.py running on {}'.format(link.port))
    return link


def check_pico():
    '''Report whether a usable board is connected. Prints and returns a bool.

    Separates the three cases: no board, board but not running the server, and
    ready to go.
    '''
    try:
        link = get_link()
    except PicoNotConnected as e:
        print('NOT CONNECTED\n{}'.format(e))
        return False
    except PicoNotReady as e:
        print('CONNECTED BUT NOT READY\n{}'.format(e))
        return False
    status = link.command('status')
    print('Ready: pico_server.py v{} on {} ({})'.format(
        PROTOCOL_VERSION, link.port, link.description))
    print('  card: {}'.format(status.get('card') or 'none set yet'))
    return True


check_board = check_pico


# ── reading a card's tokens off the air ──────────────────────────────────

def find_card(card_serial, card_color=None, timeout=TOKEN_SCAN_TIMEOUT):
    '''Listen for a card and return (card_color, b2, b7).

    A motor validates bytes 2 and 7 of the beacon. They are a per-card token
    that cannot be computed from the color and serial, so they have to be
    read off a device already carrying the card. This is the one part of the
    job the Mac is better at than the board, since it can already listen.

    The tokens are only in a *sender's* broadcast, so a controller or color
    sensor tapped with this card must be switched on and nearby. A motor's own
    advertisement does not carry them.
    '''
    found = {}

    def on_advertisement(device, adv):
        if found:
            return
        for uuid, payload in (adv.service_data or {}).items():
            if uuid.lower() != cardlib._FD02_UUID or len(payload) < 8:
                continue
            if not cardlib._card_matches(payload, card_serial, card_color):
                continue
            found['color'] = _firmware_to_app(cardlib._signed_byte(payload[1]))
            found['b2'] = payload[2]
            found['b7'] = payload[7]

    async def scan():
        scanner = cardlib.BleakScanner(detection_callback=on_advertisement)
        await scanner.start()
        try:
            deadline = time.time() + timeout
            while time.time() < deadline and not found:
                await cardlib.asyncio.sleep(0.1)
        finally:
            await scanner.stop()

    cardlib._run(scan())

    if not found:
        card = card_serial if card_color is None else '{}/{}'.format(
            card_color, card_serial)
        raise CardNotFound(
            'Could not read the tokens for card {} in {:.0f}s.\n'
            'A controller or color sensor tapped with this card has to be '
            'switched on and nearby -- the tokens are only in what those '
            'broadcast, not in what a motor broadcasts.'.format(card, timeout))
    return found['color'], found['b2'], found['b7']


# ── motors ───────────────────────────────────────────────────────────────

SPEED_STEPS = cardlib.SPEED_STEPS
round_speed = cardlib.round_speed


class _BroadcastMotor(object):
    '''Shared behavior: hold a speed, broadcast it on run(), stop on stop().

    Speed works the way it does in lelib -- set_speed() stores it and run()
    starts moving -- even though the broadcast has no separate notion of a
    speed setting. The stored speed is simply what run() sends.
    '''

    def __init__(self):
        self.connected = False
        self.card_serial = None
        self.card_color = None
        self.speed = 100
        self._link = None

    def connect(self, card_serial, card_color=None):
        '''Point the board at the motor holding this card.

        Nothing is connected in the Bluetooth sense -- the motor is never
        paired with. This reads the card's tokens off the air, hands them to
        the board, and checks the board is ready.
        '''
        link = get_link()
        color, b2, b7 = find_card(card_serial, card_color)
        link.command('card', color=color, serial=card_serial, b2=b2, b7=b7)
        self._link = link
        self.card_serial = card_serial
        self.card_color = color
        self.connected = True

    def _require_connection(self):
        if not self.connected:
            raise ConnectionError(
                'Not connected. Call connect(card_serial, card_color=...) first.')
        return self._link

    def set_speed(self, speed):
        '''Store the speed for later run() calls, rounded to SPEED_STEPS.

        Returns the speed actually stored. The seven steps mirror the seven
        positions a real joystick reports; there is nothing finer on the air.
        '''
        self.speed = round_speed(speed)
        return self.speed

    def run(self):
        '''Start moving at the stored speed, and keep going until stop().'''
        link = self._require_connection()
        return link.command('run', speed=self.speed)['speed']

    def run_time(self, time_ms=2000):
        '''Move at the stored speed for this many milliseconds, then stop.'''
        link = self._require_connection()
        seconds = time_ms / 1000.0
        # The board is busy broadcasting for the whole run, so allow for it.
        link.command('run_time', speed=self.speed, seconds=seconds,
                     timeout=seconds + REPLY_TIMEOUT)

    def stop(self):
        '''Stop the motor and go quiet.'''
        link = self._require_connection()
        link.command('stop')


class singleMotor(_BroadcastMotor):
    '''A Single Motor, driven by broadcast.'''


class doubleMotor(_BroadcastMotor):
    '''A Double Motor, driven by broadcast.

    The beacon's two sticks are what a Double Motor uses to steer, so tank
    driving works here. Turning by a number of degrees does not -- that needs
    feedback the broadcast has no room for.
    '''

    def tank(self, left, right):
        '''Drive the two sides at separate speeds, each rounded to SPEED_STEPS.

        Returns the (left, right) speeds actually sent.
        '''
        link = self._require_connection()
        reply = link.command('tank', left=round_speed(left), right=round_speed(right))
        return reply['left'], reply['right']

    def run_left(self, speed=None):
        '''Run only the left side, at the stored speed unless one is given.'''
        return self.tank(self.speed if speed is None else speed, 0)

    def run_right(self, speed=None):
        '''Run only the right side, at the stored speed unless one is given.'''
        return self.tank(0, self.speed if speed is None else speed)


# ── sensors (read on the Mac; the board is not involved) ─────────────────

class _BroadcastReader(object):
    '''A device read passively from its advertisement.

    No connect() in the Bluetooth sense and no board -- the Mac listens to what
    the device broadcasts anyway. Because nothing is connected, this does not
    use up the device's single connection slot.
    '''

    def __init__(self):
        self.connected = False
        self.card_serial = None
        self.card_color = None
        self.timeout = 3.0

    def connect(self, card_serial, card_color=None):
        '''Remember which card to listen for, and check it can be heard.'''
        reading = cardlib.read_sensor(card_serial, card_color, timeout=self.timeout)
        if reading['color'] is None and reading['controller'] is None:
            card = card_serial if card_color is None else '{}/{}'.format(
                card_color, card_serial)
            raise ConnectionError(
                'Nothing broadcasting under card {} was heard in {:.0f}s. '
                'Check the device is switched on and nearby.'.format(
                    card, self.timeout))
        self.card_serial = card_serial
        self.card_color = card_color
        self.connected = True

    def _read(self):
        if not self.connected:
            raise ConnectionError(
                'Not connected. Call connect(card_serial, card_color=...) first.')
        return cardlib.read_sensor(self.card_serial, self.card_color,
                                 timeout=self.timeout)


class colorSensor(_BroadcastReader):
    '''A Color Sensor, read from its broadcast.

    reflection() is absent on purpose: reflection is not broadcast at all, so
    it genuinely needs lelib and a real connection.
    '''

    _COLOR_NAMES = {
        0: 'No color', 1: 'Red', 2: 'Yellow', 3: 'Blue', 4: 'Teal', 5: 'Green',
        6: 'Purple', 7: 'White', 8: 'Magenta', 9: 'Orange', 10: 'Azure',
    }

    def detect_color(self):
        '''Name of the color the sensor is looking at.

        Black and an empty field of view both read 'No color' -- the sensor
        cannot tell them apart.
        '''
        color = self._read()['color']
        if color is None:
            return 'Unknown'
        return self._COLOR_NAMES.get(color, 'Unknown')

    def color_number(self):
        '''The color as a LEGO_COLOR_* code, or None if nothing was heard.'''
        return self._read()['color']


class controller(_BroadcastReader):
    '''A Controller, read from its broadcast.

    Stick positions here run -3..+3, the seven steps that are actually on the
    air. lelib reports percentages instead, over a real connection.
    '''

    def _sticks(self):
        sticks = self._read()['controller']
        if sticks is None:
            raise ConnectionError(
                'No controller broadcasting under card {} was heard.'.format(
                    self.card_serial))
        return sticks

    def left_position(self):
        return self._sticks()[0]

    def right_position(self):
        return self._sticks()[1]

    def left_up(self):
        return self.left_position() > 0

    def left_down(self):
        return self.left_position() < 0

    def left_released(self):
        return self.left_position() == 0

    def right_up(self):
        return self.right_position() > 0

    def right_down(self):
        return self.right_position() < 0

    def right_released(self):
        return self.right_position() == 0
