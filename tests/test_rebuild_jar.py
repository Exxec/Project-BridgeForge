"""Tests for `bridgeforge rebuild-jar`."""
from __future__ import annotations

import shutil
import subprocess
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from bridgeforge.rebuild_jar import (
    RebuildJarError,
    _Member,
    _ParsedClass,
    _diff_class,
    _resolve_original_jar,
    _resolve_sources_dir,
    _resolve_workspace,
    compare_jars,
    rebuild_jar,
)
from tests.support import resolved_temp_dir

ACC_PUBLIC = 0x0001
ACC_STATIC = 0x0008
ACC_SYNCHRONIZED = 0x0020
ACC_SYNTHETIC = 0x1000


def _cls(name: str = "Foo", major: int = 61, minor: int = 0, methods: dict | None = None, fields: dict | None = None, refs: set | None = None) -> _ParsedClass:
    return _ParsedClass(name, major, minor, methods or {}, fields or {}, refs or set())


class ResolveWorkspaceTests(unittest.TestCase):
    def test_accepts_workspace_root(self) -> None:
        with resolved_temp_dir() as root:
            (root / "MyMod" / "working").mkdir(parents=True)
            workspace, working = _resolve_workspace(root / "MyMod")
            self.assertEqual(workspace, (root / "MyMod").resolve())
            self.assertEqual(working, (root / "MyMod" / "working").resolve())

    def test_accepts_working_copy_directly(self) -> None:
        with resolved_temp_dir() as root:
            (root / "MyMod" / "working").mkdir(parents=True)
            workspace, working = _resolve_workspace(root / "MyMod" / "working")
            self.assertEqual(workspace, (root / "MyMod").resolve())
            self.assertEqual(working, (root / "MyMod" / "working").resolve())

    def test_neither_raises(self) -> None:
        with resolved_temp_dir() as root:
            (root / "NotAMod").mkdir()
            with self.assertRaises(RebuildJarError):
                _resolve_workspace(root / "NotAMod")


class ResolveSourcesDirTests(unittest.TestCase):
    def test_relative_to_workspace(self) -> None:
        with resolved_temp_dir() as root:
            workspace = root / "MyMod"
            working = workspace / "working"
            (working / "data" / "scripts").mkdir(parents=True)
            found = _resolve_sources_dir(workspace, working, "working\\data\\scripts")
            self.assertEqual(found, (working / "data" / "scripts").resolve())

    def test_relative_to_working(self) -> None:
        with resolved_temp_dir() as root:
            workspace = root / "MyMod"
            working = workspace / "working"
            (working / "data" / "scripts").mkdir(parents=True)
            found = _resolve_sources_dir(workspace, working, "data/scripts")
            self.assertEqual(found, (working / "data" / "scripts").resolve())

    def test_missing_raises(self) -> None:
        with resolved_temp_dir() as root:
            workspace = root / "MyMod"
            working = workspace / "working"
            working.mkdir(parents=True)
            with self.assertRaises(RebuildJarError):
                _resolve_sources_dir(workspace, working, "nope")


