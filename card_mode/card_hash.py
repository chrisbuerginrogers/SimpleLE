'''
Compute a card's b2/b7 hash from its RFID UID.

Bytes 2 and 7 of the FD02 beacon are a CRC-16 of the card's 7-byte NFC UID:
polynomial 0x0001, reflected in and out, init 0, result big-endian, so b2 is
the high byte and b7 the low one. Polynomial 0x0001 is x^16 + 1, which makes
this a plain XOR/parity fold of the UID rather than anything cryptographic.

Verified against all 39 cards in card_taps.csv, exactly, with no exceptions.

    python card_hash.py 04:13:AA:7A:CC:21:91
    python card_hash.py 0413AA7ACC2191 04B6A9A2CC2190
    python card_hash.py --verify

Colons, dashes, spaces or bare hex all parse. --verify re-checks the whole
algorithm against card_taps.csv, which is the evidence the claim rests on.

Why this matters: it takes a physical tap out of the loop. Before this, the
tokens could only be read off the air from a device already carrying the card,
because they are not stored on the card either (see Card_mode.md). Now a UID
is enough -- and since a UID is just a number, so is a card that never existed.

The motor cannot check this itself: the UID is not in the broadcast, so it
compares the incoming b2/b7 against what it stored when the card was tapped.
'''

import argparse
import csv
import os
import sys


def _reflect(value, width):
    '''Reverse the low `width` bits of value -- 0b1101 -> 0b1011 at width 4.'''
    out = 0
    for _ in range(width):
        out = (out << 1) | (value & 1)
        value >>= 1
    return out


def card_hash(uid):
    '''(b2, b7) for a 7-byte card UID, given as bytes or a hex string.'''
    uid = parse_uid(uid) if isinstance(uid, str) else bytes(uid)
    crc = 0
    for byte in uid:
        crc ^= _reflect(byte, 8) << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x0001) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    crc = _reflect(crc, 16)
    return (crc >> 8) & 0xFF, crc & 0xFF


def parse_uid(text):
    '''Bytes for a UID written with colons, dashes, spaces or none of those.'''
    cleaned = text.replace(':', '').replace('-', '').replace(' ', '').strip()
    try:
        uid = bytes.fromhex(cleaned)
    except ValueError:
        raise ValueError('{!r} is not hex'.format(text))
    if len(uid) != 7:
        raise ValueError(
            '{!r} is {} bytes, but a LEGO card UID is 7'.format(text, len(uid)))
    return uid


# ── checking the claim against the logged cards ──────────────────────────

CARD_TAPS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         'card_taps.csv')


def verify(path=CARD_TAPS):
    '''Recompute every logged card. Returns (checked, list of failures).'''
    failures = []
    checked = 0
    with open(path) as handle:
        for row in csv.DictReader(handle):
            if not row.get('uid'):
                continue
            checked += 1
            got = card_hash(parse_uid(row['uid']))
            want = (int(row['b2']), int(row['b7']))
            if got != want:
                failures.append((row['uid'], want, got))
    return checked, failures


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.strip().split('\n')[0])
    parser.add_argument('uid', nargs='*',
                        help='card UID(s), 7 bytes of hex')
    parser.add_argument('--verify', action='store_true',
                        help='re-check the algorithm against card_taps.csv')
    args = parser.parse_args(argv)

    if args.verify:
        checked, failures = verify()
        for uid, want, got in failures:
            print('MISMATCH {}  logged {:02x}/{:02x}  computed {:02x}/{:02x}'
                  .format(uid, want[0], want[1], got[0], got[1]))
        print('{}/{} cards match'.format(checked - len(failures), checked))
        return 1 if failures else 0

    if not args.uid:
        parser.error('give a UID, or --verify')

    for text in args.uid:
        try:
            uid = parse_uid(text)
        except ValueError as e:
            print('{}: {}'.format(text, e), file=sys.stderr)
            return 1
        b2, b7 = card_hash(uid)
        print('{}  b2=0x{:02x}  b7=0x{:02x}'.format(
            ''.join('%02X' % b for b in uid), b2, b7))
    return 0


if __name__ == '__main__':
    sys.exit(main())
