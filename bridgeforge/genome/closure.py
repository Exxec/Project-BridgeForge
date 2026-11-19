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
    """Settings keys a compiled class passes, as its string argument, to a SettingsAPI getter."""
    from bridgeforge.atlas.atlas_classfile import ClassFormatError, parse_class

    try:
        info = parse_class(data, frozenset(GETTERS))
    except ClassFormatError:
        return set()
    return {arg[1] for call in info.calls if call.owner.endswith("SettingsAPI") for arg in call.args[:1] if arg[0] == "str"}


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


__all__ = ["GETTERS", "SETTINGS_FILE", "extend", "keys_read_by_class", "keys_read_by_source", "pointer", "value_sha256"]
