# doubleMotor — Full Reference

`lelib.doubleMotor` wraps `legoeducation.DoubleMotor` (which itself extends `SingleMotor`). It controls a paired left/right drive motor and adds retry-based connecting plus `set_update_rate`/`on_button_press` on top of the full underlying API — every method below (including all `singleMotor` per-motor methods) works directly on a `doubleMotor` instance.

```python
from lelib import doubleMotor
import legoeducation as le

dm = doubleMotor()
dm.connect(1234)  # your Bluetooth card serial
```

Per-motor commands take a `motor=` argument: `le.MOTOR_LEFT` (0), `le.MOTOR_RIGHT` (1), or `le.MOTOR_BOTH` (2, the default for most).

## Live sensor attributes

| Attribute | Fields | Description |
|---|---|---|
| `dm.button` | `.state` | Current button state. |
| `dm.motor[le.MOTOR_LEFT]` / `dm.motor[le.MOTOR_RIGHT]` | `.position`, `.speed`, `.power`, `.absolutePosition`, `.motorState`, `.gesture` | Live per-motor telemetry (`dm.motor` is a 2-element list). |
| `dm.imu_gesture` | `.gesture` (`le.MOTION_GESTURE_TAPPED`, `_DOUBLE_TAPPED`, `_COLLISION`, `_SHAKE`, `_FREEFALL`, or `_NO_GESTURE`) | Latest detected motion gesture. |
| `dm.imu_device` | `.orientation`, `.yaw`, `.pitch`, `.roll`, `.accelerometerX/Y/Z`, `.gyroscopeX/Y/Z` | Full IMU telemetry. |

```python
print(dm.motor[le.MOTOR_RIGHT].position)  # cumulative degrees, right motor
print(dm.imu_gesture.gesture == le.MOTION_GESTURE_TAPPED)
```

---

## lelib convenience methods

#### `connect(card_serial, card_color=None)`
Connects with up to 5 retries (1s delay) if the hardware reports "not ready".
```python
dm.connect(1234)
```

#### `move_steps(step=1)`
Moves both motors together; one step = 180°.
```python
dm.move_steps(2)  # 360°
```

#### `run()`
Runs both motors continuously (backward direction).
```python
dm.run()
```

#### `run_time(time=2000)`
Runs both motors together for a fixed duration in milliseconds.
```python
dm.run_time(1500)
```

#### `run_left(degrees=None)` / `run_right(degrees=None)`
Runs one side counter-clockwise; continuously if `degrees` is `None`, otherwise for that many degrees.
```python
dm.run_left(90)
dm.run_right()  # continuous until stop()
```

#### `turn_left(degrees=90)` / `turn_right(degrees=90)`
Turns the robot in place by the given number of degrees.
```python
dm.turn_left(90)
```

#### `set_speed(speed)` / `set_speed_left(speed)` / `set_speed_right(speed)`
Sets speed (-100 to 100) for both motors + movement system, or one side only.
```python
dm.set_speed(60)
dm.set_speed_left(30)
```

#### `stop()`
Stops both motors.
```python
dm.stop()
```

#### `set_update_rate(delay_ms=100)`
Sends the BLE command controlling how often the hardware reports sensor/button/IMU state. `0` turns updates off; otherwise 15–1000.
```python
dm.set_update_rate(1000)  # once a second
```

#### `on_button_press(callback)`
Registers a no-argument callback that fires once per button press (rising edge only).
```python
dm.on_button_press(lambda: print("Pressed!"))
```

---

## Full underlying API (inherited from `legoeducation`)

### Connection & device info

