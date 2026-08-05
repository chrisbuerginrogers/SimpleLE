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
| 2 | CRC-16 of the card's RFID UID, high byte — **motor validates it** | confirmed, 39/39 |
| 3–4 | card serial, little-endian | confirmed |
| 5 | **sensor:** live detected color (`0xff` = none) · **controller:** RIGHT stick | confirmed |
| 6 | **sensor:** always `0x00`, *not* reflection · **controller:** LEFT stick | confirmed |
| 7 | same CRC-16, low byte — **motor validates it** | confirmed, 39/39 |
| 8 | slowly-varying, dithers ±1 — counter tail or an analog value | unidentified |
| 9–11 | sender uptime: 24-bit little-endian, 1/256 ms per tick (so 10–11 alone = a 16-bit millisecond clock, wrapping every 65.5 s) | confirmed |

**Group address = card color (byte 1) + serial (bytes 3–4).** A brick
only obeys broadcasts matching its own card. You don't need the physical
card, just the numbers.

**A motor only ever listens — it does not advertise at all.** Retracted
claim: earlier notes here (inherited from `pico_fake_controller.py`) said
a motor announces its own card in a manufacturer-data advertisement, and
`AUTO_ADOPT` was built on scanning for exactly that. It does not. A scan
filtering on LEGO's company ID `0x0397` returned **zero** devices with a
motor powered on and carded.

Also tested in the case that would most plausibly break it: tapping a card
**onto** the motor produces nothing either. 40 s of scanning across
repeated taps, diffed against a baseline, showed no new advertisement of
any kind. So it is not "quiet until a tap" — it is silent always.

**That test needs a positive control and the first two attempts didn't
have one.** An empty result means nothing if the scanner would have heard
nothing regardless: the first run was scanned before the tap actually
happened, and in the second every LEGO device in the room had gone to
sleep, so the baseline was empty too. The run that counts had the ESP32
broadcasting throughout — 59 control packets heard in the baseline alone,
proving the scanner worked, while the tapped motor stayed silent. Any
future "device X doesn't advertise" claim needs the same control.

Everything you need about a card comes from a *sender* carrying it — a
controller or color sensor — or from the card's own RFID. This is also
why spoofing works so cleanly: nothing on the motor's side ever talks
back, so there is nothing to contradict a forged beacon.

**Bytes 2 and 7 are mandatory.** They are a per-card hash: the same card
yields the same pair on any device. A beacon with the correct serial but
wrong b2/b7 is **ignored by the motor** (confirmed by spoofing).

**They are a CRC-16 of the card's 7-byte RFID UID** — polynomial `0x0001`,
reflected in and out, init `0`, big-endian out, so b2 is the high byte and b7
the low one. Verified on all 39 cards in `card_taps.csv`, exactly. Since
`0x0001` is x¹⁶ + 1 this is an XOR fold, not cryptography: the UID is all you
need. Use `card_hash.py` (Mac, has a CLI and `--verify`) or
`lego_card.card_hash()` (board).

So there are two ways to get the tokens, and the first is now the easy one:
compute them from the card's UID, or read them off any device already
carrying that card. **A card's UID is enough to drive its motor** — and since
a UID is just a number, a fully fabricated card needs no physical tap.

**The motor can't verify this itself.** The UID is not in the broadcast, so
it compares b2/b7 against the value stored when the card was tapped. The
check is an equality test, not a computation.

**Not a checksum of the color and serial** — that stays true and is why the
hunt took so long. b2/b7 are not *any* GF(2)-affine function of those 24
message bits, on any output bit, over 39 cards. The message was never on the
air. Don't re-run a sweep against color+serial; it is the wrong input.

**Nothing in the beacon carries a card's printed symbol.** `b1` is the only
color-dependent field and it differs per color, so two colors sharing a symbol
share no byte. The symbol is a fixed attribute of the color, two colors per
symbol, read off the physical cards:

| fw | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| color | magenta | purple | blue | azure | teal | green | yellow | orange | red | white |
| symbol | heart | square | diamond | heart | *no card* | square | circle | diamond | circle | *no card* |

**Complete — eight card colors, four symbols, two colors each.** There is no
fifth symbol, because there are no teal or white cards. That squares with the
already-known fact that magenta, orange and azure are card-only colors: the
ten firmware codes split into card-only (magenta, azure, orange), both
(red, yellow, blue, green, purple) and sensor-only (teal, white).

**Do not look for an arithmetic rule mapping code → symbol** — an earlier
"period-4 pairing" claim was fitted to four points and is now retracted,
killed by red carrying a circle rather than the square it predicted. See
`Card_mode.md`.

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
- **Teal and white are the mirror image: sensor-only, with no card.** So
  the ten firmware codes partition cleanly — card-only `{magenta, azure,
  orange}`, both `{red, yellow, blue, green, purple}`, sensor-only
  `{teal, white}`. Eight card colors, seven detectable colors, five shared.
