'''
Fake LEGO Education controller for a Raspberry Pi Pico W / Pico 2 W
(MicroPython). Broadcasts a crafted advertising beacon so a nearby Single (or
Double) Motor drives itself — NO GATT connection, NO real controller, NO hub.

  >>> Runs ON the Pico W, not the Mac. A plain Pico (no radio) can't do this.
      Copy to the Pico as main.py (e.g. via Thonny) and run. <<<

Why the Pico and not the Mac: macOS/bleak can only scan & connect, never
transmit custom advertisements. Brick-to-brick control here is connectionless
BLE *broadcast*: every device tapped with the same card is one group, keyed by
the card's color + serial. Controllers broadcast their stick state; motors
listen and act, combining/averaging all senders they hear.

── Auto-adopt: DOES NOT WORK, retracted ────────────────────────────────
AUTO_ADOPT was built on the belief that a motor announces its own
color+serial in a manufacturer-data advertisement, so the Pico could scan
for the nearest motor and copy its card. **A motor does not advertise at
all** -- it only ever listens. A scan filtering on LEGO's company ID 0x0397
returns nothing with a motor powered on and carded, so scan_for_motor()
below can never find one. Leave AUTO_ADOPT = False and set the card by hand.

Get the numbers from a *sender* carrying the card (a controller or color
sensor) with ../watch_service_data.py, or read the color and serial off the
card itself with ../examples/stick_read_card.py.

── Beacon layout (reverse-engineered; see scan_advertising.py) ──────────
    03  cc  f3  sl sh   b5 b6   48 80   k2 k1 k0
    |   |   |   \___/   \___/   \___/   \______/
    |   |   |   serial  sticks  const   24-bit counter (big-endian; must keep
    |   |   |  (le16)  (see     per-     advancing so packets look "fresh")
    |   |   |          below)   ctrlr
    |   |   byte 2: unknown constant, copied from a real controller
    |   card color (0x02 = purple)
    byte 0: message/type tag, constant 0x03

Two joysticks are nibble-INTERLEAVED across bytes 5 & 6, each a signed 8-bit
value (~+/-48 full scale):
    LEFT  = (b6 low nibble << 4) | (b5 high nibble)
    RIGHT = (b5 low nibble << 4) | (b6 high nibble)
The motor combines them: both up -> full forward, both down -> full reverse,
opposite -> ~cancel. This file encodes that layout exactly (earlier versions
used a wrong merged-12-bit value that only worked at the extremes).
'''

import bluetooth
import time
from micropython import const

# ── behavior ─────────────────────────────────────────────────────────
AUTO_ADOPT = False         # BROKEN -- motors do not advertise; see the note above
SCAN_MS = 4000             # how long to scan for a motor before giving up

# Manual card — used when AUTO_ADOPT is False (the reliable, known-good path).
# Set these to YOUR motor's card. Read them off the Mac: run
# scan_advertising.py and look at the motor's "LEGO Card" column, e.g.
# "Purple#1126" -> CARD_COLOR = 0x02 (purple), CARD_SERIAL = 1126.
CARD_COLOR = 0x02          # 0x02 = purple (legoeducation color map)
CARD_SERIAL = 1126

# Drive: hold fixed stick values, or (both None) sweep both sticks together
# 0 -> +100 -> 0 -> -100 -> 0 so the motor goes full-forward then full-reverse.
FIXED_LEFT = None          # -100..100, or None
FIXED_RIGHT = None         # -100..100, or None
LOOP = True

# ── beacon constants (copied from a real controller; meaning unconfirmed) ─
TYPE_TAG = 0x03
BYTE2 = 0xf3
FIXED_78 = b'\x48\x80'
SERVICE_UUID16 = 0xFD02
STICK_FULL_SCALE = 48      # signed-8 value a real stick sends at full deflection

ADV_INTERVAL_US = 100_000
STEP_MS = 40
COUNTER_STEP = 0x00B300

LEGO_COMPANY_ID = 0x0397
MOTOR_PRODUCT_GROUP = 2    # product_id high byte for Single/Double Motor (512/513)

_IRQ_SCAN_RESULT = const(5)
_IRQ_SCAN_DONE = const(6)


# ── stick encoding (inverse of decode_controller_axes) ────────────────
def _clamp(p):
    return -100 if p < -100 else 100 if p > 100 else p


def _stick_pair(left_pct, right_pct):
    '''(left%, right%) -> (b5, b6), nibble-interleaved signed-8 each.'''
    left = round(_clamp(left_pct) / 100 * STICK_FULL_SCALE) & 0xFF
    right = round(_clamp(right_pct) / 100 * STICK_FULL_SCALE) & 0xFF
    b5 = ((left & 0x0F) << 4) | (right >> 4)   # left low nibble | right high nibble
    b6 = ((right & 0x0F) << 4) | (left >> 4)   # right low nibble | left high nibble
    return b5, b6


