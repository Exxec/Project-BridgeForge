"""Settings keys a mod reads that no settings.json defines (owner crash log 2026-10-04).

Exigency 0.8's Avesta black market read `Global.getSettings().getFloat("blackMarketMinSupplies")` (and ...MinFuel,
...MinMarines): vanilla dropped those keys in 0.9a (0.8.1a had 50, 50, 30), Exigency never defined them, and RC8 threw
`JSONException: JSONObject["blackMarketMinSupplies"] not found` when the market was opened. A settings read resolves
against the merged settings: vanilla's settings.json plus every enabled mod's (lists add; keys merge). So a literal key
is suspect when neither RC8's settings.json nor the mod's nor a declared dependency's defines it.

Reads are found in Java sources (`getSettings().getFloat("key")`) and, with a JDK, in jar classes via javap (`ldc
String key` followed by `SettingsAPI.getFloat/getInt/getBoolean/getString/getColor:(Ljava/lang/String;)`). `getSettingsJSON()`
reads with opt*/has guards are not flagged.

Two kinds of read are not misses (98.8; Wide Horizons 1.5.1b raised 15 keys, none missing). A wrong exemption hides a crash
and a missed one costs an acceptance, so every uncertain case below counts as a miss:
- *A key the mod writes.* `SettingsAPI.setFloat`/`setBoolean` put the key into the settings JSONObject the getters read (RC9
  `StarfarerSettings$1.setFloat/setBoolean` -> `JSONObject.put` on `StarfarerSettings.öØ0000`, the field `getFloat` and
  `getBoolean` read; javap 2026-11-26). Wide Horizons sets 14 keys from its LunaLib settings. A key written in one of the
  mod's jars, or in a loose script the game runs (under `data/`, not shadowed by a jar class), counts as defined; the order
  of write and read is not checked.
- *A read under a catch that does not rethrow.* Each getter rethrows a missing key as `RuntimeException(JSONException)`
  (javap 2026-11-26: `getFloat`/`getInt` via `StarfarerSettings.if`, `getBoolean`, `getString`, `getColor`), so only a handler
  of RuntimeException, Exception or Throwable catches it, not one of JSONException. Wide Horizons reads
  `campaignSecondsPerDay`, which no settings file has, inside `catch (Throwable)` that returns a fallback. The table is read
  the way the JVM reads it (`_caught`). Jar classes only: a source's try/catch is not read (no case yet).
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import NamedTuple

from bridgeforge.bytecode.javap_batch import class_listings
from bridgeforge.zipsafe import read_class

GETTERS = ("getFloat", "getInt", "getBoolean", "getString", "getColor", "getDouble", "getLong")
SETTERS = ("setFloat", "setBoolean")
# What a setter writes and which getters read it (javap of RC9 StarfarerSettings, 2026-11-26): setFloat fills the float cache
# that getFloat and getInt read (both go through `StarfarerSettings.if`), setBoolean the boolean cache getBoolean reads. A
# boolean read as a float misses its cache and fails in JSONObject.getDouble, so a write covers only reads of its own kind.
SETTER_KIND = {"setFloat": "float", "setBoolean": "boolean"}
GETTER_KIND = {"getFloat": "float", "getInt": "float", "getBoolean": "boolean"}
_SOURCE_READ = re.compile(r"getSettings\s*\(\s*\)\s*\.\s*(" + "|".join(GETTERS) + r")\s*\(\s*\"([^\"]+)\"\s*\)")
# The literal must be the whole key (`setFloat("wh_" + id, v)` names none), the receiver the game's own Global, and the value
# a literal: anything else may be null, and a null write makes the next read throw (the cache holds the null).
_SOURCE_WRITE = re.compile(r"\bGlobal\s*\.\s*getSettings\s*\(\s*\)\s*\.\s*(" + "|".join(SETTERS) + r")\s*\(\s*\"([^\"]+)\"\s*,"
                           r"\s*(?:-?\d+(?:\.\d+)?[fFdD]?|true|false)\s*\)")
_PACKAGE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.M)
_LDC = re.compile(r"ldc(?:_w)?\s+#\d+\s+// String (.+)$")
_SETTINGS_CALL = re.compile(r"invokeinterface\s+#\d+,\s*\d+\s+// InterfaceMethod com/fs/starfarer/api/SettingsAPI\.(" + "|".join(GETTERS) + r"):\(Ljava/lang/String;\)")
_SETTER_CALL = re.compile(r"invokeinterface\s+#\d+,\s*\d+\s+// InterfaceMethod com/fs/starfarer/api/SettingsAPI\.(" + "|".join(SETTERS) + r"):\(Ljava/lang/String;")
# A value that cannot be null: a boxing call, a Boolean constant or a new Float/Boolean, right before the setter.
_BOXED_VALUE = re.compile(r"// (?:Method java/lang/(?:Float|Boolean)\.(?:valueOf|\"<init>\")|Field java/lang/Boolean\.(?:TRUE|FALSE)):")
# Calls a handler may make and still return: logging, building its text, a java.lang exception's constructor.
_SAFE_CALL = re.compile(r"// (?:(?:Interface)?Method (?:org/apache/log4j/(?:Logger|Category)\.\w+|com/fs/starfarer/api/Global\.getLogger"
                        r"|java/lang/Throwable\.(?:printStackTrace|getMessage|getLocalizedMessage|toString)"
                        r"|java/lang/StringBuilder\.(?:\"<init>\"|append|toString)|java/lang/String\.valueOf|java/io/PrintStream\.print(?:ln)?"
                        r"|java/lang/\w*(?:Exception|Error|Throwable)\.\"<init>\")|InvokeDynamic #\d+:makeConcatWithConstants):")
_GET_SETTINGS = re.compile(r"invokestatic\s+#\d+\s+// Method com/fs/starfarer/api/Global\.getSettings:\(\)Lcom/fs/starfarer/api/SettingsAPI;")
_INVOKE_DESCRIPTOR = re.compile(r"//.*:\(([^)]*)\)(\S+)\s*$")
_DESCRIPTOR_PART = re.compile(r"\[*(?:[ZBCSIJFD]|L[^;]+;)")
_INSTRUCTION = re.compile(r"^\s*(\d+):\s+([a-z]\w*)")  # a letter first: a switch's case lines (`  1: 32`) are not instructions
_HANDLER_ROW = re.compile(r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+(?:Class\s+(\S+)|any)\s*$")
_GOTO = re.compile(r"goto(?:_w)?\s+(\d+)")
# Where a statement ends, a getSettings() before it can no longer be the receiver of a later set* call.
_STATEMENT_END = re.compile(r"^(?:[adfil]store(?:_\d)?|[abcdfils]astore|pop2?|[adfil]?return|athrow|put(?:field|static)"
                            r"|if\w*|goto(?:_w)?|tableswitch|lookupswitch|jsr(?:_w)?)$")
_RETURN = re.compile(r"^[adfil]?return$")
_BRANCH = re.compile(r"^(?:if\w*|tableswitch|lookupswitch|jsr(?:_w)?|ret)$")
# Stack effects (values taken, values left) of the instructions a setter's value is built from; anything else is unknown.
_PUSH = re.compile(r"^(?:[adfil]load(?:_\d)?|[adfil]const_\w+|bipush|sipush|ldc(?:_w|2_w)?|new|getstatic)$")
_SAME = re.compile(r"^(?:[dfil]2[bcdfils]|[dfil]neg|checkcast|instanceof|arraylength|getfield)$")
_COMBINE = re.compile(r"^(?:[dfil](?:add|sub|mul|div|rem)|[il](?:and|or|xor|shl|shr|ushr)|[abcdfils]aload|lcmp|[df]cmp[gl])$")
CATCHES_MISSING_KEY = frozenset({"java/lang/RuntimeException", "java/lang/Exception", "java/lang/Throwable"})
MAX_RETHROWS = 4  # handlers followed through rethrows before a read counts as uncaught


def settings_keys(*settings_files: Path) -> set[str]:
    """Top-level keys of the given settings.json files (lenient: RC8 org.json rules)."""
    from bridgeforge.scan.scanner import _load_lenient_json_file

    keys: set[str] = set()
    for path in settings_files:
        if path and Path(path).is_file():
            data = _load_lenient_json_file(Path(path))
            if isinstance(data, dict):
                keys |= set(data)
    return keys


OVERRIDE_CLASSES = ("add", "same", "change")


def classify_overrides(mod: dict, vanilla: dict, prefix: str = "") -> dict[str, str]:
    """Dotted path -> `add` | `same` | `change` for every key the mod shares with vanilla's settings.json (ROADMAP item 73 C4).

    - `add`: a list that RC8 merges (RC8-02, docs/RC8_BEHAVIOUR.md: settings.json lists add to vanilla's list, they do
      not replace it) and that carries items vanilla's list lacks. It cannot take anything away.
    - `same`: the value equals RC8's, or a list whose every item vanilla's list already has: nothing changes.
    - `change`: a scalar or type that differs; it wins over RC8's value for every mod and the base game.
    Objects are compared value by value (RC8-01: nested keys merge, so a key only the mod has is not listed at all)."""
    result: dict[str, str] = {}
    for key, value in mod.items():
        if key not in vanilla:
            continue
        path, theirs = f"{prefix}{key}", vanilla[key]
        if isinstance(value, dict) and isinstance(theirs, dict):
            result.update(classify_overrides(value, theirs, path + "."))
        elif isinstance(value, list) and isinstance(theirs, list):
            result[path] = "same" if all(item in theirs for item in value) else "add"
        else:
            result[path] = "same" if value == theirs else "change"
    return result


_MOD_GUARD =re.compile(r"isModEnabled\s*\(\s*\"[^\"]+\"\s*\)\s*(?:&&|\?)")


def source_reads(text: str) -> list[tuple[int, str, str]]:
    """(line, getter, key) for literal settings reads in Java source (comments must be blanked).

    A read guarded earlier in the same statement by `isModEnabled("x") &&` (or `? ...`) is left out: the key is that
    other mod's setting, read only when it is enabled (Kadur Remnant reads IndEvo's PirateHaven/dryDock and Better
    Deserving S-Mods' BuiltInSMod that way, 2026-10-05)."""
    found = []
    for m in _SOURCE_READ.finditer(text):
        statement_start = max(text.rfind(";", 0, m.start()), text.rfind("{", 0, m.start()), text.rfind("}", 0, m.start()))
        if _MOD_GUARD.search(text[statement_start + 1:m.start()]):
            continue
        found.append((text.count("\n", 0, m.start()) + 1, m.group(1), m.group(2)))
    return found


