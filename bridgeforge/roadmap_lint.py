"""`roadmap-lint`: a ROADMAP item that says it is Done must name what proves it (ROADMAP 70 H3.3).

Claims in this project need evidence (CLAUDE.md). A roadmap entry marked `**Done` counts as evidenced when its text names a test
file or `Tests:` line, or a live test id (`GRP...-20261011`, `REG-...`, `LOAD-...`), or a `docs/` evidence file. The existing roadmap
has older entries that do not; `tests/roadmap_lint_baseline.json` lists them so new ones cannot join, and it may only shrink.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from .safeio import atomic_write_json

HEADER = re.compile(r"^(?P<indent>\s*)(?:- )?(?P<id>\d+[a-z]?(?:\.\d+)?)\. \*\*")
DONE = re.compile(r"\*\*(?:[A-Za-z0-9 ,()'/\-]*\s)?Done\b|\bDone 20\d\d-\d\d-\d\d|\*\*Done")
EVIDENCE = (re.compile(r"tests/[\w/]*test_\w+|\bTests?:|`tests\.test_"), re.compile(r"\b[A-Z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*-20\d{6}\b"),
            re.compile(r"docs/[\w\-/]+\.md"))
DEFAULT_ROADMAP = Path("ROADMAP.md")
DEFAULT_BASELINE = Path("tests") / "roadmap_lint_baseline.json"
# The roadmap is paged to stay under 64k tokens per file (owner 2026-10-18): ROADMAP.md, ROADMAP-2.md, ... Navigation
# notes sit between these markers, and a page that starts inside a section repeats its heading with "(continued)".
NAV = re.compile(r"<!-- page-nav:start -->.*?<!-- page-nav:end -->\n?", re.S)
CONTINUED_HEADING = re.compile(r"\A\s*## [^\n]* \(continued\)\n\n?")


def roadmap_pages(first: Path) -> list[Path]:
    """`first` and its continuation pages `<stem>-2<suffix>`, `<stem>-3<suffix>`, ... in order."""
    first = Path(first)
    # B1 relocated historical pages; preserve the old default/explicit path and the full evidence ratchet.
    archived = first.parent / "docs" / "archive" / first.name
    if first.name == "ROADMAP.md" and not first.is_file() and archived.is_file():
        pages = roadmap_pages(archived)
        n = len(pages) + 1
    else:
        pages, n = [first], 2
    while (page := first.with_name(f"{first.stem}-{n}{first.suffix}")).is_file():
        pages.append(page)
        n += 1
    return pages


def roadmap_text(first: Path) -> str:
    """The whole roadmap as one text: every page joined, navigation notes and repeated '(continued)' headings removed."""
    parts = []
    for i, page in enumerate(roadmap_pages(first)):
        part = NAV.sub("", page.read_text(encoding="utf-8").replace("\r\n", "\n"))
        if i:
            part = CONTINUED_HEADING.sub("", part)
        parts.append(part.strip("\n"))
    return "\n\n".join(parts) + "\n"


def items(text: str) -> list[dict]:
    """[{"key", "line", "text"}]: each numbered item with its continuation lines. `key` is the number plus the start of the title
    (the roadmap restarts numbering in later sections, and a key built from a count would shift when an item is inserted above)."""
    lines = text.splitlines()
    starts = [(i, HEADER.match(line)) for i, line in enumerate(lines)]
    starts = [(i, m) for i, m in starts if m]
    found = []
    for k, (i, m) in enumerate(starts):
        indent = len(m.group("indent"))
        end = next((j for j, n in starts[k + 1:] if len(n.group("indent")) <= indent), len(lines))
        title = re.sub(r"\s+", " ", lines[i][m.end():]).strip()[:60]
        found.append({"key": f"{m.group('id')}|{title}", "line": i + 1, "text": "\n".join(lines[i:end])})
    return found


def violations(text: str) -> list[dict]:
    out = []
    for item in items(text):
        header = item["text"].split("\n", 1)[0]
        if DONE.search(header) and not any(p.search(item["text"]) for p in EVIDENCE):
            out.append({"key": item["key"], "line": item["line"], "title": header.strip()[:100]})
    return out


def load_baseline(path: Path) -> set[str]:
    try:
        return set(json.loads(Path(path).read_text(encoding="utf-8")).get("items", []))
    except (OSError, ValueError):
        return set()


def add_parser(subcommands) -> None:
    lint = subcommands.add_parser("roadmap-lint", help="ROADMAP items marked Done must cite a test file, a Tests: line, a live test id or a docs/ evidence file; items listed in tests/roadmap_lint_baseline.json are tolerated")
    lint.add_argument("--roadmap", type=Path, default=DEFAULT_ROADMAP)
    lint.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    lint.add_argument("--all", action="store_true", help="also list the tolerated ones")
    lint.add_argument("--json", action="store_true")


def run_cli(args: argparse.Namespace) -> int:
    found = violations(roadmap_text(Path(args.roadmap)))
    tolerated = load_baseline(args.baseline)
    new = [v for v in found if v["key"] not in tolerated]
    if args.json:
        print(json.dumps({"new": new, "tolerated": [v for v in found if v["key"] in tolerated]}, indent=2))
    else:
        print(f"{len(new)} new and {len(found) - len(new)} tolerated Done item(s) without evidence")
        for v in (found if args.all else new):
            print(f"  line {v['line']} item {v['key']}: {v['title']}")
    return 1 if new else 0


if __name__ == "__main__":
    if "--write-baseline" in sys.argv:
        found = violations(roadmap_text(DEFAULT_ROADMAP))
        atomic_write_json(DEFAULT_BASELINE, {"schema_version": 1, "items": sorted(v["key"] for v in found)})
        print("wrote", DEFAULT_BASELINE, len(found))
