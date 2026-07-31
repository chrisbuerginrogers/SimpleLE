import time
import legoeducation as le
from lelib import controller

SERIAL = 1133

COLORS = [
    le.LEGO_COLOR_RED,
    le.LEGO_COLOR_YELLOW,
    le.LEGO_COLOR_GREEN,
    le.LEGO_COLOR_BLUE,
    le.LEGO_COLOR_PURPLE,
]

ctrl = controller()

print("Connecting to controller...")
ctrl.connect(SERIAL)
print("Connected.")

ctrl.set_update_rate(100)  # ten times a second

index = 0


def cycle_light():
    global index
    index = (index + 1) % len(COLORS)
    ctrl.light_color(COLORS[index], blocking=False)


ctrl.on_button_press(cycle_light)

print("Press the controller button to cycle the light color. Ctrl+C to quit.")
try:
    while True:
        time.sleep(0.1)
except KeyboardInterrupt:
    pass
