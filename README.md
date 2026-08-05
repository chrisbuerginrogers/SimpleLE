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

## cardlib: talking to a card, with no connection

`cardlib.py` identifies hardware by its **card** rather than by a connected
object. It listens to the advertisement every device broadcasts anyway, so it
needs no pairing and doesn't use up a device's single connection slot — you can
watch a controller while a motor is being driven by it. A card names a *group*,
so one call can report a color sensor and a controller together.

`lelib` stays the plain connect-and-drive library; this is kept separate so the
two don't get mixed up.

| Function | Purpose |
|---|---|
| `find_cards()` | List every card broadcasting nearby — run this first |
| `read_sensor(card_serial, card_color=None)` | Read everything broadcasting under one card — **without connecting to it** |
| `set_speed(card_serial, speed, card_color=None)` | Set the speed of whichever motor holds that card, rounded to seven steps |

```python
import cardlib
import legoeducation as le

cardlib.find_cards()
# [{'color': 6, 'serial': 6055, 'device': 'color sensor'},
#  {'color': 6, 'serial': 6055, 'device': 'controller'}]

cardlib.read_sensor(6055, le.LEGO_COLOR_PURPLE)
# {'color': 2, 'controller': (0, 0)}    color 2 = Yellow, both sticks centered

cardlib.set_speed(6055, 45, le.LEGO_COLOR_PURPLE)   # 45 rounds to 33
# 33
```

If `read_sensor()` comes back empty, `find_cards()` is the answer — an empty
read is nearly always a card number matching nothing on the air.

Serials are allocated per color, so `1126` alone can match a red card *and* a
blue one. Pass `card_color` whenever you can.

## Driving motors with no connection

`pico_lelib.py` gives you the same syntax as lelib, but drives motors by
**broadcast** — no pairing and no connection to the motor at all. macOS cannot
transmit a BLE advertisement, so the broadcast comes from a MicroPython board
(ESP32 or Pico W) on the end of a USB cable; your code still runs on the Mac.

```python
import pico_lelib
pico_lelib.install()      # copy the board libraries over, once
pico_lelib.check_pico()   # "no board" / "not running the server" / "ready"

motor = pico_lelib.doubleMotor()
motor.connect(6055, card_color=le.LEGO_COLOR_PURPLE)
motor.set_speed(70)       # rounds to 67
motor.run()
motor.tank(100, -100)     # spin on the spot
motor.stop()
```

It carries only what the broadcast can express: two joystick positions with
seven steps each. `spin()`, `turn_left()` and `move_steps()` need the motor to
report back, which a broadcast cannot do, so they are absent rather than faked
— use `lelib` for those. Requires `pip install pyserial`.

Verified end to end on an ESP32-S3 running MicroPython, driving a real LEGO
motor with no connection and no controller — on two different cards, each with
its own tokens. A Pico W uses the same API.

## Reading the cards themselves

The connection cards are NTAG/Ultralight tags, and they carry their color and
serial in the clear behind an ASCII `L3G0` marker. With an RFID reader on the
board you can tap a card and have the code work out which motor to talk to —
see [card_mode/examples/](card_mode/examples/).

## Examples and the protocol

- [card_mode/examples/](card_mode/examples/) — small single-purpose programs,
  split into `mac_*.py` (run on your Mac) and `stick_*.py` (run on the board)
- [card_mode/](card_mode/) — how the broadcast protocol was reverse-engineered,
  and the tools that did it

## Installation

```bash
pip install legoeducation matplotlib
pip install pyserial          # only for pico_lelib.py, which talks to a board
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

See [lelib.md](lelib.md) for the lelib API reference and [cardlib.md](cardlib.md) for the card-addressed one, or `docs/` for a full per-class reference covering every method (including the underlying `legoeducation` calls lelib doesn't rename) with an example each:

- [docs/singleMotor.md](docs/singleMotor.md)
- [docs/doubleMotor.md](docs/doubleMotor.md)
- [docs/controller.md](docs/controller.md)
- [docs/colorSensor.md](docs/colorSensor.md)

## Example: joystick-controlled drive with live color graph

`projects/drive.py` connects a double motor, controller, and color sensor to the same Bluetooth card, then:

- Runs a background thread that tank-drives the motors from joystick input and samples the color sensor at 20 Hz
- Opens a live `matplotlib` plot of the reflection value

```bash
python projects/drive.py
```

Edit the `SERIAL` constant at the top of the file to match your Bluetooth card.
