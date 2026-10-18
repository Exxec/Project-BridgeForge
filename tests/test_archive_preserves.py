"""BUGS.md DOC-001: `archive --refresh` moves the previous archive aside; it never deletes it."""
from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from unittest import mock

from bridgeforge.archive import ArchiveError, archive_mod
from bridgeforge.release import record_policy_decision
from tests.support import resolved_temp_dir

REPO_POLICY = Path(__file__).resolve().parent.parent / "bridgeforge" / "release_policy.json"


def _setup(root: Path) -> tuple[Path, Path, Path]:
    ws = root / "In operation" / "Radar"
    working = ws / "working"
    (working / "reports").mkdir(parents=True)
    (working / "mod_info.json").write_text(json.dumps({"id": "bf_fx_radar", "name": "Radar", "version": "3.0", "gameVersion": "0.98a-RC8"}), encoding="utf-8")
    (working / "data").mkdir()
    (working / "data" / "a.csv").write_text("id\n1\n", encoding="utf-8")
    (working / "reports" / "REVIVAL_REPORT.md").write_text("# R\n\nLIVE_VALIDATED\n", encoding="utf-8")
    policy = root / "policy.json"
    shutil.copy2(REPO_POLICY, policy)
    record_policy_decision("bf_fx_radar", local_only=True, reason="fixture", policy_path=policy)
    archive_mod(ws, root / "Done", policy_path=policy, today="2026-10-18")
    (root / "Done" / "Radar" / "marker.txt").write_text("first archive bytes", encoding="utf-8")
    return ws, root / "Done", policy


class RefreshPreservesTests(unittest.TestCase):
    def test_old_bytes_survive_a_successful_refresh(self) -> None:
        with resolved_temp_dir() as root:
            ws, done, policy = _setup(root)
            result = archive_mod(ws, done, policy_path=policy, today="2026-10-19", refresh=True)
            kept = (done / "_replaced-2026-10-19" / "Radar" / "marker.txt").read_text(encoding="utf-8")
            new_has_marker = (done / "Radar" / "marker.txt").exists()
        self.assertEqual(kept, "first archive bytes")
        self.assertFalse(new_has_marker)
        self.assertTrue(result["replaced"].endswith("Radar"))

    def test_a_failure_during_the_new_write_restores_the_old_archive_and_reports_the_state(self) -> None:
        with resolved_temp_dir() as root:
            ws, done, policy = _setup(root)
            with mock.patch("bridgeforge.archive.atomic_write_text", side_effect=OSError("disk full")):
                with self.assertRaises(ArchiveError) as ctx:
                    archive_mod(ws, done, policy_path=policy, today="2026-10-19", refresh=True)
            back = (done / "Radar" / "marker.txt").read_text(encoding="utf-8")
            note = (done / "Radar" / "ARCHIVE_NOTE.md").is_file()
            partial = list((done / "_failed-2026-10-19").glob("Radar*"))
            replaced_left = list((done / "_replaced-2026-10-19").glob("*")) if (done / "_replaced-2026-10-19").exists() else []
        self.assertEqual(back, "first archive bytes")
        self.assertTrue(note)
        self.assertEqual(len(partial), 1)
        self.assertEqual(replaced_left, [])
        self.assertIn("disk full", str(ctx.exception))
        self.assertIn("moved back", str(ctx.exception))
        self.assertIn("partial new archive was moved to", str(ctx.exception))

    def test_a_conflicting_replaced_destination_gets_a_numbered_suffix(self) -> None:
        with resolved_temp_dir() as root:
            ws, done, policy = _setup(root)
            archive_mod(ws, done, policy_path=policy, today="2026-10-19", refresh=True)
            (done / "Radar" / "marker.txt").write_text("second archive bytes", encoding="utf-8")
            archive_mod(ws, done, policy_path=policy, today="2026-10-19", refresh=True)
            first = (done / "_replaced-2026-10-19" / "Radar" / "marker.txt").read_text(encoding="utf-8")
            second = (done / "_replaced-2026-10-19" / "Radar-2" / "marker.txt").read_text(encoding="utf-8")
        self.assertEqual((first, second), ("first archive bytes", "second archive bytes"))

    def test_unsafe_targets_are_refused_and_nothing_moves(self) -> None:
        with resolved_temp_dir() as root:
            ws, done, policy = _setup(root)
            (done / "Radar" / "ARCHIVE_NOTE.md").unlink()
            with self.assertRaisesRegex(ArchiveError, "no ARCHIVE_NOTE.md"):
                archive_mod(ws, done, policy_path=policy, today="2026-10-19", refresh=True)
            still = (done / "Radar" / "marker.txt").is_file()
            (done / "Radar" / "ARCHIVE_NOTE.md").write_text("note", encoding="utf-8")
            holder = done / "_replaced-2026-10-19"
            holder.write_text("a file, not a folder", encoding="utf-8")
            with self.assertRaisesRegex(ArchiveError, "not a folder"):
                archive_mod(ws, done, policy_path=policy, today="2026-10-19", refresh=True)
            still_after = (done / "Radar" / "marker.txt").is_file()
        self.assertTrue(still and still_after)

    def test_plain_archive_still_refuses_an_existing_folder(self) -> None:
        with resolved_temp_dir() as root:
            ws, done, policy = _setup(root)
            with self.assertRaisesRegex(ArchiveError, "already exists"):
                archive_mod(ws, done, policy_path=policy, today="2026-10-19")


if __name__ == "__main__":
    unittest.main()
