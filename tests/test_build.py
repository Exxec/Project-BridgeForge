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



class BuildTests(unittest.TestCase):
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


    def test_build_profile_includes_active_data_sources_but_excludes_disabled_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            (source / "data" / "hullmods").mkdir(parents=True)
            (source / "disabled_files").mkdir()
            (source / "mod_info.json").write_text("{}", encoding="utf-8")
            (source / "data" / "hullmods" / "Active.java").write_text("class Active {}", encoding="utf-8")
            (source / "disabled_files" / "Disabled.java").write_text("class Disabled {}", encoding="utf-8")
            workspace = create_workspace(source, root / "workspace")
            profile = create_build_profile(workspace, TargetProfile("0.98a", 17), None, [], [])
            self.assertEqual(profile.source_roots, ["data/hullmods"])
            self.assertIn(str(workspace / "working-copy" / "data" / "hullmods" / "Active.java"), profile.command_preview)
            self.assertNotIn(str(workspace / "working-copy" / "disabled_files" / "Disabled.java"), profile.command_preview)


    def test_build_profile_records_explicit_starsector_install_classpath(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "mod_info.json").write_text("{}", encoding="utf-8")
            install = root / "starsector"
            core = install / "starsector-core"
            core.mkdir(parents=True)
            for name in ("starfarer.api.jar", "log4j-1.2.9.jar", "ignored-sources.jar"):
                with zipfile.ZipFile(core / name, "w") as archive:
                    archive.writestr("marker.txt", name)
            workspace = create_workspace(source, root / "workspace")
            profile = create_build_profile(workspace, TargetProfile("0.98a", 17), None, [], [], starsector_install=install)
            self.assertEqual(profile.starsector_install["mode"], "EXPLICIT_LOCAL_STARSECTOR_INSTALL")
            self.assertEqual(len(profile.starsector_install["jars"]), 2)
            self.assertTrue(any(item.endswith("log4j-1.2.9.jar") for item in profile.api_jars))


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


    def test_library_registry_rejects_invalid_schema_and_missing_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bad_schema = root / "bad-schema.json"
            bad_schema.write_text(json.dumps({"schema_version": 2, "libraries": {}}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_library_registry(bad_schema)
            bad_entry = root / "bad-entry.json"
            bad_entry.write_text(json.dumps({"schema_version": 1, "libraries": {"lw_lazylib": {}}}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_library_registry(bad_entry)


    def test_library_registry_loads_valid_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry_path = root / "libraries.json"
            registry_path.write_text(json.dumps({"schema_version": 1, "libraries": {"lw_lazylib": {"path": "C:/lazylib/LazyLib.jar", "note": "LazyLib 3.0.0"}}}), encoding="utf-8")
            registry = load_library_registry(registry_path)
            self.assertEqual(registry["lw_lazylib"], LibraryRegistryEntry("lw_lazylib", "C:/lazylib/LazyLib.jar", "LazyLib 3.0.0"))


    def test_resolve_registered_dependency_jars_warns_without_a_registry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "mod_info.json").write_text(json.dumps({"id": "fixture", "gameVersion": "0.98", "dependencies": [{"id": "lw_lazylib", "name": "LazyLib"}]}), encoding="utf-8")
            resolved, findings = resolve_registered_dependency_jars(source, TargetProfile("0.98", 17), None)
            self.assertEqual(resolved, [])
            self.assertEqual(findings[0]["id"], "declared-dependency-unregistered")
            self.assertIn("no --library-registry was supplied", findings[0]["explanation"])


    def test_resolve_registered_dependency_jars_warns_on_unregistered_id_and_missing_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "mod_info.json").write_text(json.dumps({"id": "fixture", "gameVersion": "0.98", "dependencies": [{"id": "lw_lazylib", "name": "LazyLib"}, {"id": "org_magiclib", "name": "MagicLib"}]}), encoding="utf-8")
            registry = {"org_magiclib": LibraryRegistryEntry("org_magiclib", str(root / "does-not-exist.jar"))}
            resolved, findings = resolve_registered_dependency_jars(source, TargetProfile("0.98", 17), registry)
            self.assertEqual(resolved, [])
            findings_by_id = {finding["library_id"]: finding for finding in findings}
            self.assertIn("no entry for it", findings_by_id["lw_lazylib"]["explanation"])
            self.assertIn("no longer exists on disk", findings_by_id["org_magiclib"]["explanation"])


    def test_resolve_registered_dependency_jars_resolves_a_real_local_jar(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "mod_info.json").write_text(json.dumps({"id": "fixture", "gameVersion": "0.98", "dependencies": [{"id": "lw_lazylib", "name": "LazyLib"}]}), encoding="utf-8")
            real_jar = root / "LazyLib.jar"
            with zipfile.ZipFile(real_jar, "w") as archive:
                archive.writestr("marker.txt", "lazylib")
            registry = {"lw_lazylib": LibraryRegistryEntry("lw_lazylib", str(real_jar))}
            resolved, findings = resolve_registered_dependency_jars(source, TargetProfile("0.98", 17), registry)
            self.assertEqual(resolved, [real_jar])
            self.assertEqual(findings, [])


    def test_build_profile_auto_resolves_declared_dependency_via_registry(self) -> None:
        javac = shutil.which("javac")
        if not javac:
            self.skipTest("JDK compiler unavailable")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            (source / "src").mkdir(parents=True)
            (source / "mod_info.json").write_text(json.dumps({"id": "fixture", "gameVersion": "0.98", "dependencies": [{"id": "lw_lazylib", "name": "LazyLib"}]}), encoding="utf-8")
            (source / "src" / "Example.java").write_text("class Example {}", encoding="utf-8")
            workspace = create_workspace(source, root / "workspace")
            real_jar = root / "LazyLib.jar"
            with zipfile.ZipFile(real_jar, "w") as archive:
                archive.writestr("marker.txt", "lazylib")
            registry = {"lw_lazylib": LibraryRegistryEntry("lw_lazylib", str(real_jar))}
            profile = create_build_profile(workspace, TargetProfile("0.98", 17), Path(javac).parent.parent, [], [], registry)
            self.assertEqual(profile.compile_validation["status"], "AVAILABLE")
            self.assertIn(str(real_jar.resolve()), profile.dependency_jars)


    def test_build_profile_prefers_explicit_dependency_jar_over_registry_without_duplicating(self) -> None:
        javac = shutil.which("javac")
        if not javac:
            self.skipTest("JDK compiler unavailable")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            (source / "src").mkdir(parents=True)
            (source / "mod_info.json").write_text(json.dumps({"id": "fixture", "gameVersion": "0.98", "dependencies": [{"id": "lw_lazylib", "name": "LazyLib"}]}), encoding="utf-8")
            (source / "src" / "Example.java").write_text("class Example {}", encoding="utf-8")
            workspace = create_workspace(source, root / "workspace")
            real_jar = root / "LazyLib.jar"
            with zipfile.ZipFile(real_jar, "w") as archive:
                archive.writestr("marker.txt", "lazylib")
            registry = {"lw_lazylib": LibraryRegistryEntry("lw_lazylib", str(real_jar))}
            profile = create_build_profile(workspace, TargetProfile("0.98", 17), Path(javac).parent.parent, [], [real_jar], registry)
            self.assertEqual(profile.dependency_jars, [str(real_jar.resolve())])


    def test_build_profile_reports_duplicate_compile_classpath_classes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "mod_info.json").write_text("{}", encoding="utf-8")
            first, second = root / "first.jar", root / "second.jar"
            for jar in (first, second):
                with zipfile.ZipFile(jar, "w") as archive:
                    archive.writestr("shared/Thing.class", b"\xca\xfe\xba\xbe")
            workspace = create_workspace(source, root / "workspace")
            profile = create_build_profile(workspace, TargetProfile("0.98", 17), None, [first], [second])
            finding = next(item for item in profile.compile_validation["findings"] if item["id"] == "compile-classpath-duplicate-class")
            self.assertEqual(profile.compile_validation["status"], "AVAILABLE")
            self.assertEqual(finding["class"], "shared/Thing.class")
            self.assertEqual(profile.dependency_provenance[0]["jar"], str(second.resolve()))
            self.assertEqual(len(profile.dependency_provenance[0]["sha256"]), 64)
            self.assertEqual(profile.compile_validation["status"], "AVAILABLE")


    def test_package_compiled_jar_writes_output_copy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            (source / "jar").mkdir(parents=True)
            (source / "mod_info.json").write_text("{}", encoding="utf-8")
            with zipfile.ZipFile(source / "jar" / "fixture.jar", "w") as archive:
                archive.writestr("keep.txt", b"keep")
            workspace = create_workspace(source, root / "workspace")
            classes = workspace / "build" / "classes"
            (classes / "data").mkdir(parents=True)
            (classes / "data" / "Fixture.class").write_bytes(b"\xca\xfe\xba\xbe\x00\x00\x00\x34")
            (workspace / "build-result.json").write_text(json.dumps({"success": True}), encoding="utf-8")
            result = package_compiled_jar(workspace, "jar/fixture.jar")
            repeat = package_compiled_jar(workspace, "jar/fixture.jar", "repeat.jar")
            with zipfile.ZipFile(result["output"]) as archive:
                self.assertEqual(archive.read("keep.txt"), b"keep")
                self.assertEqual(archive.read("data/Fixture.class"), b"\xca\xfe\xba\xbe\x00\x00\x00\x34")
            self.assertTrue(result["input_preserved"])
            self.assertEqual(Path(result["output"]).read_bytes(), Path(repeat["output"]).read_bytes())


