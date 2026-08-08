'''
picolib — drive LEGO Education motors by BLE broadcast, with no connection.

  >>> Runs ON a Pico W / Pico 2 W (MicroPython), NOT on the Mac. Copy this
      file to the Pico alongside your script. A plain Pico has no radio. <<<

This is the transmit half of the protocol, and it is the half a Mac cannot do:
macOS/bleak can scan and connect but never transmit a custom advertisement.
Everything readable from the Mac lives in ../../lelib.py instead.

Brick-to-brick control is connectionless BLE *broadcast*. Every device tapped
with the same card forms a group; controllers broadcast their stick positions,
and motors listen and act. Impersonate the controller and the motor obeys --
no GATT, no pairing, no real controller, no hub.

    import picolib

    card = picolib.Card(color=picolib.PURPLE, serial=1126, b2=0xf3, b7=0x48)
    motor = picolib.Motor(card)
    motor.set_speed(45)      # rounds to 33 -> stick step +1
    motor.drive(3)           # keep broadcasting it for 3 seconds
    motor.stop()

The protocol byte map and the evidence for it are in ../CLAUDE.md.

── You need the card's b2/b7 tokens ──────────────────────────────────────
A motor validates bytes 2 and 7. They are a per-card token that is NOT
derivable from the color and serial, so a beacon with the right serial and
wrong tokens is silently ignored. You cannot make them up.

Read them off any controller or color sensor already carrying that card:
run ../watch_service_data.py on the Mac and take bytes 2 and 7 of the FD02
payload. A motor's own advertisement does NOT contain them -- it uses the
manufacturer-data layout, which carries only color and serial. That is why
this library asks for them explicitly rather than scanning for them.
'''

# MicroPython's bluetooth module only exists on the Pico. Guarding the import
# lets the encoding functions below be imported and checked on a laptop; any
# actual broadcasting still needs real hardware.
try:
    import bluetooth
except ImportError:
    bluetooth = None

import time


# ── card colors ──────────────────────────────────────────────────────────
# Colors have TWO numbering schemes and mixing them up yields plausible-
# looking wrong answers. These constants are the App codes, matching
# legoeducation's LEGO_COLOR_* values and lelib's read_sensor(); the wire
# wants the firmware code, and _wire_color() below does that conversion.
NOCOLOR = 0
RED = 1
YELLOW = 2
BLUE = 3
TEAL = 4
GREEN = 5
PURPLE = 6
WHITE = 7
MAGENTA = 8
ORANGE = 9
AZURE = 10

_APP_TO_FIRMWARE = {0: -1, 1: 9, 2: 7, 3: 3, 4: 5, 5: 6, 6: 2, 7: 10,
                    8: 1, 9: 8, 10: 4}


def _wire_color(app_color):
    '''App color code -> the firmware code that goes on the wire.'''
    if app_color not in _APP_TO_FIRMWARE:
        raise ValueError('unknown color {}; use picolib.PURPLE etc.'.format(app_color))
    return _APP_TO_FIRMWARE[app_color] & 0xFF


# ── speeds ────────────────────────────────────────────────────────────────
# A stick reports seven positions and the motor reads only the low nibble of
# the stick byte, as a signed 4-bit value: 0 stop, +1..+3 forward, -1..-3
# reverse. Everything else (0x4..0xc) is out of range and reads as dead.
#
# SPEED_STEPS matches cardlib.SPEED_STEPS, so a percentage rounds the same way
# whether it is sent over GATT from the Mac or broadcast from the Pico.
SPEED_STEPS = (-100, -67, -33, 0, 33, 67, 100)
MAX_STEP = 3


def round_speed(speed):
    '''Round a percentage to the nearest of the seven speeds in SPEED_STEPS.'''
    if speed < -100 or speed > 100:
        raise ValueError('speed must be between -100 and 100, got {}'.format(speed))
    best = SPEED_STEPS[0]
    for step in SPEED_STEPS:
        if abs(step - speed) < abs(best - speed):
            best = step
    return best


def speed_to_step(speed):
    '''Percentage -> the stick step (-3..+3) the motor acts on.'''
    return round(round_speed(speed) * MAX_STEP / 100)


def step_to_byte(step):
    '''Stick step (-3..+3) -> the byte to broadcast.

    Only the low nibble matters, so this is the signed 4-bit encoding:
    +3 -> 0x03, -3 -> 0x0d, 0 -> 0x00.
    '''
    if step < -MAX_STEP or step > MAX_STEP:
        raise ValueError('step must be between {} and {}, got {}'.format(
            -MAX_STEP, MAX_STEP, step))
    return step & 0x0F


