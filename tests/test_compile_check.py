"""Tests for `bridgeforge compile-check`."""
from __future__ import annotations

import shutil
import unittest
from pathlib import Path
from unittest import mock

from bridgeforge.compile_check import _janino_gap_warnings, compile_loose_scripts, discover_loose_scripts
from tests.support import resolved_temp_dir


class DiscoverLooseScriptsTests(unittest.TestCase):
    def test_finds_data_java_and_skips_disabled_files(self) -> None:
        with resolved_temp_dir() as root:
            (root / "data" / "scripts").mkdir(parents=True)
            (root / "data" / "scripts" / "Foo.java").write_text("class Foo {}", encoding="utf-8")
            (root / "data" / "scripts" / "disabled_files").mkdir()
            (root / "data" / "scripts" / "disabled_files" / "Old.java").write_text("class Old {}", encoding="utf-8")
            found = discover_loose_scripts(root)
            self.assertEqual([p.name for p in found], ["Foo.java"])

    def test_ignores_src_and_jars_src(self) -> None:
        with resolved_temp_dir() as root:
            (root / "src").mkdir()
            (root / "src" / "Lib.java").write_text("class Lib {}", encoding="utf-8")
            (root / "jars" / "src").mkdir(parents=True)
            (root / "jars" / "src" / "Lib2.java").write_text("class Lib2 {}", encoding="utf-8")
            self.assertEqual(discover_loose_scripts(root), [])

    def test_no_data_dir(self) -> None:
        with resolved_temp_dir() as root:
            self.assertEqual(discover_loose_scripts(root), [])


class JaninoGapWarningsTests(unittest.TestCase):
    def _hits(self, source_text: str) -> list[str]:
        with resolved_temp_dir() as root:
            path = root / "S.java"
            path.write_text(source_text, encoding="utf-8")
            warnings = _janino_gap_warnings([path], root)
            return warnings[0]["java8plus_syntax"] if warnings else []

    def test_lambda_no_parens(self) -> None:
        self.assertIn("lambda", self._hits("class S { void r() { items.forEach(s -> use(s)); } }"))

    def test_lambda_with_parens(self) -> None:
        self.assertIn("lambda", self._hits("class S { void r() { items.forEach((s) -> use(s)); } }"))

    def test_method_reference(self) -> None:
        self.assertIn("method-reference", self._hits("class S { Runnable r = System.out::println; }"))

    def test_diamond_operator(self) -> None:
        self.assertIn("diamond-operator", self._hits("class S { List<String> l = new ArrayList<>(); }"))

    def test_try_with_resources(self) -> None:
        self.assertIn("try-with-resources", self._hits("class S { void r() { try (Reader x = open()) {} } }"))

    def test_multi_catch(self) -> None:
        self.assertIn("multi-catch", self._hits("class S { void r() { try {} catch (IOException | RuntimeException e) {} } }"))

    def test_var_keyword(self) -> None:
        self.assertIn("var-keyword", self._hits("class S { void r() { var x = 5; } }"))

    def test_clean_source_has_no_hits(self) -> None:
        self.assertEqual(self._hits("class S { int add(int a, int b) { return a + b; } }"), [])

    def test_comment_mentioning_syntax_is_blanked(self) -> None:
        # A comment that merely mentions "->" or "var" shouldn't trip the heuristic.
        text = "class S {\n  // uses a lambda x -> x and a var somewhere\n  int add(int a, int b) { return a + b; }\n}\n"
        self.assertEqual(self._hits(text), [])


class CompileLooseScriptsUnavailableTests(unittest.TestCase):
    def test_unavailable_when_no_jdk_found(self) -> None:
        with resolved_temp_dir() as root:
            (root / "data").mkdir()
            with mock.patch("bridgeforge.compile_check.find_jdk", return_value=None):
                result = compile_loose_scripts(root)
            self.assertEqual(result["status"], "UNAVAILABLE")
            self.assertEqual(result["schema_version"], 1)
            self.assertEqual(result["mode"], "COMPILE_CHECK")

    def test_not_a_directory_raises(self) -> None:
        with resolved_temp_dir() as root:
            with self.assertRaises(ValueError):
                compile_loose_scripts(root / "does-not-exist")