#### `disconnect()` / `search(...)` / `info()` / `device_uuid()` / `set_notification_callback(callback)` / `device_notification_request(delay_ms)` / `program_flow_notification(action)`
Same shared behavior as on `singleMotor` — see [singleMotor.md](singleMotor.md#connection--device-info).
```python
dm.disconnect()
```

### Per-motor control (same as singleMotor, with `motor=` argument)

#### `motor_set_speed(speed, motor=le.MOTOR_LEFT, blocking=True)`
```python
dm.motor_set_speed(-50, motor=le.MOTOR_LEFT)  # negative = counter-clockwise
```

#### `motor_run(direction=..., motor=le.MOTOR_LEFT, speed=None, blocking=True)`
```python
dm.motor_run(motor=le.MOTOR_BOTH)
```

#### `motor_run_for_time(time_ms, direction=..., motor=le.MOTOR_LEFT, speed=None, blocking=True)`
```python
dm.motor_run_for_time(1000, motor=le.MOTOR_RIGHT)
```

#### `motor_run_for_degrees(degrees, direction=..., motor=le.MOTOR_LEFT, speed=None, blocking=True)`
```python
dm.motor_run_for_degrees(90, motor=le.MOTOR_RIGHT)
```

#### `motor_reset_relative_position(motor=le.MOTOR_BOTH, position=0, blocking=True)`
```python
dm.motor_reset_relative_position(motor=le.MOTOR_LEFT, position=180)
```

#### `motor_run_to_relative_position(position, motor=le.MOTOR_LEFT, speed=None, blocking=True)`
```python
dm.motor_run_to_relative_position(90, motor=le.MOTOR_LEFT, speed=30, blocking=False)
```

#### `motor_run_to_absolute_position(position, direction=le.MOTOR_MOVE_DIRECTION_SHORTEST, motor=le.MOTOR_LEFT, speed=None, blocking=True)`
```python
dm.motor_run_to_absolute_position(180, motor=le.MOTOR_LEFT)
```

#### `motor_set_duty_cycle(duty_cycle, motor=le.MOTOR_LEFT, blocking=True)`
```python
dm.motor_set_duty_cycle(50, motor=le.MOTOR_RIGHT)
```

#### `motor_stop(motor=le.MOTOR_LEFT, blocking=True)`
```python
dm.motor_stop(motor=le.MOTOR_BOTH)
```

#### `motor_set_end_state(end_state, motor=le.MOTOR_LEFT, blocking=True)`
```python
dm.motor_set_end_state(le.MOTOR_END_STATE_COAST, motor=le.MOTOR_RIGHT)
```

#### `motor_set_acceleration(acceleration, deceleration, motor=le.MOTOR_LEFT, blocking=True)`
```python
dm.motor_set_acceleration(50, 50, motor=le.MOTOR_RIGHT)
```

#### `done(motor=None)`
```python
dm.motor_run_for_degrees(360, motor=le.MOTOR_LEFT, speed=10, blocking=False)
while not dm.done(motor=le.MOTOR_LEFT):
    time.sleep(0.1)
```

### Whole-robot movement (drives both motors together)

#### `movement_move(direction=le.MOVEMENT_DIRECTION_FORWARD, speed=None, blocking=True)`
Drives continuously in a direction (`_FORWARD`, `_BACKWARD`, `_LEFT`, `_RIGHT`).
```python
dm.movement_move(direction=le.MOVEMENT_DIRECTION_BACKWARD, speed=50)
```

#### `movement_move_for_time(time_ms, direction=..., speed=None, blocking=True)`
```python
dm.movement_move_for_time(2000)
```

#### `movement_move_for_degrees(degrees, direction=le.MOVEMENT_MOVE_DIRECTION_FORWARD, speed=None, blocking=True)`
```python
dm.movement_move_for_degrees(360)  # one full wheel rotation, forward
```

#### `movement_move_tank(speed_left, speed_right, blocking=True)`
Independent left/right speeds (-100 to 100 each) — classic tank drive.
```python
dm.movement_move_tank(40, 40)  # straight forward at 40%
```

#### `movement_move_tank_for_degrees(degrees, speed_left=50, speed_right=50, blocking=True)`
Tank drive until the faster wheel has turned `degrees`.
```python
dm.movement_move_tank_for_degrees(360, speed_left=30, speed_right=60)
```

#### `movement_turn_for_degrees(degrees, direction=le.MOVEMENT_TURN_DIRECTION_LEFT, speed=None, blocking=True)`
Turns in place using the IMU to confirm rotation.
```python
dm.movement_turn_for_degrees(90, direction=le.MOVEMENT_TURN_DIRECTION_RIGHT)
```

#### `movement_stop(blocking=True)`
```python
dm.movement_stop()
```

#### `movement_set_speed(speed, blocking=True)`
```python
dm.movement_set_speed(-20)  # negative drives backward
```

#### `movement_set_end_state(end_state, blocking=True)`
```python
dm.movement_set_end_state(le.MOTOR_END_STATE_BRAKE)
```

#### `movement_set_acceleration(acceleration, deceleration, blocking=True)`
```python
dm.movement_set_acceleration(20, 80)
```

#### `movement_set_turn_steering(steering, blocking=True)`
Adjusts turn sharpness (0–100) by biasing the left/right balance.
```python
dm.movement_set_turn_steering(50)
```

### IMU (yaw)

#### `imu_set_yaw_face(yaw_face, blocking=True)`
Chooses which physical side is "up" for yaw readings (`le.DEVICE_FACE_TOP/_FRONT/_RIGHT/_BOTTOM/_BACK/_LEFT`).
```python
dm.imu_set_yaw_face(le.DEVICE_FACE_RIGHT)
```

#### `imu_reset_yaw_axis(value=0, blocking=True)`
Resets the yaw reading to a new value.
```python
dm.imu_reset_yaw_axis()
```

### Light & sound

#### `light_color(color, pattern=le.LIGHT_PATTERN_SOLID, intensity=100, blocking=True)`
```python
dm.light_color(le.LEGO_COLOR_RED)
```

#### `beep(pattern=le.SOUND_PATTERN_BEEP_SINGLE, frequency=440, count=1, blocking=True)` / `stop_beep(blocking=True)`
```python
dm.beep(pattern=le.SOUND_PATTERN_BEEP_DOUBLE, frequency=880)
```

### Batching

#### `begin_batch()` / `end_batch(blocking=True)` / `batch(blocking=True)` / `cancel_batch()`
Sends multiple per-motor commands together so they start simultaneously (movement_* commands can't be batched — use per-motor commands instead).
```python
with dm.batch():
    dm.motor_run(motor=le.MOTOR_LEFT, speed=50)
    dm.motor_run(motor=le.MOTOR_RIGHT, speed=10)
```