def pct_to_byte_v04(speed):
    '''Percentage -> direct signed-8 byte, for the confirmed 0x04 device type.

    Continuous (up to 254 distinct values) rather than DEVICE_TYPE_CONTROLLER's
    7 steps. See the note on DEVICE_TYPE_DOUBLE_MOTOR_V04 above and
    Motor.set_tank_v04's docstring for the mirror-image sign handling this
    hides from callers.
    '''
    if speed < -100 or speed > 100:
        raise ValueError('speed must be between -100 and 100, got {}'.format(speed))
    return round(speed / 100 * 127) & 0xFF


# ── beacon ────────────────────────────────────────────────────────────────
DEVICE_TYPE_CONTROLLER = 0x03

# Confirmed live 2026-08-08 against a real Double Motor (PURPLE #6055),
# following a lead from an external writeup on the same protocol
# (fantasticalWands MOTOR_BROADCAST_RECIPE.md) -- see ../Card_mode.md, "A
# second device type, byte0 = 0x04: confirmed". Takes a direct signed-8
# per-wheel speed in b5/b6, continuous rather than DEVICE_TYPE_CONTROLLER's
# 7-state low-nibble encoding. This rig's wheels are mounted mirror-image, so
# the right wheel's sign has to be flipped to get ordinary tank() semantics
# (both positive = straight forward) -- Motor.set_tank_v04 does that.
#
# One gotcha found along the way: reconnecting immediately after installing
# new board code / a soft reset produced a spurious "nothing happens" result
# once, not reproduced with the same bytes moments later in a stable
# connection. Repeated trials within one continuous connection were fully
# reproducible in both directions -- if this looks flaky again, reconnect
# fresh and retest before doubting the protocol.
DEVICE_TYPE_DOUBLE_MOTOR_V04 = 0x04

SERVICE_UUID16 = 0xFD02

# Byte 8 is unidentified -- it drifts by +/-1 on a real device and is held
# constant here, which works. Bytes 9-11 are a counter that must keep
# advancing or packets stop looking fresh.
DEFAULT_BYTE8 = 0x80
COUNTER_STEP = 0x00B300

ADV_INTERVAL_US = 100_000
DEFAULT_STEP_MS = 40


class Card(object):
    '''The identity a beacon is broadcast under.

    color   -- App color code (picolib.PURPLE, ...)
    serial  -- card serial number
    b2, b7  -- the card's tokens, which the motor validates. See the note at
               the top of this file for how to read them off a real device.
    '''

    def __init__(self, color, serial, b2, b7, byte8=DEFAULT_BYTE8):
        self.color = color
        self.wire_color = _wire_color(color)
        self.serial = serial & 0xFFFF
        self.b2 = b2 & 0xFF
        self.b7 = b7 & 0xFF
        self.byte8 = byte8 & 0xFF

    def __repr__(self):
        return 'Card(color {} serial {} tokens {:02x}/{:02x})'.format(
            self.color, self.serial, self.b2, self.b7)


def build_beacon(card, device_type, left_byte, right_byte, counter):
    '''The 12-byte FD02 payload, wrapped as a complete advertisement.

        byte 0     device type -- 0x03 controller, 0x04 double-motor direct speed
        byte 1     card color (firmware code)
        byte 2     card token
        bytes 3-4  card serial, little-endian
        byte 5     RIGHT (already the final wire byte -- caller encodes it)
        byte 6     LEFT (ditto)
        byte 7     card token
        byte 8     unidentified, held constant
        bytes 9-11 counter, big-endian
    '''
    service_data = bytes([
        device_type,
        card.wire_color,
        card.b2,
        card.serial & 0xFF, (card.serial >> 8) & 0xFF,
        right_byte,
        left_byte,
        card.b7,
        card.byte8,
        (counter >> 16) & 0xFF, (counter >> 8) & 0xFF, counter & 0xFF,
    ])
    block = bytes([0x16, SERVICE_UUID16 & 0xFF, (SERVICE_UUID16 >> 8) & 0xFF]) + service_data
    flags = bytes([0x02, 0x01, 0x06])
    return flags + bytes([len(block)]) + block


