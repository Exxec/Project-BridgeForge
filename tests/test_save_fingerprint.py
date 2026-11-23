"""Probe 0.2.28 save-reload fingerprint: the log parser, the run-manifest milestone, the live/reload drivers (synthetic logs, no game)."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from bridgeforge.live import live_run
from bridgeforge.save import save_reload_run
from bridgeforge.save.save_fingerprint import SECTIONS, parse_fingerprint
from bridgeforge.run_manifest import evaluate_run, read_manifest
from tests.bound_runs import LOAD, MENU, bound_run
from tests.support import resolved_temp_dir
from tests.test_run_manifest import _two

P = "BF-PROBE|0.2.27|fingerprint|"
COMPARE = save_reload_run.COMPARE_MARKER


def phase(name: str, digests: dict[str, str], source: str = "") -> list[str]:
    return [f"{P}INFO|phase={name}|section={s};count=3;len=40;fnv={digests[s]}{source}" for s in SECTIONS]


SAME = {s: format(i, "x") * 16 for i, s in enumerate(SECTIONS, 1)}
SAVE_LINE = P + "INFO|save|cmdSave returned true;ts=123;slot_note=zorg"


def compare(equal: bool, diff: str = "") -> str:
    return f"{P}{'INFO' if equal else 'FAIL'}|compare|equal={str(equal).lower()};diff={diff};sections=8;slot_note=zorg"


def reload_log(after: dict[str, str], logged_equal: bool, diff: str = "") -> list[str]:
    return [*phase("before", SAME, ";source=file"), *phase("after", after), compare(logged_equal, diff)]


class ParseTests(unittest.TestCase):
    def test_no_fingerprint_lines_means_no_block(self) -> None:
        self.assertIsNone(parse_fingerprint("BF-PROBE|0.2.27|probe|INFO|campaign|END"))

    def test_first_launch_has_before_and_save_but_no_compare(self) -> None:
        block = parse_fingerprint("\n".join([*phase("before", SAME), SAVE_LINE]))
        self.assertFalse(block["compare_observed"])
        self.assertFalse(block["equal"])
        self.assertTrue(block["save_returned_true"])

    def test_equal_reload_is_equal_with_no_diff(self) -> None:
        block = parse_fingerprint("\n".join(reload_log(SAME, True)))
        self.assertEqual((block["compare_observed"], block["equal"], block["diff_sections"]), (True, True, []))

    def test_differing_reload_names_the_sections(self) -> None:
        after = {**SAME, "markets": "f" * 16}
        block = parse_fingerprint("\n".join(reload_log(after, False, "markets")))
        self.assertEqual((block["compare_observed"], block["equal"], block["diff_sections"]), (True, False, ["markets"]))

    def test_probe_saying_equal_is_not_taken_on_its_word(self) -> None:
        after = {**SAME, "cargo": "e" * 16}
        block = parse_fingerprint("\n".join(reload_log(after, True)))
        self.assertTrue(block["compare_observed"])
        self.assertFalse(block["equal"])
        self.assertEqual(block["diff_sections"], ["cargo"])

    def test_a_missing_section_is_a_difference(self) -> None:
        lines = [line for line in reload_log(SAME, True) if "section=rings" not in line]
        block = parse_fingerprint("\n".join(lines))
        self.assertFalse(block["equal"])
        self.assertEqual(block["diff_sections"], ["rings"])


class MilestoneTests(unittest.TestCase):
    def _evidence(self, lines: list[str], expected=("main_menu", "campaign_load", "reload_after_save")) -> dict:
        with resolved_temp_dir() as root:
            _, targets = _two(root)
            rig, log = bound_run(root, targets, "R-F", [MENU, LOAD, *lines], expected=expected, kind="live", providers={"lib": []})
            return evaluate_run(rig, read_manifest(rig, "R-F"), log)

    def test_reload_after_save_is_true_only_when_the_compare_line_was_observed(self) -> None:
        seen = self._evidence(reload_log(SAME, True))
        self.assertTrue(seen["milestones"]["reload_after_save"])
        self.assertTrue(seen["fingerprint"]["equal"])
        first = self._evidence([*phase("before", SAME), SAVE_LINE], expected=("main_menu", "campaign_load"))
        self.assertFalse(first["milestones"]["reload_after_save"])
        self.assertIsNone(self._evidence([], expected=("main_menu", "campaign_load"))["fingerprint"])

    def test_expecting_the_milestone_without_a_compare_line_is_refused(self) -> None:
        evidence = self._evidence([*phase("before", SAME), SAVE_LINE])
        self.assertEqual(evidence["status"], "REFUSED")
        self.assertIn("reload_after_save not observed", " ".join(evidence["problems"]))

    def test_a_differing_reload_still_reports_the_block_for_the_record(self) -> None:
        evidence = self._evidence(reload_log({**SAME, "fleets": "9" * 16}, False, "fleets"))
        self.assertTrue(evidence["milestones"]["reload_after_save"])
        self.assertEqual((evidence["fingerprint"]["equal"], evidence["fingerprint"]["diff_sections"]), (False, ["fleets"]))


class DriveTests(unittest.TestCase):
    def test_live_drive_with_save_reload_waits_for_the_fingerprint_save(self) -> None:
        from tests.test_live_run import FakeGame

        for logged, expect in ((True, "LIVE_DONE"), (False, "LIVE_STUCK")):
            with resolved_temp_dir() as base:
                log = base / "run.stdout.log"
                game = FakeGame(log)
                click = game.click

                def click_and_save(fx, fy, click=click, log=log, logged=logged):
                    click(fx, fy)
                    if (fx, fy) == live_run.START_GAME and logged:
                        game._append("BF-PROBE|0.2.27|fingerprint|INFO|save|cmdSave returned true;ts=5;slot_note=")

                game.click = click_and_save
                result = live_run.drive(log, game.hands(), menu_timeout=0.2, campaign_timeout=0.2, combat_timeout=0.2, save_reload=True)
            self.assertEqual(result.verdict, expect, result)
            if logged:
                self.assertEqual(result.stages[:3], ["main-menu", "campaign", "fingerprint-saved"])
            else:
                self.assertEqual(result.stage, "fingerprint-save")

    def _reload(self, after_click: list[str], alive=lambda: True, dialog: str | None = None, after_compare: list[str] = ()):
        """drive_reload on a log that gets `after_click` once Continue is clicked; `after_compare` lines and a windows.txt
        `dialog` appear during the settle period."""
        with resolved_temp_dir() as base:
            log = base / "run.stdout.log"
            log.write_text("1 [main] INFO  Reading save data from [x]\n", encoding="utf-8")
            clicks: list[tuple] = []
            sleeps = [0]

            def click(fx, fy):
                clicks.append((fx, fy))
                with log.open("a", encoding="utf-8") as handle:
                    handle.write("\n".join(after_click) + "\n")

            def sleep(_seconds):
                if COMPARE in log.read_text(encoding="utf-8"):
                    sleeps[0] += 1
                    if sleeps[0] == 2:  # one second into the settle period
                        with log.open("a", encoding="utf-8") as handle:
                            handle.write("".join(line + "\n" for line in after_compare))
                        if dialog:
                            (base / "run.windows.txt").write_text(f"20:10:38 dialog: 'Error' text: '{dialog}'\n", encoding="utf-8")

            hands = live_run.Hands(click=click, key=lambda v: None, scroll=lambda *a: None, sleep=sleep, alive=alive)
            result = save_reload_run.drive_reload(log, hands, menu_timeout=0.2, compare_timeout=0.2, load_timeout=0.2,
                                                  settle_seconds=3)
        return result, clicks

    def test_reload_drive_continues_then_waits_for_the_load_and_compare_lines(self) -> None:
        result, clicks = self._reload([LOAD, *reload_log(SAME, True)])
        self.assertEqual(result.verdict, "LIVE_DONE", result)
        self.assertEqual(result.stages, ["main-menu", "continue", "fingerprint-compare", "settled"])
        self.assertEqual(clicks[0], save_reload_run.MAIN_MENU_CONTINUE)
        result, _ = self._reload([LOAD])
        self.assertEqual((result.verdict, result.stage), ("LIVE_STUCK", "fingerprint-compare"))

    def test_continue_that_loads_no_save_is_stuck_at_continue(self) -> None:
        # 88.22: ICBF2C-J28's Continue started a New Game; the log showed a new sector, not a load.
        result, _ = self._reload(["200 [main] INFO  com.fs.starfarer.campaign.CampaignEngine  - Generating sector"])
        self.assertEqual((result.verdict, result.stage), ("LIVE_STUCK", "continue"))
        self.assertIn("Continue loaded no save", result.detail)

    def test_a_dialog_after_the_compare_line_fails_the_reload(self) -> None:
        # 88.19: ICBF2-J28FR's Fatal came 243 ms after the compare line and the run was called LIVE_DONE.
        result, _ = self._reload([LOAD, *reload_log(SAME, True)], dialog="Fatal: java.lang.NullPointerException")
        self.assertEqual((result.verdict, result.stage), ("LIVE_STUCK", "after-compare"))
        self.assertIn("Fatal: java.lang.NullPointerException", result.detail)

    def test_a_fatal_log_line_after_the_compare_line_fails_the_reload(self) -> None:
        result, _ = self._reload([LOAD, *reload_log(SAME, True)], after_compare=["300 [main] FATAL x  - it broke"])
        self.assertEqual((result.verdict, result.stage), ("LIVE_STUCK", "after-compare"))

    def test_a_game_that_dies_after_the_compare_line_fails_the_reload(self) -> None:
        calls = [0]

        def dies():  # the load and compare lines are already there, so only the settle period asks
            calls[0] += 1
            return calls[0] < 3  # gone two seconds into the settle period

        result, _ = self._reload([LOAD, *reload_log(SAME, True)], alive=dies)
        self.assertEqual((result.verdict, result.stage), ("LIVE_STUCK", "after-compare"))
        self.assertIn("exited", result.detail)

    def test_a_vanished_window_at_continue_is_stuck_there(self) -> None:
        with resolved_temp_dir() as base:
            log = base / "run.stdout.log"
            log.write_text("1 [main] INFO  Reading save data from [x]\n", encoding="utf-8")

            def click(fx, fy):
                raise live_run.GameWindowGone("the game window is gone")

            hands = live_run.Hands(click=click, key=lambda v: None, scroll=lambda *a: None, sleep=lambda s: None)
            result = save_reload_run.drive_reload(log, hands, menu_timeout=0.2)
        self.assertEqual((result.verdict, result.stage), ("LIVE_STUCK", "continue"))
        self.assertIn("Reading save data from [x]", result.detail)

    def test_config_gate_and_stale_file_cleanup(self) -> None:
        with resolved_temp_dir() as rig:
            common = rig / "saves" / "common"
            common.mkdir(parents=True)
            self.assertEqual(save_reload_run.save_reload_configured(rig), 0)
            (common / "bf_probe_config.data").write_text(json.dumps({"save_reload": {"after_days": 3}}), encoding="utf-8")
            self.assertEqual(save_reload_run.save_reload_configured(rig), 3)
            (common / "bf_probe_fingerprint.data").write_text("{}", encoding="utf-8")
            self.assertTrue(save_reload_run.clear_stale_fingerprint(rig))
            self.assertFalse((Path(rig) / save_reload_run.FINGERPRINT_FILE).exists())


if __name__ == "__main__":
    unittest.main()