def guarded_keys(text: str) -> set[str]:
    """Keys this source reads only behind an isModEnabled guard (see source_reads)."""
    guarded = set()
    for m in _SOURCE_READ.finditer(text):
        statement_start = max(text.rfind(";", 0, m.start()), text.rfind("{", 0, m.start()), text.rfind("}", 0, m.start()))
        if _MOD_GUARD.search(text[statement_start + 1:m.start()]):
            guarded.add(m.group(2))
    return guarded


def source_writes(text: str) -> set[tuple[str, str]]:
    """(key, kind) a Java source writes with `Global.getSettings().setFloat/setBoolean("key", <literal>)` (comments must be
    blanked). Only a source the game runs counts as a definition (`loose_script_class`)."""
    return {(m.group(2), SETTER_KIND[m.group(1)]) for m in _SOURCE_WRITE.finditer(text)}


def loose_script_class(relative: str, text: str) -> str | None:
    """The class a mod source defines when the game can run it as a loose script: under the mod's `data/` folder, with a package
    that matches its folders (the script loader finds a class by that path), named by package and file name. None for any
    other source, such as a bundled `src/` tree the game never compiles. A jar class of the same name wins over the loose copy
    (memory note: loose script vs jar precedence), which the caller checks."""
    path = Path(relative)
    package = _PACKAGE.search(text)
    if package is None or len(path.parts) < 2 or path.parts[0].lower() != "data":
        return None
    if [part.lower() for part in path.parent.parts] != package.group(1).lower().split("."):
        return None
    return f"{package.group(1)}.{path.stem}"