# ── motor ─────────────────────────────────────────────────────────────────
class Motor(object):
    '''A Single or Double Motor, driven by broadcasting as its card.

    The same beacon drives either -- a Double Motor combines the two sticks
    (both forward -> straight, opposite -> spin on the spot), and a Single
    Motor responds to the pair as one. Nothing here identifies the motor type,
    because the protocol does not distinguish them.
    '''

    def __init__(self, card, step_ms=DEFAULT_STEP_MS):
        if bluetooth is None:
            raise RuntimeError(
                'picolib needs MicroPython on a Pico W. There is no way to '
                'transmit a BLE advertisement from macOS -- use lelib on the Mac.')
        self.card = card
        self.step_ms = step_ms
        self.device_type = DEVICE_TYPE_CONTROLLER
        self.left_byte = 0
        self.right_byte = 0
        self._counter = 0
        self._ble = bluetooth.BLE()
        self._ble.active(True)

    def set_speed(self, speed):
        '''Set both sticks to one speed, rounded to SPEED_STEPS.

        Returns the speed actually sent. Starts broadcasting immediately and
        keeps broadcasting it until changed, but the counter only advances
        when you call drive() or refresh() -- a motor that stops hearing fresh
        packets will eventually give up. Confirmed encoding -- see set_tank_v04
        for the unverified alternative.
        '''
        rounded = round_speed(speed)
        byte = step_to_byte(speed_to_step(rounded))
        self.device_type = DEVICE_TYPE_CONTROLLER
        self.left_byte = byte
        self.right_byte = byte
        self.refresh()
        return rounded

    def set_tank(self, left, right):
        '''Set the two sticks separately, each rounded to SPEED_STEPS.

        Returns the (left, right) speeds actually sent. Confirmed encoding --
        see set_tank_v04 for the unverified alternative.
        '''
        left_rounded = round_speed(left)
        right_rounded = round_speed(right)
        self.device_type = DEVICE_TYPE_CONTROLLER
        self.left_byte = step_to_byte(speed_to_step(left_rounded))
        self.right_byte = step_to_byte(speed_to_step(right_rounded))
        self.refresh()
        return left_rounded, right_rounded

    def set_tank_v04(self, left, right):
        '''Direct signed-8 per-wheel speed under device type 0x04.

        Continuous rather than SPEED_STEPS' 7 steps. Confirmed live
        2026-08-08 on a real Double Motor (PURPLE #6055): repeated trials
        within one continuous connection reproduced cleanly in both
        directions -- same-sign left/right (what this method sends after the
        flip below) drove straight forward, twice; opposite-sign drove a turn,
        twice. This rig's wheels are mounted mirror-image, so the right
        wheel's sign has to be flipped to get ordinary tank() semantics (both
        positive = straight forward) -- exactly the gotcha
        MOTOR_BROADCAST_RECIPE.md calls out ("negate one wheel if the motors
        are mounted mirror-image"). See ../Card_mode.md, "A second device
        type, byte0 = 0x04: confirmed" for the full trial log, including one
        spurious no-movement result that turned out to be caused by
        reconnecting right after a board reboot, not the protocol.

        If your build's motors are mounted the other way around, flip which
        side gets negated below.

        Returns the (left, right) percentages actually sent, clamped to
        -100..100 (not rounded to SPEED_STEPS -- there is nothing to round to).
        '''
        left = -100 if left < -100 else 100 if left > 100 else left
        right = -100 if right < -100 else 100 if right > 100 else right
        self.device_type = DEVICE_TYPE_DOUBLE_MOTOR_V04
        self.left_byte = pct_to_byte_v04(left)
        self.right_byte = pct_to_byte_v04(-right)
        self.refresh()
        return left, right

    def refresh(self):
        '''Re-broadcast the current sticks with the counter advanced.'''
        self._ble.gap_advertise(None)
        self._ble.gap_advertise(
            ADV_INTERVAL_US,
            adv_data=build_beacon(self.card, self.device_type,
                                  self.left_byte, self.right_byte,
                                  self._counter),
            connectable=False)
        self._counter = (self._counter + COUNTER_STEP) & 0xFFFFFF

    def drive(self, seconds):
        '''Hold the current speed for this many seconds, keeping packets fresh.'''
        deadline = time.ticks_add(time.ticks_ms(), int(seconds * 1000))
        while time.ticks_diff(deadline, time.ticks_ms()) > 0:
            self.refresh()
            time.sleep_ms(self.step_ms)

    def stop(self):
        '''Send stop, then leave the air quiet.'''
        self.device_type = DEVICE_TYPE_CONTROLLER
        self.left_byte = 0
        self.right_byte = 0
        self.refresh()
        time.sleep_ms(self.step_ms * 5)
        self._ble.gap_advertise(None)

    def close(self):
        '''Stop broadcasting and power the radio down.'''
        try:
            self.stop()
        finally:
            self._ble.active(False)
