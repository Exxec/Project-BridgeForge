"""94.G2 slice 13: a literal that only names an id is a mention, not a need (owner 2026-11-20).

**The ruling.** Eridani's faction, 17 hulls and 12 hull mods closed into one block of 30 genes only because their code
names other ids: other hull mods' ids as stat-modifier source keys, status keys and "is it installed?" checks
(`hasHullMod`, `getHullMods().contains`), and a constants class holding the faction id that no instruction loads. The
owner ruled (AskUserQuestion, "Mention = suspect"): such a mention is recorded as a suspect; only code that adds or uses
the content is a need.

**How a literal's use is read (jar classes).** For each `ldc` of a string, the operand stack is followed to the instruction
that pops it. Its sink is `owner.method#argument`. A sink this module cannot follow is `unknown`: a jump target in between,
a store, a `dup` of the value, or an opcode the stack model does not cover. A literal is a need unless *every* occurrence
ends in a mention sink below, so one use among mentions keeps it a need, and so does every unknown sink (advisor
2026-11-20: unknowns stay needs; `Map.put` and `Set.add` stay needs too, since a stored id may be added as content
later). A `static final` string that no instruction of its class loads is a mention: javac inlines its uses, and each use is
judged where it is loaded. Loose `.java` scripts keep their literals as before (P1 is a loose script).

**The mention sinks**, only those the trace of Eridani's and Tania's jars showed (2026-11-20), each with its evidence.
"""
from __future__ import annotations

import struct

from bridgeforge.atlas.atlas_classfile import ClassFormatError, instructions, iter_method_code, jump_targets

MENTION_SINKS = {
    "java/util/Collection.contains#0": "JDK: a membership test",
    "java/util/LinkedHashSet.contains#0": "JDK: a membership test",
    "java/lang/String.contains#0": "JDK: a substring test",
    "com/fs/starfarer/api/combat/ShipVariantAPI.hasHullMod#0": "RC7 HullVariantSpec.hasHullMod: getHullMods().contains (javap)",
    "com/fs/starfarer/api/combat/ShipVariantAPI.removeMod#0":
        "RC7 HullVariantSpec.removeMod: LinkedHashSet contains and remove, and the hull's isBuiltInMod (javap)",
    "com/fs/starfarer/api/combat/MutableStat.modifyMult#0": "MutableStat keys its multiplier mods by this source id: HashMap put (javap)",
    "com/fs/starfarer/api/combat/MutableStat.modifyPercent#0": "MutableStat keys its percent mods by this source id: HashMap put (javap)",
    "com/fs/starfarer/api/combat/MutableStat.modifyFlat#0": "MutableStat keys its flat mods by this source id: HashMap put (javap)",
    "com/fs/starfarer/api/combat/MutableStat.unmodify#0": "MutableStat removes the mods keyed by this source id: HashMap remove (javap)",
    "com/fs/starfarer/api/combat/StatBonus.modifyPercent#0": "StatBonus keys its percent bonuses by this source id: HashMap put (javap)",
    "com/fs/starfarer/api/combat/CombatEngineAPI.maintainStatusForPlayerShip#0":
        "RC7 CombatEngine passes it to the status list's maintainStatusFor(Object key, ...): a UI entry keyed by it (javap)",
    "com/fs/starfarer/api/loading/WeaponSpecAPI.hasTag#0": "RC7 BaseWeaponSpec.hasTag: Set.contains (javap)",
}
NOT_LOADED = "a static final constant no instruction of its class loads"

