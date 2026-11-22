"""94.G2: closure rules beyond vendor-plan's, applied by `gene describe` (docs/FEATURE_GENOME_ROADMAP.md section 6).

The first pilot (P1, Scrapyard Armories' `sa_lobster_tanks` hull mod) showed two gaps in a gene's closure: the settings keys
its script reads were only a whole-file SUSPECT on `settings.json`, and the vanilla commodities it handles were not needs.

**Settings keys (evidence only).** A key is part of the gene when a member script passes it to a SettingsAPI getter
(`getFloat`, `getInt`, `getBoolean`, `getString`, `getColor`, `getJSONObject`, ...): as a string literal, or as a
`static final String` constant holding that literal, in a loose `.java` member; as the string argument of the call in a jar
member's bytecode. The key becomes a `json-entry` member, `data/config/settings.json#/<key>`, when the mod's settings.json
has it; `setting:<key>` in `needs.vanilla` when only the core's has it; missing otherwise. A key that is only mentioned (a
settings key containing a closure id that no member reads) stays SUSPECT, at key level, never by prefix.

**Commodities.** `Commodities.X` in a member script is resolved against the core's own `Commodities` class constants and
becomes `commodity:<id>` in `needs.vanilla` when the core's commodities.csv has it.

A `json-entry` member's hash is the SHA-256 of its parsed value as canonical JSON (sorted keys, `,`/`:` separators, UTF-8,
integral numbers as integers), parsed with the suite's one lenient reader, so `5` and `5.0`, or two layouts of one object,
are the same allele.
"""
from __future__ import annotations

import functools
import hashlib
import json
import re
import zipfile
from pathlib import Path

from bridgeforge.scan.scan_json import _parse_json

SETTINGS_FILE = "data/config/settings.json"
GETTERS = ("getFloat", "getInt", "getInteger", "getBoolean", "getString", "getColor", "getJSONObject", "getJSONArray",
           "getLong", "getDouble", "getSprite")
_GETTER_CALL = re.compile(r"\.(" + "|".join(GETTERS) + r")\s*\(\s*(?:\"([^\"\\]+)\"|([A-Za-z_][\w.]*))\s*\)")
_CONSTANT = re.compile(r"\bstatic\s+final\s+String\s+([A-Za-z_]\w*)\s*=\s*\"([^\"\\]+)\"\s*;")
_COMMODITY = re.compile(r"\bCommodities\.([A-Z][A-Z0-9_]*)\b")
COMMODITIES_CLASS = "com/fs/starfarer/api/impl/campaign/ids/Commodities.class"


def pointer(key: str) -> str:
    """A JSON Pointer (RFC 6901) to a top-level key."""
    return "/" + key.replace("~", "~0").replace("/", "~1")


