'''
Easiet way to use:

import lelib
from lelib import singleMotor, doubleMotor, colorSensor, controller
'''


import asyncio
import time

import legoeducation as le
from bleak import BleakScanner
from legoeducation.basic_ble import SERVICE_UUID
from legoeducation.color_map import _firmware_to_app

class singleMotor(le.SingleMotor):
    def __init__(self):
        super().__init__()

    def connect(self, card_serial, card_color=None):
        for attempt in range(5):
            try:
                super().connect(card_color=card_color, card_serial=card_serial)
                break
            except Exception as e:
                if "not ready" in str(e).lower() and attempt < 4:
                    time.sleep(1)
                else:
                    raise
        if not self.connected:
            raise ConnectionError('Error connecting to Single Motor.')

    def set_update_rate(self, delay_ms=100):
        '''
        Set how often (in milliseconds) the hardware sends automatic
        sensor/button updates over Bluetooth. Must be 0 (off) or between
        15 and 1000.
        '''
        self.device_notification_request(delay_ms)

    def on_button_press(self, callback):
        '''
        Register a function to be called each time the button is pressed.
        callback() is called with no arguments.
        '''
        was_pressed = self.button.state == le.BUTTON_STATE_PRESSED

        def _handle_notification(notification):
            nonlocal was_pressed
            pressed = self.button.state == le.BUTTON_STATE_PRESSED
            if pressed and not was_pressed:
                callback()
            was_pressed = pressed

        self.set_notification_callback(_handle_notification)

    def spin(self, rotations=1):
        self.motor_run_for_degrees(rotations * 360)

    def stop(self):
        self.motor_stop()
    
    def set_speed(self, speed):
        self.motor_set_speed(speed)

    def run(self):
        self.motor_run() 


class doubleMotor(le.DoubleMotor):

    def connect(self, card_serial, card_color=None):
        for attempt in range(5):
            try:
                super().connect(card_color=card_color, card_serial=card_serial)
                break
            except Exception as e:
                if "not ready" in str(e).lower() and attempt < 4:
                    time.sleep(1)
                else:
                    raise
        if not self.connected:
            raise ConnectionError('Error connecting to Double Motor.')

    def set_update_rate(self, delay_ms=100):
        '''
        Set how often (in milliseconds) the hardware sends automatic
        sensor/button updates over Bluetooth. Must be 0 (off) or between
        15 and 1000.
        '''
        self.device_notification_request(delay_ms)

    def on_button_press(self, callback):
        '''
        Register a function to be called each time the button is pressed.
        callback() is called with no arguments.
        '''
        was_pressed = self.button.state == le.BUTTON_STATE_PRESSED

        def _handle_notification(notification):
            nonlocal was_pressed
            pressed = self.button.state == le.BUTTON_STATE_PRESSED
            if pressed and not was_pressed:
                callback()
            was_pressed = pressed

        self.set_notification_callback(_handle_notification)

    def move_steps(self, step=1):
        '''
        Move both motors at once for given number of steps. 
        One step defined to be 180 degrees.
        '''
        self.movement_move_for_degrees(-180*step)

    def run(self):
        self.movement_move(direction=le.MOVEMENT_MOVE_DIRECTION_BACKWARD)

    def run_time(self, time=2000):
        self.movement_move_for_time(time)

    
    def run_left(self, degrees=None):
        if degrees is None:
            self.motor_run(direction=le.MOTOR_MOVE_DIRECTION_COUNTERCLOCKWISE, motor=le.MOTOR_LEFT)
        else:
            self.motor_run_for_degrees(degrees=degrees, direction=le.MOTOR_MOVE_DIRECTION_COUNTERCLOCKWISE, motor=le.MOTOR_LEFT)

    def run_right(self, degrees=None):
        if degrees is None:
            self.motor_run(direction=le.MOTOR_MOVE_DIRECTION_COUNTERCLOCKWISE, motor=le.MOTOR_RIGHT)
        else:
            self.motor_run_for_degrees(degrees=degrees, direction=le.MOTOR_MOVE_DIRECTION_COUNTERCLOCKWISE, motor=le.MOTOR_RIGHT)
    

    def turn_left(self, degrees=90):
        '''
        Turns left by specified number of degrees.
        '''
        self.movement_turn_for_degrees(degrees, direction=le.MOVEMENT_TURN_DIRECTION_LEFT)

    def turn_right(self, degrees=90):
        '''
        Turns right by specified number of degrees.
        '''
        self.movement_turn_for_degrees(degrees, direction=le.MOVEMENT_TURN_DIRECTION_RIGHT)

    def set_speed(self, speed):
        '''
        Set speed of both motors for individual rotation and movement.
        '''
        self.motor_set_speed(speed, motor=le.MOTOR_LEFT)   
        self.motor_set_speed(speed, motor=le.MOTOR_RIGHT)   
        self.movement_set_speed(speed)

    def set_speed_left(self, speed):
        '''
        Set speed of left motor for individual rotation.
        '''
        self.motor_set_speed(speed, motor=le.MOTOR_LEFT)   

    def set_speed_right(self, speed):
        '''
        Set speed of right motor for individual rotation.
        '''
        self.motor_set_speed(speed, motor=le.MOTOR_RIGHT)   


    def stop(self):
        self.motor_stop()


