"""`bridgeforge verify-shadow`: does a jar set really compile the class a loose script defines? (ROADMAP P14 item 26)

E12 (2026-09-21): 50 of Rebal's loose scripts were moved out as "jar-shadowed" on the strength of a
`Path.is_file()` check that a vanilla file existed at the same path. None of the 50 was in any jar;
all were live code. Whether a loose script is shadowed is a question about jar contents, so this
answers it only by parsing class files, with the same loop and parser the scanner's
`loose-script-shadowed-by-jar` check uses (`scanner.iter_class_files_in_jars`, `_parse_class_file`).

A script's class is its declared `package` plus its file name; with no package line, its path
below the mod root (the folder holding mod_info.json). `--against` takes a jar, a mod folder (its
declared jars, as the game loads them) or any other folder (every jar under it, e.g. a
starsector-core, where `starfarer_obf.jar` counts too). Every jar that could not be read is listed,
so "not shadowed" states what it did not look inside. Read-only.
"""
from __future__ import annotations

import re
from pathlib import Path

from .scanner import _loaded_mod_jars, _parse_class_file, iter_class_files_in_jars

SCHEMA_VERSION = 1
_PACKAGE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.MULTILINE)
_COMMENTS = re.compile(r"/\*.*?\*/|//[^\n]*", re.DOTALL)


class VerifyShadowError(ValueError):
    """Raised for a missing script or --against path."""


def script_class_name(script: Path) -> tuple[str, str]:
    """(fully-qualified class name, how it was derived) for a loose .java file."""
    text = script.read_text(encoding="utf-8-sig", errors="replace")
    match = _PACKAGE.search(_COMMENTS.sub("", text))
    if match:
        return f"{match.group(1)}.{script.stem}", "package declaration"
    for parent in script.parents:
        if (parent / "mod_info.json").is_file():
            return ".".join(script.relative_to(parent).with_suffix("").parts), f"path below mod root {parent}"
    return script.stem, "file name only (no package line and no mod root)"


def _jars(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    if (target / "mod_info.json").is_file():
        return list(_loaded_mod_jars(target))
    return sorted(target.rglob("*.jar"))


def verify_shadow(scripts: list[Path], against: list[Path]) -> dict:
    scripts = [Path(p).expanduser().resolve() for p in scripts]
    against = [Path(p).expanduser().resolve() for p in against]
    for path in scripts:
        if not path.is_file():
            raise VerifyShadowError(f"{path} is not a file.")
    for path in against:
        if not path.exists():
            raise VerifyShadowError(f"--against {path} does not exist.")
    jars = sorted({jar for target in against for jar in _jars(target)})
    unreadable: list[str] = []
    owners: dict[str, list[str]] = {}
    class_count = 0
    for jar, member, data in iter_class_files_in_jars(jars, unreadable):
        info = _parse_class_file(data)
        if info is not None and info.this_class:
            class_count += 1
            owners.setdefault(info.this_class.replace("/", "."), []).append(f"{jar}!{member}")
    results = []
    for script in scripts:
        name, derived = script_class_name(script)
        found = sorted(owners.get(name, []))
        results.append({"script": str(script), "class": name, "class_from": derived,
                        "status": "SHADOWED" if found else "NOT_SHADOWED", "supplied_by": found})
    return {
        "schema_version": SCHEMA_VERSION, "mode": "VERIFY_SHADOW",
        "against": [str(p) for p in against], "jars_checked": len(jars) - len(unreadable), "classes_checked": class_count,
        "unreadable_jars": unreadable, "results": results,
        "note": "SHADOWED: a jar compiles this class, so the game loads the jar's copy and never compiles the loose file. NOT_SHADOWED covers only the jars checked.",
    }
