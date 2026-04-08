"""Unit tests for _protocol.py — runs outside FL Studio (stdlib only)."""
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from _protocol import (
    encode_sysex, decode_sysex,
    TAG_CMD, TAG_RESP, MFR_ID,
)


class TestEncodeDecodeSysex(unittest.TestCase):

    def test_roundtrip_ascii_json(self):
        original = '{"id":"abc","action":"set_bpm","params":{"bpm":160}}'
        sysex = encode_sysex(TAG_CMD, original)
        tag, decoded = decode_sysex(sysex)
        self.assertEqual(tag, TAG_CMD)
        self.assertEqual(decoded, original)

    def test_roundtrip_unicode_track_name(self):
        original = '{"name":"Küche — Drums"}'
        sysex = encode_sysex(TAG_CMD, original)
        tag, decoded = decode_sysex(sysex)
        self.assertEqual(decoded, original)

    def test_header_structure(self):
        sysex = encode_sysex(TAG_CMD, "{}")
        self.assertEqual(sysex[0], 0xF0)
        self.assertEqual(sysex[1], MFR_ID)
        self.assertEqual(sysex[2], TAG_CMD)
        self.assertEqual(sysex[-1], 0xF7)

    def test_all_payload_bytes_midi_safe(self):
        # Every byte between F0 and F7 must be < 0x80
        sysex = encode_sysex(TAG_CMD, '{"name":"Küche — test é"}')
        data_bytes = sysex[1:-1]  # exclude F0, F7
        for i, b in enumerate(data_bytes):
            self.assertLess(b, 0x80, f"byte[{i+1}] = {b:#x} exceeds 0x7F")

    def test_tag_resp(self):
        sysex = encode_sysex(TAG_RESP, '{"success":true,"data":{}}')
        tag, decoded = decode_sysex(sysex)
        self.assertEqual(tag, TAG_RESP)

    def test_rejects_too_short(self):
        with self.assertRaises(ValueError):
            decode_sysex(bytes([0xF0, MFR_ID]))

    def test_rejects_wrong_mfr_id(self):
        with self.assertRaises(ValueError):
            decode_sysex(bytes([0xF0, 0x41, TAG_CMD, 0x00, 0xF7]))

    def test_rejects_missing_f7(self):
        with self.assertRaises(ValueError):
            decode_sysex(bytes([0xF0, MFR_ID, TAG_CMD, 0x00, 0x00]))

    def test_empty_payload_roundtrip(self):
        sysex = encode_sysex(TAG_CMD, "{}")
        tag, decoded = decode_sysex(sysex)
        self.assertEqual(decoded, "{}")


if __name__ == "__main__":
    unittest.main()
