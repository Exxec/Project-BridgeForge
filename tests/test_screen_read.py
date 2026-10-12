"""screen_read: BMP parsing and main-menu button detection on a synthetic menu."""
from __future__ import annotations

import struct
import unittest

from bridgeforge.screen_read import Bitmap, bands, main_menu_buttons, main_menu_target

TEAL = (40, 95, 120)
DARK = (5, 8, 12)


def _bmp(width: int, height: int, rows_y: list[tuple[int, int]]) -> bytes:
    row_bytes = (width * 3 + 3) & ~3
    pixels = bytearray()
    for y in reversed(range(height)):  # bottom-up
        line = bytearray()
        for x in range(width):
            inside = any(a <= y <= b for a, b in rows_y) and int(width * 0.62) <= x <= int(width * 0.76)
            r, g, b = TEAL if inside else DARK
            line += bytes((b, g, r))
        line += b"\x00" * (row_bytes - width * 3)
        pixels += line
    header = b"BM" + struct.pack("<IHHI", 54 + len(pixels), 0, 0, 54)
    info = struct.pack("<IiiHHIIiiII", 40, width, height, 1, 24, 0, len(pixels), 0, 0, 0, 0)
    return header + info + bytes(pixels)


class NexerelinSelectTests(unittest.TestCase):
    """Nexerelin's faction page shows four teal Select buttons at y 0.31-0.42 (EXPLORE-NEWGAME-20261011)."""

    def test_the_first_select_button_is_found_only_when_the_fleet_panel_is_up(self) -> None:
        from bridgeforge.screen_read import nexerelin_fleet_select

        h = 960
        rows = [(int(h * y), int(h * y) + 18) for y in (0.30, 0.335, 0.37, 0.405)]
        found = nexerelin_fleet_select(Bitmap(_bmp(400, h, rows)))
        self.assertIsNotNone(found)
        self.assertAlmostEqual(found[1], (rows[0][0] + rows[0][1]) / 2 / h, places=2)
        self.assertIsNone(nexerelin_fleet_select(Bitmap(_bmp(400, h, []))))


class ScreenReadTests(unittest.TestCase):
    def test_bands_bridge_small_gaps_and_drop_short_runs(self) -> None:
        flags = [False, True, True, False, True, True, False, False, False, True]
        self.assertEqual(bands(flags, 3, 1), [(1, 5)])

    def test_the_menu_is_read_from_the_bottom_with_or_without_continue(self) -> None:
        h = 400
        nine = [(110 + i * 25, 128 + i * 25) for i in range(9)]  # Continue + the eight fixed buttons
        buttons = main_menu_buttons(Bitmap(_bmp(300, h, nine)))
        self.assertEqual(len(buttons), 9)
        missions = main_menu_target(buttons, "Missions")
        self.assertAlmostEqual(missions[1], (nine[2][0] + nine[2][1]) / 2 / h, places=2)
        eight = nine[1:]
        buttons = main_menu_buttons(Bitmap(_bmp(300, h, eight)))
        self.assertAlmostEqual(main_menu_target(buttons, "New Game")[1], (eight[2][0] + eight[2][1]) / 2 / h, places=2)

    def test_too_few_buttons_gives_nothing(self) -> None:
        self.assertIsNone(main_menu_target([(0.7, 0.5)] * 3, "Missions"))


if __name__ == "__main__":
    unittest.main()
