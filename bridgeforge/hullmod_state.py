"""Move a hull mod's per-ship instance fields into per-ship state (ROADMAP 34.1, 2026-10-04).

The game makes one instance of a hull mod and shares it across every ship that has it, so a field written in
combat leaks between ships (`hullmod-instance-state`). Done by hand three times the same way (SEEKER's
ART_organicHull, Sylphon's SRD_AdvisorSubroutines and SRD_EccentricCoreTakumi): the fields become members of a
static inner `State` kept in `ship.getCustomData()`, and every method that touches them reads its ship's State.

Mechanical only where it is unambiguous. Refused (left for a person or an agent) when a field:
- is declared with other fields on one line, or is static or final;
- is used in a method without a `ShipAPI` parameter (no ship to key the state on), or in two ShipAPI parameters;
- is shadowed by a local or parameter of the same name in a method that uses it;
- is used outside any method (an initializer of another field).
Formulas, timings and effects are untouched; only where each value is kept changes.
"""
from __future__ import annotations

import re

from .scanner import _blank_java_comments

_TYPES = r"(?:float|int|boolean|double|long|short|byte|char|String|Vector2f|Color)"
_FIELD = re.compile(r"^(?P<indent>[ \t]*)(?:private\s+|protected\s+|public\s+)?(?P<type>" + _TYPES +
                    r")\s+(?P<name>\w+)\s*(?:=\s*(?P<init>[^;,]+?))?\s*;[ \t]*(?:\r?\n)", re.M)
_METHOD = re.compile(r"\b[\w<>\[\],. ]+?\s+(\w+)\s*\(([^()]*)\)\s*(?:throws\s+[\w., ]+)?\{")


class HullModStateError(ValueError):
    pass


def _close_brace(blank: str, open_index: int) -> int:
    depth = 0
    for i in range(open_index, len(blank)):
        if blank[i] == "{":
            depth += 1
        elif blank[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    raise HullModStateError("unbalanced braces")


def port_hullmod_state(text: str, fields: list[str], class_name: str) -> str:
    """Return `text` with `fields` moved into a per-ship State; raise HullModStateError when not mechanical."""
    blank = _blank_java_comments(text, strings=True)
    declarations = {}
    for match in _FIELD.finditer(blank):
        if match.group("name") in fields:
            line = blank[match.start():match.end()]
            if re.search(r"\b(static|final)\b", line):
                raise HullModStateError(f"{match.group('name')} is static or final")
            declarations[match.group("name")] = match
    missing = [f for f in fields if f not in declarations]
    if missing:
        raise HullModStateError(f"no single-field declaration for {', '.join(missing)} (shared line or other type)")
    methods = []
    for match in _METHOD.finditer(blank):
        if match.group(1) in {"if", "for", "while", "switch", "catch", "synchronized"}:
            continue
        open_index = match.end() - 1
        close = _close_brace(blank, open_index)
        if any(start < match.start() < end for start, end, *_ in methods):
            continue  # a method of an inner/anonymous class: judged with its enclosing method
        methods.append((match.start(), close, open_index, match.group(2)))
    names = "|".join(re.escape(f) for f in fields)
    use = re.compile(r"(?<![\w.])(?:this\s*\.\s*)?(" + names + r")\b")
    decl_spans = [(m.start(), m.end()) for m in declarations.values()]
    for m in use.finditer(blank):
        if any(s <= m.start() < e for s, e in decl_spans):
            continue
        if not any(start < m.start() < end for start, end, *_ in methods):
            raise HullModStateError(f"{m.group(1)} is used outside a method")
    edits: list[tuple[int, int, str]] = []
    for start, end, open_index, params in methods:
        body = blank[open_index:end]
        if not use.search(body):
            continue
        ships = re.findall(r"\bShipAPI\s+(\w+)", params)
        if len(ships) != 1:
            raise HullModStateError(f"a method using {names} has {len(ships)} ShipAPI parameter(s)")
        if re.search(r"\b" + _TYPES + r"\s+(" + names + r")\b", blank[start:end]):
            raise HullModStateError("a local or parameter shadows a moved field")
        edits.append((open_index + 1, open_index + 1, f"\n        State bfState = bfState({ships[0]});"))
        for m in use.finditer(blank, open_index, end):
            edits.append((m.start(), m.end(), f"bfState.{m.group(1)}"))
    if not edits:
        raise HullModStateError("no method uses the fields")
    first = min(m.start() for m in declarations.values())
    indent = declarations[min(declarations, key=lambda f: declarations[f].start())].group("indent")
    members = "".join(f"{indent}    {m.group('type')} {m.group('name')}"
                      f"{' = ' + text[m.start('init'):m.end('init')].strip() if m.group('init') else ''};\n"
                      for m in sorted(declarations.values(), key=lambda m: m.start()))
    key = f"{class_name}_bfState"
    block = (f"{indent}// BridgeForge: these were fields of the one hull mod instance every ship shares, so one ship's values\n"
             f"{indent}// drove every other ship's. Each ship keeps its own (ROADMAP 34.1).\n"
             f"{indent}private static class State {{\n{members}{indent}}}\n\n"
             f"{indent}private static State bfState(ShipAPI ship) {{\n"
             f"{indent}    if (ship == null) return new State(); // tooltips without a ship (the codex)\n"
             f"{indent}    Object found = ship.getCustomData().get(\"{key}\");\n"
             f"{indent}    if (found instanceof State) return (State) found;\n"
             f"{indent}    State created = new State();\n"
             f"{indent}    ship.setCustomData(\"{key}\", created);\n"
             f"{indent}    return created;\n{indent}}}\n\n")
    for name, m in declarations.items():
        edits.append((m.start(), m.end(), block if m.start() == first else ""))
    out = text
    for s, e, new in sorted(edits, key=lambda x: (x[0], x[1]), reverse=True):
        out = out[:s] + new + out[e:]
    if "import com.fs.starfarer.api.combat.ShipAPI;" not in out and "import com.fs.starfarer.api.combat.*;" not in out:
        package = re.search(r"^package [\w.]+;\s*\n", out, re.M)
        at = package.end() if package else 0
        out = out[:at] + "import com.fs.starfarer.api.combat.ShipAPI;\n" + out[at:]
    return out
