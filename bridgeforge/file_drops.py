"""File-level drops for `dropped-features` (ROADMAP 77.19 extension): files under `data/` the older tree had and `working/` lacks.

Not counted as drops: a path that exists in the vanilla core (the mod only overrode it; skipped, and reported as such, when no
core is given) and a `.java` source whose class ships in one of the working copy's jars (the source moved into the jar).
"""
from __future__ import annotations

import fnmatch
import os
import re
import zipfile
from pathlib import Path

DATA = "data"
_PACKAGE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.M)
_JUNK_GLOBS = ("*.old", "*~", "*.bak", "*.bak.*", "*.pre-bf-*", "*.log", "*.lnk", "*.rar", "*.zip", "*.7z", "desktop.ini", "thumbs.db")
_JUNK_MARKERS = ("копия", "副本", " - copy", "copy of ", "(copy)")


def is_junk_file(path: str) -> bool:
    """True for editor/OS/archive leftovers (backups, logs, shortcuts, archives, `- Copy` files) that are never a mod feature."""
    name = path.replace("\\", "/").rsplit("/", 1)[-1].casefold()
    return any(fnmatch.fnmatchcase(name, glob) for glob in _JUNK_GLOBS) or any(marker in name for marker in _JUNK_MARKERS)


def _data_files(tree: Path) -> list[str]:
    base = Path(tree) / DATA
    found: list[str] = []
    for current, _dirs, files in os.walk(base):
        for name in files:
            found.append((Path(current) / name).relative_to(tree).as_posix())
    return sorted(found)


def shipped_classes(working: Path) -> set[str]:
    """Slash-separated class paths (`pkg/Name.class`) inside every jar below `working/`."""
    classes: set[str] = set()
    for current, _dirs, files in os.walk(working):
        for name in files:
            if name.lower().endswith(".jar"):
                try:
                    with zipfile.ZipFile(Path(current) / name) as jar:
                        classes.update(n for n in jar.namelist() if n.endswith(".class"))
                except (OSError, zipfile.BadZipFile):
                    continue
    return classes


def _java_class_path(source: Path) -> str:
    try:
        text = source.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""
    found = _PACKAGE.search(text)
    package = found.group(1).replace(".", "/") + "/" if found else ""
    return f"{package}{source.stem}.class"


def _class_name(old: Path, relative: str) -> str:
    """Dotted class name of a `.java` source (package line + stem) or a loose `.class` (its folder path), else ''."""
    if relative.lower().endswith(".java"):
        path = _java_class_path(Path(old) / relative)
        return path[:-6].replace("/", ".") if path else ""
    if relative.lower().endswith(".class"):
        return relative[:-6].replace("/", ".")
    return ""


def split_dropped_files(old: Path, working: Path, vanilla_core: Path | None = None,
                        dropped_classes: frozenset[str] | set[str] = frozenset()) -> tuple[list[str], list[str]]:
    """`(files, junk)`: sorted `data/...` paths `old` has and `working` lacks, minus vanilla-core paths, sources shipped as classes
    and sources/`.class` files whose class is already in `dropped_classes` (the `classes` category lists them). Junk is split off."""
    present = {path.casefold() for path in _data_files(working)}
    jars: set[str] | None = None
    dropped: list[str] = []
    junk: list[str] = []
    for relative in _data_files(old):
        if relative.casefold() in present:
            continue
        if vanilla_core is not None and (Path(vanilla_core) / relative).is_file():
            continue
        if is_junk_file(relative):
            junk.append(relative)
            continue
        if relative.lower().endswith(".java"):
            jars = shipped_classes(working) if jars is None else jars
            if jars and _java_class_path(Path(old) / relative) in jars:
                continue
        if dropped_classes and _class_name(old, relative) in dropped_classes:
            continue
        dropped.append(relative)
    return dropped, junk


def dropped_files(old: Path, working: Path, vanilla_core: Path | None = None,
                  dropped_classes: frozenset[str] | set[str] = frozenset()) -> list[str]:
    return split_dropped_files(old, working, vanilla_core, dropped_classes)[0]
