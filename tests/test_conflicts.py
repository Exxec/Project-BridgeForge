import json
import io
import tempfile
import unittest
import warnings
import zipfile
import shutil
import subprocess
from contextlib import redirect_stderr
from unittest.mock import patch
from pathlib import Path

from bridgeforge import __version__, scanner
from bridgeforge.bytecode import inspect_bytecode, rewrite_class
from bridgeforge.bytecode_diff import diff_bytecode
from bridgeforge.bytecode_rules import apply_bytecode_class, apply_bytecode_jar, load_bytecode_rules, plan_bytecode
from bridgeforge.scanner import scan_mod
from bridgeforge.report import write_artifacts
from bridgeforge.migrate import apply_plan, build_plan, load_rules
from bridgeforge.models import TargetProfile
from bridgeforge.workspace import create_workspace, rollback, workspace_paths
from bridgeforge.build import compile_feedback, create_build_profile, package_compiled_jar, resolve_registered_dependency_jars, run_compile
from bridgeforge.library_registry import LibraryRegistryEntry, load_library_registry
from bridgeforge.review import create_review_bundle
from bridgeforge.validate import validate_workspace
from bridgeforge.save_risk import analyze_save_risk
from bridgeforge.pipeline import run_pipeline
from bridgeforge.packs import BRIDGEFORGE_VERSION, MigrationPack, compatible, discover_packs, resolve_pack_rule_paths
from bridgeforge.opportunities import analyze_opportunities
from bridgeforge.doctor import doctor
from bridgeforge.conflicts import detect_conflicts
from bridgeforge.provenance import write_provenance
from bridgeforge.corpus import compare_corpus
from bridgeforge.evaluation import evaluate_releases
from bridgeforge.runtime import create_runtime_profile, run_runtime_smoke
from bridgeforge.fixtures import discover_compatibility_fixtures, discover_corpus_baselines
from bridgeforge.interface import export_patch, inspect_workspace
from bridgeforge.corpus_audit import audit_directories
from bridgeforge.corpus_audit import write_corpus_audit
from bridgeforge.archive_intake import inspect_zip_archive, stage_zip_archive
from bridgeforge.library_api import inventory_library_api, match_library_imports
from bridgeforge.cli import main



class ConflictsTests(unittest.TestCase):
    def test_plan_reports_conflicts_and_apply_never_starts_when_a_target_changed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "one.json").write_text(json.dumps({"one": "old"}), encoding="utf-8")
            (source / "two.json").write_text(json.dumps({"two": "old"}), encoding="utf-8")
            rules = root / "rules.json"
            rules.write_text(json.dumps({"pack": {"schema_version": 1, "id": "test"}, "rules": [
                {"id": "one", "classification": "SAFE", "confidence": "HIGH", "description": "one", "file": "one.json", "json_key": "one", "value_from_target": "starsector"},
                {"id": "two", "classification": "SAFE", "confidence": "HIGH", "description": "two", "file": "two.json", "json_key": "two", "value_from_target": "starsector"},
                {"id": "two-conflict", "classification": "SAFE", "confidence": "HIGH", "description": "conflict", "file": "two.json", "json_key": "other", "value_from_target": "starsector"}
            ]}), encoding="utf-8")
            workspace = create_workspace(source, root / "workspace")
            plan = build_plan(workspace, TargetProfile("0.98", 17), [rules])
            self.assertEqual(plan["conflicts"][0]["rule_id"], "two-conflict")
            (workspace / "working-copy" / "two.json").write_text(json.dumps({"two": "changed"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                apply_plan(workspace, {"one", "two"})
            self.assertEqual(json.loads((workspace / "working-copy" / "one.json").read_text(encoding="utf-8"))["one"], "old")


    def test_conflict_and_provenance_artifacts_are_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "mod_info.json").write_text("{}", encoding="utf-8")
            for name in ("one.jar", "two.jar"):
                with zipfile.ZipFile(source / name, "w") as archive:
                    archive.writestr("same/Thing.class", b"\xca\xfe\xba\xbe\x00\x00\x00\x34")
            workspace = create_workspace(source, root / "workspace")
            conflicts = detect_conflicts(workspace)
            provenance = write_provenance(workspace)
            repeat_provenance = write_provenance(workspace)
            (workspace / "working-copy" / "new-file.txt").write_text("changed", encoding="utf-8")
            changed_provenance = write_provenance(workspace)
            self.assertEqual(conflicts["status"], "CONFLICTS_FOUND")
            self.assertTrue(any(item["kind"] == "duplicate-class" for item in conflicts["findings"]))
            self.assertEqual(provenance["schema_version"], 1)
            self.assertEqual(provenance["working_copy_tree_sha256"], repeat_provenance["working_copy_tree_sha256"])
            self.assertNotEqual(provenance["working_copy_tree_sha256"], changed_provenance["working_copy_tree_sha256"])
            self.assertTrue((workspace / "conflicts.json").is_file())
            self.assertTrue((workspace / "provenance.json").is_file())

