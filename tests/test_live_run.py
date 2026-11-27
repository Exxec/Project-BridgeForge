"""probe-group live (ROADMAP 60f(2)): the sequence and its log-confirmed stages, with fake hands and a scripted log."""
from __future__ import annotations

import json
import threading
import unittest
from pathlib import Path

from bridgeforge.live import live_run
from tests.support import resolved_temp_dir


class FakeGame:
    """Hands that record every action and append log lines when the run reaches the stage that would produce them. As in the real
    game, a battle logs its round and 'combat START' as it begins, and after its END the game defines the mission again, which
    logs the next round's line (`late_redefinition`: only at the next pause, as when the game takes its time). `lost_starts` names
    DEPLOY clicks (1-based) that start nothing, like the round-2 restarts of UAF and SR3-LIVE-0985a-20261117. `dies_at_deploy`
    ends the game at that DEPLOY click; after it, clicks, scrolls and front() raise as real_hands' geometry() does (a key press
    needs no window)."""

    def __init__(self, log: Path, rounds: int = 1, stall_at: str | None = None, lost_starts: tuple[int, ...] = (),
                 late_redefinition: bool = False, dies_at_deploy: int | None = None, dies_in_battle: bool = False,
                 saves_after_end: bool = False, menu_after_exits: int | None = None, lost_spaces: int = 0,
                 round_seconds: float = 0.0, window_gone_on: tuple[float, float] | None = None,
                 window_gone_at_deploy: int | None = None, extra_bands: int = 0) -> None:
        self.log, self.rounds, self.stall_at = log, rounds, stall_at
        self.extra_bands = extra_bands  # bands the menu reader sees below the nine buttons (98.11)
        # window_gone_on: a click on this point finds no window (SR7-LIVE-0985a-20261117's New Game click, 93.50);
        # window_gone_at_deploy: the Nth DEPLOY click does
        self.window_gone_on, self.window_gone_at_deploy = window_gone_on, window_gone_at_deploy
        # lost_spaces: that many SPACE presses in battle land before the mission takes input (SA-SR2-20261119 lost the press
        # after deploying and the first retry). round_seconds: the battle runs that long after the press that takes, then
        # logs END (93.62); 0 ends it at once.
        self.lost_spaces, self.round_seconds, self.timers = lost_spaces, round_seconds, []
        self.dies_at_deploy, self.dies_in_battle, self.alive = dies_at_deploy, dies_in_battle, True
        self.lost_starts, self.late_redefinition = set(lost_starts), late_redefinition
        self.actions: list[tuple] = []
        self.combat_started = self.deploys = 0
        self.running, self.pending_redefinition = False, None
        self.captures: list[Path] = []
        # saves_after_end: the probe saves after 'campaign END' and logs 'cmdSave returned' at the second pause after it (the New
        # Game flow's own pause after Start Game is shorter than the save); keys and clicks sent before that are lost to the save,
        # as in P962BS4 and P962YC2 (93.59). "never": the save never reports.
        self.saves_after_end, self.saving, self.save_pauses, self.lost_to_save = saves_after_end, False, 0, []
        # menu_after_exits (96.9): the fake has a readable screen, and the main menu shows after that many Exit-OK clicks (the
        # earlier ones are lost, as in a stall); a large number means it never shows.
        self.menu_after_exits, self.exit_oks, self.menu = menu_after_exits, 0, False
        self.log.write_text("1 [main] INFO  Reading save data from [x]\n", encoding="utf-8")

    def _append(self, text: str) -> None:
        with self.log.open("a", encoding="utf-8") as handle:
            handle.write(text + "\n")

    def _round_line(self, ahead: int = 0) -> str:
        number = (self.combat_started - 1 + ahead) % self.rounds + 1
        return f"BF-PROBE|0.3.3|combat-round|INFO|round {number} of {self.rounds}|hulls 1-2 of 2"

    def _window(self) -> None:
        if not self.alive:
            raise live_run.GameWindowGone("the game window is gone")

    def front(self) -> None:
        self._window()

    def scroll(self, *args) -> None:
        self._window()
        self.actions.append(("scroll", *args))

    def click(self, fx: float, fy: float) -> None:
        self._window()
        if (fx, fy) == self.window_gone_on or ((fx, fy) == live_run.DEPLOY and self.deploys + 1 == self.window_gone_at_deploy):
            raise live_run.GameWindowGone("the game window is gone")
        self.actions.append(("click", fx, fy))
        if self.saving:
            self.lost_to_save.append(("click", fx, fy))
        if self.menu_after_exits is not None:
            if (fx, fy) == live_run.GAME_MENU_EXIT_OK:
                self.exit_oks += 1
                self.menu = self.exit_oks >= self.menu_after_exits
            elif self.menu:
                self.menu = False  # Missions clicked: the menu gives way to the mission list
        if (fx, fy) == live_run.START_GAME and self.stall_at != "new-game":
            self._append("BF-PROBE|0.2.23|probe|INFO|campaign|END")
            self.saving, self.save_pauses = bool(self.saves_after_end), 2
        if (fx, fy) == live_run.DEPLOY:
            self.deploys += 1
            if self.deploys == self.dies_at_deploy:
                self.alive = False  # the java process exited while the battle loaded
                return
            if self.deploys in self.lost_starts:
                return  # the clicks landed nowhere: no mission, no battle
            self.combat_started += 1
            self.running = True
            self._append(self._round_line())
            self._append("BF-PROBE|0.3.3|probe|INFO|combat|START")

    def key(self, vk: int) -> None:
        self.actions.append(("key", vk))
        if self.saving:
            self.lost_to_save.append(("key", vk))
        if vk != live_run.SPACE_KEY or not self.running:
            return
        if self.dies_in_battle:
            self.alive = False  # the java process exited mid-battle
            return
        if self.stall_at == "first-space":
            self.stall_at = None  # the first press landed before the mission took input; the next one starts it
            return
        if self.lost_spaces:
            self.lost_spaces -= 1
            return
        if self.stall_at != "combat":
            self.running = False
            if self.round_seconds:
                timer = threading.Timer(self.round_seconds, self._end_round)
                timer.daemon = True
                self.timers.append(timer)
                timer.start()
            else:
                self._end_round()

    def _end_round(self) -> None:
        self._append("BF-PROBE|0.3.3|probe|INFO|combat|END")
        if self.late_redefinition:
            self.pending_redefinition = self._round_line(1)
        else:
            self._append(self._round_line(1))

    def sleep(self, _seconds: float) -> None:
        if self.saving and self.saves_after_end != "never":
            self.save_pauses -= 1
            if self.save_pauses == 0:
                self.saving = False
                self._append("BF-PROBE|0.3.3|save|INFO|campaign|cmdSave returned true")
        if self.pending_redefinition:
            self._append(self.pending_redefinition)
            self.actions.append(("logged", "redefinition"))
            self.pending_redefinition = None

    def capture(self, path: Path) -> bool:
        self.captures.append(path)
        return True

    def menu_buttons(self, _hands) -> list[tuple[float, float]]:
        """The main menu's nine buttons while it shows, none on any other screen (stands in for live_run._menu_buttons);
        `extra_bands` more below them, as RC9NC-LIVE3's reading had (98.11)."""
        count = 9 + self.extra_bands
        return [(0.72, 0.30 + 0.05 * i) for i in range(count)] if self.menu else []

    def hands(self) -> live_run.Hands:
        geometry = (lambda: (0, 0, 0, 1920, 1440)) if self.menu_after_exits is not None else None
        return live_run.Hands(click=self.click, key=self.key, scroll=self.scroll, sleep=self.sleep, capture=self.capture,
                              alive=lambda: self.alive, front=self.front, geometry=geometry)


