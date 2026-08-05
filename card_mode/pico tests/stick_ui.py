'''
stick_ui — the screen and speaker, shared by every Stick example.

  >>> Runs ON the M5StickS3. Needs m5/ on the board. <<<

One look for all the examples: the screen fills with the card's own color and
names it, a short high beep says a card was read, a low buzz says something is
wrong. Written once here so the examples stay short and behave the same.

    ui = stick_ui.UI()
    ui.looking('TAP A CARD')
    ui.card(color, serial)             # fills the screen, beeps
    ui.status('DRIVING')               # a line under the card, color kept
    ui.problem('NEED TOKENS', 'run watch_service_data')

The screen deliberately keeps showing the last card after it is lifted off the
reader. That card's color and serial are the ones in use, so blanking them
would throw away the answer.
'''

from m5.m5_audio import Speaker
from m5.m5_display import Display, WHITE, BLACK, FONT_8X8

GRAY = 0x8410
RED = 0xF800

# ── the missing letters ───────────────────────────────────────────────────
# m5_display's FONT_8X8 ships 31 glyphs -- digits plus C H P V W X Y Z and a
# few lowercase. draw_char() silently falls back to a blank for anything else,
# so "PURPLE" came out as "P  P  " and "ORANGE" as nothing at all.
#
# These are the same 8x8 font the existing glyphs come from (C, H, P, V, W, X,
# Y and Z here match m5_display byte for byte), just the uppercase letters it
# left out. Patched in rather than edited into m5_display.py so the m5 library
# stays exactly as it is in the micropython repo -- the permanent home for
# these is that file's FONT_8X8, if you want them everywhere.
_MISSING_GLYPHS = {
    'A': bytes([0x0C, 0x1E, 0x33, 0x33, 0x3F, 0x33, 0x33, 0x00]),
    'B': bytes([0x3F, 0x66, 0x66, 0x3E, 0x66, 0x66, 0x3F, 0x00]),
    'D': bytes([0x1F, 0x36, 0x66, 0x66, 0x66, 0x36, 0x1F, 0x00]),
    'E': bytes([0x7F, 0x46, 0x16, 0x1E, 0x16, 0x46, 0x7F, 0x00]),
    'F': bytes([0x7F, 0x46, 0x16, 0x1E, 0x16, 0x06, 0x0F, 0x00]),
    'G': bytes([0x3C, 0x66, 0x03, 0x03, 0x73, 0x66, 0x7C, 0x00]),
    'I': bytes([0x1E, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x1E, 0x00]),
    'J': bytes([0x78, 0x30, 0x30, 0x30, 0x33, 0x33, 0x1E, 0x00]),
    'K': bytes([0x67, 0x66, 0x36, 0x1E, 0x36, 0x66, 0x67, 0x00]),
    'L': bytes([0x0F, 0x06, 0x06, 0x06, 0x46, 0x66, 0x7F, 0x00]),
    'M': bytes([0x63, 0x77, 0x7F, 0x7F, 0x6B, 0x63, 0x63, 0x00]),
    'N': bytes([0x63, 0x67, 0x6F, 0x7B, 0x73, 0x63, 0x63, 0x00]),
    'O': bytes([0x1C, 0x36, 0x63, 0x63, 0x63, 0x36, 0x1C, 0x00]),
    'Q': bytes([0x1E, 0x33, 0x33, 0x33, 0x3B, 0x1E, 0x38, 0x00]),
    'R': bytes([0x3F, 0x66, 0x66, 0x3E, 0x36, 0x66, 0x67, 0x00]),
    'S': bytes([0x1E, 0x33, 0x07, 0x0E, 0x38, 0x33, 0x1E, 0x00]),
    'T': bytes([0x3F, 0x2D, 0x0C, 0x0C, 0x0C, 0x0C, 0x1E, 0x00]),
    'U': bytes([0x33, 0x33, 0x33, 0x33, 0x33, 0x33, 0x3F, 0x00]),
}

