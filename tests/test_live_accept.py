"""`bridgeforge accept` and `archive --refresh/--readme-copy` (2026-10-06 ideas, items 2 and 3)."""
from __future__ import annotations

import json
import shutil
import unittest
import zipfile
from pathlib import Path

from bridgeforge.archive import ArchiveError, archive_mod, write_readme_copies
from bridgeforge.live.live_accept import AcceptError, accept_run
from bridgeforge.live.live_trust import live_status
from bridgeforge.release import record_policy_decision
from tests.bound_runs import bound_run
from tests.support import resolved_temp_dir

REPO_POLICY = Path(__file__).resolve().parent.parent / "bridgeforge" / "release_policy.json"

_MENU = "100 [Thread-8] INFO  sound.H  - Playing music with id [miscallenous_main_menu.ogg]"
_LOAD = "150 [Thread-2] INFO  com.fs.starfarer.campaign.save.CampaignGameManager  - Loading C:\\rig\\saves\\save_Test_1..."
_SAVED = "160 [Thread-2] INFO  com.fs.starfarer.campaign.save.CampaignGameManager  - Finished saving"
_DAY = "170 [Thread-2] INFO  com.bridgeforge.probe.ProbeLog  - BF-PROBE|0.2.17|campaign-day|INFO|clock|daysSinceStart=70.0"
_NPE = [
    "200 [Thread-3] ERROR exerelin.campaign.ai.StrategicAI  - Strategic AI: executive module failed",
    "java.lang.NullPointerException: x",
    "        at com.fs.starfarer.api.impl.campaign.intel.raid.RaidIntel.getETA(RaidIntel.java:292) ~[starfarer.api.jar:?]",
    "",
]


def _workspace(root: Path) -> Path:
    ws = root / "In operation" / "Radar"
    working = ws / "working"
    (working / "reports").mkdir(parents=True)
    (working / "jars").mkdir()
    (working / "mod_info.json").write_text(json.dumps({"id": "bf_fixture_radar", "name": "Radar", "version": "3.0", "gameVersion": "0.98a-RC8"}), encoding="utf-8")
    (working / "jars" / "radar.jar").write_bytes(b"PK\x05\x06" + b"\x00" * 18)
    (working / "reports" / "REVIVAL_REPORT.md").write_text("# Report\n\nREADY_FOR_LIVE_TEST\n", encoding="utf-8")
    return ws


def _log(root: Path, lines: list[str]) -> Path:
    path = root / "run.stdout.log"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _run(root: Path, ws: Path, test_id: str, lines: list[str], expected: tuple[str, ...] = ("main_menu", "campaign_load")) -> tuple[Path, Path]:
    """A synthetic staged run of the workspace's mod: (rig, the run's own log). R1: acceptance needs this manifest."""
    return bound_run(root, {"bf_fixture_radar": ws}, test_id, lines, expected=expected)


