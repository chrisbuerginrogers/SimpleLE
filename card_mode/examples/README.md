# Examples

Small, self-contained programs. Each does one thing.

These sit inside `card_mode/` because they all use the broadcast protocol
reverse-engineered there — none of them open a GATT connection.

They split by **where they run**, which decides what they can do:

| | Runs on | Can transmit? | Needs |
|---|---|---|---|
| `stick_*.py` | the M5StickS3 | yes | `m5/` + the board libraries on the Stick |
| `mac_*.py` | your Mac | no — listens only | `lelib.py`, or `pico_lelib.py` + a Stick on USB |

A Mac cannot transmit a BLE advertisement at all, so anything that *drives* a
motor either runs on the Stick or goes through `pico_lelib` to a Stick. Anything
that only *reads* can run straight off the Mac.

## The screen and the beep

All three Stick examples share one look, in `stick_ui.py`:

- the screen fills with the **card's own color** and shows its name and serial
- a short high beep when a card is read, a low buzz when something is wrong
- the last card **stays on screen** after you lift it off the reader — that is
  the card whose details are in use, so blanking it would throw away the answer

`ui.card(color, serial)` draws and beeps; `ui.status('DRIVING')` adds a line
underneath while keeping the card's color; `ui.problem(...)` takes over the
screen in red and buzzes.

## On the Stick

| Example | What it does |
|---|---|
| `stick_drive_known_card.py` | Card color and serial are typed into the file. Drives the motor straight away — nothing else needed. |
| `stick_tap_to_drive.py` | Starts up, waits for a card tap on the RFID reader, then drives the motor belonging to *that* card. |
| `stick_read_card.py` | Tap a card and see what the reader makes of it. Use this to fill in the numbers for the other two. |
| `stick_log_cards.py` | Tap a stack of cards and log each one — RFID UID, color, serial and all twelve FD02 bytes — to a CSV on the Stick. Meant to be installed as `main.py` and carried around. |

Copy the example you want to the Stick. Its libraries — `picolib.py`,
`lego_card.py` and `stick_ui.py` — go over in one step from the Mac:

```python
import pico_lelib
pico_lelib.install()          # puts the board libraries on the Stick
```

## On the Mac

| Example | What it does |
|---|---|
| `mac_drive_known_card.py` | Same as the Stick version, but written on the Mac in lelib syntax and sent over USB to the Stick. |
| `mac_run_on_stick.py` | Runs any `stick_*.py` **on the Stick** from here, with its `print()` output coming back to your terminal. Ctrl-C stops it on the board too. |
| `mac_watch_card.py` | Watches everything broadcasting under one card — color sensor readings and joystick positions, live. No Stick needed. |
| `mac_fetch_cards.py` | `--install` puts `stick_log_cards.py` on the Stick as `main.py`; with no arguments it copies the logged cards back to `../card_taps.csv`. |

The quickest way to work on a Stick example is to leave it in this folder and
run it from the Mac — no copying, no Thonny:

```bash
python3 mac_run_on_stick.py stick_read_card.py
```

**In VS Code just press Run.** The Run button passes no arguments, so with none
it runs whichever file `EXAMPLE` names at the top of `mac_run_on_stick.py` —
edit that line to switch. It also runs from the workspace root rather than this
folder, which is why the `mac_*.py` files resolve their paths themselves.

## The catch: b2/b7

A motor checks two bytes of the beacon that are a per-card token. They cannot be
worked out from the color and serial, so a beacon with the right serial and the
wrong tokens is ignored.

They are **not stored on the card** — they differ per card across every card
sampled, so tapping gets you the color and serial for free but never the
tokens. Each card needs registering once.

Getting them depends on the example:

- **`stick_tap_to_drive.py`** reads the color and serial off the card, and looks
  the tokens up in its `TOKENS` table. Tap an unregistered card and it prints
  the line to paste in.
- **The known-card examples** need them typed in at the top of the file.
- **`mac_drive_known_card.py`** does not ask you for them: `pico_lelib`'s
  `connect()` scans the air for them, which the Mac can do and the Stick cannot.

To read a card's tokens, run `../watch_service_data.py` on the Mac
with a controller or color sensor carrying that card switched on, and take
bytes 2 and 7 of the FD02 payload.
