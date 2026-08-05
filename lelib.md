# lelib API Reference

`lelib.py` wraps the `legoeducation` package with four classes that add automatic retry logic on connect and friendlier method names.

```python
import lelib
from lelib import singleMotor, doubleMotor, colorSensor, controller
```

All four classes share the same `connect()` signature and retry behavior: up to 5 attempts, 1-second delay between retries if the device reports "not ready", raising a `ConnectionError` on final failure.

All four classes also share these two methods:

| Method | Parameters | Description |
|---|---|---|
| `set_update_rate(delay_ms=100)` | `delay_ms` *(int, default `100`)* – milliseconds between automatic Bluetooth updates; `0` turns updates off, otherwise must be 15–1000 | Sends the BLE command that controls how often the hardware reports sensor/button state. |
| `on_button_press(callback)` | `callback` – function called with no arguments | Registers `callback` to fire once each time the hardware button is pressed (rising edge only, not on hold or release). Requires automatic updates to be on (they are by default after `connect()`). |

```python
motor = singleMotor()
motor.connect(1234)

motor.set_update_rate(1000)     # only report state once a second
motor.set_update_rate(0)        # turn automatic updates off entirely
motor.set_update_rate()         # back to the default, 100ms (10x/second)

motor.on_button_press(lambda: print("Button pressed!"))
```

---

## singleMotor

Controls a single LEGO motor. Extends `legoeducation.SingleMotor`.

| Method | Parameters | Description |
|---|---|---|
| `connect(card_color, card_serial)` | `card_color` – color of the Bluetooth card; `card_serial` – serial number of the card | Connects to the motor with up to 5 retries. |
| `spin(rotations=1)` | `rotations` *(int/float, default `1`)* – number of full rotations | Runs the motor for the given number of rotations (converts to degrees internally). |
| `stop()` | — | Stops the motor immediately. |
| `set_speed(speed)` | `speed` – speed value (units defined by underlying library) | Sets the motor speed. |
| `run()` | — | Runs the motor continuously until stopped. |

---

## doubleMotor

Controls a paired left/right drive motor setup. Extends `legoeducation.DoubleMotor`.

| Method | Parameters | Description |
|---|---|---|
| `connect(card_color, card_serial)` | `card_color` – color of the Bluetooth card; `card_serial` – serial number of the card | Connects to the motor pair with up to 5 retries. |
| `move_steps(step=1)` | `step` *(int/float, default `1`)* – number of steps; 1 step = 180° | Moves both motors together for the given number of steps. |
| `run()` | — | Runs both motors continuously in the backward direction. |
| `run_time(time=2000)` | `time` *(int, default `2000`)* – duration in milliseconds | Runs both motors together for a fixed duration. |
| `run_left(degrees=None)` | `degrees` *(int/float or `None`)* – if `None`, runs continuously; otherwise runs for that many degrees | Runs the left motor counter-clockwise. |
| `run_right(degrees=None)` | `degrees` *(int/float or `None`)* – if `None`, runs continuously; otherwise runs for that many degrees | Runs the right motor counter-clockwise. |
| `turn_left(degrees=90)` | `degrees` *(int/float, default `90`)* – degrees to turn | Turns the robot left by the specified number of degrees. |
| `turn_right(degrees=90)` | `degrees` *(int/float, default `90`)* – degrees to turn | Turns the robot right by the specified number of degrees. |
| `set_speed(speed)` | `speed` – speed value | Sets the speed of both motors and the movement system simultaneously. |
| `set_speed_left(speed)` | `speed` – speed value | Sets the speed of the left motor only. |
| `set_speed_right(speed)` | `speed` – speed value | Sets the speed of the right motor only. |
| `stop()` | — | Stops both motors. |

---

## controller

Reads input from a LEGO controller (two joysticks). Extends `legoeducation.Controller`.

| Method | Parameters | Returns | Description |
|---|---|---|---|
| `connect(card_color, card_serial)` | `card_color` – color of the Bluetooth card; `card_serial` – serial number of the card | — | Connects to the controller with up to 5 retries. |
| `left_up()` | — | `bool` | `True` when the left joystick is pushed up (positive percent). |
| `left_down()` | — | `bool` | `True` when the left joystick is pushed down (negative percent). |
| `left_released()` | — | `bool` | `True` when the left joystick is centered (zero percent). |
| `right_up()` | — | `bool` | `True` when the right joystick is pushed up. |
| `right_down()` | — | `bool` | `True` when the right joystick is pushed down. |
| `right_released()` | — | `bool` | `True` when the right joystick is centered. |
| `left_position()` | — | `int/float` | Raw percent position of the left joystick (negative = down, positive = up). |
| `right_position()` | — | `int/float` | Raw percent position of the right joystick. |
| `drive(dm, t=100)` | `dm` – a `doubleMotor` instance; `t` *(int, default `100`)* – number of 0.1-second ticks to run | — | Tank-drives `dm` using both joystick positions for `t × 0.1` seconds total. |

