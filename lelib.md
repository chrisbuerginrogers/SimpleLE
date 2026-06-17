# lelib API Reference

`lelib.py` wraps the `legoeducation` package with four classes that add automatic retry logic on connect and friendlier method names.

```python
import lelib
from lelib import singleMotor, doubleMotor, colorSensor, controller
```

All four classes share the same `connect()` signature and retry behavior: up to 5 attempts, 1-second delay between retries if the device reports "not ready", raising a `ConnectionError` on final failure.

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