class AcceptTests(unittest.TestCase):
    def test_a_clean_run_writes_the_evidence_section_and_a_current_run_record(self) -> None:
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            rig, log = _run(root, ws, "T-1", [_MENU, _LOAD, _SAVED, _DAY])
            result = accept_run(ws, log, test_id="T-1", note="played 70 days", days=60, not_exercised="no raid happened",
                                today="2026-10-06", rig=rig)
            report = (ws / "working" / "reports" / "REVIVAL_REPORT.md").read_text(encoding="utf-8")
            status = live_status(ws)
            record = json.loads((ws.parent / "_live" / "T-1.json").read_text(encoding="utf-8"))
        self.assertIn("## Live run T-1 (2026-10-06, RC8 rig)", report)
        self.assertIn("Not exercised: no raid happened", report)
        self.assertTrue(report.rstrip().endswith("LIVE_VALIDATED"))
        self.assertEqual(status["status"], "CURRENT")
        self.assertEqual(status["provenance"], "BOUND")
        self.assertEqual(record["members"][0]["provenance"], "BOUND")
        self.assertEqual(record["manifest_id"], record["evidence"]["manifest_id"])
        self.assertEqual(result["soak"], "PASS")

    def test_a_run_without_a_manifest_is_not_accepted(self) -> None:
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            log = _log(root, [_MENU, _LOAD])
            with self.assertRaises(AcceptError) as no_rig:
                accept_run(ws, log, test_id="T-0", note="n")
            rig, _ = _run(root, ws, "T-0", [_MENU, _LOAD])
            with self.assertRaises(AcceptError) as other_id:
                accept_run(ws, log, test_id="T-OTHER", note="n", rig=rig)
            report = (ws / "working" / "reports" / "REVIVAL_REPORT.md").read_text(encoding="utf-8")
        self.assertIn("--rig", str(no_rig.exception))
        self.assertIn("no readable manifest", str(other_id.exception))
        self.assertNotIn("LIVE_VALIDATED", report)

    def test_a_run_without_a_save_or_load_is_refused(self) -> None:
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            rig, log = _run(root, ws, "T-2", [_MENU], expected=("main_menu",))
            with self.assertRaises(AcceptError) as ctx:
                accept_run(ws, log, test_id="T-2", note="n", rig=rig)
            report = (ws / "working" / "reports" / "REVIVAL_REPORT.md").read_text(encoding="utf-8")
        self.assertIn("no campaign load and no save", str(ctx.exception))
        self.assertNotIn("LIVE_VALIDATED", report)

    def test_too_few_days_is_refused(self) -> None:
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            rig, log = _run(root, ws, "T-3", [_MENU, _LOAD, _DAY])
            with self.assertRaises(AcceptError) as ctx:
                accept_run(ws, log, test_id="T-3", note="n", days=120, rig=rig)
        self.assertIn("soak INCOMPLETE", str(ctx.exception))

    def test_a_caught_exception_needs_a_reason_and_the_reason_is_recorded(self) -> None:
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            rig, log = _run(root, ws, "T-4", [_MENU, _LOAD, *_NPE])
            with self.assertRaises(AcceptError) as ctx:
                accept_run(ws, log, test_id="T-4", note="n", rig=rig)
            accept_run(ws, log, test_id="T-4", note="n", accept_findings="Nexerelin logs it; not this mod", today="2026-10-06", rig=rig)
            report = (ws / "working" / "reports" / "REVIVAL_REPORT.md").read_text(encoding="utf-8")
        self.assertIn("findings need a reason", str(ctx.exception))
        self.assertIn("Nexerelin logs it; not this mod", report)

    def test_the_same_test_id_is_not_recorded_twice(self) -> None:
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            rig, log = _run(root, ws, "T-5", [_MENU, _LOAD])
            accept_run(ws, log, test_id="T-5", note="n", rig=rig)
            with self.assertRaises(AcceptError):
                accept_run(ws, log, test_id="T-5", note="n", rig=rig)

    def test_record_only_leaves_the_report_alone(self) -> None:
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            before = (ws / "working" / "reports" / "REVIVAL_REPORT.md").read_text(encoding="utf-8")
            rig, log = _run(root, ws, "T-6", [_MENU, _LOAD])
            accept_run(ws, log, test_id="T-6", note="n", record_only=True, rig=rig)
            after = (ws / "working" / "reports" / "REVIVAL_REPORT.md").read_text(encoding="utf-8")
            status = live_status(ws)
        self.assertEqual(before, after)
        self.assertEqual(status["status"], "CURRENT")

    def test_an_edit_after_testing_is_refused_and_never_becomes_current(self) -> None:
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            rig, log = _run(root, ws, "T-7", [_MENU, _LOAD])
            (ws / "working" / "jars" / "radar.jar").write_bytes(b"PK\x05\x06" + b"\x01" * 18)  # same version, different bytes
            with self.assertRaises(AcceptError) as ctx:
                accept_run(ws, log, test_id="T-7", note="n", rig=rig)
            status = live_status(ws)
        self.assertIn("working copy changed", str(ctx.exception))
        self.assertEqual(status["status"], "NOT_TESTED")


class ArchiveRefreshTests(unittest.TestCase):
    def _archived(self, root: Path) -> tuple[Path, Path]:
        ws = _workspace(root)
        policy = root / "policy.json"
        shutil.copy2(REPO_POLICY, policy)
        record_policy_decision("bf_fixture_radar", local_only=True, reason="fixture", policy_path=policy)
        archive_mod(ws, root / "Done", policy_path=policy, today="2026-10-06")
        return ws, policy

    def test_refresh_replaces_an_existing_archive_and_plain_archive_still_refuses(self) -> None:
        with resolved_temp_dir() as root:
            ws, policy = self._archived(root)
            with self.assertRaises(ArchiveError):
                archive_mod(ws, root / "Done", policy_path=policy)
            (ws / "working" / "reports" / "REVIVAL_REPORT.md").write_text("# Report\n\nLIVE_VALIDATED\n", encoding="utf-8")
            result = archive_mod(ws, root / "Done", policy_path=policy, today="2026-10-07", refresh=True)
            note = Path(result["note"]).read_text(encoding="utf-8")
        self.assertIn("LIVE_VALIDATED", note)

    def test_refresh_refuses_a_folder_that_is_not_one_of_our_archives(self) -> None:
        with resolved_temp_dir() as root:
            ws, policy = self._archived(root)
            (root / "Done" / "Radar" / "ARCHIVE_NOTE.md").unlink()
            with self.assertRaises(ArchiveError) as ctx:
                archive_mod(ws, root / "Done", policy_path=policy, refresh=True)
            still_there = (root / "Done" / "Radar").is_dir()
        self.assertIn("no ARCHIVE_NOTE.md", str(ctx.exception))
        self.assertTrue(still_there)

    def test_readme_copy_adds_readme_without_the_contents_section(self) -> None:
        with resolved_temp_dir() as root:
            self._archived(root)
            target = root / "Done" / "Radar"
            written = write_readme_copies(target)
            with zipfile.ZipFile(target / written[0]) as archive:
                names = archive.namelist()
                readme = archive.read("readme.txt").decode("utf-8")
            plain = (target / "readme.txt").read_bytes().decode("utf-8")
        self.assertEqual(written, ["Radar-3.0-with-readme.zip"])
        self.assertIn("readme.txt", names)
        self.assertNotIn("## Contents", readme)
        self.assertEqual(readme, plain)


if __name__ == "__main__":
    unittest.main()
