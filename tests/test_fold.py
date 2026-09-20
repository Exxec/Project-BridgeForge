"""`bridgeforge fold` (roadmap P14 item 10) and the `revenantlib-fold-conflict` scan check it feeds.

Hermetic: every fold runs against temp directories, and `successors_path` is always pointed at a
temp file so the real `bridgeforge/dependency_successors.json` is never touched.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bridgeforge.cli import main
from bridgeforge.fold import FoldError, fold
from bridgeforge.scanner import scan_mod


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _mod_info(path: Path, **fields) -> None:
    data = {"id": "mylib", "name": "MyLib", "author": "Someone", "version": "1.0", "gameVersion": "0.9a"}
    data.update(fields)
    _write(path / "mod_info.json", json.dumps(data))


class FoldCommandTests(unittest.TestCase):
    def _source(self, root: Path, **mod_info_fields) -> Path:
        source = root / "MyLib"
        _mod_info(source, **mod_info_fields)
        _write(source / "data" / "x.csv", "a,b\n1,2\n")
        return source

    def test_dry_run_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(root)
            target = root / "RevenantLib"
            target.mkdir()
            successors_path = root / "successors.json"

            result = fold(source, target, dry_run=True, successors_path=successors_path)

            self.assertEqual(result["status"], "OK")
            self.assertTrue(result["dry_run"])
            self.assertEqual(sorted(result["files_copied"]), ["data/x.csv", "mod_info.json"])
            self.assertFalse((target / "original").exists())
            self.assertFalse((target / "reports").exists())
            self.assertFalse(successors_path.exists())

    def test_real_run_copies_files_and_writes_provenance_and_successors_entry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(root)
            target = root / "RevenantLib"
            target.mkdir()
            successors_path = root / "successors.json"

            result = fold(source, target, successors_path=successors_path)

            self.assertEqual(result["status"], "OK")
            self.assertTrue(result["provenance_written"])
            self.assertTrue(result["successors_entry_written"])
            copied_mod_info = target / "original" / "MyLib" / "mod_info.json"
            copied_csv = target / "original" / "MyLib" / "data" / "x.csv"
            self.assertEqual(copied_mod_info.read_bytes(), (source / "mod_info.json").read_bytes())
            self.assertEqual(copied_csv.read_bytes(), (source / "data" / "x.csv").read_bytes())

            provenance = (target / "reports" / "PROVENANCE.md").read_text(encoding="utf-8")
            self.assertIn("## Origin: MyLib", provenance)
            self.assertIn("mod id `mylib`", provenance)
            self.assertIn("author `Someone`", provenance)
            self.assertIn("version `1.0`", provenance)
            self.assertIn('gameVersion "0.9a"', provenance)
            self.assertIn("data/x.csv", provenance)

            successors = json.loads(successors_path.read_text(encoding="utf-8"))
            entries = [e for e in successors["successors"] if e["kind"] == "folded-into-revenantlib"]
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["match"], "mylib")
            self.assertIn("revenantlib", entries[0]["action"])

    def test_missing_mod_info_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Empty"
            source.mkdir()
            target = root / "RevenantLib"
            target.mkdir()
            with self.assertRaises(FoldError):
                fold(source, target, successors_path=root / "successors.json")

    def test_nonexistent_source_or_target_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(root)
            target = root / "RevenantLib"
            target.mkdir()
            with self.assertRaises(FoldError):
                fold(root / "NoSuchSource", target, successors_path=root / "s.json")
            with self.assertRaises(FoldError):
                fold(source, root / "NoSuchTarget", successors_path=root / "s.json")

    def test_nested_source_and_target_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "RevenantLib"
            source = target / "MyLib"
            _mod_info(source)
            with self.assertRaises(FoldError):
                fold(source, target, successors_path=root / "s.json")

    def test_existing_destination_is_refused_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(root)
            target = root / "RevenantLib"
            target.mkdir()
            successors_path = root / "successors.json"
            fold(source, target, successors_path=successors_path)

            result = fold(source, target, successors_path=successors_path)

            self.assertEqual(result["status"], "REFUSED")
            self.assertEqual(result["files_copied"], [])

    def test_rerun_with_overwrite_and_identical_content_is_a_noop(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(root)
            target = root / "RevenantLib"
            target.mkdir()
            successors_path = root / "successors.json"
            fold(source, target, successors_path=successors_path)
            provenance_before = (target / "reports" / "PROVENANCE.md").read_text(encoding="utf-8")

            result = fold(source, target, overwrite=True, successors_path=successors_path)

            self.assertEqual(result["status"], "NOOP")
            self.assertEqual((target / "reports" / "PROVENANCE.md").read_text(encoding="utf-8"), provenance_before)
            # No duplicate section or successors entry from the re-run.
            self.assertEqual(provenance_before.count("## Origin: MyLib"), 1)
            successors = json.loads(successors_path.read_text(encoding="utf-8"))
            self.assertEqual(len([e for e in successors["successors"] if e["match"] == "mylib"]), 1)

    def test_differing_existing_file_is_a_conflict_and_nothing_is_written(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(root)
            target = root / "RevenantLib"
            target.mkdir()
            successors_path = root / "successors.json"
            fold(source, target, successors_path=successors_path)
            # Someone/something changed the folded copy.
            (target / "original" / "MyLib" / "data" / "x.csv").write_text("a,b\n9,9\n", encoding="utf-8")
            # And the source mod also picked up a genuinely new file.
            _write(source / "data" / "new.csv", "c\n3\n")

            result = fold(source, target, overwrite=True, successors_path=successors_path)

            self.assertEqual(result["status"], "CONFLICT")
            self.assertEqual(result["conflicts"], ["data/x.csv"])
            # Never resolved silently: the new file is not copied either, and nothing else changes.
            self.assertFalse((target / "original" / "MyLib" / "data" / "new.csv").exists())
            self.assertEqual((target / "original" / "MyLib" / "data" / "x.csv").read_text(encoding="utf-8"), "a,b\n9,9\n")

    def test_licence_file_is_reported_as_factual_evidence_not_a_judgement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(root)
            _write(source / "LICENSE.txt", "MIT")
            target = root / "RevenantLib"
            target.mkdir()
            result = fold(source, target, successors_path=root / "successors.json")
            self.assertIn("LICENSE.txt", result["licence_evidence"])

    def test_default_name_and_version_fall_back_when_metadata_is_sparse(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Sparse"
            _write(source / "mod_info.json", json.dumps({"id": "sparse"}))
            target = root / "RevenantLib"
            target.mkdir()
            result = fold(source, target, successors_path=root / "successors.json")
            self.assertEqual(result["mod_name"], "sparse")
            self.assertEqual(result["author"], "unknown")
            self.assertEqual(result["version"], "unknown")
            self.assertEqual(result["game_version"], "unknown")

    def test_cli_dry_run_reports_ok_and_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(root)
            target = root / "RevenantLib"
            target.mkdir()
            successors_path = root / "successors.json"
            exit_code = main([
                "fold", str(source), str(target), "--dry-run",
                "--successors-path", str(successors_path), "--json",
            ])
            self.assertEqual(exit_code, 0)
            self.assertFalse((target / "original").exists())

    def test_cli_real_run_then_refused_rerun_exit_codes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(root)
            target = root / "RevenantLib"
            target.mkdir()
            successors_path = root / "successors.json"
            self.assertEqual(main(["fold", str(source), str(target), "--successors-path", str(successors_path)]), 0)
            self.assertEqual(main(["fold", str(source), str(target), "--successors-path", str(successors_path)]), 1)

    def test_cli_bad_source_is_a_usage_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "RevenantLib"
            target.mkdir()
            exit_code = main(["fold", str(root / "NoSuchSource"), str(target), "--successors-path", str(root / "s.json")])
            self.assertEqual(exit_code, 2)


def _successors_patch(entries: list[dict]):
    return mock.patch("bridgeforge.substitutes.load_successors", return_value=entries)


class RevenantlibFoldConflictScanTests(unittest.TestCase):
    """The MANUAL check that fires when a mod declares both revenantlib and an id
    dependency_successors.json records as folded into it (deliverable 4 of the fold-in workflow).
    `bridgeforge.substitutes.load_successors` is patched (not a real file) so this stays hermetic and
    independent of whatever real folds have happened by the time this test runs.
    """

    FOLDED_ENTRY = {"match": "oldlib", "kind": "folded-into-revenantlib", "successor": "s", "action": "a", "evidence": "e"}

    def _mod(self, root: Path, dependencies: list) -> None:
        _write(root / "mod_info.json", json.dumps({"id": "dependent", "name": "Dependent", "gameVersion": "0.98a", "dependencies": dependencies}))

    def test_declaring_both_the_original_and_revenantlib_is_manual(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._mod(root, [{"id": "revenantlib", "name": "RevenantLib"}, {"id": "oldlib", "name": "OldLib"}])
            with _successors_patch([self.FOLDED_ENTRY]):
                result = scan_mod(root)
            findings = [f for f in result.findings if f.id == "revenantlib-fold-conflict"]
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].classification, "MANUAL")
            self.assertEqual(findings[0].evidence, ["oldlib"])

    def test_bare_string_dependency_entries_are_also_matched(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._mod(root, ["revenantlib", "oldlib"])
            with _successors_patch([self.FOLDED_ENTRY]):
                result = scan_mod(root)
            self.assertEqual(len([f for f in result.findings if f.id == "revenantlib-fold-conflict"]), 1)

    def test_declaring_only_revenantlib_is_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._mod(root, [{"id": "revenantlib", "name": "RevenantLib"}])
            with _successors_patch([self.FOLDED_ENTRY]):
                result = scan_mod(root)
            self.assertEqual([f for f in result.findings if f.id == "revenantlib-fold-conflict"], [])

    def test_declaring_only_the_original_without_revenantlib_is_not_flagged(self) -> None:
        # revenantlib not declared at all: not the double-registration this check reports.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._mod(root, [{"id": "oldlib", "name": "OldLib"}])
            with _successors_patch([self.FOLDED_ENTRY]):
                result = scan_mod(root)
            self.assertEqual([f for f in result.findings if f.id == "revenantlib-fold-conflict"], [])

    def test_no_folded_ids_recorded_anywhere_means_no_finding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._mod(root, [{"id": "revenantlib", "name": "RevenantLib"}, {"id": "oldlib", "name": "OldLib"}])
            with _successors_patch([]):
                result = scan_mod(root)
            self.assertEqual([f for f in result.findings if f.id == "revenantlib-fold-conflict"], [])


if __name__ == "__main__":
    unittest.main()