class DriveTests(unittest.TestCase):
    def _drive(self, rounds: int = 1, stall_at: str | None = None, **fake):
        with resolved_temp_dir() as base:
            log = base / "run.stdout.log"
            game = FakeGame(log, rounds, stall_at, **fake)
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

    def test_a_battle_that_never_ends_leaves_a_screenshot(self) -> None:
        # SR4-LIVE-0985a-20261117: the battle started and nothing more was logged, not even a ship (93.40).
        result, game = self._drive(stall_at="combat")
        self.assertEqual((result.verdict, result.stage), ("LIVE_STUCK", "combat-round-1"))
        self.assertEqual([path.name for path in game.captures], ["run.round1-no-end.png"])
        self.assertIn("run.round1-no-end.png", result.detail)

    def test_a_game_that_exits_mid_battle_is_named_and_not_photographed(self) -> None:
        result, game = self._drive(dies_in_battle=True)
        self.assertEqual((result.verdict, result.stage), ("LIVE_STUCK", "combat-round-1"))
        self.assertIn("the game exited during", result.detail)
        self.assertEqual(game.captures, [])

    def test_silent_combat_is_stuck_at_its_round(self) -> None:
        result, _ = self._drive(stall_at="combat")
        self.assertEqual((result.verdict, result.stage), ("LIVE_STUCK", "combat-round-1"))
        self.assertIn("after the probe mission started", result.detail)

    def test_a_restart_that_starts_nothing_is_retried_once_after_a_screenshot(self) -> None:
        # UAF and SR3-LIVE-0985a-20261117: round 2's clicks back into the mission list started no battle (95.12(a)).
        result, game = self._drive(rounds=2, lost_starts=(2,))
        self.assertEqual((result.verdict, result.rounds), ("LIVE_DONE", 2), result)
        self.assertIn("combat-2-retry", result.stages)
        self.assertEqual([path.name for path in game.captures], ["run.round2-no-start.png"])
        clicks = [action[1:] for action in game.actions if action[0] == "click"]
        deploys = [index for index, click in enumerate(clicks) if click == live_run.DEPLOY]
        self.assertEqual(len(deploys), 3)
        # the retry clicks Continue first, in case the last battle's results are still up
        self.assertIn(live_run.COMBAT_CONTINUE, clicks[deploys[1]:deploys[2]])

    def test_a_mission_that_never_starts_is_stuck_at_its_round_naming_the_retry(self) -> None:
        result, game = self._drive(rounds=2, lost_starts=(2, 3))
        self.assertEqual((result.verdict, result.stage), ("LIVE_STUCK", "combat-round-2"))
        self.assertIn("also after one retry", result.detail)
        self.assertIn("run.round2-no-start.png", result.detail)
        self.assertEqual(game.combat_started, 1)

    def test_a_game_that_exits_while_a_round_loads_is_stuck_without_a_retry(self) -> None:
        # Review 2026-11-17: the retry clicked into a closed window (RuntimeError) where the old loop stopped cleanly.
        result, game = self._drive(rounds=2, dies_at_deploy=2)
        self.assertEqual((result.verdict, result.stage), ("LIVE_STUCK", "combat-round-2"))
        self.assertIn("the game exited", result.detail)
        self.assertEqual((game.deploys, game.captures), (2, []))

    def test_a_first_round_that_starts_nothing_is_retried_without_a_continue_click(self) -> None:
        result, game = self._drive(lost_starts=(1,))
        self.assertEqual((result.verdict, result.rounds), ("LIVE_DONE", 1), result)
        self.assertIn("combat-1-retry", result.stages)
        self.assertNotIn(("click", *live_run.COMBAT_CONTINUE), game.actions)

    def test_continue_waits_for_the_game_to_define_the_mission_again(self) -> None:
        # The game defines the mission again about 2 s after a battle ends; a Continue click before that can land in the transition.
        result, game = self._drive(rounds=2, late_redefinition=True)
        self.assertEqual((result.verdict, result.rounds), ("LIVE_DONE", 2), result)
        self.assertLess(game.actions.index(("logged", "redefinition")), game.actions.index(("click", *live_run.COMBAT_CONTINUE)))

    def test_combat_left_paused_by_the_first_space_is_unpaused_by_a_retry(self) -> None:
        # EXO-RC4B-LIVE-20261026: combat stopped logging after deployment; the owner had been unpausing by hand.
        retry = live_run.COMBAT_UNPAUSE_RETRY
        live_run.COMBAT_UNPAUSE_RETRY = 0.05
        try:
            with resolved_temp_dir() as base:
                log = base / "run.stdout.log"
                game = FakeGame(log, stall_at="first-space")
                result = live_run.drive(log, game.hands(), menu_timeout=0.2, campaign_timeout=0.2, combat_timeout=0.5)
        finally:
            live_run.COMBAT_UNPAUSE_RETRY = retry
        self.assertEqual(result.verdict, "LIVE_DONE", result)
        self.assertEqual(sum(1 for action in game.actions if action == ("key", live_run.SPACE_KEY)), 2)

    def _drive_slow_round(self, combat_timeout: float | None) -> tuple[live_run.LiveResult, FakeGame]:
        # SA-SR2-20261119 (93.62), scaled: the press after deploying and the first retry are lost, the second retry starts the
        # round and the round runs most of COMBAT_ROUND_SECONDS before its END. As in the game, a round is shorter than the retry
        # period (about 62 s against 90 s), so no retry lands in a running round and pauses it: three presses in all.
        saved = live_run.COMBAT_UNPAUSE_RETRY, live_run.COMBAT_ROUND_SECONDS
        live_run.COMBAT_UNPAUSE_RETRY, live_run.COMBAT_ROUND_SECONDS = 0.6, 0.55
        try:
            with resolved_temp_dir() as base:
                log = base / "run.stdout.log"
                game = FakeGame(log, lost_spaces=2, round_seconds=0.4)
                result = live_run.drive(log, game.hands(), menu_timeout=0.2, campaign_timeout=0.2, combat_timeout=combat_timeout)
                for timer in game.timers:
                    timer.join()
        finally:
            live_run.COMBAT_UNPAUSE_RETRY, live_run.COMBAT_ROUND_SECONDS = saved
        return result, game

    def test_the_default_combat_wait_holds_the_last_retry_and_a_whole_round(self) -> None:
        result, game = self._drive_slow_round(None)
        self.assertEqual(result.verdict, "LIVE_DONE", result)
        self.assertEqual(sum(1 for action in game.actions if action == ("key", live_run.SPACE_KEY)), 3)

    def test_a_wait_shorter_than_the_retries_and_a_round_gives_up_mid_round(self) -> None:
        # The flat 240 s of before, scaled: the round that the last retry started ends after the wait.
        result, _game = self._drive_slow_round(1.4)
        self.assertEqual(result.verdict, "LIVE_STUCK", result)
        self.assertEqual(result.stage, "combat-round-1")

    def test_the_real_combat_wait_covers_sa_sr2(self) -> None:
        # SA-SR2-20261119: the round began with the 180 s retry and its END came about 62 s later.
        self.assertEqual(live_run.combat_wait(), 255.0)
        self.assertGreater(live_run.combat_wait(), 2 * live_run.COMBAT_UNPAUSE_RETRY + 62)

    def test_a_probe_save_is_waited_for_before_leaving_the_campaign(self) -> None:
        # 93.59: P962BS4 (27.8 s save) and P962YC2 (20.3 s) lost the Escape and the Exit clicks to the probe's save.
        with resolved_temp_dir() as base:
            log = base / "run.stdout.log"
            game = FakeGame(log, saves_after_end=True)
            result = live_run.drive(log, game.hands(), menu_timeout=0.2, campaign_timeout=0.2, combat_timeout=0.2, probe_saves=True)
        self.assertEqual(result.verdict, "LIVE_DONE", result)
        self.assertEqual(result.stages, ["main-menu", "campaign", "probe-saved", "combat-1"])
        self.assertEqual(game.lost_to_save, [])

    def test_without_the_wait_the_escape_lands_during_the_save(self) -> None:
        # What the stalled runs did: the fake keeps playing, the real game ignored these.
        with resolved_temp_dir() as base:
            log = base / "run.stdout.log"
            game = FakeGame(log, saves_after_end=True)
            live_run.drive(log, game.hands(), menu_timeout=0.2, campaign_timeout=0.2, combat_timeout=0.2)
        self.assertIn(("key", live_run.ESCAPE_KEY), game.lost_to_save)

    def test_a_save_that_never_reports_is_stuck_at_probe_save(self) -> None:
        with resolved_temp_dir() as base:
            log = base / "run.stdout.log"
            game = FakeGame(log, saves_after_end="never")
            original = live_run.PROBE_SAVE_TIMEOUT
            live_run.PROBE_SAVE_TIMEOUT = 0.2
            try:
                result = live_run.drive(log, game.hands(), menu_timeout=0.2, campaign_timeout=0.2, combat_timeout=0.2, probe_saves=True)
            finally:
                live_run.PROBE_SAVE_TIMEOUT = original
        self.assertEqual((result.verdict, result.stage), ("LIVE_STUCK", "probe-save"))
        self.assertNotIn(("key", live_run.ESCAPE_KEY), game.actions)

    def test_probe_saves_after_checks_reads_the_rig_config(self) -> None:
        from bridgeforge.run_manifest import CONFIG_RELATIVE

        with resolved_temp_dir() as rig:
            self.assertFalse(live_run.probe_saves_after_checks(rig))  # no config
            config = rig / CONFIG_RELATIVE
            config.parent.mkdir(parents=True)
            for text, expected in (('{"save_after_checks": true}', True), ('{"save_after_checks": false}', False),
                                   ('{"save_after_checks": "true"}', False), ("not json", False), ("[]", False)):
                config.write_text(text, encoding="utf-8")
                self.assertIs(live_run.probe_saves_after_checks(rig), expected, text)

    def _drive_screen(self, menu_after_exits: int, extra_bands: int = 0):
        from unittest import mock

        with resolved_temp_dir() as base:
            log = base / "run.stdout.log"
            game = FakeGame(log, menu_after_exits=menu_after_exits, extra_bands=extra_bands)
            with mock.patch.object(live_run, "_menu_buttons", game.menu_buttons):
                result = live_run.drive(log, game.hands(), menu_timeout=0.2, campaign_timeout=0.2, combat_timeout=0.2,
                                        generic_fallback=False)
            actions_file = Path(f"{log}.actions.json")
            saved = json.loads(actions_file.read_text(encoding="utf-8")) if actions_file.is_file() else None
        return result, game, saved

    def test_a_lost_exit_is_seen_on_screen_and_sent_again(self) -> None:
        # 96.9: after 93.59's stalls the harness clicked Missions blind on the campaign map.
        result, game, _ = self._drive_screen(menu_after_exits=2)
        self.assertEqual(result.verdict, "LIVE_DONE", result)
        self.assertEqual(game.exit_oks, 2)
        self.assertEqual([p.name for p in game.captures], ["run.stdout.log.leave-campaign.png"])

    def test_a_menu_that_never_shows_is_stuck_at_leave_campaign_with_its_actions(self) -> None:
        result, game, saved = self._drive_screen(menu_after_exits=99)
        self.assertEqual((result.verdict, result.stage), ("LIVE_STUCK", "leave-campaign"))
        self.assertEqual(game.exit_oks, 2)  # one retry, then nothing more is clicked
        self.assertNotIn(("click", *live_run.PLAY_MISSION), game.actions)
        self.assertEqual(saved, result.actions)
        escapes = [a for a in result.actions if a["action"] == "key 0x1B"]
        self.assertEqual(len(escapes), 2)
        self.assertTrue(all(isinstance(a["log_bytes"], int) and a["log_bytes"] > 0 for a in escapes))

    def test_a_menu_that_reads_with_extra_bands_is_not_clicked_and_the_run_stops(self) -> None:
        # 98.11, RC9NC-LIVE3-0985a-20261126: two extra bands shifted "Missions" onto "Load Game"; the row, Play and Deploy clicks
        # then loaded a save. Now nothing is clicked on a menu that is not eight or nine buttons, and the run stops with a
        # screenshot and its actions.
        result, game, saved = self._drive_screen(menu_after_exits=1, extra_bands=2)
        self.assertEqual((result.verdict, result.stage), ("LIVE_STUCK", "leave-campaign"))
        self.assertIn("11 buttons", result.detail)
        self.assertIn("leave-campaign-menu.png", result.detail)
        self.assertEqual([p.name for p in game.captures], ["run.leave-campaign-menu.png"])
        menu = game.menu_buttons(None)
        self.assertTrue(menu)  # the menu is still up: nothing was clicked on it
        clicks = [a[1:] for a in game.actions if a[0] == "click"]
        self.assertFalse(set(clicks) & set(menu))
        self.assertNotIn(live_run.PLAY_MISSION, clicks)
        self.assertNotIn(live_run.DEPLOY, clicks)
        self.assertEqual(saved, result.actions)
        self.assertEqual(game.exit_oks, 1)  # a menu that is up but misread is not taken for a missing one: no second Exit

    def test_a_menu_on_the_first_exit_needs_no_retry(self) -> None:
        result, game, _ = self._drive_screen(menu_after_exits=1)
        self.assertEqual(result.verdict, "LIVE_DONE", result)
        self.assertEqual((game.exit_oks, game.captures), (1, []))

    def test_every_action_is_recorded_against_the_log(self) -> None:
        result, game = self._drive()
        self.assertEqual(len(result.actions), len(game.actions) - sum(1 for a in game.actions if a[0] == "logged"))
        sizes = [a["log_bytes"] for a in result.actions]
        self.assertEqual(sizes, sorted(sizes))  # the log only grows while the run acts

    def test_a_window_that_vanishes_at_new_game_is_stuck_there_with_the_logs_last_lines(self) -> None:
        # SR7-LIVE-0985a-20261117: New Game's click raised "the game window is gone" and the run gave no verdict (93.50).
        result, game = self._drive(window_gone_on=live_run.MAIN_MENU_NEW_GAME)
        self.assertEqual((result.verdict, result.stage), ("LIVE_STUCK", "new-game"))
        self.assertIn("the game window is gone", result.detail)
        self.assertIn("Reading save data from [x]", result.detail)  # the log's last line, quoted
        self.assertEqual(game.combat_started, 0)

    def test_a_window_that_vanishes_while_leaving_the_campaign_names_that_stage(self) -> None:
        result, _ = self._drive(window_gone_on=live_run.GAME_MENU_EXIT_OK)
        self.assertEqual((result.verdict, result.stage), ("LIVE_STUCK", "leave-campaign"))
        self.assertIn("campaign|END", result.detail)

    def test_a_window_that_vanishes_at_a_battles_deploy_names_its_round(self) -> None:
        result, _ = self._drive(rounds=2, window_gone_on=live_run.DEPLOY)
        self.assertEqual((result.verdict, result.stage), ("LIVE_STUCK", "combat-round-1"))
        self.assertIn("the game window is gone", result.detail)
        result, _ = self._drive(rounds=2, window_gone_at_deploy=2)  # review of #213: the round's number, not a fixed one
        self.assertEqual((result.verdict, result.stage), ("LIVE_STUCK", "combat-round-2"))

    def test_the_window_gone_detail_quotes_the_last_three_lines(self) -> None:
        from bridgeforge.live.window_gone import detail

        quoted = detail("one\ntwo\n\nthree\nfour\nfive\n")
        self.assertTrue(quoted.endswith("three | four | five"), quoted)
        self.assertNotIn("two", quoted)
        self.assertIn("(the log is empty)", detail("\n  \n"))

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


