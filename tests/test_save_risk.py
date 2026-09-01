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



class Save_riskTests(unittest.TestCase):
    def test_save_risk_flags_changed_persistent_identifier(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "config.json").write_text('{"factionId": "legacy"}', encoding="utf-8")
            workspace = create_workspace(source, root / "workspace")
            _, working, _ = workspace_paths(workspace)
            (working / "config.json").write_text('{"factionIdRenamed": "modern"}', encoding="utf-8")
            result = analyze_save_risk(workspace)
            self.assertEqual(result["risk"], "HIGH")


    def test_save_risk_flags_identifier_value_change_and_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "a.json").write_text('{"factionId": "old"}', encoding="utf-8")
            (source / "deleted.json").write_text('{"shipId": "removed"}', encoding="utf-8")
            workspace = create_workspace(source, root / "workspace")
            _, working, _ = workspace_paths(workspace)
            (working / "a.json").write_text('{"factionId": "new"}', encoding="utf-8")
            (working / "deleted.json").unlink()
            result = analyze_save_risk(workspace)
            self.assertEqual(len(result["findings"]), 2)