for _ch, _glyph in _MISSING_GLYPHS.items():
    FONT_8X8.setdefault(_ch, _glyph)      # never overwrite an existing glyph

# Each card color as RGB565, so the screen can show the color itself rather
# than only name it. Values follow LEGO's own color map where it has one.
CARD_COLORS = {
    1: 0xD8C4,   # red
    2: 0xFEA0,   # yellow
    3: 0x0377,   # blue
    4: 0x05B6,   # teal
    5: 0x6546,   # green
    6: 0x4972,   # purple
    7: 0xFFFF,   # white
    8: 0xE2D3,   # magenta
    9: 0xF3E4,   # orange
    10: 0x7DFD,  # azure
}

COLOR_NAMES = {1: 'RED', 2: 'YELLOW', 3: 'BLUE', 4: 'TEAL', 5: 'GREEN',
               6: 'PURPLE', 7: 'WHITE', 8: 'MAGENTA', 9: 'ORANGE', 10: 'AZURE'}

# Yellow and white backgrounds need dark text to stay readable.
_DARK_TEXT_ON = (2, 7)

BEEP_OK = (1760, 120)      # short and high: card read
BEEP_BAD = (220, 250)      # low buzz: not a card we can use


def color_name(color):
    return COLOR_NAMES.get(color, str(color))


class UI(object):
    def __init__(self, volume=70):
        self.display = Display()
        self.speaker = Speaker(volume=volume)
        self.background = BLACK
        self.text = WHITE

    # ── drawing ───────────────────────────────────────────────────────
    def _line(self, y, text, color, scale=1, spacing=2):
        '''Draw one line centered, blanking the rest of that line first.

        Everything is drawn uppercase. The font has all 26 capitals once
        _MISSING_GLYPHS is patched in, but only nine lowercase letters, so
        mixed-case text comes out full of holes.
        '''
        cell = 8 * scale + spacing
        wide = (self.display.WIDTH + spacing) // cell
        text = str(text).upper()[:wide]
        self.display.draw_text(0, y, ' ' * wide, color, self.background,
                               scale=scale, spacing=spacing)
        x = (self.display.WIDTH - self.display.text_width(text, scale, spacing)) // 2
        self.display.draw_text(x, y, text, color, self.background,
                               scale=scale, spacing=spacing)

    def looking(self, message='LOOKING', hint='tap a card'):
        '''Waiting for a card. Only shown before the first one arrives.'''
        self.background = BLACK
        self.text = WHITE
        self.display.fill(BLACK)
        self._line(40, message, WHITE, scale=2, spacing=0)
        self._line(70, hint, GRAY)

    def card(self, color, serial, beep=True):
        '''Fill the screen with the card's own color and name it.'''
        self.background = CARD_COLORS.get(color, BLACK)
        self.text = BLACK if color in _DARK_TEXT_ON else WHITE
        self.display.fill(self.background)
        self._line(20, color_name(color), self.text, scale=2, spacing=0)
        self._line(50, '#{}'.format(serial), self.text, scale=2, spacing=0)
        if beep:
            self.beep()

    def status(self, message):
        '''A line under the card, keeping the card's color on screen.'''
        self._line(90, message, self.text)

    def problem(self, headline, detail='', beep=True):
        '''Something is wrong, on a black screen so it cannot be missed.'''
        self.background = BLACK
        self.text = WHITE
        self.display.fill(BLACK)
        self._line(34, headline, RED, scale=2, spacing=0)
        if detail:
            self._line(70, detail, GRAY)
        if beep:
            self.buzz()

    # ── sound ─────────────────────────────────────────────────────────
    def beep(self):
        '''Short high note: a card was read.'''
        self.speaker.tone(*BEEP_OK)

    def buzz(self):
        '''Low note: not a card we can use.'''
        self.speaker.tone(*BEEP_BAD)

    def close(self):
        self.speaker.deinit()
