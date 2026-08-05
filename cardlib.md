# cardlib API Reference

`cardlib.py` talks to LEGO Education hardware by its **card**, with no
connection and no pairing.

```python
import cardlib
```

Devices continuously broadcast their live state in a BLE advertisement, keyed
by the card they were tapped with. Listening to that costs nothing and does not
use up a device's single connection slot — you can watch a controller while a
motor is being driven by it.

## How this differs from lelib

| | |
|---|---|
| [`lelib.py`](lelib.md) | Connect to one device over Bluetooth, then call methods on it. The full API. |
| `cardlib.py` | Listen to what devices broadcast. No connection, and a strictly smaller set of things. |
| `pico_lelib.py` | Broadcast *commands*, through a microcontroller on USB. |

`lelib` is the simple LEGO library and stays that way; anything card-addressed
lives here so the two do not get mixed up.

**Cards are `(color, serial)`, not serial.** Serials are handed out per color,
so RED#1126 and BLUE#1126 are different cards. Pass `card_color` whenever you
can — leaving it out matches any color sharing that serial.

## Functions

Every one of these identifies hardware by its **card** rather than by a
connected object.

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
cardlib.read_sensor(6055, le.LEGO_COLOR_PURPLE)
# {'color': 2, 'controller': (0, 0)}
```

| Key | Value |
|---|---|
| `'color'` | Color the sensor is currently looking at, as a `LEGO_COLOR_*` code (`0` = no color; the numbers are in the [color mapping table](lelib.md#color-mapping)). `None` if no color sensor with this card was heard from. |
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
cardlib.find_cards()
# [{'color': 6, 'serial': 6055, 'device': 'color sensor'},
#  {'color': 6, 'serial': 6055, 'device': 'controller'}]
```

One entry per (color, serial, device type), so a color sensor and a controller
sharing a card appear separately. Only *senders* broadcast this way — a motor
does not show up here.

### `set_speed()` and `SPEED_STEPS`

**This is the one function here that does connect**, over Bluetooth, using
`lelib`'s motor classes. It lives in `cardlib` because it is addressed by card
rather than by an object you already hold, and because `SPEED_STEPS` is a
broadcast idea the board side shares.

`SPEED_STEPS` is `(-100, -67, -33, 0, 33, 67, 100)` — seven evenly spaced
speeds, mirroring the seven positions a controller stick can report (−3…+3),
so a motor driven from code feels like one driven from a controller.

Works for both motor types: whichever answers to the card is the one that gets
set, and on a Double Motor both sides and the movement speed are set together.
The first call scans and connects (a few seconds); the connection is kept and
reused, so later calls are quick. Speed is a setting rather than a command, so
it applies to whatever the motor is asked to do next. Call `disconnect_all()`
when you are done.

```python
cardlib.set_speed(6055, 45, le.LEGO_COLOR_PURPLE)   # 45 rounds to 33
# 33
```
