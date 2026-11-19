"""93.58: a live run holds the display on, and gives the power plan its timeouts back afterwards."""
from __future__ import annotations

import unittest
from unittest import mock

import tests.support  # noqa: F401  installs the registry guard when this module runs alone (96.5 C4)
from bridgeforge.live import display_awake
from bridgeforge.live.display_awake import ES_CONTINUOUS, ES_DISPLAY_REQUIRED, ES_SYSTEM_REQUIRED, display_kept_on


class DisplayAwakeTests(unittest.TestCase):
    def test_the_display_is_held_inside_and_released_after_even_on_error(self) -> None:
        calls: list[int] = []
        with mock.patch.object(display_awake, "_set_state", side_effect=lambda flags: calls.append(flags) or True):
            with self.assertRaises(RuntimeError), display_kept_on() as held:
                self.assertTrue(held)
                raise RuntimeError("the run failed")
        self.assertEqual(calls, [ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED, ES_CONTINUOUS])

    def test_nothing_is_released_when_nothing_was_held(self) -> None:
        calls: list[int] = []
        with mock.patch.object(display_awake, "_set_state", side_effect=lambda flags: calls.append(flags) or False):
            with display_kept_on() as held:
                self.assertFalse(held)
        self.assertEqual(calls, [ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED])

    def test_live_run_holds_the_display_around_the_game(self) -> None:
        from bridgeforge.live import live_run

        events: list[str] = []

        class FakeGame:
            def __enter__(self):
                events.append("game")
                raise live_run.LaunchNoProcess("no game in this test")

            def __exit__(self, *exc):
                return False

        with mock.patch.object(display_awake, "_set_state", side_effect=lambda flags: events.append(hex(flags)) or True), \
                mock.patch.object(live_run, "running_game", return_value=FakeGame()):
            result = live_run.live_run(mock.MagicMock(), "T1")
        self.assertEqual(result.verdict, "LIVE_STUCK")
        self.assertEqual(events, [hex(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED), "game", hex(ES_CONTINUOUS)])

    @unittest.skipUnless(display_awake.sys.platform == "win32", "Windows only")
    def test_windows_accepts_the_request(self) -> None:
        with display_kept_on() as held:
            self.assertTrue(held)


if __name__ == "__main__":
    unittest.main()
