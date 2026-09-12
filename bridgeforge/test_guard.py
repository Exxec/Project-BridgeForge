"""Run tests while checking the checkout and ignored probe release stay unchanged."""
from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import sys


def snapshot(repo: Path) -> dict[str, str]:
    repo = repo.resolve()
    status = subprocess.check_output(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], cwd=repo)
    paths = subprocess.check_output(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=repo)
    result = {"<git-status>": hashlib.sha256(status).hexdigest()}
    for raw in paths.split(b"\0"):
        if not raw:
            continue
        name = raw.decode("utf-8", errors="surrogateescape")
        path = repo / name
        if path.is_symlink():
            result[name] = "link:" + str(path.readlink())
        elif path.is_file():
            result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            result[name] = "<missing>"
    release = repo / "probe-mod" / "releases" / "bridgeforge-probe"
    result["<probe-release>"] = "present" if release.exists() else "absent"
    if release.exists():
        for path in sorted(release.rglob("*")):
            name = path.relative_to(repo).as_posix()
            if path.is_symlink():
                result[name] = "link:" + str(path.readlink())
            elif path.is_file():
                result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
            elif path.is_dir():
                result[name] = "<directory>"
    return result


def changed_paths(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(key for key in before.keys() | after.keys() if before.get(key) != after.get(key))


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "--":
        args.pop(0)
    command = args or [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]
    repo = Path.cwd().resolve()
    before = snapshot(repo)
    try:
        code = subprocess.call(command, cwd=repo)
    finally:
        changes = changed_paths(before, snapshot(repo))
        if changes:
            print("Test hermeticity FAIL: checkout/probe release changed:", file=sys.stderr)
            for path in changes:
                print("  " + path, file=sys.stderr)
        else:
            print("Test hermeticity PASS: checkout and probe release unchanged.", flush=True)
    return 1 if changes else code


if __name__ == "__main__":
    raise SystemExit(main())
