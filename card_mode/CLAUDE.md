# card_mode — Claude context

Reverse-engineering of the **FD02 BLE broadcast protocol** that LEGO
Education devices use to control each other **with no hub, no pairing and
no GATT connection**. Bricks tapped with the same card form a group;
senders (controllers, color sensors) broadcast their live state in a
connectionless BLE advertisement, and motors listen and act — combining
multiple senders.

This makes two things possible, and both are proven working:
1. **Read** card taps, sensor readings and stick positions passively.
2. **Drive a real motor** by broadcasting a crafted beacon (Pico W).

`Card_mode.md` is the full writeup with the evidence behind every claim.
**This file is the distilled version** — read it before doing protocol
work so you don't re-derive what's settled or re-test what's already been
ruled out.

> Status: reverse-engineered from live captures, not official LEGO docs.
> Confidence is marked per row; open questions are at the end.

## The beacon — FD02 service data, 12 bytes

Carried as a **Service Data – 16-bit UUID** (`0xFD02`) AD structure. Byte
offsets below are as bleak delivers it (UUID / length prefix already
stripped).

| Byte | Meaning | Status |
|---|---|---|
| 0 | device type — `0x02` color sensor, `0x03` controller | confirmed |
| 1 | card color, **firmware** code | confirmed |
| 2 | per-card token — **motor validates it** | required, algorithm not cracked |
| 3–4 | card serial, little-endian | confirmed |
| 5 | **sensor:** live detected color (`0xff` = none) · **controller:** RIGHT stick | confirmed |
| 6 | **sensor:** always `0x00`, *not* reflection · **controller:** LEFT stick | confirmed |
| 7 | per-card token — **motor validates it** | required, algorithm not cracked |
| 8 | slowly-varying, dithers ±1 — counter tail or an analog value | unidentified |
| 9–11 | counters / CRC, change every packet | confirmed |

**Group address = card color (byte 1) + serial (bytes 3–4).** A brick
only obeys broadcasts matching its own card. You don't need the physical
card, just the numbers — a motor announces its own card in its
manufacturer-data advertisement.

**Bytes 2 and 7 are mandatory.** They are a per-card hash: the same card
yields the same pair on any device. A beacon with the correct serial but
wrong b2/b7 is **ignored by the motor** (confirmed by spoofing). To
impersonate a card you must use its real b2/b7 — read them off any device
already carrying that card.

Manufacturer data (company ID `0x0397`) is a **different layout** —
`[group, device, color, serial_lo, serial_hi]`, with the color at index
**2** rather than 1. The serial is at bytes 3–4 either way.

## Controller — `byte0 = 0x03`

Two joysticks: **`byte6` = LEFT**, **`byte5` = RIGHT**.

The motor uses **only the low nibble** of each byte, read as a signed
4-bit value. The high nibble is ignored entirely (proven by sweeping many
byte values at a real motor).

| low nibble | `0` | `1` | `2` | `3` | `D` | `E` | `F` | `4`–`C` |
|---|---|---|---|---|---|---|---|---|
| action | stop | +1 | +2 | **+3 fwd** | **−3 rev** | −2 | −1 | dead (out of range) |

→ **7 states per stick.** The motor **combines** the two axes: both up →
full forward, both down → full reverse, opposite → cancel.

Note the real controller rests at exactly `0` and its transmitted values
skip 1 and 2, so a deadzone is applied on-device — it is not a dumb ADC.

## Color sensor — `byte0 = 0x02`

**`byte5` = the color it is currently looking at**, as a raw **firmware**
color code, in every advertisement, no connection required. `byte6` is
unused.

| App | Color | byte 5 | Verified |
|---|---|---|---|
| 0 | No color | `0xff` | ✅ 12/12, plus every idle observation |
| — | *Black* | reads `0xff` | ✅ 11/11 — **not** firmware `0x00` |
| 1 | Red | `0x09` | ✅ 11/11, and 24/24 in an earlier predicted test |
| 2 | Yellow | `0x07` | ✅ 9/9 |
| 3 | Blue | `0x03` | ✅ on re-measure |
| 4 | Teal | `0x05` | ✅ on re-measure |
| 5 | Green | `0x06` | ✅ 8/8 |
| 6 | Purple | `0x02` | ✅ observed live |
| 8 | Magenta | `0x01` | n/a — card-only color |
| 9 | Orange | `0x08` | n/a — card-only color |
| 10 | Azure | `0x04` | n/a — card-only color |

All eight testable colors are confirmed. Raw results are in
`color_verify.csv`.

