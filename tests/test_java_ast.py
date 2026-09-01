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



class Java_astTests(unittest.TestCase):
    def test_bytecode_inspector_reports_symbolic_references_without_execution(self) -> None:
        if not shutil.which("javac") or not shutil.which("java"):
            self.skipTest("JDK is unavailable")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Fixture.java"
            source.write_text("class Fixture { static String value() { try { int i = 1; if (i > 0) System.out.print(\"\"); return new String(String.valueOf(Math.abs(-1))); } catch (RuntimeException ex) { return \"\"; } } }", encoding="utf-8")
            completed = subprocess.run(["javac", "--release", "17", "-d", str(root), str(source)], capture_output=True, text=True, check=False)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = inspect_bytecode([root / "Fixture.class"])
            self.assertEqual(result["mode"], "INSPECTION_ONLY")
            self.assertEqual(len(result["classes"]), 1)
            references = result["classes"][0]["references"]
            self.assertTrue(any(reference.get("owner") == "java/lang/Math" and reference.get("name") == "abs" for reference in references))
            self.assertEqual(diff_bytecode([root / "Fixture.class"], [root / "Fixture.class"])["changed_classes"], [])
            rules = root / "bytecode-rules.json"
            evidence = {"provenance": "fixture", "before_fixture": "fixture", "after_fixture": "fixture", "semantic_diff_validation": "fixture", "idempotence": "fixture", "conflict_review": "fixture", "save_risk_assessment": "fixture"}
            rules.write_text(json.dumps({"schema_version": 1, "kind": "bridgeforge-bytecode-rules", "rules": [{"id": "fixture-type", "action": "remap-class-reference", "classification": "REVIEW", "description": "fixture", "owner": "java/lang/String", "replacement_owner": "example/String", "opcode": 187, "expected_matches": 1, "evidence": evidence}]}), encoding="utf-8")
            plan = plan_bytecode([root / "Fixture.class"], rules)
            self.assertEqual(len(plan["planned"]), 1)
            self.assertEqual(plan["planned"][0]["constraints"]["application"], "REVIEW_GATED_OUTPUT_COPY")
            type_applied = apply_bytecode_class(root / "Fixture.class", root / "Fixture.type-output.class", rules, {"fixture-type"})
            self.assertEqual(type_applied["mode"], "REVIEW_APPLIED_TO_OUTPUT_COPY")
            self.assertTrue(any(reference.get("owner") == "example/String" for reference in inspect_bytecode([root / "Fixture.type-output.class"])["classes"][0]["references"]))
            method_rules = root / "method-rules.json"
            method_rules.write_text(json.dumps({"schema_version": 1, "kind": "bridgeforge-bytecode-rules", "rules": [{"id": "fixture-method", "action": "remap-method-reference", "classification": "REVIEW", "description": "fixture", "owner": "java/lang/Math", "name": "abs", "descriptor": "(I)I", "opcode": 184, "replacement_owner": "example/Math", "replacement_name": "abs", "replacement_descriptor": "(I)I", "expected_matches": 1, "evidence": evidence}]}), encoding="utf-8")
            method_plan = plan_bytecode([root / "Fixture.class"], method_rules)
            self.assertEqual(len(method_plan["planned"]), 1)
            rewritten = root / "Fixture.rewritten.class"
            self.assertEqual(rewrite_class(root / "Fixture.class", rewritten, load_bytecode_rules(method_rules)[0]), 1)
            diff = diff_bytecode([root / "Fixture.class"], [rewritten])
            self.assertEqual(len(diff["changed_classes"]), 1)
            self.assertTrue(diff["changed_classes"][0]["invariants"]["same_reference_shape"])
            for key in ("same_instruction_counts", "same_opcode_sequence", "same_branch_counts", "same_exception_tables"):
                self.assertTrue(diff["changed_classes"][0]["invariants"][key])
            self.assertTrue(any(reference.get("owner") == "example/Math" for reference in inspect_bytecode([rewritten])["classes"][0]["references"]))
            applied = apply_bytecode_class(root / "Fixture.class", root / "Fixture.output.class", method_rules, {"fixture-method"})
            self.assertEqual(applied["mode"], "REVIEW_APPLIED_TO_OUTPUT_COPY")
            input_jar, output_jar = root / "Fixture.jar", root / "Fixture.output.jar"
            with zipfile.ZipFile(input_jar, "w") as archive:
                archive.write(root / "Fixture.class", "Fixture.class")
                archive.writestr("assets/keep.txt", b"unchanged")
            jar_applied = apply_bytecode_jar(input_jar, output_jar, method_rules, {"fixture-method"})
            self.assertEqual(jar_applied["mode"], "REVIEW_APPLIED_TO_JAR_COPY")
            with zipfile.ZipFile(output_jar) as archive:
                self.assertEqual(archive.read("assets/keep.txt"), b"unchanged")
            self.assertTrue(any(reference.get("owner") == "example/Math" for reference in inspect_bytecode([output_jar])["classes"][0]["references"]))
            field_rules = root / "field-rules.json"
            field_rules.write_text(json.dumps({"schema_version": 1, "kind": "bridgeforge-bytecode-rules", "rules": [{"id": "fixture-field", "action": "remap-field-reference", "classification": "REVIEW", "description": "fixture", "owner": "java/lang/System", "name": "out", "descriptor": "Ljava/io/PrintStream;", "opcode": 178, "replacement_owner": "example/System", "replacement_name": "out", "replacement_descriptor": "Ljava/io/PrintStream;", "expected_matches": 1, "evidence": evidence}]}), encoding="utf-8")
            self.assertEqual(len(plan_bytecode([root / "Fixture.class"], field_rules)["planned"]), 1)
            self.assertEqual(apply_bytecode_class(root / "Fixture.class", root / "Fixture.field-output.class", field_rules, {"fixture-field"})["mode"], "REVIEW_APPLIED_TO_OUTPUT_COPY")
            self.assertTrue(any(reference.get("owner") == "example/System" for reference in inspect_bytecode([root / "Fixture.field-output.class"])["classes"][0]["references"]))


    def test_scans_metadata_bytecode_and_assets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text(json.dumps({"id": "legacy", "gameVersion": "0.95.1a", "dependencies": ["MagicLib"]}), encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "Example.java").write_text("import sun.misc.Unsafe;", encoding="utf-8")
            (root / "data").mkdir()
            (root / "data" / "broken.json").write_text("{", encoding="utf-8")
            with zipfile.ZipFile(root / "LazyLib.jar", "w") as archive:
                archive.writestr("Example.class", b"\xca\xfe\xba\xbe\x00\x00\x00\x34")
            result = scan_mod(root)
            self.assertEqual(result.estimated_starsector, "0.95.1a")
            self.assertEqual(result.estimated_java, "8")
            self.assertTrue(any(f.id == "bundled-lazylib" for f in result.findings))
            self.assertTrue(any(f.id == "internal-jvm-api" for f in result.findings))
            self.assertTrue(any(f.id == "unverified-json-syntax" for f in result.findings))


    def test_ast_source_analysis_collects_method_invocations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Example.java").write_text("import java.util.List; class Example { void x() { System.out.println(List.of()); } }", encoding="utf-8")
            result = scan_mod(root)
            self.assertIn("java.util.List", result.imports)
            self.assertTrue(any(fact["kind"] == "method_invocation" and fact["value"] == "System.out.println" for fact in result.source_facts))


    def test_method_migration_uses_ast_source_offset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "Example.java").write_text('class Example { void x() { String note = "OldApi.foo"; OldApi.foo(); } }', encoding="utf-8")
            pack = root / "methods.json"
            pack.write_text(json.dumps({"pack": {"id": "fixture-methods", "schema_version": 1}, "rules": [{"id": "migrate-method", "classification": "REVIEW", "confidence": "DETERMINISTIC", "description": "fixture", "action": "replace-method-invocation", "from_invocation": "OldApi.foo", "to_invocation": "NewApi.bar"}]}), encoding="utf-8")
            workspace = create_workspace(source, root / "workspace")
            build_plan(workspace, TargetProfile(), [pack])
            apply_plan(workspace, {"migrate-method"})
            _, working, _ = workspace_paths(workspace)
            content = (working / "Example.java").read_text(encoding="utf-8")
            self.assertIn('"OldApi.foo"', content)
            self.assertIn("NewApi.bar();", content)


    def test_method_migration_handles_utf16_source_offsets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "Example.java").write_text('class Example { String note = "ðŸ˜€"; void x() { OldApi.foo(); } }', encoding="utf-8")
            pack = root / "methods.json"
            pack.write_text(json.dumps({"pack": {"id": "fixture-utf16", "schema_version": 1}, "rules": [{"id": "migrate-utf16", "classification": "REVIEW", "confidence": "DETERMINISTIC", "description": "fixture", "action": "replace-method-invocation", "from_invocation": "OldApi.foo", "to_invocation": "NewApi.bar"}]}), encoding="utf-8")
            workspace = create_workspace(source, root / "workspace")
            build_plan(workspace, TargetProfile(), [pack])
            apply_plan(workspace, {"migrate-utf16"})
            _, working, _ = workspace_paths(workspace)
            self.assertIn("NewApi.bar();", (working / "Example.java").read_text(encoding="utf-8"))


