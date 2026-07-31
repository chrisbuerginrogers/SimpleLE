# controller — Full Reference

`lelib.controller` wraps `legoeducation.Controller`. It reads input from a LEGO controller's two joysticks and adds retry-based connecting plus `set_update_rate`/`on_button_press` on top of the full underlying API — every method below works directly on a `controller` instance.

```python
from lelib import controller
import legoeducation as le

ctrl = controller()
ctrl.connect(1234)  # your Bluetooth card serial
```

## Live sensor attributes

| Attribute | Fields | Description |
|---|---|---|
| `ctrl.button` | `.state` | Current button state. |
| `ctrl.sensor` | `.leftPercent`, `.rightPercent`, `.leftAngle`, `.rightAngle` | Raw joystick readings; `*Percent` is -100 to 100, `*Angle` is the physical stick angle. |

```python
print(ctrl.sensor.leftPercent, ctrl.sensor.rightPercent)
```

---

## lelib convenience methods

#### `connect(card_serial, card_color=None)`
Connects with up to 5 retries (1s delay) if the hardware reports "not ready".
```python
ctrl.connect(1234)
```

#### `left_up()` / `left_down()` / `left_released()`
`True` when the left joystick is pushed up, pushed down, or centered.
```python
if ctrl.left_up():
    print("left stick is up")
```

#### `right_up()` / `right_down()` / `right_released()`
Same, for the right joystick.
```python
if ctrl.right_released():
    print("right stick centered")
```

#### `left_position()` / `right_position()`
Raw percent position of a joystick (negative = down, positive = up).
```python
print(ctrl.left_position())
```

#### `drive(dm, t=100)`
Tank-drives a `doubleMotor` instance from both joysticks for `t × 0.1` seconds.
```python
from lelib import doubleMotor
dm = doubleMotor()
dm.connect(1234)
ctrl.drive(dm, t=50)  # drive for 5 seconds
```

#### `set_update_rate(delay_ms=100)`
Sends the BLE command controlling how often the hardware reports joystick/button state. `0` turns updates off; otherwise 15–1000.
```python
ctrl.set_update_rate(1000)  # once a second
```

#### `on_button_press(callback)`
Registers a no-argument callback that fires once per button press (rising edge only).
```python
ctrl.on_button_press(lambda: print("Pressed!"))
```

---

## Full underlying API (inherited from `legoeducation`)

### Connection & device info

#### `disconnect()`
```python
ctrl.disconnect()
```

#### `search(timeout=5, card_color=None, card_serial=None)`
```python
found = ctrl.search(card_color=le.LEGO_COLOR_RED)
```

#### `info()`
```python
info = ctrl.info()
print(info.batteryLevel)
```

#### `device_uuid()`
```python
print(ctrl.device_uuid().uuid.hex())
```

#### `set_notification_callback(callback)`
Registers a raw callback fired on every hardware notification (lower-level than `on_button_press`).
```python
ctrl.set_notification_callback(lambda n: print("notification"))
```

#### `device_notification_request(delay_ms, blocking=True)`
The raw BLE command behind `set_update_rate()`.
```python
ctrl.device_notification_request(50)
```

#### `program_flow_notification(action, blocking=True)`
```python
ctrl.program_flow_notification(le.PROGRAM_ACTION_START)
```

### Light & sound

#### `light_color(color, pattern=le.LIGHT_PATTERN_SOLID, intensity=100, blocking=True)`
```python
ctrl.light_color(le.LEGO_COLOR_BLUE, pattern=le.LIGHT_PATTERN_BREATHE, intensity=75)
```

#### `beep(pattern=le.SOUND_PATTERN_BEEP_SINGLE, frequency=440, count=1, blocking=True)`
```python
ctrl.beep(frequency=880, count=3)
```

#### `stop_beep(blocking=True)`
```python
ctrl.stop_beep()
```

### Batching

#### `begin_batch()` / `end_batch(blocking=True)` / `batch(blocking=True)` / `cancel_batch()`
Not particularly useful on `controller` (it has no motor/movement commands to synchronize), but inherited from the shared base class.
```python
with ctrl.batch():
    ctrl.light_color(le.LEGO_COLOR_GREEN)
```
