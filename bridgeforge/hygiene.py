"""`hygiene`: a read-only preflight before an agent session ends or a commit is made (ROADMAP-3 items 77.13 and 80.8).

It reports tracked files changed against HEAD (flagging a source file that shrank by more than half or lost public functions or
classes, the Project Go incident where an agent replaced InventoryFingerprint.java's API), untracked code files, ignored local
evidence folders (names only), interpreter and ruff availability, ruff over the tracked Python files and over the whole folder
(kept apart so a failing untracked script is never hidden), file names with private-use characters (mis-saved paths), and an
optional build command. It never deletes, moves, stages or writes into the repository, and it never opens an ignored file.

Exit codes: 0 clean, 1 findings, 2 cannot check. A check that could not run reports INCOMPLETE; an INCOMPLETE run is never clean.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

SHRINK_FRACTION = 0.5  # a tracked file that lost more than this share of its HEAD lines is flagged
RUFF_BATCH = 150  # tracked Python files per ruff call, to keep the command line short on Windows
BUILD_TIMEOUT_SECONDS = 1800
RUFF_TIMEOUT_SECONDS = 900
TAIL_LINES = 15
EXAMPLE_LIMIT = 10
CODE_SUFFIXES = frozenset({".py", ".java", ".kt", ".js", ".jsx", ".ts", ".tsx", ".cs", ".go", ".rs", ".c", ".cc", ".cpp", ".h",
                           ".hpp", ".rb", ".scala", ".swift", ".ps1", ".psm1", ".sh", ".bat", ".cmd"})
PRIVATE_USE = re.compile("[-]")  # a mis-saved name carries e.g. U+F03A where a colon belongs
JAVA_PUBLIC = re.compile(r"\bpublic\b[^;{=]*?\b([A-Za-z_]\w*)\s*[({]")
PYTHON_PUBLIC = re.compile(r"^(?:async\s+)?(?:def|class)\s+([A-Za-z]\w*)", re.MULTILINE)

PASS, FINDING, INCOMPLETE, INFO, SKIPPED, NOT_RUN = "PASS", "FINDING", "INCOMPLETE", "INFO", "SKIPPED", "NOT_RUN"


def _git(top: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=top, capture_output=True, encoding="utf-8", errors="replace")
    if done.returncode != 0:
        raise ValueError(f"git {' '.join(args)}: {done.stderr.strip()}")
    return done.stdout


def _entries(text: str) -> list[str]:
    return [entry for entry in text.split("\0") if entry]


def _public_names(path: str, text: str) -> set[str]:
    """Public top-level names of a source file; empty for languages this check does not model."""
    suffix = Path(path).suffix.lower()
    if suffix == ".py":
        return set(PYTHON_PUBLIC.findall(text))
    if suffix == ".java":
        return set(JAVA_PUBLIC.findall(text))
    return set()


def _head_text(top: Path, path: str) -> str | None:
    done = subprocess.run(["git", "show", f"HEAD:{path}"], cwd=top, capture_output=True, encoding="utf-8", errors="replace")
    return done.stdout if done.returncode == 0 else None


def _working_text(top: Path, path: str) -> str:
    full = top / path
    if not full.is_file():
        return ""
    return full.read_bytes().decode("utf-8", errors="replace")


def _modified_entries(top: Path) -> list[tuple[str, str, str | None]]:
    """(status, path, original path for a rename or copy) for each tracked file that differs from HEAD."""
    items = _entries(_git(top, "status", "--porcelain=v1", "-z", "--untracked-files=no"))
    result, index = [], 0
    while index < len(items):
        code, path = items[index][:2], items[index][3:]
        original = None
        if "R" in code or "C" in code:
            index += 1
            original = items[index]
        result.append((code, path, original))
        index += 1
    return result


def _check_modified(top: Path) -> dict:
    files = []
    for code, path, original in _modified_entries(top):
        head_path = original or path
        head = _head_text(top, head_path)
        flags, lost, before, now = [], [], None, None
        if head is not None:
            before = len(head.splitlines())
            current = _working_text(top, path) if "D" not in code else ""
            now = len(current.splitlines())
            if "D" in code:
                flags.append("deleted")
            if before and now < before * (1 - SHRINK_FRACTION):
                flags.append("shrunk")
            lost = sorted(_public_names(head_path, head) - _public_names(path, current))
            if lost:
                flags.append("lost_public_api")
        files.append({"path": path, "status": code.strip(), "flags": flags, "lines_before": before, "lines_now": now, "lost_public": lost})
    flagged = [item for item in files if item["flags"]]
    status = FINDING if flagged else PASS
    return {"status": status, "modified": len(files), "flagged": len(flagged), "files": files}


def _check_untracked(top: Path, paths: list[str]) -> dict:
    code_files = sorted(path for path in paths if Path(path).suffix.lower() in CODE_SUFFIXES)
    return {"status": FINDING if code_files else PASS, "untracked_files": len(paths), "code_files": code_files}


def _check_ignored(top: Path) -> dict:
    """Names only: ignored folders are collapsed, so their contents are never listed."""
    names = sorted(_entries(_git(top, "ls-files", "-z", "--others", "--ignored", "--exclude-standard", "--directory")))
    return {"status": INFO, "entries": names}


def _find_ruff() -> list[str] | None:
    """The first ruff that runs: a `ruff` on PATH, then `python -m ruff` for this interpreter, then for the `python` on PATH
    (the project venv has no ruff, so the system Python is the usual fallback)."""
    candidates: list[list[str]] = [["ruff"], [sys.executable, "-m", "ruff"]]
    system_python = shutil.which("python")
    if system_python:
        candidates.append([system_python, "-m", "ruff"])
    for candidate in candidates:
        try:
            probe = subprocess.run([*candidate, "--version"], capture_output=True, text=True)
        except OSError:
            continue
        if probe.returncode == 0:
            return candidate
    return None


def _check_interpreter(ruff: list[str] | None) -> dict:
    version = None
    if ruff:
        try:
            probe = subprocess.run([*ruff, "--version"], capture_output=True, text=True)
        except OSError:
            return {"status": INCOMPLETE, "python": sys.version.split()[0], "executable": sys.executable,
                    "ruff": {"available": False, "command": " ".join(ruff), "version": None}}
        version = probe.stdout.strip() or None
    return {"status": PASS if ruff else INCOMPLETE, "python": sys.version.split()[0], "executable": sys.executable,
            "ruff": {"available": ruff is not None, "command": " ".join(ruff) if ruff else None, "version": version}}


def _run_ruff(top: Path, ruff: list[str], paths: list[str]) -> tuple[list[dict], str | None]:
    """Ruff findings for `paths` (or the whole folder when `paths` is None), or an error text. Never writes a cache."""
    findings: list[dict] = []
    chunks = [paths[start:start + RUFF_BATCH] for start in range(0, len(paths), RUFF_BATCH)] if paths is not None else [["."]]
    for chunk in chunks:
        try:
            done = subprocess.run([*ruff, "check", "--no-cache", "--output-format", "json", "--", *chunk], cwd=top, capture_output=True,
                                  text=True, encoding="utf-8", errors="replace", timeout=RUFF_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            return findings, f"ruff timed out after {RUFF_TIMEOUT_SECONDS} seconds"
        if done.returncode not in (0, 1):
            return findings, (done.stderr.strip() or f"ruff exited {done.returncode}")[-500:]
        try:
            findings.extend(json.loads(done.stdout or "[]"))
        except json.JSONDecodeError:
            return findings, "ruff produced output that is not JSON"
    return findings, None


def _lint_result(findings: list[dict], error: str | None, scope: str) -> dict:
    examples = [f"{item.get('filename', '')}:{item.get('location', {}).get('row', '')} {item.get('code', '')} {item.get('message', '')}"
                for item in findings[:EXAMPLE_LIMIT]]
    if error is not None:
        return {"status": INCOMPLETE, "scope": scope, "findings": len(findings), "error": error, "examples": examples}
    return {"status": FINDING if findings else PASS, "scope": scope, "findings": len(findings), "examples": examples}


def _check_lint(top: Path, ruff: list[str] | None, tracked_python: list[str]) -> dict:
    if ruff is None:
        unavailable = {"status": INCOMPLETE, "error": "ruff is not installed for this interpreter (python -m pip install ruff)"}
        return {"tracked": {**unavailable, "scope": "tracked"}, "whole": {**unavailable, "scope": "whole"}}
    if not tracked_python:
        tracked = {"status": SKIPPED, "scope": "tracked", "findings": 0, "examples": [], "reason": "no tracked Python files"}
    else:
        tracked = _lint_result(*_run_ruff(top, ruff, tracked_python), "tracked")
    whole_findings, whole_error = _run_ruff(top, ruff, None)
    return {"tracked": tracked, "whole": _lint_result(whole_findings, whole_error, "whole")}


def _check_misnamed(paths: list[str]) -> dict:
    flagged = [path for path in paths if PRIVATE_USE.search(path)]
    return {"status": FINDING if flagged else PASS, "files": flagged}


def _check_build(top: Path, command: str | None) -> dict:
    if not command:
        return {"status": NOT_RUN}
    try:
        done = subprocess.run(command, shell=True, cwd=top, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=BUILD_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return {"status": FINDING, "command": command, "exit_code": None, "tail": [f"timed out after {BUILD_TIMEOUT_SECONDS} seconds"]}
    output = (done.stdout + done.stderr).splitlines()
    status = PASS if done.returncode == 0 else FINDING
    return {"status": status, "command": command, "exit_code": done.returncode, "tail": output[-TAIL_LINES:]}


def _overall(checks: dict) -> str:
    statuses = [check["status"] for check in _flatten(checks)]
    if FINDING in statuses:
        return FINDING
    return INCOMPLETE if INCOMPLETE in statuses else PASS


def _flatten(checks: dict) -> list[dict]:
    flat = []
    for value in checks.values():
        if "status" in value:
            flat.append(value)
        else:
            flat.extend(item for item in value.values() if isinstance(item, dict) and "status" in item)
    return flat


def check(repo: Path, build: str | None = None) -> dict:
    """Run every check on the git repository containing `repo`. Raises ValueError when `repo` is not inside a git repository."""
    top = Path(_git(Path(repo), "rev-parse", "--show-toplevel").strip())
    tracked = _entries(_git(top, "ls-files", "-z", "--cached"))
    untracked = _entries(_git(top, "ls-files", "-z", "--others", "--exclude-standard"))
    ignored = _check_ignored(top)
    ruff = _find_ruff()
    tracked_python = [path for path in tracked if path.endswith(".py") and (top / path).is_file()]
    checks = {
        "tracked_modified": _check_modified(top),
        "untracked_code": _check_untracked(top, untracked),
        "ignored_evidence": ignored,
        "interpreter": _check_interpreter(ruff),
        "lint": _check_lint(top, ruff, tracked_python),
        "misnamed_paths": _check_misnamed(tracked + untracked + ignored["entries"]),
        "build": _check_build(top, build),
    }
    return {"repo": top.as_posix(), "status": _overall(checks), "checks": checks}


def _summary_lines(result: dict) -> list[str]:
    checks = result["checks"]
    modified = checks["tracked_modified"]
    lines = [f"hygiene {result['repo']}: {result['status']}"]
    lines.append(f"  tracked modified: {modified['modified']} file(s), {modified['flagged']} flagged [{modified['status']}]")
    for item in modified["files"]:
        if item["flags"]:
            detail = f" lost {', '.join(item['lost_public'])}" if item["lost_public"] else ""
            lines.append(f"    FLAG {item['path']} ({', '.join(item['flags'])}; lines {item['lines_before']} -> {item['lines_now']}){detail}")
    untracked = checks["untracked_code"]
    lines.append(f"  untracked code files: {len(untracked['code_files'])} of {untracked['untracked_files']} untracked [{untracked['status']}]")
    lines.extend(f"    {path}" for path in untracked["code_files"])
    lines.append(f"  ignored evidence entries (names only): {len(checks['ignored_evidence']['entries'])}")
    lines.extend(f"    {name}" for name in checks["ignored_evidence"]["entries"])
    interpreter = checks["interpreter"]
    lines.append(f"  interpreter: Python {interpreter['python']}; ruff: {interpreter['ruff']['version'] or 'not available'} [{interpreter['status']}]")
    lines.extend(_lint_lines(checks["lint"]))
    misnamed = checks["misnamed_paths"]
    lines.append(f"  mis-saved names: {len(misnamed['files'])} [{misnamed['status']}]")
    lines.extend(f"    {path!r}" for path in misnamed["files"])
    build = checks["build"]
    if build["status"] != NOT_RUN:
        lines.append(f"  build `{build['command']}`: exit {build['exit_code']} [{build['status']}]")
        lines.extend(f"    {line}" for line in build["tail"])
    return lines


def _lint_lines(lint: dict) -> list[str]:
    lines = []
    for key in ("tracked", "whole"):
        item = lint[key]
        if "error" in item:
            lines.append(f"  lint {item['scope']}: {item['error']} [{item['status']}]")
            continue
        if item["status"] == SKIPPED:
            lines.append(f"  lint {item['scope']}: skipped ({item['reason']}) [{item['status']}]")
            continue
        lines.append(f"  lint {item['scope']}: {item['findings']} finding(s) [{item['status']}]")
        lines.extend(f"    {example}" for example in item["examples"])
        if item.get("error"):
            lines.append(f"    ruff error: {item['error']}")
    return lines


def add_parser(subcommands) -> None:
    command = subcommands.add_parser("hygiene", help="read-only agent preflight: modified and untracked files, shrunk or API-losing sources, "
                                     "mis-saved names, tracked and whole-folder ruff, optional build (exit 0 clean, 1 findings, 2 cannot check)")
    command.add_argument("repo_dir", nargs="?", type=Path, default=Path("."))
    command.add_argument("--json", action="store_true")
    command.add_argument("--build", metavar="CMD", help="shell command run in the repository root; its exit code is a finding when non-zero")


def run_cli(args: argparse.Namespace) -> int:
    try:
        result = check(args.repo_dir, args.build)
    except ValueError as exc:
        print(f"bridgeforge: hygiene cannot check: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2) if args.json else "\n".join(_summary_lines(result)))
    return {FINDING: 1, INCOMPLETE: 2}.get(result["status"], 0)
