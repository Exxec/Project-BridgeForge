"""Find fixer backups whose file is gone (BUGS.md FIX-001).

`apply_fix` writes `<file>.pre-bf-fix-<id>.bak` (or `.bak.N`) next to every file it changes and keeps it. A backup with no
file beside it means the fixed file was lost after the fix: a shipped mod then silently lacks that file (All the Domain
Drones shipped without rules.csv, 2026-10-05). Backups under a `scratch` folder are by design and are ignored.
"""
from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

BACKUP_MARKER = ".pre-bf-fix-"
IGNORED_FOLDER = "scratch"


def backup_target(name: str) -> str | None:
    """`rules.csv` for `rules.csv.pre-bf-fix-data-file-not-utf8.bak[.N]`, else None."""
    target, marker, rest = name.partition(BACKUP_MARKER)
    if not marker or not target:
        return None
    base, bak, counter = rest.partition(".bak")
    if not bak or not base or (counter and not (counter.startswith(".") and counter[1:].isdigit())):
        return None
    return target


def orphaned_backups_in(relative_paths: list[str]) -> list[str]:
    """Backup paths (posix, relative) from a file listing that have no sibling file; case-insensitive like Windows."""
    present = {path.casefold() for path in relative_paths}
    orphans = []
    for relative in relative_paths:
        pure = PurePosixPath(relative)
        if IGNORED_FOLDER in (part.casefold() for part in pure.parts[:-1]):
            continue
        target = backup_target(pure.name)
        if target is not None and str(pure.with_name(target)).casefold() not in present:
            orphans.append(relative)
    return sorted(orphans)


def orphaned_backups(root: Path) -> list[str]:
    """Orphaned fixer backups under `root`, as posix paths relative to it."""
    listing: list[str] = []
    for folder, dirs, files in os.walk(root):
        relative = Path(folder).relative_to(root).as_posix()
        if relative != "." and IGNORED_FOLDER in (part.casefold() for part in relative.split("/")):
            dirs.clear()
            continue
        prefix = "" if relative == "." else relative + "/"
        listing.extend(prefix + name for name in files)
    return orphaned_backups_in(listing)