The sensor broadcasts **only the detected color** — the behaviors it
triggers (turn 90°, pulse, back-and-forth) are **not** on the air. That
color→action logic lives motor-side.

## Settled facts

- **A card serial is not unique.** RED#1126, YELLOW#1126 and PURPLE#1126
  all exist — three collisions in a 20-card sample, so serials are
  allocated per color. The identifying key is the **(color, serial)
  pair**. Anything keyed on serial alone will silently collide.
  This also affects `lelib`'s `connect(card_serial, card_color=None)`.
- **A card's bytes are deterministic across devices.** The same card
  produces identical b1/b2/b3/b4/b7 on any hardware it's tapped onto.
- **Device-specific decodes must be gated on byte 0.** Without that gate,
  a color sensor's byte 5 gets read as a stick axis and reports a
  phantom `-1`. That was a real bug in `decode_controller_axes()`.
- **Reflection is not broadcast.** Byte 6 stays `0x00` even with white at
  contact — maximum reflectance. `colorSensor.reflection()` genuinely
  requires a GATT connection; don't try to make it connectionless.
- **The sensor only detects 7 colors.** `SENSOR_DETECTABLE_COLORS` is
  `{RED, YELLOW, BLUE, TEAL, GREEN, PURPLE, WHITE}`. Magenta, orange and
  azure exist only as *card* colors — testing the sensor against them
  measures nothing. A black brick reads `0xff` (No color), so black and
  an empty field of view are indistinguishable.
- **Re-measure before believing a color mismatch.** Brick distance, angle
  and room light all move byte 5. A purple brick read as RED in one sweep
  while `0x02` had been observed directly from the same sensor minutes
  earlier. `0xff` usually means the brick wasn't presented well, not that
  the table is wrong — blue and teal both did this and came back correct.
- **Spoofing works.** A Pico W broadcasting a crafted beacon drove a real
  motor with no connection and no real controller present.
- **No transmit on macOS.** bleak can only scan and connect. Broadcasting
  a beacon needs a Pico W (or Linux/BlueZ) — see `pico tests/`.

## The card itself (RFID)

Connection cards are **NTAG/Ultralight** tags (SAK `0x00`, 7-byte UID), and
they carry the color and serial in the clear from page 4:

```
page 4   4C 33 47 30                  ASCII "L3G0", magic marker
page 5   00 <color> <serial hi> <lo>  color is the FIRMWARE code
page 6   00 00 00 00
page 7   FF EE DD CC                  fixed filler
```

Read live from a purple #6055 card via the M5StickS3's RFID2 Unit:
`4C334730 000217A7 ...` — firmware `0x02` = purple, `0x17A7` = 6055.
Decoder is `pico tests/lego_card.py`; `decode_pages()` is pure and testable
off-hardware, `read_card()` needs the reader.

**The serial is big-endian on the card and little-endian in the FD02
broadcast.** Don't copy one into the other without swapping.

**b2/b7 are NOT on the card.** They differ per card across all 16 cards in
`cards.csv`, and nothing in the pages resembles them — so a tap gets you
color and serial for free, but the tokens still have to be read off the air
with `watch_service_data.py`. Untested idea worth a look: whether they derive
from the card's **RFID UID**, which is new information the earlier CRC hunts
never had. Purple#6055 is UID `04B1C882871F90`.

**Reader gotcha:** the driver powers the Grove 5V rail itself, but on a cold
start the first register write can go out before the boost settles and raise
`ETIMEDOUT`. Retry — `lego_card.open_reader()` does. The RFID/Grove code is
maintained in `chrisbuerginrogers/micropython` under `M5StickS3/`, not here.

## Ruled out — don't retry these

