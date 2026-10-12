"""Which star systems a mod creates, and which star/planet types it defines (P15 item 25).

Zorg18 (2026-09-27): its `star_zorg` and `zorg_planet` carried vanilla-sized weights in the procgen tables, so
the artificial star meant for Zorg Zeta also appeared in random systems (the owner saw one in Johannam). This
module supplies the facts for the probe's `campaign-layout` check and the scanner's static check:

- `mod_created_systems`: names passed to `SectorAPI.createStarSystem(String)`, as a string literal in loose or
  jar sources, or in a jar as an `ldc`/`ldc_w` of a String constant immediately before the call (ZorgGen:
  `ldc "Zorg Zeta"; invokeinterface SectorAPI.createStarSystem`, javap 2026-09-27).
- `mod_body_types`: the mod's own `data/config/planets.json` types, each with whether it is a star and its
  weight in the mod's `star_gen_data.csv` / `planet_gen_data.csv` (0 when it has no row).
- `mod_placed_types`: type ids that appear as string constants in the mod's code (placed by id).
"""
from __future__ import annotations

import csv
import io
import re
import struct
import zipfile
from pathlib import Path

from .scanner import _load_lenient_json_file, _loaded_mod_jars

_CREATE_SYSTEM_SOURCE = re.compile(r'createStarSystem\(\s*"([^"]+)"\s*\)')
_OP_LDC, _OP_LDC_W = 0x12, 0x13
_OP_INVOKES = {0xB6, 0xB7, 0xB8, 0xB9}  # invokevirtual/special/static/interface


def _constant_pool(data: bytes) -> tuple[dict[int, tuple], int] | None:
    """{index: entry} for the entries this module needs, plus the offset after the pool. None if not a class."""
    if data[:4] != b"\xca\xfe\xba\xbe":
        return None
    count = struct.unpack(">H", data[8:10])[0]
    pos, index, pool = 10, 1, {}
    try:
        while index < count:
            tag = data[pos]
            if tag == 1:
                length = struct.unpack(">H", data[pos + 1:pos + 3])[0]
                pool[index] = ("utf8", data[pos + 3:pos + 3 + length].decode("utf-8", errors="replace"))
                pos += 3 + length
            elif tag in (7, 8, 16, 19, 20):
                pool[index] = (tag, struct.unpack(">H", data[pos + 1:pos + 3])[0])
                pos += 3
            elif tag in (9, 10, 11, 12):
                a, b = struct.unpack(">HH", data[pos + 1:pos + 5])
                pool[index] = (tag, a, b)
                pos += 5
            elif tag in (3, 4, 17, 18):
                pos += 5
            elif tag in (5, 6):
                pos += 9
                index += 1
            elif tag == 15:
                pos += 4
            else:
                return None
            index += 1
    except (IndexError, struct.error):
        return None
    return pool, pos


def _utf8(pool: dict, index: int) -> str:
    entry = pool.get(index)
    return entry[1] if entry and entry[0] == "utf8" else ""


def _jar_system_names(data: bytes) -> list[str]:
    """String constants loaded right before a createStarSystem call, anywhere in the class's bytecode."""
    parsed = _constant_pool(data)
    if parsed is None:
        return []
    pool, _ = parsed
    create_refs = set()
    for index, entry in pool.items():
        if isinstance(entry[0], int) and entry[0] in (10, 11):
            name_and_type = pool.get(entry[2])
            if name_and_type and _utf8(pool, name_and_type[1]) == "createStarSystem":
                create_refs.add(index)
    if not create_refs:
        return []
    strings = {index: _utf8(pool, entry[1]) for index, entry in pool.items() if entry[0] == 8}
    found = []
    for i in range(len(data) - 5):
        op = data[i]
        if op == _OP_LDC and data[i + 1] in strings and data[i + 2] in _OP_INVOKES:
            ref = struct.unpack(">H", data[i + 3:i + 5])[0]
            if ref in create_refs:
                found.append(strings[data[i + 1]])
        elif op == _OP_LDC_W and i + 6 <= len(data):
            const = struct.unpack(">H", data[i + 1:i + 3])[0]
            if const in strings and data[i + 3] in _OP_INVOKES and struct.unpack(">H", data[i + 4:i + 6])[0] in create_refs:
                found.append(strings[const])
    return found


