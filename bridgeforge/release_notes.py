"""Changelog fragments (ROADMAP-3 item 80.1): `changelog.d/<slug>.md` files assembled into CHANGELOG.md.

Branches add a fragment instead of editing CHANGELOG.md, so they never conflict on it. `release-notes assemble` moves the
fragments under the top `## <version> (unreleased)` heading in file-name order and deletes them.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from .safeio import atomic_write_text

ROOT = Path(__file__).resolve().parent.parent
FRAGMENT_DIR = "changelog.d"
UNRELEASED_HEADING = re.compile(r"^##\s+(\S+)\s+\(unreleased\)\s*$")


class ReleaseNotesError(ValueError):
    pass


def pending_fragments(root: Path) -> list[Path]:
    folder = Path(root) / FRAGMENT_DIR
    if not folder.is_dir():
        return []
    return sorted((p for p in folder.glob("*.md") if p.name.lower() != "readme.md"), key=lambda p: p.name)


def fragment_bullet(path: Path) -> str:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ReleaseNotesError(f"{path.name}: empty fragment")
    return text if text.startswith("- ") else "- " + text


def insert_bullets(changelog: str, bullets: list[str], version: str | None) -> str:
    lines = changelog.splitlines()
    for index, line in enumerate(lines):
        match = UNRELEASED_HEADING.match(line)
        if match and (version is None or match.group(1) == version):
            break
    else:
        wanted = f"## {version} (unreleased)" if version else "## <version> (unreleased)"
        raise ReleaseNotesError(f"CHANGELOG.md has no '{wanted}' heading")
    at = index + 1
    while at < len(lines) and not lines[at].strip():
        at += 1
    merged = lines[: index + 1] + [""] + bullets + [""] + lines[at:]
    return "\n".join(merged) + "\n"


def assemble(root: Path, version: str | None = None, dry_run: bool = False) -> list[str]:
    """Returns the names of the fragments moved. Nothing is deleted unless CHANGELOG.md was written."""
    fragments = pending_fragments(root)
    if not fragments:
        return []
    bullets = [fragment_bullet(path) for path in fragments]
    changelog_path = Path(root) / "CHANGELOG.md"
    updated = insert_bullets(changelog_path.read_text(encoding="utf-8"), bullets, version)
    if not dry_run:
        atomic_write_text(changelog_path, updated, newline="")
        for path in fragments:
            path.unlink()
    return [path.name for path in fragments]


def add_parser(subcommands) -> None:
    notes = subcommands.add_parser("release-notes", help="changelog fragments: 'assemble' moves changelog.d/*.md under the top unreleased heading of CHANGELOG.md; '--check' lists the pending ones")
    notes.add_argument("action", nargs="?", choices=("assemble",), help="assemble the pending fragments into CHANGELOG.md")
    notes.add_argument("--version", help="the '## <version> (unreleased)' heading to use (default: the first one)")
    notes.add_argument("--check", action="store_true", help="list pending fragments; exit 1 when there are any")
    notes.add_argument("--dry-run", action="store_true", help="show what assemble would move, change nothing")
    notes.add_argument("--root", type=Path, default=ROOT, help="repository root (default: this checkout)")
    notes.add_argument("--json", action="store_true")


def run_cli(args: argparse.Namespace) -> int:
    root = Path(args.root)
    if args.check or not args.action:
        names = [p.name for p in pending_fragments(root)]
        if args.json:
            print(json.dumps({"pending": names}, indent=2))
        else:
            print(f"{len(names)} pending changelog fragment(s)")
            for name in names:
                print(f"  {FRAGMENT_DIR}/{name}")
        return 1 if names and args.check else 0
    try:
        moved = assemble(root, args.version, args.dry_run)
    except (ReleaseNotesError, OSError) as error:
        print(f"release-notes: {error}")
        return 2
    verb = "would move" if args.dry_run else "moved"
    if args.json:
        print(json.dumps({"moved": moved, "dry_run": bool(args.dry_run)}, indent=2))
    else:
        print(f"{verb} {len(moved)} fragment(s) into CHANGELOG.md")
        for name in moved:
            print(f"  {name}")
    return 0