def listed_jars(root: Path) -> set[str]:
    """The jars mod_info.json lists, as paths relative to the mod root: the only ones the game loads (a leftover
    `jars/old/x.jar` never runs)."""
    from bridgeforge.mod_files import read_mod_info

    entries = (read_mod_info(Path(root)) or {}).get("jars")
    if not isinstance(entries, list):
        return set()
    return {Path(entry.replace("\\", "/")).as_posix().removeprefix("./") for entry in entries if isinstance(entry, str)}


class _Method(NamedTuple):
    instructions: tuple[tuple[int, str, str], ...]  # (offset, opcode, line)
    handlers: tuple[tuple[int, int, int, str | None], ...]  # (from, to, target, caught class; None for `any`, a finally)

    def index_of(self, offset: int) -> int | None:
        return next((i for i, (at, _op, _line) in enumerate(self.instructions) if at == offset), None)


def _methods(listing: str) -> list[_Method]:
    """A javap -c listing's method bodies, each with its exception table. A body starts at its `Code:` line."""
    methods: list[_Method] = []
    instructions: list[tuple[int, str, str]] = []
    handlers: list[tuple[int, int, int, str | None]] = []
    for line in listing.splitlines():
        if line.strip() == "Code:":
            if instructions:
                methods.append(_Method(tuple(instructions), tuple(handlers)))
            instructions, handlers = [], []
        elif (ins := _INSTRUCTION.match(line)) is not None:
            instructions.append((int(ins.group(1)), ins.group(2), line))
        elif (row := _HANDLER_ROW.match(line)) is not None:
            handlers.append((int(row.group(1)), int(row.group(2)), int(row.group(3)), row.group(4)))
    if instructions:
        methods.append(_Method(tuple(instructions), tuple(handlers)))
    return methods


