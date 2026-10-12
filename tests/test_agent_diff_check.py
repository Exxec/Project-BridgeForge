"""ROADMAP 70 H5: an agent's branch is checked for deleted and sharply shrunk files before it is merged."""
from __future__ import annotations

import io
import subprocess
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from bridgeforge.agent_diff_check import check
from bridgeforge.cli import main
from tests.support import resolved_temp_dir


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=repo, check=True, capture_output=True)


def _repo(root: Path) -> Path:
    _git(root, "init", "-q", "-b", "main")
    (root / "keep.py").write_text("x = 1\n" * 100, encoding="utf-8")
    (root / "migrate.py").write_text("def apply_plan(): pass\n" * 200, encoding="utf-8")
    (root / "gone.py").write_text("y = 2\n", encoding="utf-8")
    (root / "tiny.py").write_text("a\nb\nc\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    return root


class AgentDiffCheckTests(unittest.TestCase):
    def test_a_deleted_file_and_a_rewritten_file_are_flagged_and_a_clean_addition_is_not(self) -> None:
        with resolved_temp_dir() as root:
            repo = _repo(root)
            _git(repo, "checkout", "-q", "-b", "agent")
            (repo / "migrate.py").write_text("def brand_new(): pass\n" * 20, encoding="utf-8")  # the 2026-10-12 near miss: an existing module overwritten
            (repo / "gone.py").unlink()
            (repo / "keep.py").write_text("x = 1\n" * 100 + "z = 3\n", encoding="utf-8")  # an addition only
            (repo / "tiny.py").write_text("a\n", encoding="utf-8")  # small: ignored
            (repo / "new_module.py").write_text("n = 1\n" * 50, encoding="utf-8")
            _git(repo, "add", "-A")
            _git(repo, "commit", "-q", "-m", "agent work")
            result = check(repo, "agent", "main")
            code = None
            out = io.StringIO()
            with redirect_stdout(out):
                code = main(["agent-diff-check", "agent", "--repo", str(repo)])
        self.assertEqual(result["deleted"], ["gone.py"])
        self.assertEqual([s["path"] for s in result["shrunk"]], ["migrate.py"])
        self.assertEqual(result["shrunk"][0]["share_removed"], 1.0)
        self.assertEqual(code, 1)
        self.assertIn("SHRUNK  migrate.py", out.getvalue())
        self.assertIn("DELETED gone.py", out.getvalue())

    def test_a_branch_that_only_adds_passes_and_an_unknown_branch_is_an_error(self) -> None:
        with resolved_temp_dir() as root:
            repo = _repo(root)
            _git(repo, "checkout", "-q", "-b", "agent")
            (repo / "added.py").write_text("n = 1\n", encoding="utf-8")
            _git(repo, "add", "-A")
            _git(repo, "commit", "-q", "-m", "add")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["agent-diff-check", "agent", "--repo", str(repo)]), 0)
                self.assertEqual(main(["agent-diff-check", "no-such-branch", "--repo", str(repo)]), 2)


if __name__ == "__main__":
    unittest.main()
