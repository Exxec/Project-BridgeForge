"""Atlas census, save-risk part (ROADMAP-3 81.3): what a mod puts into a save, and what can break one. STATIC.

Rows (area `save`):
  persistent-key / memory-key   a string constant given to `getPersistentData().put` / a `MemoryAPI.set*` call
  duplicate-script-risk         `onGameLoad` calls addScript/addListener (saved) with no hasScript/remove/transient guard,
                                so each load can stack another copy (a class's own `onGameLoad` only, helpers not followed)
  serialization-hook            a class declaring readResolve or writeReplace (save-format migration code)
  transient-field               a `transient` instance field in a class that looks saved (EveryFrameScript, BaseIntelPlugin
                                or handed to addScript/addListener): it is dropped on load and comes back null/zero
"""
from __future__ import annotations

import re

from .atlas_census import ClassRefs, LooseFile, Tally
from .atlas_classfile import ACC_STATIC, ACC_TRANSIENT
from .atlas_code import _PERSISTENT_REGISTER, SAVED_BASES, _simple

SAVE_WATCH = frozenset({"put", "set", "setFloat", "setLong", "setInt"})
GUARDS = frozenset({"hasScript", "hasTransientScript", "hasListener", "hasListenerOfClass", "removeScriptsOfClass",
                    "removeScript", "removeListener", "removeListenerOfClass", "getScripts", "getListeners",
                    "getTransientScripts", "getTransientListeners"})
PERSISTENT_ADDS = frozenset(_PERSISTENT_REGISTER)
SERIALIZATION_HOOKS = ("readResolve", "writeReplace")
MEMORY_OWNER = "com/fs/starfarer/api/campaign/rules/MemoryAPI"

_PERSISTENT_PUT = re.compile(r'getPersistentData\s*\(\s*\)\s*\.\s*put\s*\(\s*"([^"\\n]{1,120})"')
_MEMORY_SET = re.compile(r'getMemory\w*\s*\([^()]*\)\s*\.\s*set\w*\s*\(\s*"([^"\\n]{1,120})"')
_ON_LOAD = re.compile(r"\bvoid\s+onGameLoad\s*\([^)]*\)\s*(?:throws\s+[\w.,\s]+)?\{")
_ADD_CALL = re.compile(r"\b(addScript|addListener)\s*\(")
_GUARD_CALL = re.compile(r"\b(" + "|".join(sorted(GUARDS)) + r")\s*\(")
_TRANSIENT_FIELD = re.compile(r"\btransient\s+(?!static\b)[\w<>\[\],.? ]+?\s+(\w+)\s*(?:=|;)")
_SAVED_BASE_RE = re.compile(r"\b(?:extends|implements)\b[^{;]*\b(" + "|".join(sorted(SAVED_BASES)) + r")\b")
_REGISTER_NEW = re.compile(r"\b(addListener|addScript)\s*\(\s*new\s+([\w.]+)")


def _body_after(text: str, start: int) -> str:
    depth, pos = 1, start
    while pos < len(text) and depth:
        depth += (text[pos] == "{") - (text[pos] == "}")
        pos += 1
    return text[start:pos]


def save_from_jar(classes: list[ClassRefs], tally: Tally) -> None:
    persistent_targets = {target for entry in classes for method, target in entry.info.registrations if method in PERSISTENT_ADDS}
    transient_targets = {target for entry in classes for method, target in entry.info.registrations if method not in PERSISTENT_ADDS}
    for entry in classes:
        info = entry.info
        if "getPersistentData" in info.called_methods:
            for call in info.calls:
                if call.name == "put" and call.args and call.args[-1][0] == "str" and not call.owner.startswith("com/fs/"):
                    tally.add("save", "persistent-key", call.args[-1][1], entry.rel)
        for call in info.calls:
            if call.owner == MEMORY_OWNER and call.args and call.args[0][0] == "str":
                tally.add("save", "memory-key", call.args[0][1], entry.rel)
        dotted_name = entry.name.replace("/", ".")
        for index, method in enumerate(info.code_methods):
            names = info.method_calls[index]
            if method == "onGameLoad" and names & PERSISTENT_ADDS and not names & GUARDS:
                tally.add("save", "duplicate-script-risk", dotted_name, entry.rel)
        for hook in SERIALIZATION_HOOKS:
            if hook in info.methods:
                tally.add("save", "serialization-hook", f"{dotted_name}.{hook}", entry.rel)
        roles = {_simple(info.super_name)} | {_simple(name) for name in info.interfaces}
        saved = (roles & SAVED_BASES and entry.name not in transient_targets - persistent_targets) or entry.name in persistent_targets
        if saved:
            for name, _descriptor, flags in info.fields:
                if flags & ACC_TRANSIENT and not flags & ACC_STATIC:
                    tally.add("save", "transient-field", f"{dotted_name}.{name}", entry.rel)


def save_from_loose(files: list[LooseFile], tally: Tally) -> None:
    persistent_targets = {_simple(m.group(2)) for item in files for m in _REGISTER_NEW.finditer(item.text)}
    for item in files:
        for pattern, kind in ((_PERSISTENT_PUT, "persistent-key"), (_MEMORY_SET, "memory-key")):
            for key in {m.group(1) for m in pattern.finditer(item.text)}:
                tally.add("save", kind, key, item.rel)
        stem = item.rel.rsplit("/", 1)[-1].removesuffix(".java")
        for match in _ON_LOAD.finditer(item.text):
            body = _body_after(item.text, match.end())
            if _ADD_CALL.search(body) and not _GUARD_CALL.search(body):
                tally.add("save", "duplicate-script-risk", f"{item.package}.{stem}".lstrip("."), item.rel)
        for hook in SERIALIZATION_HOOKS:
            if re.search(r"\b" + hook + r"\s*\(", item.text):
                tally.add("save", "serialization-hook", f"{item.package}.{stem}.{hook}".lstrip("."), item.rel)
        if _SAVED_BASE_RE.search(item.text) or stem in persistent_targets:
            for field in {m.group(1) for m in _TRANSIENT_FIELD.finditer(item.text)}:
                tally.add("save", "transient-field", f"{item.package}.{stem}.{field}".lstrip("."), item.rel)
