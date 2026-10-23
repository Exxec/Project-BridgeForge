"""ROADMAP item 73 G1: the generic New Game fallback, on synthetic screenshots and fake hands (no game)."""
from __future__ import annotations

import struct
import unittest
from unittest import mock

from bridgeforge.live import live_run
from bridgeforge.new_game_generic import OPTION_ROWS, run_pages
from bridgeforge.screen_read import Bitmap, confirm_button, page_fingerprint, pages_differ
from tests.support import resolved_temp_dir

TEAL, DARK, GREY = (40, 95, 120), (5, 8, 12), (140, 140, 150)
W, H = 320, 240


def bmp(rects: list[tuple[float, float, float, float, tuple[int, int, int]]], base: tuple[int, int, int] = DARK) -> Bitmap:
    """A bottom-up 24-bit BMP with filled rectangles given as client fractions (x0, y0, x1, y1, colour)."""
    row_bytes = (W * 3 + 3) & ~3
    pixels = bytearray()
    for y in reversed(range(H)):
        line = bytearray()
        for x in range(W):
            r, g, b = base
            for x0, y0, x1, y1, colour in rects:
                if x0 * W <= x < x1 * W and y0 * H <= y < y1 * H:
                    r, g, b = colour
            line += bytes((b, g, r))
        pixels += line + b"\x00" * (row_bytes - W * 3)
    header = b"BM" + struct.pack("<IHHI", 54 + len(pixels), 0, 0, 54)
    info = struct.pack("<IiiHHIIiiII", 40, W, H, 1, 24, 0, len(pixels), 0, 0, 0, 0)
    return Bitmap(header + info + bytes(pixels))


CONFIRM_PAGE = bmp([(0.60, 0.80, 0.80, 0.86, TEAL)])
TEXT_PAGE = bmp([(0.25, 0.55, 0.45, 0.70, GREY)])
OTHER_PAGE = bmp([(0.10, 0.10, 0.60, 0.40, GREY)])


class ScreenTests(unittest.TestCase):
    def test_the_confirm_button_is_the_lowest_fill_in_the_lower_right_and_centred(self) -> None:
        page = bmp([(0.60, 0.60, 0.80, 0.66, TEAL), (0.60, 0.80, 0.80, 0.86, TEAL), (0.66, 0.30, 0.76, 0.36, TEAL)])
        x, y = confirm_button(page)
        self.assertAlmostEqual(x, 0.70, delta=0.02)
        self.assertAlmostEqual(y, 0.83, delta=0.02)

    def test_no_button_on_a_text_page_or_for_a_fill_only_in_the_upper_half(self) -> None:
        self.assertIsNone(confirm_button(TEXT_PAGE))
        self.assertIsNone(confirm_button(bmp([(0.66, 0.30, 0.76, 0.36, TEAL)])))

    def test_pages_differ_only_when_the_picture_changed(self) -> None:
        self.assertFalse(pages_differ(page_fingerprint(TEXT_PAGE), page_fingerprint(bmp([(0.25, 0.55, 0.45, 0.70, GREY)]))))
        self.assertTrue(pages_differ(page_fingerprint(TEXT_PAGE), page_fingerprint(OTHER_PAGE)))


class Script:
    """Serves the screens in order; a click moves to the next one unless `frozen`."""

    def __init__(self, screens: list[Bitmap], frozen: bool = False) -> None:
        self.screens, self.index, self.frozen = screens, 0, frozen
        self.clicks: list[tuple[float, float]] = []

    def capture(self) -> Bitmap:
        return self.screens[min(self.index, len(self.screens) - 1)]

    def click(self, fx: float, fy: float) -> None:
        self.clicks.append((fx, fy))
        if not self.frozen:
            self.index += 1


