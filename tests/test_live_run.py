"""probe-group live (ROADMAP 60f(2)): the sequence and its log-confirmed stages, with fake hands and a scripted log."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from bridgeforge.live import live_run
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
        if self.stall_at == "first-space" and vk == live_run.SPACE_KEY and self.combat_started:
            self.stall_at = None  # the first press landed before the mission took input; the next one starts it
            return
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
