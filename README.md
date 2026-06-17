# SimpleLE

A thin Python wrapper around the [`legoeducation`](https://pypi.org/project/legoeducation/) package that adds automatic Bluetooth reconnect logic and friendlier method names for LEGO Education hardware.

## Classes

| Class | Wraps | Purpose |
|---|---|---|
| `singleMotor` | `le.SingleMotor` | Drive a single LEGO motor |
| `doubleMotor` | `le.DoubleMotor` | Drive a paired left/right motor setup |
| `controller` | `le.Controller` | Read joystick input from a LEGO controller |
| `colorSensor` | `le.ColorSensor` | Read color and reflection data from a LEGO color sensor |

All four classes share the same connection behavior: up to 5 retries with a 1-second delay between attempts, raising `ConnectionError` on final failure.

## Installation

```bash
pip install legoeducation matplotlib
```

Then copy `lelib.py` into your project.

## Quick start

```python
from lelib import singleMotor, doubleMotor, colorSensor, controller

SERIAL = 1234  # your Bluetooth card serial number

motor = singleMotor()
motor.connect(SERIAL)
motor.spin(2)      # spin 2 full rotations
motor.stop()
```

## API

See [lelib.md](lelib.md) for the full API reference.

## Example: joystick-controlled drive with live color graph

`drive.py` connects a double motor, controller, and color sensor to the same Bluetooth card, then:

- Runs a background thread that tank-drives the motors from joystick input and samples the color sensor at 20 Hz
- Opens a live `matplotlib` plot of the reflection value

```bash
python drive.py
```

Edit the `SERIAL` constant at the top of the file to match your Bluetooth card.