class ResolveOriginalJarTests(unittest.TestCase):
    def test_found_under_original_archive_subfolder(self) -> None:
        with resolved_temp_dir() as root:
            workspace = root / "MyMod"
            working = workspace / "working"
            working.mkdir(parents=True)
            original_jar = workspace / "original" / "ArchiveFolder" / "jars" / "M.jar"
            original_jar.parent.mkdir(parents=True)
            original_jar.write_bytes(b"PK\x03\x04")
            resolved, relative = _resolve_original_jar(workspace, working, "jars\\M.jar")
            self.assertEqual(resolved, original_jar.resolve())
            self.assertEqual(relative, "jars/M.jar")

    def test_found_relative_to_workspace_root_first(self) -> None:
        with resolved_temp_dir() as root:
            workspace = root / "MyMod"
            working = workspace / "working"
            working.mkdir(parents=True)
            direct_jar = workspace / "jars" / "M.jar"
            direct_jar.parent.mkdir(parents=True)
            direct_jar.write_bytes(b"PK\x03\x04")
            # Also place a decoy under original/ to prove the workspace-root match wins first.
            decoy = workspace / "original" / "Arc" / "jars" / "M.jar"
            decoy.parent.mkdir(parents=True)
            decoy.write_bytes(b"decoy")
            resolved, relative = _resolve_original_jar(workspace, working, "jars/M.jar")
            self.assertEqual(resolved, direct_jar.resolve())
            self.assertEqual(relative, "jars/M.jar")

    def test_falls_back_to_working_copy(self) -> None:
        with resolved_temp_dir() as root:
            workspace = root / "MyMod"
            working = workspace / "working"
            (working / "jars").mkdir(parents=True)
            jar = working / "jars" / "M.jar"
            jar.write_bytes(b"PK\x03\x04")
            resolved, relative = _resolve_original_jar(workspace, working, "jars/M.jar")
            self.assertEqual(resolved, jar.resolve())

    def test_not_found_raises_with_tried_paths(self) -> None:
        with resolved_temp_dir() as root:
            workspace = root / "MyMod"
            working = workspace / "working"
            working.mkdir(parents=True)
            with self.assertRaises(RebuildJarError) as ctx:
                _resolve_original_jar(workspace, working, "jars/Nope.jar")
            self.assertIn("Nope.jar", str(ctx.exception))


class DiffClassNormalizationTests(unittest.TestCase):
    """Hermetic (no JDK needed): hand-built _ParsedClass records exercise the normalization rules directly."""

    def test_identical_classes_produce_no_diff(self) -> None:
        methods = {("run", "()V"): _Member("run", "()V", ACC_PUBLIC)}
        old = _cls(methods=methods)
        new = _cls(methods=dict(methods))
        self.assertIsNone(_diff_class("Foo.class", old, new))

    def test_real_method_removal_is_reported_not_normalized(self) -> None:
        old = _cls(methods={("sub", "(II)I"): _Member("sub", "(II)I", ACC_PUBLIC)})
        new = _cls(methods={})
        diff = _diff_class("Foo.class", old, new)
        self.assertIsNotNone(diff)
        self.assertEqual(diff["methods_removed"], ["sub(II)I"])
        self.assertEqual(diff["expected_differences"], [])

    def test_real_method_addition_is_reported_not_normalized(self) -> None:
        old = _cls(methods={})
        new = _cls(methods={("mul", "(II)I"): _Member("mul", "(II)I", ACC_PUBLIC)})
        diff = _diff_class("Foo.class", old, new)
        self.assertEqual(diff["methods_added"], ["mul(II)I"])
        self.assertEqual(diff["methods_removed"], [])

    def test_lombok_lock_field_removed_is_expected(self) -> None:
        old = _cls(fields={("$lock", "Ljava/lang/Object;"): _Member("$lock", "Ljava/lang/Object;", 0)})
        new = _cls(fields={})
        diff = _diff_class("Foo.class", old, new)
        self.assertEqual(diff["fields_removed"], [])
        self.assertTrue(any("$lock" in note for note in diff["expected_differences"]))

    def test_lombok_static_lock_field_added_is_expected(self) -> None:
        old = _cls(fields={})
        new = _cls(fields={("$LOCK", "Ljava/lang/Object;"): _Member("$LOCK", "Ljava/lang/Object;", ACC_STATIC)})
        diff = _diff_class("Foo.class", old, new)
        self.assertEqual(diff["fields_added"], [])
        self.assertTrue(any("$LOCK" in note for note in diff["expected_differences"]))

    def test_synthetic_lambda_member_is_expected(self) -> None:
        key = ("lambda$run$0", "()V")
        old = _cls(methods={})
        new = _cls(methods={key: _Member(*key, ACC_SYNTHETIC | 0x0002)})
        diff = _diff_class("Foo.class", old, new)
        self.assertEqual(diff["methods_added"], [])
        self.assertTrue(any("lambda$run$0" in note for note in diff["expected_differences"]))

    def test_synthetic_access_member_removed_is_expected(self) -> None:
        key = ("access$000", "()I")
        old = _cls(methods={key: _Member(*key, ACC_SYNTHETIC)})
        new = _cls(methods={})
        diff = _diff_class("Foo.class", old, new)
        self.assertEqual(diff["methods_removed"], [])
        self.assertTrue(any("access$000" in note for note in diff["expected_differences"]))

    def test_synchronized_only_modifier_change_is_expected(self) -> None:
        key = ("run", "()V")
        old = _cls(methods={key: _Member(*key, ACC_PUBLIC)})
        new = _cls(methods={key: _Member(*key, ACC_PUBLIC | ACC_SYNCHRONIZED)})
        diff = _diff_class("Foo.class", old, new)
        self.assertEqual(diff["methods_modified"], [])
        self.assertTrue(any("synchronized" in note for note in diff["expected_differences"]))

    def test_non_synchronized_modifier_change_is_not_normalized(self) -> None:
        key = ("run", "()V")
        old = _cls(methods={key: _Member(*key, ACC_PUBLIC)})
        new = _cls(methods={key: _Member(*key, 0x0002)})  # public -> private: not a synchronized-only change
        diff = _diff_class("Foo.class", old, new)
        self.assertEqual(len(diff["methods_modified"]), 1)
        self.assertEqual(diff["methods_modified"][0]["member"], "run()V")

    def test_class_file_version_difference_is_expected(self) -> None:
        old = _cls(major=52, minor=0)
        new = _cls(major=61, minor=0)
        diff = _diff_class("Foo.class", old, new)
        self.assertIsNotNone(diff)
        self.assertTrue(any("52.0 -> 61.0" in note for note in diff["expected_differences"]))

    def test_forbidden_sandbox_reference_reported(self) -> None:
        old = _cls(refs=set())
        new = _cls(refs={"java/io/File", "java/lang/String"})
        diff = _diff_class("Foo.class", old, new)
        self.assertIsNotNone(diff)
        self.assertEqual(diff["forbidden_sandbox_references"], ["java.io.File"])


