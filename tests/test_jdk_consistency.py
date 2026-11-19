"""96.5 C6: CI and a local run compile with the same JDK, and every test javac names its source encoding."""
from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

from bridgeforge.bytecode.java_toolchain import find_jdk, jdk_major
from tests.support import javac_path, project_jdk_major, resolved_temp_dir
from tests.test_java_toolchain import _touch_javac

ROOT = Path(__file__).resolve().parents[1]
STEP = re.compile(r"^\s*- (?:name:|uses:)", re.MULTILINE)


def setup_java_steps(workflow_text: str) -> list[str]:
    """The text of each step that uses actions/setup-java."""
    starts = [match.start() for match in STEP.finditer(workflow_text)] + [len(workflow_text)]
    steps = [workflow_text[start:end] for start, end in zip(starts, starts[1:])]
    return [step for step in steps if "actions/setup-java" in step]


def javac_lists_without_encoding(source: str) -> list[int]:
    """Lines of list literals whose first element is a javac and which pass no `-encoding`.

    Without it javac reads a source in the platform's encoding: UTF-8 on the Ubuntu runners, the ANSI code page on
    Windows, so a fixture with a non-ASCII character compiles on one and not the other. A starred
    `DEFAULT_JAVAC_ARGS` carries it."""
    lines = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.List) or not node.elts:
            continue
        if "javac" not in ast.unparse(node.elts[0]).lower():
            continue
        rest = node.elts[1:]
        if any(isinstance(element, ast.Constant) and element.value == "-encoding" for element in rest):
            continue
        if any(isinstance(element, ast.Starred) and "DEFAULT_JAVAC_ARGS" in ast.unparse(element) for element in rest):
            continue
        lines.append(node.lineno)
    return lines


class SameJdkTests(unittest.TestCase):
    def test_java_version_file_names_one_feature_version(self) -> None:
        self.assertIsNotNone(project_jdk_major(), ".java-version must hold one number, e.g. 25")

    def test_every_setup_java_step_reads_the_java_version_file(self) -> None:
        workflows = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
        checked = 0
        for workflow in workflows:
            for step in setup_java_steps(workflow.read_text(encoding="utf-8")):
                checked += 1
                with self.subTest(workflow=workflow.name):
                    self.assertIn("java-version-file: .java-version", step)
                    self.assertNotRegex(step, r"java-version:\s")
        self.assertGreater(checked, 0)

    def test_the_step_reader_sees_a_hardcoded_version(self) -> None:
        text = ("    steps:\n      - uses: actions/checkout@v7\n      - uses: actions/setup-java@v6\n        with:\n"
                "          distribution: temurin\n          java-version: \"17\"\n      - name: Next\n        run: x\n")
        steps = setup_java_steps(text)
        self.assertEqual(len(steps), 1)
        self.assertRegex(steps[0], r"java-version:\s")
        self.assertNotIn("Next", steps[0])

    def test_the_local_jdk_is_the_one_ci_uses(self) -> None:
        javac = javac_path()
        if javac is None:
            self.skipTest("no JDK found")
        major = jdk_major(Path(javac).resolve().parent.parent)
        if major != project_jdk_major():
            self.skipTest(f"local JDK {major} differs from .java-version {project_jdk_major()}: install that JDK")
        self.assertEqual(major, project_jdk_major())


class JdkMajorTests(unittest.TestCase):
    def test_the_release_file_gives_the_feature_version(self) -> None:
        with resolved_temp_dir() as root:
            (root / "release").write_text('IMPLEMENTOR="x"\nJAVA_VERSION="25.0.5"\n', encoding="utf-8")
            self.assertEqual(jdk_major(root), 25)
            (root / "release").write_text('JAVA_VERSION="1.8.0_512"\n', encoding="utf-8")
            self.assertEqual(jdk_major(root), 8)
            (root / "release").unlink()
            self.assertIsNone(jdk_major(root))

    def test_a_preferred_version_wins_over_the_search_order(self) -> None:
        with resolved_temp_dir() as root:
            rig = root / "repo" / "In operation" / "_rig"
            for name, version in (("jdk-17", "17.0.12"), ("jdk-25", "25.0.5")):
                _touch_javac(rig / name)
                (rig / name / "release").write_text(f'JAVA_VERSION="{version}"\n', encoding="utf-8")
            self.assertEqual(find_jdk(repo_root=root / "repo").home.name, "jdk-17")
            self.assertEqual(find_jdk(repo_root=root / "repo", prefer_major=25).home.name, "jdk-25")
            self.assertEqual(find_jdk(repo_root=root / "repo", prefer_major=21).home.name, "jdk-17")  # none matches


class TestJavacEncodingTests(unittest.TestCase):
    def test_every_test_javac_names_its_source_encoding(self) -> None:
        missing = {}
        for path in sorted((ROOT / "tests").glob("*.py")):
            lines = javac_lists_without_encoding(path.read_text(encoding="utf-8-sig"))
            if lines:
                missing[path.name] = lines
        self.assertEqual(missing, {}, "add \"-encoding\", \"UTF-8\" after the javac")

    def test_the_detector_cases(self) -> None:
        source = (
            'a = [javac, "-d", out]\n'
            'b = [str(self.jdk.javac), "-encoding", "UTF-8", "-d", out]\n'
            'c = ["javac", *DEFAULT_JAVAC_ARGS, "-d", out]\n'
            'd = ["java", "-version"]\n'
            'e = ["javac"]\n'
        )
        self.assertEqual(javac_lists_without_encoding(source), [1, 5])


if __name__ == "__main__":
    unittest.main()
