"""probe-group duel: the log parser and summary, and the mod install (the clicks are proven live, not here)."""
from __future__ import annotations

import json
import unittest

from bridgeforge import duel_run
from bridgeforge.live.live_run import GameRefused
from tests.support import resolved_temp_dir

LOG = "\n".join([
    "1 [Thread-9] INFO  data.scripts.bfduel.BfDuelPlugin  - BF-DUEL|seeker|START|label=seeker",
    "2 [Thread-9] INFO  x - BF-DUEL|seeker|SECOND|t=1.0 frames=60 avgMs=16.7 maxMs=20.0 alive=1/1 hulks=0 ships=2 projectiles=5 missiles=0 beams=0 asteroids=0",
    "3 [Thread-9] INFO  x - BF-DUEL|seeker|FIGHT|gameSeconds=2.5 realSeconds=3.1 destroyed=ART_shockwave owner=0 ships=3 projectiles=40",
    "4 [Thread-9] INFO  x - BF-DUEL|seeker|SECOND|t=3.0 frames=20 avgMs=50.0 maxMs=120.5 alive=0/1 hulks=7 ships=9 projectiles=60 missiles=0 beams=0 asteroids=0",
    "5 [Thread-9] INFO  x - BF-DUEL|seeker|DESTRUCTION-COST|t=6.5 worstFrameMs=120.5 in the 4 s after the last destruction",
    "6 [Thread-9] INFO  x - BF-DUEL|seeker|END|t=15.0 frames=900 avgMs=20.1 worstMs=120.5 reason=side-gone",
    "7 [Thread-9] INFO  x - BF-DUEL|baseline|SECOND|t=1.0 frames=60 avgMs=16.7 maxMs=17.0 alive=1/1 hulks=0 ships=2 projectiles=5 missiles=0 beams=0 asteroids=0",
    "other line",
])


class ParseTests(unittest.TestCase):
    def test_summary_splits_frame_time_at_the_first_destruction(self) -> None:
        summary = duel_run.summarise(duel_run.parse_duel_log(LOG))
        seeker = summary["seeker"]
        self.assertEqual((seeker["avg_ms_before"], seeker["avg_ms_after"]), (16.7, 50.0))
        self.assertEqual((seeker["worst_frame_ms"], seeker["worst_after_destruction_ms"], seeker["peak_hulks"]), (120.5, 120.5, 7))
        self.assertEqual((seeker["fight_game_seconds"], seeker["fight_real_seconds"]), (2.5, 3.1))
        self.assertTrue(seeker["finished"])
        self.assertFalse(summary["baseline"]["finished"])
        self.assertIsNone(summary["baseline"]["first_destruction_t"])


class InstallTests(unittest.TestCase):
    def test_installs_the_mod_and_enables_it_beside_the_others(self) -> None:
        with resolved_temp_dir() as base:
            rig = base / "rig"
            (rig / "starsector-core").mkdir(parents=True)
            (rig / "mods").mkdir()
            (rig / "mods" / "enabled_mods.json").write_text(json.dumps({"enabledMods": ["SEEKER"]}), encoding="utf-8")
            target = duel_run.install_duel_mod(rig)
            enabled = json.loads((rig / "mods" / "enabled_mods.json").read_text(encoding="utf-8"))["enabledMods"]
            self.assertTrue((target / "mod_info.json").is_file())
            self.assertTrue((target / "data" / "scripts" / "bfduel" / "BfDuelPlugin.java").is_file())
        self.assertEqual(enabled, ["SEEKER", "bf_duel"])

    def test_a_folder_that_is_not_a_rig_is_refused(self) -> None:
        with resolved_temp_dir() as base:
            with self.assertRaises(GameRefused):
                duel_run.install_duel_mod(base / "nope")

    def test_a_misread_main_menu_plays_no_duel(self) -> None:
        # 98.11: the Missions click is refused on a menu that reads as eleven buttons; no duel is played and the run says why.
        import contextlib
        from unittest import mock

        from bridgeforge.live import live_run

        with resolved_temp_dir() as base:
            log = base / "duel.stdout.log"
            log.write_text("1 [main] INFO  Reading save data from [x]\n", encoding="utf-8")
            clicks: list[tuple] = []
            hands = live_run.Hands(click=lambda fx, fy: clicks.append((fx, fy)), key=lambda v: None, scroll=lambda *a: None,
                                   sleep=lambda s: None, front=lambda: None, geometry=lambda: (0, 0, 0, 1920, 1440))

            @contextlib.contextmanager
            def game(*_args, **_kwargs):
                yield log, hands, 14

            menu = [(0.72, 0.30 + 0.05 * i) for i in range(11)]
            with mock.patch.object(duel_run, "install_duel_mod"), mock.patch.object(live_run, "running_game", game), \
                    mock.patch.object(live_run, "_menu_buttons", lambda _hands: menu):
                result = duel_run.run_duel(base, "DUEL-T")
        self.assertEqual((result["played"], clicks), ([], []))
        self.assertIn("main-menu: the main menu read as 11 buttons", result["problem"])


if __name__ == "__main__":
    unittest.main()
