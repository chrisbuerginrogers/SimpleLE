# singleMotor — Full Reference

`lelib.singleMotor` wraps `legoeducation.SingleMotor`. It controls one motor over Bluetooth and adds retry-based connecting plus two convenience methods (`set_update_rate`, `on_button_press`) on top of the full underlying `legoeducation` API — every method below works directly on a `singleMotor` instance.

```python
from lelib import singleMotor

motor = singleMotor()
motor.connect(1234)  # your Bluetooth card serial
```

## Live sensor attributes

Updated automatically in the background as notifications arrive (see `set_update_rate`).

| Attribute | Fields | Description |
|---|---|---|
| `motor.button` | `.state` (`le.BUTTON_STATE_PRESSED` / `le.BUTTON_STATE_RELEASED`) | Current button state. |
| `motor.motor` | `.position`, `.speed`, `.power`, `.absolutePosition`, `.motorState`, `.gesture` | Live motor telemetry. `.position` is cumulative (tracks past 360°); `.absolutePosition` is 0–359. |
| `motor.info_device` | `.batteryLevel`, `.UsbPowerState` | Battery and USB status. |

```python
print(motor.motor.position)      # cumulative degrees turned
print(motor.button.state == le.BUTTON_STATE_PRESSED)
```

---

## lelib convenience methods

#### `connect(card_serial, card_color=None)`
Connects with up to 5 retries (1s delay) if the hardware reports "not ready".
```python
motor.connect(1234)
```

#### `spin(rotations=1)`
Runs the motor for a number of full rotations.
```python
motor.spin(2)  # 2 full rotations
```

#### `stop()`
Stops the motor immediately.
```python
motor.stop()
```

#### `set_speed(speed)`
Sets the motor's rotation speed as a percentage (-100 to 100).
```python
motor.set_speed(50)
```

#### `run()`
Runs the motor continuously until `stop()` is called.
```python
motor.run()
```

#### `set_update_rate(delay_ms=100)`
Sends the BLE command controlling how often the hardware reports sensor/button state. `0` turns updates off; otherwise 15–1000.
```python
motor.set_update_rate(1000)  # once a second
```

#### `on_button_press(callback)`
Registers a no-argument callback that fires once per button press (rising edge only).
```python
motor.on_button_press(lambda: print("Pressed!"))
```

---

## Full underlying API (inherited from `legoeducation`)

### Connection & device info

#### `disconnect()`
Disconnects and returns the hardware to Bluetooth broadcast mode.
```python
motor.disconnect()
```

#### `search(timeout=5, card_color=None, card_serial=None)`
Scans for nearby hardware matching the given filters, without connecting.
```python
found = motor.search(card_color=le.LEGO_COLOR_RED)
```

#### `info()`
Returns technical info (firmware/RPC versions, battery, etc.) about the hardware.
```python
info = motor.info()
print(info.batteryLevel)
```

#### `device_uuid()`
Returns the hardware's permanent UUID.
```python
print(motor.device_uuid().uuid.hex())
```

#### `set_notification_callback(callback)`
Registers a raw callback fired on every hardware notification (lower-level than `on_button_press`).
```python
motor.set_notification_callback(lambda n: print("notification"))
```

#### `device_notification_request(delay_ms, blocking=True)`
The raw BLE command behind `set_update_rate()`.
```python
motor.device_notification_request(50)
```

#### `program_flow_notification(action, blocking=True)`
Tells the hardware a program has started or stopped.
```python
motor.program_flow_notification(le.PROGRAM_ACTION_START)
```

### Motor control

#### `motor_set_speed(speed, blocking=True)`
Sets rotation speed as a percentage (-100 to 100); positive = clockwise.
```python
motor.motor_set_speed(50)
```

#### `motor_run(direction=le.MOTOR_MOVE_DIRECTION_CLOCKWISE, speed=None, blocking=True)`
Runs the motor continuously until stopped.
```python
motor.motor_run()
```

#### `motor_run_for_time(time_ms, direction=..., speed=None, blocking=True)`
Runs the motor for a duration, then stops.
```python
motor.motor_run_for_time(2000)  # 2 seconds
```

#### `motor_run_for_degrees(degrees, direction=..., speed=None, blocking=True)`
Rotates the motor by a number of degrees, then stops.
```python
motor.motor_run_for_degrees(180)
```

#### `motor_reset_relative_position(position=0, blocking=True)`
Sets the current relative-position counter to a new value (default 0).
```python
motor.motor_reset_relative_position()
```

#### `motor_run_to_relative_position(position, speed=None, blocking=True)`
Rotates to a target position measured from the last reset point. Not wrapped to 0–360, so negative or >360 targets work directly.
```python
motor.motor_run_to_relative_position(-120)
```

#### `motor_run_to_absolute_position(position, direction=le.MOTOR_MOVE_DIRECTION_SHORTEST, speed=None, blocking=True)`
Rotates to a fixed position 0–359 (position is taken mod 360).
```python
motor.motor_run_to_absolute_position(90)
```

#### `motor_set_duty_cycle(duty_cycle, blocking=True)`
Directly drives the motor with a raw duty cycle (-100 to 100), bypassing normal speed control.
```python
motor.motor_set_duty_cycle(50)
```

#### `motor_stop(blocking=True)`
Stops the motor using the current end state (see below).
```python
motor.motor_stop()
```

#### `motor_set_end_state(end_state, blocking=True)`
Sets what the motor does when stopped: `le.MOTOR_END_STATE_COAST`, `_BRAKE`, `_HOLD`, `_CONTINUE`, `_SMART_COAST`, `_SMART_BRAKE`.
```python
motor.motor_set_end_state(le.MOTOR_END_STATE_HOLD)
```

#### `motor_set_acceleration(acceleration, deceleration, blocking=True)`
Sets how fast the motor speeds up / slows down (0–100 each).
```python
motor.motor_set_acceleration(25, 75)
```

#### `done(motor=None)`
Returns `True` if no motor commands are still running (useful with `blocking=False`).
```python
motor.motor_run_for_degrees(360, speed=10, blocking=False)
while not motor.done():
    time.sleep(0.1)
```

### Light & sound

#### `light_color(color, pattern=le.LIGHT_PATTERN_SOLID, intensity=100, blocking=True)`
Sets the button light color/pattern/brightness.
```python
motor.light_color(le.LEGO_COLOR_BLUE, pattern=le.LIGHT_PATTERN_BREATHE, intensity=75)
```

#### `beep(pattern=le.SOUND_PATTERN_BEEP_SINGLE, frequency=440, count=1, blocking=True)`
Plays a beep sound pattern.
```python
motor.beep(frequency=880, count=3)
```

#### `stop_beep(blocking=True)`
Stops any ongoing beep.
```python
motor.stop_beep()
```

### Batching (send multiple commands in one BLE packet)

#### `begin_batch()` / `end_batch(blocking=True)`
Queues commands, then sends them together so they start nearly simultaneously.
```python
motor.begin_batch()
motor.motor_set_speed(50)
motor.light_color(le.LEGO_COLOR_GREEN)
motor.end_batch()
```

#### `batch(blocking=True)`
Context-manager form of `begin_batch()`/`end_batch()`.
```python
with motor.batch():
    motor.motor_set_speed(50)
    motor.light_color(le.LEGO_COLOR_GREEN)
```

#### `cancel_batch()`
Discards a batch without sending it; returns the number of commands dropped.
```python
motor.begin_batch()
motor.motor_set_speed(50)
n = motor.cancel_batch()
```
