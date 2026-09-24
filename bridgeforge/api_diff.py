"""`bridgeforge api-diff`: what changed in the public game API between two versions.

Removed APIs kept turning up one method at a time during revival work (ROADMAP P14 item 11:
`SectorAPI.createFleet(faction, fleetType)`, then `SectorAPI.addMessage`, which RC8 moved to
`CampaignUIAPI`), each found only when a compile check failed. This compares two API jars --
normally an old install's `starfarer.api.jar` against RC8's -- once, member by member, and writes a
catalogue of every public/protected class, method and field that was removed or changed.

For each removed method the catalogue lists the new overloads of the same name in the same class
(a signature change) and other classes that now declare the same name and descriptor (a move).
Both are candidates, not proof of intent: a matching descriptor elsewhere is a lead to check, never
an automatic rewrite. `annotate_errors` attaches those leads to compile-check's javac errors.

Read-only: both jars are only read. The catalogue holds API names and descriptors, never game code.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .rebuild_jar import _ACC_SYNTHETIC, _classes_from_jar, _parse_class

SCHEMA_VERSION = 1
API_JAR_NAME = "starfarer.api.jar"
MAX_CANDIDATES = 5

_ACC_PUBLIC = 0x0001
_ACC_PROTECTED = 0x0004
_ACC_BRIDGE = 0x0040  # same bit as ACC_VOLATILE on fields; only consulted for methods

_BASE_TYPES = {"B": "byte", "C": "char", "D": "double", "F": "float", "I": "int", "J": "long", "S": "short", "Z": "boolean", "V": "void"}
_ANONYMOUS_CLASS = re.compile(r"\$\d")


class ApiDiffError(ValueError):
    """Raised when an input is neither an API jar nor a starsector-core folder holding one."""


def resolve_api_jar(path: Path) -> Path:
    """Accept the jar itself or a starsector-core folder (where the game keeps starfarer.api.jar)."""
    path = Path(path).expanduser().resolve()
    if path.is_dir():
        path = path / API_JAR_NAME
    if not path.is_file():
        raise ApiDiffError(f"{path} is not an API jar or a starsector-core folder holding {API_JAR_NAME}.")
    return path


def _simple(internal_name: str) -> str:
    return internal_name.rsplit("/", 1)[-1].replace("$", ".")


def _dotted(internal_name: str) -> str:
    return internal_name.replace("/", ".")


def _parse_type(descriptor: str, pos: int) -> tuple[str, int]:
    dims = 0
    while descriptor[pos] == "[":
        dims += 1
        pos += 1
    code = descriptor[pos]
    if code == "L":
        end = descriptor.index(";", pos)
        name, pos = _simple(descriptor[pos + 1:end]), end + 1
    else:
        name, pos = _BASE_TYPES[code], pos + 1
    return name + "[]" * dims, pos


def render_method(class_internal: str, name: str, descriptor: str) -> str:
    """`(Ljava/lang/String;I)V` on addMessage -> `void addMessage(String, int)`; constructors take the class name."""
    try:
        params, pos = [], 1
        while descriptor[pos] != ")":
            param, pos = _parse_type(descriptor, pos)
            params.append(param)
        returns, _ = _parse_type(descriptor, pos + 1)
    except (IndexError, KeyError, ValueError):
        return f"{name}{descriptor}"
    if name == "<init>":
        return f"{_simple(class_internal)}({', '.join(params)})"
    return f"{returns} {name}({', '.join(params)})"


def render_field(name: str, descriptor: str) -> str:
    try:
        kind, _ = _parse_type(descriptor, 0)
    except (IndexError, KeyError, ValueError):
        return f"{name}:{descriptor}"
    return f"{kind} {name}"


def _visible(member) -> bool:
    flags = member.access_flags
    if not flags & (_ACC_PUBLIC | _ACC_PROTECTED) or flags & _ACC_SYNTHETIC:
        return False
    return member.name != "<clinit>"


def _load(jar: Path) -> tuple[dict[str, object], list[str]]:
    classes: dict[str, object] = {}
    unparseable: list[str] = []
    for entry, data in sorted(_classes_from_jar(jar.read_bytes()).items()):
        internal = entry[:-len(".class")]
        if _ANONYMOUS_CLASS.search(internal):
            continue
        parsed = _parse_class(data)
        if parsed is None:
            unparseable.append(internal)
        else:
            classes[internal] = parsed
    return classes, unparseable


def _methods(parsed) -> dict[tuple[str, str], object]:
    return {key: member for key, member in parsed.methods.items() if _visible(member) and not member.access_flags & _ACC_BRIDGE}


def _fields(parsed) -> dict[tuple[str, str], object]:
    return {key: member for key, member in parsed.fields.items() if _visible(member)}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def diff_api_jars(old_jar: Path, new_jar: Path) -> dict:
    """Compare two API jars; return a JSON-serialisable catalogue (schema_version 1)."""
    old_path, new_path = resolve_api_jar(old_jar), resolve_api_jar(new_jar)
    old_classes, old_unparseable = _load(old_path)
    new_classes, new_unparseable = _load(new_path)

    new_by_simple: dict[str, list[str]] = {}
    new_method_owners: dict[tuple[str, str], list[str]] = {}
    for internal, parsed in new_classes.items():
        new_by_simple.setdefault(_simple(internal), []).append(internal)
        for key in _methods(parsed):
            if key[0] != "<init>":
                new_method_owners.setdefault(key, []).append(internal)

    removed_classes = []
    for internal in sorted(set(old_classes) - set(new_classes)):
        moved = sorted(_dotted(name) for name in new_by_simple.get(_simple(internal), []) if name not in old_classes)
        removed_classes.append({"class": _dotted(internal), "same_name_elsewhere": moved[:MAX_CANDIDATES]})

    changed: dict[str, dict] = {}
    for internal in sorted(set(old_classes) & set(new_classes)):
        old_methods, new_methods = _methods(old_classes[internal]), _methods(new_classes[internal])
        old_fields, new_fields = _fields(old_classes[internal]), _fields(new_classes[internal])
        methods_removed = []
        for name, descriptor in sorted(set(old_methods) - set(new_methods)):
            overloads = sorted(render_method(internal, name, d) for (n, d) in new_methods if n == name)
            elsewhere = sorted(
                f"{_dotted(owner)}.{render_method(owner, name, descriptor).split(' ', 1)[-1]}"
                for owner in new_method_owners.get((name, descriptor), []) if owner != internal
            )
            methods_removed.append({
                "name": name, "descriptor": descriptor, "signature": render_method(internal, name, descriptor),
                "same_name_in_class": overloads, "same_signature_elsewhere": elsewhere[:MAX_CANDIDATES],
            })
        fields_removed = [
            {"name": name, "descriptor": descriptor, "signature": render_field(name, descriptor),
             "same_name_in_class": sorted(render_field(n, d) for (n, d) in new_fields if n == name)}
            for name, descriptor in sorted(set(old_fields) - set(new_fields))
        ]
        methods_added = sorted(render_method(internal, n, d) for (n, d) in set(new_methods) - set(old_methods))
        if methods_removed or fields_removed or methods_added:
            changed[_dotted(internal)] = {"methods_removed": methods_removed, "fields_removed": fields_removed, "methods_added": methods_added}

    removed_method_count = sum(len(entry["methods_removed"]) for entry in changed.values())
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "API_DIFF",
        "old": {"jar": str(old_path), "sha256": _sha256(old_path), "classes": len(old_classes), "unparseable": old_unparseable},
        "new": {"jar": str(new_path), "sha256": _sha256(new_path), "classes": len(new_classes), "unparseable": new_unparseable},
        "summary": {
            "classes_removed": len(removed_classes),
            "classes_added": len(set(new_classes) - set(old_classes)),
            "classes_changed": len(changed),
            "methods_removed": removed_method_count,
            "fields_removed": sum(len(entry["fields_removed"]) for entry in changed.values()),
        },
        "removed_classes": removed_classes,
        "added_classes": sorted(_dotted(name) for name in set(new_classes) - set(old_classes)),
        "changed_classes": changed,
        "note": "Candidates only: a same-named member or class elsewhere is a lead to verify, not proof of a move.",
    }


# --- compile-check annotation ----------------------------------------------------------------
# javac's continuation lines, as parse_javac_errors records them: "symbol: method addMessage(String)",
# "symbol: class CampaignClockAPI", "location: variable sector of type SectorAPI",
# "location: interface SectorAPI". A "cannot be applied" header names the method and type itself.
_SYMBOL = re.compile(r"^symbol:\s*(?P<kind>method|class|variable)\s+(?P<name>[\w$]+)")
_LOCATION_TYPE = re.compile(r"^location:\s*(?:variable \S+ of type|class|interface)\s+(?P<type>[\w.$]+)")
_NOT_APPLICABLE = re.compile(r"^(?P<what>method|constructor) (?P<name>[\w$]+) in (?:class|interface) (?P<type>[\w.$]+)")


def _strip_generics(type_name: str) -> str:
    return type_name.split("<", 1)[0].rsplit(".", 1)[-1]


def _index(catalogue: dict) -> tuple[dict[str, list[tuple[str, dict]]], dict[str, list[dict]]]:
    changed: dict[str, list[tuple[str, dict]]] = {}
    for dotted, entry in catalogue.get("changed_classes", {}).items():
        changed.setdefault(dotted.rsplit(".", 1)[-1], []).append((dotted, entry))
    removed: dict[str, list[dict]] = {}
    for entry in catalogue.get("removed_classes", []):
        removed.setdefault(entry["class"].rsplit(".", 1)[-1], []).append(entry)
    return changed, removed


def _member_hints(changed_index, type_simple: str, member: str, kind: str) -> list[dict]:
    hints = []
    for dotted, entry in changed_index.get(type_simple, []):
        key = "methods_removed" if kind == "method" else "fields_removed"
        for removed in entry[key]:
            if removed["name"] == member:
                hints.append({"removed": f"{dotted}.{removed['signature'].split(' ', 1)[-1]}", **{
                    k: removed[k] for k in ("same_name_in_class", "same_signature_elsewhere") if k in removed}})
    return hints


def annotate_errors(errors: list[dict], catalogue: dict) -> int:
    """Add an `api_changes` list to each javac error the catalogue explains; return how many got one."""
    changed_index, removed_index = _index(catalogue)
    annotated = 0
    for error in errors:
        detail = [str(line) for line in error.get("detail", [])]
        hints: list[dict] = []
        if error.get("kind") == "missing-symbol":
            symbol = next((m for m in map(_SYMBOL.match, detail) if m), None)
            location = next((m for m in map(_LOCATION_TYPE.match, detail) if m), None)
            if symbol and symbol.group("kind") == "class":
                hints = [{"removed_class": entry["class"], "same_name_elsewhere": entry["same_name_elsewhere"]}
                         for entry in removed_index.get(symbol.group("name"), [])]
            elif symbol and location:
                kind = "method" if symbol.group("kind") == "method" else "field"
                hints = _member_hints(changed_index, _strip_generics(location.group("type")), symbol.group("name"), kind)
        elif error.get("kind") == "cannot-be-applied":
            header = _NOT_APPLICABLE.match(str(error.get("message", "")))
            if header:
                member = "<init>" if header.group("what") == "constructor" else header.group("name")
                hints = _member_hints(changed_index, _strip_generics(header.group("type")), member, "method")
        if hints:
            error["api_changes"] = hints
            annotated += 1
    return annotated