class MissionsBelowProbeTests(unittest.TestCase):
    """GRP1B-20261011: Neutrino's five missions sit below the probe's in the list, so a fixed click started one of them."""

    def _log(self, base: Path, rows: dict[str, int]) -> str:
        lines = ["1 [Thread-2] INFO  com.fs.starfarer.StarfarerLauncher  - Running with the following mods (in order of priority):"]
        order = ["BridgeForge Probe|bridgeforge_probe", "Other Mod|other", "Neutrino Corporation|Neutrino"]
        for entry in order:
            name, mod_id = entry.split("|")
            folder = base / mod_id
            (folder / "data" / "missions").mkdir(parents=True)
            body = "mission,\n" + "".join(f"m{i},\n" for i in range(rows.get(mod_id, 0))) + ",,\n"
            (folder / "data" / "missions" / "mission_list.csv").write_text(body, encoding="utf-8")
            lines.append(f"1 [Thread-2] INFO  com.fs.starfarer.StarfarerLauncher  -     {name} [id: {mod_id}] [version 1] (from {folder})")
        lines.append("1 [Thread-2] INFO  com.fs.starfarer.StarfarerLauncher  - Mod list finished")
        return "\n".join(lines) + "\n"

    def test_counts_only_the_missions_of_mods_listed_after_the_probe(self) -> None:
        with resolved_temp_dir() as base:
            text = self._log(base, {"bridgeforge_probe": 1, "other": 2, "Neutrino": 5})
            self.assertEqual(live_run.missions_below_probe(text), 7)

    def test_probe_alone_has_nothing_below_it(self) -> None:
        with resolved_temp_dir() as base:
            text = self._log(base, {"bridgeforge_probe": 1})
            self.assertEqual(live_run.missions_below_probe(text), 0)

    def test_a_log_without_a_mod_list_is_unknown(self) -> None:
        self.assertIsNone(live_run.missions_below_probe("nothing here\n"))

    def test_click_moves_up_one_row_per_mission_below(self) -> None:
        clicks = []
        hands = live_run.Hands(click=lambda fx, fy: clicks.append((fx, fy)), key=lambda v: None, scroll=lambda *a: None, sleep=lambda s: None)
        live_run.play_probe_combat(hands, rows_below=3)
        self.assertAlmostEqual(clicks[0][1], live_run.PROBE_MISSION[1] - 3 * live_run.MISSION_ROW_STEP)


