import json
import tempfile
import unittest
import zipfile
import shutil
import subprocess
from unittest.mock import patch
from pathlib import Path

from bridgeforge import __version__, scanner
from bridgeforge.bytecode import inspect_bytecode, rewrite_class
from bridgeforge.bytecode_diff import diff_bytecode
from bridgeforge.bytecode_rules import apply_bytecode_class, load_bytecode_rules, plan_bytecode
from bridgeforge.scanner import scan_mod
from bridgeforge.report import write_artifacts
from bridgeforge.migrate import apply_plan, build_plan, load_rules
from bridgeforge.models import TargetProfile
from bridgeforge.workspace import create_workspace, rollback, workspace_paths
from bridgeforge.build import compile_feedback, create_build_profile, run_compile
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
from bridgeforge.runtime import create_runtime_profile, run_runtime_smoke
from bridgeforge.fixtures import discover_compatibility_fixtures, discover_corpus_baselines
from bridgeforge.interface import export_patch, inspect_workspace


class ScannerTests(unittest.TestCase):
    def test_bytecode_inspector_reports_symbolic_references_without_execution(self) -> None:
        if not shutil.which("javac") or not shutil.which("java"):
            self.skipTest("JDK is unavailable")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Fixture.java"
            source.write_text("class Fixture { static String value() { return new String(String.valueOf(Math.abs(-1))); } }", encoding="utf-8")
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
            rules.write_text(json.dumps({"schema_version": 1, "kind": "bridgeforge-bytecode-rules", "rules": [{"id": "fixture-type", "action": "remap-class-reference", "classification": "REVIEW", "description": "fixture", "owner": "java/lang/String", "replacement_owner": "example/String", "expected_matches": 1, "evidence": evidence}]}), encoding="utf-8")
            plan = plan_bytecode([root / "Fixture.class"], rules)
            self.assertEqual(len(plan["planned"]), 1)
            self.assertEqual(plan["planned"][0]["constraints"]["application"], "NOT_IMPLEMENTED")
            method_rules = root / "method-rules.json"
            method_rules.write_text(json.dumps({"schema_version": 1, "kind": "bridgeforge-bytecode-rules", "rules": [{"id": "fixture-method", "action": "remap-method-reference", "classification": "REVIEW", "description": "fixture", "owner": "java/lang/Math", "name": "abs", "descriptor": "(I)I", "opcode": 184, "replacement_owner": "example/Math", "replacement_name": "abs", "replacement_descriptor": "(I)I", "expected_matches": 1, "evidence": evidence}]}), encoding="utf-8")
            method_plan = plan_bytecode([root / "Fixture.class"], method_rules)
            self.assertEqual(len(method_plan["planned"]), 1)
            rewritten = root / "Fixture.rewritten.class"
            self.assertEqual(rewrite_class(root / "Fixture.class", rewritten, load_bytecode_rules(method_rules)[0]), 1)
            diff = diff_bytecode([root / "Fixture.class"], [rewritten])
            self.assertEqual(len(diff["changed_classes"]), 1)
            self.assertTrue(diff["changed_classes"][0]["invariants"]["same_reference_shape"])
            applied = apply_bytecode_class(root / "Fixture.class", root / "Fixture.output.class", method_rules, {"fixture-method"})
            self.assertEqual(applied["mode"], "REVIEW_APPLIED_TO_OUTPUT_COPY")

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

    def test_refuses_artifacts_inside_original_mod(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = scan_mod(root)
            with self.assertRaises(ValueError):
                write_artifacts(result, root / "artifacts")

    def test_scanner_reports_wrapper_directory_layout_without_retargeting_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wrapped = root / "release-wrapper" / "actual-mod"
            wrapped.mkdir(parents=True)
            (wrapped / "mod_info.json").write_text("{}", encoding="utf-8")
            result = scan_mod(root / "release-wrapper")
            self.assertTrue(any(finding.id == "missing-mod-info" for finding in result.findings))
            self.assertTrue(any(finding.id == "wrapper-directory-layout" and finding.classification == "REVIEW" for finding in result.findings))

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
            (source / "Example.java").write_text('class Example { String note = "😀"; void x() { OldApi.foo(); } }', encoding="utf-8")
            pack = root / "methods.json"
            pack.write_text(json.dumps({"pack": {"id": "fixture-utf16", "schema_version": 1}, "rules": [{"id": "migrate-utf16", "classification": "REVIEW", "confidence": "DETERMINISTIC", "description": "fixture", "action": "replace-method-invocation", "from_invocation": "OldApi.foo", "to_invocation": "NewApi.bar"}]}), encoding="utf-8")
            workspace = create_workspace(source, root / "workspace")
            build_plan(workspace, TargetProfile(), [pack])
            apply_plan(workspace, {"migrate-utf16"})
            _, working, _ = workspace_paths(workspace)
            self.assertIn("NewApi.bar();", (working / "Example.java").read_text(encoding="utf-8"))

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

    def test_bundled_pack_registry_is_unique_and_conservative(self) -> None:
        packs = discover_packs()
        self.assertGreaterEqual(len(packs), 8)
        self.assertEqual(len({pack.id for pack in packs}), len(packs))
        self.assertTrue(all(pack.status == "SCAFFOLDED" for pack in packs))
        self.assertEqual(resolve_pack_rule_paths(["java"]), [])

    def test_pack_version_compatibility_is_enforced(self) -> None:
        self.assertEqual(BRIDGEFORGE_VERSION, __version__)
        alpha_pack = MigrationPack("alpha", "alpha", "test", "SCAFFOLDED", None, Path("."), min_bridgeforge_version="0.1.0a1")
        final_pack = MigrationPack("final", "final", "test", "SCAFFOLDED", None, Path("."), min_bridgeforge_version="0.1.0")
        later_pack = MigrationPack("later", "later", "test", "SCAFFOLDED", None, Path("."), min_bridgeforge_version="0.1.1")
        self.assertTrue(compatible(alpha_pack))
        self.assertTrue(compatible(final_pack))
        self.assertFalse(compatible(later_pack))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pack = root / "future"
            pack.mkdir()
            (pack / "pack.json").write_text(json.dumps({"schema_version": 1, "id": "future", "name": "future", "scope": "test", "status": "SCAFFOLDED", "min_bridgeforge_version": "2.0.0"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                resolve_pack_rule_paths(["future"], root)

    def test_library_migration_rules_require_verified_evidence_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rules.json"
            base = {"id": "library-rule", "classification": "REVIEW", "confidence": "HIGH", "description": "fixture", "file": "mod_info.json", "json_key": "gameVersion", "value_from_target": "starsector"}
            path.write_text(json.dumps({"pack": {"schema_version": 1, "id": "magiclib"}, "rules": [base]}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_rules([path])
            base["evidence"] = {field: "verified" for field in ("provenance", "before_fixture", "after_fixture", "compile_validation", "idempotence", "conflict_review", "save_risk_assessment")}
            path.write_text(json.dumps({"pack": {"schema_version": 1, "id": "magiclib"}, "rules": [base]}), encoding="utf-8")
            self.assertEqual(load_rules([path])[0].id, "library-rule")

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

    def test_apply_preflights_all_changes_and_blocks_manual_rules(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "mod_info.json").write_text(json.dumps({"gameVersion": "0.95"}), encoding="utf-8")
            workspace = create_workspace(source, root / "workspace")
            plan = build_plan(workspace, TargetProfile("0.98", 17))
            plan["migrations"][0]["classification"] = "MANUAL"
            (workspace / "migration-plan.json").write_text(json.dumps(plan), encoding="utf-8")
            self.assertEqual(len(apply_plan(workspace, {"metadata-target-starsector-version"})["applied"]), 0)

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

    def test_apply_recovers_every_file_after_a_later_write_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "one.json").write_text(json.dumps({"one": "old"}), encoding="utf-8")
            (source / "two.json").write_text(json.dumps({"two": "old"}), encoding="utf-8")
            rules = root / "rules.json"
            rules.write_text(json.dumps({"pack": {"schema_version": 1, "id": "fault-test"}, "rules": [
                {"id": "one", "classification": "SAFE", "confidence": "HIGH", "description": "one", "file": "one.json", "json_key": "one", "value_from_target": "starsector"},
                {"id": "two", "classification": "SAFE", "confidence": "HIGH", "description": "two", "file": "two.json", "json_key": "two", "value_from_target": "starsector"}
            ]}), encoding="utf-8")
            workspace = create_workspace(source, root / "workspace")
            build_plan(workspace, TargetProfile("0.98", 17), [rules])
            import os
            real_replace = os.replace

            def fail_second_temp_replace(source_path: str | Path, destination_path: str | Path) -> None:
                if str(source_path).endswith("two.json.bridgeforge-tmp"):
                    raise OSError("simulated disk failure")
                real_replace(source_path, destination_path)

            with patch("bridgeforge.migrate.os.replace", side_effect=fail_second_temp_replace):
                with self.assertRaises(OSError):
                    apply_plan(workspace, {"one", "two"})
            self.assertEqual(json.loads((workspace / "working-copy" / "one.json").read_text(encoding="utf-8"))["one"], "old")
            self.assertEqual(json.loads((workspace / "working-copy" / "two.json").read_text(encoding="utf-8"))["two"], "old")

    def test_scanner_enforces_jar_limits_before_reading_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text("{}", encoding="utf-8")
            with zipfile.ZipFile(root / "large.jar", "w") as archive:
                archive.writestr("Example.class", b"x" * 20)
            prior = scanner.MAX_JAR_UNCOMPRESSED_BYTES
            scanner.MAX_JAR_UNCOMPRESSED_BYTES = 10
            try:
                result = scan_mod(root)
            finally:
                scanner.MAX_JAR_UNCOMPRESSED_BYTES = prior
            self.assertTrue(any(finding.id == "jar-scan-limit" for finding in result.findings))

    def test_scanner_rejects_compression_bombs_and_archive_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text("{}", encoding="utf-8")
            with zipfile.ZipFile(root / "compressed.jar", "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("Example.class", b"x" * 10_000)
            prior_ratio = scanner.MAX_JAR_COMPRESSION_RATIO
            scanner.MAX_JAR_COMPRESSION_RATIO = 2
            try:
                result = scan_mod(root)
            finally:
                scanner.MAX_JAR_COMPRESSION_RATIO = prior_ratio
            self.assertTrue(any(finding.id == "jar-scan-limit" for finding in result.findings))
            with zipfile.ZipFile(root / "traversal.jar", "w") as archive:
                archive.writestr("../Escape.class", b"\xca\xfe\xba\xbe\x00\x00\x00\x34")
            result = scan_mod(root)
            self.assertTrue(any(finding.id == "jar-path-traversal" for finding in result.findings))

    def test_scanner_reports_trailing_comma_json_as_review_without_rewriting_strings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text('{"id": "fixture", "gameVersion": "0.98",}', encoding="utf-8")
            (root / "legacy.json").write_text('{"literal": ",}", "enabled": true,}', encoding="utf-8")
            result = scan_mod(root)
            non_strict = [finding for finding in result.findings if finding.id == "non-strict-json-trailing-comma"]
            self.assertEqual(len(non_strict), 2)
            self.assertFalse(any(finding.id in {"unverified-mod-info-syntax", "unverified-json-syntax", "version-inference-blocked"} for finding in result.findings))

    def test_scanner_separates_encoding_and_structural_ambiguity_from_breakage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text("{}", encoding="utf-8")
            (root / "legacy.csv").write_bytes(b"id,name\n1,\x92legacy\n")
            (root / "src").mkdir()
            source = "class Duplicate {}"
            (root / "src" / "One.java").write_text(source, encoding="utf-8")
            (root / "src" / "Two.java").write_text(source, encoding="utf-8")
            with zipfile.ZipFile(root / "large.jar", "w") as archive:
                archive.writestr("Example.class", b"\xca\xfe\xba\xbe\x00\x00\x00\x34")
            prior_limit = scanner.LARGE_BUNDLED_JAR_BYTES
            scanner.LARGE_BUNDLED_JAR_BYTES = 1
            try:
                result = scan_mod(root)
            finally:
                scanner.LARGE_BUNDLED_JAR_BYTES = prior_limit
            self.assertTrue(any(finding.id == "csv-encoding-unverified" for finding in result.findings))
            self.assertTrue(any(finding.id == "duplicate-source-layout" for finding in result.findings))
            self.assertTrue(any(finding.id == "large-bundled-archive" for finding in result.findings))

    def test_scanner_keeps_unreadable_json_separate_from_parser_tolerance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text("{}", encoding="utf-8")
            bad_json = root / "unreadable.json"
            bad_json.write_text("{}", encoding="utf-8")
            original_read_text = Path.read_text

            def read_text(path: Path, *args: object, **kwargs: object) -> str:
                if path.name == bad_json.name:
                    raise OSError("fixture access denied")
                return original_read_text(path, *args, **kwargs)

            with patch.object(Path, "read_text", read_text):
                result = scan_mod(root)
            self.assertTrue(any(finding.id == "unreadable-json" for finding in result.findings))
            self.assertFalse(any(finding.id == "unverified-json-syntax" for finding in result.findings))

    def test_scanner_hashes_duplicate_sources_as_raw_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text("{}", encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "One.java").write_bytes(b"class Source { // \x80\n }")
            (root / "src" / "Two.java").write_bytes(b"class Source { // \x81\n }")
            result = scan_mod(root)
            self.assertFalse(any(finding.id == "duplicate-source-layout" for finding in result.findings))

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
