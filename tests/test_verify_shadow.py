from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.cli import main
from bridgeforge.scanner import verify_shadow
from tests.save_fixtures import build_class_file, write_jar


class VerifyShadowTests(unittest.TestCase):
    """ROADMAP P14 item 26: a direct, callable answer to "does this jar set actually supply a
    compiled class for this loose script" - reusing the same real class-file parsing item 14's
    fixer guard uses, not a `Path.is_file()` path-existence guess. Item 25/E12 found that guess
    trusted as proof of jar-shadowing for 50 of Rebal's loose .java files, none of which were
    actually shadowed.
    """

    def _write(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_not_shadowed_when_no_jar_supplies_the_class(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write(root / "data" / "hullmods" / "Foo.java", "package data.hullmods;\nclass Foo {}\n")
            core = root / "core"
            core.mkdir()
            result = verify_shadow(Path("data/hullmods/Foo.java"), core, root)
            self.assertEqual(result["status"], "NOT_SHADOWED")
            self.assertEqual(result["class_name"], "data.hullmods.Foo")
            self.assertEqual(result["shadowing_jars"], [])

    def test_shadowed_when_a_jar_in_the_against_directory_supplies_the_class(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write(root / "data" / "hullmods" / "Foo.java", "package data.hullmods;\nclass Foo {}\n")
            against = root / "jars"
            jar_path = against / "fixture.jar"
            write_jar(jar_path, {"data/hullmods/Foo.class": build_class_file("data/hullmods/Foo")})
            result = verify_shadow(Path("data/hullmods/Foo.java"), against, root)
            self.assertEqual(result["status"], "SHADOWED")
            self.assertEqual(result["shadowing_jars"], [str(jar_path)])

    def test_against_a_single_jar_file_not_a_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write(root / "data" / "hullmods" / "Foo.java", "package data.hullmods;\nclass Foo {}\n")
            jar_path = root / "jars" / "fixture.jar"
            write_jar(jar_path, {"data/hullmods/Foo.class": build_class_file("data/hullmods/Foo")})
            result = verify_shadow(Path("data/hullmods/Foo.java"), jar_path, root)
            self.assertEqual(result["status"], "SHADOWED")
            self.assertEqual(result["shadowing_jars"], [str(jar_path)])

    def test_script_outside_root_is_an_error_not_a_false_not_shadowed(self) -> None:
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as other:
            root = Path(directory)
            outside = Path(other) / "data" / "hullmods" / "Foo.java"
            self._write(outside, "class Foo {}\n")
            against = root / "jars"
            against.mkdir()
            result = verify_shadow(outside, against, root)
            self.assertEqual(result["status"], "ERROR")
            self.assertIn("not under root", result["error"])

    def test_cli_reports_shadowed_and_not_shadowed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write(root / "data" / "hullmods" / "Foo.java", "package data.hullmods;\nclass Foo {}\n")
            self._write(root / "data" / "hullmods" / "Bar.java", "package data.hullmods;\nclass Bar {}\n")
            against = root / "jars"
            write_jar(against / "fixture.jar", {"data/hullmods/Foo.class": build_class_file("data/hullmods/Foo")})
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                exit_code = main([
                    "verify-shadow", "data/hullmods/Foo.java",
                    "--against", str(against), "--root", str(root), "--json",
                ])
            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(out.getvalue())["status"], "SHADOWED")

            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                exit_code = main([
                    "verify-shadow", "data/hullmods/Bar.java",
                    "--against", str(against), "--root", str(root), "--json",
                ])
            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(out.getvalue())["status"], "NOT_SHADOWED")


if __name__ == "__main__":
    unittest.main()
