"""BUGS.md FIX-001: a fixer backup with no file beside it must be caught (apply_fix, scanner, archive, zip preflight)."""
from __future__ import annotations

import shutil
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from bridgeforge.archive import ArchiveError, archive_mod
from bridgeforge.archive_intake import inspect_zip_archive
from bridgeforge.fixer_backups import backup_target, orphaned_backups, orphaned_backups_in
from bridgeforge.fixers import FileChange, FixerError, FixPlan, apply_fix, compute_fix
from bridgeforge.release import record_policy_decision
from bridgeforge.scanner import scan_mod
from tests.support import resolved_temp_dir

REPO_POLICY = Path(__file__).resolve().parent.parent / "bridgeforge" / "release_policy.json"
BAK = ".pre-bf-fix-data-file-not-utf8.bak"
MOD_INFO = '{"id": "bf_fixture_orphan", "name": "Orphan", "author": "A", "version": "1.0", "gameVersion": "0.98a-RC8"}'


def _mod(root: Path) -> Path:
    mod = root / "working"
    (mod / "data" / "campaign").mkdir(parents=True)
    (mod / "mod_info.json").write_text(MOD_INFO, encoding="utf-8")
    return mod


class BackupNameTests(unittest.TestCase):
    def test_backup_names_map_to_their_file(self) -> None:
        self.assertEqual(backup_target("rules.csv" + BAK), "rules.csv")
        self.assertEqual(backup_target("rules.csv" + BAK + ".2"), "rules.csv")
        self.assertIsNone(backup_target("rules.csv.bak"))
        self.assertIsNone(backup_target("rules.csv" + BAK + ".old"))

    def test_scratch_backups_and_backups_with_a_file_are_ignored(self) -> None:
        listing = ["data/a.csv", "data/a.csv" + BAK, "data/b.csv" + BAK, "scratch/c.csv" + BAK, "Data/D.csv", "data/d.csv" + BAK + ".3"]
        self.assertEqual(orphaned_backups_in(listing), ["data/b.csv" + BAK])


class ApplyFixGuardTests(unittest.TestCase):
    def test_large_rules_csv_with_isolated_cp1252_byte_survives_the_fix(self) -> None:
        with resolved_temp_dir() as root:
            mod = _mod(root)
            rules = mod / "data" / "campaign" / "rules.csv"
            rules.write_bytes(b"id,trigger\n" + b'x,"It\x92s fine"\n' * 100_000)
            apply_fix(compute_fix(mod, "data-file-not-utf8", {}))
            text = rules.read_bytes().decode("utf-8")
            backup_kept = (rules.parent / ("rules.csv" + BAK)).is_file()
        self.assertIn("It’s fine", text)
        self.assertTrue(backup_kept)

    def test_a_fixed_file_that_vanishes_after_writing_raises_and_keeps_the_backup(self) -> None:
        with resolved_temp_dir() as root:
            mod = _mod(root)
            target = mod / "data" / "campaign" / "rules.csv"
            target.write_bytes(b"a\x92b\n")
            plan = FixPlan("data-file-not-utf8", mod, [FileChange(path=target, before=b"a\x92b\n", after="a’b\n".encode())])
            real_write = Path.write_bytes

            def lossy_write(self: Path, data: bytes) -> int:
                written = real_write(self, data)
                if self.name == "rules.csv":
                    self.unlink()  # the planned file is lost right after it is written
                return written

            with mock.patch.object(Path, "write_bytes", lossy_write):
                with self.assertRaises(FixerError) as raised:
                    apply_fix(plan)
            backup = (target.parent / ("rules.csv" + BAK)).read_bytes()
        self.assertIn("rules.csv", str(raised.exception))
        self.assertEqual(backup, b"a\x92b\n")

    def test_a_file_holding_other_bytes_than_planned_raises(self) -> None:
        with resolved_temp_dir() as root:
            mod = _mod(root)
            target = mod / "data" / "campaign" / "rules.csv"
            target.write_bytes(b"old\n")
            plan = FixPlan("data-file-not-utf8", mod, [FileChange(path=target, before=b"old\n", after=b"new\n")])
            real_write = Path.write_bytes

            def wrong_write(self: Path, data: bytes) -> int:
                return real_write(self, data[:-1] if self.name == "rules.csv" else data)

            with mock.patch.object(Path, "write_bytes", wrong_write):
                with self.assertRaises(FixerError):
                    apply_fix(plan)


class OrphanFindingTests(unittest.TestCase):
    def _orphaned_mod(self, root: Path) -> Path:
        mod = _mod(root)
        (mod / "data" / "campaign" / ("rules.csv" + BAK)).write_bytes(b"id\n")
        return mod

    def test_scanner_reports_a_manual_finding_for_an_orphaned_backup(self) -> None:
        with resolved_temp_dir() as root:
            mod = self._orphaned_mod(root)
            findings = [f for f in scan_mod(mod).findings if f.id == "fixer-backup-orphaned"]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].classification, "MANUAL")
        self.assertIn("data/campaign/rules.csv" + BAK, findings[0].evidence)

    def test_scanner_is_quiet_when_the_file_is_beside_its_backup_or_the_backup_is_in_scratch(self) -> None:
        with resolved_temp_dir() as root:
            mod = self._orphaned_mod(root)
            (mod / "data" / "campaign" / "rules.csv").write_bytes(b"id\n")
            (mod / "scratch").mkdir()
            (mod / "scratch" / ("gone.csv" + BAK)).write_bytes(b"x")
            found = [f.id for f in scan_mod(mod).findings]
            listed = orphaned_backups(mod)
        self.assertNotIn("fixer-backup-orphaned", found)
        self.assertEqual(listed, [])

    def test_archive_refuses_while_a_backup_is_orphaned(self) -> None:
        with resolved_temp_dir() as root:
            workspace = root / "Orphan"
            shutil.copytree(self._orphaned_mod(root / "stage"), workspace / "working")
            policy = root / "policy.json"
            shutil.copy2(REPO_POLICY, policy)
            record_policy_decision("bf_fixture_orphan", local_only=True, reason="fixture", policy_path=policy)
            with self.assertRaises(ArchiveError) as raised:
                archive_mod(workspace, root / "Done", policy_path=policy)
            made = (root / "Done").exists()
        self.assertIn("fixer-backup-orphaned", str(raised.exception))
        self.assertFalse(made)

    def test_zip_preflight_blocks_an_archive_with_an_orphaned_backup(self) -> None:
        with resolved_temp_dir() as root:
            archive = root / "mod.zip"
            with zipfile.ZipFile(archive, "w") as handle:
                handle.writestr("Orphan/mod_info.json", MOD_INFO)
                handle.writestr("Orphan/data/campaign/rules.csv" + BAK, "id\n")
            report = inspect_zip_archive(archive)
        ids = [item["id"] for item in report["findings"]]
        self.assertIn("fixer-backup-orphaned", ids)
        self.assertFalse(report["safe_to_stage"])


if __name__ == "__main__":
    unittest.main()
