import time
from lelib import singleMotor, colorSensor

SERIAL = 1131

DROP_POSITION = 50
END_POSITION = -120
HOME_POSITION = 0

motor = singleMotor()
cs = colorSensor()

print("Connecting to single motor...")
motor.connect(SERIAL)
print("Connecting to color sensor...")
cs.connect(SERIAL)
print("Connected.")

motor.motor_reset_relative_position()

motor.motor_run_to_relative_position(DROP_POSITION)
time.sleep(1)
color = cs.detect_color()
print(f"Color reading: {color}")

motor.motor_run_to_relative_position(END_POSITION)
time.sleep(1)

motor.motor_run_to_relative_position(HOME_POSITION)
print("Done.")
