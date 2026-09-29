"""ROADMAP P15 item 20.1: package a finished revival into Done/ in one step."""
from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from bridgeforge.archive import ArchiveError, archive_mod
from bridgeforge.release import record_policy_decision
from tests.support import resolved_temp_dir

REPO_POLICY = Path(__file__).resolve().parent.parent / "bridgeforge" / "release_policy.json"


def _workspace(root: Path) -> Path:
    ws = root / "In operation" / "Radar"
    original = ws / "original" / "Radar 3.0"
    (original / "jars").mkdir(parents=True)
    (original / "mod_info.json").write_text('{"id": "bf_fixture_radar", "name": "Radar", "author": "LazyWizard", "version": "3.0", "gameVersion": "0.9a"}', encoding="utf-8")
    (original / "jars" / "radar.jar").write_bytes(b"PK\x05\x06" + b"\x00" * 18)
    shutil.copytree(original, ws / "working")
    (ws / "working" / "mod_info.json").write_text('{"id": "bf_fixture_radar", "name": "Radar", "author": "LazyWizard", "version": "3.0", "gameVersion": "0.98a-RC8", "jars": ["jars/radar.jar"]}', encoding="utf-8")
    (ws / "working" / "reports").mkdir()
    (ws / "working" / "reports" / "REVIVAL_REPORT.md").write_text("# Report\n\nREADY_FOR_LIVE_TEST\n", encoding="utf-8")
    (ws / "working" / "mod_info.json.pre-bf-fix-x.bak").write_text("backup", encoding="utf-8")
    return ws


class ArchiveTests(unittest.TestCase):
    def test_object_versions_are_written_as_dotted_text(self) -> None:
        from bridgeforge.archive import _version_text

        self.assertEqual(_version_text({"major": "0", "minor": "2", "patch": "4"}), "0.2.4")
        self.assertEqual(_version_text("1.0.e"), "1.0.e")
        self.assertEqual(_version_text(None), "unversioned")

    def test_archives_the_layout_and_writes_an_evidence_based_note(self) -> None:
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            policy = root / "policy.json"
            shutil.copy2(REPO_POLICY, policy)
            with self.assertRaises(ArchiveError):
                archive_mod(ws, root / "Done", policy_path=policy)  # no licence decision yet
            record_policy_decision("bf_fixture_radar", local_only=True, reason="author unreachable", policy_path=policy)
            result = archive_mod(ws, root / "Done", policy_path=policy, today="2026-09-27")
            target = root / "Done" / "Radar"
            note = (target / "ARCHIVE_NOTE.md").read_text(encoding="utf-8")
            shipped = sorted(p.relative_to(target / "Radar").as_posix() for p in (target / "Radar").rglob("*") if p.is_file())
            layout = sorted(p.name for p in target.iterdir())
            still_there = (ws / "working" / "mod_info.json").is_file()
            with self.assertRaises(ArchiveError):
                archive_mod(ws, root / "Done", policy_path=policy)  # never overwrites
        self.assertEqual(layout, ["ARCHIVE_NOTE.md", "Radar", "Radar-3.0.zip", "original", "workspace"])
        self.assertEqual(shipped, ["jars/radar.jar", "mod_info.json"])  # no backups or reports shipped
        self.assertEqual((result["changed"], result["jars_identical"]), (["mod_info.json"], True))
        self.assertIn("**Original author: LazyWizard.**", note)
        self.assertIn("LOCAL_ONLY`: author unreachable", note)
        self.assertIn("Every jar is byte-identical", note)
        self.assertIn("READY_FOR_LIVE_TEST", note)
        self.assertTrue(still_there)

    def test_an_original_descriptions_copy_is_archived_with_its_own_zip(self) -> None:
        # Owner request 2026-09-28: keep a copy without BridgeForge-written descriptions beside the revival.
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            alt = ws / "alt-original-descriptions" / "Radar"
            shutil.copytree(ws / "original" / "Radar 3.0", alt)
            policy = root / "policy.json"
            shutil.copy2(REPO_POLICY, policy)
            record_policy_decision("bf_fixture_radar", local_only=True, reason="author unreachable", policy_path=policy)
            archive_mod(ws, root / "Done", policy_path=policy, today="2026-09-28")
            target = root / "Done" / "Radar"
            layout = sorted(p.name for p in target.iterdir())
            kept = (target / "alt-original-descriptions" / "Radar" / "mod_info.json").is_file()
        self.assertIn("Radar-3.0-original-descriptions.zip", layout)
        self.assertTrue(kept)

    def test_the_original_descriptions_copy_is_rebuilt_from_the_current_working_copy(self) -> None:
        # Broken Star r2 (2026-09-29): a jar fix made after the descriptions were applied was missing from the
        # author-only zip, because that copy had been taken once, at apply time.
        import zipfile
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            working = ws / "working"
            strings = working / "data" / "strings"
            strings.mkdir(parents=True, exist_ok=True)
            (strings / "descriptions.csv").write_text("id,type,text1\nradar,CUSTOM,crafted\n", encoding="utf-8")
            (ws / "scratch").mkdir(exist_ok=True)
            (ws / "scratch" / "descriptions.csv.pre-bf-crafted").write_text("id,type,text1\n", encoding="utf-8")
            stale = ws / "alt-original-descriptions" / "Radar"
            stale.mkdir(parents=True)
            (stale / "mod_info.json").write_text('{"id":"stale"}', encoding="utf-8")
            (working / "fix.txt").write_text("fixed later", encoding="utf-8")
            policy = root / "policy.json"
            shutil.copy2(REPO_POLICY, policy)
            record_policy_decision("bf_fixture_radar", local_only=True, reason="author unreachable", policy_path=policy)
            archive_mod(ws, root / "Done", policy_path=policy, today="2026-09-29")
            zip_path = next((root / "Done" / "Radar").glob("*-original-descriptions.zip"))
            with zipfile.ZipFile(zip_path) as archive:
                names = set(archive.namelist())
                info = archive.read("Radar/mod_info.json").decode("utf-8")
                descriptions = archive.read("Radar/data/strings/descriptions.csv").decode("utf-8")
        self.assertIn("Radar/fix.txt", names)
        self.assertNotIn("stale", info)
        self.assertNotIn("crafted", descriptions)

if __name__ == "__main__":
    unittest.main()
