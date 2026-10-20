"""`bridgeforge remove WORKSPACE PATH... --reason TEXT` (ROADMAP 77.27): a hand removal that leaves a record.

Files moved by hand into `scratch/removed/` carried no reason, so a mistaken move shipped (FIX-001). This moves each file from
`working/` to `<workspace>/scratch/removed/<YYYY-MM-DD>/<same relative path>`, writes a `files` entry per path to
`working/reports/REMOVALS.json`, and refuses while another file in `working/` still mentions the removed file's id (its name
without extension) or its path, unless `--force-dangling` (then the referencing files are written into the recorded reason).
"""
from __future__ import annotations

import os
import re
import shutil
import sys
from datetime import date
from pathlib import Path, PurePosixPath

from .removals import FILES_CATEGORY, REMOVALS_FILE, SOURCES, add_removals, covers, load_removals, make_entry
from .safeio import UnsafePathError, _is_link, safe_unlink

REMOVED_DIR = "scratch/removed"
TEXT_SUFFIXES = {".csv", ".json", ".ship", ".variant", ".wpn", ".skin", ".faction", ".proj", ".system", ".fighter", ".java",
                 ".txt", ".jason", ".mode", ".shot", ".market", ".map", ".kt", ".xml", ".properties", ".sm"}
MAX_REFERENCES_SHOWN = 8


class RemoveError(ValueError):
    """The removal was refused; nothing was moved."""


def _relative(working: Path, raw: str) -> str:
    text = raw.replace("\\", "/").strip()
    pure = PurePosixPath(text)
    if not text or pure.is_absolute() or re.match(r"^[A-Za-z]:", text) or ".." in pure.parts:
        raise RemoveError(f"{raw!r}: give a path below working/ (no absolute path, no `..`)")
    relative = pure.as_posix().removeprefix("./")
    if relative.casefold() == REMOVALS_FILE.casefold():
        raise RemoveError(f"{raw!r}: the removal record itself cannot be removed")
    current = working
    for part in PurePosixPath(relative).parts:
        current = current / part
        if _is_link(current):
            raise RemoveError(f"{raw!r}: {part} is a link or junction; refusing")
    if not current.is_file():
        raise RemoveError(f"{raw!r}: not a file in working/ ({'a folder' if current.is_dir() else 'missing'}); remove files one by one")
    return relative


def _text_files(working: Path, skip: set[str]) -> list[tuple[str, Path]]:
    found = []
    for current, dirs, files in os.walk(working):
        here = Path(current)
        dirs[:] = [d for d in dirs if not _is_link(here / d)]
        for name in files:
            path = here / name
            relative = path.relative_to(working).as_posix()
            if path.suffix.lower() in TEXT_SUFFIXES and relative.casefold() not in skip and relative != REMOVALS_FILE:
                found.append((relative, path))
    return found


def find_references(working: Path, relatives: list[str]) -> dict[str, list[str]]:
    """Per removed path, the other files in working/ whose text holds its id (stem) or its path. Files removed together ignore each other."""
    skip = {r.casefold() for r in relatives}
    patterns = {r: re.compile(rf"(?<!\w){re.escape(PurePosixPath(r).stem)}(?!\w)|{re.escape(r)}") for r in relatives}
    hits: dict[str, list[str]] = {r: [] for r in relatives}
    for relative, path in _text_files(working, skip):
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        for removed, pattern in patterns.items():
            if pattern.search(text):
                hits[removed].append(relative)
    return {r: files for r, files in hits.items() if files}


def _move(source: Path, destination: Path, working: Path) -> None:
    if destination.exists():
        raise RemoveError(f"{destination} already exists; refusing to overwrite an earlier removal")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(source, destination)
    except OSError:
        shutil.copy2(source, destination)
        try:
            safe_unlink(source, [working])
        except UnsafePathError as exc:
            raise RemoveError(str(exc)) from exc


