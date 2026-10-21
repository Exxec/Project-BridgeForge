"""ROADMAP-3 item 80.1: the merge driver for generated files and the regeneration script."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path

from tests.support import resolved_temp_dir

ROOT = Path(__file__).resolve().parent.parent


def load_tool(name: str):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, capture_output=True, text=True)


class MergeRegenTests(unittest.TestCase):
    def test_driver_takes_theirs_and_records_each_path_once(self) -> None:
        tool = load_tool("merge-regen")
        with resolved_temp_dir() as tmp:
            (tmp / "o").write_text("base", encoding="utf-8")
            (tmp / "a").write_text("ours", encoding="utf-8")
            (tmp / "b").write_text("theirs", encoding="utf-8")
            marker = tmp / "marker"
            self.assertEqual(tool.merge(str(tmp / "o"), str(tmp / "a"), str(tmp / "b"), "docs/COMMANDS.md", marker), 0)
            tool.merge(str(tmp / "o"), str(tmp / "a"), str(tmp / "b"), "docs/COMMANDS.md", marker)
            self.assertEqual((tmp / "a").read_text(encoding="utf-8"), "theirs")
            self.assertEqual(marker.read_text(encoding="utf-8"), "docs/COMMANDS.md\n")
            self.assertEqual(tool.main(["only", "three", "args"]), 2)

    def test_gitattributes_marks_the_generated_files_and_they_exist(self) -> None:
        text = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        tool = load_tool("regen-generated")
        for name in tool.GENERATED:
            self.assertIn(f"{name} merge=bfregen", text)
            self.assertTrue((ROOT / name).exists(), name)

    def test_real_git_merge_uses_the_driver(self) -> None:
        with resolved_temp_dir() as tmp:
            if git(tmp, "init", "-q", "-b", "main").returncode != 0:
                self.skipTest("git unavailable")
            driver = f'"{Path(sys.executable).as_posix()}" "{(ROOT / "tools" / "merge-regen.py").as_posix()}" %O %A %B %P'
            git(tmp, "config", "merge.bfregen.driver", driver)
            (tmp / ".gitattributes").write_text("gen.txt merge=bfregen\n", encoding="utf-8")
            (tmp / "gen.txt").write_text("1\n2\n3\n", encoding="utf-8")
            git(tmp, "add", "-A")
            git(tmp, "commit", "-qm", "base")
            git(tmp, "checkout", "-qb", "side")
            (tmp / "gen.txt").write_text("1\nside\n3\n", encoding="utf-8")
            git(tmp, "commit", "-qam", "side")
            git(tmp, "checkout", "-q", "main")
            (tmp / "gen.txt").write_text("1\nmain\n3\n", encoding="utf-8")
            git(tmp, "commit", "-qam", "main")
            result = git(tmp, "merge", "side", "-m", "merge")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual((tmp / "gen.txt").read_text(encoding="utf-8").replace("\r\n", "\n"), "1\nside\n3\n")
            self.assertEqual((tmp / ".git" / "bf-regen-needed").read_text(encoding="utf-8").strip(), "gen.txt")


if __name__ == "__main__":
    unittest.main()
