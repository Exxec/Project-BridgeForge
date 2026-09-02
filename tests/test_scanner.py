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
from bridgeforge.cross_mod import analyze_mod_set
from bridgeforge.identity_registry import build_campaign_identity_inventory, check_campaign_identity_references
from bridgeforge.decompiler import create_decompiler_review, run_decompiler_review
from bridgeforge.lineage import analyze_release_lineage
from bridgeforge.archive_intake import inspect_zip_archive, stage_zip_archive
from bridgeforge.library_api import check_dependency_apis, inventory_library_api, match_library_imports
from bridgeforge.cli import main



class ScannerTests(unittest.TestCase):
    def test_corpus_audit_is_deterministic_and_path_minimal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            alpha, beta = root / "Alpha", root / "Beta"
            alpha.mkdir()
            beta.mkdir()
            (alpha / "mod_info.json").write_text('{"id":"alpha","gameVersion":"0.98"}', encoding="utf-8")
            (beta / "mod_info.json").write_text('{"id":"beta","gameVersion":"0.95",}', encoding="utf-8")
            (beta / "disabled_files").mkdir()
            (beta / "disabled_files" / "Old.java").write_text("class Old {}", encoding="utf-8")
            (beta / "jars" / "sources").mkdir(parents=True)
            (beta / "jars" / "sources" / "Bundled.java").write_text("class Bundled {}", encoding="utf-8")
            report = audit_directories([beta, alpha, alpha], TargetProfile("0.98", 17))
            self.assertEqual(report["mode"], "READ_ONLY_CORPUS_AUDIT")
            self.assertEqual([row["mod"] for row in report["mods"]], ["Alpha", "Beta"])
            self.assertEqual(report["duplicate_input_count"], 1)
            self.assertEqual(report["mods"][0]["audit_status"], "AVAILABLE")
            self.assertEqual(report["finding_counts"]["non-strict-json-trailing-comma"], 1)
            beta_row = next(row for row in report["mods"] if row["mod"] == "Beta")
            self.assertEqual(beta_row["source_layout"]["disabled_java_file_count"], 1)
            self.assertEqual(beta_row["source_layout"]["bundled_or_archive_java_file_count"], 1)
            self.assertNotIn(str(root), __import__("json").dumps(report))
            output = write_corpus_audit(report, root / "audit.json", [alpha, beta])
            self.assertEqual(__import__("json").loads(output.read_text(encoding="utf-8"))["mod_count"], 2)
            with self.assertRaises(ValueError):
                write_corpus_audit(report, alpha / "audit.json", [alpha, beta])
            degraded = audit_directories([alpha, root / "missing"], TargetProfile(), continue_on_error=True)
            self.assertEqual(degraded["unavailable_mod_count"], 1)

    def test_cross_mod_analysis_resolves_selected_dependencies_classes_and_campaign_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            alpha, beta = root / "Alpha", root / "Beta"
            for mod, metadata, source in (
                (alpha, '{"id":"alpha"}', 'package data.shared; class Same { void f() { createStarSystem("alpha_system"); } }'),
                (beta, '{"id":"beta","dependencies":["alpha"]}', 'package data.shared; class Same { void f() { getStarSystem("alpha_system"); } }'),
            ):
                (mod / "src").mkdir(parents=True)
                (mod / "mod_info.json").write_text(metadata, encoding="utf-8")
                (mod / "src" / "Example.java").write_text(source, encoding="utf-8")
            report = analyze_mod_set([beta, alpha, alpha], TargetProfile())
            self.assertEqual(report["mod_count"], 2)
            self.assertEqual(report["duplicate_input_count"], 1)
            self.assertEqual(report["dependency_edges"][0]["status"], "RESOLVED_IN_SELECTED_SET")
            self.assertEqual(report["duplicate_class_ownership"], [{"class": "data.shared.Same", "owners": ["Alpha", "Beta"]}])
            lookup = report["campaign_lookup_resolution"][0]
            self.assertEqual(lookup["status"], "RESOLVED_BY_SELECTED_MOD")
            self.assertNotIn(str(root), json.dumps(report))

    def test_cross_mod_analysis_uses_explicit_alias_for_unavailable_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer, legacy = root / "Consumer", root / "LegacyLibrary"
            consumer.mkdir()
            legacy.mkdir()
            (consumer / "mod_info.json").write_text('{"id":"consumer","dependencies":["LegacyLib"]}', encoding="utf-8")
            (legacy / "mod_info.json").write_text("{ invalid", encoding="utf-8")
            report = analyze_mod_set([consumer, legacy], TargetProfile(), {"LegacyLibrary": "LegacyLib"})
            library = next(item for item in report["mods"] if item["mod"] == "LegacyLibrary")
            self.assertEqual(library["identity_source"], "EXPLICIT_ALIAS")
            self.assertEqual(report["dependency_edges"][0]["status"], "RESOLVED_IN_SELECTED_SET")

    def test_campaign_identity_inventory_and_check_are_explicit_and_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            owner, consumer = root / "Owner", root / "Consumer"
            for mod, source in (
                (owner, 'class Owner { void f() { createStarSystem("owner_system"); addCustomEntity("owner_entity", "N", "T", "f"); } }'),
                (consumer, 'class Consumer { void f() { getStarSystem("owner_system"); getEntityById("owner_entity"); getStarSystem("Askonia"); } }'),
            ):
                (mod / "src").mkdir(parents=True)
                (mod / "mod_info.json").write_text('{"id":"' + mod.name.lower() + '"}', encoding="utf-8")
                (mod / "src" / "Example.java").write_text(source, encoding="utf-8")
            inventory = build_campaign_identity_inventory([owner], TargetProfile())
            self.assertEqual([(item["kind"], item["id"]) for item in inventory["entries"]], [("entity", "owner_entity"), ("system", "owner_system")])
            result = check_campaign_identity_references(consumer, inventory, TargetProfile())
            statuses = {item["id"]: item["status"] for item in result["checks"]}
            self.assertEqual(statuses["owner_system"], "RESOLVED_EXPLICIT_REGISTRY")
            self.assertEqual(statuses["owner_entity"], "RESOLVED_EXPLICIT_REGISTRY")
            self.assertEqual(statuses["Askonia"], "NOT_IN_EXPLICIT_REGISTRY")

    def test_decompiler_review_requires_explicit_execution_and_marks_output_untrusted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "legacy.class"
            source.write_bytes(b"\xca\xfe\xba\xbe")
            output = root / "review"
            plan = create_decompiler_review(
                source,
                output,
                Path(__import__("sys").executable),
                ["-c", "from pathlib import Path; Path(r'{output}/Recovered.java').write_text('class Recovered {}')", "{input}", "{output}"],
            )
            self.assertTrue((output / "decompiler-review-plan.json").is_file())
            self.assertEqual(run_decompiler_review(output)["status"], "NOT_EXECUTED")
            result = run_decompiler_review(output, execute=True)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["mode"], "DECOMPILER_OUTPUT_UNTRUSTED_REVIEW_ONLY")
            self.assertTrue((output / "decompiled" / "Recovered.java").is_file())
            self.assertEqual(source.read_bytes(), b"\xca\xfe\xba\xbe")
            self.assertEqual(plan["input"]["name"], "legacy.class")

    def test_release_lineage_preserves_user_order_and_reports_transition_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second, third = root / "v1", root / "v2", root / "v3"
            for release, version, body in ((first, "0.95", "one"), (second, "0.96", "two"), (third, "0.98", "two")):
                release.mkdir()
                (release / "mod_info.json").write_text('{"id":"fixture","gameVersion":"' + version + '"}', encoding="utf-8")
                (release / "content.txt").write_text(body, encoding="utf-8")
            report = analyze_release_lineage([first, second, third], TargetProfile())
            self.assertEqual(report["mode"], "READ_ONLY_RELEASE_LINEAGE")
            self.assertEqual([item["release"] for item in report["releases"]], ["v1", "v2", "v3"])
            self.assertEqual(len(report["transitions"]), 2)
            self.assertEqual(report["transitions"][0]["content"]["changed_file_count"], 2)
            self.assertEqual(report["transitions"][1]["content"]["changed_file_count"], 1)


    def test_zip_preflight_rejects_path_traversal_without_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "fixture.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("../escape/mod_info.json", "{}")
            result = inspect_zip_archive(archive)
            self.assertFalse(result["safe_to_extract"])
            self.assertEqual(result["findings"][0]["id"], "archive-path-traversal")


    def test_zip_preflight_flags_symlinks_and_duplicate_extraction_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "fixture.zip"
            link = zipfile.ZipInfo("link")
            link.external_attr = 0o120777 << 16
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                with zipfile.ZipFile(archive, "w") as bundle:
                    bundle.writestr(link, "target")
                    bundle.writestr("nested\\mod_info.json", "{}")
                    bundle.writestr("nested/mod_info.json", "{}")
            findings = {item["id"] for item in inspect_zip_archive(archive)["findings"]}
            self.assertTrue({"archive-symlink-member", "archive-duplicate-member"}.issubset(findings))


    def test_zip_preflight_reports_wrapper_and_stages_only_to_empty_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive, staged = root / "fixture.zip", root / "staged"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("Wrapper/mod_info.json", "{}")
                bundle.writestr("Wrapper/data/value.txt", "ok")
            report = inspect_zip_archive(archive)
            self.assertTrue(report["safe_to_stage"])
            self.assertEqual(report["candidate_mod_roots"], ["Wrapper"])
            self.assertIn("archive-wrapper-directory-layout", {item["id"] for item in report["findings"]})
            self.assertEqual(stage_zip_archive(archive, staged), staged.resolve())
            self.assertEqual((staged / "Wrapper" / "data" / "value.txt").read_text(encoding="utf-8"), "ok")
            with self.assertRaises(ValueError):
                stage_zip_archive(archive, staged)


    def test_preflight_and_inventory_cli_never_replace_input_archives(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "fixture.zip"
            jar = Path(directory) / "fixture.jar"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("mod_info.json", "{}")
            with zipfile.ZipFile(jar, "w") as bundle:
                bundle.writestr("sample/Api.class", b"\xca\xfe\xba\xbe")
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(["archive-preflight", str(archive), "--output", str(archive)]), 2)
                self.assertEqual(main(["library-api-inventory", str(jar), "--output", str(jar)]), 2)
            self.assertTrue(zipfile.is_zipfile(archive))
            self.assertTrue(zipfile.is_zipfile(jar))


    def test_library_api_inventory_and_match_are_review_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            jar = root / "LazyLib.jar"
            with zipfile.ZipFile(jar, "w") as archive:
                archive.writestr("org/lazywizard/lazylib/MathUtils.class", b"\xca\xfe\xba\xbe")
            mod = root / "mod"
            (mod / "src").mkdir(parents=True)
            (mod / "mod_info.json").write_text("{}", encoding="utf-8")
            (mod / "src" / "Example.java").write_text("import org.lazywizard.lazylib.MathUtils; import com.fs.starfarer.api.Global; class Example { void f() { MathUtils.getDistance(); } }", encoding="utf-8")
            inventory = inventory_library_api(jar, "LazyLib", "2.0")
            match = match_library_imports(mod, inventory, TargetProfile())
            self.assertEqual(inventory["class_count"], 1)
            self.assertEqual(match["unmatched_imports"], [])
            self.assertEqual(match["inventory_namespace"], "org.lazywizard.lazylib")
            self.assertEqual(match["inventory_packages"], ["org.lazywizard.lazylib"])
            self.assertEqual(match["inventory_identity"]["library_id"], "LazyLib")
            self.assertEqual(match["migration_candidates"][0]["mode"], "RESEARCH_CANDIDATE_ONLY")


    def test_library_api_match_marks_wildcards_reflection_and_unknown_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, jar = Path(directory), Path(directory) / "api.jar"
            with zipfile.ZipFile(jar, "w") as archive:
                archive.writestr("org/example/Api.class", b"\xca\xfe\xba\xbe")
            mod = root / "mod"
            (mod / "src").mkdir(parents=True)
            (mod / "mod_info.json").write_text("{}", encoding="utf-8")
            (mod / "src" / "Example.java").write_text("import org.example.*; class Example { void f() throws Exception { Class.forName(\"org.example.Api\"); } }", encoding="utf-8")
            result = match_library_imports(mod, inventory_library_api(jar), TargetProfile())
            self.assertEqual({item["id"] for item in result["uncertainty_findings"]}, {"library-api-wildcard-import", "library-api-reflection-uncertain", "library-api-identity-unknown", "library-api-version-unknown"})

    def test_dependency_api_check_uses_only_explicit_matching_inventories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            magic_jar = root / "magic.jar"
            with zipfile.ZipFile(magic_jar, "w") as archive:
                archive.writestr("data/scripts/util/MagicRender.class", b"\xca\xfe\xba\xbe")
            mod = root / "mod"
            (mod / "src").mkdir(parents=True)
            (mod / "mod_info.json").write_text('{"dependencies":["MagicLib"]}', encoding="utf-8")
            (mod / "data").mkdir()
            (mod / "data" / "plugins.json").write_text('{"script":"data.scripts.util.MagicRender"}', encoding="utf-8")
            (mod / "src" / "Example.java").write_text(
                "import data.scripts.util.MagicRender; import org.lazywizard.console.Console; class Example {}",
                encoding="utf-8",
            )
            result = check_dependency_apis(mod, [inventory_library_api(magic_jar, "MagicLib", "0.48")], TargetProfile())
            checks = {item["dependency"]: item for item in result["checks"]}
            self.assertEqual(checks["MagicLib"]["status"], "IMPORT_CLASSES_PRESENT")
            self.assertTrue(checks["MagicLib"]["declared"])
            self.assertEqual(checks["Console Commands"]["status"], "NO_MATCHING_LOCAL_INVENTORY")
            self.assertEqual(result["configured_class_checks"][0]["status"], "PRESENT_IN_EXPLICIT_INVENTORY")

    def test_dependency_api_check_compares_unambiguous_imported_method_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mod = root / "mod"
            (mod / "src").mkdir(parents=True)
            (mod / "mod_info.json").write_text("{}", encoding="utf-8")
            (mod / "src" / "Example.java").write_text(
                "import data.scripts.util.MagicRender; class Example { void f() { MagicRender.draw(); MagicRender.missing(); } }",
                encoding="utf-8",
            )
            inventory = {"classes": ["data.scripts.util.MagicRender"], "method_symbol_status": "AVAILABLE", "method_symbols": ["data.scripts.util.MagicRender#draw"], "identity": {"library_id": "MagicLib", "version": "fixture"}, "sha256": "fixture"}
            result = check_dependency_apis(mod, [inventory], TargetProfile())
            checks = result["checks"][0]["method_checks"]
            self.assertEqual(checks, [{"class": "data.scripts.util.MagicRender", "method": "draw", "status": "METHOD_NAME_PRESENT"}, {"class": "data.scripts.util.MagicRender", "method": "missing", "status": "METHOD_NAME_MISSING"}])


    def test_corpus_audit_skips_declared_budget_excess(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod = Path(directory) / "mod"
            mod.mkdir()
            (mod / "mod_info.json").write_text("{}", encoding="utf-8")
            report = audit_directories([mod], TargetProfile(), max_files_per_mod=0)
            self.assertEqual(report["mods"][0]["audit_status"], "SKIPPED_BUDGET")
            self.assertEqual(report["skipped_budget_mod_count"], 1)

    def test_scanner_reports_missing_configured_classes_and_library_usage_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text(json.dumps({"id": "fixture", "dependencies": ["LazyLib"]}), encoding="utf-8")
            (root / "data" / "hullmods").mkdir(parents=True)
            (root / "data" / "hullmods" / "Local.java").write_text("package data.hullmods; import org.lazywizard.lazylib.MathUtils; public class Local { void x() { MathUtils.getRandomNumberInRange(1, 2); } }", encoding="utf-8")
            (root / "data" / "hullmods" / "hull_mods.csv").write_text("script\ndata.hullmods.Local\n", encoding="utf-8")
            with zipfile.ZipFile(root / "fixture.jar", "w") as archive:
                archive.writestr("Example.class", b"\xca\xfe\xba\xbe\x00\x00\x00\x34org/lazywizard/lazylib")
            result = scan_mod(root)
            missing = next(finding for finding in result.findings if finding.id == "configured-source-class-missing-from-jar")
            self.assertEqual(missing.evidence, ["data.hullmods.Local"])
            lazy = next(item for item in result.library_usage if item["library"] == "LazyLib")
            self.assertTrue(lazy["declared"])
            self.assertTrue(lazy["imported"])
            self.assertTrue(lazy["source_called"])
            self.assertTrue(lazy["bytecode_referenced"])

    def test_scanner_attaches_packaging_and_reachability_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text('{"id":"fixture"}', encoding="utf-8")
            (root / "data" / "scripts").mkdir(parents=True)
            (root / "data" / "scripts" / "Plugin.java").write_text(
                "package data.scripts; public class Plugin { void init() { throw new UnsupportedOperationException(); } }",
                encoding="utf-8",
            )
            (root / "data" / "scripts" / "plugins.json").write_text('{"plugin":"data.scripts.Plugin"}', encoding="utf-8")
            result = scan_mod(root)
            context = result.migration_context["configured_class_integrity"]
            self.assertEqual(context["source_only"], ["data.scripts.Plugin"])
            self.assertEqual(context["configured_entrypoint_sources"], ["data/scripts/Plugin.java"])
            placeholder = next(item for item in result.findings if item.id == "runtime-placeholder-unsupported-operation")
            self.assertIn("reachability: configured-entrypoint", placeholder.evidence)

    def test_scanner_follows_unambiguous_local_call_from_configured_entrypoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text('{"id":"fixture"}', encoding="utf-8")
            (root / "data" / "scripts").mkdir(parents=True)
            (root / "data" / "scripts" / "Entry.java").write_text(
                "package data.scripts; public class Entry { void init() { Helper.run(); } }",
                encoding="utf-8",
            )
            (root / "data" / "scripts" / "Helper.java").write_text(
                "package data.scripts; public class Helper { static void run() { throw new UnsupportedOperationException(); } }",
                encoding="utf-8",
            )
            (root / "data" / "scripts" / "plugins.json").write_text('{"plugin":"data.scripts.Entry"}', encoding="utf-8")
            result = scan_mod(root)
            context = result.migration_context["source_reachability"]
            self.assertEqual(context["reachable_local_sources"], ["data/scripts/Entry.java", "data/scripts/Helper.java"])
            placeholder = next(item for item in result.findings if item.id == "runtime-placeholder-unsupported-operation")
            self.assertIn("reachability: reachable-local-call", placeholder.evidence)

    def test_scanner_attributes_local_campaign_identifiers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text('{"id":"fixture"}', encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "World.java").write_text(
                'class World { void generate() { createStarSystem("fixture_system"); addCustomEntity("fixture_entity", "N", "T", "f"); getStarSystem("fixture_system"); getEntityById("fixture_entity"); getStarSystem("Askonia"); } }',
                encoding="utf-8",
            )
            result = scan_mod(root)
            findings = {item.evidence[0]: item.evidence[-1] for item in result.findings if item.id.startswith("hard-coded-campaign-")}
            self.assertEqual(findings["fixture_system"], "ownership: defined-locally")
            self.assertEqual(findings["fixture_entity"], "ownership: defined-locally")
            self.assertEqual(findings["Askonia"], "ownership: external-or-core-unresolved")


    def test_scanner_reports_runtime_placeholders_in_source_and_compiled_classes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text("{}", encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "Placeholder.java").write_text(
                "class Placeholder { void callback() { throw new UnsupportedOperationException(); } }",
                encoding="utf-8",
            )
            with zipfile.ZipFile(root / "fixture.jar", "w") as archive:
                archive.writestr(
                    "example/Placeholder.class",
                    b"\xca\xfe\xba\xbe\x00\x00\x00\x34java/lang/UnsupportedOperationException",
                )
            result = scan_mod(root)
            findings = {finding.id for finding in result.findings}
            self.assertIn("runtime-placeholder-unsupported-operation", findings)
            self.assertIn("bytecode-runtime-placeholder-reference", findings)

    def test_scanner_reports_missing_target_levelup_plugin_contract_method(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text("{}", encoding="utf-8")
            (root / "data" / "scripts" / "plugins").mkdir(parents=True)
            source = root / "data" / "scripts" / "plugins" / "LevelupPluginImpl.java"
            source.write_text(
                "import com.fs.starfarer.api.plugins.LevelupPlugin; public class LevelupPluginImpl implements LevelupPlugin { public int getPointsAtLevel(int l) { return 1; } }",
                encoding="utf-8",
            )
            result = scan_mod(root)
            finding = next(item for item in result.findings if item.id == "target-interface-method-missing")
            self.assertEqual(finding.evidence, ["LevelupPlugin", "int getBonusXPUseMultAtMaxLevel()"])
            source.write_text(
                "import com.fs.starfarer.api.plugins.LevelupPlugin; public class LevelupPluginImpl implements LevelupPlugin { public int getBonusXPUseMultAtMaxLevel() { return 1; } }",
                encoding="utf-8",
            )
            self.assertFalse(any(item.id == "target-interface-method-missing" for item in scan_mod(root).findings))


    def test_scanner_reports_only_type_proven_lazylib_30_removals(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "data" / "scripts" / "Fixture.java"
            source.parent.mkdir(parents=True)
            source.write_text("""import org.lazywizard.lazylib.ui.LazyFont;
import org.lazywizard.lazylib.campaign.orbits.KeplerOrbit;
class Fixture { void test(LazyFont.DrawableString text, LazyFont font, Object unknown) { text.appendText(\"x\"); text.setColor(null); text.getColor(); text.checkRebuild(); font.drawText(\"x\", 0f, 0f, 1f, 1f, 1f); unknown.appendText(\"x\"); } }""", encoding="utf-8")
            findings = {item.id: item for item in scan_mod(root).findings}
            self.assertEqual(findings["lazylib-drawable-string-appendText"].classification, "REVIEW")
            self.assertIn("lazylib-drawable-string-setColor", findings)
            self.assertIn("lazylib-drawable-string-getColor", findings)
            self.assertIn("lazylib-drawable-string-checkRebuild", findings)
            self.assertEqual(findings["lazylib-lazy-font-draw-text"].classification, "MANUAL")
            self.assertEqual(findings["lazylib-kepler-orbit-removed"].classification, "MANUAL")
            self.assertEqual(len([item for item in findings if item == "lazylib-drawable-string-appendText"]), 1)

    def test_scanner_records_ashlib_evidence_without_inferring_a_rewrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text('{"id":"fixture"}', encoding="utf-8")
            (root / "ashlib.version").write_text('{"modVersion":{"major":2,"minor":2,"patch":3}}', encoding="utf-8")
            source = root / "data" / "scripts" / "Fixture.java"
            source.parent.mkdir(parents=True)
            source.write_text("import ashlib.data.plugins.misc.AshMisc; class Fixture {}", encoding="utf-8")
            findings = {item.id: item for item in scan_mod(root).findings}
            self.assertEqual(findings["ashlib-version-evidence"].evidence, ["2.2.3"])
            self.assertEqual(findings["ashlib-api-usage"].classification, "SAFE")
            self.assertFalse(any("candidate" in item.id for item in findings.values()))

    def test_scanner_reports_graphicslib_98a_removals_as_manual_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text('{"id":"fixture"}', encoding="utf-8")
            (root / "shaderlib.version").write_text('{"modVersion":{"major":1,"minor":10,"patch":0}}', encoding="utf-8")
            config = root / "data" / "config"
            config.mkdir(parents=True)
            (config / "no_self_destruct.csv").write_text("id\nfixture_missile\n", encoding="utf-8")
            (root / "shaderSettings.json").write_text('{"enableShaders":true,}', encoding="utf-8")
            source = root / "src" / "Fixture.java"
            source.parent.mkdir()
            source.write_text("import org.dark.shaders.plugins.MissileSelfDestruct; class Fixture {}", encoding="utf-8")
            findings = {item.id: item for item in scan_mod(root).findings}
            self.assertEqual(findings["graphicslib-version-evidence"].evidence, ["1.10.0"])
            self.assertEqual(findings["graphicslib-api-usage"].classification, "SAFE")
            self.assertEqual(findings["graphicslib-missile-self-destruct-removed"].classification, "MANUAL")
            self.assertEqual(findings["graphicslib-no-self-destruct-config-removed"].classification, "MANUAL")
            self.assertEqual(findings["graphicslib-shader-settings-renamed"].classification, "REVIEW")


    def test_scanner_reports_lombok_and_external_mod_api_build_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text("{}", encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "Example.java").write_text(
                "import lombok.Getter; import org.lazywizard.console.Console; import data.scripts.util.MagicRender; import indevo.ids.Ids; class Example { @Getter int value; }",
                encoding="utf-8",
            )
            result = scan_mod(root)
            findings = {item.id for item in result.findings}
            self.assertIn("source-lombok-annotation-processing", findings)
            self.assertIn("external-mod-api-import", findings)
            self.assertEqual(3, sum(item.id == "external-mod-api-import" for item in result.findings))
            magic = next(item for item in result.library_usage if item["library"] == "MagicLib")
            self.assertTrue(magic["imported"])

    def test_scanner_records_declared_status_for_direct_external_apis(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text('{"dependencies":[{"id":"MagicLib","name":"MagicLib"}]}', encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "Example.java").write_text(
                "import data.scripts.util.MagicRender; class Example {}",
                encoding="utf-8",
            )
            result = scan_mod(root)
            matrix = result.migration_context["dependency_compatibility"]["direct_api_dependencies"]
            self.assertEqual(matrix, [{"dependency": "MagicLib", "declared": True, "imports": ["data.scripts.util.MagicRender"]}])


    def test_scanner_reports_legacy_custom_ui_and_dialog_callbacks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text("{}", encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "LegacyUi.java").write_text(
                "class LegacyUi implements CustomUIPanelPlugin { void processInput() {} }",
                encoding="utf-8",
            )
            (root / "src" / "LegacyDialog.java").write_text(
                "class LegacyDialog implements CustomDialogDelegate { void createCustomDialog(CustomPanelAPI panel) {} }",
                encoding="utf-8",
            )
            result = scan_mod(root)
            findings = {item.id for item in result.findings}
            self.assertIn("missing-custom-ui-button-pressed-callback", findings)
            self.assertIn("legacy-custom-dialog-delegate-signature", findings)


    def test_scanner_reports_missing_callback_in_anonymous_custom_ui_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text("{}", encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "MixedUi.java").write_text(
                "class MixedUi implements CustomUIPanelPlugin { void buttonPressed(Object id) {} void f() { new CustomUIPanelPlugin() { void render(float alpha) {} }; } }",
                encoding="utf-8",
            )
            result = scan_mod(root)
            finding = next(item for item in result.findings if item.id == "missing-custom-ui-button-pressed-callback")
            self.assertEqual(finding.evidence, ["1 plugin block(s) missing buttonPressed(Object)"])


    def test_scanner_reports_release_blocking_source_todo(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text("{}", encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "DevLeak.java").write_text(
                "class DevLeak { void load() { // TODO remove before final release\n } }",
                encoding="utf-8",
            )
            result = scan_mod(root)
            self.assertTrue(any(item.id == "release-blocking-source-todo" for item in result.findings))


    def test_scanner_reports_campaign_ui_robot_input_injection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text("{}", encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "Dialog.java").write_text(
                "class Dialog { void open() throws Exception { new java.awt.Robot(); } }",
                encoding="utf-8",
            )
            result = scan_mod(root)
            self.assertTrue(any(item.id == "campaign-ui-robot-input-injection" for item in result.findings))


    def test_scanner_reports_live_objects_and_external_keys_in_campaign_memory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text("{}", encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "Memory.java").write_text(
                "class Memory { void save(MemoryAPI memory) { memory.set(\"$local\", this); memory.getFleet(\"$nex_responseFleet\"); } }",
                encoding="utf-8",
            )
            result = scan_mod(root)
            findings = {item.id for item in result.findings}
            self.assertIn("campaign-memory-live-object", findings)
            self.assertIn("external-campaign-memory-key", findings)


    def test_scanner_reports_campaign_spawning_disabled_only_in_active_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text("{}", encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "World.java").write_text(
                "class World { void generate() { // system.addSpawnPoint(oldSpawner); } }",
                encoding="utf-8",
            )
            (root / "disabled_files").mkdir()
            (root / "disabled_files" / "Archived.java").write_text(
                "class Archived { void generate() { // system.addSpawnPoint(oldSpawner); } }",
                encoding="utf-8",
            )
            result = scan_mod(root)
            finding = next(item for item in result.findings if item.id == "campaign-spawn-registration-disabled")
            self.assertEqual(finding.file, "src/World.java")


    def test_scanner_reports_multiplier_expression_passed_to_modify_percent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text("{}", encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "Hullmod.java").write_text(
                "class Hullmod { void apply(Object stats, String id) { stats.getTurnRate().modifyPercent(id, 1f - PENALTY * 0.01f); } }",
                encoding="utf-8",
            )
            result = scan_mod(root)
            self.assertTrue(any(item.id == "suspicious-percent-multiplier" for item in result.findings))


    def test_scanner_reports_hard_coded_campaign_references_and_missing_local_mission_member(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text('{"id":"zorg"}', encoding="utf-8")
            source = root / "data" / "missions" / "fixture"
            source.mkdir(parents=True)
            (source / "MissionDefinition.java").write_text(
                "class MissionDefinition { void define() { sector.getStarSystem(\"Askonia\"); sector.getEntityById(\"zorg_signal\"); api.addToFleet(FleetSide.PLAYER, \"zorg_missing_Configurated\", FleetMemberType.SHIP, \"Z\", true); } }",
                encoding="utf-8",
            )
            (root / "data" / "variants").mkdir(parents=True)
            (root / "data" / "variants" / "zorg_present_Configurated.variant").write_text("{}", encoding="utf-8")
            result = scan_mod(root)
            findings = {item.id for item in result.findings}
            self.assertIn("hard-coded-campaign-system-reference", findings)
            self.assertIn("hard-coded-campaign-entity-reference", findings)
            self.assertIn("mission-local-fleet-reference-missing", findings)

    def test_scanner_resolves_local_mission_variant_hull_and_weapon_assets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text('{"id":"fixture"}', encoding="utf-8")
            mission = root / "data" / "missions" / "fixture"
            mission.mkdir(parents=True)
            (mission / "MissionDefinition.java").write_text(
                'class MissionDefinition { void define() { api.addToFleet(FleetSide.PLAYER, "fixture_variant", FleetMemberType.SHIP, "F", true); } }',
                encoding="utf-8",
            )
            (root / "data" / "variants").mkdir(parents=True)
            (root / "data" / "variants" / "fixture_variant.variant").write_text(
                '{"hullId":"fixture_hull","weaponGroups":[{"weapons":{"WS001":"fixture_weapon"}}]}',
                encoding="utf-8",
            )
            result = scan_mod(root)
            findings = {item.id for item in result.findings}
            self.assertIn("mission-local-variant-hull-missing", findings)
            self.assertIn("mission-local-variant-weapon-missing", findings)


    def test_scanner_reports_wrapper_directory_layout_without_retargeting_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wrapped = root / "release-wrapper" / "actual-mod"
            wrapped.mkdir(parents=True)
            (wrapped / "mod_info.json").write_text("{}", encoding="utf-8")
            result = scan_mod(root / "release-wrapper")
            self.assertTrue(any(finding.id == "missing-mod-info" for finding in result.findings))
            self.assertTrue(any(finding.id == "wrapper-directory-layout" and finding.classification == "REVIEW" for finding in result.findings))


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


    def test_scanner_structurally_reads_hash_comments_without_claiming_target_compatibility(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text('{"id":"zorg", # retained historical comment\n"gameVersion":"0.98a"}', encoding="utf-8")
            (root / "data").mkdir()
            (root / "data" / "settings.json").write_text('{"label":"# not a comment", # comment\n"value":1}', encoding="utf-8")
            result = scan_mod(root)
            self.assertEqual(result.metadata["id"], "zorg")
            self.assertEqual(result.declared_starsector, "0.98a")
            self.assertEqual(result.estimated_starsector, "UNKNOWN")
            self.assertEqual(result.metadata_parse_mode, "HASH-COMMENTS")
            self.assertTrue(any(finding.id == "historical-json-hash-comment" and finding.file == "mod_info.json" for finding in result.findings))
            self.assertTrue(any(finding.id == "historical-json-hash-comment" and finding.file == "data/settings.json" for finding in result.findings))
            self.assertTrue(any(finding.id == "version-inference-blocked" for finding in result.findings))


    def test_scanner_separates_encoding_and_structural_ambiguity_from_breakage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text("{}", encoding="utf-8")
            (root / "legacy.json").write_bytes(b'{"name":"\x92legacy"}')
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
            self.assertTrue(any(finding.id == "json-encoding-unverified" for finding in result.findings))
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
