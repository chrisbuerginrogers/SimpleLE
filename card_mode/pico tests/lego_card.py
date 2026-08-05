'''
lego_card — read a LEGO Education connection card with an RFID reader.

  >>> read_card() runs ON the M5StickS3 (needs m5/ and the RFID2 Unit).
      decode_pages() is pure and can be checked anywhere. <<<

The cards are NTAG/Ultralight tags (SAK 0x00, 7-byte UID). The color and
serial are stored in the clear from page 4:

    page 4   4C 33 47 30                    ASCII "L3G0", a magic marker
    page 5   00 <color> <serial hi> <lo>    color is the FIRMWARE code,
                                            serial is big-endian
    page 6   00 00 00 00
    page 7   FF EE DD CC                    fixed filler

Read from a purple #6055 card:

    page 4  4C334730 000217A7 00000000 FFEEDDCC
                     ^^ ^^^^-- 0x17A7 = 6055
                     +-------- 0x02 = firmware PURPLE

Note the serial is big-endian here, while the FD02 broadcast carries it
little-endian. Do not copy one into the other without swapping.

── What is NOT on the card ───────────────────────────────────────────────
The b2/b7 tokens a motor validates are not here. They differ per card across
all 16 cards in ../cards.csv, so they are not a constant this could hardcode,
and nothing on the card looks like them. They still have to be read off the
air with ../watch_service_data.py. The card gets you the color and serial for
free; the tokens remain a one-off registration per card.
'''

# Firmware color code -> App color code, matching picolib's constants and
# lelib's read_sensor(). The wire and the App number the colors differently.
_FIRMWARE_TO_APP = {9: 1, 7: 2, 3: 3, 5: 4, 6: 5, 2: 6, 10: 7,
                    1: 8, 8: 9, 4: 10}

CARD_MAGIC = b'L3G0'
FIRST_DATA_PAGE = 4


class NotALegoCard(Exception):
    '''The tag read is genuinely not a LEGO connection card.'''


class CardReadFailed(Exception):
    '''The read did not complete -- says nothing about what the card is.

    Kept separate from NotALegoCard on purpose. A page read comes back empty
    every so often even on a card that reads fine on either side of it (seen
    live), usually because the card moved or was re-selected a moment before.
    Treating that as "not a LEGO card" tells the user their good card is bad;
    the right response is to read it again.
    '''


def decode_pages(data):
    '''(app_color, serial) from the 16 bytes read at page 4.

    Raises NotALegoCard if the magic marker is not there, which is what tells
    a LEGO card apart from any other NTAG that happens to be nearby, and
    CardReadFailed if the read simply did not deliver the bytes.
    '''
    if data is None or len(data) < 8:
        raise CardReadFailed('only {} bytes read'.format(
            0 if data is None else len(data)))
    if bytes(data[0:4]) != CARD_MAGIC:
        raise NotALegoCard('no {} marker (got {})'.format(
            CARD_MAGIC, ''.join('%02X' % b for b in data[0:4])))

    firmware_color = data[5]
    serial = (data[6] << 8) | data[7]
    if firmware_color not in _FIRMWARE_TO_APP:
        raise NotALegoCard('unknown color code {:#04x}'.format(firmware_color))
    return _FIRMWARE_TO_APP[firmware_color], serial


def open_reader(attempts=6, delay_ms=500):
    '''An RFID reader, retrying while the Grove 5V boost settles.

    The driver powers the rail itself, but on a cold start the first register
    write can go out before the boost has come up and time out.
    '''
    from time import sleep_ms
    from m5.m5_rfid import RFID

    last = None
    for attempt in range(attempts):
        try:
            return RFID()
        except OSError as e:
            last = e
            sleep_ms(delay_ms)
    raise OSError('RFID2 Unit did not answer on the Grove port after {} tries '
                  '({}). Check it is plugged in.'.format(attempts, last))


def read_card_data(rfid, attempts=3):
    '''(app_color, serial) for the selected card, retrying an empty read.

    Raises CardReadFailed only if every attempt came back short.
    '''
    from time import sleep_ms

    last = None
    for attempt in range(attempts):
        try:
            return decode_pages(rfid.read_pages(FIRST_DATA_PAGE))
        except CardReadFailed as e:
            last = e
            sleep_ms(60)
    raise last


def read_card(rfid, attempts=3):
    '''(uid_bytes, (app_color, serial)) for the card on the reader, or None.

    Returns None when no tag is present. Raises NotALegoCard for a tag that is
    there but is not a LEGO card, CardReadFailed if the read kept coming back
    empty.
    '''
    uid = rfid.read_uid()
    if uid is None:
        return None
    if rfid.sak != 0x00:
        raise NotALegoCard('SAK {:#04x}; LEGO cards are Ultralight/NTAG (0x00)'
                           .format(rfid.sak))
    return bytes(uid), read_card_data(rfid, attempts)
