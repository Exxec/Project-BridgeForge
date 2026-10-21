"""ROADMAP-3 item 80.1: merge-train with fake gh and git (no network)."""
from __future__ import annotations

import io
import re
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from bridgeforge.cli import main
from bridgeforge.merge_train import (
    CROSS_CUTTING_TESTS, Result, Train, TrainStop, keep_both_sides, parse_worktrees, test_modules_for,
)
from tests.support import resolved_temp_dir

ROOT = Path(__file__).resolve().parent.parent
CONFLICTED = "# Changelog\n<<<<<<< HEAD\n- main\n=======\n- branch\n>>>>>>> abc (msg)\n"


class FakeWorld:
    """Scripted gh/git: `rules` is a list of (regex on the joined command, Result or callable) tried in order."""

    def __init__(self, rules) -> None:
        self.rules, self.calls, self.now = list(rules), [], 0.0

    def __call__(self, command, cwd=None) -> Result:
        text = " ".join(command)
        self.calls.append(text)
        for pattern, answer in self.rules:
            if re.search(pattern, text):
                return answer(text) if callable(answer) else answer
        return Result(0)

    def sleep(self, seconds: float) -> None:
        self.now += seconds

    def clock(self) -> float:
        return self.now

    def train(self, **kw) -> Train:
        return Train(runner=self, sleep=self.sleep, clock=self.clock, python="py", log=lambda _m: None, **kw)

    def ran(self, pattern: str) -> bool:
        return any(re.search(pattern, c) for c in self.calls)


