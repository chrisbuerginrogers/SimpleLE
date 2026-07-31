'''
Connects to whatever LEGO Education device is tagged with card serial 1126
(RED) and live-plots its reading. Checks for a single motor first — if one's
connected, plots abs(position) clamped to 0-800 degrees and linearly mapped
to 65-85 (rounded to the nearest integer) — otherwise falls back to the
color/light sensor and plots reflection. Samples are captured via the
notification callback, i.e. every time the device pushes a BLE update, not
on a polling timer, so this reads as fast as the hardware sends data.
Ctrl+C or close the plot window to stop.
'''

import time
import collections
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import legoeducation as le
from lelib import colorSensor, singleMotor

SERIAL = 1126
CARD_COLOR = le.LEGO_COLOR_RED
HISTORY = 300  # number of samples shown in the window
POSITION_RANGE = 800  # clamp |position| to this many degrees before mapping
MAPPED_RANGE = (65, 85)


def map_position(position):
    magnitude = min(abs(position), POSITION_RANGE)
    lo, hi = MAPPED_RANGE
    return round(lo + magnitude / POSITION_RANGE * (hi - lo))


def try_connect(cls, label):
    print(f"Checking for a {label} (card {SERIAL}/{CARD_COLOR})...")
    device = cls()
    try:
        device.connect(SERIAL, card_color=CARD_COLOR)
    except ConnectionError:
        return None
    print(f"Connected to {label}.")
    return device


device = try_connect(singleMotor, "single motor") or try_connect(colorSensor, "light sensor")
if device is None:
    raise SystemExit(f"No LEGO device found on card {SERIAL}/{CARD_COLOR}.")

is_motor = isinstance(device, singleMotor)
read_value = (lambda: map_position(device.motor.position)) if is_motor else device.reflection
ylabel = f"Mapped position ({MAPPED_RANGE[0]}-{MAPPED_RANGE[1]})" if is_motor else "Reflection (0-255)"
plot_title = "Motor — Mapped Position" if is_motor else "Light Sensor — Reflection"

print("Reading as fast as the device reports. Close the window to quit.")

value_buf = collections.deque([0] * HISTORY, maxlen=HISTORY)
sample_count = 0
start_time = time.monotonic()


def on_notification(_):
    global sample_count
    value_buf.append(read_value())
    sample_count += 1


device.set_notification_callback(on_notification)

fig, ax = plt.subplots()
ax.set_ylim(*MAPPED_RANGE) if is_motor else ax.set_ylim(0, 255)
ax.set_xlim(0, HISTORY)
ax.set_xlabel("Samples")
ax.set_ylabel(ylabel)
title = ax.set_title(plot_title)
line, = ax.plot([], [], lw=2)


def init():
    line.set_data([], [])
    return (line,)


def update(_):
    data = list(value_buf)
    line.set_data(range(len(data)), data)
    elapsed = time.monotonic() - start_time
    rate = sample_count / elapsed if elapsed > 0 else 0
    title.set_text(f"{plot_title} ({rate:.1f} samples/sec)")
    return (line, title)


ani = animation.FuncAnimation(fig, update, init_func=init, interval=30, blit=False)

try:
    plt.show()
finally:
    device.set_notification_callback(None)
