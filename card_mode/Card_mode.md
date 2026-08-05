# Card Mode — decoding LEGO card taps from BLE advertisements

Working notes on how `scan_advertising.py` reads a LEGO Education
card's **color** and **serial number** straight out of a device's BLE
advertisement, with no GATT connection.

This file carries the evidence behind every claim. `CLAUDE.md` in the same
folder is the distilled version — the byte map, what's settled, and a
"don't retry these" list — for picking the work back up quickly.

Status:

- Card color + serial — **confirmed working**
- Device type at byte 0 — **confirmed** (`0x02` color sensor, `0x03` controller)
- Color sensor's live detected color at byte 5 — **confirmed by prediction**,
  readable passively with no GATT connection
- Reflection is **not** broadcast — `reflection()` needs a connection
- A card serial is **not unique** — the key is the (color, serial) pair
- Bytes 2 and 7 are **solved** — a CRC-16 of the card's 7-byte RFID UID,
  verified on all 39 cards in `card_taps.csv`. Not derived from anything
  *visible* in the beacon, which is why they resisted so long
- Byte 8 is an **unidentified** slowly-varying analog value
- L/R stick axes — the spurious readings on non-controllers are **fixed**;
  the value *encoding* is still unresolved, see
  [Open problem: L/R axes](#open-problem-lr-axes)

---

## The idea

When you tap a LEGO Education card against a hub or tech element, the
device starts broadcasting that card's color and serial in its BLE
advertisement payload. Advertisements are passive — any scanner in range
picks them up. So you can watch card taps live without pairing,
connecting, or holding a session open.

`scan_advertising.py` is a live-refreshing table of every LEGO
advertisement in range, one row per device address, showing that device's
latest decoded card plus the raw payload bytes it came from.

---

## Where the card data lives

There are **two different carriers**, and a given device uses one or the
other:

| Carrier | Key | Layout | Source |
|---|---|---|---|
| Manufacturer data | company ID `0x0397` | `[product_group, product_device, color, serial_lo, serial_hi]` | Documented — matches `legoeducation/basic_ble.py::_extract_manufacturer_info` |
| Service data | service UUID `0xFD02` | `[device_type, color, hash_hi, serial_lo, serial_hi, ...]` | **Inferred empirically** — not from LEGO docs |

The serial is the same in both: little-endian at bytes 3–4,
`payload[3] | (payload[4] << 8)`.

The **color byte moves**: index 2 in manufacturer data, index 1 in service
data. That's the whole reason `_decode_card_bytes()` takes a `color_index`
argument. Note this is *not* a clean one-byte shift of the whole
structure — the serial stays at 3–4 either way, so byte 2 in the service
data form is something else entirely. It turned out to be half of a hash of
the card's RFID UID; see
[Bytes 2 and 7](#bytes-2-and-7--a-crc-16-of-the-cards-rfid-uid).

`decode_lego_card()` tries manufacturer data first, then falls back to
FD02 service data.

## Color numbering: two schemes

The byte on the wire is a **firmware** color code. The `legoeducation`
package exposes **App-aligned** codes, which are numbered differently.
`_firmware_to_app()` translates between them, so the decoder pipeline is:

```
raw byte  →  _firmware_to_app()  →  LEGO_COLOR_NAME_MAP  →  "PURPLE"
```

Firmware codes (from `legoeducation/rpc_message.py`): `NONE=-1, BLACK=0,
MAGENTA=1, PURPLE=2, BLUE=3, AZURE=4, TURQUOISE=5, GREEN=6, YELLOW=7,
ORANGE=8, RED=9, WHITE=10`.

Skipping the translation step would give you wrong color names — e.g.
firmware `2` (purple) would read as App `YELLOW`.

---

## Worked examples

Two devices observed live, both broadcasting via **FD02 service data**
(their Mfg Data columns were empty):

These were the document's first two captures, back when only the color and
serial were readable and the rest was `?`. Every byte in both is now
accounted for, so they are reproduced here fully decoded — they double as the
worked example for the whole byte map.

**`0xfd02:0302f3660400004883fbb6b0`** — a controller

| Byte | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9–11 |
|---|---|---|---|---|---|---|---|---|---|---|
| Value | `03` | `02` | `f3` | `66` | `04` | `00` | `00` | `48` | `83` | `fbb6b0` |
| Meaning | controller | color | hash hi | serial lo | serial hi | R stick | L stick | hash lo | analog | uptime |

- device: `0x03` → controller
- color: `0x02` → firmware PURPLE → `PURPLE`
- serial: `0x66 | (0x04 << 8)` = `102 + 1024` = **1126**
- sticks: both `0x00` → centered, motor stopped
- hash: `f3`/`48` = `card_hash(0413AA7ACC2191)` ✓
- uptime: `0xb0b6fb` / 256 ≈ **45.2 s** since the controller powered up
- decoded → `PURPLE#1126`, sticks centered ✓

**`0xfd02:0209de6d04ff0075874de086`** — a color sensor

| Byte | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9–11 |
|---|---|---|---|---|---|---|---|---|---|---|
| Value | `02` | `09` | `de` | `6d` | `04` | `ff` | `00` | `75` | `87` | `4de086` |
| Meaning | sensor | color | hash hi | serial lo | serial hi | detected | unused | hash lo | analog | uptime |

- device: `0x02` → color sensor
- color: `0x09` → firmware RED → `RED`
- serial: `0x6d | (0x04 << 8)` = `109 + 1024` = **1133**
- detected: `0xff` → nothing in front of it (or black — they are the same
  reading)
- hash: `de`/`75` = `card_hash(04F686A2CC2190)` ✓, and that card is row 1 of
  `card_taps.csv`
- uptime: `0x86e04d` / 256 ≈ **34.5 s**
- decoded → `RED#1133`, seeing nothing ✓

This pair was originally the evidence for the index-1 color hypothesis: two
independent devices where byte 1 matched the known card color *and* bytes 3–4
matched the known serial. That was "consistent, but a working hypothesis, not
a spec" at the time. It has since been confirmed on 39 cards.

The `card_hash` lines are the newest part and close the last gap. Note the
first one is a small recovery: `f3`/`48` is PURPLE #1126, the single card lost
when `cards.csv` was retired, so its UID is on record here even though it has
no row in `card_taps.csv`. Worth one tap to confirm the color and serial
directly if it matters — the identification is by hash match, and two cards
colliding on both bytes is a 1-in-65536 shot rather than an impossibility.

---

## The FD02 service-data byte map

Established by running a controller and a color sensor side by side while
they carried **the same card**, which separates card-derived bytes from
device-derived ones:

| Byte | Meaning | Confidence |
|---|---|---|
| 0 | device type — `0x02` color sensor, `0x03` controller | confirmed |
| 1 | card color, firmware code | confirmed |
| 2 | CRC-16 of the card's RFID UID, high byte | confirmed, 39/39 |
| 3–4 | card serial, little-endian | confirmed |
| 5 | **color sensor**: detected color, firmware code (`0xff` = none) | confirmed |
| 5–6 | **controller**: stick axes | position confirmed, encoding open |
| 6 | **color sensor**: always `0x00` so far — *not* reflection | see below |
| 7 | same CRC-16, low byte | confirmed, 39/39 |
| 8 | slowly-varying analog value, oscillates ±1 | unidentified |
| 9–11 | sender uptime, 24-bit little-endian, 1/256 ms per tick | confirmed |

### Bytes 9–11 — the sender's uptime clock

Not a CRC and not opaque churn: read little-endian as a 24-bit value they
count **1/256 of a millisecond per tick**, so bytes 10–11 on their own are
a 16-bit millisecond clock that wraps every 65.5 seconds.

The 39 taps in `card_taps.csv` each carry the Stick's own `uptime_ms`
alongside the payload, which makes this directly checkable. **It is the
sender's clock, so the taps must first be split by `b0`** — one logging
session used a color sensor and a controller alternately, and comparing
across the two makes the numbers look like noise. Split correctly, all
**26 gaps** agree with the elapsed wall time to within 2%:

```
color sensor (b0=02), 13 gaps      controller (b0=03), 13 gaps
  d16=5474  elapsed=5466  1.001      d16=3109  elapsed=3118  0.997
  d16=3525  elapsed=3510  1.004      d16=2905  elapsed=2917  0.996
  d16=3103  elapsed=3119  0.995      d16=6084  elapsed=6076  1.001
  d16=17224 elapsed=17231 1.000      d16=23949 elapsed=23978 0.999
```

The long gaps matter most: 17.2 s and 24.0 s of wall time tracked to
within 0.1%, which no counter of packets or CRC would do. Being the
sender's clock it says nothing about the card, and two devices carrying
the same card disagree — which is precisely how the split was found.

### Byte 0 — device type

Gating on this byte is what fixes the phantom axes readings. One caveat:
two distinct devices have been seen advertising `0x03` simultaneously, so
`0x03` may name a *class* rather than "controller" specifically.

Note the card serial follows the **card**, not the device. The same
`RED#1133` card read `0x02` on the color sensor and `0x03` once moved to
the controller, at a different BLE address. Never use the card serial to
identify hardware.

### Byte 5 on a color sensor — the live reading

The sensor broadcasts what it is currently looking at, as a raw firmware
color code, in every advertisement. **No connection required.**

This was confirmed by prediction rather than curve-fitting. Values
observed against known targets:

| App | Color | Expected byte | Verified | Evidence |
|---|---|---|---|---|
| 0 | No color | `0xff` | ✅ | 12/12 packets, plus every idle observation all session |
| — | *Black* | `0x00` | ❌ **reads `0xff`** | 11/11 packets — see below |
| 1 | Red | `0x09` | ✅ | 11/11, and 24/24 in an earlier predicted test |
| 2 | Yellow | `0x07` | ✅ | 9/9 packets |
| 3 | Blue | `0x03` | ✅ | confirmed on a re-measure |
| 4 | Teal | `0x05` | ✅ | confirmed on a re-measure |
| 5 | Green | `0x06` | ✅ | 8/8, plus observed live earlier |
| 6 | Purple | `0x02` | ✅ | observed live earlier; the sweep read RED, see below |
| 7 | White | `0x0a` | ✅ | 7/7, and 26/26 in an earlier predicted test |
| 8 | Magenta | `0x01` | n/a | card-only color, sensor can't detect it |
| 9 | Orange | `0x08` | n/a | card-only color, sensor can't detect it |
| 10 | Azure | `0x04` | n/a | card-only color, sensor can't detect it |

**All eight testable colors are confirmed.** Blue and teal read `0xff`
on a first attempt — nothing detected rather than the wrong color — and
came back correct on a re-measure. That pattern is worth remembering:
`0xff` usually means the brick wasn't presented well, not that the table
is wrong.

**Magenta, orange and azure are not testable.** `SENSOR_DETECTABLE_COLORS`
in `legoeducation/color_map.py` is `{RED, YELLOW, BLUE, TEAL, GREEN,
PURPLE, WHITE}` — the other three are *card* colors only. Asking the sensor
for them and calling the answer a mismatch measures nothing, so
`verify_colors.py` now excludes them from a default run and reports them as
`n/a` when named explicitly.

**Purple's mismatch was measurement, not decoding.** The sweep read `0x09`
(RED) for the purple brick, but `0x02` was observed directly from this same
sensor earlier in the session while it sat on something purple. Brick
distance, angle and room light all move this reading — re-measure before
believing any single mismatch.

**Black reads as "no color", and that's a real finding.** A black brick
gave `0xff` on 11/11 packets, not the firmware `BLACK = 0x00`. So this
sensor doesn't distinguish black from an empty field of view, and
`colorSensor.detect_color()` returning `'No color'` is genuinely ambiguous.
Worth confirming with a second black brick before treating it as settled.

Raw results for both runs are in `color_verify.csv`.

The RED and WHITE rows were predicted before the measurement, and the
controller in the same scans stayed unaffected. **The remaining codes are
assumed from `legoeducation/rpc_message.py`, not measured.**

`verify_colors.py` closes that gap: it prompts through all 11 App colors,
samples byte 5 for each, and reports whether the raw byte matches the
firmware table *and* whether `_firmware_to_app()` lands on the right App
code. Skipping a color you have no brick for is supported — a skipped row
is honest, a guessed one isn't.

```bash
python verify_colors.py                              # everything
python verify_colors.py --only orange,black,teal,blue
python verify_colors.py --only 4,8,10                # App codes work too
```

Anything that doesn't come back clean offers an immediate re-measure, so
a fumbled brick doesn't cost a whole rerun.

**Black is tested even though the App has no BLACK color.** Firmware `0`
is BLACK and translates to App `No color`, so a black brick and an empty
sensor both arrive as `No color` and *only the raw byte separates them*.
Those two targets are therefore checked strictly against the wire byte
(`0x00` vs `0xff`) rather than the translated code — otherwise each would
pass while reading the other.

That's a real question about the hardware, not just bookkeeping: if a
black brick reports `0xff`, the sensor cannot distinguish black from
nothing, and `colorSensor.detect_color()` returning `'No color'` is
ambiguous by design. Because `black` has no App code, `--only` reaches it
by name only; numbers never select it.

### Byte 6 on a color sensor — not reflection

Byte 6 held `0x00` with a **white** brick at contact — maximum
reflectance, the condition that would peg a reflection byte. It was also
`0x00` for red and for nothing-at-all. So the light level is not in the
advertisement, at least not here.

Practical consequence: `colorSensor.detect_color()` could in principle be
served passively from advertisements, but `colorSensor.reflection()`
genuinely requires a GATT connection.

It also retroactively explains the `0xff` that originally looked like a
stick reading of `-1`. It was never an axis. `0xff` is
`LEGO_COLOR_NONE` (firmware `-1`), i.e. "no color detected", being
misread by an axes decoder that had no business running on that device.

Because it's a *firmware* code it needs `_firmware_to_app()` before it
means anything to the `legoeducation` API — see the numbering section above.

### A card serial is not unique

**Cards can share a serial number if they're different colors.** Three
cards numbered 1126 turned up in a single 20-card sample — purple, yellow
and red — all with identical `b3 b4` = `66 04`:

```
PURPLE#1126   b1=02  b2=f3  b3,b4=66 04  b7=48
YELLOW#1126   b1=07  b2=c2  b3,b4=66 04  b7=12
RED#1126      b1=09  b2=f1  b3,b4=66 04  b7=35
```

Three collisions in twenty cards means this is normal, not a fluke —
serial numbers are evidently allocated per color.

The identifying key for a card is the **(color, serial) pair**. Anything
keyed on serial alone will silently collide — `log_cards.py` had
exactly that bug, caught by its own consistency check.

Worth checking what this means for `lelib`'s
`connect(card_serial, card_color=None)`: with `card_color` left at
`None`, a serial that exists in more than one color is ambiguous, and
which device you reach may come down to whichever answers first.

### Bytes 2 and 7 — a CRC-16 of the card's RFID UID

**Solved, and verified on all 39 cards in `card_taps.csv` with no
exceptions.** `b2:b7` is a **CRC-16 of the card's 7-byte NFC UID**:
polynomial `0x0001`, reflected in and out, init `0`, output big-endian, so
`b2` is the high byte and `b7` the low one.

Polynomial `0x0001` is x¹⁶ + 1, which makes this a 16-bit XOR/parity fold of
the UID rather than anything cryptographic. Anyone holding the UID can
compute it.

1. Start a 16-bit running value at `0`.
2. For each UID byte: reverse its 8 bits (the chip reads bits lowest-first),
   XOR it into the top of the running value, then run 8 rounds of "shift left
   one bit; if a bit fell off the top, XOR the polynomial back in."
3. Reverse the 16 result bits and split: high half is `b2`, low half is `b7`.

| UID | b2 | b7 |
|---|---|---|
| `0413AA7ACC2191` | `0xf3` | `0x48` |
| `04B6A9A2CC2190` | `0xf1` | `0x35` |
| `0419AA7ACC2190` | `0xf2` | `0x42` |

Implementations: `card_hash.py` on the Mac (`python card_hash.py
04:13:AA:7A:CC:21:91`, and `--verify` re-checks all 39 rows of
`card_taps.csv`), and `card_hash()` in `pico tests/lego_card.py` for the
board, next to the RFID read that produces the UID.

**Getting the UID:** read the card with `examples/stick_read_card.py`, or take
it from `card_taps.csv`. Do *not* take it from page 0 of the raw tag dump
without care — that page splices the BCC check byte into the middle of the UID
(`04B1C8` **`F5`** `82871F90`). `read_card()` hands back the clean seven bytes.

The first two cards ever to have UID and tokens recorded together, from back
when this was still an open question, both check out:

| Card | RFID UID | b2 | b7 |
|---|---|---|---|
| PURPLE #6055 | `04 B1 C8 82 87 1F 90` | `0xdb` | `0x2c` |
| ORANGE #7569 | `04 1C 6E 82 87 1F 90` | `0x7d` | `0x81` |

**Why this held out so long: the message was never on the air.** Every
earlier attack solved for a function of the color and serial, and no such
function exists — correctly, since the input is the UID, which the beacon
does not carry. The negative results below all stand; they were aimed at the
wrong message.

**A motor cannot verify this either**, for the same reason: with no UID in
the broadcast it can only compare the incoming `b2`/`b7` against what it
stored when the card was tapped. So the check is an equality test against a
remembered value, not a computation.

**What it changes.** A card's UID is now enough to drive its motor — no tap
on a sender, no harvesting bytes off the air. `examples/stick_tap_to_drive.py`
used to carry a hand-filled table of tokens and now computes them, so any
card works on first tap. And since a UID is just a number, a `(serial, hash)`
pair can be fabricated for a card that was never manufactured.

#### How it was cornered

The rest of this section is the road there, kept because the reasoning is
worth not repeating. Read it as "why the answer had to be an invisible
per-card input," which is what pointed at the UID.

Neither byte can be device identity: `b2=de`/`b7=75` were **identical across two
different physical devices** holding the same card. And they're
deterministic per card — swapping RED#1133 for PURPLE#1126 on one sensor
produced `f3`/`48`, exactly the values that card had shown on a different
device earlier.

Sixteen cards were logged with `log_cards.py` into a `cards.csv` that has
since been deleted, superseded by the larger `card_taps.csv` (recover it
with `git show 2d9c572:card_mode/cards.csv` if a claim below needs
re-checking; earlier revisions of this file said twenty cards, but it held
sixteen rows from the commit that added it). The conclusion from
that sample: **b2 and b7 are not
derived from the visible card fields at all.** That held up — the input is
the UID, which is not a visible field.

The evidence, in the order it ruled things out:

**Not a sequential ID.** Adjacent serials give unrelated bytes. BLUE#1001
→ `d6`/`12` and BLUE#1003 → `c3`/`c9`; ORANGE#7551 → `09`/`fd` and
ORANGE#7552 → `c8`/`a0`. A one-step serial change scrambles both bytes,
which kills the "extra low bytes of a longer ID" reading they first
suggested.

**Color is an input, if it's a function at all.** Three cards share
serial 1126 and differ only in color, producing three different pairs:

| Card | b1 | b2 | b7 |
|---|---|---|---|
| PURPLE#1126 | `02` | `f3` | `48` |
| YELLOW#1126 | `07` | `c2` | `12` |
| RED#1126 | `09` | `f1` | `35` |

**Not a CRC-8.** Brute force over all 256 polynomials × 256 init values ×
input reflection × output reflection × xorout, across several input-byte
selections, for b2 and b7 independently: zero hits over 20 cards.

**Not a CRC-16 either.** Same search shape treating b2/b7 as the two
halves of a 16-bit checksum — all 65536 polynomials × init × reflection
combinations × several input orderings and both byte orders: zero hits
over 16 cards. With 16 samples a chance hit is ~2⁻²⁵⁶, so a genuine CRC
would have been found.

**They are unique per card.** All 16 `(b2, b7)` pairs are distinct, and so
are all 16 values of b2 and all 16 of b7. Consistent with a random-per-card
token. (Across the 39 in `card_taps.csv` all 39 pairs are still distinct,
with 34 distinct values each — the collisions are in single bytes only,
about what 39 draws from 256 should give.)

> Retracted: an earlier note here claimed every observed b2 had both top
> bits set, suggesting `b2 & 0xc0` was a constant marker. That held for
> the first six cards and broke immediately on a wider sample — b2 values
> include `53`, `09`, `04`, `1e`, `2b`. b2 is uniformly distributed.

#### Settled at 39 cards: not a checksum of the color and serial

(Still true, and the reason to look elsewhere for the message.)

`card_taps.csv` holds **39 cards with their RFID UIDs**. Before the older
`cards.csv` was retired, 15 of its 16 cards overlapped these and every one
agreed exactly — measured months apart, with a different tool. So b2/b7
really are a deterministic function of the card; the question was only ever
*of what*.

**Device type is not one of the inputs.** Eleven of those repeat cards were
measured on a **color sensor** (`b0=02`) one time and a **controller**
(`b0=03`) the other, and every one gave byte-identical b2/b7:

```
fw1 #1127  dev2 27/e0 | dev3 27/e0      fw3 #1392  dev2 04/ab | dev3 04/ab
fw1 #2306  dev2 31/49 | dev3 31/49      fw7 #2     dev2 53/27 | dev3 53/27
fw2 #6081  dev2 ef/0a | dev3 ef/0a      fw8 #7583  dev2 de/a2 | dev3 de/a2
```

A checksum whose message includes the device type has to change when the
device type changes. So byte 0 contributes nothing, which also means
"checksum of color + serial + sensor type" reduces to "checksum of color +
serial" — already dead by the GF(2) test below. Adding fields that are
constant per card cannot rescue the idea; only a field that *varies between
cards* can, and the UID is the only candidate left.

**One test kills the whole checksum family.** Every CRC, of any width,
polynomial, init value, reflection and xorout, and every XOR/parity or
LFSR digest, is an **affine function over GF(2)** of the message bits. So
instead of sweeping parameters, solve for affinity directly: build the
39×25 system over GF(2) (24 message bits — color and 16-bit serial — plus a
constant) and ask whether *any* affine function reproduces the target bit.

    b7 ~ affine(color, serial)      bits 0-7:  no no no no no no no no
    b2 ~ affine(color, serial)      bits 0-7:  no no no no no no no no
    CONTROL: serial_lo ~ affine(…)  bits 0-7:  OK OK OK OK OK OK OK OK

The control — a byte that *is* trivially linear in the message — passes on
all eight bits, so the machinery works. b2 and b7 fail on all eight. That
is not "no parameters found"; it is "no such function exists," and it
supersedes the CRC-8 and CRC-16 sweeps above rather than repeating them.

**Sum-style checksums fail too**, and they need a separate argument because
carries make them non-linear over GF(2). Any checksum that adds the color
and the serial into an accumulator is *separable*: the difference between
two colors at the same serial must be the same at every serial. It isn't.
Four serials are carried by more than one color — 1126 (yellow, orange,
red), 1127 and 1128 (magenta, purple), and 1133 (five colors) — which gives
two color pairs sampled at more than one serial:

| pair | serials | Δb2 | Δb7 |
|---|---|---|---|
| magenta − purple | 1127, 1128, 1133 | `b3 55 ad` | `48 c4 7e` |
| orange − red | 1126, 1133 | `88 75` | `50 35` |

Both scatter. Serial 1133 alone exists in five colors and gives five
unrelated pairs (`f2/42`, `45/c4`, `e6/ae`, `53/aa`, `de/75`).

The magenta−purple row is the load-bearing one: three serials, three
different deltas, so no additive scheme can hold.

**What that left open — and how it resolved.** The one reading that survived
everything above was a digest over a *larger* message, one including the RFID
UID or some registration number never seen. That is exactly what it turned
out to be, with the UID as the whole message.

The plan recorded here was to wait for about **90 UID-bearing cards** before
the GF(2) test could decide it, on the grounds that 39 cards against 81
unknowns is underdetermined and fits trivially. That was the right caution
for *that* test and the wrong prediction about the work: the answer came from
searching CRC parameters against the UID directly, where 39 cards is a
crushing amount of evidence rather than a shortage. A 16-bit function
matching 39 known outputs by chance is ~2⁻⁶²⁴.

**One earlier near-miss, worth keeping.** When only the two cards above had
UID and tokens together, a CRC-8 sweep over them produced 54 candidate
parameter sets, and the note here called it *not a result* — two samples of
8 bits are fitted by chance by roughly any 8-bit function. That caution was
right, and doubly so in hindsight: the real answer is 16-bit and treats b2
and b7 as one value, so a CRC-8 sweep was searching a space that never
contained it. All 54 were noise. What the note asked for — more cards — is
what arrived, via `examples/stick_log_cards.py`.

Worth keeping as a lesson: the sample was sufficient two paragraphs before
anyone believed it was. The blocker was the choice of message, not the number
of cards.

### The symbol printed on a card is not in the broadcast

Cards of different colors carry the same printed symbol — purple and green
both show a square. Nothing in the twelve bytes reflects that.

`b1` is the beacon's only color-dependent field, and it is exactly the
color — green broadcasts `06`, every purple broadcasts `02`. b2/b7 are
per-card, and the twelve purple cards logged hold twelve different values
of each. The card's own memory has nothing either: pages 8–19 read as
zeros and page 5 carries only the color and serial. So a device cannot
tell "same symbol" from the air, and neither can we.

**The full mapping, read off the physical cards** (eight of the ten colors
photographed together; teal and white were not in the set):

| fw | color | symbol |
|---|---|---|
| 1 | magenta | heart |
| 2 | purple | square |
| 3 | blue | diamond |
| 4 | azure | heart |
| 5 | teal | — **no such card** |
| 6 | green | square |
| 7 | yellow | circle |
| 8 | orange | diamond |
| 9 | red | circle |
| 10 | white | — **no such card** |

**The table is complete: eight card colors, four symbols, two colors each.**
Teal and white are not missing data — there are no teal or white cards, so
there is no fifth symbol to look for.

That is not just an argument from an incomplete photo. It falls out of a
partition this document already had, from the other direction:

| | sensor detects it | sensor cannot |
|---|---|---|
| **card exists** | red, yellow, blue, green, purple | magenta, azure, orange |
| **no card** | teal, white | — |

The right-hand column is the already-recorded fact that magenta, orange and
azure exist *only* as card colors. The bottom-left cell is the new one, and it
is the exact complement: teal and white exist only as things the **sensor** can
see. Two independent observations, each derived without reference to the other,
carving the ten firmware codes into the same three groups.

Corroborating: none of the 39 cards in `card_taps.csv` is teal or white. That
is weaker than it looks — no card there is azure either, and azure cards
plainly exist — so treat it as consistent rather than as the proof.

> **Retracted: the period-4 pairing.** An earlier version of this section had
> only four data points and read the colors as pairing off by firmware code,
> `(1,2) (3,4) (5,6) (7,8) (9,10)`, with each pair sharing a symbol. It set
> its own falsification test — *"look at a red card. Symbol A confirms the
> period-4 reading; anything else means the pairing stops at pairs"* — where
> symbol A was the square shared by purple and green.
>
> **A red card carries a circle.** The pattern is dead, exactly as the test
> specified, and it failed twice over: `(1,2)` is wrong too, since magenta is
> a heart and purple a square.
>
> That last point also contradicts the prose this section opened with, which
> claimed magenta shared the green/purple symbol. The photograph says
> otherwise. Flagged rather than quietly dropped, since it was recorded as a
> direct observation of physical cards: if a magenta card showing a square
> does turn up, the "two colors per symbol" reading is wrong as well.

The real pairs are `{1,4} {2,6} {3,8} {7,9}` by firmware code and
`{8,10} {5,6} {3,9} {1,2}` by App code. Neither is a clean arithmetic rule,
and after two overfitted patterns in this document the right move is to stop
looking for one: the symbol is an attribute of the color, assigned two colors
to a symbol, and nothing observed says it is computed from the code.

**Is the symbol constant within a color?** Assumed throughout, and it is what
makes "magenta is a heart" a fact about magenta rather than about one card. The
support is the purple set — every purple card seen carries a square — and the
b1 argument, since the beacon has one byte per color and no room to distinguish
cards of the same color. Not yet checked directly on magenta, which is the
largest group in `card_taps.csv` at 11 cards and therefore the cheapest place
to falsify it: one magenta card with a square would overturn this whole
section.

Colors here were identified from a photograph, so azure and blue could in
principle be swapped with each other. That does not touch the retraction
above — red against square is what killed it, and red is unmistakable.

### Byte 8 — unidentified analog value

Differs between two devices holding the same card (`86` vs `85`), and
drifts downward over a session on a single device (`87 → 85 → 84 → 7f`).
That rules out the uptime-counter reading it first suggested.

It also **oscillates** in place. Watching RED#1133 for 20 seconds with
`watch_service_data.py`, b8 went `7f → 7e → 7f → 7e` while nothing else
moved and nothing was touched. A counter doesn't do that; a live analog
measurement dithering around its true level does. Combined with the
long-run decline, battery voltage fits well.

**But it is not monotonic.** On the color sensor b8 read `86`, then `85`,
then `7f`, then `85` again twenty minutes later — a rise of 6. Battery
voltage does recover when load drops, so this isn't fatal to the reading,
but "slowly declining counter" is definitely wrong and "battery" is not
established. A temperature reading would behave similarly.

Test to confirm: compare a freshly charged device against a nearly flat
one, and check whether the oscillation band tracks the level. If that
fails, treat b8 as an unidentified slowly-varying analog value.

## The card itself, read over RFID

The connection cards turn out to be plain **NTAG/Ultralight** tags (SAK
`0x00`, 7-byte UID), and they store the color and serial in the clear.
Read with an M5Stack RFID2 Unit (WS1850S) on an M5StickS3:

```
UID  04B1C882871F90
page 0   04B1C8 F5 82871F90 8A 48 FFFF 0000     standard NTAG: UID, BCC, lock
page 4   4C334730 000217A7 00000000 FFEEDDCC
         "L3G0"      ^^ ^^^^-- 0x17A7 = 6055
                     +-------- 0x02 = firmware PURPLE
page 16  000000FF 00050000 ...
```

So the layout from page 4 is:

| Page | Bytes | Meaning |
|---|---|---|
| 4 | `4C 33 47 30` | ASCII `L3G0` — magic marker, tells a LEGO card from any other NTAG |
| 5 | `00 <color> <serial hi> <lo>` | color is the **firmware** code; serial is **big-endian** |
| 6 | `00 00 00 00` | zero |
| 7 | `FF EE DD CC` | fixed filler |

Confirmed on two cards of different colors: purple `000217A7` → 6055, and
orange `00081D91` → firmware `0x08` (orange), 7569. Both match what is
printed on the card.

**The serial is big-endian on the card and little-endian in the FD02
broadcast.** Copying one into the other without swapping gives a
plausible-looking wrong number.

**b2/b7 are not stored on the card**, but they are *computed from* it — a
CRC-16 of the UID that page 0 carries. Nothing in pages 4–19 resembles them.
The whole story is in
[Bytes 2 and 7](#bytes-2-and-7--a-crc-16-of-the-cards-rfid-uid); the only
thing to know here is that **page 0 splices the BCC check byte into the UID**
(`04B1C8` **`F5`** `82871F90`), so feeding that page straight to `card_hash()`
gives a wrong answer. `read_card()` returns the clean seven bytes.

So one tap now gets you everything: color, serial *and* the hash. That closes
the last thing the air was needed for.

Both cards in that section's UID table read identically from a color sensor
and from a controller carrying the same card — the "per card, not per device"
property, confirmed directly rather than inferred.

Decoder: `pico tests/lego_card.py`. `decode_pages()` is pure and can be
checked off-hardware; `read_card()` needs the reader, and `card_hash()`
turns the UID it returns into b2/b7.

## Tooling

| Script | Purpose |
|---|---|
| `scan_advertising.py` | live table of everything in range, for eyeballing |
| `watch_service_data.py` | lock onto one card, log every byte change |
| `verify_colors.py` | prompt through all 11 colors, verify what byte 5 reports |
| `log_cards.py` | tap-through card logger — one row per (color, serial) |
| `card_hash.py` | b2/b7 from a card's RFID UID; `--verify` re-checks all 39 cards |
| `capture_controller.py` | guided capture protocol for the controller |
| `capture_colorsensor.py` | guided capture protocol for the color sensor |
| `adv_capture.py` | shared capture engine — discovery, prompting, timed segments, CSV |
| `analyze_payload.py` | per-byte differencing over a capture CSV |
| `simpletest.py` | hardcoded decoder for the original `data from controller` log |
| `CLAUDE.md` | distilled findings + "don't retry these" list |

Data files: `card_taps.csv` (39 cards with their RFID UIDs) and `data from
controller` (38 controller packets, the original capture this all started
from).

The older `cards.csv` (16 cards, no UIDs, written by `log_cards.py`) has
been **deleted** — `card_taps.csv` covers 15 of its 16 and carries the UID
as well. The one card lost is PURPLE #1126 (`b2=f3 b7=48`), which was the
second sample in the purple−orange and purple−red separability rows; those
rows are gone from the table above, and magenta−purple across three serials
carries the argument on its own. Retrieve the whole file from git if it is
ever wanted again:

```bash
git show 2d9c572:card_mode/cards.csv
```

Note `mac_fetch_cards.py` overwrites `card_taps.csv` verbatim from the
board, so hand-pasted rows do not survive a fetch — to restore that card,
re-tap it and let the Stick log it.

### Watching one device

`watch_service_data.py` locks onto a single card and prints an event log —
one line per byte that moves, nothing while things are still. Every event
leads with the full payload and puts carets under what changed:

```
11:52:06.153  02 09 de 6d 04 09 00 75 7e | 3c 22 9e
                             ^^
              b5  0xff -> 0x09   DETECTS NOCOLOR -> RED
```

The `|` marks where the churn bytes start. Bytes 9–11 are still printed
but don't count as changes, otherwise every advertisement would be an
event.

```bash
python watch_service_data.py                        # defaults to RED#1133
python watch_service_data.py --bytes 5,6            # just the reading
python watch_service_data.py --serial 1126 --color PURPLE
python watch_service_data.py --every                # payload every packet
```

It matches on color **and** serial, because a bare serial is ambiguous —
see [A card serial is not unique](#a-card-serial-is-not-unique).

### Guided capture

The capture scripts prompt you through a scripted sequence ("LEFT lever
FULL forward, hold"), record every advertisement during each window, and
label the rows automatically. The analyzer then compares each byte's
distribution under stimulus against its distribution during a
hands-off `baseline` segment, which is what separates payload bytes from
counters and CRC.

```bash
python capture_controller.py --manual
python analyze_payload.py capture_controller.csv
python analyze_payload.py a.csv b.csv     # compare mode
```

Validated against the existing `data from controller` capture: the
analyzer independently classified b5/b6 as responsive, b9–b11 as
counters/CRC, and rediscovered the deadzone (magnitudes jump 0 → 3,
skipping 1 and 2).

## Other things scan_advertising.py does

**LEGO-only filtering** (`is_lego()`) — by default only advertisements
carrying LEGO's signature are shown: company ID `0x0397` in manufacturer
data, or `FD02` in `service_uuids` / `service_data`. `--all` disables
this.

**Noise filtering** — with `--all`, a secondary filter suppresses known
irrelevant traffic by name substring, company ID (Apple's `0x004c`, etc.),
service UUID, or exact address. `--include-noisy` disables it.

**Change detection (`*` marker)** — compares on the *decoded* fields
(card + axes), not the raw payload. LEGO's trailing bytes past
color/serial appear to rotate on every single advertisement, so comparing
raw bytes would light up `*` permanently instead of only on a real card
tap.

**Row lifecycle** — rows refresh in place every 0.5 s and are dropped
after 10 s of silence.

**Note on extended advertising**: bleak hands you the merged
advertisement + scan-response payload, not the raw HCI PDU, so there's no
portable way to tell whether a packet arrived as a legacy or BLE5
extended-advertising PDU. That needs a dedicated sniffer (nRF52840 +
Nordic sniffer firmware + Wireshark, or `btmon`/`hcidump` on Linux).

---

## Open problem: L/R axes

Both original symptoms are now explained, and one of them is fixed.

1. ~~**It fires on non-controllers.**~~ **Fixed.** `decode_controller_axes()`
   now gates on the byte-0 device type, so only `0x03` devices produce an
   axes reading. Verified against real payloads: the color sensor's
   phantom reading is gone and card decoding is unaffected.
2. ~~**`RED#1133` read `R:-1` at rest.**~~ **Explained, not a bug in the
   axes at all.** That was the color sensor, and `0xff` was
   `LEGO_COLOR_NONE` — "no color detected" — not a signed `-1`. The
   controller's axes do rest at exactly `0`, replicated across two
   sessions and two devices.

**What remains open is the encoding of the values themselves**, and
whether the controller reports stick position or motor speed.

### What we already know

From the 38-sample `data from controller` capture, two findings that
narrow the question considerably:

**The controller is not a dumb ADC.** The resting value is *exactly* `0`
in every sample, and the observed magnitudes skip 1 and 2 (the set is
`{0, 3, 13, 14, 16}`). A raw potentiometer read jitters in the low bits
and never sits at a clean zero. The controller is applying centering and
a deadzone, so it is doing *some* processing. The open question is
narrower than raw-vs-cooked: is byte 5/6 a normalized stick **position**,
or an actual motor **speed command**?

**The encoding is ambiguous, and one test settles it.** Every observed
magnitude is ≤ 16, which fits two readings equally well:

- **signed byte** — `0xf0` = −16, `0x10` = +16; full deflection lands near ±100
- **two packed 4-bit fields** — `0xf0` = high nibble −1, `0x03` = low nibble +3,
  and each byte would carry *two* axes, making bytes 5–6 four axes total

Push a lever to its mechanical stop and read the magnitude: ~±100 means a
normalized percentage (a speed command), ±127 means position-like, ±7
means packed nibbles.

### Debugging plan

- [x] ~~**Gate the axes decode on byte 0**, not on payload length.~~ Done.
      Still only a partial fix while two distinct devices both advertise
      `0x03`.
- [ ] **Full-deflection capture** — the scale test above. Highest-value
      single measurement; do it first.
- [ ] **Combination segments** (both levers at once). If moving one lever
      touches one nibble and moving both lights up two, the packed layout
      is confirmed. The existing capture never moved two levers together,
      which is exactly why it can't distinguish.
- [ ] **Receiver-dependence test** — capture the same lever position with
      no motor powered, with the single motor, and with the double motor,
      then `analyze_payload.py a.csv b.csv c.csv`. Identical bytes ⇒ the
      controller broadcasts blindly and the motor interprets. Different
      bytes ⇒ the controller is computing something receiver-specific.
- [ ] **Byte vs. actual RPM** — log advertisements while measuring motor
      speed optically (striped wheel + color sensor at `set_update_rate(15)`,
      reusing `../tests/light_scope.py`). Linear ⇒ the byte is the speed
      command. Nonlinear ⇒ the motor applies its own curve. Optical
      avoids the connection conflict: the controller likely occupies the
      motor's only BLE connection slot.
- [ ] **Sideways axes** — check whether the levers move on a second axis
      at all. A null result is still data.
- [x] ~~**Bytes 7–8** — possibly a 16-bit uptime clock.~~ Wrong. They're
      two unrelated things: b7 is the low byte of the card's UID hash, and
      b8 is a device-level analog value that oscillates and has risen as
      well as fallen. Neither is a counter.
- [x] ~~**Byte 2** — identity or session nonce?~~ Neither. It's card-derived
      and stable across devices and power cycles — the high byte of the same
      CRC-16 as b7.
- [ ] **Buttons** — still unlocated. They aren't in b7/b8, and no payload
      length change has been seen. `capture_controller.py` and
      `capture_colorsensor.py` both include a `button_held` segment.

Once the axes are actually pinned down, update both this file and the
docstring on `decode_controller_axes()` in
`scan_advertising.py`.

---

## Running it

```bash
python scan_advertising.py                      # LEGO devices only
python scan_advertising.py --name Move          # filter by name substring
python scan_advertising.py --all                # every BLE device in range
python scan_advertising.py --all --include-noisy
```

Ctrl+C to stop.
