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



class PipelineTests(unittest.TestCase):
    def test_missing_compile_library_keeps_pipeline_running_as_unavailable(self) -> None:
        javac = shutil.which("javac")
        if not javac:
            self.skipTest("JDK compiler unavailable")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            (source / "src").mkdir(parents=True)
            (source / "mod_info.json").write_text(json.dumps({"id": "fixture", "gameVersion": "0.98"}), encoding="utf-8")
            (source / "src" / "Example.java").write_text("class Example {}", encoding="utf-8")
            workspace = create_workspace(source, root / "workspace")
            missing = root / "missing-lazylib.jar"
            profile = create_build_profile(workspace, TargetProfile("0.98", 17), Path(javac).parent.parent, [], [missing])
            self.assertEqual(profile.compile_validation["status"], "UNAVAILABLE")
            self.assertEqual(profile.compile_validation["findings"][0]["id"], "compile-validation-unavailable")
            result = run_pipeline(workspace, TargetProfile("0.98", 17), jdk=Path(javac).parent.parent, dependency_jars=[missing], compile_requested=True)
            self.assertEqual(result["compile_status"], "UNAVAILABLE")
            self.assertIsNone(result["compile"])
            self.assertEqual(result["compile_validation"]["findings"][0]["jar"], str(missing.resolve()))
            self.assertIn(str(missing.resolve()), (workspace / "BUILD_REPORT.md").read_text(encoding="utf-8"))
            self.assertIn(str(missing.resolve()), (workspace / "MODERNIZATION_REPORT.md").read_text(encoding="utf-8"))
            self.assertTrue((workspace / "MODERNIZATION_REPORT.md").is_file())


    def test_review_bundle_is_bounded_to_planned_working_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "mod_info.json").write_text(json.dumps({"id": "legacy", "gameVersion": "0.95"}), encoding="utf-8")
            workspace = create_workspace(source, root / "workspace")
            build_plan(workspace, TargetProfile("0.98", 17))
            bundle = create_review_bundle(workspace)
            self.assertTrue((bundle / "prompt.md").is_file())
            self.assertTrue((bundle / "working-copy-files" / "mod_info.json").is_file())


    def test_validation_keeps_runtime_explicitly_unconfigured(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "mod_info.json").write_text(json.dumps({"id": "modern", "gameVersion": "0.98"}), encoding="utf-8")
            workspace = create_workspace(source, root / "workspace")
            result = validate_workspace(workspace, TargetProfile("0.98", 17))
            self.assertEqual(result["reference_integrity"]["status"], "PASS")
            self.assertEqual(result["runtime_validation"]["status"], "NOT_CONFIGURED")


    def test_pipeline_writes_final_report_without_implicit_review_apply(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "mod_info.json").write_text(json.dumps({"id": "legacy", "gameVersion": "0.95"}), encoding="utf-8")
            workspace = create_workspace(source, root / "workspace")
            result = run_pipeline(workspace, TargetProfile("0.98", 17))
            self.assertEqual(result["apply"]["applied_count"], 0)
            self.assertTrue(Path(result["scan"]["manifest"]).is_file())
            self.assertTrue((workspace / "MODERNIZATION_REPORT.md").is_file())


    def test_pipeline_can_emit_review_gated_bytecode_artifact(self) -> None:
        if not shutil.which("javac") or not shutil.which("java"):
            self.skipTest("JDK is unavailable")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "mod_info.json").write_text(json.dumps({"id": "legacy", "gameVersion": "0.95"}), encoding="utf-8")
            java_source = source / "Fixture.java"
            java_source.write_text("class Fixture { static int value() { return Math.abs(-1); } }", encoding="utf-8")
            completed = subprocess.run(["javac", "--release", "17", "-d", str(source), str(java_source)], capture_output=True, text=True, check=False)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            evidence = {"provenance": "fixture", "before_fixture": "fixture", "after_fixture": "fixture", "semantic_diff_validation": "fixture", "idempotence": "fixture", "conflict_review": "fixture", "save_risk_assessment": "fixture"}
            rules = root / "bytecode-rules.json"
            rules.write_text(json.dumps({"schema_version": 1, "kind": "bridgeforge-bytecode-rules", "rules": [{"id": "fixture-method", "action": "remap-method-reference", "classification": "REVIEW", "description": "fixture", "owner": "java/lang/Math", "name": "abs", "descriptor": "(I)I", "opcode": 184, "replacement_owner": "example/Math", "replacement_name": "abs", "replacement_descriptor": "(I)I", "expected_matches": 1, "evidence": evidence}]}), encoding="utf-8")
            workspace = create_workspace(source, root / "workspace")
            result = run_pipeline(workspace, TargetProfile("0.98", 17), bytecode_file="Fixture.class", bytecode_rules=rules, bytecode_approved={"fixture-method"})
            self.assertEqual(result["bytecode"]["mode"], "REVIEW_APPLIED_TO_OUTPUT_COPY")
            self.assertTrue((workspace / "bytecode-artifacts" / "Fixture.class").is_file())
            self.assertIn("03-bytecode-artifact", workspace_paths(workspace)[2]["checkpoints"])


    def test_runtime_profile_never_executes_without_explicit_flag(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            workspace = create_workspace(source, root / "workspace")
            executable = root / "launcher.exe"
            executable.write_text("not executed", encoding="utf-8")
            create_runtime_profile(workspace, executable, [], root, 60)
            self.assertEqual(run_runtime_smoke(workspace)["status"], "NOT_EXECUTED")


    def test_runtime_smoke_can_require_explicit_log_markers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            workspace = create_workspace(source, root / "workspace")
            create_runtime_profile(workspace, Path(__import__("sys").executable), ["-c", "from pathlib import Path; Path('runtime.log').write_text('READY')"], root, 10, "runtime.log", ["READY"])
            self.assertEqual(run_runtime_smoke(workspace, execute=True)["status"], "PASS")


    def test_runtime_smoke_fails_when_expected_log_marker_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            workspace = create_workspace(source, root / "workspace")
            create_runtime_profile(workspace, Path(__import__("sys").executable), ["-c", "from pathlib import Path; Path('runtime.log').write_text('READY')"], root, 10, "runtime.log", ["STARTED"])
            result = run_runtime_smoke(workspace, execute=True)
            self.assertEqual(result["status"], "FAILED")
            self.assertEqual(result["log_validation"]["missing_markers"], ["STARTED"])


    def test_release_evaluation_reports_content_and_finding_deltas_without_runtime_claim(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before, after = root / "before", root / "after"
            before.mkdir()
            after.mkdir()
            (before / "mod_info.json").write_text('{"id":"fixture","gameVersion":"0.95",}', encoding="utf-8")
            (after / "mod_info.json").write_text('{"id":"fixture","gameVersion":"0.98"}', encoding="utf-8")
            (before / "shared.txt").write_text("same", encoding="utf-8")
            (after / "shared.txt").write_text("same", encoding="utf-8")
            (before / "changed.txt").write_text("old", encoding="utf-8")
            (after / "changed.txt").write_text("new", encoding="utf-8")
            (before / "legacy.java").write_text("class Legacy {}", encoding="utf-8")
            (after / "replacement.jar").write_bytes(b"not a jar")
            result = evaluate_releases(before, after)
            self.assertEqual(result["mode"], "READ_ONLY_RELEASE_EVALUATION")
            self.assertEqual(result["assessment"], "PARTIALLY_COMPARABLE")
            self.assertEqual(result["content"]["identical_file_count"], 1)
            self.assertEqual(result["content"]["changed_paths"], ["changed.txt", "mod_info.json"])
            self.assertEqual(result["comparability"]["runtime_validation"], "NOT_PERFORMED")
            self.assertFalse(any(str(before) in str(value) or str(after) in str(value) for value in result.values()))


    def test_opportunities_are_review_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            (source / "src").mkdir(parents=True)
            (source / "src" / "Bounty.java").write_text("class Bounty { void settings() {} }", encoding="utf-8")
            workspace = create_workspace(source, root / "workspace")
            result = analyze_opportunities(workspace)
            self.assertGreaterEqual(len(result["findings"]), 2)
            self.assertTrue(all("do not adopt automatically" in item["recommendation"].lower() for item in result["findings"]))


    def test_doctor_emits_machine_readable_status(self) -> None:
        result = doctor()
        self.assertEqual(result["schema_version"], 1)
        self.assertTrue(any(check["id"] == "migration-packs" for check in result["checks"]))


