# SimpleLE — Claude context

## What this project is
A thin Python wrapper around the `legoeducation` pip package. The goal is simpler method names and automatic Bluetooth reconnect logic for classroom use with LEGO Education hardware.

## Key files
- `lelib.py` — the library (four classes: `singleMotor`, `doubleMotor`, `controller`, `colorSensor`)
- `lelib.md` — API reference; keep in sync with `lelib.py` whenever methods change
- `projects/` — scripts that build something with lelib (e.g. `drive.py` — joystick tank-drive + live matplotlib color-sensor graph)
- `tests/` — diagnostic/scratch scripts for exercising lelib or BLE hardware, not end-user builds
- `card_mode/` — BLE advertisement reverse-engineering: decoding card taps, device
  type, sensor readings and controller sticks straight from the advertisement, with
  no GATT connection. Self-contained (the scripts import each other by bare module
  name, so run them from inside the folder). `Card_mode.md` is the findings
  writeup — keep it updated as bytes get identified.
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
