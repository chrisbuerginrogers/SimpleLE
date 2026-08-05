# SimpleLE — Claude context

## What this project is
A thin Python wrapper around the `legoeducation` pip package. The goal is simpler method names and automatic Bluetooth reconnect logic for classroom use with LEGO Education hardware.

## Key files
- `lelib.py` — the library (four classes: `singleMotor`, `doubleMotor`, `controller`,
  `colorSensor`). **Keep it to GATT-connected work only.** Anything addressed by card
  rather than by a connected object belongs in `cardlib.py`, deliberately, so the
  simple LEGO library doesn't get mixed up with the broadcast protocol.
- `lelib.md` — API reference; keep in sync with `lelib.py` whenever methods change
- `cardlib.py` — connectionless: `find_cards()`, `read_sensor()`, `set_speed()`. Named by
  card, no pairing, doesn't consume a device's one connection slot. Imports `lelib` for
  the motor classes `set_speed()` needs; the dependency runs one way only.
- `cardlib.md` — its API reference
- `pico_lelib.py` — same syntax as lelib, but drives motors by BLE *broadcast*. macOS
  cannot transmit an advertisement, so commands go over USB serial to a MicroPython
  board (`card_mode/pico tests/pico_server.py` + `picolib.py`) which does the radio
  work. Only the subset a broadcast can express — no `spin`/`turn_left`/`move_steps`,
  since those need feedback the beacon has no room for. Also the file-transfer
  route to the board: `install()` (libraries), `install_main()` (a script as
  `main.py`), `fetch_file()` (a file back off). Anything that talks to the board
  stops what it was running, so `install_main`/`fetch_file` reboot it afterwards.
- `projects/` — scripts that build something with lelib (e.g. `drive.py` — joystick tank-drive + live matplotlib color-sensor graph)
- `tests/` — diagnostic/scratch scripts for exercising lelib or BLE hardware, not end-user builds
- `card_mode/` — BLE advertisement reverse-engineering: decoding card taps, device
  type, sensor readings and controller sticks straight from the advertisement, with
  no GATT connection, plus the transmit side that drives motors by broadcast.
  Self-contained (the scripts import each other by bare module name, so run them
  from inside the folder). `Card_mode.md` is the findings writeup and
  `card_mode/CLAUDE.md` the distilled version — keep both updated as bytes get
  identified. `card_hash.py` computes the b2/b7 bytes a motor validates from a
  card's RFID UID (a CRC-16 of it); `--verify` re-checks that against all 39
  logged cards, and `lego_card.card_hash()` is the board-side copy — keep the
  two in step. Sub-folders:
  - `card_mode/examples/` — small single-purpose examples, split by where they run:
    `stick_*.py` on the M5StickS3 (can transmit), `mac_*.py` on the Mac (listens, or
    drives a Stick over USB). `stick_log_cards.py` is the odd one out: it is meant to
    be installed as the Stick's `main.py` (`mac_fetch_cards.py --install`) so the
    board harvests cards on its own, off USB.
  - `card_mode/pico tests/` — MicroPython for the board: `picolib.py` (broadcast),
    `lego_card.py` (RFID card decode), `stick_ui.py` (screen + beep),
    `pico_server.py` (serial command server)
- `README.md` — user-facing intro and quick-start

## Conventions
- All four classes follow the same `connect(card_serial, card_color=None)` signature with up to 5 retries and a 1-second delay on "not ready" errors.
- Method names are plain English verbs (`spin`, `stop`, `turn_left`, `drive`) rather than the underlying library's verbose names (`motor_run_for_degrees`, `movement_turn_for_degrees`, etc.).
- One step in `doubleMotor.move_steps()` = 180 degrees (half rotation).
- `controller.drive()` takes a `doubleMotor` instance and runs tank-drive for `t × 0.1` seconds.

## When adding a new method
1. Add it to `lelib.py`.
2. Add a row to the matching table in `lelib.md`.
3. If it changes the public API, update `README.md` too.
