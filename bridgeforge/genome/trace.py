"""94.G1 WP3 (GR-4): `trace ID` lists what cites a roadmap id: commits, the pull requests that merged them, tests and documents.

Read-only and offline: commits from `git log` of HEAD, pull requests from the "Merge pull request #N" commits whose merged
branch holds a citing commit, tests and documents from the checkout's tracked files. An id matches only whole: `94.G2` is
not `94.G21`, `96.1` is not `96.10`, and a sentence's full stop after it still counts.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

DOC_SUFFIXES = (".md", ".txt", ".json", ".yml", ".yaml", ".toml")
MERGE_PR = re.compile(r"^Merge pull request #(\d+)\b")
MAX_LINES_PER_FILE = 3


def id_pattern(item_id: str) -> re.Pattern[str]:
    """The id as a whole token: not inside a longer id, before or after."""
    return re.compile(r"(?<![\w.])" + re.escape(item_id) + r"(?![\w]|\.\d)")


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()[:200]}")
    return result.stdout


def citing_commits(root: Path, pattern: re.Pattern[str]) -> list[dict]:
    out = _git(root, "log", "--no-merges", "--format=%H%x1f%s%x1f%b%x1e", "HEAD")
    commits = []
    for record in out.split("\x1e"):
        parts = record.strip("\n").split("\x1f")
        if len(parts) < 3:
            continue
        sha, subject, body = parts[0].strip(), parts[1], parts[2]
        if pattern.search(subject) or pattern.search(body):
            commits.append({"commit": sha[:12], "subject": subject})
    return commits


def pull_requests(root: Path, commits: list[dict]) -> list[dict]:
    """The pull requests whose merge brought in one of `commits` (first-parent merges of HEAD named 'Merge pull request #N')."""
    if not commits:
        return []
    wanted = {c["commit"] for c in commits}
    found = []
    merges = _git(root, "log", "--merges", "--first-parent", "--format=%H%x1f%s", "HEAD")
    for line in merges.splitlines():
        sha, _, subject = line.partition("\x1f")
        number = MERGE_PR.match(subject)
        if not number:
            continue
        merged = {c[:12] for c in _git(root, "rev-list", f"{sha}^1..{sha}^2").split()}
        hits = sorted(wanted & merged)
        if hits:
            found.append({"pr": int(number.group(1)), "merge": sha[:12], "commits": hits})
    return sorted(found, key=lambda p: p["pr"])


def citing_files(root: Path, pattern: re.Pattern[str]) -> tuple[list[dict], list[dict]]:
    """(tests, documents): tracked files that cite the id, with up to three citing lines each."""
    tests, docs = [], []
    for relative in _git(root, "ls-files").splitlines():
        path = root / relative
        is_test = relative.startswith("tests/") and relative.endswith((".py", ".json"))
        is_doc = not relative.startswith("tests/") and relative.endswith(DOC_SUFFIXES) and not relative.startswith("bridgeforge/")
        if not (is_test or is_doc):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = [(n, line.strip()) for n, line in enumerate(text.splitlines(), 1) if pattern.search(line)]
        if lines:
            entry = {"path": relative, "count": len(lines),
                     "lines": [{"line": n, "text": t[:160]} for n, t in lines[:MAX_LINES_PER_FILE]]}
            (tests if is_test else docs).append(entry)
    return tests, docs


def trace(item_id: str, root: Path) -> dict:
    pattern = id_pattern(item_id)
    commits = citing_commits(Path(root), pattern)
    tests, docs = citing_files(Path(root), pattern)
    return {"id": item_id, "commits": commits, "pull_requests": pull_requests(Path(root), commits), "tests": tests, "documents": docs}


def render(result: dict) -> str:
    lines = [f"{result['id']}: {len(result['commits'])} commit(s), {len(result['pull_requests'])} pull request(s), "
             f"{len(result['tests'])} test file(s), {len(result['documents'])} document(s)"]
    for c in result["commits"]:
        lines.append(f"  commit {c['commit']} {c['subject'][:100]}")
    for p in result["pull_requests"]:
        lines.append(f"  PR #{p['pr']} (merge {p['merge']}): {', '.join(p['commits'])}")
    for kind in ("tests", "documents"):
        for f in result[kind]:
            first = f["lines"][0]
            lines.append(f"  {kind[:-1]} {f['path']}:{first['line']} ({f['count']} line(s)) {first['text'][:90]}")
    return "\n".join(lines)
