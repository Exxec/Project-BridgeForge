"""ROADMAP item 73 G5: `probe-group record --accept` records through accept_run and carries only covered findings."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from bridgeforge.group_accept import assess_group, context_of
from bridgeforge.live.live_accept import accept_run
from bridgeforge.probe.probe_config import build_probe_config
from bridgeforge.run_manifest import read_manifest
from bridgeforge.probe.probe_group import ProbeGroupError, merge_configs, record_group
from tests.bound_runs import bound_run
from tests.support import resolved_temp_dir
from tests.test_probe_group import _workspace

PREFIX = "9 [Thread-2] INFO  com.bridgeforge.probe.ProbeLog  - "
MENU = "100 [Thread-8] INFO  sound.H  - Playing music with id [miscallenous_main_menu.ogg]"
LOAD = "150 [Thread-2] INFO  com.fs.starfarer.campaign.save.CampaignGameManager  - Loading C:\\rig\\saves\\save_Test_1..."
OK = PREFIX + "BF-PROBE|0.2.9|content-ids|OK|all-content|checked=2 failed=0"
FAIL_A = PREFIX + "BF-PROBE|0.2.9|content-ids|FAIL|variant:hull_a_Std|broken"
FAIL_B = PREFIX + "BF-PROBE|0.2.9|content-ids|FAIL|variant:hull_b_Std|broken"


class _Fixture:
    def __init__(self, root: Path, log_lines: list[str]) -> None:
        self.queue = root / "In operation"
        self.a = _workspace(self.queue, "A", "mod_a", "hull_a")
        self.b = _workspace(self.queue, "B", "mod_b", "hull_b")
        self.config = merge_configs([build_probe_config(self.a), build_probe_config(self.b)])
        self.rig, self.log = bound_run(root, {"mod_a": self.queue / "A", "mod_b": self.queue / "B"}, "GRP-A", [MENU, LOAD, *log_lines],
                                       core_build="0.98.5a-RC7")

    def record(self, **kwargs):
        return record_group(self.log, self.config, self.queue, self.rig, test_id="GRP-A", today="2026-10-14", **kwargs)

    def report(self, name: str) -> str:
        return (self.queue / name / "working" / "reports" / "REVIVAL_REPORT.md").read_text(encoding="utf-8")

    def accept_standing(self, name: str, check: str, subject: str, reason: str) -> None:
        path = self.queue / name / "working" / "reports" / "probe_accepted.json"
        path.write_text(json.dumps({"accepted": [{"check": check, "subject": subject, "reason": reason}]}), encoding="utf-8")


class AcceptRecordTests(unittest.TestCase):
    def test_a_clean_group_is_recorded_through_accept_run_with_the_note(self) -> None:
        with resolved_temp_dir() as root:
            fx = _Fixture(root, [OK])
            result = fx.record(accept=True, note="ran New Game and a day")
            run = json.loads((fx.queue / "_live" / "GRP-A.json").read_text(encoding="utf-8"))
            report_a = fx.report("A")
        self.assertEqual(result["recorded"], ["A", "B"])
        self.assertIsNone(result["stopped"])
        self.assertIn("## Live run GRP-A (2026-10-14, 0.98.5a-RC7 rig)", report_a)
        self.assertIn("Owner's account: ran New Game and a day", report_a)
        self.assertNotIn("## Live probe run", report_a)
        self.assertEqual(sorted(m["workspace"] for m in run["members"]), ["A", "B"])  # the group record was not replaced by a one-member one

    def test_a_plain_record_names_the_rigs_build_and_not_the_owner(self) -> None:
        # 96.5 A1: the heading said "RC8 rig" on the 0.98.5a-RC7 rig, and the body credited the owner with runs the harness played.
        with resolved_temp_dir() as root:
            fx = _Fixture(root, [OK])
            fx.record()
            report_a = fx.report("A")
        self.assertIn("## Live probe run GRP-A (group run, 0.98.5a-RC7 rig)", report_a)
        self.assertIn("The run started a New Game, played one in-game day and the probe combat mission.", report_a)
        self.assertNotIn("Owner ran", report_a)

    def test_accept_needs_a_note(self) -> None:
        with resolved_temp_dir() as root:
            fx = _Fixture(root, [OK])
            with self.assertRaises(ProbeGroupError):
                fx.record(accept=True)

    def test_a_fail_line_an_earlier_standing_acceptance_covers_is_carried(self) -> None:
        with resolved_temp_dir() as root:
            fx = _Fixture(root, [OK, FAIL_A])
            fx.accept_standing("A", "content-ids", "variant:hull_a_Std", "hidden faction builds no patrol")
            result = fx.record(accept=True, note="played")
            report_a = fx.report("A")
        self.assertEqual(result["recorded"], ["A", "B"])
        self.assertIn("carried from earlier acceptance of the same mod version: hidden faction builds no patrol", report_a)

    def test_a_content_parity_line_every_id_of_which_is_accepted_is_carried(self) -> None:
        # ROADMAP-3 93.26: per-id acceptances cover the probe's per-mod content-parity line (Tania, G4B-LIVE-0985a-20261117).
        parity = PREFIX + "BF-PROBE|0.3.2|content-parity|FAIL|mod=mod_a|kind=hulls missing 1/2: hull_x"
        with resolved_temp_dir() as root:
            fx = _Fixture(root, [OK, parity])
            fx.accept_standing("A", "content-parity", "hulls:hull_x", "a CSV row with no .ship file")
            result = fx.record(accept=True, note="played")
            report_a = fx.report("A")
        self.assertEqual(result["recorded"], ["A", "B"])
        self.assertIn("carried from earlier acceptance of the same mod version: a CSV row with no .ship file", report_a)

    def test_a_content_parity_line_with_an_id_not_accepted_still_stops(self) -> None:
        parity = PREFIX + "BF-PROBE|0.3.2|content-parity|FAIL|mod=mod_a|kind=hulls missing 0/2: hull_x,hull_y"
        with resolved_temp_dir() as root:
            fx = _Fixture(root, [OK, parity])
            fx.accept_standing("A", "content-parity", "hulls:hull_x", "a CSV row with no .ship file")
            result = fx.record(accept=True, note="played")
        self.assertEqual(result["recorded"], [])
        self.assertEqual(result["stopped"]["uncovered_probe_fail"], ["content-parity|mod=mod_a"])

    def test_a_fail_line_nothing_covers_stops_the_group_and_records_nothing(self) -> None:
        with resolved_temp_dir() as root:
            fx = _Fixture(root, [OK, FAIL_A, FAIL_B])
            fx.accept_standing("A", "content-ids", "variant:hull_a_Std", "known")
            result = fx.record(accept=True, note="played")
            report_a = fx.report("A")
        self.assertEqual(result["recorded"], [])
        self.assertEqual(result["stopped"]["uncovered_probe_fail"], ["content-ids|variant:hull_b_Std"])
        self.assertNotIn("Live run", report_a)

    def test_a_remembered_acceptance_covers_the_same_version_only(self) -> None:
        with resolved_temp_dir() as root:
            fx = _Fixture(root, [OK, FAIL_A])
            accept_run(fx.queue / "A", fx.log, test_id="GRP-A", note="first run", accept_findings="harmless, checked by hand",
                       mods_dir=fx.rig / "mods", today="2026-10-01", write_record=False, rig=fx.rig)
            kept = (fx.queue / "A" / "reports" / "live_accepted.jsonl").read_text(encoding="utf-8")
            context = context_of(read_manifest(fx.rig, "GRP-A"))
            same = assess_group(fx.log, [fx.queue / "A", fx.queue / "B"], context=context)
            other = assess_group(fx.log, [fx.queue / "A", fx.queue / "B"], context={**context, "probe_config_sha256": "changed"})
            info = fx.queue / "A" / "working" / "mod_info.json"
            info.write_text(json.dumps({"id": "mod_a", "gameVersion": "0.98a-RC8", "version": "2.0"}), encoding="utf-8")
            newer = assess_group(fx.log, [fx.queue / "A", fx.queue / "B"], context=context)
        self.assertIn("content-ids|variant:hull_a_Std", kept)
        self.assertEqual(same["uncovered_keys"], [])
        self.assertIn("harmless, checked by hand", same["reason"])
        self.assertEqual(newer["uncovered_keys"], ["content-ids|variant:hull_a_Std"])
        self.assertEqual(other["uncovered_keys"], ["content-ids|variant:hull_a_Std"])  # same version, other circumstances: not carried

    def test_a_log_without_the_main_menu_is_refused_by_accept_run_and_stops(self) -> None:
        with resolved_temp_dir() as root:
            fx = _Fixture(root, [OK])
            fx.log.write_text(OK + "\n", encoding="utf-8")
            result = fx.record(accept=True, note="played")
        self.assertEqual(result["recorded"], [])
        self.assertIn("main_menu", " ".join(result["stopped"]["problems"]))


if __name__ == "__main__":
    unittest.main()