class controller(le.Controller):

    def connect(self, card_serial, card_color=None):
        for attempt in range(5):
            try:
                super().connect(card_color=card_color, card_serial=card_serial)
                break
            except Exception as e:
                if "not ready" in str(e).lower() and attempt < 4:
                    time.sleep(1)
                else:
                    raise
        if not self.connected:
            raise ConnectionError('Error connecting to Controller.')

    def set_update_rate(self, delay_ms=100):
        '''
        Set how often (in milliseconds) the hardware sends automatic
        sensor/button updates over Bluetooth. Must be 0 (off) or between
        15 and 1000.
        '''
        self.device_notification_request(delay_ms)

    def on_button_press(self, callback):
        '''
        Register a function to be called each time the button is pressed.
        callback() is called with no arguments.
        '''
        was_pressed = self.button.state == le.BUTTON_STATE_PRESSED

        def _handle_notification(notification):
            nonlocal was_pressed
            pressed = self.button.state == le.BUTTON_STATE_PRESSED
            if pressed and not was_pressed:
                callback()
            was_pressed = pressed

        self.set_notification_callback(_handle_notification)

    def left_up(self):
        return self.sensor.leftPercent > 0
    
    def left_down(self):
        return self.sensor.leftPercent < 0

    def left_released(self):
        return self.sensor.leftPercent == 0

    def right_up(self):
        return self.sensor.rightPercent > 0

    def right_down(self):
        return self.sensor.rightPercent < 0

    def right_released(self):
        return self.sensor.rightPercent == 0
    
    def left_position(self):
        return self.sensor.leftPercent
    
    def right_position(self):
        return self.sensor.rightPercent
        
    # ── driving helper ──────────────────

    def drive(self, dm, t=100): 
        for i in range(t):
            dm.movement_move_tank(self.left_position(), self.right_position())
            time.sleep(0.1)

class colorSensor(le.ColorSensor):
    def __init__(self):
        super().__init__()

    def connect(self, card_serial, card_color=None):
        for attempt in range(5):
            try:
                super().connect(card_color=card_color, card_serial=card_serial)
                break
            except Exception as e:
                if "not ready" in str(e).lower() and attempt < 4:
                    time.sleep(1)
                else:
                    raise
        if not self.connected:
            raise ConnectionError('Error connecting to Color Sensor.')

    def set_update_rate(self, delay_ms=100):
        '''
        Set how often (in milliseconds) the hardware sends automatic
        sensor/button updates over Bluetooth. Must be 0 (off) or between
        15 and 1000.
        '''
        self.device_notification_request(delay_ms)

    def on_button_press(self, callback):
        '''
        Register a function to be called each time the button is pressed.
        callback() is called with no arguments.
        '''
        was_pressed = self.button.state == le.BUTTON_STATE_PRESSED

        def _handle_notification(notification):
            nonlocal was_pressed
            pressed = self.button.state == le.BUTTON_STATE_PRESSED
            if pressed and not was_pressed:
                callback()
            was_pressed = pressed

        self.set_notification_callback(_handle_notification)

    def reflection(self):
        return self.sensor.reflection

    def detect_color(self):
        color_number = self.sensor.color
        color_mapping = {
            0: 'No color',
            1: 'Red',
            2: 'Yellow',
            3: 'Blue',
            4: 'Teal',
            5: 'Green',
            6: 'Purple',
            7: 'White',
            8: 'Magenta',
            9: 'Orange',
            10: 'Azure'
        }
        #detect the color, return the detected color
        return color_mapping.get(color_number, 'Unknown')


# ── connectionless reading (no connect() needed) ────────────────────
#
# LEGO Education devices continuously broadcast their live state in a BLE
# advertisement (service UUID FD02), addressed by the card they were tapped
# with. Reading that takes no connection and no pairing, so it does not use
# up a device's single connection slot -- you can watch a controller while
# a motor is being driven by it.
#
# The byte map and the evidence behind it are in card_mode/CLAUDE.md.

_FD02_UUID = SERVICE_UUID.lower()

_DEVICE_TYPE_COLOR_SENSOR = 0x02
_DEVICE_TYPE_CONTROLLER = 0x03


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
    '''True if an FD02 payload was broadcast by a device carrying this card.

    A serial on its own is NOT unique -- serials are handed out per color,
    so RED#1126 and BLUE#1126 are different cards. Pass card_color whenever
    you can; without it this matches any color sharing the serial.
    '''
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
        'read_sensor() cannot be called from inside a running event loop; '
        'await the scan yourself instead.')


def read_sensor(card_serial, card_color=None, timeout=3.0):
    '''Listen for everything broadcasting under one card and report its state.

        >>> read_sensor(1126, le.LEGO_COLOR_BLUE)
        {'color': 4, 'controller': (2, 3)}

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


DEVICE_NAMES = {_DEVICE_TYPE_COLOR_SENSOR: 'color sensor',
                _DEVICE_TYPE_CONTROLLER: 'controller'}


def find_cards(timeout=5.0):
    '''Every card heard broadcasting nearby, without connecting to anything.

        >>> find_cards()
        [{'color': 6, 'serial': 6055, 'device': 'color sensor'},
         {'color': 6, 'serial': 6055, 'device': 'controller'}]

    Use this when read_sensor() comes back empty: it answers "what IS out
    there", which is almost always a card number that does not match the one
    being asked for. Serials are handed out per color, so the color matters --
    RED#1126 and BLUE#1126 are different cards.

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


# ── speed control by card ───────────────────────────────────────────

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

        >>> set_speed(1126, 45, le.LEGO_COLOR_BLUE)   # 45 -> 33
        33

    Works for both a Single Motor and a Double Motor -- whichever answers to
    the card. On a Double Motor both sides and the movement speed are set
    together. Returns the speed actually sent.

    The first call scans and connects, which takes a few seconds; the
    connection is then kept and reused, so later calls are quick. Speed is a
    setting rather than a command, so it applies to whatever the motor is
    asked to do next.

    Pass card_color whenever you can -- serials are allocated per color, so
    a serial on its own can match the wrong card.
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
    for motor_class in (singleMotor, doubleMotor):
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

