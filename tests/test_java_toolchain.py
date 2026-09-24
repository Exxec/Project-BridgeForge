"""Tests for the shared Java-toolchain module used by compile-check and rebuild-jar."""
from __future__ import annotations

import contextlib
import os
import shutil
import unittest
from pathlib import Path

from bridgeforge.java_toolchain import (
    assemble_classpath,
    declared_dependencies,
    find_jdk,
    DEFAULT_JAVAC_ARGS,
    parse_javac_errors,
    run_javac,
)
from tests.support import resolved_temp_dir


def _touch_javac(home: Path) -> None:
    bin_dir = home / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    exe = "javac.exe" if os.name == "nt" else "javac"
    (bin_dir / exe).write_text("", encoding="utf-8")
    for other in ("javap", "jar"):
        (bin_dir / (other + (".exe" if os.name == "nt" else ""))).write_text("", encoding="utf-8")


@contextlib.contextmanager
def _env(name: str, value: str | None):
    old = os.environ.get(name)
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value
    try:
        yield
    finally:
        if old is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = old


class FindJdkTests(unittest.TestCase):
    def test_explicit_wins_over_repo_rig(self) -> None:
        with resolved_temp_dir() as root:
            explicit = root / "explicit-jdk"
            rig_jdk = root / "repo" / "In operation" / "_rig" / "jdk-1"
            _touch_javac(explicit)
            _touch_javac(rig_jdk)
            info = find_jdk(explicit=explicit, repo_root=root / "repo")
            self.assertIsNotNone(info)
            self.assertEqual(info.source, "explicit")
            self.assertEqual(info.home, explicit.resolve())
            self.assertTrue(info.javac.is_file())

    def test_falls_back_to_repo_rig_jdk(self) -> None:
        with resolved_temp_dir() as root:
            rig_jdk = root / "repo" / "In operation" / "_rig" / "jdk-25.0"
            _touch_javac(rig_jdk)
            info = find_jdk(explicit=None, repo_root=root / "repo")
            self.assertIsNotNone(info)
            self.assertEqual(info.source, "repo-rig")
            self.assertEqual(info.home, rig_jdk.resolve())

    def test_falls_back_to_java_home(self) -> None:
        with resolved_temp_dir() as root:
            home = root / "java-home-jdk"
            _touch_javac(home)
            empty_repo = root / "empty-repo"
            empty_repo.mkdir()
            with _env("JAVA_HOME", str(home)):
                info = find_jdk(explicit=None, repo_root=empty_repo)
            self.assertIsNotNone(info)
            self.assertEqual(info.source, "JAVA_HOME")

    def test_explicit_missing_javac_falls_back(self) -> None:
        """An explicit --jdk with no bin/javac is skipped, not treated as fatal here."""
        with resolved_temp_dir() as root:
            bad_explicit = root / "not-a-jdk"
            bad_explicit.mkdir()
            rig_jdk = root / "repo" / "In operation" / "_rig" / "jdk-1"
            _touch_javac(rig_jdk)
            info = find_jdk(explicit=bad_explicit, repo_root=root / "repo")
            self.assertIsNotNone(info)
            self.assertEqual(info.source, "repo-rig")

    def test_none_when_nothing_found(self) -> None:
        with resolved_temp_dir() as root:
            empty_repo = root / "empty-repo"
            empty_repo.mkdir()
            with _env("JAVA_HOME", None), _env("PATH", str(root / "nothing-here")):
                info = find_jdk(explicit=None, repo_root=empty_repo)
            self.assertIsNone(info)


class DeclaredDependenciesTests(unittest.TestCase):
    def test_reads_dict_and_string_entries(self) -> None:
        with resolved_temp_dir() as root:
            (root / "mod_info.json").write_text(
                '{"id":"m","dependencies":[{"id":"lw_lazylib","name":"LazyLib"}, "bare_id", {"name":"no id here"}]}',
                encoding="utf-8",
            )
            self.assertEqual(declared_dependencies(root), ["lw_lazylib", "bare_id"])

    def test_no_mod_info_or_no_dependencies_key(self) -> None:
        with resolved_temp_dir() as root:
            self.assertEqual(declared_dependencies(root), [])
            (root / "mod_info.json").write_text('{"id":"m"}', encoding="utf-8")
            self.assertEqual(declared_dependencies(root), [])


