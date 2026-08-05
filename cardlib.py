'''
cardlib — talk to LEGO Education hardware by its card, with no connection.

    import cardlib

    cardlib.find_cards()
    # [{'color': 6, 'serial': 6055, 'device': 'color sensor'},
    #  {'color': 6, 'serial': 6055, 'device': 'controller'}]

    cardlib.read_sensor(6055, card_color=6)
    # {'color': 2, 'controller': (0, 0)}

LEGO Education devices continuously broadcast their live state in a BLE
advertisement (service UUID FD02), addressed by the card they were tapped
with. Reading that takes no connect() and no pairing, so it does not use up a
device's single connection slot -- you can watch a controller while a motor is
being driven by it.

── How this differs from lelib ───────────────────────────────────────────────
`lelib` is the simple LEGO library: you make a singleMotor or a colorSensor,
connect() to it, and call methods on it. That is a real Bluetooth connection,
and it can do everything the hardware can do.

Here there is no object and no connection -- you name a *card* and get whatever
is broadcasting under it. That is a strictly smaller set of things (no
reflection, no button presses, no rotation feedback), so the two are kept
apart rather than mixed: if you want the full API, use lelib.

    lelib.py        connect to one device over Bluetooth, do anything
    cardlib.py      listen to what devices broadcast, no connection  (here)
    pico_lelib.py   broadcast commands, via a microcontroller on USB

── Cards are (color, serial), not serial ─────────────────────────────────────
Serials are handed out per color, so RED#1126 and BLUE#1126 are different
cards. Pass card_color whenever you can; leaving it out matches any color
sharing that serial.

The byte map behind all of this, and the evidence for it, is in
card_mode/CLAUDE.md.
'''

import asyncio
import time

from bleak import BleakScanner
from legoeducation.basic_ble import SERVICE_UUID
from legoeducation.color_map import _firmware_to_app

import lelib

_FD02_UUID = SERVICE_UUID.lower()

_DEVICE_TYPE_COLOR_SENSOR = 0x02
_DEVICE_TYPE_CONTROLLER = 0x03

DEVICE_NAMES = {_DEVICE_TYPE_COLOR_SENSOR: 'color sensor',
                _DEVICE_TYPE_CONTROLLER: 'controller'}


def _signed_byte(b):
    return b - 256 if b >= 128 else b


def _signed_nibble(b):
    '''Decode one stick byte from a controller broadcast.

    The motor ignores the high nibble entirely and reads the low one as a
    signed 4-bit value, so this returns exactly what the motor acts on:
    0 stop, +1..+3 forward, -1..-3 reverse. A real controller only ever
    sends those seven states; anything else is out of range and the motor
    treats it as dead.
    '''
    nibble = b & 0x0f
    return nibble - 16 if nibble >= 8 else nibble


def _card_matches(payload, card_serial, card_color):
    '''True if an FD02 payload was broadcast by a device carrying this card.'''
    if len(payload) < 5:
        return False
    if (payload[3] | (payload[4] << 8)) != card_serial:
        return False
    if card_color is None:
        return True
    return _firmware_to_app(_signed_byte(payload[1])) == card_color