_LDC = (0x12, 0x13)
_INVOKES = {0xb6: False, 0xb7: False, 0xb8: True, 0xb9: False}  # opcode -> static
_STORES = set(range(0x36, 0x57)) | {0xb3, 0xb5}
_EFFECTS: dict[int, tuple[int, int]] = {0x00: (0, 0), 0x57: (1, 0), 0x84: (0, 0)}
_EFFECTS.update({op: (0, 1) for op in range(0x01, 0x2e)})   # constants and loads
_EFFECTS.update({op: (2, 1) for op in range(0x2e, 0x36)})   # array loads
_EFFECTS.update({op: (1, 0) for op in range(0x36, 0x4f)})   # stores
_EFFECTS.update({op: (3, 0) for op in range(0x4f, 0x57)})   # array stores
_EFFECTS.update({op: (2, 1) for op in [*range(0x60, 0x74), *range(0x78, 0x84), *range(0x94, 0x99)]})
_EFFECTS.update({op: (1, 1) for op in [*range(0x74, 0x78), *range(0x85, 0x94)]})
_EFFECTS.update({op: (1, 0) for op in range(0x99, 0x9f)})
_EFFECTS.update({op: (2, 0) for op in range(0x9f, 0xa7)})
_EFFECTS.update({0xb2: (0, 1), 0xb3: (1, 0), 0xb4: (1, 1), 0xb5: (2, 0), 0xbb: (0, 1), 0xbc: (1, 1), 0xbd: (1, 1), 0xbe: (1, 1),
                 0xc1: (1, 1), 0xc2: (1, 0), 0xc3: (1, 0), 0xc6: (1, 0), 0xc7: (1, 0)})


def _argument_count(descriptor: str) -> int:
    params, i, count = descriptor[1:descriptor.index(")")], 0, 0
    while i < len(params):
        while params[i] == "[":
            i += 1
        i = params.index(";", i) + 1 if params[i] == "L" else i + 1
        count += 1
    return count


def sink_of(steps: list, start: int, targets: set[int], pool) -> str:
    """Where the value pushed by `steps[start]` goes: `owner.method#argument` (`#recv` for the receiver), or `unknown: why`."""
    depth = 0  # values pushed above ours
    for pc, op, arg in steps[start + 1:]:
        if pc in targets:
            return "unknown: a jump target before its use"
        if op == 0x59:  # dup
            if depth == 0:
                return "unknown: duplicated"
            depth += 1
            continue
        if op == 0xc0:  # checkcast passes the value through
            continue
        if op in _INVOKES:
            owner, name, descriptor = pool.member(arg)
            count = _argument_count(descriptor) + (0 if _INVOKES[op] else 1)
            if depth < count:
                index = count - 1 - depth
                position = index if _INVOKES[op] else index - 1
                return f"{owner}.{name}#{'recv' if position < 0 else position}"
            depth = depth - count + (0 if descriptor.endswith(")V") else 1)
            continue
        effect = _EFFECTS.get(op)
        if effect is None:
            return f"unknown: opcode {op:#04x}"
        pops, pushes = effect
        if pops > depth:
            return "unknown: stored" if op in _STORES else f"unknown: opcode {op:#04x} takes it"
        depth = depth - pops + pushes
    return "unknown: the end of the code"


def class_literal_sinks(data: bytes, constants: list[str] | set[str]) -> dict[str, set[str]]:
    """{string literal of one class: the sinks of its ldc occurrences}; a string constant no instruction loads maps to
    {NOT_LOADED}. A class this cannot read gives every constant an unknown sink (kept as a need)."""
    sinks: dict[str, set[str]] = {}
    try:
        methods = iter_method_code(data)
        for _owner, _method, code, pool, _params in methods:
            steps, targets = instructions(code), jump_targets(code)
            for i, (_pc, op, arg) in enumerate(steps):
                if op in _LDC:
                    value = pool.string(arg)
                    if value is not None:
                        sinks.setdefault(value, set()).add(sink_of(steps, i, targets, pool))
    except (ClassFormatError, ValueError, IndexError, KeyError, struct.error):  # truncated code: struct.error (review)
        return {value: {"unknown: the class could not be read"} for value in constants}
    for value in constants:
        sinks.setdefault(value, {NOT_LOADED})
    return sinks


def is_mention(sinks: set[str]) -> bool:
    """True when every occurrence only names the literal: a mention sink, or a constant never loaded."""
    return bool(sinks) and all(s in MENTION_SINKS or s == NOT_LOADED for s in sinks)


__all__ = ["MENTION_SINKS", "NOT_LOADED", "class_literal_sinks", "is_mention", "sink_of"]