def _beacon(color, serial, left_pct, right_pct, counter):
    b5, b6 = _stick_pair(left_pct, right_pct)
    svc_payload = bytes([
        TYPE_TAG, color, BYTE2,
        serial & 0xFF, (serial >> 8) & 0xFF,
        b5, b6,
    ]) + FIXED_78 + bytes([
        (counter >> 16) & 0xFF, (counter >> 8) & 0xFF, counter & 0xFF,  # big-endian
    ])
    sd = bytes([0x16, SERVICE_UUID16 & 0xFF, (SERVICE_UUID16 >> 8) & 0xFF]) + svc_payload
    flags = bytes([0x02, 0x01, 0x06])
    return flags + bytes([len(sd)]) + sd


# ── advertisement parsing (find a motor's card) ───────────────────────
def _lego_card_from_adv(adv):
    '''Return (product_id, color, serial) if adv carries LEGO manufacturer
    data (company 0x0397), else None. Layout after the 2-byte company id:
    [group, device, color, serial_lo, serial_hi].'''
    i = 0
    n = len(adv)
    while i + 1 < n:
        ln = adv[i]
        if ln == 0:
            break
        ad_type = adv[i + 1]
        payload = adv[i + 2:i + 1 + ln]
        if ad_type == 0xFF and len(payload) >= 7:
            company = payload[0] | (payload[1] << 8)
            if company == LEGO_COMPANY_ID:
                lego = payload[2:]
                product_id = (lego[0] << 8) | lego[1]
                return product_id, lego[2], lego[3] | (lego[4] << 8)
        i += 1 + ln
    return None


def scan_for_motor(ble, duration_ms):
    '''Scan and return (color, serial) of the strongest nearby motor, or None.'''
    best = {'rssi': -999, 'color': None, 'serial': None, 'product': None}
    done = {'flag': False}

    def on_irq(event, data):
        if event == _IRQ_SCAN_RESULT:
            _, _, _, rssi, adv_data = data
            card = _lego_card_from_adv(bytes(adv_data))
            if card is None:
                return
            product_id, color, serial = card
            # Only adopt motors (product group 2 = Single/Double Motor).
            if (product_id >> 8) == MOTOR_PRODUCT_GROUP and rssi > best['rssi']:
                best.update(rssi=rssi, color=color, serial=serial, product=product_id)
        elif event == _IRQ_SCAN_DONE:
            done['flag'] = True

    ble.irq(on_irq)
    ble.gap_scan(duration_ms, 30_000, 30_000, True)  # active scan
    while not done['flag']:
        time.sleep_ms(50)
    ble.irq(None)
    if best['color'] is None:
        return None
    return best['color'], best['serial'], best['product']


# ── drive ─────────────────────────────────────────────────────────────
def _sweep_together():
    def ramp(a, b, n):
        return [round(a + (b - a) * i / n) for i in range(1, n + 1)]
    seq = [0]
    seq += ramp(0, 100, 40) + [100] * 15 + ramp(100, 0, 40) + [0] * 10
    seq += ramp(0, -100, 40) + [-100] * 15 + ramp(-100, 0, 40) + [0]
    return [(v, v) for v in seq]  # both sticks together


def main():
    ble = bluetooth.BLE()
    ble.active(True)

    color, serial = CARD_COLOR, CARD_SERIAL
    if AUTO_ADOPT:
        print("Scanning {} ms for a motor...".format(SCAN_MS))
        found = scan_for_motor(ble, SCAN_MS)
        if found:
            color, serial, product = found
            print("Adopted motor card: color 0x{:02x} serial {} (product {})".format(
                color, serial, product))
        else:
            print("No motor found — falling back to manual card 0x{:02x}#{}".format(
                CARD_COLOR, CARD_SERIAL))

    print("Broadcasting as card 0x{:02x}#{}".format(color, serial))

    counter = 0

    def emit(left_pct, right_pct):
        nonlocal counter
        ble.gap_advertise(None)
        ble.gap_advertise(ADV_INTERVAL_US,
                          adv_data=_beacon(color, serial, left_pct, right_pct, counter),
                          connectable=False)
        counter = (counter + COUNTER_STEP) & 0xFFFFFF

    try:
        if FIXED_LEFT is not None or FIXED_RIGHT is not None:
            l = FIXED_LEFT or 0
            r = FIXED_RIGHT or 0
            print("Holding L:{:+d} R:{:+d}".format(l, r))
            while True:
                emit(l, r)
                time.sleep_ms(STEP_MS)
        else:
            seq = _sweep_together()
            while True:
                for l, r in seq:
                    emit(l, r)
                    print("L:{:+4d} R:{:+4d}".format(l, r))
                    time.sleep_ms(STEP_MS)
                if not LOOP:
                    break
    finally:
        ble.gap_advertise(None)
        ble.active(False)
        print("Stopped broadcasting.")


main()
