# SPDX-License-Identifier: GPL-3.0-or-later
"""Offline tests for cykb.py. No keyboard and no vendor files needed."""
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import cykb  # noqa: E402


def make_image(size=0x1000, header=(0x04040000, 0x34000001, 0x00020004)):
    image = bytearray(b"\xff" * size)
    struct.pack_into("<II", image, 0, 0x20003FE0, 0x32C1)
    struct.pack_into("<3I", image, 0x9F8, *header)
    return bytes(image)


def make_version_page(magic=0x001C5AA5):
    page = bytearray(b"\xff" * 0xB4)
    words = (0x00100004, 0x00010005, 0xDB, 0xEFFFFFFF, 1, 0, 0x030104D9)
    struct.pack_into("<7I", page, 0x78, *words)
    struct.pack_into("<I", page, 0xB0, magic)
    return bytes(page)


class ImageChecks(unittest.TestCase):
    def test_valid_image(self):
        self.assertEqual(cykb.check_image(make_image()), make_image())

    def test_pads_to_word(self):
        self.assertEqual(len(cykb.check_image(make_image(0x1001))), 0x1004)

    def test_rejects_missing_header(self):
        with self.assertRaises(SystemExit):
            cykb.check_image(make_image(header=(0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF)))

    def test_rejects_short_image(self):
        with self.assertRaises(SystemExit):
            cykb.check_image(make_image()[:0x800])

    def test_rejects_wrong_base(self):
        image = bytearray(make_image())
        struct.pack_into("<I", image, 4, 0x1C1)
        with self.assertRaises(SystemExit):
            cykb.check_image(bytes(image))


class VersionPageChecks(unittest.TestCase):
    def test_valid_page_returns_app_pid(self):
        self.assertEqual(cykb.check_version_page(make_version_page()), 0x0301)

    def test_rejects_template(self):
        template = bytearray(make_version_page())
        template[0xAE:0xB4] = b"\x1c\xff\xa5\x5a\xff\x00"
        with self.assertRaises(SystemExit):
            cykb.check_version_page(bytes(template))

    def test_template_conversion(self):
        template = bytearray(make_version_page())
        template[0xAE:0xB4] = b"\x1c\xff\xa5\x5a\xff\x00"
        self.assertEqual(cykb.version_template_to_page(bytes(template)), make_version_page())

    def test_rejects_erased_word(self):
        page = bytearray(make_version_page())
        struct.pack_into("<I", page, 0x7C, 0xFFFFFFFF)
        with self.assertRaises(SystemExit):
            cykb.check_version_page(bytes(page))


class Encoding(unittest.TestCase):
    def test_xor_round_trip(self):
        data = bytes(range(256)) * 4
        self.assertEqual(cykb.xor_encode(cykb.xor_encode(data)), data)

    def test_xor_key_period(self):
        enc = cykb.xor_encode(b"\0" * 104)
        self.assertEqual(enc[:52], enc[52:])

    def test_checksum_is_word_sum(self):
        self.assertEqual(cykb.checksum(struct.pack("<2I", 0xFFFFFFFF, 2)), 1)


if __name__ == "__main__":
    unittest.main()
