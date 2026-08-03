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
- Bytes 2 and 7 are an **independent per-card token** — not a checksum, not
  an ID extension, not derived from anything visible
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
| Service data | service UUID `0xFD02` | `[?, color, ?, serial_lo, serial_hi, ...]` | **Inferred empirically** — not from LEGO docs |

The serial is the same in both: little-endian at bytes 3–4,
`payload[3] | (payload[4] << 8)`.

The **color byte moves**: index 2 in manufacturer data, index 1 in service
data. That's the whole reason `_decode_card_bytes()` takes a `color_index`
argument. Note this is *not* a clean one-byte shift of the whole
structure — the serial stays at 3–4 either way, so byte 2 in the service
data form is something else entirely. It turned out to be half of a
per-card token; see
[Bytes 2 and 7](#bytes-2-and-7--an-independent-per-card-token).

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

**`0xfd02:0302f3660400004883fbb6b0`**

| Byte | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7… |
|---|---|---|---|---|---|---|---|---|
| Value | `03` | `02` | `f3` | `66` | `04` | `00` | `00` | `4883fbb6b0` |
| Meaning | ? | color | ? | serial lo | serial hi | ? | ? | rotating |

- color: `0x02` → firmware PURPLE → `PURPLE`
- serial: `0x66 | (0x04 << 8)` = `102 + 1024` = **1126**
- decoded → `PURPLE#1126` ✓

**`0xfd02:0209de6d04ff0075874de086`**

- color: `0x09` → firmware RED → `RED`
- serial: `0x6d | (0x04 << 8)` = `109 + 1024` = **1133**
- decoded → `RED#1133` ✓

This is the evidence the index-1 color hypothesis rests on: two
independent devices where the byte at index 1 matched the known card
color *and* bytes 3–4 matched the known serial. Consistent, but still a
working hypothesis, not a spec.

---

## The FD02 service-data byte map

Established by running a controller and a color sensor side by side while
they carried **the same card**, which separates card-derived bytes from
device-derived ones:

| Byte | Meaning | Confidence |
|---|---|---|
| 0 | device type — `0x02` color sensor, `0x03` controller | confirmed |
| 1 | card color, firmware code | confirmed |
| 2 | per-card token, not derived from anything visible | see below |
| 3–4 | card serial, little-endian | confirmed |
| 5 | **color sensor**: detected color, firmware code (`0xff` = none) | confirmed |
| 5–6 | **controller**: stick axes | position confirmed, encoding open |
| 6 | **color sensor**: always `0x00` so far — *not* reflection | see below |
| 7 | per-card token, same story as byte 2 | see below |
| 8 | slowly-varying analog value, oscillates ±1 | unidentified |
| 9–11 | change every packet — counters / CRC | confirmed |

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
| 3 | Blue | `0x03` | ⬜ not yet | read `0xff` (nothing detected) — needs a retest |
| 4 | Teal | `0x05` | ⬜ not yet | read `0xff` (nothing detected) — needs a retest |
| 5 | Green | `0x06` | ✅ | 8/8, plus observed live earlier |
| 6 | Purple | `0x02` | ✅ | observed live earlier; the sweep read RED, see below |
| 7 | White | `0x0a` | ✅ | 7/7, and 26/26 in an earlier predicted test |
| 8 | Magenta | `0x01` | n/a | card-only colour, sensor can't detect it |
| 9 | Orange | `0x08` | n/a | card-only colour, sensor can't detect it |
| 10 | Azure | `0x04` | n/a | card-only colour, sensor can't detect it |

**Six of the eight testable colors are confirmed.** Blue and teal both read
`0xff` — the sensor detected nothing at all rather than the wrong color,
which points at brick presentation rather than a wrong table entry. They
need re-measuring, not rewriting.

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

**Black is tested even though the App has no BLACK colour.** Firmware `0`
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
serial numbers are evidently allocated per colour.

The identifying key for a card is the **(color, serial) pair**. Anything
keyed on serial alone will silently collide — `log_cards.py` had
exactly that bug, caught by its own consistency check.

Worth checking what this means for `lelib`'s
`connect(card_serial, card_color=None)`: with `card_color` left at
`None`, a serial that exists in more than one color is ambiguous, and
which device you reach may come down to whichever answers first.

### Bytes 2 and 7 — an independent per-card token

Neither can be device identity: `b2=de`/`b7=75` were **identical across two
different physical devices** holding the same card. And they're
deterministic per card — swapping RED#1133 for PURPLE#1126 on one sensor
produced `f3`/`48`, exactly the values that card had shown on a different
device earlier.

Twenty cards were logged with `log_cards.py` (raw data in
`cards.csv`). The conclusion from that sample: **b2 and b7 are not
derived from the visible card fields at all.** They behave like an
independent per-card token.

The evidence, in the order it ruled things out:

**Not a sequential ID.** Adjacent serials give unrelated bytes. BLUE#1001
→ `d6`/`12` and BLUE#1003 → `c3`/`c9`; ORANGE#7551 → `09`/`fd` and
ORANGE#7552 → `c8`/`a0`. A one-step serial change scrambles both bytes,
which kills the "extra low bytes of a longer ID" reading they first
suggested.

**Colour is an input, if it's a function at all.** Three cards share
serial 1126 and differ only in colour, producing three different pairs:

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
over 20 cards. With 20 samples a chance hit is ~2⁻³²⁰, so a genuine CRC
would have been found.

**They are unique per card.** All 20 `(b2, b7)` pairs are distinct; b2 and
b7 each take 19 distinct values across 20 cards. Consistent with a
random-per-card token.

> Retracted: an earlier note here claimed every observed b2 had both top
> bits set, suggesting `b2 & 0xc0` was a constant marker. That held for
> the first six cards and broke immediately on a wider sample — b2 values
> include `53`, `09`, `04`, `1e`, `2b`. b2 is uniformly distributed.

**Recommendation: stop here.** Nothing in SimpleLE needs these bytes —
devices are addressed by colour and serial, both of which decode cleanly.
Cracking them would need either a much larger card sample or LEGO's own
documentation, and the payoff is curiosity rather than capability.

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

## Tooling

| Script | Purpose |
|---|---|
| `scan_advertising.py` | live table of everything in range, for eyeballing |
| `watch_service_data.py` | lock onto one card, log every byte change |
| `verify_colors.py` | prompt through all 11 colors, verify what byte 5 reports |
| `log_cards.py` | tap-through card logger — one row per (color, serial) |
| `capture_controller.py` | guided capture protocol for the controller |
| `capture_colorsensor.py` | guided capture protocol for the color sensor |
| `adv_capture.py` | shared capture engine — discovery, prompting, timed segments, CSV |
| `analyze_payload.py` | per-byte differencing over a capture CSV |
| `simpletest.py` | hardcoded decoder for the original `data from controller` log |
| `CLAUDE.md` | distilled findings + "don't retry these" list |

Data files: `cards.csv` (20 logged cards) and `data from controller` (38
controller packets, the original capture this all started from).

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
      two unrelated things: b7 is part of the per-card token, and b8 is a
      device-level analog value that oscillates and has risen as well as
      fallen. Neither is a counter.
- [x] ~~**Byte 2** — identity or session nonce?~~ Neither. It's card-derived
      and stable across devices and power cycles, part of the same token
      as b7.
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