class CompareJarsTests(unittest.TestCase):
    def _jar_bytes(self, entries: dict[str, bytes]) -> bytes:
        import io
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as archive:
            for name, data in entries.items():
                archive.writestr(name, data)
        return buf.getvalue()

    def test_added_and_removed_classes(self) -> None:
        old = self._jar_bytes({"A.class": b"\xca\xfe\xba\xbe" + b"\x00" * 20})
        new = self._jar_bytes({"B.class": b"\xca\xfe\xba\xbe" + b"\x00" * 20})
        comparison = compare_jars(old, new)
        self.assertEqual(comparison["removed_classes"], ["A.class"])
        self.assertEqual(comparison["added_classes"], ["B.class"])
        self.assertTrue(comparison["unexpected_member_or_class_loss"])


class RebuildJarUnavailableTests(unittest.TestCase):
    def test_unavailable_when_no_jdk_found(self) -> None:
        with resolved_temp_dir() as root:
            workspace = root / "MyMod"
            working = workspace / "working"
            working.mkdir(parents=True)
            (working / "mod_info.json").write_text('{"id":"m1"}', encoding="utf-8")
            (working / "data" / "scripts").mkdir(parents=True)
            jar = workspace / "original" / "Arc" / "jars" / "M.jar"
            jar.parent.mkdir(parents=True)
            jar.write_bytes(b"PK\x03\x04")
            with mock.patch("bridgeforge.rebuild_jar.find_jdk", return_value=None):
                result = rebuild_jar(workspace, "working/data/scripts", "jars/M.jar", provider_roots=[])
            self.assertEqual(result["status"], "UNAVAILABLE")


