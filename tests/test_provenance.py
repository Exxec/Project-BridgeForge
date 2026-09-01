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



class ProvenanceTests(unittest.TestCase):
    def test_synthetic_fixture_corpus_has_declared_expectations(self) -> None:
        fixtures = discover_compatibility_fixtures()
        self.assertTrue(any(item["name"] == "import-migration" for item in fixtures))
        self.assertTrue(all(item["expected"]["classification"] in {"SAFE", "REVIEW", "MANUAL", "UNKNOWN"} for item in fixtures))
        for fixture in fixtures:
            expected_findings = fixture["expected"].get("findings") or ([{"id": fixture["expected"]["finding_id"], "classification": fixture["expected"]["classification"]}] if fixture["expected"].get("finding_id") else [])
            findings = scan_mod(Path(fixture["path"])).findings
            for expected in expected_findings:
                self.assertTrue(any(finding.id == expected["id"] and finding.classification == expected["classification"] for finding in findings), fixture["name"])


    def test_sanitized_corpus_baselines_have_no_mod_content(self) -> None:
        baselines = discover_corpus_baselines()
        baseline = next(item for item in baselines if item["name"] == "edmunds-church-2.5-ai-rewrite")
        self.assertEqual(baseline["file_count"], 442)
        self.assertRegex(baseline["mod_info_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(len(baseline["expected_findings"]), 5)


    def test_sanitized_bytecode_baselines_contain_aggregates_only(self) -> None:
        root = Path(__file__).parent / "fixtures" / "bytecode-baselines"
        allowed = {"schema_version", "name", "source_kind", "class_count", "class_file_versions", "method_reference_count", "field_reference_count", "type_reference_count", "invokedynamic_count", "native_method_count", "string_constant_count"}
        for baseline in root.glob("*.json"):
            data = json.loads(baseline.read_text(encoding="utf-8"))
            self.assertEqual(set(data), allowed)
            self.assertNotIn("path", json.dumps(data).lower())


    def test_opt_in_corpus_comparison_uses_only_a_supplied_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mod = root / "mod"
            mod.mkdir()
            metadata = b'{"id":"fixture","gameVersion":"0.98"}'
            (mod / "mod_info.json").write_bytes(metadata)
            baseline = root / "baseline.json"
            baseline.write_text(json.dumps({"schema_version": 1, "name": "fixture", "file_count": 1, "mod_info_sha256": __import__("hashlib").sha256(metadata).hexdigest(), "expected_findings": []}), encoding="utf-8")
            self.assertEqual(compare_corpus(mod, baseline)["status"], "PASS")
            baseline_data = json.loads(baseline.read_text(encoding="utf-8"))
            baseline_data["file_count"] = 2
            baseline.write_text(json.dumps(baseline_data), encoding="utf-8")
            self.assertEqual(compare_corpus(mod, baseline)["status"], "MISMATCH")