def remove_files(workspace: Path, paths: list[str], *, reason: str, source: str = "owner", force_dangling: bool = False,
                 when: str | None = None) -> list[dict]:
    """Move `paths` out of working/ and record them; returns the recorded entries. Raises RemoveError (nothing moved) on refusal."""
    working = Path(workspace) / "working"
    if not working.is_dir():
        raise RemoveError(f"{workspace} has no working/ folder")
    if not isinstance(reason, str) or not reason.strip():
        raise RemoveError("--reason is required")
    if source not in SOURCES:
        raise RemoveError(f"--source must be one of {', '.join(SOURCES)}")
    relatives = list(dict.fromkeys(_relative(working, raw) for raw in paths))
    if not relatives:
        raise RemoveError("give at least one PATH")
    day = when or date.today().isoformat()
    references = find_references(working, relatives)
    note = ""
    if references:
        lines = [f"{removed} is still referenced by {', '.join(files[:MAX_REFERENCES_SHOWN])}"
                 + (f" (+{len(files) - MAX_REFERENCES_SHOWN} more)" if len(files) > MAX_REFERENCES_SHOWN else "")
                 for removed, files in references.items()]
        if not force_dangling:
            raise RemoveError("refusing, other files still reference what you remove (remove them together, repoint them, or "
                              "pass --force-dangling): " + "; ".join(lines))
        note = " [dangling references accepted: " + "; ".join(lines) + "]"
    entries = [make_entry(FILES_CATEGORY, item=r, reason=reason.strip() + note, source=source, when=day) for r in relatives]
    target_root = Path(workspace) / REMOVED_DIR / day
    for relative in relatives:
        _move(working / relative, target_root / relative, working)
    add_removals(working, entries)
    return entries


def unrecorded_removed_files(workspace_root: Path, working: Path) -> list[str]:
    """Files under `<workspace_root>/scratch/removed/` that no `files` REMOVALS entry of `working` covers (posix, relative to it)."""
    base = Path(workspace_root) / REMOVED_DIR
    if not base.is_dir():
        return []
    try:
        entries = [e for e in load_removals(working) if e["category"] == FILES_CATEGORY]
    except ValueError:
        entries = []
    missing = []
    for current, _dirs, files in os.walk(base):
        for name in files:
            relative = (Path(current) / name).relative_to(base).as_posix()
            parts = relative.split("/")
            candidates = {relative}
            if len(parts) > 1 and re.fullmatch(r"\d{4}-\d{2}-\d{2}", parts[0]):
                candidates.add("/".join(parts[1:]))
            if not any(covers(e, FILES_CATEGORY, c) for e in entries for c in candidates):
                missing.append(relative)
    return sorted(missing)


def add_parser(subcommands) -> None:
    cmd = subcommands.add_parser("remove", help="move files out of working/ into scratch/removed/<date>/ and record them in reports/REMOVALS.json; refuses while other files still reference them (ROADMAP 77.27)")
    cmd.add_argument("workspace", type=Path, help="the folder holding working/")
    cmd.add_argument("paths", nargs="+", metavar="PATH", help="file paths below working/")
    cmd.add_argument("--reason", required=True, help="why the file goes (recorded)")
    cmd.add_argument("--source", choices=SOURCES, default="owner", help="who decided (default owner)")
    cmd.add_argument("--force-dangling", action="store_true", help="remove although other files still reference it; the references are written into the recorded reason")


def run_cli(args) -> int:
    try:
        entries = remove_files(args.workspace, args.paths, reason=args.reason, source=args.source, force_dangling=args.force_dangling)
    except (RemoveError, ValueError) as exc:
        print(f"bridgeforge: {exc}", file=sys.stderr)
        return 2
    for entry in entries:
        print(f"removed {entry['item']} -> {REMOVED_DIR}/{entry['date']}/{entry['item']}")
    print(f"Recorded {len(entries)} file removal(s) in working/{REMOVALS_FILE}")
    return 0