class RebuildJarEndToEndTests(unittest.TestCase):
    """Real javac + jar packaging; skipped cleanly when no JDK is on PATH."""

    def setUp(self) -> None:
        javac = shutil.which("javac")
        if javac is None:
            self.skipTest("no javac on PATH")
        self.javac = Path(javac)

    def _build_original_jar(self, root: Path, java_source: str, dest: Path) -> None:
        src_dir = root / "orig-src"
        src_dir.mkdir(exist_ok=True)
        source = src_dir / "Foo.java"
        source.write_text(java_source, encoding="utf-8")
        classes = root / "orig-classes"
        classes.mkdir(exist_ok=True)
        completed = subprocess.run([str(self.javac), "--release", "17", "-d", str(classes), str(source)], capture_output=True, text=True, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(dest, "w") as archive:
            for class_file in classes.rglob("*.class"):
                archive.write(class_file, class_file.relative_to(classes).as_posix())

    def _make_workspace(self, root: Path) -> Path:
        workspace = root / "MyMod"
        (workspace / "working" / "jars").mkdir(parents=True)
        (workspace / "working" / "data" / "scripts").mkdir(parents=True)
        (workspace / "working" / "mod_info.json").write_text(
            '{"id":"mymod","name":"MyMod","author":"t","version":"1.0","gameVersion":"0.98a-RC8","jars":["jars/MyMod.jar"]}',
            encoding="utf-8",
        )
        return workspace

    ORIGINAL_SOURCE = (
        "package data.scripts;\n"
        "public class Foo {\n"
        "    public int add(int a, int b) { return a + b; }\n"
        "    public int sub(int a, int b) { return a - b; }\n"
        "}\n"
    )

    def test_pass_when_rebuild_matches_original(self) -> None:
        with resolved_temp_dir() as root:
            workspace = self._make_workspace(root)
            original_jar = workspace / "original" / "Arc" / "jars" / "MyMod.jar"
            self._build_original_jar(root, self.ORIGINAL_SOURCE, original_jar)
            shutil.copy2(original_jar, workspace / "working" / "jars" / "MyMod.jar")
            (workspace / "working" / "data" / "scripts" / "Foo.java").write_text(self.ORIGINAL_SOURCE, encoding="utf-8")
            result = rebuild_jar(workspace, "working/data/scripts", "jars/MyMod.jar", provider_roots=[])
            self.assertEqual(result["status"], "PASS", result)
            self.assertEqual(result["comparison"]["removed_classes"], [])
            self.assertEqual(result["comparison"]["class_changes"], [])

    def test_fail_when_rebuild_drops_a_method(self) -> None:
        with resolved_temp_dir() as root:
            workspace = self._make_workspace(root)
            original_jar = workspace / "original" / "Arc" / "jars" / "MyMod.jar"
            self._build_original_jar(root, self.ORIGINAL_SOURCE, original_jar)
            shutil.copy2(original_jar, workspace / "working" / "jars" / "MyMod.jar")
            reduced_source = (
                "package data.scripts;\n"
                "public class Foo {\n"
                "    public int add(int a, int b) { return a + b; }\n"
                "}\n"
            )
            (workspace / "working" / "data" / "scripts" / "Foo.java").write_text(reduced_source, encoding="utf-8")
            result = rebuild_jar(workspace, "working/data/scripts", "jars/MyMod.jar", provider_roots=[])
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["comparison"]["class_changes"][0]["methods_removed"], ["sub(II)I"])

    def test_review_when_rebuild_adds_a_method(self) -> None:
        with resolved_temp_dir() as root:
            workspace = self._make_workspace(root)
            original_jar = workspace / "original" / "Arc" / "jars" / "MyMod.jar"
            self._build_original_jar(root, self.ORIGINAL_SOURCE, original_jar)
            shutil.copy2(original_jar, workspace / "working" / "jars" / "MyMod.jar")
            expanded_source = (
                "package data.scripts;\n"
                "public class Foo {\n"
                "    public int add(int a, int b) { return a + b; }\n"
                "    public int sub(int a, int b) { return a - b; }\n"
                "    public int mul(int a, int b) { return a * b; }\n"
                "}\n"
            )
            (workspace / "working" / "data" / "scripts" / "Foo.java").write_text(expanded_source, encoding="utf-8")
            result = rebuild_jar(workspace, "working/data/scripts", "jars/MyMod.jar", provider_roots=[])
            self.assertEqual(result["status"], "REVIEW")

    def test_compile_failure_is_fail_with_no_comparison(self) -> None:
        with resolved_temp_dir() as root:
            workspace = self._make_workspace(root)
            original_jar = workspace / "original" / "Arc" / "jars" / "MyMod.jar"
            self._build_original_jar(root, self.ORIGINAL_SOURCE, original_jar)
            shutil.copy2(original_jar, workspace / "working" / "jars" / "MyMod.jar")
            (workspace / "working" / "data" / "scripts" / "Foo.java").write_text(
                "package data.scripts;\npublic class Foo { void use() { undefinedThing(); } }", encoding="utf-8"
            )
            result = rebuild_jar(workspace, "working/data/scripts", "jars/MyMod.jar", provider_roots=[])
            self.assertEqual(result["status"], "FAIL")
            self.assertIsNone(result["comparison"])
            self.assertEqual(result["compile"]["error_count"], 1)

    def test_install_refused_when_not_pass(self) -> None:
        with resolved_temp_dir() as root:
            workspace = self._make_workspace(root)
            original_jar = workspace / "original" / "Arc" / "jars" / "MyMod.jar"
            self._build_original_jar(root, self.ORIGINAL_SOURCE, original_jar)
            shutil.copy2(original_jar, workspace / "working" / "jars" / "MyMod.jar")
            reduced_source = (
                "package data.scripts;\n"
                "public class Foo {\n"
                "    public int add(int a, int b) { return a + b; }\n"
                "}\n"
            )
            (workspace / "working" / "data" / "scripts" / "Foo.java").write_text(reduced_source, encoding="utf-8")
            working_jar_before = (workspace / "working" / "jars" / "MyMod.jar").read_bytes()
            result = rebuild_jar(workspace, "working/data/scripts", "jars/MyMod.jar", provider_roots=[], install=True)
            self.assertEqual(result["status"], "FAIL")
            self.assertFalse(result["installed"])
            self.assertIn("refused", result["install_note"])
            self.assertFalse((workspace / "scratch").exists())
            self.assertEqual((workspace / "working" / "jars" / "MyMod.jar").read_bytes(), working_jar_before)

    def test_install_moves_old_jar_and_copies_new_one_on_pass(self) -> None:
        with resolved_temp_dir() as root:
            workspace = self._make_workspace(root)
            original_jar = workspace / "original" / "Arc" / "jars" / "MyMod.jar"
            self._build_original_jar(root, self.ORIGINAL_SOURCE, original_jar)
            shutil.copy2(original_jar, workspace / "working" / "jars" / "MyMod.jar")
            (workspace / "working" / "data" / "scripts" / "Foo.java").write_text(self.ORIGINAL_SOURCE, encoding="utf-8")
            result = rebuild_jar(workspace, "working/data/scripts", "jars/MyMod.jar", provider_roots=[], install=True)
            self.assertEqual(result["status"], "PASS")
            self.assertTrue(result["installed"])
            moved_to = Path(result["moved_original_to"])
            self.assertTrue(moved_to.is_file())
            installed_to = Path(result["installed_to"])
            self.assertTrue(installed_to.is_file())
            self.assertEqual(installed_to.read_bytes(), Path(result["new_jar"]).read_bytes())
            log_text = (workspace / "scratch" / "MOVES.log").read_text(encoding="utf-8")
            self.assertIn("moved working\\jars\\MyMod.jar", log_text)
            self.assertIn("rebuild-jar", log_text)


if __name__ == "__main__":
    unittest.main()