def _run(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError(
        'cardlib cannot be called from inside a running event loop; '
        'await the scan yourself instead.')


# ── listening ────────────────────────────────────────────────────────────

def read_sensor(card_serial, card_color=None, timeout=3.0):
    '''Listen for everything broadcasting under one card and report its state.

        >>> read_sensor(6055, card_color=6)
        {'color': 2, 'controller': (0, 0)}

    A card names a *group*, not a single device, so both keys can be filled
    at once if a color sensor and a controller carry the same card.

    Returns a dict:
        'color'      -- the color the sensor is currently looking at, as a
                        LEGO_COLOR_* code (0 = no color). None if no color
                        sensor with this card was heard from.
        'controller' -- (left, right) stick positions, each -3..+3, resting
                        at 0. None if no controller with this card was heard
                        from.

    Listens for `timeout` seconds and returns the most recent reading, so it
    blocks for that long. macOS coalesces advertisements down to a few per
    second, so shorter windows can miss a device entirely.

    Note that black reads the same as an empty field of view -- the sensor
    reports "no color" for both.
    '''
    reading = {'color': None, 'controller': None}

    def on_advertisement(device, adv):
        for uuid, payload in (adv.service_data or {}).items():
            if uuid.lower() != _FD02_UUID or len(payload) < 7:
                continue
            if not _card_matches(payload, card_serial, card_color):
                continue
            # Byte 5 means completely different things on the two devices,
            # so this has to be gated on the device type in byte 0.
            if payload[0] == _DEVICE_TYPE_COLOR_SENSOR:
                reading['color'] = _firmware_to_app(_signed_byte(payload[5]))
            elif payload[0] == _DEVICE_TYPE_CONTROLLER:
                reading['controller'] = (_signed_nibble(payload[6]),
                                         _signed_nibble(payload[5]))

    async def scan():
        scanner = BleakScanner(detection_callback=on_advertisement)
        await scanner.start()
        try:
            await asyncio.sleep(timeout)
        finally:
            await scanner.stop()

    _run(scan())
    return reading


def find_cards(timeout=5.0):
    '''Every card heard broadcasting nearby, without connecting to anything.

        >>> find_cards()
        [{'color': 6, 'serial': 6055, 'device': 'color sensor'},
         {'color': 6, 'serial': 6055, 'device': 'controller'}]

    Use this when read_sensor() comes back empty: it answers "what IS out
    there", which is almost always a card number that does not match the one
    being asked for.

    Only *senders* broadcast this way. A motor does not appear here.

    Listens for `timeout` seconds, so it blocks for that long.
    '''
    found = {}

    def on_advertisement(device, adv):
        for uuid, payload in (adv.service_data or {}).items():
            if uuid.lower() != _FD02_UUID or len(payload) < 7:
                continue
            color = _firmware_to_app(_signed_byte(payload[1]))
            serial = payload[3] | (payload[4] << 8)
            found[(color, serial, payload[0])] = {
                'color': color,
                'serial': serial,
                'device': DEVICE_NAMES.get(payload[0],
                                           'unknown (0x%02x)' % payload[0]),
            }

    async def scan():
        scanner = BleakScanner(detection_callback=on_advertisement)
        await scanner.start()
        try:
            await asyncio.sleep(timeout)
        finally:
            await scanner.stop()

    _run(scan())
    return [found[key] for key in sorted(found)]


# ── speed control by card ────────────────────────────────────────────────
#
# This one does open a real connection, using lelib's motor classes -- it is
# here because it is addressed by card rather than by an object you already
# hold, and because SPEED_STEPS is a broadcast idea that the Pico side shares.

# Seven speed steps, evenly spaced, mirroring the seven positions a
# controller stick can report (-3..+3). Rounding to these keeps a motor
# driven from code feeling like a motor driven from a controller, and
# stops small differences in a typed-in percentage from mattering.
SPEED_STEPS = (-100, -67, -33, 0, 33, 67, 100)

# Motors connected by set_speed(), keyed on (serial, color) so repeat
# calls reuse one connection instead of re-scanning every time.
_connected_motors = {}


def round_speed(speed):
    '''Round a percentage to the nearest of the seven speeds in SPEED_STEPS.'''
    if speed < -100 or speed > 100:
        raise ValueError(f'speed must be between -100 and 100, got {speed}')
    return min(SPEED_STEPS, key=lambda step: abs(step - speed))


def set_speed(card_serial, speed, card_color=None):
    '''Set the speed of the motor holding this card, rounded to SPEED_STEPS.

        >>> set_speed(6055, 45, card_color=6)   # 45 -> 33
        33

    Works for both a Single Motor and a Double Motor -- whichever answers to
    the card. On a Double Motor both sides and the movement speed are set
    together. Returns the speed actually sent.

    Unlike the rest of this module this DOES connect, over Bluetooth, using
    lelib's motor classes. The first call scans and connects, which takes a
    few seconds; the connection is then kept and reused, so later calls are
    quick. Speed is a setting rather than a command, so it applies to whatever
    the motor is asked to do next.
    '''
    rounded = round_speed(speed)
    motor = _motor_for_card(card_serial, card_color)
    motor.set_speed(rounded)
    return rounded


def _motor_for_card(card_serial, card_color):
    '''The connected motor carrying this card, connecting it if needed.

    A singleMotor only ever finds Single Motors and a doubleMotor only ever
    finds Double Motors, so which one connects is what tells us the type.
    '''
    key = (card_serial, card_color)
    motor = _connected_motors.get(key)
    if motor is not None and motor.connected:
        return motor
    _connected_motors.pop(key, None)

    errors = []
    for motor_class in (lelib.singleMotor, lelib.doubleMotor):
        motor = motor_class()
        try:
            motor.connect(card_serial, card_color=card_color)
        except Exception as e:
            errors.append(f'{motor_class.__name__}: {e}')
            continue
        _connected_motors[key] = motor
        return motor

    card = f'card {card_serial}' if card_color is None else f'card {card_color}/{card_serial}'
    raise ConnectionError(
        f'No Single Motor or Double Motor found for {card}. ' + ' | '.join(errors))


def disconnect_all():
    '''Disconnect every motor that set_speed() has connected.'''
    while _connected_motors:
        _, motor = _connected_motors.popitem()
        try:
            motor.disconnect()
        except Exception:
            pass
