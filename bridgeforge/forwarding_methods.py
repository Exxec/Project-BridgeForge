"""Forwarding classes short of a game interface's new methods (2026-11-15, 0.98.5a-RC3).

DroneLib's `dl_DroneAPI implements ShipAPI` (in RevenantLib and DroneLib) wraps a drone and forwards nearly every call to
it (`return drone.getFluxTracker();`, 313 times). 0.98.5a added six `ShipAPI` methods; every new game version that grows
`ShipAPI` means typing the forwards by hand, and a forgotten one is an AbstractMethodError when the game calls it on a drone.

Check `forwarding-class-method-missing` (needs the target core): a loose source class that implements a game interface and
forwards to one field of that interface's type (at least FORWARDS_MIN calls on it) lacks a method the interface requires on
the target. Methods are compared by name and parameter count, so an overload with other types counts as present (no false
alarm, possibly a miss). The fixer appends one forwarding method per missing method, before the class's closing brace,
with fully qualified types: `public java.util.List getCommands2() { return drone.getCommands2(); }`.
"""
from __future__ import annotations

import re
from pathlib import Path

FORWARDS_MIN = 5
_CLASS = re.compile(r"\bclass\s+(\w+)[^{]*?\bimplements\s+([\w.,\s<>]+?)\s*\{")
_PACKAGE = re.compile(r"(?m)^\s*package\s+([\w.]+)\s*;")
_IMPORT = re.compile(r"(?m)^\s*import\s+([\w.]+)(\.\*)?\s*;")
# A type without free spaces or commas (generics are their own group, one level of nesting): a type class that also matched
# spaces and commas backtracked for minutes on Angry Periphery's long world-generation lines (2026-11-15). Declarations
# are matched from the start of a line.
_TYPE = r"[\w.$?]+(?:\s*<[^<>(){};]*(?:<[^<>(){};]*>[^<>(){};]*)*>)?(?:\s*\[\s*\])*"
# Modifiers, then a generic method's own type parameters (`public <T> List<T> getListeners(Class<T> c)`, dl_DroneAPI).
_MODIFIERS = r"(?:(?:public|protected|private|static|final|synchronized|abstract|native|default)\s+)*(?:<[^<>(){};]*(?:<[^<>(){};]*>[^<>(){};]*)*>\s*)?"
_METHOD = re.compile(rf"(?m)^[ \t]*(?:@\w+[ \t]*)*{_MODIFIERS}{_TYPE}\s+(\w+)\s*\(([^)]*)\)\s*(?:throws[^{{;]*)?\{{")
_FIELD = r"\b{type}\s+(\w+)\s*[;=]"
_BASE = {"B": "byte", "C": "char", "D": "double", "F": "float", "I": "int", "J": "long", "S": "short", "Z": "boolean", "V": "void"}


def _types(descriptor: str) -> tuple[list[str], str]:
    """Java source types (fully qualified) of a descriptor's parameters and return."""
    def one(pos: int) -> tuple[str, int]:
        dims = 0
        while descriptor[pos] == "[":
            dims, pos = dims + 1, pos + 1
        if descriptor[pos] == "L":
            end = descriptor.index(";", pos)
            return descriptor[pos + 1:end].replace("/", ".").replace("$", ".") + "[]" * dims, end + 1
        return _BASE[descriptor[pos]] + "[]" * dims, pos + 1

    params, pos = [], 1
    while descriptor[pos] != ")":
        kind, pos = one(pos)
        params.append(kind)
    return params, one(pos + 1)[0]


def _param_count(text: str) -> int:
    depth, count = 0, 1 if text.strip() else 0
    for char in text:
        depth += char == "<"
        depth -= char == ">"
        count += char == "," and depth == 0
    return count


def _resolve(simple: str, text: str, core: dict) -> str | None:
    """The core class (internal name) a simple or qualified interface name in this source means."""
    if "." in simple:
        name = simple.replace(".", "/")
        return name if name in core else None
    for match in _IMPORT.finditer(text):
        target, star = match.group(1), match.group(2)
        candidate = f"{target}.{simple}" if star else (target if target.rsplit(".", 1)[-1] == simple else None)
        if candidate and candidate.replace(".", "/") in core:
            return candidate.replace(".", "/")
    package = _PACKAGE.search(text)
    candidate = f"{package.group(1)}.{simple}".replace(".", "/") if package else simple
    return candidate if candidate in core else None


def _required(interface: str, core: dict) -> list[tuple[str, str]]:
    found, seen, stack = set(), set(), [interface]
    while stack:
        current = stack.pop()
        if current in seen or current not in core:
            continue
        seen.add(current)
        found |= core[current].abstract_methods
        stack += list(core[current].interfaces)
    return sorted(found)


