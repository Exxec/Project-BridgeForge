import json
import tempfile
import unittest
import zipfile
import shutil
from pathlib import Path

from bridgeforge.scanner import scan_mod
from bridgeforge.report import write_artifacts
from bridgeforge.migrate import apply_plan, build_plan
from bridgeforge.models import TargetProfile
from bridgeforge.workspace import create_workspace, rollback, workspace_paths
from bridgeforge.build import compile_feedback, create_build_profile, run_compile
from bridgeforge.review import create_review_bundle
from bridgeforge.validate import validate_workspace
from bridgeforge.save_risk import analyze_save_risk


class ScannerTests(unittest.TestCase):
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
            self.assertTrue(any(f.id == "invalid-json" for f in result.findings))

    def test_ast_source_analysis_collects_method_invocations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Example.java").write_text("import java.util.List; class Example { void x() { System.out.println(List.of()); } }", encoding="utf-8")
            result = scan_mod(root)
            self.assertIn("java.util.List", result.imports)
            self.assertTrue(any(fact["kind"] == "method_invocation" and fact["value"] == "System.out.println" for fact in result.source_facts))

    def test_refuses_artifacts_inside_original_mod(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = scan_mod(root)
            with self.assertRaises(ValueError):
                write_artifacts(result, root / "artifacts")

    def test_workspace_plan_apply_and_rollback_preserve_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "mod_info.json").write_text(json.dumps({"id": "legacy", "gameVersion": "0.95.1a"}), encoding="utf-8")
            workspace = create_workspace(source, root / "workspace")
            plan = build_plan(workspace, TargetProfile("0.98a-RC8", 17))
            self.assertEqual(len(plan["migrations"]), 1)
            manifest = apply_plan(workspace, {"metadata-target-starsector-version"})
            self.assertEqual(len(manifest["applied"]), 1)
            _, working, _ = workspace_paths(workspace)
            self.assertEqual(json.loads((working / "mod_info.json").read_text(encoding="utf-8"))["gameVersion"], "0.98a-RC8")
            self.assertEqual(json.loads((source / "mod_info.json").read_text(encoding="utf-8"))["gameVersion"], "0.95.1a")
            rollback(workspace, "00-original")
            self.assertEqual(json.loads((working / "mod_info.json").read_text(encoding="utf-8"))["gameVersion"], "0.95.1a")

    def test_safe_rule_packs_apply_only_with_safe_flag(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "mod_info.json").write_text(json.dumps({"id": "legacy", "gameVersion": "0.95.1a"}), encoding="utf-8")
            pack = root / "safe-pack.json"
            pack.write_text(json.dumps({"pack": {"id": "fixture", "schema_version": 1}, "rules": [{"id": "fixture-safe", "classification": "SAFE", "confidence": "DETERMINISTIC", "description": "fixture", "file": "mod_info.json", "json_key": "gameVersion", "value_from_target": "starsector"}]}), encoding="utf-8")
            workspace = create_workspace(source, root / "workspace")
            plan = build_plan(workspace, TargetProfile("0.98a-RC8", 17), [pack])
            self.assertEqual(plan["rule_packs"], ["fixture"])
            self.assertEqual(len(apply_plan(workspace, set())["applied"]), 0)
            self.assertEqual(len(apply_plan(workspace, set(), apply_safe=True)["applied"]), 1)

    def test_import_migration_uses_ast_confirmed_import_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "Example.java").write_text("import old.api.Helper;\nclass Example { String note = \"import old.api.Helper;\"; }\n", encoding="utf-8")
            pack = root / "imports.json"
            pack.write_text(json.dumps({"pack": {"id": "fixture-imports", "schema_version": 1}, "rules": [{"id": "migrate-helper-import", "classification": "REVIEW", "confidence": "DETERMINISTIC", "description": "fixture", "action": "replace-import", "from_import": "old.api.Helper", "to_import": "new.api.Helper"}]}), encoding="utf-8")
            workspace = create_workspace(source, root / "workspace")
            plan = build_plan(workspace, TargetProfile(), [pack])
            self.assertEqual(len(plan["migrations"]), 1)
            apply_plan(workspace, {"migrate-helper-import"})
            _, working, _ = workspace_paths(workspace)
            content = (working / "Example.java").read_text(encoding="utf-8")
            self.assertIn("import new.api.Helper;", content)
            self.assertIn('"import old.api.Helper;"', content)

    def test_build_profile_records_jdk_and_command_without_compiling(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            (source / "src").mkdir(parents=True)
            (source / "src" / "Example.java").write_text("class Example {}", encoding="utf-8")
            workspace = create_workspace(source, root / "workspace")
            jdk = root / "jdk"
            (jdk / "bin").mkdir(parents=True)
            (jdk / "release").write_text('IMPLEMENTOR="Eclipse Adoptium"\nJAVA_VERSION="27"\n', encoding="utf-8")
            profile = create_build_profile(workspace, TargetProfile("0.98a-RC8", 17), jdk, [], [])
            self.assertEqual(profile.jdk.metadata["JAVA_VERSION"], "27")
            self.assertEqual(profile.source_roots, ["src"])
            self.assertIn("--release", profile.command_preview)

    def test_compile_executes_profile_and_classifies_errors(self) -> None:
        javac = shutil.which("javac")
        if not javac:
            self.skipTest("JDK compiler unavailable")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            (source / "src").mkdir(parents=True)
            (source / "src" / "Example.java").write_text("class Example { MissingType x; }", encoding="utf-8")
            workspace = create_workspace(source, root / "workspace")
            create_build_profile(workspace, TargetProfile("0.98a-RC8", 17), Path(javac).parent.parent, [], [])
            result = run_compile(workspace)
            self.assertFalse(result["success"])
            self.assertTrue(any(item["kind"] == "missing-symbol" for item in result["diagnostics"]))
            feedback = compile_feedback(workspace)
            self.assertEqual(len(feedback["findings"]), len(result["diagnostics"]))
            self.assertTrue((workspace / "COMPILE_FEEDBACK.md").is_file())

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
