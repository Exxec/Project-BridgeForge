"""Side-by-side checks between two game builds for `target-impact` (ROADMAP-3 item 91, owner 2026-11-15).

- `touches`: the API classes and changed member names a mod uses. CLEAN only says no check failed; a CLEAN mod that calls
  into the 108 classes 0.98.5a changed is riskier than one that does not, so the catalogue orders live tests by it.
- `id_collisions`: content ids a mod defines that the new vanilla also defines for the first time. A CSV row with the
  mod's id replaces vanilla's row, so the new vanilla ship, weapon or hull mod is silently swapped for the mod's.
- `now_provides`: static helper methods a mod declares whose name and arity match a method the new API added under a name
  the old API did not have: a lead that the game now does what the mod (or RevenantLib) worked around. Information only.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

_IMPORT = re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+)\s*;", re.M)
_DESCRIPTOR_CLASS = re.compile(r"L([\w/$]+);")
_STATIC_DECL = re.compile(r"\bstatic\b[^;{}()=\n]*?\b(\w+)\s*\(([^)]*)\)\s*(?:throws[^{;]*)?\{")


def _arity(descriptor: str) -> int:
    from .target_impact import _descriptor_arity

    return _descriptor_arity(descriptor)


@lru_cache(maxsize=4)
def changed_api(old_core: str, new_core: str) -> dict:
    """{"classes": {internal: changed method/field names}, "new_names": {(name, arity): owner}} between two cores."""
    from .linkage import core_index

    old, new = core_index(old_core), core_index(new_core)
    classes: dict[str, frozenset[str]] = {}
    new_names: dict[tuple[str, int], str] = {}
    for name in old.keys() & new.keys():
        if not name.startswith("com/fs/starfarer/api/"):
            continue
        before, after = old[name], new[name]
        changed = {m for m, _ in before.methods ^ after.methods} | {f for f, _ in before.fields ^ after.fields}
        if changed:
            classes[name] = frozenset(changed)
        old_method_names = {m for m, _ in before.methods}
        for method, descriptor in after.methods - before.methods:
            if method not in old_method_names and method != "<init>":
                new_names.setdefault((method, _arity(descriptor)), name)
    return {"classes": classes, "new_names": new_names}


def touches(folder: Path, jars: list[Path], old_core: Path, new_core: Path) -> dict:
    """{"classes": [...], "members": [...]}: changed API classes the mod references, and calls to their changed names."""
    from .linkage import jar_classes

    changed = changed_api(str(old_core), str(new_core))["classes"]
    classes: set[str] = set()
    members: set[str] = set()
    for jar in jars:
        try:
            parsed = jar_classes(jar)
        except OSError:
            continue
        for info in parsed.values():
            named = {info.super_name, *info.interfaces}
            for _kind, owner, name, descriptor in info.refs:
                named.update(_DESCRIPTOR_CLASS.findall(descriptor or ""))
                if owner in changed:
                    classes.add(owner)
                    if name in changed[owner]:
                        members.add(f"{owner.replace('/', '.')}.{name}")
            classes.update(n for n in named if n in changed)
    dotted = {name.replace("/", "."): name for name in changed}
    for source in folder.rglob("*.java"):
        try:
            text = source.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for imported in _IMPORT.findall(text):
            internal = dotted.get(imported)
            if internal is None:
                continue
            classes.add(internal)
            for name in changed[internal]:
                if re.search(rf"\.\s*{re.escape(name)}\s*\(", text):
                    members.add(f"{imported}.{name}")
    return {"classes": sorted(c.replace("/", ".") for c in classes), "members": sorted(members)}


@lru_cache(maxsize=4)
def _new_vanilla_ids(old_core: str, new_core: str) -> dict[str, frozenset[str]]:
    from .content_diff import content_ids

    old, new = content_ids(Path(old_core)), content_ids(Path(new_core))
    return {kind: frozenset(new[kind] - old.get(kind, set())) for kind in new}


def id_collisions(folder: Path, old_core: Path, new_core: Path) -> list[dict]:
    from .content_diff import content_ids

    fresh = _new_vanilla_ids(str(old_core), str(new_core))
    if not any(fresh.values()):
        return []
    mine = content_ids(folder)
    return [{"kind": "new-vanilla-id-collision", "detail": f"{kind}:{content_id}"}
            for kind in sorted(fresh) for content_id in sorted(mine.get(kind, set()) & fresh[kind])]


def now_provides(folder: Path, old_core: Path, new_core: Path) -> list[dict]:
    new_names = changed_api(str(old_core), str(new_core))["new_names"]
    names = {name for name, _ in new_names}
    hits = []
    for source in sorted(folder.rglob("*.java")):
        try:
            text = source.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not any(name in text for name in names):
            continue
        for match in _STATIC_DECL.finditer(text):
            params = match.group(2).strip()
            key = (match.group(1), params.count(",") + 1 if params else 0)
            if key in new_names:
                owner = new_names[key].replace("/", ".")
                hits.append({"kind": "vanilla-now-provides",
                             "detail": f"{source.relative_to(folder).as_posix()}: {key[0]}/{key[1]} (new in {owner})"})
    return hits
