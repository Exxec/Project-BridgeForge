"""Author changelogs as hints for `research report` (ROADMAP-3 82.11). Reads only.

Finds obvious changelog files in a tree (CHANGELOG*, changelog*, *changes*.txt, release notes) and README sections titled changelog,
splits them by version heading where it can, and quotes the lines naming a feature term with file and line. Everything quoted is
labelled AUTHOR CLAIM: what the author says changed. It is weaker than STATIC and is only ever a hint to confirm in code.
"""
from __future__ import annotations

import re
from pathlib import Path

from .research_terms import AUTHOR_CLAIM, Matcher

CHANGELOG_NAME = re.compile(r"^(?:change[-_ ]?log|changes|release[-_ ]?notes|version[-_ ]?history|whats[-_ ]?new)[\w .-]*$|^[\w .-]*changes[\w .-]*\.txt$", re.IGNORECASE)
README_NAME = re.compile(r"^readme[\w .-]*$", re.IGNORECASE)
TEXT_EXTENSIONS = {"", ".txt", ".md", ".rst", ".markdown"}
SECTION_TITLE = re.compile(r"^\s*(?:#{1,6}\s*|=+\s*)?(?:change[-_ ]?log|version history|release notes|changes)\s*[:=#-]*\s*$", re.IGNORECASE)
VERSION_HEADING = re.compile(r"^\s*(?:#{1,6}\s*|=+\s*|\[\s*)?(?:version\s+|ver\.?\s*|v\s*)?(\d+(?:\.\d+){1,3}[A-Za-z]?(?:[-_.]?(?:rc|alpha|beta)\d*)?)\b[^\n]{0,60}$", re.IGNORECASE)
SKIPPED_DIRS = {"graphics", "sounds", ".git", "__pycache__", "native", "reports", "jars", "data"}
MAX_DEPTH = 2
MAX_FILE_BYTES = 2_000_000
MAX_FILES_PER_TREE = 12
MAX_LINES_PER_TERM_FILE = 6
LINE_TEXT_LIMIT = 220


def _candidates(root: Path) -> list[Path]:
    found: list[Path] = []
    for path in sorted(root.rglob("*")):
        parts = path.relative_to(root).parts
        if len(parts) > MAX_DEPTH + 1 or any(p in SKIPPED_DIRS for p in parts[:-1]) or not path.is_file():
            continue
        if path.suffix.lower() in TEXT_EXTENSIONS and (CHANGELOG_NAME.match(path.name) or README_NAME.match(path.name)):
            found.append(path)
    return found[:MAX_FILES_PER_TREE * 3]


def _read_lines(path: Path) -> list[str] | None:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        return path.read_bytes().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return None


def _section_start(lines: list[str], whole_file: bool) -> int | None:
    """Index of the first line to read: 0 for a changelog file; for a README, the line after a changelog-titled heading (None: no such section)."""
    if whole_file:
        return 0
    for index, line in enumerate(lines):
        if SECTION_TITLE.match(line):
            return index + 1
    return None


def _quote_lines(lines: list[str], start: int, matcher: Matcher, rel: str, tree_id: str, kind: str) -> list[dict]:
    version = None
    shown: dict[str, int] = {}
    quotes = []
    for index in range(start, len(lines)):
        line = lines[index]
        heading = VERSION_HEADING.match(line)
        if heading and len(line.strip()) <= 70:
            version = heading.group(1)
        for term in matcher.text_hits(line):
            shown[term] = shown.get(term, 0) + 1
            if shown[term] <= MAX_LINES_PER_TERM_FILE:
                quotes.append({"tree": tree_id, "term": term, "file": rel, "line": index + 1, "version": version, "kind": kind,
                               "text": line.strip()[:LINE_TEXT_LIMIT], "label": AUTHOR_CLAIM})
    return quotes


def changelog_files(root: Path) -> list[dict]:
    """`[{"file", "kind"}]` for the changelog files and README changelog sections under `root` (kind: `file` or `readme-section`)."""
    out = []
    for path in _candidates(root):
        lines = _read_lines(path)
        if lines is None:
            continue
        whole = bool(CHANGELOG_NAME.match(path.name))
        if _section_start(lines, whole) is not None:
            out.append({"file": path.relative_to(root).as_posix(), "kind": "file" if whole else "readme-section", "lines": len(lines)})
    return out[:MAX_FILES_PER_TREE]


def tree_changelog_quotes(root: Path, tree_id: str, matcher: Matcher) -> dict:
    """`{"files": [...], "quotes": [...]}` for one tree: every quoted line is an AUTHOR CLAIM with its version heading when one was found."""
    files = changelog_files(root)
    quotes: list[dict] = []
    for entry in files:
        lines = _read_lines(root / entry["file"]) or []
        start = _section_start(lines, entry["kind"] == "file") or 0
        quotes += _quote_lines(lines, start, matcher, entry["file"], tree_id, entry["kind"])
    return {"files": [{"tree": tree_id, **e} for e in files], "quotes": quotes}