def _handler_outcome(method: _Method, target: int) -> tuple[str, int | None]:
    """What the handler at `target` does: ("returns", None), ("throws", offset of its athrow) or ("unknown", None).

    It is followed instruction by instruction and through gotos: javac's try-with-resources handler closes the resource and
    jumps to an athrow, and so does a catch block holding a try or a synchronized block (review of 98.8). A conditional branch,
    a loop or the end of the code is unknown, and unknown counts as not caught. So is a call, other than logging or building
    an exception (`_SAFE_CALL`): `catch (Exception e) { fail(e); return 0f; }` throws from inside `fail` (second review)."""
    i, seen = method.index_of(target), set()
    while i is not None and i < len(method.instructions) and i not in seen:
        seen.add(i)
        offset, opcode, line = method.instructions[i]
        if _BRANCH.match(opcode) or (opcode.startswith("invoke") and not _SAFE_CALL.search(line)):
            return "unknown", None
        if opcode == "athrow":
            return "throws", offset
        if _RETURN.match(opcode):
            return "returns", None
        if opcode.startswith("goto"):
            jump = _GOTO.search(line)
            i = method.index_of(int(jump.group(1))) if jump else None
            continue
        i += 1
    return "unknown", None


def _caught(method: _Method, offset: int, rethrows: int = 0) -> bool:
    """Whether a missing key thrown at `offset` ends in a handler that returns. The JVM takes the first row of the exception
    table, in order, that covers the offset and catches the thrown class: the getter's RuntimeException is caught by a
    RuntimeException, Exception, Throwable or `any` (finally) row. When that handler throws, what it throws is unknown, so
    only a Throwable or `any` row can be the next stop, and any other covering row first leaves it undecided."""
    for start, end, target, caught in method.handlers:
        if not start <= offset < end:
            continue
        if rethrows == 0 and caught is not None and caught not in CATCHES_MISSING_KEY:
            continue  # cannot catch java.lang.RuntimeException: the JVM looks on
        if rethrows > 0 and caught not in (None, "java/lang/Throwable"):
            return False
        outcome, thrown_at = _handler_outcome(method, target)
        if outcome == "throws" and thrown_at is not None and rethrows < MAX_RETHROWS:
            return _caught(method, thrown_at, rethrows + 1)
        return outcome == "returns"
    return False


def javap_reads(listing: str) -> list[tuple[str, str]]:
    """(getter, key) for `ldc String key; invokeinterface SettingsAPI.getX(String)` pairs in a javap -c listing, except reads
    that end in a handler that returns (`_caught`)."""
    found = []
    for method in _methods(listing):
        previous = None
        for offset, _opcode, line in method.instructions:
            call = _SETTINGS_CALL.search(line)
            if call and previous is not None and not _caught(method, offset):
                found.append((call.group(1), previous))
            ldc = _LDC.search(line)
            previous = ldc.group(1).strip() if ldc else None  # only the instruction right before the call counts
    return found


