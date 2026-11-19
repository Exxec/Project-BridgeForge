"""96.5 A2: one resolver for the checkout and the data folder, and the hygiene check for a stale installed copy."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from bridgeforge import paths
from bridgeforge.hygiene import FINDING, PASS, SKIPPED, _check_installed
from tests.support import resolved_temp_dir

ROOT = Path(__file__).resolve().parents[1]
# A data folder computed from a module's own location: the pattern A2 replaced with paths.data_root().
FILE_ROOT_TO_DATA = re.compile(r"Path\(__file__\)\.resolve\(\)\.(?:parent\.parent|parents\[2\])\s*/\s*\"(?:In operation|Done|bridgeforge-state)\"")


class PathsTests(unittest.TestCase):
    def test_without_the_variable_both_roots_are_the_checkout(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(paths.DATA_ROOT_ENV, None)
            self.assertEqual(paths.checkout_root(), ROOT)
            self.assertEqual(paths.data_root(), ROOT)
            self.assertEqual(paths.state_dir(), ROOT / "bridgeforge-state")
            self.assertEqual(paths.ops_dir(), ROOT / "In operation")
            self.assertEqual(paths.done_dir(), ROOT / "Done")

    def test_the_variable_names_the_data_root(self) -> None:
        with resolved_temp_dir() as data, mock.patch.dict(os.environ, {paths.DATA_ROOT_ENV: f"  {data}  "}):
            self.assertEqual(paths.data_root(), data)
            self.assertEqual(paths.state_dir(), data / "bridgeforge-state")
            self.assertEqual(paths.checkout_root(), ROOT)  # the source tree does not move

    def test_the_modules_defaults_follow_the_variable(self) -> None:
        # Module-level defaults are read at import, so ask a fresh interpreter.
        code = ("from bridgeforge.substitutes import REPO_ROOT; from bridgeforge.bytecode.java_toolchain import REPO_ROOT as J; "
                "from bridgeforge.targets import state_dir; from bridgeforge.rig.rig_doctor import _repo_root, _checkout_root; "
                "from bridgeforge.checks_index import REPO_ROOT as C; "
                "print(REPO_ROOT); print(J); print(state_dir()); print(_repo_root()); print(_checkout_root()); print(C)")
        with resolved_temp_dir() as data:
            env = {**os.environ, paths.DATA_ROOT_ENV: str(data)}
            done = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, check=True)
        lines = [Path(line) for line in done.stdout.splitlines()]
        self.assertEqual(lines[:4], [data, data, data / "bridgeforge-state", data])
        self.assertEqual(lines[4:], [ROOT, ROOT])  # the probe release copy and the docs stay in the source tree

    def test_no_module_computes_a_data_folder_from_its_own_location(self) -> None:
        found = []
        for path in sorted((ROOT / "bridgeforge").rglob("*.py")):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if FILE_ROOT_TO_DATA.search(line):
                    found.append(f"{path.relative_to(ROOT).as_posix()}:{number}")
        self.assertEqual(found, [], "use bridgeforge.paths.data_root()")
        self.assertTrue(FILE_ROOT_TO_DATA.search('x = Path(__file__).resolve().parent.parent / "Done"'))

    def test_the_suite_never_sees_the_variable(self) -> None:
        self.assertNotIn(paths.DATA_ROOT_ENV, os.environ)  # tests/support drops it
        from bridgeforge.test_guard import run_recorded_suite

        probe = [sys.executable, "-c", f"import os; print('seen=' + str('{paths.DATA_ROOT_ENV}' in os.environ))"]
        with mock.patch.dict(os.environ, {paths.DATA_ROOT_ENV: "C:/somewhere"}), mock.patch("builtins.print"):
            with mock.patch("bridgeforge.test_guard.parse_unittest_output", side_effect=lambda lines: {"lines": lines}):
                _, parsed = run_recorded_suite(ROOT, probe)
        self.assertIn("seen=False", parsed["lines"])


class _Dist:
    def __init__(self, version: str, direct: dict | None) -> None:
        self.version, self._direct = version, direct

    def read_text(self, name: str) -> str | None:
        return json.dumps(self._direct) if name == "direct_url.json" and self._direct is not None else None


class InstalledPackageCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.version = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M).group(1)
        self.url = ROOT.as_uri()

    def test_a_plain_install_is_a_finding(self) -> None:
        # White_Legion's .venv on 2026-11-18: a plain 0.4.0 copy, 68 files behind.
        result = _check_installed(ROOT, _Dist("0.4.0", {"url": self.url, "dir_info": {}}), main_checkout=Path("C:/main"))
        self.assertEqual(result["status"], FINDING)
        self.assertIn("frozen copy", result["reason"])
        self.assertIn('-e "' + str(Path("C:/main")) + '"', result["fix"])  # the main checkout, not a worktree

    def test_an_editable_install_at_another_version_is_a_finding(self) -> None:
        result = _check_installed(ROOT, _Dist("0.0.1", {"url": self.url, "dir_info": {"editable": True}}))
        self.assertEqual(result["status"], FINDING)
        self.assertIn("0.0.1", result["reason"])

    def test_an_editable_install_at_this_version_passes(self) -> None:
        result = _check_installed(ROOT, _Dist(self.version, {"url": self.url, "dir_info": {"editable": True}}))
        self.assertEqual(result["status"], PASS)
        self.assertEqual(Path(result["source"]).resolve(), ROOT)

    def test_no_install_is_skipped(self) -> None:
        with mock.patch("bridgeforge.hygiene._installed_distribution", return_value=None):
            self.assertEqual(_check_installed(ROOT)["status"], SKIPPED)

    def test_build_metadata_left_in_the_checkout_is_not_the_install(self) -> None:
        # 2026-11-18: run from White_Legion's main checkout, an old build's gitignored bridgeforge.egg-info (on sys.path as
        # the current folder) was found first, and a fresh editable install was reported as plain.
        from bridgeforge.hygiene import _installed_distribution

        with resolved_temp_dir() as checkout, resolved_temp_dir() as site:
            stale = checkout / "bridgeforge.egg-info"
            stale.mkdir()
            (stale / "PKG-INFO").write_text("Metadata-Version: 2.1\nName: bridgeforge\nVersion: 0.0.1\n", encoding="utf-8")
            real = site / "bridgeforge-9.9.9.dist-info"
            real.mkdir()
            (real / "METADATA").write_text("Metadata-Version: 2.1\nName: bridgeforge\nVersion: 9.9.9\n", encoding="utf-8")
            found = _installed_distribution(checkout, [str(checkout), str(site)])
            self.assertEqual(found.version, "9.9.9")
            self.assertIsNone(_installed_distribution(checkout, [str(checkout)]))


if __name__ == "__main__":
    unittest.main()