class MissionListScrollTests(unittest.TestCase):
    """REG-20261012 group 10: 58 missions loaded; 40 wheel ticks stopped short of the probe's row."""

    def _scrolled(self, total: int | None) -> int:
        ticks = []
        hands = live_run.Hands(click=lambda fx, fy: None, key=lambda v: None, scroll=lambda fx, fy, n: ticks.append(n), sleep=lambda s: None)
        live_run.play_probe_combat(hands, 0, total)
        return ticks[0]

    def test_scrolls_at_least_forty_ticks_and_two_per_row_in_a_long_list(self) -> None:
        self.assertEqual(self._scrolled(None), -40)
        self.assertEqual(self._scrolled(17), -40)
        self.assertEqual(self._scrolled(48), -96)


class MissionListLayoutTests(unittest.TestCase):
    """GRP10Y2-20261011: Ironclads replaces the mission list (no vanilla missions) and the probe's mission is the last of its eight."""

    def _log(self, base: Path, mods: list[tuple[str, str, int, bool]]) -> str:
        lines = ["1 [Thread-2] INFO  com.fs.starfarer.StarfarerLauncher  - Running with the following mods (in order of priority):"]
        for name, mod_id, rows, replaces in mods:
            folder = base / mod_id
            (folder / "data" / "missions").mkdir(parents=True)
            (folder / "data" / "missions" / "mission_list.csv").write_text("mission,\n" + "".join(f"m{i},\n" for i in range(rows)), encoding="utf-8")
            info = {"id": mod_id, "replace": ["data/missions/mission_list.csv"] if replaces else []}
            (folder / "mod_info.json").write_text(json.dumps(info), encoding="utf-8")
            lines.append(f"1 [Thread-2] INFO  com.fs.starfarer.StarfarerLauncher  -     {name} [id: {mod_id}] [version 1] (from {folder})")
        lines.append("1 [Thread-2] INFO  com.fs.starfarer.StarfarerLauncher  - Mod list finished")
        return "\n".join(lines) + "\n"

    def test_a_replacing_mod_hides_vanilla_and_holds_the_probe_row_last(self) -> None:
        with resolved_temp_dir() as base:
            text = self._log(base, [("BridgeForge Probe", "bridgeforge_probe", 1, False), ("Ironclads", "ironclads", 8, True), ("SpeedUp", "speedUp", 0, False)])
            self.assertEqual(live_run.mission_list_layout(text, 14), (0, 8))

    def test_a_probe_row_listed_by_both_the_replacer_and_the_probe_mod_counts_once(self) -> None:
        """REG2-20261012: the probe is listed after Ironclads; both csv files carry the probe mission, the game shows it once."""
        with resolved_temp_dir() as base:
            text = self._log(base, [("Ironclads", "ironclads", 7, True), ("SpeedUp", "speedUp", 0, False), ("BridgeForge Probe", "bridgeforge_probe", 0, False)])
            for mod_id in ("ironclads", "bridgeforge_probe"):
                csv_path = base / mod_id / "data" / "missions" / "mission_list.csv"
                csv_path.write_text(csv_path.read_text(encoding="utf-8") + "bfprobe_combat,\n", encoding="utf-8")
            self.assertEqual(live_run.mission_list_layout(text, 14), (0, 8))

    def test_without_a_replacement_vanilla_rows_count_and_mods_after_the_probe_sit_below(self) -> None:
        with resolved_temp_dir() as base:
            text = self._log(base, [("BridgeForge Probe", "bridgeforge_probe", 1, False), ("Neutrino", "Neutrino", 5, False)])
            self.assertEqual(live_run.mission_list_layout(text, 14), (5, 20))

    def test_a_short_list_is_top_anchored_and_a_long_one_bottom_anchored(self) -> None:
        self.assertAlmostEqual(live_run.probe_mission_y(0, 8), live_run.FIRST_MISSION_ROW_Y + 7 * live_run.MISSION_ROW_STEP)
        self.assertAlmostEqual(live_run.probe_mission_y(0, 15), live_run.PROBE_MISSION[1])
        self.assertAlmostEqual(live_run.probe_mission_y(2, 15), live_run.PROBE_MISSION[1] - 2 * live_run.MISSION_ROW_STEP)

    def test_a_group_with_ironclads_gets_its_own_new_game_flow(self) -> None:
        with resolved_temp_dir() as base:
            text = self._log(base, [("BridgeForge Probe", "bridgeforge_probe", 1, False), ("Ironclads", "ironclads", 8, True)])
        self.assertEqual(live_run.new_game_flow_for(text), "ironclads")
        self.assertEqual(live_run.new_game_flow_for("nothing\n"), "default")

    def test_nexerelin_new_game_uses_number_keys_the_fleet_select_and_g(self) -> None:
        """Nexerelin's own New Game dialog (EXPLORE-NEWGAME-20261011): option keys, then the fleet's Select button, then G."""
        with resolved_temp_dir() as base:
            text = self._log(base, [("BridgeForge Probe", "bridgeforge_probe", 1, False), ("Nexerelin", "nexerelin", 4, False)])
        self.assertEqual(live_run.new_game_flow_for(text), "nexerelin")
        actions: list[tuple] = []
        hands = live_run.Hands(click=lambda fx, fy: actions.append(("click", fx, fy)), key=lambda vk: actions.append(("key", vk)),
                               scroll=lambda *a: None, sleep=lambda _s: None)
        live_run.new_game(hands, "nexerelin")
        keys = [a[1] for a in actions if a[0] == "key"]
        self.assertEqual(keys, [live_run.KEY_1] * 8 + [live_run.KEY_G])
        self.assertIn(("click", *live_run.NEX_FLEET_SELECT), actions)
        self.assertLess(actions.index(("click", *live_run.NEX_FLEET_SELECT)), len(actions) - 3)


