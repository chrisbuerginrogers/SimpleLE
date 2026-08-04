# card_mode — Claude context

Reverse-engineering of the FD02 BLE service data that LEGO Education
devices broadcast, so card taps and sensor readings can be read passively
with no GATT connection and no pairing.

`Card_mode.md` is the full writeup with the evidence behind every claim.
**This file is the distilled version** — read it before doing protocol
work so you don't re-derive what's settled or re-test what's already been
ruled out.

## Established byte map

FD02 service data, as delivered by bleak (company ID / length prefix
already stripped):

| Byte | Meaning | Status |
|---|---|---|
| 0 | device type — `0x02` color sensor, `0x03` controller | confirmed |
| 1 | card colour, **firmware** code | confirmed |
| 2 | per-card token | not derived from anything visible |
| 3–4 | card serial, little-endian | confirmed |
| 5 | **sensor:** live detected colour (`0xff` = none) · **controller:** right stick | confirmed |
| | — all 8 sensor-detectable colour codes verified against real bricks | measured |
| | — Magenta/Orange/Azure are **card-only**, sensor can't detect them | n/a |
| 6 | **sensor:** always `0x00`, *not* reflection · **controller:** left stick | confirmed |
| 7 | per-card token | not derived from anything visible |
| 8 | slowly-varying analog value, possibly battery | unidentified |
| 9–11 | counters / CRC, change every packet | confirmed |

Manufacturer data (company ID `0x0397`) uses a different layout —
`[group, device, colour, serial_lo, serial_hi]`, with the colour at index
**2** rather than 1. The serial is at bytes 3–4 either way.

## Settled facts

- **A card serial is not unique.** RED#1126, YELLOW#1126 and PURPLE#1126
  all exist — three collisions in a 20-card sample, so serials are
  allocated per colour. The identifying key is the **(colour, serial)
  pair**. Anything keyed on serial alone will silently collide.
  This also affects `lelib`'s `connect(card_serial, card_color=None)`.
- **Device-specific decodes must be gated on byte 0.** Without that gate,
  a color sensor's byte 5 gets read as a stick axis and reports a
  phantom `-1`. That was a real bug in `decode_controller_axes()`.
- **Reflection is not broadcast.** Byte 6 stays `0x00` even with white at
  contact — maximum reflectance. `colorSensor.reflection()` genuinely
  requires a GATT connection; don't try to make it connectionless.
- **A card's bytes are deterministic across devices.** The same card
  produces identical b1/b2/b3/b4/b7 on any hardware it's tapped onto.
- **The sensor only detects 7 colours.** `SENSOR_DETECTABLE_COLORS` is
  `{RED, YELLOW, BLUE, TEAL, GREEN, PURPLE, WHITE}`. Magenta, orange and
  azure exist only as *card* colours — testing the sensor against them
  measures nothing. A black brick reads `0xff` (No color), so black and
  an empty field of view are indistinguishable.
- **Re-measure before believing a colour mismatch.** Brick distance, angle
  and room light all move byte 5. A purple brick read as RED in one sweep
  while `0x02` had been observed directly from the same sensor minutes
  earlier.

## Ruled out — don't retry these

| Hypothesis | How it died |
|---|---|
| b2/b7 = CRC-8 of the card fields | brute force over all 256 polys × 256 inits × reflections × xorout, several input selections, 20 cards → 0 hits |
| b2/b7 = halves of a CRC-16 | all 65536 polynomials × inits × reflections × input orders × both byte orders, 20 cards → 0 hits |
| b2/b7 = sequential ID extension | adjacent serials scramble both bytes (BLUE#1001 `d6`/`12` vs BLUE#1003 `c3`/`c9`) |
| b2 & 0xc0 is a constant marker | held for 6 cards, broke on 20 — retracted |
| b8 = uptime counter | it oscillates in place and has risen as well as fallen |
| byte 0 = message type | it's the device type; a capture locked to one address sees it constant |

Raw data for re-checking any of this is in `cards.csv` (20 cards) and
`data from controller` (38 controller packets).

## Open questions

1. **Controller axis encoding.** Every magnitude observed so far is ≤ 16,
   which fits *both* a signed byte (full deflection ≈ ±100) and two
   packed 4-bit fields (max ±7, meaning bytes 5–6 carry four axes, not
   two). Decisive test: push a lever to its mechanical stop and read the
   magnitude. `capture_controller.py` is built for this.
2. **Position or speed command?** The controller is not a dumb ADC — it
   rests at exactly `0` and its values skip 1 and 2, so a deadzone is
   applied on-device. Whether byte 5/6 is a normalized stick position or
   an actual motor speed is untested. Run `capture_controller.py` with no
   motor / single motor / double motor and compare with
   `analyze_payload.py a.csv b.csv c.csv`.
3. **Byte 8.** Slowly varying, oscillates by ±1, has both risen and
   fallen. Battery and temperature both fit.

## Conventions

- **Scripts import each other by bare module name.** Run them from inside
  this folder.
- **Firmware vs App colour codes are different numbering schemes.**
  Always pass a wire byte through `_firmware_to_app()` before naming it.
  Skipping that silently yields plausible-looking wrong colours — firmware
  `2` is purple, App `2` is yellow.
- **Captures log the full payload, never a pre-decoded field.** The decode
  is the hypothesis under test.
- **Every capture starts with a hands-off `baseline` segment.** That's
  what lets the analyzer separate payload bytes from counters.
- **Keep `Card_mode.md` in sync** as bytes get identified. When something
  turns out wrong, record it as an explicit retraction rather than
  deleting it — the reasoning is worth not repeating.

## Hardware gotchas

- **macOS coalesces advertisements.** Expect ~2–10 packets/sec. Hold
  positions steady; fast sweeps alias and short windows miss cards
  entirely.
- **BLE addresses rotate between sessions on macOS.** Never use an address
  as device identity across runs.
- **The controller probably occupies the motor's only connection slot**,
  so you likely can't connect to a motor to read its speed while the
  controller is driving it. Measure RPM optically instead — striped wheel
  plus the color sensor at `set_update_rate(15)`, reusing
  `../tests/light_scope.py`.
- **Extended advertising is invisible here.** bleak hands you the merged
  advertisement + scan response, not the raw HCI PDU, so there's no
  portable way to tell legacy from BLE5 extended PDUs. That needs a
  dedicated sniffer.

## Tooling

| Script | Purpose |
|---|---|
| `scan_advertising.py` | live table of everything in range |
| `watch_service_data.py` | lock onto one card, log every byte change with the full payload |
| `verify_colors.py` | prompt through all 11 colours, verify byte 5 against the firmware table |
| `log_cards.py` | tap-through card logger, keyed on (colour, serial) |
| `capture_controller.py` | guided capture protocol for the controller |
| `capture_colorsensor.py` | guided capture protocol for the color sensor |
| `adv_capture.py` | shared capture engine — discovery, prompts, timed segments, CSV |
| `analyze_payload.py` | per-byte differencing vs. baseline, plus receiver-comparison mode |
| `simpletest.py` | hardcoded decoder for the original `data from controller` log |
