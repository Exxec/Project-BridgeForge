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



class WorkspaceTests(unittest.TestCase):
    def test_refuses_artifacts_inside_original_mod(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = scan_mod(root)
            with self.assertRaises(ValueError):
                write_artifacts(result, root / "artifacts")


    def test_inspect_and_patch_export_exclude_original_mod(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "mod_info.json").write_text(json.dumps({"id": "legacy", "gameVersion": "0.95"}), encoding="utf-8")
            workspace = create_workspace(source, root / "workspace")
            build_plan(workspace, TargetProfile("0.98", 17))
            self.assertEqual(len(inspect_workspace(workspace)["planned_migrations"]), 1)
            output = export_patch(workspace, root / "patch")
            self.assertTrue((output / "migration-plan.json").is_file())
            self.assertFalse((output / "original-reference").exists())


    def test_workspace_rejects_manifest_path_escape_and_repeated_plan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "mod_info.json").write_text(json.dumps({"gameVersion": "0.95"}), encoding="utf-8")
            workspace = create_workspace(source, root / "workspace")
            build_plan(workspace, TargetProfile("0.98", 17))
            build_plan(workspace, TargetProfile("0.98", 17))
            self.assertTrue((workspace / "checkpoints" / "01-scanned-2").is_dir())
            manifest = json.loads((workspace / "workspace-manifest.json").read_text(encoding="utf-8"))
            manifest["working_copy"] = "../source"
            (workspace / "workspace-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(ValueError):
                workspace_paths(workspace)


    def test_workspace_rejects_manifest_symlink_escape_when_supported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "mod_info.json").write_text("{}", encoding="utf-8")
            workspace = create_workspace(source, root / "workspace")
            outside = root / "outside"
            outside.mkdir()
            link = workspace / "linked-working-copy"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest("symlink creation is unavailable in this environment")
            manifest = json.loads((workspace / "workspace-manifest.json").read_text(encoding="utf-8"))
            manifest["working_copy"] = link.name
            (workspace / "workspace-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(ValueError):
                workspace_paths(workspace)