def missing_forwards(text: str, core: dict) -> list[dict]:
    """[{class, interface, delegate, missing: [(name, descriptor)], insert_at}] for each forwarding class in one source."""
    from .scan.scan_javatext import _blank_java_comments

    blank = _blank_java_comments(text, strings=True)
    results = []
    for match in _CLASS.finditer(blank):
        declared = {(m.group(1), _param_count(m.group(2))) for m in _METHOD.finditer(blank)}
        for simple in (s.strip().split("<", 1)[0] for s in match.group(2).split(",")):
            interface = _resolve(simple, text, core)
            if interface is None:
                continue
            fields = re.findall(_FIELD.format(type=re.escape(simple)), blank)
            counts = {f: len(re.findall(rf"\b{re.escape(f)}\s*\.\s*\w+\s*\(", blank)) for f in set(fields)}
            delegate = max(counts, key=counts.get) if counts else None
            if delegate is None or counts[delegate] < FORWARDS_MIN:
                continue
            missing = [(n, d) for n, d in _required(interface, core) if (n, len(_types(d)[0])) not in declared]
            if missing:
                results.append({"class": match.group(1), "interface": interface.replace("/", "."), "delegate": delegate,
                                "missing": missing, "insert_at": blank.rindex("}")})
    return results


def forwarding_source(name: str, descriptor: str, delegate: str, indent: str = "    ") -> str:
    params, returns = _types(descriptor)
    args = ", ".join(f"{kind} a{i}" for i, kind in enumerate(params))
    call = f"{delegate}.{name}({', '.join(f'a{i}' for i in range(len(params)))})"
    body = f"{call};" if returns == "void" else f"return {call};"
    return f"{indent}public {returns} {name}({args}) {{ {body} }}"


_OBJECT = {("equals", 1), ("hashCode", 0), ("toString", 0), ("clone", 0), ("finalize", 0)}
_OVERRIDE = re.compile(rf"@Override\s*(?={_MODIFIERS}{_TYPE}\s+(\w+)\s*\(([^)]*)\))")


def _drop_stale_overrides(text: str, interface: str, core: dict) -> tuple[str, int]:
    """Remove `@Override` from methods no supertype has any more (dl_DroneAPI's `isBeingIgnored()`, gone in 0.98.5a, which
    javac rejects with @Override). Only for a class whose supertypes are the core interface alone: anything else could
    supply the method."""
    match = _CLASS.search(text)
    if match is None or "extends" in text[match.start():match.end()] or "," in match.group(2):
        return text, 0
    known, seen, stack = set(_OBJECT), set(), [interface]
    while stack:
        current = stack.pop()
        if current in seen or current not in core:
            continue
        seen.add(current)
        known |= {(name, len(_types(desc)[0])) for name, desc in core[current].methods}
        stack += list(core[current].interfaces)
    out, last, dropped = [], 0, 0
    for m in _OVERRIDE.finditer(text):
        if (m.group(1), _param_count(m.group(2))) in known:
            continue
        out.append(text[last:m.start()])
        last, dropped = m.end(), dropped + 1
    out.append(text[last:])
    return "".join(out), dropped


def add_forwards(text: str, core: dict, target: str) -> tuple[str, int]:
    """Text with every missing forward appended to its class (one class per file is the common case; the last brace)."""
    found = missing_forwards(text, core)
    if len(found) != 1:
        return text, 0  # none, or several forwarding classes in one file: left for a person
    item = found[0]
    text, _ = _drop_stale_overrides(text, item["interface"].replace(".", "/"), core)
    item = missing_forwards(text, core)[0]
    newline = "\r\n" if "\r\n" in text else "\n"
    block = newline.join([f"    // Forwarded like the methods above; added by BridgeForge for {target}."] +
                         [forwarding_source(n, d, item["delegate"]) for n, d in item["missing"]])
    at = item["insert_at"]
    head = text[:at].rstrip(" \t")
    return head + (newline if not head.endswith(("\n", "\r")) else "") + block + newline + text[at:], len(item["missing"])


def scan_forwarding(root: Path, result, vanilla_core: Path | None) -> None:
    """forwarding-class-method-missing (see module docstring)."""
    if vanilla_core is None:
        return
    from .linkage import core_index
    from .scan.scan_common import _relative

    core = core_index(str(Path(vanilla_core).resolve()))
    if not core:
        return
    for source in sorted(root.rglob("*.java")):
        if "disabled_files" in source.relative_to(root).parts:
            continue
        try:
            text = source.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "implements" not in text:
            continue
        for item in missing_forwards(text, core):
            result.add(
                id="forwarding-class-method-missing",
                category="api",
                severity="high",
                classification="REVIEW",
                confidence="HIGH",
                explanation=(f"{item['class']} implements {item['interface']} by forwarding to `{item['delegate']}` but lacks "
                             f"{len(item['missing'])} method(s) the target requires (an AbstractMethodError when the game calls "
                             "one; javac refuses the class). The fixer appends forwards to the same field."),
                file=_relative(root, source),
                evidence=[f"{n}{d}" for n, d in item["missing"]][:12],
            )
