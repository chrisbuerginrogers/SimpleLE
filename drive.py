import time
import threading
import collections
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from lelib import controller, doubleMotor, colorSensor

SERIAL = 1128
HISTORY = 200  # number of samples shown in the window

dm   = doubleMotor()
ctrl = controller()
cs   = colorSensor()

print("Connecting to double motor...")
dm.connect(SERIAL)
print("Connecting to controller...")
ctrl.connect(SERIAL)
print("Connecting to color sensor...")
cs.connect(SERIAL)
print("Connected. Use joysticks to drive. Ctrl+C to quit.")

reflection_buf = collections.deque([0] * HISTORY, maxlen=HISTORY)
stop_event = threading.Event()


def drive_loop():
    while not stop_event.is_set():
        left  = ctrl.left_position()
        right = ctrl.right_position()
        dm.movement_move_tank(left, right)
        reflection_buf.append(cs.reflection())
        time.sleep(0.05)
    dm.stop()


drive_thread = threading.Thread(target=drive_loop, daemon=True)
drive_thread.start()

fig, ax = plt.subplots()
ax.set_ylim(0, 255)
ax.set_xlim(0, HISTORY)
ax.set_title("Color Sensor — Reflection")
ax.set_xlabel("Samples")
ax.set_ylabel("Reflection (0–255)")
line, = ax.plot([], [], lw=2)

def init():
    line.set_data([], [])
    return (line,)

def update(_):
    data = list(reflection_buf)
    line.set_data(range(len(data)), data)
    return (line,)

ani = animation.FuncAnimation(fig, update, init_func=init, interval=50, blit=True)

try:
    plt.show()
finally:
    stop_event.set()
    drive_thread.join(timeout=2)