---

## colorSensor

Reads color data from a LEGO color sensor. Extends `legoeducation.ColorSensor`.

| Method | Parameters | Returns | Description |
|---|---|---|---|
| `connect(card_color, card_serial)` | `card_color` – color of the Bluetooth card; `card_serial` – serial number of the card | — | Connects to the sensor with up to 5 retries. |
| `reflection()` | — | `int/float` | Returns the raw reflection value from the sensor (0–255). |
| `detect_color()` | — | `str` | Returns the name of the detected color (see table below). |

### Color mapping

| Sensor value | Color name |
|---|---|
| 0 | No color |
| 1 | Red |
| 2 | Yellow |
| 3 | Blue |
| 4 | Teal |
| 5 | Green |
| 6 | Purple |
| 7 | White |
| 8 | Magenta |
| 9 | Orange |
| 10 | Azure |
| other | Unknown |

---

## Module-level functions

These are called on `lelib` itself rather than on a class, and identify
hardware by its card instead of by a connected object.

Serials are allocated per color, so `1126` alone can match a red card *and* a
blue one. Pass `card_color` whenever you can.

| Function | Parameters | Returns | Description |
|---|---|---|---|
| `read_sensor(card_serial, card_color=None, timeout=3.0)` | `card_serial` – serial number of the card; `card_color` – `LEGO_COLOR_*` constant; `timeout` *(float, default `3.0`)* – seconds to listen | `dict` | Reads every device broadcasting under one card without connecting to any of them. See below. |
| `find_cards(timeout=5.0)` | `timeout` *(float, default `5.0`)* – seconds to listen | `list` of `dict` | Every card heard broadcasting nearby. Use it when `read_sensor()` comes back empty — it answers "what *is* out there". See below. |
| `set_speed(card_serial, speed, card_color=None)` | `card_serial` – serial number of the card; `speed` *(int/float, −100 to 100)*; `card_color` – `LEGO_COLOR_*` constant | `int` | Sets the speed of the Single or Double Motor holding that card, rounded to `SPEED_STEPS`. Returns the speed actually sent. |
| `round_speed(speed)` | `speed` *(int/float, −100 to 100)* | `int` | Rounds a percentage to the nearest entry in `SPEED_STEPS`. Raises `ValueError` outside −100…100. |
| `disconnect_all()` | — | — | Disconnects every motor `set_speed()` has connected. |

### `read_sensor()`

Needs no `connect()` and no pairing — it listens to the advertisement every
device broadcasts continuously. Because it doesn't connect, it doesn't use up
a device's single connection slot, so you can watch a controller while a motor
is being driven by it.

A card names a *group* rather than one device, so both keys can be filled at
once when a color sensor and a controller share a card.

```python
lelib.read_sensor(1126, le.LEGO_COLOR_BLUE)
# {'color': 4, 'controller': (2, 3)}
```

| Key | Value |
|---|---|
| `'color'` | Color the sensor is currently looking at, as a sensor value from the table above (`0` = no color). `None` if no color sensor with this card was heard from. |
| `'controller'` | `(left, right)` stick positions, each −3…+3, resting at `0`. `None` if no controller with this card was heard from. |

Blocks for `timeout` seconds and returns the most recent reading. macOS
coalesces advertisements down to a few per second, so shorter windows can miss
a device. Black and an empty field of view both report "no color" — the
sensor cannot tell them apart.

### `find_cards()`

Answers the question you actually have when nothing shows up: *what is out
there?* An empty `read_sensor()` is nearly always a card number matching
nothing on the air, not a device that is switched off.

```python
lelib.find_cards()
# [{'color': 6, 'serial': 6055, 'device': 'color sensor'},
#  {'color': 6, 'serial': 6055, 'device': 'controller'}]
```

One entry per (color, serial, device type), so a color sensor and a controller
sharing a card appear separately. Only *senders* broadcast this way — a motor
does not show up here.

### `set_speed()` and `SPEED_STEPS`

`SPEED_STEPS` is `(-100, -67, -33, 0, 33, 67, 100)` — seven evenly spaced
speeds, mirroring the seven positions a controller stick can report (−3…+3),
so a motor driven from code feels like one driven from a controller.

Works for both motor types: whichever answers to the card is the one that gets
set, and on a Double Motor both sides and the movement speed are set together.
The first call scans and connects (a few seconds); the connection is kept and
reused, so later calls are quick. Speed is a setting rather than a command, so
it applies to whatever the motor is asked to do next.

```python
lelib.set_speed(1126, 45, le.LEGO_COLOR_BLUE)   # 45 rounds to 33
# 33
```
