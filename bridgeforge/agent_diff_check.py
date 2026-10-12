"""`agent-diff-check`: look for destructive changes in an agent's branch before merging it (ROADMAP 70 H5).

An agent building a new module once overwrote the existing `bridgeforge/migrate.py` with new code (noticed, restored from git, no
harm). A branch that deletes a file, or cuts more than a fifth of an existing file, is not necessarily wrong, but it is exactly what a
reviewer must look at before a merge. Read-only: it runs `git diff --numstat` between the merge base and the branch.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

SHRINK_FRACTION = 0.2  # more than this share of the file's lines removed ...
SHRINK_MIN_LINES = 30  # ... and at least this many lines, to ignore tiny files


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if done.returncode != 0:
        raise ValueError(f"git {' '.join(args)}: {done.stderr.strip()}")
    return done.stdout


def check(repo: Path, branch: str, base: str = "main") -> dict:
    repo = Path(repo)
    merge_base = _git(repo, "merge-base", base, branch).strip()
    deleted = [line.split("\t", 1)[1] for line in _git(repo, "diff", "--name-status", "--diff-filter=D", f"{merge_base}..{branch}").splitlines()
               if "\t" in line]
    shrunk = []
    for line in _git(repo, "diff", "--numstat", "--diff-filter=M", f"{merge_base}..{branch}").splitlines():
        parts = line.split("\t")
        if len(parts) != 3 or not parts[0].isdigit() or not parts[1].isdigit():
            continue  # binary files show '-'
        added, removed, path = int(parts[0]), int(parts[1]), parts[2]
        before = _git(repo, "show", f"{merge_base}:{path}").count("\n")
        if removed >= SHRINK_MIN_LINES and before and removed / before > SHRINK_FRACTION:
            shrunk.append({"path": path, "lines_before": before, "removed": removed, "added": added, "share_removed": round(removed / before, 2)})
    return {"branch": branch, "base": base, "merge_base": merge_base, "deleted": deleted, "shrunk": sorted(shrunk, key=lambda s: -s["share_removed"])}


def add_parser(subcommands) -> None:
    command = subcommands.add_parser("agent-diff-check", help="before merging an agent's branch: list files it deleted and files it cut by more than a fifth (read-only, git only)")
    command.add_argument("branch")
    command.add_argument("--base", default="main")
    command.add_argument("--repo", type=Path, default=Path("."))
    command.add_argument("--json", action="store_true")


def run_cli(args: argparse.Namespace) -> int:
    try:
        result = check(args.repo, args.branch, args.base)
    except ValueError as exc:
        print(f"bridgeforge: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"{args.branch} vs {args.base}: {len(result['deleted'])} deleted file(s), {len(result['shrunk'])} file(s) cut by more than {SHRINK_FRACTION:.0%}")
        for path in result["deleted"]:
            print(f"  DELETED {path}")
        for item in result["shrunk"]:
            print(f"  SHRUNK  {item['path']}: {item['removed']} of {item['lines_before']} lines removed ({item['share_removed']:.0%}), {item['added']} added")
    return 1 if result["deleted"] or result["shrunk"] else 0
