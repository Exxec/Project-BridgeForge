"""`merge-train PR...`: merge pull requests one after another without hand-resolving the same conflicts (ROADMAP-3 item 80.1).

For each PR in the order given: wait until its checks are registered (polling up to 10 minutes), watch them, merge with
`--merge --delete-branch` on success. Before each following PR, rebase its branch (in the worktree given with
`--worktree PR=PATH`) onto origin/main. Conflicts are resolved automatically only in CHANGELOG.md (keep both sides) and in the
generated files (taken from origin/main, then regenerated); any other conflict stops the train with the rebase left in place.
The cross-cutting tests plus the test modules of the touched files run before a force-push with lease.

`gh` and `git` are reached only through a runner, so the tests use a fake and never touch the network.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from .safeio import atomic_write_text

CROSS_CUTTING_TESTS = (
    "tests.test_probe_contract",
    "tests.test_safeio_ratchet",
    "tests.test_checks_index",
    "tests.test_cli_golden",
    "tests.test_test_guard",
)
GENERATED_FILES = ("tests/cli_help_golden.json", "docs/COMMANDS.md", "docs/CHECKS.md")
CHANGELOG = "CHANGELOG.md"
CHECKS_TIMEOUT_SECONDS = 600
POLL_SECONDS = 15
MAX_REBASE_STEPS = 100
CONFLICT_MARKER = re.compile(r"^(<{7}( .*)?|={7}|>{7}( .*)?)$")


@dataclass(frozen=True)
class Result:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class Runner(Protocol):
    def __call__(self, command: list[str], cwd: Path | None = None) -> Result: ...


class TrainStop(Exception):
    """The train cannot go on; the message says why."""


def subprocess_runner(command: list[str], cwd: Path | None = None) -> Result:
    done = subprocess.run(command, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return Result(done.returncode, done.stdout, done.stderr)


def test_modules_for(changed: list[str], tests_dir: Path) -> list[str]:
    """Cross-cutting modules first, then tests/test_<name>*.py for each changed bridgeforge/<name>.py; only modules that exist."""
    modules = list(CROSS_CUTTING_TESTS)
    for path in changed:
        match = re.fullmatch(r"bridgeforge/([A-Za-z0-9_]+)\.py", path.replace("\\", "/"))
        if match:
            modules.extend(f"tests.{p.stem}" for p in sorted(Path(tests_dir).glob(f"test_{match.group(1)}*.py")))
    present = [m for m in modules if (Path(tests_dir) / (m.split(".", 1)[1] + ".py")).exists()]
    return list(dict.fromkeys(present))


def keep_both_sides(text: str) -> str:
    """Drop conflict marker lines, keeping the content of both sides."""
    return "".join(line for line in text.splitlines(keepends=True) if not CONFLICT_MARKER.match(line.rstrip("\r\n")))


class Train:
    def __init__(self, runner: Runner = subprocess_runner, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic, python: str = sys.executable,
                 timeout: float = CHECKS_TIMEOUT_SECONDS, poll: float = POLL_SECONDS, log: Callable[[str], None] = print) -> None:
        self.run, self.sleep, self.clock, self.python = runner, sleep, clock, python
        self.timeout, self.poll, self.log = timeout, poll, log

    # --- gh side -------------------------------------------------------------------------------------------------
    def _wait_head(self, pr: str, sha: str) -> None:
        deadline = self.clock() + self.timeout
        while self.run(["gh", "pr", "view", pr, "--json", "headRefOid", "-q", ".headRefOid"]).stdout.strip() != sha:
            if self.clock() >= deadline:
                raise TrainStop(f"PR {pr}: GitHub did not show the pushed head {sha[:10]} within {self.timeout:.0f}s")
            self.sleep(self.poll)

    def _wait_registered(self, pr: str) -> None:
        deadline = self.clock() + self.timeout
        while True:
            out = self.run(["gh", "pr", "checks", pr, "--json", "name,state"])
            if out.stdout.strip() not in ("", "[]"):
                return
            if self.clock() >= deadline:
                raise TrainStop(f"PR {pr}: no checks registered within {self.timeout:.0f}s")
            self.sleep(self.poll)

    def merge_when_green(self, pr: str, head_sha: str | None = None) -> None:
        if head_sha:
            self._wait_head(pr, head_sha)
        self._wait_registered(pr)
        self.log(f"PR {pr}: watching checks")
        if self.run(["gh", "pr", "checks", pr, "--watch"]).returncode != 0:
            raise TrainStop(f"PR {pr}: checks failed; not merged")
        merged = self.run(["gh", "pr", "merge", pr, "--merge", "--delete-branch"])
        if merged.returncode != 0:
            raise TrainStop(f"PR {pr}: merge failed: {merged.stderr.strip() or merged.stdout.strip()}")
        self.log(f"PR {pr}: merged")

    # --- git side ------------------------------------------------------------------------------------------------
    def _git(self, worktree: Path, *args: str) -> Result:
        return self.run(["git", *args], worktree)

    def _resolve_conflicts(self, worktree: Path) -> bool:
        """Resolve the current conflict if it is only CHANGELOG.md / generated files. Returns True when generated files were touched."""
        names = [n for n in self._git(worktree, "diff", "--name-only", "--diff-filter=U").stdout.split() if n]
        other = [n for n in names if n != CHANGELOG and n not in GENERATED_FILES]
        if not names or other:
            raise TrainStop(f"rebase stopped on a conflict in {', '.join(other) or 'unknown files'}; resolve it in {worktree}")
        regenerate = False
        for name in names:
            if name == CHANGELOG:
                target = Path(worktree) / name
                atomic_write_text(target, keep_both_sides(target.read_text(encoding="utf-8")), newline="")
            else:
                # during a rebase "ours" is the branch being rebased onto, i.e. origin/main; regenerated afterwards
                self._git(worktree, "checkout", "--ours", "--", name)
                regenerate = True
            self._git(worktree, "add", "--", name)
        return regenerate

    def rebase(self, worktree: Path) -> bool:
        """Rebase the worktree's branch onto origin/main. Returns True when generated files need regenerating."""
        if self._git(worktree, "fetch", "origin").returncode != 0:
            raise TrainStop("git fetch origin failed")
        regenerate = False
        result = self._git(worktree, "rebase", "origin/main")
        for _ in range(MAX_REBASE_STEPS):
            if result.returncode == 0:
                return regenerate
            regenerate = self._resolve_conflicts(worktree) or regenerate
            result = self.run(["git", "-c", "core.editor=true", "rebase", "--continue"], worktree)
        raise TrainStop("rebase did not finish")

    def regenerate(self, worktree: Path) -> None:
        for step in (("-m", "tests.test_cli_golden", "--write"), ("-m", "bridgeforge", "docs-index")):
            if self.run([self.python, *step], worktree).returncode != 0:
                raise TrainStop(f"regeneration failed: python {' '.join(step)}")
        self._git(worktree, "add", "--", *GENERATED_FILES)
        if self._git(worktree, "diff", "--cached", "--quiet").returncode != 0:
            self._git(worktree, "commit", "-m", "chore: regenerate generated files after rebase")

    def test(self, worktree: Path) -> None:
        changed = self._git(worktree, "diff", "--name-only", "origin/main...HEAD").stdout.split()
        modules = test_modules_for(changed, Path(worktree) / "tests")
        self.log(f"running {len(modules)} test module(s)")
        if self.run([self.python, "-m", "unittest", *modules, "-q"], worktree).returncode != 0:
            raise TrainStop(f"tests failed in {worktree}; not pushed")

    def prepare(self, pr: str, worktree: Path) -> str:
        """Rebase, regenerate if needed, test, force-push with lease. Returns the pushed head sha."""
        if self.rebase(worktree):
            self.regenerate(worktree)
        self.test(worktree)
        if self._git(worktree, "push", "--force-with-lease").returncode != 0:
            raise TrainStop(f"PR {pr}: force-push with lease failed")
        return self._git(worktree, "rev-parse", "HEAD").stdout.strip()

    # --- the whole train -----------------------------------------------------------------------------------------
    def go(self, prs: list[str], worktrees: dict[str, Path]) -> None:
        head_sha: str | None = None
        for index, pr in enumerate(prs):
            if index > 0:
                if pr in worktrees:
                    head_sha = self.prepare(pr, worktrees[pr])
                else:
                    self.log(f"PR {pr}: no --worktree given, merging without a rebase")
                    head_sha = None
            self.merge_when_green(pr, head_sha)
            head_sha = None


