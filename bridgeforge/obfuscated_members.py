"""Does each obfuscated game member a mod class references still exist in RC8? (item 73 F6, `obfuscated-internal-api-use`)

A class that names `com.fs.starfarer` internals (outside `api`) was always reported, however many of those names RC8 still has.
With RC8's core jars at hand the constant pool settles it: every Methodref/Fieldref whose owner is such a class is resolved with
`linkage` (name + descriptor, through the owner's supertypes inside the core jars), and every other class name is looked up by
name. The result per mod class: `missing` (class or member absent, the real breakage), `unverified` (the hierarchy leaves the core
jars, so nothing is claimed) and `resolved` (found, with the count). Evidence is a class-file read of RC8's jars, the same
method as `jar-linkage-unresolved`; no `javap` run is needed.
"""
from __future__ import annotations

from .linkage import ClassInfo, _resolve, parse_class

INTERNAL_PREFIX = "com/fs/starfarer/"
API_PREFIX = "com/fs/starfarer/api/"


def is_internal(name: str) -> bool:
    return name.startswith(INTERNAL_PREFIX) and not name.startswith(API_PREFIX)


def classify_internal_references(data: bytes, core: dict[str, ClassInfo], mod_classes: frozenset[str] = frozenset()) -> dict[str, list[str]] | None:
    """{'missing': [...], 'unverified': [...], 'resolved': [...]} for one mod class file, or None if it names no internal class.

    Names the mod's own jars define (`mod_classes`, slash form) are not game classes and are skipped."""
    info = parse_class(data)
    if info is None:
        return None
    out: dict[str, list[str]] = {"missing": [], "unverified": [], "resolved": []}
    owners = {owner for _, owner, _, _ in info.refs if is_internal(owner)}
    for owner in sorted(owners - mod_classes):
        if owner not in core:
            out["missing"].append(f"class {owner.replace('/', '.')}")
    for kind, owner, name, descriptor in sorted(info.refs):
        if not is_internal(owner) or owner in mod_classes or owner not in core:
            continue
        found = _resolve(core, owner, kind, name, descriptor)
        label = f"{owner.replace('/', '.')}.{name}{descriptor if kind == 'method' else ''}"
        out["missing" if found is False else "unverified" if found is None else "resolved"].append(f"{kind} {label}")
    if not any(out.values()):
        return None
    return out
