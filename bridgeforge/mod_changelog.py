"""MOD_CHANGELOG.md: the bigger updates to each revived mod, by date (owner request 2026-09-30).

CHANGELOG.md is the tool's history; this is the mods'. One section per date, newest first; one line per update:
"- **Mod Name** version: what changed". `archive` adds an entry for every mod it archives; anything else worth a line
(a new revision, a crash fixed after archiving, a translation) is added with `bridgeforge mod-changelog add`. Mod names
and versions only, never game or mod files.
"""
from __future__ import annotations

from .safeio import atomic_write_text

import re
from datetime import date
from pathlib import Path
from .paths import checkout_root

DEFAULT_PATH = checkout_root() / "MOD_CHANGELOG.md"
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


# Entries are fragments (ROADMAP-3 96.5 A7): Test1's `archive` and White_Legion's sessions both added lines to MOD_CHANGELOG.md,
# so two branches edited the same lines. Each entry is now one file in mod-changelog.d/ beside it, named by date, mod and a
# hash of the line, so the same entry made on both machines is the same file. Readers see the file and the fragments
# together; `release-notes assemble` folds the fragments into the file.
FRAGMENT_DIR = "mod-changelog.d"


def fragments_dir(path: Path | None = None) -> Path:
    return Path(path or DEFAULT_PATH).parent / FRAGMENT_DIR


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "mod"


def fragment_name(day: str, mod: str, line: str) -> str:
    import hashlib

    return f"{day}-{_slug(mod)}-{hashlib.sha256(line.encode('utf-8')).hexdigest()[:10]}.md"


def pending_fragments(path: Path | None = None) -> list[Path]:
    folder = fragments_dir(path)
    return sorted(p for p in folder.glob("*.md") if _DATE.match("## " + p.name[:10])) if folder.is_dir() else []


def sections(path: Path | None = None) -> dict[str, list[str]]:
    """The file's entries with every pending fragment added under its date (file order first, then fragment-name order)."""
    path = Path(path or DEFAULT_PATH)
    merged = _parse(path.read_text(encoding="utf-8")) if path.is_file() else {}
    for fragment in pending_fragments(path):
        line = fragment.read_text(encoding="utf-8").strip()
        lines = merged.setdefault(fragment.name[:10], [])
        if line.startswith("- ") and line not in lines:
            lines.append(line)
    return merged


def merged_text(path: Path | None = None) -> str:
    """MOD_CHANGELOG.md as it reads with the pending fragments folded in."""
    return render(sections(path))


def add_entry(mod: str, text: str, *, version: str | None = None, day: str | None = None, path: Path | None = None) -> str:
    """Add one line under its date (today by default), as a fragment beside the file. An identical line is not added twice."""
    path = Path(path or DEFAULT_PATH)
    line = entry_line(mod, version, text)
    day = day or date.today().isoformat()
    if line not in sections(path).get(day, []):
        atomic_write_text(fragments_dir(path) / fragment_name(day, mod, line), line + "\n", newline="")
    return line


def assemble(path: Path | None = None, *, dry_run: bool = False) -> list[str]:
    """Fold the pending fragments into the file and delete them; the fragment names folded, in order."""
    path = Path(path or DEFAULT_PATH)
    fragments = pending_fragments(path)
    if fragments and not dry_run:
        atomic_write_text(path, merged_text(path), newline="")
        for fragment in fragments:
            fragment.unlink()
    return [fragment.name for fragment in fragments]


# The lines written while 0.98a-RC8 was the only target say "RC8"; the same words keep a re-seed from adding a second line for each.
_LEGACY_LABELS = {"0.98a-RC8": "RC8"}
# The build an archive note's credit line names ("Revival for Starsector 0.98.5a-RC7: BridgeForge by Exxec."); a credit line
# for a revival whose build is not known names none ("Revival: BridgeForge by Exxec.", archive._render_note).
NOTE_BUILD = re.compile(r"Revival for Starsector (\S+?):")
NO_BUILD_CREDIT = "Revival: BridgeForge by Exxec."


def note_build(text: str) -> str | None:
    """The build an archive note says the mod was revived for. None when its credit line names no build. A note older than
    the credit line (`archive` has written one since 2026-09-27) is from when 0.98a-RC8 was the only target."""
    found = NOTE_BUILD.search(text)
    if found:
        return found.group(1)
    return None if NO_BUILD_CREDIT in text else "0.98a-RC8"


def build_label(build: str) -> str:
    """How the changelog and master log name a build: as the core reports it, except the legacy "RC8"."""
    return _LEGACY_LABELS.get(build, build)


def archived_text(build: str | None, status: str | None) -> str:
    """The changelog text for an archive, naming the build the mod was revived for (ROADMAP-3 96.5 A1: every line said RC8)."""
    state = (status or "no status").replace("_", " ").lower()
    return f"revived for {build_label(build)} and archived ({state})" if build else f"revived and archived ({state})"


def seed_from_archives(done: Path, path: Path | None = None) -> int:
    """One "archived" line per Done/<mod>/ARCHIVE_NOTE.md, under its archive date. Returns the lines added."""
    added = 0
    for note in sorted(Path(done).glob("*/ARCHIVE_NOTE.md")):
        text = note.read_text(encoding="utf-8", errors="replace")
        title = re.match(r"#\s*(.+?):\s*archive note", text)
        stamp = re.search(r"status: \*\*([A-Z_]+)\*\* \(archived (\d{4}-\d{2}-\d{2})\)", text)
        if not title or not stamp:
            continue
        before = merged_text(path)
        add_entry(title.group(1).strip(), archived_text(note_build(text), stamp.group(1)), day=stamp.group(2), path=path)
        added += merged_text(path) != before
    return added