def _canonical(value: object) -> object:
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {str(k): _canonical(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_canonical(v) for v in value]
    return value


def value_sha256(value: object) -> str:
    text = json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _settings(root: Path) -> dict:
    path = Path(root) / SETTINGS_FILE
    if not path.is_file():
        return {}
    try:
        data, _ = _parse_json(path.read_text(encoding="utf-8-sig", errors="replace"))
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def keys_read_by_source(text: str) -> set[str]:
    """Settings keys a loose script passes to a SettingsAPI getter, as a literal or a static final String constant."""
    constants = dict(_CONSTANT.findall(text))
    keys = set()
    for _getter, literal, name in _GETTER_CALL.findall(text):
        if literal:
            keys.add(literal)
        elif name.rsplit(".", 1)[-1] in constants:
            keys.add(constants[name.rsplit(".", 1)[-1]])
    return keys


def keys_read_by_class(data: bytes) -> set[str]:
    """Settings keys a compiled class passes to a one-String SettingsAPI getter: a constant, directly or through a local.
    `getString(category, id)` reads the string tables, not settings.json, and is not a key (P3, 2026-11-20: Eridani's
    `getString("scripts", id)` read as a missing settings key `scripts`)."""
    import struct

    from bridgeforge.atlas.atlas_classfile import ClassFormatError, iter_method_code, last_argument_constants

    def getter(owner: str, name: str, descriptor: str) -> bool:
        return owner.endswith("SettingsAPI") and name in GETTERS and descriptor.startswith("(Ljava/lang/String;)")

    try:
        methods = iter_method_code(data)
    except ClassFormatError:
        return set()
    keys: set[str] = set()
    for _owner, _method, code, pool, params in methods:
        try:
            keys |= {constant for *_call, constant in last_argument_constants(code, pool, getter, params) if constant}
        except (ClassFormatError, struct.error, IndexError, KeyError):
            continue  # an unreadable method names no key; the others still do
    return keys


def _core_commodities(vanilla_core: Path | None) -> tuple[dict[str, str], set[str]]:
    """({constant name: id} from the core's Commodities class, {ids in the core's commodities.csv})."""
    if vanilla_core is None:
        return {}, set()
    from bridgeforge.atlas.atlas_classfile import ClassFormatError, parse_class
    from bridgeforge.vendor_plan import _rows
    from bridgeforge.zipsafe import MAX_CLASS_BYTES, read_limited

    constants: dict[str, str] = {}
    api = Path(vanilla_core) / "starfarer.api.jar"
    try:
        with zipfile.ZipFile(api) as archive:
            constants = parse_class(read_limited(archive, COMMODITIES_CLASS, MAX_CLASS_BYTES)).constants
    except (OSError, KeyError, zipfile.BadZipFile, ValueError, ClassFormatError):
        constants = {}
    return constants, set(_rows(Path(vanilla_core), "data/campaign/commodities.csv"))


_STRING_LITERAL = re.compile(r'"((?:[^"\\\n]|\\.)*)"')


def _jar_class_sinks(root: Path, member: dict) -> dict[str, set[str]] | None:
    """{literal: sinks} of one jar-class member (genome/literal_sinks.py), or None when it cannot be read."""
    from bridgeforge.genome.literal_sinks import class_literal_sinks
    from bridgeforge.scan.scan_classfile import _parse_class_file
    from bridgeforge.zipsafe import MAX_CLASS_BYTES, read_limited

    jar, _, entry = member["path"].partition("!")
    try:
        with zipfile.ZipFile(Path(root) / jar) as archive:
            data = read_limited(archive, entry, MAX_CLASS_BYTES)
    except (OSError, KeyError, zipfile.BadZipFile, ValueError):
        return None
    info = _parse_class_file(data)
    return class_literal_sinks(data, info.string_constants) if info is not None else None


@functools.lru_cache(maxsize=16)
def _lookup_only_cached(jars: tuple[tuple[str, int, int], ...], scripts: tuple[tuple[str, int, int], ...]) -> frozenset[str]:
    from bridgeforge.genome.literal_sinks import lookup_only_maps
    from bridgeforge.scan.scan_classfile import iter_class_files_in_jars
    from bridgeforge.vendor_plan import _COMMENTS, _PACKAGE

    unreadable: list[str] = []
    skipped: list[str] = []
    classes, names = [], set()
    for _jar, member, data in iter_class_files_in_jars([Path(path) for path, _s, _t in jars], unreadable, skipped_entries=skipped):
        classes.append(data)
        names.add(member[:-len(".class")].replace("/", "."))
    if unreadable or skipped:
        return frozenset()  # a jar or class not read might iterate the map (review 2026-11-20)
    loose = []
    for path, _size, _time in scripts:  # loose scripts, not a jar class's shipped source: the game compiles them
        text = _COMMENTS.sub("", Path(path).read_text(encoding="utf-8-sig", errors="replace"))
        package = _PACKAGE.search(text)
        if (f"{package.group(1)}.{Path(path).stem}" if package else Path(path).stem) not in names:
            loose.append(text)
    return lookup_only_maps(classes, "\n".join(loose))


def lookup_only(root: Path) -> frozenset[str]:
    """The map fields of the mod's loaded classes that are only looked up (slice 14, `literal_sinks.lookup_only_maps`),
    cached by the paths, sizes and times of the loaded jars and the mod's .java files."""
    from bridgeforge.scan.scan_classfile import _loaded_mod_jars

    def stats(paths) -> tuple[tuple[str, int, int], ...]:
        return tuple((str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in sorted(Path(x).resolve() for x in paths))

    root = Path(root).resolve()
    return _lookup_only_cached(stats(_loaded_mod_jars(root)), stats(root.rglob("*.java")))


def code_literals(root: Path, members: list[dict]) -> set[str]:
    """The string literals of a gene's code members that may name what the code needs: every literal of a loose script (by
    text), and each literal of a jar class used at least once other than as a mention (slice 13, owner 2026-11-20:
    `literal_sinks.is_mention`; slice 14: a key of a map field that is only looked up is a mention too)."""
    from bridgeforge.genome.literal_sinks import is_mention

    literals: set[str] = set()
    maps = lookup_only(root) if any(m["what"] == "jar-class" for m in members) else frozenset()
    for member in members:
        if member["what"] == "file" and member["path"].endswith(".java"):
            literals |= set(_STRING_LITERAL.findall((Path(root) / member["path"]).read_text(encoding="utf-8-sig", errors="replace")))
        elif member["what"] == "jar-class":
            sinks = _jar_class_sinks(root, member)
            literals |= {value for value, where in (sinks or {}).items() if not is_mention(where, maps)}
    return literals


def code_mentions(root: Path, members: list[dict]) -> dict[str, dict[str, set[str]]]:
    """{jar-class member path: {literal: its sinks}} for the literals its code only mentions (slice 13)."""
    from bridgeforge.genome.literal_sinks import is_mention

    found: dict[str, dict[str, set[str]]] = {}
    maps = lookup_only(root) if any(m["what"] == "jar-class" for m in members) else frozenset()
    for member in members:
        if member["what"] == "jar-class":
            mentioned = {value: where for value, where in (_jar_class_sinks(root, member) or {}).items() if is_mention(where, maps)}
            if mentioned:
                found[member["path"]] = mentioned
    return found


def mention_suspects(root: Path, members: list[dict], vanilla_core: Path | None, own: set[str] = frozenset()) -> list[dict]:
    """One suspect per jar class whose code only mentions ids the mod or the core defines (content, faction or campaign ids):
    recorded, not followed (owner 2026-11-20, "Mention = suspect"). An id the gene's code needs elsewhere, or one of the
    gene's own ids (`own`, such as a hull mod's id used as its stat key), is no suspect (review 2026-11-20)."""
    return mention_findings(root, members, vanilla_core, own)[0]


def mention_findings(root: Path, members: list[dict], vanilla_core: Path | None,
                     own: set[str] = frozenset()) -> tuple[list[dict], list[dict]]:
    """(suspects, conditions) for the ids the gene's jar classes only mention (see `mention_suspects`). An id some
    occurrence of which is a check (`literal_sinks.CHECK_SINKS`) is also a condition `{kind: "checks-for", subject:
    "<kind>:<id>", locus, via}`: the gene may act only where that content is present (slice 15, advisor 2026-11-20)."""
    from bridgeforge.genome.campaign import _CampaignIndex
    from bridgeforge.genome.literal_sinks import CHECK_SINKS
    from bridgeforge.vendor_plan import KINDS, _Index

    core = Path(vanilla_core).expanduser().resolve() if vanilla_core else None
    indexes = [_Index(Path(root)), _Index(core)]
    campaigns = [_CampaignIndex(Path(root))] + ([_CampaignIndex(core)] if core else [])
    needed = code_literals(root, members) | set(own)
    suspects, conditions = [], []
    mentions = code_mentions(root, members)
    literals = set(needed)  # a graphics key counts only when its category is a literal too, used or mentioned
    for mentioned in mentions.values():
        literals |= set(mentioned)
    for path, mentioned in sorted(mentions.items()):
        ids: dict[str, set[str]] = {}
        for value, where in mentioned.items():
            if value in needed:
                continue
            # A graphics key is `graphics:<category>/<key>`, as campaign_ids names it (review 2026-11-20).
            subjects = sorted({f"{kind}:{value}" for kind in KINDS for index in indexes if index.defines(kind, value)}
                              | {f"graphics:{detail}/{value}" if kind == "graphics" else f"{kind}:{value}"
                                 for campaign in campaigns for kind, detail in campaign.hits(value, literals)})
            if subjects:
                ids[value] = where
                checks = sorted(s.split("/")[-1] for s in where & CHECK_SINKS)
                several = {"note": "the id names several kinds; which one the check means is not known"} if len(subjects) > 1 else {}
                conditions += [{"kind": "checks-for", "subject": subject, "locus": path, "via": checks, **several}
                               for subject in subjects if checks]
        if ids:
            sinks = sorted({s.split("/")[-1] for where in ids.values() for s in where})
            suspects.append({"path": path, "mentions": sorted(ids),
                             "reason": f"named only as a key, a check or an unloaded constant ({', '.join(sinks)}): a mention, "
                                       "not a need (owner 2026-11-20)"})
    return suspects, sorted(conditions, key=lambda c: (c["subject"], c["locus"]))


def ids_named_by_code(root: Path, members: list[dict], vanilla_core: Path | None) -> list[str]:
    """`kind:id` for each string literal of the gene's code that is exactly an id the mod or the core defines (evidence only:
    a plugin's `spawnShipOrWing("x_Var1", ...)` or `getHullMods().contains("x_spawner")`). Every kind that defines it is
    named, so an id shared by a hull and a variant brings both."""
    from bridgeforge.vendor_plan import KINDS, _Index

    literals = code_literals(root, members)
    indexes = [_Index(Path(root)), _Index(Path(vanilla_core).expanduser().resolve() if vanilla_core else None)]
    return sorted({f"{kind}:{value}" for value in literals for kind in KINDS if any(index.defines(kind, value) for index in indexes)})


def libraries_used(root: Path, members: list[dict]) -> set[str]:
    """Library names (atlas_census_libs) the gene's code references: imports and qualified names of loose scripts, the
    class references of jar classes."""
    from bridgeforge.atlas.atlas_census_libs import library_of
    from bridgeforge.scan.scan_classfile import _parse_class_file
    from bridgeforge.zipsafe import MAX_CLASS_BYTES, read_limited

    used: set[str] = set()
    for member in members:
        if member["what"] == "file" and member["path"].endswith(".java"):
            text = (Path(root) / member["path"]).read_text(encoding="utf-8-sig", errors="replace")
            for name in re.findall(r"\b((?:[a-z_][\w]*\.)+[A-Z]\w*)", text):
                library = library_of(name.replace(".", "/"))
                if library and not library.startswith("pkg:"):
                    used.add(library)
        elif member["what"] == "jar-class":
            jar, _, entry = member["path"].partition("!")
            try:
                with zipfile.ZipFile(Path(root) / jar) as archive:
                    info = _parse_class_file(read_limited(archive, entry, MAX_CLASS_BYTES))
            except (OSError, KeyError, zipfile.BadZipFile, ValueError):
                continue
            for name in (info.referenced_classes if info is not None else ()):
                library = library_of(name)
                if library and not library.startswith("pkg:"):
                    used.add(library)
    return used


def mods_needed(root: Path, members: list[dict], declared: list[str]) -> list[str]:
    """The declared dependencies a gene needs: a known library only when the gene's code references it (P2, 2026-11-19: a
    carrier declaring MagicLib for a plugin that never calls it was a finding); an unknown one is kept, as it cannot be
    shown unused."""
    from bridgeforge.atlas.atlas_census_libs import DECLARED_ID_LIBRARY

    used = libraries_used(root, members)
    return sorted(mod for mod in declared if DECLARED_ID_LIBRARY.get(mod.lower()) is None or DECLARED_ID_LIBRARY[mod.lower()] in used)


def extend(root: Path, members: list[dict], vanilla_core: Path | None, closure_needles: list[str]) -> dict:
    """What the G2 rules add to a closure: {"members": [...], "vanilla": [...], "missing": [...], "suspects": [...],
    "settings_suspect_resolved": bool}. `members` are the gene's members so far (file and jar-class ones are read)."""
    from bridgeforge.zipsafe import MAX_CLASS_BYTES, read_limited

    root = Path(root)
    keys, sources = set(), []
    for member in members:
        if member["what"] == "file" and member["path"].endswith(".java"):
            text = (root / member["path"]).read_text(encoding="utf-8-sig", errors="replace")
            sources.append(text)
            keys |= keys_read_by_source(text)
        elif member["what"] == "jar-class":
            jar, _, entry = member["path"].partition("!")
            try:
                with zipfile.ZipFile(root / jar) as archive:
                    keys |= keys_read_by_class(read_limited(archive, entry, MAX_CLASS_BYTES))
            except (OSError, KeyError, zipfile.BadZipFile, ValueError):
                continue
    mod_settings = _settings(root)
    core_settings = _settings(Path(vanilla_core)) if vanilla_core else {}
    added, vanilla, missing = [], [], []
    for key in sorted(keys):
        if key in mod_settings:
            added.append({"what": "json-entry", "path": f"{SETTINGS_FILE}#{pointer(key)}", "sha256": value_sha256(mod_settings[key]),
                          "reason": "settings key a member script reads"})
        elif key in core_settings:
            vanilla.append(f"setting:{key}")
        else:
            missing.append(f"setting:{key} (read by a member script; in neither the mod's nor the core's settings.json)")
    names, known = _core_commodities(vanilla_core)
    if vanilla_core is not None:  # without a core nothing is guessed
        for constant in sorted({c for text in sources for c in _COMMODITY.findall(text)}):
            ident = names.get(constant)
            if ident is None:
                missing.append(f"commodity:Commodities.{constant} (the core's Commodities class has no such constant)")
            elif ident in known:
                vanilla.append(f"commodity:{ident}")
            else:
                missing.append(f"commodity:{ident} (Commodities.{constant}; not in the core's commodities.csv)")
    mentioned = [key for key in mod_settings if key not in keys and any(needle in key for needle in closure_needles)]
    suspects = [{"path": f"{SETTINGS_FILE}#{pointer(key)}", "mentions": [n for n in closure_needles if n in key],
                 "reason": "settings key that mentions a closure id but no member script reads: decide whether it is part of the piece"}
                for key in sorted(mentioned)]
    return {"members": added, "vanilla": sorted(set(vanilla)), "missing": missing, "suspects": suspects}


__all__ = ["GETTERS", "SETTINGS_FILE", "code_literals", "code_mentions", "extend", "ids_named_by_code", "keys_read_by_class", "keys_read_by_source", "mention_findings", "mention_suspects", "pointer", "value_sha256"]