def mod_created_systems(root: Path) -> list[str]:
    root = Path(root)
    names: set[str] = set()
    for source in root.rglob("*.java"):
        if "disabled_files" in source.relative_to(root).parts:
            continue
        try:
            names.update(_CREATE_SYSTEM_SOURCE.findall(source.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            continue
    string_values = _strings_json_values(root)
    for jar in _loaded_mod_jars(root):
        try:
            with zipfile.ZipFile(jar) as archive:
                for member in archive.namelist():
                    if member.endswith(".class"):
                        data = archive.read(member)
                        names.update(_jar_system_names(data))
                        # Names read at runtime from data/strings/strings.json (Outer Rim Alliance's ORA_godunov:
                        # getString("ORA", "gdnv_system") -> "Godunov"; the probe saw no ORA systems, 2026-10-05).
                        # Through any wrapper (ORA_txt.txt(key)): a *_system key constant is specific enough.
                        if string_values and b"createStarSystem" in data:
                            parsed = _constant_pool(data)
                            if parsed is not None:
                                pool, _ = parsed
                                for entry in pool.values():
                                    if entry[0] == 8:
                                        key = _utf8(pool, entry[1])
                                        if key in string_values:
                                            names.add(string_values[key])
        except (OSError, zipfile.BadZipFile):
            continue
    return sorted(names)


def _strings_json_values(root: Path) -> dict[str, str]:
    """{key: value} for the string entries of the mod's data/strings/strings.json (every category)."""
    from .scanner import _load_lenient_json_file

    path = Path(root) / "data" / "strings" / "strings.json"
    spec = _load_lenient_json_file(path) if path.is_file() else None
    values: dict[str, str] = {}
    for category in (spec or {}).values() if isinstance(spec, dict) else []:
        if isinstance(category, dict):
            values.update({k: v for k, v in category.items() if isinstance(v, str) and k.endswith("_system")})
    return values


def _procgen_weights(root: Path) -> dict[str, float]:
    weights: dict[str, float] = {}
    for name, columns in (("star_gen_data.csv", ("freqYOUNG", "freqAVERAGE", "freqOLD")), ("planet_gen_data.csv", ("frequency",))):
        path = root / "data" / "campaign" / "procgen" / name
        if not path.is_file():
            continue
        for row in csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig", errors="replace"))):
            type_id = (row.get("id") or "").strip()
            if not type_id or type_id.startswith("#"):
                continue
            total = 0.0
            for column in columns:
                try:
                    total += float((row.get(column) or "0").strip() or 0)
                except ValueError:
                    continue
            weights[type_id] = total
    return weights


def mod_body_types(root: Path) -> dict[str, dict]:
    planets = _load_lenient_json_file(Path(root) / "data" / "config" / "planets.json")
    if not isinstance(planets, dict):
        return {}
    weights = _procgen_weights(Path(root))
    return {type_id: {"star": bool(spec.get("isStar")), "procgen_weight": weights.get(type_id, 0.0)}
            for type_id, spec in planets.items() if isinstance(spec, dict)}


def mod_placed_types(root: Path, types: set[str]) -> set[str]:
    """Types whose id appears as a string in the mod's code: placed by the mod itself, by id."""
    root = Path(root)
    placed: set[str] = set()
    for source in root.rglob("*.java"):
        if "disabled_files" in source.relative_to(root).parts:
            continue
        try:
            text = source.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        placed.update(t for t in types if f'"{t}"' in text)
    for jar in _loaded_mod_jars(root):
        try:
            with zipfile.ZipFile(jar) as archive:
                for member in archive.namelist():
                    if member.endswith(".class"):
                        data = archive.read(member)
                        parsed = _constant_pool(data)
                        if parsed:
                            values = {entry[1] for entry in parsed[0].values() if entry[0] == "utf8"}
                            placed.update(types & values)
        except (OSError, zipfile.BadZipFile):
            continue
    return placed