class AssembleClasspathTests(unittest.TestCase):
    def test_core_jars_mod_jars_and_missing_dependency(self) -> None:
        with resolved_temp_dir() as root:
            core = root / "core"
            core.mkdir()
            (core / "starfarer.api.jar").write_bytes(b"not-a-real-jar")
            (core / "json.jar").write_bytes(b"not-a-real-jar")
            mod = root / "mod"
            (mod / "jars").mkdir(parents=True)
            (mod / "jars" / "M1.jar").write_bytes(b"not-a-real-jar")
            (mod / "mod_info.json").write_text(
                '{"id":"m1","jars":["jars/M1.jar"],"dependencies":[{"id":"missing_dep"}]}', encoding="utf-8"
            )
            result = assemble_classpath(mod, core, provider_roots=[root / "no-providers-here"])
            self.assertEqual(len(result.core_jars), 2)
            self.assertEqual(len(result.mod_jars), 1)
            self.assertIn("missing_dep", result.dependencies_missing)
            self.assertEqual(result.dependency_jars, {})
            self.assertTrue(result.classpath())
            self.assertEqual(len(result.entries()), 3)

    def test_dependency_found_via_provider_index(self) -> None:
        with resolved_temp_dir() as root:
            providers = root / "providers"
            dep = providers / "DepMod"
            dep.mkdir(parents=True)
            (dep / "mod_info.json").write_text('{"id":"depid","jars":["dep.jar"]}', encoding="utf-8")
            (dep / "dep.jar").write_bytes(b"not-a-real-jar")
            mod = root / "mod"
            mod.mkdir()
            (mod / "mod_info.json").write_text('{"id":"m1","dependencies":[{"id":"depid"}]}', encoding="utf-8")
            result = assemble_classpath(mod, None, provider_roots=[providers])
            self.assertIn("depid", result.dependency_jars)
            self.assertEqual(len(result.dependency_jars["depid"]), 1)
            self.assertEqual(result.dependencies_missing, [])
            self.assertEqual(result.core_jars, [])

    def test_mod_jars_fall_back_to_every_jar_when_none_declared(self) -> None:
        with resolved_temp_dir() as root:
            mod = root / "mod"
            (mod / "jars").mkdir(parents=True)
            (mod / "jars" / "Loose.jar").write_bytes(b"not-a-real-jar")
            (mod / "build" / "cp").mkdir(parents=True)
            (mod / "build" / "cp" / "cached.jar").write_bytes(b"not-a-real-jar")
            (mod / "mod_info.json").write_text('{"id":"m1"}', encoding="utf-8")
            result = assemble_classpath(mod, None, provider_roots=[])
            names = [Path(p).name for p in result.mod_jars]
            self.assertIn("Loose.jar", names)
            self.assertNotIn("cached.jar", names)

    def test_exclude_removes_a_classpath_entry(self) -> None:
        with resolved_temp_dir() as root:
            mod = root / "mod"
            (mod / "jars").mkdir(parents=True)
            jar = mod / "jars" / "M1.jar"
            jar.write_bytes(b"not-a-real-jar")
            (mod / "mod_info.json").write_text('{"id":"m1","jars":["jars/M1.jar"]}', encoding="utf-8")
            result = assemble_classpath(mod, None, provider_roots=[])
            self.assertEqual(len(result.entries()), 1)
            self.assertEqual(result.entries(exclude={str(jar)}), [])


class ParseJavacErrorsTests(unittest.TestCase):
    """Fixture-based: real javac stderr captured once (see below), needs no JDK to run."""

    WINDOWS_FIXTURE = (
        "C:\\Users\\dev\\Foo.java:4: error: cannot find symbol\r\n"
        "        someMethod();\r\n"
        "        ^\r\n"
        "  symbol:   method someMethod()\r\n"
        "  location: class Foo\r\n"
        "C:\\Users\\dev\\Foo.java:5: error: incompatible types: String cannot be converted to int\r\n"
        "        int x = \"hello\";\r\n"
        "                ^\r\n"
        "C:\\Users\\dev\\Foo.java:6: error: method bar in class Foo cannot be applied to given types;\r\n"
        "        bar(1, 2, 3, 4);\r\n"
        "        ^\r\n"
        "  required: int,int,int\r\n"
        "  found:    int,int,int,int\r\n"
        "  reason: actual and formal argument lists differ in length\r\n"
        "3 errors\r\n"
    )
    POSIX_FIXTURE = (
        "/home/dev/Foo.java:9: error: ';' expected\n"
        "    int x = 5\n"
        "             ^\n"
        "1 error\n"
    )

    def test_windows_fixture_classifies_all_three_kinds(self) -> None:
        errors = parse_javac_errors(self.WINDOWS_FIXTURE)
        self.assertEqual(len(errors), 3)
        self.assertEqual(errors[0]["file"], "C:\\Users\\dev\\Foo.java")
        self.assertEqual(errors[0]["line"], 4)
        self.assertEqual(errors[0]["kind"], "missing-symbol")
        self.assertEqual(errors[0]["message"], "cannot find symbol")
        self.assertEqual(errors[0]["detail"], ["symbol: method someMethod()", "location: class Foo"])
        self.assertEqual(errors[1]["kind"], "incompatible-types")
        self.assertEqual(errors[1]["detail"], [])
        self.assertEqual(errors[2]["kind"], "cannot-be-applied")
        # required:/found:/reason: are deliberately not captured -- only symbol:/location: are.
        self.assertEqual(errors[2]["detail"], [])

    def test_posix_path_and_other_kind(self) -> None:
        errors = parse_javac_errors(self.POSIX_FIXTURE)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["file"], "/home/dev/Foo.java")
        self.assertEqual(errors[0]["line"], 9)
        self.assertEqual(errors[0]["kind"], "other")

    def test_no_errors(self) -> None:
        self.assertEqual(parse_javac_errors(""), [])
        self.assertEqual(parse_javac_errors("Note: Foo.java uses unchecked operations.\n"), [])


