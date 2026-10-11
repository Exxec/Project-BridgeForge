"""probe-group live (ROADMAP 60f(2)): the sequence and its log-confirmed stages, with fake hands and a scripted log."""
from __future__ import annotations

import unittest
from pathlib import Path

from bridgeforge import live_run
from tests.support import resolved_temp_dir


class FakeGame:
    """Hands that record every action and append log lines when the run reaches the stage that would produce them."""

    def __init__(self, log: Path, rounds: int = 1, stall_at: str | None = None) -> None:
        self.log, self.rounds, self.stall_at = log, rounds, stall_at
        self.actions: list[tuple] = []
        self.combat_started = 0
        self.log.write_text("1 [main] INFO  Reading save data from [x]\n", encoding="utf-8")

    def _append(self, text: str) -> None:
        with self.log.open("a", encoding="utf-8") as handle:
            handle.write(text + "\n")

    def click(self, fx: float, fy: float) -> None:
        self.actions.append(("click", fx, fy))
        if (fx, fy) == live_run.START_GAME and self.stall_at != "new-game":
            self._append("BF-PROBE|0.2.23|probe|INFO|campaign|END")
        if (fx, fy) == live_run.DEPLOY:
            self.combat_started += 1

    def key(self, vk: int) -> None:
        self.actions.append(("key", vk))
        if vk == live_run.SPACE_KEY and self.combat_started and self.stall_at != "combat":
            self._append(f"BF-PROBE|0.2.23|combat-round|INFO|round {self.combat_started} of {self.rounds}|x")
            self._append("BF-PROBE|0.2.23|probe|INFO|combat|END")

    def hands(self) -> live_run.Hands:
        return live_run.Hands(click=self.click, key=self.key, scroll=lambda *a: self.actions.append(("scroll", *a)),
                              sleep=lambda _s: None)


class DriveTests(unittest.TestCase):
    def _drive(self, rounds: int = 1, stall_at: str | None = None):
        with resolved_temp_dir() as base:
            log = base / "run.stdout.log"
            game = FakeGame(log, rounds, stall_at)
            result = live_run.drive(log, game.hands(), menu_timeout=0.2, campaign_timeout=0.2, combat_timeout=0.2)
        return result, game

    def test_full_run_clicks_new_game_then_plays_the_probe_mission(self) -> None:
        result, game = self._drive()
        self.assertEqual(result.verdict, "LIVE_DONE", result)
        self.assertEqual(result.stages, ["main-menu", "campaign", "combat-1"])
        clicks = [a[1:] for a in game.actions if a[0] == "click"]
        self.assertEqual(clicks[0], live_run.MAIN_MENU_NEW_GAME)
        self.assertIn(live_run.START_GAME, clicks)
        self.assertLess(clicks.index(live_run.START_GAME), clicks.index(live_run.PROBE_MISSION))

    def test_every_round_of_the_combat_plan_is_played(self) -> None:
        result, game = self._drive(rounds=3)
        self.assertEqual(result.verdict, "LIVE_DONE", result)
        self.assertEqual(result.rounds, 3)
        self.assertEqual(game.combat_started, 3)

    def test_silent_new_game_is_stuck_there_and_never_reaches_combat(self) -> None:
        result, game = self._drive(stall_at="new-game")
        self.assertEqual((result.verdict, result.stage), ("LIVE_STUCK", "new-game"))
        self.assertEqual(game.combat_started, 0)

    def test_silent_combat_is_stuck_at_its_round(self) -> None:
        result, _ = self._drive(stall_at="combat")
        self.assertEqual((result.verdict, result.stage), ("LIVE_STUCK", "combat-round-1"))

    def test_game_that_never_reaches_the_menu_is_stuck_at_the_menu(self) -> None:
        with resolved_temp_dir() as base:
            log = base / "run.stdout.log"
            log.write_text("nothing useful\n", encoding="utf-8")
            hands = live_run.Hands(click=lambda *a: None, key=lambda v: None, scroll=lambda *a: None, sleep=lambda s: None, alive=lambda: False)
            result = live_run.drive(log, hands, menu_timeout=0.2)
        self.assertEqual((result.verdict, result.stage), ("LIVE_STUCK", "main-menu"))


class RefusalTests(unittest.TestCase):
    def test_refuses_a_rig_whose_core_is_not_linked(self) -> None:
        with resolved_temp_dir() as base:
            (base / "rig" / "starsector-core").mkdir(parents=True)
            result = live_run.live_run(base / "rig", "T1")
        self.assertEqual((result.verdict, result.stage), ("LIVE_STUCK", "refused"))


if __name__ == "__main__":
    unittest.main()
