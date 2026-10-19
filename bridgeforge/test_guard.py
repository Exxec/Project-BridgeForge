"""Run tests while checking the checkout and ignored probe release stay unchanged.

The default full-suite run also records its result in bridgeforge-state/last-suite.json (gitignored), so a commit
message can quote it with `python -m bridgeforge.test_guard --suite-line` instead of from memory; the line says so when code
changed after the suite ran (2026-10-11: a commit message once claimed a failure count the run did not have).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

RESULT_FILE = Path("bridgeforge-state") / "last-suite.json"
# Changes to these never invalidate a suite result: records and prose, not code the tests exercise.
RECORD_ONLY_PREFIXES = ("docs/", "ROADMAP.md", "ROADMAP-", "CHANGELOG.md", "MOD_CHANGELOG.md", "README.md", ".gitignore",
                        "bridgeforge/release_policy.json", "bridgeforge/automation_tiers.json")


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


def parse_unittest_output(lines: list[str]) -> dict:
    """Counts and failing test names from unittest's own summary lines."""
    ran = next((m for m in (re.match(r"Ran (\d+) tests? in", line) for line in reversed(lines)) if m), None)
    verdict = next((line for line in reversed(lines) if line.startswith(("OK", "FAILED"))), "")
    failures = re.search(r"failures=(\d+)", verdict)
    errors = re.search(r"errors=(\d+)", verdict)
    skipped = re.search(r"skipped=(\d+)", verdict)
    failed = [m.group(1) for m in (re.match(r"(?:FAIL|ERROR): (\S+)", line) for line in lines) if m]
    return {"tests": int(ran.group(1)) if ran else None, "failures": int(failures.group(1)) if failures else 0,
            "errors": int(errors.group(1)) if errors else 0, "skipped": int(skipped.group(1)) if skipped else 0,
            "failed_tests": failed, "verdict": verdict}


KNOWN_FAILURES_FILE = Path("tests") / "known_failures.json"


def load_known_failures(repo: Path) -> list[dict]:
    """Tests allowed to fail on this machine, each with a reason, the date it was added and an expiry date (ROADMAP 70 H1.8). A bare
    environmental failure on every full run taught everyone to read 'FAILED (failures=1)' as normal, which hides a second failure."""
    path = repo / KNOWN_FAILURES_FILE
    if not path.is_file():
        return []
    try:
        entries = json.loads(path.read_text(encoding="utf-8")).get("failures", [])
    except (OSError, ValueError):
        return []
    return [e for e in entries if isinstance(e, dict) and e.get("test")]


def apply_known_failures(counts: dict, known: list[dict], today: str) -> dict:
    """Split a run's failures into expected and unexpected. A known entry that has expired counts as unexpected again; one whose test now
    passes is listed so it can be removed."""
    failed = list(counts.get("failed_tests", []))
    active = {e["test"]: e for e in known if str(e.get("expires", "")) >= today}
    expired = [e["test"] for e in known if str(e.get("expires", "")) < today and e["test"] in failed]
    expected = [t for t in failed if t in active]
    unexpected = [t for t in failed if t not in active]
    total = counts.get("failures", 0) + counts.get("errors", 0)
    return {"expected": expected, "unexpected": unexpected, "expired": expired,
            "now_passing": [e["test"] for e in known if e["test"] not in failed],
            "uncounted": max(0, total - len(failed))}  # failures the summary reported but no FAIL/ERROR line named


def run_recorded_suite(repo: Path, command: list[str]) -> tuple[int, dict]:
    """Run the suite, echo its output as it comes, and return (exit code, parsed counts)."""
    process = subprocess.Popen(command, cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                               encoding="utf-8", errors="replace")
    lines: list[str] = []
    assert process.stdout is not None
    for line in process.stdout:
        lines.append(line.rstrip("\r\n"))
        print(line, end="", flush=True)
    return process.wait(), parse_unittest_output(lines)


def save_result(repo: Path, state: dict[str, str], counts: dict, code: int) -> None:
    path = repo / RESULT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    files = {name: digest for name, digest in state.items() if not name.startswith("<")}
    path.write_text(json.dumps({"finished": time.strftime("%Y-%m-%d %H:%M:%S"), "exit_code": code, **counts, "files": files}),
                    encoding="utf-8")


def suite_line(repo: Path) -> str:
    """The `Full suite:` line for a commit message, from the last recorded run; says so when code changed since it ran."""
    path = repo / RESULT_FILE
    if not path.is_file():
        return "Full suite: no recorded run (run `python -m bridgeforge.test_guard` first)."
    saved = json.loads(path.read_text(encoding="utf-8"))
    now = {name: digest for name, digest in snapshot(repo).items() if not name.startswith("<")}
    moved = changed_paths(saved["files"], now)
    code_moved = [name for name in moved if not name.startswith(RECORD_ONLY_PREFIXES)]
    known = saved.get("known_failures") or []
    failed = saved["failures"] + saved["errors"] - len(known)
    text = f"{saved['tests']} tests, {'OK' if not failed else str(failed) + ' failure(s)'} (skipped={saved['skipped']})"
    if known:
        text += f", {len(known)} known environmental failure(s): " + ", ".join(known)
    elif saved["failed_tests"]:
        text += " [" + ", ".join(saved["failed_tests"]) + "]"
    if code_moved:
        shown = ", ".join(code_moved[:4]) + (" ..." if len(code_moved) > 4 else "")
        return f"Full suite: NOT RERUN since code changed (last run {saved['finished']}: {text}); changed since: {shown}."
    note = f"; records only changed since: {len(moved)} file(s)" if moved else ""
    return f"Full suite: {text}; run {saved['finished']}{note}."


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "--":
        args.pop(0)
    if args == ["--suite-line"]:
        print(suite_line(Path.cwd().resolve()))
        return 0
    command = args or [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]
    repo = Path.cwd().resolve()
    before = snapshot(repo)
    counts: dict | None = None
    try:
        if args:
            code = subprocess.call(command, cwd=repo)
        else:
            code, counts = run_recorded_suite(repo, command)
    finally:
        changes = changed_paths(before, snapshot(repo))
        if changes:
            print("Test hermeticity FAIL: checkout/probe release changed:", file=sys.stderr)
            for path in changes:
                print("  " + path, file=sys.stderr)
        else:
            print("Test hermeticity PASS: checkout and probe release unchanged.", flush=True)
    if counts is not None and code != 0 and not changes:
        split = apply_known_failures(counts, load_known_failures(repo), time.strftime("%Y-%m-%d"))
        counts["known_failures"] = split["expected"]
        if split["expected"] and not split["unexpected"] and not split["uncounted"]:
            print(f"Known failure(s) only, not counted as a failure: {', '.join(split['expected'])} (tests/known_failures.json).", flush=True)
            code = 0
        for name in split["expired"]:
            print(f"Known failure EXPIRED, counts as a failure again: {name} (fix it or renew the entry with a reason).", file=sys.stderr)
        for name in split["now_passing"]:
            print(f"Known failure now passes: remove {name} from tests/known_failures.json.", flush=True)
    if counts is not None and not changes:
        save_result(repo, before, counts, code)
    return 1 if changes else code


if __name__ == "__main__":
    raise SystemExit(main())
