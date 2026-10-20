"""File-level drops for `dropped-features` (ROADMAP 77.19 extension): files under `data/` the older tree had and `working/` lacks.

Not counted as drops: a path that exists in the vanilla core (the mod only overrode it; skipped, and reported as such, when no
core is given) and a `.java` source whose class ships in one of the working copy's jars (the source moved into the jar).
"""
from __future__ import annotations

import os
import re
import zipfile
from pathlib import Path

DATA = "data"
_PACKAGE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.M)


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


def dropped_files(old: Path, working: Path, vanilla_core: Path | None = None) -> list[str]:
    """Sorted `data/...` paths `old` has and `working` lacks, minus vanilla-core paths and sources shipped as classes."""
    present = {path.casefold() for path in _data_files(working)}
    jars: set[str] | None = None
    dropped: list[str] = []
    for relative in _data_files(old):
        if relative.casefold() in present:
            continue
        if vanilla_core is not None and (Path(vanilla_core) / relative).is_file():
            continue
        if relative.lower().endswith(".java"):
            jars = shipped_classes(working) if jars is None else jars
            if jars and _java_class_path(Path(old) / relative) in jars:
                continue
        dropped.append(relative)
    return dropped
