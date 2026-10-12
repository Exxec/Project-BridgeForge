"""Mod Atlas: facts from a mod's jars, read through class-file constant pools and Code attributes (`atlas_classfile`).

ROADMAP item 67a: an id string is attributed to the call that consumes it (`getIndustry("farming")` becomes a `reads`
fact), not to the whole class, so a class that merely contains the word "habitable" and also calls `removeCondition`
no longer looks like it removes "habitable". 67e: `addScript(new X(...))` marks X as saved (addScript/addListener) or
transient (addTransient*), and synthetic fields (`this$0`, `val$x`) are never saved fields. Class-level guesses survive
only as UNKNOWN, for a class whose bytecode could not be scanned (`ClassInfo.code_ok`).
"""
from __future__ import annotations

from .zipsafe import MAX_CLASS_BYTES, read_limited

import re
import zipfile
from pathlib import Path
from typing import NamedTuple

from .atlas_classfile import (ACC_STATIC, ACC_SYNTHETIC, ACC_TRANSIENT, REGISTER_METHODS, ClassFormatError, ClassInfo,
                              parse_class)
from .atlas_code import (_MUTATORS, _PERSISTENT_REGISTER, CALLS, CAMPAIGN_PLUGIN_ROLES, CONSTANT_CLASSES, HEAVY_DESCRIPTORS,
                         ID_LIKE, MAX_DYNAMIC_PER_FILE, MAX_JAR_ENTRIES, PICK_PRIORITIES, SAVED_BASES, CodeResult, _digest,
                         _dynamic_fact, _is_role_hook, _simple)
from .atlas_data import Fact

WATCH = frozenset(CALLS) | REGISTER_METHODS
_CALLED_ID = re.compile(r"^[A-Za-z0-9_$.-]{1,80}$")


class Registered(NamedTuple):
    persistent: frozenset  # internal names handed to addScript/addListener
    transient_only: frozenset  # handed only to addTransient*: never saved


def registered_classes(infos: list[ClassInfo]) -> Registered:
    persistent, transient = set(), set()
    for info in infos:
        for method, target in info.registrations:
            (persistent if method in _PERSISTENT_REGISTER else transient).add(target)
    return Registered(frozenset(persistent), frozenset(transient - persistent))


def _heavy_type(descriptor: str, signature: str) -> str:
    for key, label in HEAVY_DESCRIPTORS.items():
        if key == descriptor:
            return label
        if key in signature:  # List<MarketAPI> keeps its element type only in the Signature attribute
            return f"{label} inside a collection ({signature})"
    return ""


def _saved_field_facts(info: ClassInfo, rel: str, roles: set[str], registered: Registered) -> list[Fact]:
    via_base = roles & SAVED_BASES
    if not ((via_base and info.name not in registered.transient_only) or info.name in registered.persistent):
        return []
    fqcn, how = info.name.replace("/", "."), "/".join(sorted(via_base)) or "added with addScript"
    facts = []
    for name, descriptor, flags in info.fields:
        if flags & (ACC_STATIC | ACC_TRANSIENT | ACC_SYNTHETIC) or name.startswith(("this$", "val$")):
            continue
        heavy = _heavy_type(descriptor, info.field_signatures.get(name, ""))
        if heavy:
            facts.append(Fact("saved-field", f"{fqcn}.{name}", "persists", rel, 0, f"{heavy} held by a saved script/plugin ({how})", "REVIEW"))
    return facts


def _call_site_facts(info: ClassInfo, rel: str) -> list[Fact]:
    facts, seen, dynamic = [], set(), 0
    for call in info.calls:
        if call.name not in CALLS:
            continue
        kind, action = CALLS[call.name]
        arg = call.args[-1] if call.args else ("none", "", "")
        if arg[0] == "str" and _CALLED_ID.match(arg[1]):
            fact = Fact(kind, arg[1], action, rel, 0, f"method={call.name} (jar call site)", "REVIEW")
        elif arg[0] == "field" and _simple(arg[1]) in CONSTANT_CLASSES:
            fact = Fact(kind, arg[2].lower(), action, rel, 0,
                        f"method={call.name} via {_simple(arg[1])}.{arg[2]} (id lower-cased from the constant name)", "REVIEW")
        elif dynamic < MAX_DYNAMIC_PER_FILE:
            dynamic += 1
            fact = _dynamic_fact(kind, action, rel, 0, call.name, "jar call site", arg[1] if arg[0] == "prefix" else "",
                                 f"{_simple(arg[1])}.{arg[2]}" if arg[0] == "field" else "")
        else:
            continue
        if fact not in seen:
            seen.add(fact)
            facts.append(fact)
    return facts