| Hypothesis | How it died |
|---|---|
| b2/b7 = CRC-8 of the card fields | brute force over all 256 polys × 256 inits × reflections × xorout, several input selections, 20 cards → 0 hits |
| b2/b7 = halves of a CRC-16 | all 65536 polynomials × inits × reflections × input orders × both byte orders, 20 cards → 0 hits |
| b2/b7 = sequential ID extension | adjacent serials scramble both bytes (BLUE#1001 `d6`/`12` vs BLUE#1003 `c3`/`c9`) |
| b2 & 0xc0 is a constant marker | held for 6 cards, broke on 20 — retracted |
| b8 = reflection / brightness | it holds and dithers ±1 regardless of brightness |
| b8 = uptime counter | it oscillates in place and has risen as well as fallen |
| byte 0 = message type | it's the device type; a capture locked to one address sees it constant |
| bytes 5–6 pack four 4-bit axes | there are two sticks; the motor reads one low nibble per byte |

Raw data for re-checking any of this is in `cards.csv` (20 cards) and
`data from controller` (38 controller packets).

## Open questions

1. **The b2/b7 hash algorithm.** Not a standard CRC-8/16 or Fletcher-16
   over color+serial. Until it's cracked, spoofing requires harvesting
   the real bytes off a device carrying the card.
2. **Byte 8.** Slowly varying, dithers ±1, has both risen and fallen. It
   is either the slow tail of the 8–11 counter block or a genuine analog
   value (battery and temperature both fit). The two documents disagreed
   on this; it is not settled.
3. **Position or speed command?** Whether byte 5/6 is a normalized stick
   position or an actual motor speed is untested. Run
   `capture_controller.py` with no motor / single motor / double motor and
   compare with `analyze_payload.py a.csv b.csv c.csv`.
4. **Is byte 1 (color) validated for group membership**, or does the
   serial alone suffice? Untested — the b2/b7 check may make it moot.
5. **Exact byte order and rate of the 8–11 counter.**

## Conventions

- **Scripts import each other by bare module name.** Run them from inside
  this folder.
- **Firmware vs App color codes are different numbering schemes.**
  Always pass a wire byte through `_firmware_to_app()` before naming it.
  Skipping that silently yields plausible-looking wrong colors — firmware
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
| `verify_colors.py` | prompt through all 11 colors, verify byte 5 against the firmware table |
| `log_cards.py` | tap-through card logger, keyed on (color, serial) |
| `capture_controller.py` | guided capture protocol for the controller |
| `capture_colorsensor.py` | guided capture protocol for the color sensor |
| `adv_capture.py` | shared capture engine — discovery, prompts, timed segments, CSV |
| `analyze_payload.py` | per-byte differencing vs. baseline, plus receiver-comparison mode |
| `simpletest.py` | hardcoded decoder for the original `data from controller` log |

Transmit-side code lives in `pico tests/` (MicroPython, Pico W). It runs
**on the Pico, not the Mac** — copy it over and run it.

`picolib.py` is the library: `Card` (color, serial, **and the b2/b7
tokens**) plus `Motor.set_speed()` / `set_tank()` / `drive()`. It uses the
settled low-nibble encoding and shares `SPEED_STEPS` with `lelib`, so a
percentage rounds identically whether it goes out over GATT from the Mac
or over the air from the board. `build_beacon()` and the speed helpers
import fine on a laptop for checking; `Motor` raises immediately there.

`pico_server.py` sits on top of it and takes JSON-line commands over USB
serial from `../../pico_lelib.py` on the Mac. It re-broadcasts between
commands, because a motor that stops hearing fresh packets gives up — that
is why it is a poll loop and not a one-shot script. Its stdout **is** the
protocol, so nothing in it may print anything that isn't a JSON reply.

**Not Pico-only.** Verified end-to-end on an ESP32-S3 (MicroPython 1.28):
`pico_lelib` set sticks, the board broadcast them, and `lelib.read_sensor`
read the same values back off the air. Any MicroPython board with a BLE
radio works — note the ESP32-**S2** has no Bluetooth at all.
`pico_lelib.install()` copies both files over the raw REPL and deliberately
does not write `main.py`, so a shared board keeps its normal behavior.

The experiment scripts alongside it are what established the protocol:
`pico_fake_controller.py` (first working spoof), `pico_nibble_sweep.py` /
`pico_raw_sweep.py` (which byte values the motor honors),
`pico_hash_test.py` and `pico_byte7_switch.py` (b2/b7 validation).

**Two stale things in those scripts** — they are lab notebooks, not
current API. `pico_fake_controller.py`'s docstring still describes the
superseded nibble-interleaved ±48 signed-8 stick encoding, which
`pico_nibble_sweep.py` then disproved. And they hardcode `BYTE2 = 0xf3` /
`FIXED_78 = b'\x48\x80'` copied from one real controller, so they only
drive motors carrying *that* card; `AUTO_ADOPT` harvests color and serial
but not the tokens, so it will silently produce beacons the motor ignores.
`picolib.Card` takes the tokens explicitly for this reason.

**Reading b2/b7 needs a sender, not the motor.** The tokens appear in the
FD02 service data of a controller or color sensor carrying the card —
`watch_service_data.py` shows them. A motor's own advertisement uses the
manufacturer-data layout, which carries only color and serial.