class RunPagesTests(unittest.TestCase):
    def _run(self, script: Script, done=lambda: False, **kwargs):
        return run_pages(script.click, lambda _s: None, script.capture, done, **kwargs)

    def test_a_confirm_button_is_clicked_then_the_first_option_row_of_a_text_page(self) -> None:
        script = Script([CONFIRM_PAGE, TEXT_PAGE, OTHER_PAGE])
        steps = self._run(script, done=lambda: script.index >= 3, max_pages=4)
        self.assertEqual([s.action for s in steps[:3]], ["confirm", "row", "row"])
        self.assertAlmostEqual(script.clicks[0][0], 0.70, delta=0.02)
        self.assertEqual(script.clicks[1], OPTION_ROWS[0])
        self.assertEqual(steps[-1].action, "done")

    def test_a_row_that_changes_nothing_moves_to_the_next_row_and_a_frozen_page_ends_the_loop(self) -> None:
        script = Script([TEXT_PAGE], frozen=True)
        steps = self._run(script, max_pages=12)
        self.assertEqual(steps[-1].action, "stuck")
        self.assertEqual(script.clicks[:3], list(OPTION_ROWS))
        self.assertLess(len(steps), 12)

    def test_a_confirm_button_that_does_nothing_falls_back_to_a_row(self) -> None:
        script = Script([CONFIRM_PAGE], frozen=True)
        steps = self._run(script, max_pages=4)
        self.assertEqual([s.action for s in steps[:4]], ["confirm", "row", "confirm", "row"])
        self.assertEqual(script.clicks[1], OPTION_ROWS[0])
        self.assertEqual(script.clicks[3], OPTION_ROWS[1])

    def test_an_unreadable_screen_ends_the_loop_without_clicking(self) -> None:
        steps = run_pages(lambda *_: self.fail("clicked"), lambda _s: None, lambda: None, lambda: False)
        self.assertEqual([s.action for s in steps], ["unreadable"])

    def test_done_before_the_first_page_clicks_nothing(self) -> None:
        script = Script([TEXT_PAGE])
        steps = self._run(script, done=lambda: True)
        self.assertEqual([s.action for s in steps], ["done"])
        self.assertEqual(script.clicks, [])

    def test_one_screenshot_per_page_is_kept(self) -> None:
        script = Script([CONFIRM_PAGE, TEXT_PAGE, OTHER_PAGE])
        with resolved_temp_dir() as base:
            steps = self._run(script, max_pages=3, shots_dir=base / "shots")
            shots = sorted(p.name for p in (base / "shots").iterdir())
            self.assertEqual(shots, ["page-01.bmp", "page-02.bmp", "page-03.bmp"])
            self.assertEqual(Bitmap.load(base / "shots" / "page-01.bmp").width, W)
            self.assertTrue(all(s.shot for s in steps))


class DriveFallbackTests(unittest.TestCase):
    """live_run.drive: a default flow that stops on a mod's own page is continued by the generic flow."""

    def _drive(self, reaches_campaign: bool):
        with resolved_temp_dir() as base:
            log = base / "run.stdout.log"
            log.write_text("1 [main] INFO  Reading save data from [x]\n", encoding="utf-8")
            script = Script([CONFIRM_PAGE, TEXT_PAGE], frozen=False)

            def click(fx: float, fy: float) -> None:
                script.click(fx, fy)
                if reaches_campaign and script.index >= 2:
                    with log.open("a", encoding="utf-8") as handle:
                        handle.write("BF-PROBE|0.2.23|probe|INFO|campaign|END\n")

            hands = live_run.Hands(click=click, key=lambda _vk: None, scroll=lambda *_a: None, sleep=lambda _s: None,
                                   geometry=lambda: (1, 0, 0, 1280, 960))
            with mock.patch.object(live_run, "_screen", lambda _h: script.capture()), \
                    mock.patch.object(live_run, "new_game", lambda *_a, **_k: None), \
                    mock.patch.object(live_run, "wait_for", self._fake_wait(log)):
                result = live_run.drive(log, hands, menu_timeout=0.2, campaign_timeout=0.4, combat_timeout=0.2, new_game_grace=0.1)
            return result, script, base

    @staticmethod
    def _fake_wait(log):
        def wait(_log, marker, _timeout, _hands, since=0, poll=1.0):
            return marker in log.read_text(encoding="utf-8")[since:]
        return wait

    def test_the_generic_flow_runs_after_the_fixed_flow_and_its_stage_is_recorded(self) -> None:
        result, script, _ = self._drive(reaches_campaign=True)
        self.assertIn("new-game-generic", " ".join(result.stages))
        self.assertIn(OPTION_ROWS[0], script.clicks)

    def test_a_generic_flow_that_does_not_help_still_ends_as_stuck_naming_the_attempt(self) -> None:
        result, _, _ = self._drive(reaches_campaign=False)
        self.assertEqual((result.verdict, result.stage), ("LIVE_STUCK", "new-game"))
        self.assertIn("generic New Game flow was tried", result.detail)

    def test_nexerelin_and_unreadable_screens_get_no_fallback(self) -> None:
        with resolved_temp_dir() as base:
            log = base / "run.stdout.log"
            log.write_text("1 [main] INFO  Reading save data from [x]\n", encoding="utf-8")
            hands = live_run.Hands(click=lambda *_: None, key=lambda _v: None, scroll=lambda *_: None, sleep=lambda _s: None)
            result = live_run.drive(log, hands, menu_timeout=0.2, campaign_timeout=0.4, new_game_grace=0.1)
        self.assertNotIn("generic", result.detail or "")


if __name__ == "__main__":
    unittest.main()
