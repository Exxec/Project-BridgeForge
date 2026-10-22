"""Term search over one mod tree for `research report`: text files by line, jars by entry name and class-file bytes (STATIC, read-only)."""
from __future__ import annotations

import zipfile
from pathlib import Path

from .research_terms import Matcher
from .zipsafe import MAX_CLASS_BYTES, read_limited

TEXT_SUFFIXES = {".java", ".kt", ".csv", ".json", ".faction", ".variant", ".ship", ".wpn", ".skin", ".system", ".ini", ".txt",
                 ".md", ".properties", ".version", ".jsonc"}
SKIPPED_DIRS = {"graphics", "sounds", ".git", "__pycache__", "native"}
MAX_TEXT_BYTES = 3_000_000
MAX_LINES_PER_TERM_FILE = 3
MAX_JAR_ENTRIES = 100_000
LINE_TEXT_LIMIT = 160


def _walk(root: Path):
    for path in sorted(root.rglob("*")):
        parts = path.relative_to(root).parts
        if any(part in SKIPPED_DIRS for part in parts[:-1]) or parts[0] == "reports" or not path.is_file():
            continue
        yield path


def _text_hits(path: Path, rel: str, matcher: Matcher) -> list[dict]:
    try:
        if path.stat().st_size > MAX_TEXT_BYTES:
            return []
        lines = path.read_bytes().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return []
    shown: dict[str, int] = {}
    hits = []
    for number, line in enumerate(lines, 1):
        for term in matcher.text_hits(line):
            shown[term] = shown.get(term, 0) + 1
            if shown[term] <= MAX_LINES_PER_TERM_FILE:
                hits.append({"term": term, "file": rel, "line": number, "how": "text", "text": line.strip()[:LINE_TEXT_LIMIT]})
    return hits


def _jar_hits(path: Path, rel: str, matcher: Matcher) -> list[dict]:
    hits: list[dict] = []
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()[:MAX_JAR_ENTRIES]
            for info in infos:
                for term in matcher.name_hits(info.filename):
                    hits.append({"term": term, "file": f"{rel}!{info.filename}", "line": 0, "how": "jar-entry-name", "text": ""})
                if not info.filename.endswith(".class"):
                    continue
                try:
                    data = read_limited(archive, info, MAX_CLASS_BYTES).decode("latin-1")
                except (OSError, zipfile.BadZipFile):
                    continue
                for term in matcher.text_hits(data):
                    if not any(h["term"] == term and h["file"] == f"{rel}!{info.filename}" for h in hits):
                        hits.append({"term": term, "file": f"{rel}!{info.filename}", "line": 0, "how": "jar-class-bytes", "text": ""})
    except (OSError, zipfile.BadZipFile):
        return hits
    return hits


def search_tree(root: Path, matcher: Matcher) -> list[dict]:
    """Every hit of the matcher's terms under `root`, sorted. File names are matched too (`how: file-name`)."""
    hits: list[dict] = []
    for path in _walk(root):
        rel = path.relative_to(root).as_posix()
        for term in matcher.file_hits(rel):
            hits.append({"term": term, "file": rel, "line": 0, "how": "file-name", "text": ""})
        for term in matcher.name_hits(path.name):
            if term not in matcher.file_hits(rel):
                hits.append({"term": term, "file": rel, "line": 0, "how": "file-name", "text": ""})
        suffix = path.suffix.lower()
        if suffix == ".jar":
            hits += _jar_hits(path, rel, matcher)
        elif suffix in TEXT_SUFFIXES:
            hits += _text_hits(path, rel, matcher)
    return sorted(hits, key=lambda h: (h["term"], h["file"], h["line"], h["how"]))


def summarize(hits: list[dict]) -> dict[str, dict]:
    """Per term: hit count, distinct files and the first few evidence locations."""
    out: dict[str, dict] = {}
    for hit in hits:
        entry = out.setdefault(hit["term"], {"hits": 0, "files": set(), "examples": []})
        entry["hits"] += 1
        entry["files"].add(hit["file"])
        if len(entry["examples"]) < 5:
            entry["examples"].append(f"{hit['file']}:{hit['line']}" if hit["line"] else hit["file"])
    return {term: {"hits": e["hits"], "files": len(e["files"]), "examples": e["examples"]} for term, e in sorted(out.items())}
