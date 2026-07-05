import time
import threading
import legoeducation as le
from lelib import doubleMotor, colorSensor

SERIAL      = 7569
GEAR_RATIO  = 8

dm = doubleMotor()
cs = colorSensor()

dm.connect(SERIAL)
cs.connect(SERIAL)

# ── 1. home both motors to absolute 0 ────────────────────────────────────
print("Homing to 0…")
dm.motor_run_to_absolute_position(0, motor=le.MOTOR_LEFT,  speed=30)
dm.motor_run_to_absolute_position(0, motor=le.MOTOR_RIGHT, speed=30)

# ── 2. beep, zero the relative counters, release left motor ──────────────
dm.beep()
dm.motor_reset_relative_position(motor=le.MOTOR_LEFT)
dm.motor_reset_relative_position(motor=le.MOTOR_RIGHT)
dm.motor_set_end_state(le.MOTOR_END_STATE_COAST, motor=le.MOTOR_LEFT)
dm.motor_stop(motor=le.MOTOR_LEFT)
print("Turn the left motor to your target, then tap the motor.")

# ── 3. wait for tap via IMU callback ─────────────────────────────────────
tap_event = threading.Event()

def on_notification(_):
    if dm.imu_gesture.gesture == le.MOTION_GESTURE_TAPPED:
        tap_event.set()

dm.set_notification_callback(on_notification)
tap_event.wait()
dm.set_notification_callback(None)

motor_degrees = dm.motor[le.MOTOR_RIGHT].position   # cumulative, handles >360°
steps         = int(abs(motor_degrees) / GEAR_RATIO)
print(f"Tap! Motor: {abs(motor_degrees)}° → {steps} output degrees. Timer: {steps} seconds.")

# ── 4. drive right motor back to 0, proportional over timer duration ─────
for i in range(steps):
    target = round(motor_degrees * (1 - i / steps))
    dm.motor_run_to_relative_position(int(target), motor=le.MOTOR_RIGHT, speed=30, blocking=False)
    time.sleep(1)

dm.motor_run_to_relative_position(0, motor=le.MOTOR_RIGHT, speed=30)

# ── 5. beep and spin left motor one full rotation ────────────────────────
print("At 0.")
dm.beep()
dm.motor_run_for_degrees(360, motor=le.MOTOR_LEFT, speed=30)
