"""Tests run from a git hook must not reach the real repository through inherited GIT_* variables."""
import os
import subprocess
import unittest
from pathlib import Path

from tests.support import resolved_temp_dir

ROOT = Path(__file__).resolve().parents[1]


class HookGitEnvironmentTests(unittest.TestCase):
    def test_support_clears_git_variables(self):
        self.assertEqual([name for name in os.environ if name.startswith("GIT_")], [])

    def test_git_init_under_a_poisoned_git_dir_leaves_the_decoy_alone(self):
        with resolved_temp_dir() as root:
            decoy = root / "decoy"
            subprocess.run(["git", "init", "-q", str(decoy)], check=True, capture_output=True)
            env = {**os.environ, "GIT_DIR": str(decoy / ".git")}
            # What a hook-launched test would inherit, scrubbed the way tests/support.py does it.
            clean = {name: value for name, value in env.items() if not name.startswith("GIT_")}
            target = root / "target"
            subprocess.run(["git", "init", "-q", str(target)], check=True, capture_output=True, env=clean)
            bare = subprocess.run(["git", "-C", str(decoy), "config", "--get", "core.bare"], capture_output=True, text=True)
            self.assertEqual(bare.stdout.strip(), "false")
            self.assertTrue((target / ".git").is_dir())

    def test_the_pre_push_hook_clears_git_variables_before_its_tests(self):
        script = (ROOT / "tools" / "prepush-check.ps1").read_text(encoding="utf-8")
        clear = script.index("GIT_*")
        self.assertLess(clear, script.index("-m unittest"))


if __name__ == "__main__":
    unittest.main()
