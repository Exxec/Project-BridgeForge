"""ROADMAP-3 items 77.13 and 80.8: `hygiene` reports an agent's leftovers without changing the repository.

Every git-running test works on a synthetic repository in a temporary folder (tests.support clears the GIT_* variables first).
"""
from __future__ import annotations

import io
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from tests.support import resolved_temp_dir

from bridgeforge import hygiene
from bridgeforge.cli import main

PRIVATE_COLON = ""
CLEAN_RUFF = ([], None)
FAKE_RUFF = [sys.executable, "-c", "print('ruff 0.0.0')"]  # runs, prints a version, lints nothing


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=repo, check=True, capture_output=True,
                          text=True, encoding="utf-8")
    return done.stdout


def _repo(root: Path) -> Path:
    _git(root, "init", "-q", "-b", "main")
    (root / "app.py").write_text("".join(f"value_{n} = {n}\n" for n in range(60)) + "def run():\n    return 1\n", encoding="utf-8")
    (root / "Inventory.java").write_text(
        "public class Inventory {\n    public int count() { return 0; }\n    public void add(String item) { }\n"
        "    private int hidden() { return 1; }\n}\n", encoding="utf-8")
    (root / ".gitignore").write_text("local/\n", encoding="utf-8")
    (root / "notes.txt").write_text("notes\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    return root


def _status(repo: Path) -> str:
    return _git(repo, "status", "--porcelain=v1", "--ignored", "-uall")


class HygieneTests(unittest.TestCase):
    def _check(self, repo: Path, *, ruff_clean: bool = True, build: str | None = None) -> dict:
        """Run the check with ruff stubbed clean (or unavailable) so the git results do not depend on the ruff install."""
        with mock.patch.object(hygiene, "_find_ruff", return_value=FAKE_RUFF if ruff_clean else None), \
                mock.patch.object(hygiene, "_run_ruff", return_value=CLEAN_RUFF):
            return hygiene.check(repo, build)

    def test_clean_repository_passes_and_exits_zero(self) -> None:
        with resolved_temp_dir() as root:
            repo = _repo(root)
            result = self._check(repo)
            self.assertEqual(result["status"], hygiene.PASS)
            self.assertEqual(result["checks"]["tracked_modified"]["modified"], 0)
            with mock.patch.object(hygiene, "_find_ruff", return_value=FAKE_RUFF), mock.patch.object(hygiene, "_run_ruff", return_value=CLEAN_RUFF):
                self.assertEqual(main(["hygiene", str(repo)]), 0)

    def test_modified_file_is_listed_and_a_file_that_shrank_by_half_is_flagged(self) -> None:
        with resolved_temp_dir() as root:
            repo = _repo(root)
            (repo / "app.py").write_text("value_0 = 0\n", encoding="utf-8")
            (repo / "notes.txt").write_text("changed\nmore\n", encoding="utf-8")
            before = _status(repo)
            result = self._check(repo)
            files = {item["path"]: item for item in result["checks"]["tracked_modified"]["files"]}
            self.assertEqual(set(files), {"app.py", "notes.txt"})
            self.assertEqual(files["app.py"]["flags"], ["shrunk", "lost_public_api"])  # the one def it had is gone too
            self.assertEqual(files["notes.txt"]["flags"], [])
            self.assertEqual(result["status"], hygiene.FINDING)
            self.assertEqual(_status(repo), before, "the check must not change the repository")
            with mock.patch.object(hygiene, "_find_ruff", return_value=FAKE_RUFF), mock.patch.object(hygiene, "_run_ruff", return_value=CLEAN_RUFF):
                self.assertEqual(main(["hygiene", str(repo)]), 1)

    def test_java_file_that_lost_public_methods_is_flagged_even_when_not_shrunk(self) -> None:
        with resolved_temp_dir() as root:
            repo = _repo(root)
            (repo / "Inventory.java").write_text(
                "public class Inventory {\n    public int total() { return 0; }\n    public void add(String item) { }\n"
                "    private int hidden() { return 1; }\n    // padding\n    // padding\n}\n", encoding="utf-8")
            result = self._check(repo)
            item = result["checks"]["tracked_modified"]["files"][0]
            self.assertEqual(item["path"], "Inventory.java")
            self.assertIn("lost_public_api", item["flags"])
            self.assertNotIn("shrunk", item["flags"])
            self.assertEqual(item["lost_public"], ["count"])

    def test_python_api_loss_is_flagged_and_a_private_helper_is_not(self) -> None:
        with resolved_temp_dir() as root:
            repo = _repo(root)
            (repo / "app.py").write_text("".join(f"value_{n} = {n}\n" for n in range(60)) + "def helper():\n    return 1\n", encoding="utf-8")
            item = self._check(repo)["checks"]["tracked_modified"]["files"][0]
            self.assertEqual(item["lost_public"], ["run"])
            self.assertIn("lost_public_api", item["flags"])

    def test_deleted_tracked_file_is_flagged(self) -> None:
        with resolved_temp_dir() as root:
            repo = _repo(root)
            (repo / "notes.txt").unlink()
            item = self._check(repo)["checks"]["tracked_modified"]["files"][0]
            self.assertEqual(item["path"], "notes.txt")
            self.assertIn("deleted", item["flags"])

    def test_untracked_code_is_listed_by_extension_and_ignored_folders_are_names_only(self) -> None:
        with resolved_temp_dir() as root:
            repo = _repo(root)
            (repo / "scripts").mkdir()
            (repo / "scripts" / "helper.py").write_text("x = 1\n", encoding="utf-8")
            (repo / "scratch.md").write_text("# not code\n", encoding="utf-8")
            (repo / "local").mkdir()
            (repo / "local" / "evidence.bin").write_bytes(b"\x00secret-looking-data")
            result = self._check(repo)
            untracked = result["checks"]["untracked_code"]
            self.assertEqual(untracked["code_files"], ["scripts/helper.py"])
            self.assertEqual(untracked["status"], hygiene.FINDING)
            self.assertEqual(result["checks"]["ignored_evidence"]["entries"], ["local/"])
            self.assertNotIn("secret", str(result))

    def test_unicode_and_spaced_names_are_reported_intact(self) -> None:
        with resolved_temp_dir() as root:
            repo = _repo(root)
            (repo / "my notes.py").write_text("a = 1\n", encoding="utf-8")
            (repo / "café módulo.py").write_text("b = 2\n", encoding="utf-8")
            result = self._check(repo)
            self.assertEqual(sorted(result["checks"]["untracked_code"]["code_files"]), ["café módulo.py", "my notes.py"])

    def test_private_use_colon_in_a_name_is_flagged_as_mis_saved(self) -> None:
        with resolved_temp_dir() as root:
            repo = _repo(root)
            (repo / f"C{PRIVATE_COLON} Users notes.txt").write_text("stray\n", encoding="utf-8")
            result = self._check(repo)
            self.assertEqual(result["checks"]["misnamed_paths"]["status"], hygiene.FINDING)
            self.assertEqual(result["checks"]["misnamed_paths"]["files"], [f"C{PRIVATE_COLON} Users notes.txt"])

    def test_missing_ruff_reports_incomplete_and_exit_two_when_nothing_else_is_wrong(self) -> None:
        with resolved_temp_dir() as root:
            repo = _repo(root)
            result = self._check(repo, ruff_clean=False)
            lint = result["checks"]["lint"]
            self.assertEqual(lint["tracked"]["status"], hygiene.INCOMPLETE)
            self.assertEqual(lint["whole"]["status"], hygiene.INCOMPLETE)
            self.assertEqual(result["checks"]["interpreter"]["status"], hygiene.INCOMPLETE)
            self.assertEqual(result["status"], hygiene.INCOMPLETE)
            with mock.patch.object(hygiene, "_find_ruff", return_value=None):
                self.assertEqual(main(["hygiene", str(repo)]), 2)

    def test_findings_take_precedence_over_incomplete_checks(self) -> None:
        with resolved_temp_dir() as root:
            repo = _repo(root)
            (repo / "scripts.py").write_text("x = 1\n", encoding="utf-8")
            with mock.patch.object(hygiene, "_find_ruff", return_value=None):
                result = hygiene.check(repo)
            self.assertEqual(result["status"], hygiene.FINDING)

    def test_failing_build_command_is_a_finding_with_its_exit_code(self) -> None:
        with resolved_temp_dir() as root:
            repo = _repo(root)
            command = f'"{sys.executable}" -c "import sys; print(\'broken\'); sys.exit(3)"'
            result = self._check(repo, build=command)
            build = result["checks"]["build"]
            self.assertEqual((build["status"], build["exit_code"]), (hygiene.FINDING, 3))
            self.assertIn("broken", build["tail"])
            self.assertEqual(result["status"], hygiene.FINDING)

    def test_no_build_command_is_not_run(self) -> None:
        with resolved_temp_dir() as root:
            repo = _repo(root)
            self.assertEqual(self._check(repo)["checks"]["build"], {"status": hygiene.NOT_RUN})

    def test_folder_outside_git_exits_two(self) -> None:
        with resolved_temp_dir() as root:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(main(["hygiene", str(root)]), 2)

    def test_tracked_lint_is_separate_from_whole_folder_lint(self) -> None:
        if hygiene._find_ruff() is None:
            self.skipTest("ruff is not installed")
        with resolved_temp_dir() as root:
            repo = _repo(root)
            (repo / "app.py").write_text("import os\n", encoding="utf-8")  # tracked, unused import: a finding
            (repo / "scratch_agent.py").write_text("import sys\n", encoding="utf-8")  # untracked: whole-folder only
            lint = hygiene.check(repo)["checks"]["lint"]
            self.assertEqual(lint["tracked"]["findings"], 1)
            self.assertEqual(lint["whole"]["findings"], 2)
            self.assertIn("app.py", lint["tracked"]["examples"][0])
            self.assertEqual(lint["tracked"]["status"], hygiene.FINDING)

    def test_summary_text_names_flagged_files(self) -> None:
        with resolved_temp_dir() as root:
            repo = _repo(root)
            (repo / "app.py").write_text("value_0 = 0\n", encoding="utf-8")
            result = self._check(repo)
            text = "\n".join(hygiene._summary_lines(result))
            self.assertIn("FLAG app.py (shrunk, lost_public_api; lines 62 -> 1) lost run", text)


if __name__ == "__main__":
    unittest.main()