def _class_level_fallback(info: ClassInfo, rel: str) -> list[Fact]:
    """Used only when the class's bytecode could not be scanned: weaker, so UNKNOWN."""
    facts = []
    called = sorted(info.called_methods & REGISTER_METHODS)
    if called:
        facts.append(Fact("hook", info.name.replace("/", "."), "registers", rel, 0,
                          f"jar: calls {', '.join(called)} (class-level, bytecode not scanned)", "UNKNOWN"))
    if "getConditions" in info.called_methods and info.called_methods & set(_MUTATORS):
        facts.append(Fact("collection", "market.conditions", "mutates", rel, 0,
                          "jar: getConditions and a clear/sort call in one class (co-occurrence, bytecode not scanned)", "UNKNOWN"))
    return facts


def jar_class_facts(info: ClassInfo, rel: str, digest: str, registered: Registered) -> list[Fact]:
    fqcn = info.name.replace("/", ".")
    roles = {_simple(info.super_name)} | {_simple(name) for name in info.interfaces}
    facts = []
    if "$" not in info.name:
        facts.append(Fact("class", fqcn, "defines", rel, 0, f"jar sha={digest}", "SAFE"))
    facts += [Fact("hook", fqcn, "registers", rel, 0, f"declares {role}", "REVIEW") for role in sorted(roles) if _is_role_hook(role)]
    if roles & CAMPAIGN_PLUGIN_ROLES:
        priorities = info.field_refs & PICK_PRIORITIES
        priority = next(iter(priorities)) if len(priorities) == 1 else "?"
        facts += [Fact("campaign-pick", name, "registers", rel, 0, f"{fqcn} priority={priority}", "REVIEW")
                  for name in info.methods if re.match(r"pick[A-Z]", name)]
    facts += _saved_field_facts(info, rel, roles, registered)
    if not info.code_ok:
        return facts + _class_level_fallback(info, rel)
    facts += [Fact("hook", target.replace("/", "."), "registers", rel, 0, f"jar: {method}(new {_simple(target)}) in {fqcn}", "REVIEW")
              for method, target in sorted(set(info.registrations))]
    if any("getConditions" in names and names & set(_MUTATORS) for names in info.method_calls):
        facts.append(Fact("collection", "market.conditions", "mutates", rel, 0, "jar: getConditions and a clear/sort call in one method", "REVIEW"))
    return facts + _call_site_facts(info, rel)


def _jar_literals(info: ClassInfo, rel: str) -> list[tuple[str, int, str, str]]:
    ctx = "" if info.code_ok else ",".join(sorted(info.called_methods & CALLS.keys()))
    return [(rel, 0, value, ctx) for value in sorted({s for s in info.strings if ID_LIKE.match(s)})]


def _read_classes(archive: zipfile.ZipFile, names: list[str]) -> list[tuple[str, str, ClassInfo]]:
    classes = []
    for name in names:
        try:
            data = read_limited(archive, name, MAX_CLASS_BYTES)  # bounded: a jar is untrusted input
            classes.append((name, _digest(data), parse_class(data, WATCH)))
        except (ClassFormatError, zipfile.BadZipFile, OSError, RuntimeError, EOFError):
            continue
    return classes


def extract_jar(root: Path, jar: Path) -> CodeResult:
    jar_rel = jar.relative_to(root).as_posix()
    unreadable = lambda why: CodeResult([Fact("jar", jar_rel, "unreadable", jar_rel, 0, why, "UNKNOWN")], [], {})  # noqa: E731
    try:
        with zipfile.ZipFile(jar) as archive:
            names = [n for n in archive.namelist() if n.endswith(".class")]
            if len(names) > MAX_JAR_ENTRIES:
                return unreadable("too many entries")
            classes = _read_classes(archive, names)
    except (zipfile.BadZipFile, OSError) as exc:
        return unreadable(f"{type(exc).__name__}: {exc}")
    registered = registered_classes([info for _, _, info in classes])
    facts: list[Fact] = []
    literals: list[tuple[str, int, str, str]] = []
    constants: dict = {}
    for name, digest, info in classes:
        rel = f"{jar_rel}!{name}"
        facts += jar_class_facts(info, rel, digest, registered)
        literals += _jar_literals(info, rel)
        constants.update({(_simple(info.name), field): value for field, value in info.constants.items()})
    return CodeResult(facts, literals, constants)