class CompileLooseScriptsEndToEndTests(unittest.TestCase):
    """Real javac invocations; skipped cleanly when no JDK is on PATH."""

    def setUp(self) -> None:
        if shutil.which("javac") is None:
            self.skipTest("no javac on PATH")

    def _mod(self, root: Path) -> Path:
        mod = root / "mod"
        (mod / "data" / "scripts").mkdir(parents=True)
        (mod / "mod_info.json").write_text('{"id":"m1","name":"M","author":"t","version":"1.0","gameVersion":"0.98a-RC8"}', encoding="utf-8")
        return mod

    def test_pass_with_clean_loose_script(self) -> None:
        with resolved_temp_dir() as root:
            mod = self._mod(root)
            (mod / "data" / "scripts" / "Good.java").write_text(
                "package data.scripts;\npublic class Good { public int add(int a, int b) { return a + b; } }",
                encoding="utf-8",
            )
            result = compile_loose_scripts(mod, provider_roots=[])
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["error_count"], 0)
            self.assertEqual(result["files"], ["data/scripts/Good.java"])

    def test_fail_with_missing_symbol(self) -> None:
        with resolved_temp_dir() as root:
            mod = self._mod(root)
            (mod / "data" / "scripts" / "Bad.java").write_text(
                "package data.scripts;\npublic class Bad { void use() { undefinedThing(); } }",
                encoding="utf-8",
            )
            result = compile_loose_scripts(mod, provider_roots=[])
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["error_count"], 1)
            self.assertEqual(result["error_counts_by_kind"], {"missing-symbol": 1})

    def test_loose_script_extending_a_vanilla_loose_script_resolves(self) -> None:
        """A mod script extending a vanilla loose class (e.g. BaseSpawnPoint) needs that vanilla
        class's SOURCE compiled alongside it -- it is never in a jar (real case: Gekelonians'
        gekelonianSpawnPoint extends data.scripts.world.BaseSpawnPoint)."""
        with resolved_temp_dir() as root:
            vanilla_core = root / "core"
            (vanilla_core / "data" / "scripts" / "world").mkdir(parents=True)
            (vanilla_core / "data" / "scripts" / "world" / "BaseSpawnPoint.java").write_text(
                "package data.scripts.world;\npublic abstract class BaseSpawnPoint { public void tick() {} }",
                encoding="utf-8",
            )
            mod = self._mod(root)
            (mod / "data" / "scripts" / "world").mkdir(parents=True)
            (mod / "data" / "scripts" / "world" / "MySpawn.java").write_text(
                "package data.scripts.world;\npublic class MySpawn extends BaseSpawnPoint {}",
                encoding="utf-8",
            )
            result = compile_loose_scripts(mod, vanilla_core=vanilla_core, provider_roots=[])
            self.assertEqual(result["status"], "PASS", result["errors"])
            self.assertEqual(result["vanilla_loose_script_companions"], 1)
            self.assertEqual(result["vanilla_companion_errors"], [])

    def test_pass_when_no_loose_scripts(self) -> None:
        with resolved_temp_dir() as root:
            mod = root / "mod"
            mod.mkdir()
            (mod / "mod_info.json").write_text('{"id":"m1"}', encoding="utf-8")
            result = compile_loose_scripts(mod, provider_roots=[])
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["files"], [])

    def test_missing_dependency_jar_reported(self) -> None:
        with resolved_temp_dir() as root:
            mod = self._mod(root)
            mod_info = mod / "mod_info.json"
            mod_info.write_text(
                '{"id":"m1","dependencies":[{"id":"not_installed_anywhere"}]}', encoding="utf-8"
            )
            (mod / "data" / "scripts" / "Good.java").write_text(
                "package data.scripts;\npublic class Good {}", encoding="utf-8"
            )
            result = compile_loose_scripts(mod, provider_roots=[root / "no-providers"])
            self.assertIn("not_installed_anywhere", result["classpath"]["dependencies_missing"])


    def test_script_a_dependency_jar_already_compiles_is_reported_and_its_errors_set_aside(self) -> None:
        # E8 (2026-09-20): Maelstrom's Titan scripts were shadowed by base Interstellar Imperium's II.jar.
        from tests.save_fixtures import build_class_file, write_jar

        with resolved_temp_dir() as root:
            providers = root / "mods"
            base = providers / "Interstellar Imperium"
            base.mkdir(parents=True)
            (base / "mod_info.json").write_text('{"id":"Imperium","name":"II","jars":["jars/II.jar"]}', encoding="utf-8")
            write_jar(base / "jars" / "II.jar", {"data/scripts/Titan.class": build_class_file("data/scripts/Titan")})
            mod = self._mod(root)
            (mod / "mod_info.json").write_text('{"id":"m1","dependencies":[{"id":"Imperium"}]}', encoding="utf-8")
            (mod / "data" / "scripts" / "Titan.java").write_text(
                "package data.scripts;\npublic class Titan { void f() { undefinedThing(); } }", encoding="utf-8")
            (mod / "data" / "scripts" / "Own.java").write_text("package data.scripts;\npublic class Own {}", encoding="utf-8")
            result = compile_loose_scripts(mod, provider_roots=[providers])
        self.assertEqual(result["status"], "PASS", result["errors"])
        self.assertEqual(result["error_count"], 0)
        self.assertEqual(len(result["shadowed_file_errors"]), 1)
        self.assertEqual([(e["file"], e["class"], e["dependency"]) for e in result["shadowed_by_dependency"]],
                         [("data/scripts/Titan.java", "data.scripts.Titan", "Imperium")])
        self.assertTrue(result["shadowed_by_dependency"][0]["supplied_by"].endswith("II.jar!data/scripts/Titan.class"))


class DependencyShadowScanFindingTests(unittest.TestCase):
    def test_scan_reports_loose_script_shadowed_by_dependency_jar(self) -> None:
        from unittest.mock import patch

        from bridgeforge.models import TargetProfile
        from bridgeforge.scanner import scan_mod

        outcome = {"status": "PASS", "errors": [], "shadowed_by_dependency": [
            {"file": "data/scripts/Titan.java", "class": "data.scripts.Titan", "dependency": "Imperium", "supplied_by": "II.jar!data/scripts/Titan.class"}]}
        with resolved_temp_dir() as root:
            mod, core = root / "mod", root / "core"
            (mod / "data" / "scripts").mkdir(parents=True)
            core.mkdir()
            (mod / "mod_info.json").write_text('{"id":"m1","name":"M","gameVersion":"0.98a"}', encoding="utf-8")
            with patch("bridgeforge.compile_check.compile_loose_scripts", return_value=outcome):
                result = scan_mod(mod, TargetProfile("0.98a-RC8", 17), core, compile_check=True)
        finding = next(f for f in result.findings if f.id == "loose-script-shadowed-by-dependency-jar")
        self.assertEqual((finding.classification, finding.file), ("MANUAL", "data/scripts/Titan.java"))
        self.assertIn("Imperium", finding.explanation)
        self.assertEqual(finding.evidence, ["class:data.scripts.Titan", "supplied by:II.jar!data/scripts/Titan.class"])


if __name__ == "__main__":
    unittest.main()
