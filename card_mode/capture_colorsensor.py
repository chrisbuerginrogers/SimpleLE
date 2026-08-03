'''
Guided advertisement capture for the LEGO Education color sensor.

The headline question is already answered: **byte 5 is the live detected
color**, as a raw firmware code, broadcast with no GATT connection needed.
0xff is LEGO_COLOR_NONE (nothing detected). See Card_mode.md.

So this capture is no longer a yes/no hunt. It's here to pin down the
rest:

  - Confirm the full color code table end to end. Only NONE(-1),
    PURPLE(2) and RED(9) have actually been observed; the remaining codes
    are assumed from `legoeducation/rpc_message.py`, not verified against
    real bricks.
  - Find out whether **reflection / light level** is broadcast too. Byte 6
    read 0x00 with a red brick at contact, which is not what a reflection
    byte would do — so either it's elsewhere, or it isn't advertised at
    all and `colorSensor.reflection()` genuinely requires a connection.
    The distance sweep is what answers this.
  - Establish how the sensor reports ambient extremes (fully covered,
    pointed at a bright light).

Don't confuse the two colors in play. Byte 1 is the color of the CARD
tapped against the sensor and won't change when you wave a brick at it.
Byte 5 is what the sensor is looking at right now.

Physical setup that makes the data usable:
  - Fix the distance. Rest each brick flat against the sensor face, or
    use a spacer, but keep it identical across segments — otherwise a
    reflection byte and a color byte are impossible to tell apart.
  - Keep room lighting constant for everything except the ambient_* segments.
  - Use LEGO's own colored elements where you can; the sensor is
    calibrated for them and off-brand colors read as NoColor.

Usage:
    python capture_colorsensor.py
    python capture_colorsensor.py --reps 5 --hold 8
    python capture_colorsensor.py --manual      # wait for Enter — easier when
                                                # you're swapping bricks by hand

--manual is genuinely worth it here: a 3-second countdown is not long
enough to swap a brick and get it seated flat.
'''

import sys

from adv_capture import main, segment

SEGMENTS = [
    segment('baseline',
            "Sensor pointed at nothing in particular. Don't touch it.", hold=10.0),

    # ── the color sweep: does any byte follow the brick? ──
    segment('color_red',
            "Hold a RED brick flat against the sensor face."),
    segment('color_yellow',
            "Hold a YELLOW brick flat against the sensor face."),
    segment('color_blue',
            "Hold a BLUE brick flat against the sensor face."),
    segment('color_green',
            "Hold a GREEN brick flat against the sensor face."),
    segment('color_white',
            "Hold a WHITE brick flat against the sensor face."),
    segment('color_black',
            "Hold a BLACK brick flat against the sensor face."),
    segment('color_magenta',
            "Hold a MAGENTA brick flat against the sensor face. Skip if you "
            "don't have one — just leave the sensor clear."),
    segment('color_azure',
            "Hold an AZURE / light-blue brick against the sensor. Skip if "
            "you don't have one."),

    # ── distance sweep: separates a reflection byte from a color byte ──
    # Same white brick throughout, so color is held constant and only
    # the returned light level changes.
    segment('white_contact',
            "WHITE brick touching the sensor face."),
    segment('white_1cm',
            "WHITE brick about 1 cm away."),
    segment('white_3cm',
            "WHITE brick about 3 cm away."),
    segment('white_far',
            "WHITE brick about 10 cm away, or just remove it."),

    # ── ambient light ──
    segment('ambient_dark',
            "Cup your hand tightly over the sensor to block all light."),
    segment('ambient_bright',
            "Point the sensor at a bright light or window."),

    # ── button ──
    segment('button_held',
            "Press and HOLD the sensor's button."),

    # ── card taps: confirms which byte is the card, as a control ──
    # If nothing else in this capture moves, these segments at least prove
    # the harness is working and pointed at the right device.
    segment('card_tap_a',
            "Tap ONE card against the sensor and leave it in place."),
    segment('card_tap_b',
            "Tap a DIFFERENT-colored card and leave it in place."),

    segment('idle_again',
            "Remove everything. Hands off.", hold=10.0),
]


if __name__ == '__main__':
    sys.exit(main('LEGO color sensor', SEGMENTS, default_out='capture_colorsensor.csv'))
