"""MOD_CHANGELOG.md: the bigger updates to each revived mod, by date (owner request 2026-09-30).

CHANGELOG.md is the tool's history; this is the mods'. One section per date, newest first; one line per update:
"- **Mod Name** version: what changed". `archive` adds an entry for every mod it archives; anything else worth a line
(a new revision, a crash fixed after archiving, a translation) is added with `bridgeforge mod-changelog add`. Mod names
and versions only, never game or mod files.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "MOD_CHANGELOG.md"
HEADER = ("# Mod changelog\n\nBigger updates to revived mods, newest first. Tool changes are in CHANGELOG.md; each mod's "
          "evidence is in its revival report.\n")
_DATE = re.compile(r"^## (\d{4}-\d{2}-\d{2})\s*$")


def _parse(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = None
    for line in text.splitlines():
        found = _DATE.match(line)
        if found:
            current = sections.setdefault(found.group(1), [])
        elif current is not None and line.startswith("- "):
            current.append(line)
    return sections


def render(sections: dict[str, list[str]]) -> str:
    parts = [HEADER]
    for day in sorted(sections, reverse=True):
        parts.append(f"\n## {day}\n\n" + "\n".join(sections[day]) + "\n")
    return "".join(parts)


def entry_line(mod: str, version: str | None, text: str) -> str:
    return f"- **{mod}**" + (f" {version}" if version else "") + f": {text.strip()}"


def add_entry(mod: str, text: str, *, version: str | None = None, day: str | None = None, path: Path | None = None) -> str:
    """Add one line under its date (today by default). An identical line is not added twice."""
    path = Path(path or DEFAULT_PATH)
    sections = _parse(path.read_text(encoding="utf-8")) if path.is_file() else {}
    line = entry_line(mod, version, text)
    lines = sections.setdefault(day or date.today().isoformat(), [])
    if line not in lines:
        lines.append(line)
    path.write_text(render(sections), encoding="utf-8")
    return line


def seed_from_archives(done: Path, path: Path | None = None) -> int:
    """One "archived" line per Done/<mod>/ARCHIVE_NOTE.md, under its archive date. Returns the lines added."""
    added = 0
    for note in sorted(Path(done).glob("*/ARCHIVE_NOTE.md")):
        text = note.read_text(encoding="utf-8", errors="replace")
        title = re.match(r"#\s*(.+?):\s*archive note", text)
        stamp = re.search(r"status: \*\*([A-Z_]+)\*\* \(archived (\d{4}-\d{2}-\d{2})\)", text)
        if not title or not stamp:
            continue
        before = path.read_text(encoding="utf-8") if path and Path(path).is_file() else ""
        add_entry(title.group(1).strip(), f"revived for RC8 and archived ({stamp.group(1).replace('_', ' ').lower()})",
                  day=stamp.group(2), path=path)
        added += (Path(path or DEFAULT_PATH).read_text(encoding="utf-8") != before)
    return added