- **Re-measure before believing a color mismatch.** Brick distance, angle
  and room light all move byte 5. A purple brick read as RED in one sweep
  while `0x02` had been observed directly from the same sensor minutes
  earlier. `0xff` usually means the brick wasn't presented well, not that
  the table is wrong — blue and teal both did this and came back correct.
- **Spoofing works, end to end, on two different cards.** An ESP32-S3
  broadcasting a crafted FD02 beacon drove a real motor with no connection
  and no controller involved:
  - as **ORANGE #7569** (`b2=0x7d b7=0x81`) — forward then reverse, with the
    motor confirmed *alone* on that card first (a scan showed no other orange
    sender), so nothing else could have driven it;
  - then, after the motor was re-tapped with the purple card, as
    **PURPLE #6055** (`b2=0xdb b7=0x2c`) — and orange stopped working at the
    same moment.

  That second half is the cleanest confirmation of the group address in the
  whole investigation: same board, same code, same speed, and the *only*
  variable was which card the motor had been tapped with. A motor obeys the
  card it was last tapped with, and nothing else. The whole chain is closed:
  read a card's numbers, compute its tokens from the UID, craft the beacon,
  move the motor.
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

**b2/b7 are not *stored* on the card, but they are computed from it** — a
CRC-16 of the UID, see above. Nothing in the pages resembles them, and they
differ per card across all 39 cards in `card_taps.csv`. A tap gets you the
color, the serial and (via the UID) the tokens, so nothing about a card needs
reading off the air any more.

Confirmed by dumping **every** page, not just 4–7: pages 8 through 19 are all
zeros on both cards, and page 16's `000000FF00050000` is identical on the two,
so it is not per-card either. `0x7d`/`0x81` (orange) and `0xdb`/`0x2c` (purple)
appear nowhere on the tag. There is no unread corner of the card left for them
to be hiding in.

```
PURPLE #6055   page 0  04B1C8F5 82871F90 8A48FFFF 00000000
               page 4  4C334730 000217A7 00000000 FFEEDDCC
               page 8  all zeros through page 19
ORANGE #7569   page 0  041C6EFE 82871F90 8A48FFFF 00000000
               page 4  4C334730 00081D91 00000000 FFEEDDCC
```

Note page 0 carries the UID *with* its BCC check byte spliced in (`04B1C8`
**`F5`** `82871F90`), so the seven UID bytes are not contiguous there —
feeding page 0 straight into `card_hash()` gives a wrong answer, and
`read_card()` is what returns the clean 7 bytes.

The **RFID UID** turned out to be the whole message — information the earlier
CRC hunts never had. The first two cards to carry both:

| Card | RFID UID | b2 | b7 |
|---|---|---|---|
| PURPLE #6055 | `04 B1 C8 82 87 1F 90` | `0xdb` | `0x2c` |
| ORANGE #7569 | `04 1C 6E 82 87 1F 90` | `0x7d` | `0x81` |

Both reproduce from the algorithm above.

The 39-card sample that cracked it came from `examples/stick_log_cards.py`:
installed as `main.py` it
reads the card over RFID *and* listens for its FD02 beacon at the same time,
writing one row per card with the UID, color, serial and all twelve bytes.
Two taps per card — on a controller or color sensor, then on the Stick — and
it skips cards already in the file. Collect it with
`examples/mac_fetch_cards.py`; it lands in `card_taps.csv`, **overwriting it
verbatim** — hand-edits to that file do not survive a fetch.

**That two-tap dance is now only for evidence, not for use.** It exists
because the logger records the *observed* b2/b7 from a sender's broadcast
rather than computing them — which is the point, since a computed value would
make the file useless for checking the algorithm. To simply drive a motor,
one tap on the RFID reader is enough.

Both pairs above were confirmed identical when read from a color sensor and
a controller carrying the same card, which is what "per card, not per
device" means in practice.

**Needs the m5 library from 2026-08 or later.** The RFID/Grove and display
code is maintained in `chrisbuerginrogers/micropython` under `M5StickS3/`,
not here, and that update moved three workarounds out of this repo and into
the driver where they belong:

| Was worked around here | Now |
|---|---|
| `lego_card.open_reader()` retried the Grove 5V boost settling | `RFID()` settles and retries itself |
| `CardReadFailed` vs `NotALegoCard`, because `read_pages()` returned `None` for both a wrong tag type and a failed read | `None` means only the former, `ReadError` the latter, and it retries the latter 3× |
| `stick_ui._MISSING_GLYPHS` patched in 18 missing capitals | the font is the full printable ASCII range |

