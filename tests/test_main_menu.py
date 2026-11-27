"""98.11: reading and clicking the main menu (bridgeforge/live/main_menu.py), against scripted screen readings."""
from __future__ import annotations

import unittest
from unittest import mock

import tests.support  # noqa: F401  (installs the registry guard when this module runs alone)
from bridgeforge.live import live_run, main_menu

FALLBACK = (0.5, 0.5)


def _bands(count: int) -> list[tuple[float, float]]:
    return [(0.72, 0.30 + 0.05 * i) for i in range(count)]


class _Screen:
    """Hands whose screen reads as the given band counts, one per read (the last repeats); clicks are recorded."""

    def __init__(self, counts: list[int | None]):
        self.counts, self.clicks = list(counts), []

    def read(self, _hands):
        count = self.counts.pop(0) if len(self.counts) > 1 else self.counts[0]
        return None if count is None else _bands(count)

    def hands(self) -> live_run.Hands:
        return live_run.Hands(click=lambda fx, fy: self.clicks.append((fx, fy)), key=lambda v: None, scroll=lambda *a: None,
                              sleep=lambda s: None, front=lambda: None, geometry=lambda: (0, 0, 0, 1920, 1440))


def _with(screen: _Screen):
    return mock.patch.object(main_menu, "_menu_buttons", screen.read)


class MenuPointTests(unittest.TestCase):
    def test_a_reading_that_is_not_a_menu_yet_is_read_again_not_refused(self) -> None:
        # Review of 98.11: a steady reading of a few bands (a menu sliding in, another screen) is not a misread menu.
        screen = _Screen([5, 5, 9, 9])
        with _with(screen):
            self.assertEqual(main_menu.menu_point(screen.hands(), "Missions", FALLBACK), _bands(9)[2])
        never = _Screen([3])
        with _with(never):
            self.assertEqual(main_menu.menu_point(never.hands(), "Missions", FALLBACK), FALLBACK)  # the old fallback stands

    def test_a_steady_menu_with_too_many_bands_is_refused(self) -> None:
        screen = _Screen([11])
        with _with(screen), self.assertRaisesRegex(main_menu.MenuMisread, "read as 11 buttons, not 8 or 9"):
            main_menu.menu_point(screen.hands(), "Missions", FALLBACK)

    def test_an_unreadable_screen_clicks_the_measured_point(self) -> None:
        screen = _Screen([None])
        with _with(screen):
            self.assertEqual(main_menu.menu_point(screen.hands(), "Missions", FALLBACK), FALLBACK)


class ClickMenuTests(unittest.TestCase):
    def test_a_menu_still_up_after_the_click_is_not_taken_for_gone(self) -> None:
        # Review of 98.11: after a good click the menu still read as ten bands; it is not gone, so the next attempt reads it
        # again, and a misread menu is refused instead of a Play click landing on it.
        screen = _Screen([9, 9, 10, 10, 10])
        with _with(screen), self.assertRaises(main_menu.MenuMisread):
            main_menu.click_menu(screen.hands(), "Missions", FALLBACK)
        self.assertEqual(screen.clicks, [_bands(9)[2]])

    def test_a_menu_that_gives_way_is_gone_after_one_click(self) -> None:
        screen = _Screen([9, 9, 0])
        with _with(screen):
            self.assertTrue(main_menu.click_menu(screen.hands(), "New Game", FALLBACK))
        self.assertEqual(screen.clicks, [_bands(9)[3]])


class MenuShownTests(unittest.TestCase):
    def test_eight_bands_or_more_are_a_menu_and_fewer_are_not(self) -> None:
        for count, shown in ((8, True), (9, True), (11, True), (7, False)):
            screen = _Screen([count])
            with self.subTest(count=count), _with(screen):
                self.assertIs(main_menu._main_menu_shown(screen.hands()), shown)


if __name__ == "__main__":
    unittest.main()
