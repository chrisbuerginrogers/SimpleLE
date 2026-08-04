'''
Guided advertisement capture for the LEGO Education controller.

Answers two questions:
  A. Which payload bytes carry which physical input?
  B. What is the encoding — signed byte, or two packed 4-bit fields?

The existing capture in `data from controller` shows bytes 5 and 6 moving
with the levers, with values {0, 3, 13, 14, 16, -16}. Every magnitude in
that set is <= 16, which leaves the encoding ambiguous:

  - signed byte:      0xf0 = -16, 0x10 = +16, full deflection lands near +/-100
  - two 4-bit fields: 0xf0 = high nibble -1, 0x03 = low nibble +3, and each
                      byte would carry TWO axes (so bytes 5-6 = 4 axes total)

Both fit. The full-deflection segments below are what separate them:
if the magnitude tops out near 100 it's a signed byte; if it tops out at
7 it's packed nibbles. That is the single highest-value measurement in
this script, so don't skip the *_full_* segments or go easy on them —
push the levers to their mechanical stop.

The combination segments (both levers at once) are what catch a packed
layout: if left-alone moves only one nibble and both-levers lights up
two, the packing is settled.

Usage:
    python capture_controller.py
    python capture_controller.py --reps 5 --hold 8
    python capture_controller.py --manual        # wait for Enter, don't count down

For Protocol C1 (does the broadcast depend on what's listening?) run this
three times with no motor powered, with the single motor paired, and with
the double motor paired:

    python capture_controller.py --out ctrl_no_motor.csv
    python capture_controller.py --out ctrl_single.csv
    python capture_controller.py --out ctrl_double.csv

then compare the left_full_fwd rows across the three. Identical bytes mean
the controller broadcasts its own state blindly and the motor does the
interpreting; different bytes mean the controller is tailoring output to
the receiver.
'''

import sys

from adv_capture import main, segment

SEGMENTS = [
    segment('baseline',
            "Hands OFF. Don't touch anything.", hold=10.0),

    # ── single-lever, full deflection: the Protocol B scale test ──
    segment('left_full_fwd',
            "LEFT lever FULL forward, to the mechanical stop. Hold it there."),
    segment('left_full_back',
            "LEFT lever FULL back, to the mechanical stop. Hold it there."),
    segment('right_full_fwd',
            "RIGHT lever FULL forward, to the mechanical stop. Hold it there."),
    segment('right_full_back',
            "RIGHT lever FULL back, to the mechanical stop. Hold it there."),

    # ── partial deflection: deadzone + transfer curve ──
    segment('left_half_fwd',
            "LEFT lever HALF forward. Use the jig mark. Hold steady."),
    segment('left_quarter_fwd',
            "LEFT lever a QUARTER forward. Small but definite. Hold steady."),
    segment('left_barely_fwd',
            "LEFT lever just barely off center — the smallest push you can hold."),
    segment('right_half_fwd',
            "RIGHT lever HALF forward. Hold steady."),

    # ── combinations: catch a packed-nibble layout, and any mixing ──
    segment('both_full_fwd',
            "BOTH levers FULL forward at the same time."),
    segment('both_full_back',
            "BOTH levers FULL back at the same time."),
    segment('left_fwd_right_back',
            "LEFT full FORWARD, RIGHT full BACK (spin-in-place)."),

    # ── sideways: null result is still data ──
    segment('left_full_left',
            "LEFT lever pushed SIDEWAYS left. If it doesn't move that way, "
            "just leave it centered — a null result is useful."),
    segment('left_full_right',
            "LEFT lever pushed SIDEWAYS right. Leave centered if it doesn't move."),

    # ── buttons ──
    segment('button_held',
            "Press and HOLD the controller's button."),

    # ── closing baseline: confirms the resting value didn't drift ──
    segment('center_again',
            "Hands OFF again. Everything back to neutral.", hold=10.0),
]


if __name__ == '__main__':
    sys.exit(main('LEGO controller', SEGMENTS, default_out='capture_controller.csv'))
