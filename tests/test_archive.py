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
    (original / "mod_info.json").write_text('{"id": "lw_radar", "name": "Radar", "author": "LazyWizard", "version": "3.0", "gameVersion": "0.9a"}', encoding="utf-8")
    (original / "jars" / "radar.jar").write_bytes(b"PK\x05\x06" + b"\x00" * 18)
    shutil.copytree(original, ws / "working")
    (ws / "working" / "mod_info.json").write_text('{"id": "lw_radar", "name": "Radar", "author": "LazyWizard", "version": "3.0", "gameVersion": "0.98a-RC8", "jars": ["jars/radar.jar"]}', encoding="utf-8")
    (ws / "working" / "reports").mkdir()
    (ws / "working" / "reports" / "REVIVAL_REPORT.md").write_text("# Report\n\nREADY_FOR_LIVE_TEST\n", encoding="utf-8")
    (ws / "working" / "mod_info.json.pre-bf-fix-x.bak").write_text("backup", encoding="utf-8")
    return ws


class ArchiveTests(unittest.TestCase):
    def test_archives_the_layout_and_writes_an_evidence_based_note(self) -> None:
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            policy = root / "policy.json"
            shutil.copy2(REPO_POLICY, policy)
            with self.assertRaises(ArchiveError):
                archive_mod(ws, root / "Done", policy_path=policy)  # no licence decision yet
            record_policy_decision("lw_radar", local_only=True, reason="author unreachable", policy_path=policy)
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


if __name__ == "__main__":
    unittest.main()
