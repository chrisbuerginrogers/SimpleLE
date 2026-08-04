# LEGO Education FD02 Broadcast Protocol (reverse-engineered)

LEGO Education bricks control each other **without any hub or connection** using
connectionless BLE **advertising broadcasts**. Every brick tapped with the same
card is one group (keyed by the card's colour + serial); senders (controllers,
colour sensors) broadcast their state, and motors listen and act — combining
multiple senders. This documents the beacon, decoded from live captures with
`scan_advertising.py`.

> Status: working hypothesis from captures, not official LEGO docs. Confirmed
> parts noted below; open questions at the end.

## Beacon — FD02 service data, 12 bytes

Carried as a **Service Data – 16-bit UUID** (`0xFD02`) AD structure.

| byte | meaning |
|------|---------|
| 0 | **type tag** — `0x03` = controller, `0x02` = colour sensor |
| 1 | card **colour** |
| 2 | card ID/hash (per-card; **required** — motor validates it) |
| 3–4 | card **serial**, little-endian |
| 5–6 | **live payload** (device-specific, see below) |
| 7 | card ID/hash (per-card; **required** — motor validates it) |
| 8–11 | rolling counter (byte 8 slow → byte 11 fast) |

Bytes 2 & 7 are a per-card hash (same card → same pair on any device) and the
motor **requires them** — a beacon with the right serial but wrong `byte2`/`byte7`
is ignored (confirmed). To spoof a card you must use its real `byte2`/`byte7`;
read them off any device already carrying that card. The hash algorithm is not
cracked (not a standard CRC-8/16 over colour+serial — see below).

## Controller — `byte0 = 0x03`

Two joysticks: **`byte6` = LEFT**, **`byte5` = RIGHT**.

The motor uses **only the low nibble** of each byte, read as a signed value.
The high nibble is ignored entirely (proven across many byte values).

| low nibble | `0` | `1` | `2` | `3` | `D` | `E` | `F` | `4`–`C` |
|------------|-----|-----|-----|-----|-----|-----|-----|---------|
| action | stop | +1 | +2 | **+3 fwd** | **−3 rev** | −2 | −1 | dead (out of range) |

→ **7 states per stick.** The motor **combines** the two axes (both up → full
forward, both down → full reverse, opposite → cancel).

## Colour sensor — `byte0 = 0x02`

**`byte5` = detected colour** (LEGO firmware colour code). `byte6` unused.

| `byte5` | `02` | `03` | `06` | `07` | `09` | `0A` | `FF` |
|---------|------|------|------|------|------|------|------|
| colour | purple | blue | green | yellow | red | white | none |

The sensor broadcasts **only the colour it sees** — the behaviours it triggers
(turn 90°, pulse, back-and-forth) are **not** in the packet; that colour→action
logic lives motor-side.

## Notes

- **Group address** = card colour (`byte1`) + serial (`bytes3–4`). A brick only
  obeys broadcasts matching its own card; you don't need the physical card, just
  the numbers (a motor announces its own card in its manufacturer-data ad).
- **No transmit on macOS** — bleak can only scan/connect. Broadcasting a beacon
  needs a Pico W (or Linux/BlueZ). See `pico_fake_controller.py`.
- **Confirmed by spoofing:** a Pico W broadcasting a crafted beacon drove a real
  motor with no connection and no real controller.

## Resolved

- `byte2` + `byte7` = per-card ID/hash (same card → same pair on any device),
  and the motor **requires** them (confirmed). Algorithm not cracked: no standard
  CRC-8, CRC-16, or Fletcher-16 over colour+serial reproduces them.
- `byte8` is **not** reflection — it holds/dithers ±1 regardless of brightness;
  it's part of the counter (8–11).
- Colour sensor broadcasts **only the detected colour category** (`byte5`); there
  is no reflection/brightness value in the beacon. Brightness only changes
  *which* colour it reports.

## Open questions

- Exact byte order / rate of the 8–11 counter.
- Whether `byte1` (colour) is validated for the group, or serial alone suffices.
- Behaviours (colour → 90° turn, etc.) are motor-side and not visible on the air.