`stick_ui` raises `ImportError` on an older `m5/` rather than letting text
silently lose its capitals again — that failure was invisible, which is what
made it expensive.

## Ruled out — don't retry these

These are all about the **color and serial** as the message. The answer uses
the RFID UID instead, so none of them was ever going to hit.

| Hypothesis | How it died |
|---|---|
| b2/b7 = CRC-8 of the card fields | brute force over all 256 polys × 256 inits × reflections × xorout, several input selections, 20 cards → 0 hits |
| b2/b7 = halves of a CRC-16 of the card fields | all 65536 polynomials × inits × reflections × input orders × both byte orders, 20 cards → 0 hits. The real answer *is* a CRC-16 of this shape (poly `0x0001`, reflected, init 0, big-endian out) — over the UID, which this sweep never fed it |
| b2/b7 = sequential ID extension | adjacent serials scramble both bytes (BLUE#1001 `d6`/`12` vs BLUE#1003 `c3`/`c9`) |
| b2 & 0xc0 is a constant marker | held for 6 cards, broke on 20 — retracted |
| b2 or b7 = the symbol printed on the card | every card of one color shares one symbol, yet the 8 purple cards in `card_taps.csv` carry 8 distinct b2 and 6 distinct b7. A byte that varies within a symbol is not encoding it. The symbol is also already implied by b1. |
| b7 = a shared card *design* (the same-color b7 collisions) | proposed when 3 of 5 b7 collisions turned out to be same-color, against 0.3 expected. Now fully settled by the hash: b7 is the low byte of a CRC-16 of the UID, so collisions are birthday collisions and mark nothing. Noted because the clustering is real and will look meaningful again on the next sample. |
| b8 = reflection / brightness | it holds and dithers ±1 regardless of brightness |
| b8 = uptime counter | it oscillates in place and has risen as well as fallen |
| byte 0 = message type | it's the device type; a capture locked to one address sees it constant |
| bytes 5–6 pack four 4-bit axes | there are two sticks; the motor reads one low nibble per byte |

Raw data for re-checking any of this is in `card_taps.csv` (39 cards **with
their RFID UIDs**, harvested with `examples/stick_log_cards.py`) and `data
from controller` (38 controller packets). The older `cards.csv` (16 cards,
no UIDs) has been deleted — `card_taps.csv` superseded 15 of its 16, and the
odd one out, PURPLE #1126, was judged not worth keeping a file for. It is
still in git: `git show 2d9c572:card_mode/cards.csv`.

`card_taps.csv` is what the hash was cracked with, and is still the file to
re-check it against (`python card_hash.py --verify`) — it is the only one
pairing a card's UID with its observed tokens. It cross-checked clean against
`cards.csv` before that file went: all 15 shared cards agreed on b2 and b7
exactly, captured months apart with a different tool, and **eleven of those
15 were read on the other device type**, proving b2/b7 do not depend on byte
0. Its 17 color-sensor and 22 controller rows also re-confirm the byte map
on data it was not derived from (`b5` = `0xff` or a detected color for the
sensor, stick position for the controller; `b6` always `0`).

**b2 looks like a hash, not a field** — 34 distinct values across 39 cards,
spread 4..251 over 14 of the 16 high nibbles, with 5 collisions where random
8-bit values predict 2.8. That read was right: it is half of one.

## Open questions

1. ~~**The b2/b7 hash algorithm.**~~ **Solved** — CRC-16 of the RFID UID,
   39/39 cards, see above. The note here predicted it would take ~90
   UID-bearing cards; it took 39 and a different guess at the message.
   Spoofing no longer needs a card harvested off the air.
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
| `card_hash.py` | b2/b7 from a card's RFID UID; `--verify` re-checks all 39 logged cards |
| `examples/stick_log_cards.py` | runs on the Stick as `main.py`: RFID UID + all 12 FD02 bytes per card, to `card_taps.csv` on the board |
| `examples/mac_fetch_cards.py` | installs that logger, and fetches what it collected |
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
`pico_lelib` set sticks, the board broadcast them, and `cardlib.read_sensor`
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
`picolib.Card` takes the tokens explicitly for this reason — feed it
`lego_card.card_hash(uid)` and any card works.

**Computing b2/b7 beats reading them.** `card_hash.py` /
`lego_card.card_hash()` derive them from the card's RFID UID, so the card
itself is the only thing needed.

To *read* them off the air instead — which is how you check the algorithm on
a new card — you need a **sender**, not the motor. They appear in the FD02
service data of a controller or color sensor carrying the card, and
`watch_service_data.py` shows them. A motor's own advertisement uses the
manufacturer-data layout, which carries only color and serial.