def _stack_effect(opcode: str, line: str) -> tuple[int, int] | None:
    """(values taken, values left) by one instruction of a setter's value; None for one this does not model."""
    if _PUSH.match(opcode):
        return 0, 1
    if opcode == "dup":
        return 1, 2
    if _SAME.match(opcode):
        return 1, 1
    if _COMBINE.match(opcode):
        return 2, 1
    descriptor = _INVOKE_DESCRIPTOR.search(line) if opcode.startswith("invoke") else None
    if descriptor is None:
        return None
    taken = len(_DESCRIPTOR_PART.findall(descriptor.group(1))) + (0 if opcode in ("invokestatic", "invokedynamic") else 1)
    return taken, 0 if descriptor.group(2) == "V" else 1


def _only_adds_one_value(lines: tuple[tuple[int, str, str], ...]) -> bool:
    """Whether these instructions, in order, leave exactly one value on top of the stack and never take anything that was
    there before them: then what was below them (the key, and under it the receiver) is what the next call consumes."""
    depth = 0
    for _offset, opcode, line in lines:
        effect = _stack_effect(opcode, line)
        if effect is None or effect[0] > depth:
            return False
        depth += effect[1] - effect[0]
    return depth == 1


def javap_writes(listing: str) -> set[tuple[str, str]]:
    """(key, kind) written by `Global.getSettings(); ldc String key; <value>; invokeinterface SettingsAPI.setFloat/setBoolean`.

    A write counts only when the stack proves it: between the key's ldc and the setter, the instructions leave exactly one value
    (`_only_adds_one_value`), so the setter takes that getSettings() as its receiver and that literal as its key. So
    `setFloat(key("x"), v)` and `setFloat("x".concat(y), v)` name no key, and a getter nested in the value
    (`setFloat("a", getSettings().getFloat("b"))`) is not taken for the written one. The value must also be boxed right
    there (`_BOXED_VALUE`): a Float from a call or a cast may be null, and a null write makes the next read throw. A value with
    a branch (`setBoolean("k", id != null)`), an instruction not modelled, or a receiver kept in a local is a missed write:
    its key stays reported."""
    written: set[tuple[str, str]] = set()
    for method in _methods(listing):
        candidates: list[int] = []  # instruction indexes of `getSettings(); ldc String` in the current statement
        lines = method.instructions
        for i, (_offset, opcode, line) in enumerate(lines):
            if _GET_SETTINGS.search(line) and i + 1 < len(lines) and _LDC.search(lines[i + 1][2]):
                candidates.append(i)
            elif (setter := _SETTER_CALL.search(line)) is not None:
                for start in reversed(candidates):
                    if _only_adds_one_value(lines[start + 2:i]):
                        if _BOXED_VALUE.search(lines[i - 1][2]):
                            written.add((_LDC.search(lines[start + 1][2]).group(1).strip(), SETTER_KIND[setter.group(1)]))
                        break
                candidates = []
            elif _STATEMENT_END.match(opcode):
                candidates = []
    return written


class JarSettings(NamedTuple):
    reads: list[tuple[str, str, str]]  # (class entry, getter, key)
    writes: frozenset[tuple[str, str]]  # (key, kind)


def jar_settings(jar: Path, javap: Path) -> JarSettings:
    """Settings reads (class, getter, key) and written keys of the classes in a jar that use SettingsAPI, from one javap launch
    per jar (96.5 P1). A class whose entry name is not a plain binary name is skipped: javap would read it as an option or a
    path (93.45)."""
    try:
        with zipfile.ZipFile(jar) as archive:
            names = [n for n in archive.namelist() if n.endswith(".class") and b"com/fs/starfarer/api/SettingsAPI" in (read_class(archive, n) or b"")]
    except (OSError, zipfile.BadZipFile):
        return JarSettings([], frozenset())
    reads: list[tuple[str, str, str]] = []
    writes: set[tuple[str, str]] = set()
    for name, listing in class_listings(javap, jar, names).items():
        reads += [(name, getter, key) for getter, key in javap_reads(listing)]
        writes |= javap_writes(listing)
    return JarSettings(reads, frozenset(writes))