class FreshRigMenuTests(unittest.TestCase):
    def test_menu_playback_without_save_descriptors_drives_full_sequence(self):
        with resolved_temp_dir() as root:
            log = root / 'fresh.log'; game = FakeGame(log)
            log.write_text('9287 [Thread-8] INFO sound.H - Playing music with id [miscallenous_main_menu.ogg]\n')
            result = live_run.drive(log, game.hands(), menu_timeout=0.01, campaign_timeout=0.01, combat_timeout=0.01)
            self.assertEqual(result.verdict, 'LIVE_DONE', result)
            self.assertEqual(result.stages, ['main-menu', 'campaign', 'combat-1'])

    def test_preload_or_other_music_does_not_trigger_menu_clicks(self):
        with resolved_temp_dir() as root:
            log = root / 'not-ready.log'
            for text in ('Creating streaming player for music with id [miscallenous_main_menu.ogg]',
                         'Playing music with id [battle.ogg]'):
                with self.subTest(text=text):
                    game = FakeGame(log); log.write_text(text)
                    result = live_run.drive(log, game.hands(), menu_timeout=0.01)
                    self.assertEqual(result.verdict, 'LIVE_STUCK')
                    self.assertEqual(result.stage, 'main-menu')
                    self.assertEqual(game.actions, [])
