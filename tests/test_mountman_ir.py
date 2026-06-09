"""Tests for the Mountman IR protocol tool.

These tests are intentionally small and readable. They protect the pieces of the
reverse-engineering work that would be easy to break by accident:

- checksum math
- LSB-first packet generation
- decoding real Flipper captures
- keeping the first hardware-test bundle populated
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from tools import mountman_ir as ir  # noqa: E402


class MountmanIrTests(unittest.TestCase):
    def test_checksum_example(self) -> None:
        """The checksum is the low byte of the sum of the first 13 bytes."""

        payload = [0x23, 0xCB, 0x26, 0x01, 0x00, 0x24, 0x03, 0x0D, 0x3D, 0x00, 0x00, 0x00, 0x84]
        self.assertEqual(ir.checksum(payload), 0x0A)

    def test_generate_known_packets(self) -> None:
        """Generated packets should match the current protocol notes exactly."""

        heat_72 = ir.build_mountman_packet(mode="heat", temp_f=72)
        cool_72_normal_b8_05 = ir.build_mountman_packet(mode="cool", temp_f=72, b8_override=0x05)
        cool_72_alt_high = ir.build_mountman_packet(mode="cool", temp_f=72, family="alternate", fan="high")

        self.assertEqual(ir.packet_to_hex(heat_72), "23 CB 26 01 00 24 01 09 05 00 00 00 80 C8")
        self.assertEqual(ir.packet_to_hex(cool_72_normal_b8_05), "23 CB 26 01 00 24 03 09 05 00 00 00 80 CA")
        self.assertEqual(ir.packet_to_hex(cool_72_alt_high), "23 CB 26 01 00 64 03 09 3D 00 00 00 80 42")

    def test_decode_updated_capture_has_expected_packets(self) -> None:
        """The decoder should recover known packets from the real capture file."""

        results = ir.decode_flipper_file(PROJECT_ROOT / "Remote2-updated.ir")
        by_name = {result.name: result for result in results if result.checksum_ok}

        self.assertEqual(ir.packet_to_hex(by_name["Power_on"].packet), "23 CB 26 01 00 24 03 0D 3D 00 00 00 84 0A")
        self.assertEqual(ir.packet_to_hex(by_name["Heat_72"].packet), "23 CB 26 01 00 24 01 09 05 00 00 00 80 C8")
        self.assertEqual(ir.packet_to_hex(by_name["Cool_64_new"].packet), "23 CB 26 01 00 24 03 0D 3D 00 00 00 80 06")

    def test_first_test_file_contains_all_entries(self) -> None:
        """The generated Flipper test bundle should include every planned test."""

        content = ir.first_test_flipper_file()
        for name, _packet in ir.FIRST_TEST_PACKETS:
            self.assertIn(f"name: {name}", content)


if __name__ == "__main__":
    unittest.main()