def plan(prs: list[str], worktrees: dict[str, Path]) -> list[str]:
    lines: list[str] = []
    for index, pr in enumerate(prs):
        if index > 0:
            if pr in worktrees:
                lines += [f"PR {pr}: in {worktrees[pr]}: git fetch origin; git rebase origin/main",
                          "  conflicts: CHANGELOG.md keep both sides; generated files take origin/main then regenerate; anything else stops",
                          "  run tests: " + ", ".join(CROSS_CUTTING_TESTS) + " + modules of touched bridgeforge/*.py",
                          "  git push --force-with-lease"]
            else:
                lines.append(f"PR {pr}: no --worktree given, no rebase")
        lines.append(f"PR {pr}: wait for checks (up to {CHECKS_TIMEOUT_SECONDS // 60} min to register), gh pr checks --watch, gh pr merge --merge --delete-branch")
    return lines


def parse_worktrees(values: list[str]) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for value in values:
        pr, separator, path = value.partition("=")
        if not separator or not pr or not path:
            raise ValueError(f"--worktree wants PR=PATH, got {value!r}")
        found[pr.lstrip("#")] = Path(path)
    return found


def add_parser(subcommands) -> None:
    train = subcommands.add_parser("merge-train", help="merge pull requests in order with gh: wait for checks, merge, rebase the next branch onto origin/main (CHANGELOG.md keeps both sides, generated files regenerate), test, force-push with lease")
    train.add_argument("prs", nargs="+", metavar="PR", help="pull request numbers, in merge order")
    train.add_argument("--worktree", action="append", default=[], metavar="PR=PATH", help="the worktree where that PR's branch is checked out (needed to rebase it)")
    train.add_argument("--dry-run", action="store_true", help="print the plan, run nothing")
    train.add_argument("--python", default=sys.executable, help="interpreter for the tests and the regeneration (default: this one)")
    train.add_argument("--timeout-minutes", type=float, default=CHECKS_TIMEOUT_SECONDS / 60, help="how long to wait for checks to register")


def run_cli(args: argparse.Namespace) -> int:
    try:
        worktrees = parse_worktrees(args.worktree)
    except ValueError as error:
        print(f"merge-train: {error}")
        return 2
    prs = [p.lstrip("#") for p in args.prs]
    unknown = sorted(set(worktrees) - set(prs))
    if unknown:
        print(f"merge-train: --worktree names PR(s) not in the train: {', '.join(unknown)}")
        return 2
    if args.dry_run:
        print("\n".join(plan(prs, worktrees)))
        return 0
    try:
        Train(python=args.python, timeout=args.timeout_minutes * 60).go(prs, worktrees)
    except TrainStop as stop:
        print(f"merge-train: stopped: {stop}")
        return 1
    print(f"merge-train: {len(prs)} PR(s) merged")
    return 0