class MergeTrainTests(unittest.TestCase):
    def test_modules_cross_cutting_plus_touched_only_when_present(self) -> None:
        with resolved_temp_dir() as tmp:
            for name in ("test_foo.py", "test_foo_more.py", "test_other.py"):
                (tmp / name).write_text("", encoding="utf-8")
            for name in CROSS_CUTTING_TESTS:
                (tmp / (name.split(".")[1] + ".py")).write_text("", encoding="utf-8")
            got = test_modules_for(["bridgeforge/foo.py", "bridgeforge/nope.py", "docs/x.md"], tmp)
            self.assertEqual(got, [*CROSS_CUTTING_TESTS, "tests.test_foo", "tests.test_foo_more"])

    def test_prepush_script_lists_the_same_cross_cutting_tests(self) -> None:
        script = (ROOT / "tools" / "prepush-check.ps1").read_text(encoding="utf-8")
        for name in CROSS_CUTTING_TESTS:
            self.assertIn(f"'{name}'", script)
        self.assertIn("REVIVAL_REPORT", script)

    def test_keep_both_sides_drops_only_markers(self) -> None:
        self.assertEqual(keep_both_sides(CONFLICTED), "# Changelog\n- main\n- branch\n")

    def test_first_pr_merges_after_checks_register_and_pass(self) -> None:
        polls = iter(["", "", '[{"name":"ci"}]'])
        world = FakeWorld([(r"gh pr checks 1 --json", lambda _t: Result(0, next(polls)))])
        world.train().go(["1"], {})
        self.assertTrue(world.ran(r"gh pr checks 1 --watch"))
        self.assertTrue(world.ran(r"gh pr merge 1 --merge --delete-branch"))
        self.assertGreaterEqual(world.now, 30)  # polled twice before registration

    def test_no_checks_within_timeout_stops_without_merging(self) -> None:
        world = FakeWorld([(r"gh pr checks 1 --json", Result(1, ""))])
        with self.assertRaises(TrainStop):
            world.train(timeout=60, poll=15).go(["1"], {})
        self.assertFalse(world.ran("gh pr merge"))

    def test_failed_checks_do_not_merge_and_later_prs_do_not_start(self) -> None:
        world = FakeWorld([(r"gh pr checks 1 --json", Result(0, "[{}]")), (r"gh pr checks 1 --watch", Result(1))])
        with self.assertRaises(TrainStop):
            world.train().go(["1", "2"], {"2": Path("wt2")})
        self.assertFalse(world.ran("gh pr merge"))
        self.assertFalse(world.ran("rebase"))

    def test_second_pr_is_rebased_tested_pushed_then_merged(self) -> None:
        with resolved_temp_dir() as tmp:
            (tmp / "tests").mkdir()
            (tmp / "tests" / "test_foo.py").write_text("", encoding="utf-8")
            for name in CROSS_CUTTING_TESTS:
                (tmp / "tests" / (name.split(".")[1] + ".py")).write_text("", encoding="utf-8")
            world = FakeWorld([
                (r"gh pr checks \d --json", Result(0, "[{}]")),
                (r"git diff --name-only origin/main", Result(0, "bridgeforge/foo.py\nCHANGELOG.md\n")),
                (r"rev-parse HEAD", Result(0, "abc123\n")),
                (r"headRefOid", Result(0, "abc123\n")),
            ])
            world.train().go(["1", "2"], {"2": tmp})
            order = [i for i, c in enumerate(world.calls) if re.search(r"git rebase origin/main|-m unittest|--force-with-lease|gh pr merge 2", c)]
            self.assertEqual(len(order), 4)
            self.assertTrue(world.ran(r"-m unittest .*tests\.test_foo -q"))

    def test_changelog_and_generated_conflicts_resolve_and_regenerate(self) -> None:
        with resolved_temp_dir() as tmp:
            (tmp / "tests").mkdir()
            (tmp / "CHANGELOG.md").write_text(CONFLICTED, encoding="utf-8")
            state = {"rebase_continued": False}

            def continue_(_t):
                state["rebase_continued"] = True
                return Result(0)

            world = FakeWorld([
                (r"git rebase origin/main", Result(1)),
                (r"diff --name-only --diff-filter=U", Result(0, "CHANGELOG.md\ndocs/COMMANDS.md\n")),
                (r"rebase --continue", continue_),
                (r"diff --cached --quiet", Result(1)),
                (r"gh pr checks \d --json", Result(0, "[{}]")),
            ])
            world.train().go(["1", "2"], {"2": tmp})
            self.assertEqual((tmp / "CHANGELOG.md").read_text(encoding="utf-8"), "# Changelog\n- main\n- branch\n")
            self.assertTrue(world.ran(r"checkout --ours -- docs/COMMANDS.md"))
            self.assertTrue(state["rebase_continued"])
            self.assertTrue(world.ran(r"py -m bridgeforge docs-index"))
            self.assertTrue(world.ran(r"commit -m chore: regenerate"))

    def test_a_clean_rebase_still_regenerates_generated_files(self) -> None:
        # Two PRs that each add a command rebase without a conflict, yet the generated files list only one side's.
        with resolved_temp_dir() as tmp:
            (tmp / "tests").mkdir()
            world = FakeWorld([
                (r"git rebase origin/main", Result(0)),
                (r"diff --cached --quiet", Result(1)),
                (r"gh pr checks \d --json", Result(0, "[{}]")),
            ])
            world.train().go(["1", "2"], {"2": tmp})
            self.assertTrue(world.ran(r"py -m tests.test_cli_golden --write"))
            self.assertTrue(world.ran(r"commit -m chore: regenerate"))
            self.assertTrue(world.ran(r"gh pr merge 2"))

    def test_other_conflict_stops_before_tests_and_push(self) -> None:
        world = FakeWorld([
            (r"git rebase origin/main", Result(1)),
            (r"diff --name-only --diff-filter=U", Result(0, "CHANGELOG.md\nbridgeforge/x.py\n")),
            (r"gh pr checks \d --json", Result(0, "[{}]")),
        ])
        with self.assertRaisesRegex(TrainStop, r"bridgeforge/x\.py"):
            world.train().go(["1", "2"], {"2": Path("wt")})
        self.assertFalse(world.ran("unittest"))
        self.assertFalse(world.ran("push"))
        self.assertFalse(world.ran("gh pr merge 2"))

    def test_failing_tests_stop_before_push(self) -> None:
        world = FakeWorld([(r"-m unittest", Result(1)), (r"gh pr checks \d --json", Result(0, "[{}]"))])
        with self.assertRaisesRegex(TrainStop, "tests failed"):
            world.train().go(["1", "2"], {"2": Path("wt")})
        self.assertFalse(world.ran("push"))

    def test_cli_dry_run_prints_plan_and_validates_arguments(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(["merge-train", "10", "11", "--worktree", "11=C:/wt/b", "--dry-run"]), 0)
            self.assertEqual(main(["merge-train", "10", "--worktree", "99=x", "--dry-run"]), 2)
            self.assertEqual(main(["merge-train", "10", "--worktree", "bad", "--dry-run"]), 2)
        text = out.getvalue()
        self.assertIn("PR 11: in C:", text)
        self.assertIn("gh pr merge --merge --delete-branch", text)
        self.assertEqual(parse_worktrees(["#5=a"]), {"5": Path("a")})


if __name__ == "__main__":
    unittest.main()
