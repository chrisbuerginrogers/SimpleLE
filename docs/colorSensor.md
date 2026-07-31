# colorSensor — Full Reference

`lelib.colorSensor` wraps `legoeducation.ColorSensor`. It reads color and reflection data from a LEGO color sensor and adds retry-based connecting plus `set_update_rate`/`on_button_press` on top of the full underlying API — every method below works directly on a `colorSensor` instance.

```python
from lelib import colorSensor
import legoeducation as le

cs = colorSensor()
cs.connect(1234)  # your Bluetooth card serial
```

## Live sensor attributes

| Attribute | Fields | Description |
|---|---|---|
| `cs.button` | `.state` | Current button state. |
| `cs.sensor` | `.color`, `.reflection`, `.rawRed`, `.rawGreen`, `.rawBlue`, `.hue`, `.saturation`, `.value` | Raw sensor reading; `.reflection` is 0–255, `.color` is the raw color code (see mapping below). |

```python
print(cs.sensor.reflection, cs.sensor.hue)
```

### Color mapping (used by `detect_color()`)

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

## lelib convenience methods

#### `connect(card_serial, card_color=None)`
Connects with up to 5 retries (1s delay) if the hardware reports "not ready".
```python
cs.connect(1234)
```

#### `reflection()`
Returns the raw reflection value (0–255).
```python
print(cs.reflection())
```

#### `detect_color()`
Returns the name of the detected color (see mapping above).
```python
print(cs.detect_color())  # e.g. "Red"
```

#### `set_update_rate(delay_ms=100)`
Sends the BLE command controlling how often the hardware reports sensor/button state. `0` turns updates off; otherwise 15–1000.
```python
cs.set_update_rate(1000)  # once a second
```

#### `on_button_press(callback)`
Registers a no-argument callback that fires once per button press (rising edge only).
```python
cs.on_button_press(lambda: print("Pressed!"))
```

---

## Full underlying API (inherited from `legoeducation`)

### Connection & device info

#### `disconnect()`
```python
cs.disconnect()
```

#### `search(timeout=5, card_color=None, card_serial=None)`
```python
found = cs.search(card_color=le.LEGO_COLOR_RED)
```

#### `info()`
```python
info = cs.info()
print(info.batteryLevel)
```

#### `device_uuid()`
```python
print(cs.device_uuid().uuid.hex())
```

#### `set_notification_callback(callback)`
Registers a raw callback fired on every hardware notification (lower-level than `on_button_press`); this is how you'd read `cs.sensor` as fast as the hardware reports it, rather than polling.
```python
cs.set_notification_callback(lambda n: print(cs.sensor.reflection))
```

#### `device_notification_request(delay_ms, blocking=True)`
The raw BLE command behind `set_update_rate()`.
```python
cs.device_notification_request(50)
```

#### `program_flow_notification(action, blocking=True)`
```python
cs.program_flow_notification(le.PROGRAM_ACTION_START)
```

### Light & sound

#### `light_color(color, pattern=le.LIGHT_PATTERN_SOLID, intensity=100, blocking=True)`
```python
cs.light_color(le.LEGO_COLOR_GREEN, pattern=le.LIGHT_PATTERN_BREATHE, intensity=75)
```

#### `beep(pattern=le.SOUND_PATTERN_BEEP_SINGLE, frequency=440, count=1, blocking=True)`
```python
cs.beep(frequency=220, count=3)
```

#### `stop_beep(blocking=True)`
```python
cs.beep(frequency=220, count=10, blocking=False)
time.sleep(3)
cs.stop_beep()
```

### Batching

#### `begin_batch()` / `end_batch(blocking=True)` / `batch(blocking=True)` / `cancel_batch()`
Not particularly useful on `colorSensor` (it has no motor/movement commands to synchronize), but inherited from the shared base class.
```python
with cs.batch():
    cs.light_color(le.LEGO_COLOR_GREEN)
```