class RunJavacEndToEndTests(unittest.TestCase):
    """Real javac invocations; skipped cleanly when no JDK is on PATH."""

    def _javac(self) -> Path | None:
        found = shutil.which("javac")
        return Path(found) if found else None

    def test_compiles_clean_source(self) -> None:
        javac = self._javac()
        if javac is None:
            self.skipTest("no javac on PATH")
        with resolved_temp_dir() as root:
            source = root / "Good.java"
            source.write_text("public class Good { int add(int a, int b) { return a + b; } }", encoding="utf-8")
            run = run_javac(javac, "", [source], root / "out")
            self.assertTrue(run.success, run.stderr)
            self.assertEqual(run.errors, [])
            self.assertTrue((root / "out" / "Good.class").is_file())

    def test_compiles_broken_source_and_parses_errors(self) -> None:
        javac = self._javac()
        if javac is None:
            self.skipTest("no javac on PATH")
        with resolved_temp_dir() as root:
            source = root / "Bad.java"
            source.write_text("public class Bad { void use() { undefinedThing(); } }", encoding="utf-8")
            run = run_javac(javac, "", [source], root / "out")
            self.assertFalse(run.success)
            self.assertEqual(len(run.errors), 1)
            self.assertEqual(run.errors[0]["kind"], "missing-symbol")
            self.assertIn("undefinedThing", run.errors[0]["detail"][0])


class JarEmbeddedSourceDiagnosticTests(unittest.TestCase):
    """ROADMAP P14 item 13: some mods ship .java inside their jar (Interstellar Imperium's II.jar).

    javac would otherwise recompile those classpath entries and blame the mod under test, and its
    diagnostics -- which `_ERROR_HEADER` cannot match, because of the "(" -- used to leave the
    parser appending every following "symbol:"/"location:" line to the previous real error.
    """

    FIXTURE = "\n".join(
        [
            r"C:\work\mod\data\scripts\Real.java:12: error: cannot find symbol",
            "  symbol:   variable Foo",
            "  location: class Real",
            r"C:\mods\II\jars\II.jar(/data/scripts/Bundled.java):55: error: package org.lazywizard.lazylib does not exist",
            "  symbol:   class MathUtils",
            "  location: class Bundled",
            r"C:\mods\II\jars\II.jar(/data/scripts/Other.java):77: error: cannot find symbol",
            "  symbol:   variable Bar",
        ]
    )

    def test_jar_embedded_errors_are_not_recorded(self) -> None:
        errors = parse_javac_errors(self.FIXTURE)
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0]["file"].endswith("Real.java"))

    def test_jar_embedded_details_do_not_pollute_the_previous_error(self) -> None:
        errors = parse_javac_errors(self.FIXTURE)
        self.assertEqual(errors[0]["detail"], ["symbol: variable Foo", "location: class Real"])

    def test_posix_jar_paths_are_recognised_too(self) -> None:
        fixture = "\n".join(
            [
                "/home/u/mod/data/scripts/Real.java:3: error: cannot find symbol",
                "  symbol: variable Foo",
                "/home/u/mods/II/jars/II.jar(/data/scripts/Bundled.java):9: error: cannot find symbol",
                "  symbol: class Gone",
            ]
        )
        errors = parse_javac_errors(fixture)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["detail"], ["symbol: variable Foo"])

    def test_empty_sourcepath_is_passed_to_javac(self) -> None:
        args = list(DEFAULT_JAVAC_ARGS)
        self.assertIn("-sourcepath", args)
        self.assertEqual(args[args.index("-sourcepath") + 1], "")

    def test_verbose_diagnostics_name_the_method_for_api_diff(self) -> None:
        self.assertIn("-Xdiags:verbose", DEFAULT_JAVAC_ARGS)


if __name__ == "__main__":
    unittest.main()
