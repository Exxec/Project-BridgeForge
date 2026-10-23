"""Mod Atlas phase 1: facts from a mod's data files (CSV, factions, settings.json, rules.csv, missions).

A fact is one row: (kind, id, action, file, line, evidence, confidence). Data files are SAFE facts: the game
reads them as they stand. `overrides` (same id as vanilla) is decided later, once vanilla is indexed.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import NamedTuple

from bridgeforge.scan.scanner import _load_lenient_json_file


class Fact(NamedTuple):
    kind: str
    id: str
    action: str
    file: str
    line: int
    evidence: str
    confidence: str


# Data kinds whose ids can collide between mods (everything the DUP-DEFINE rule and `overrides` look at).
CSV_KINDS = {
    "data/hulls/ship_data.csv": "hull",
    "data/weapons/weapon_data.csv": "weapon",
    "data/hulls/wing_data.csv": "wing",
    "data/hullmods/hull_mods.csv": "hullmod",
    "data/hulls/hull_mods.csv": "hullmod",
    "data/shipsystems/ship_systems.csv": "system",
    "data/campaign/commodities.csv": "commodity",
    "data/campaign/industries.csv": "industry",
    "data/campaign/market_conditions.csv": "condition",
    "data/campaign/special_items.csv": "special_item",
    "data/campaign/submarkets.csv": "submarket",
    "data/campaign/abilities.csv": "ability",
    "data/characters/skills/skill_data.csv": "skill",
}
DATA_KINDS = frozenset(CSV_KINDS.values()) | {"faction", "mission", "variant", "rule"}
SETTINGS_PATH = "data/config/settings.json"
RULES_PATH = "data/campaign/rules.csv"
VALUE_SUMMARY_LIMIT = 120


def _sig(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8", "replace")).hexdigest()[:10]


def _read_csv(path: Path) -> list[tuple[int, list[str], dict[str, str]]]:
    """(line, raw row, row by lower-cased header) for each non-blank row; [] when unreadable."""
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, None)
            if not header:
                return []
            names = [name.strip().lower() for name in header]
            rows = []
            while True:
                start = reader.line_num + 1
                try:
                    row = next(reader)
                except StopIteration:
                    break
                except csv.Error:
                    continue
                if any(cell.strip() for cell in row):
                    rows.append((start, row, {names[i]: cell.strip() for i, cell in enumerate(row) if i < len(names)}))
            return rows
    except (OSError, UnicodeDecodeError, csv.Error):
        return []


def _csv_facts(root: Path, rel: str, kind: str) -> list[Fact]:
    path = root / rel
    if not path.is_file():
        return []
    rows = _read_csv(path)
    own_ids = {fields.get("id", "") for _, _, fields in rows}
    facts, seen = [], set()
    for line, row, fields in rows:
        ident = fields.get("id", "")
        if not ident or ident.startswith("#") or ident in seen:
            continue
        seen.add(ident)
        facts.append(Fact(kind, ident, "defines", rel, line, f"row sig={_sig(*row)}", "SAFE"))
        if kind == "industry":
            for column in ("upgrade", "downgrade"):
                target = fields.get(column, "")
                if target and target != ident and target not in own_ids:
                    facts.append(Fact(kind, target, "replaces", rel, line,
                                      f"{ident} lists {column}={target}: the chain points past it", "REVIEW"))
    return facts


def _rules_facts(root: Path) -> list[Fact]:
    path = root / RULES_PATH
    facts = []
    for line, row, fields in _read_csv(path) if path.is_file() else []:
        trigger, conditions = fields.get("trigger", ""), fields.get("conditions", "")
        if not trigger:
            continue
        payload = _sig(fields.get("script", ""), fields.get("text", ""), fields.get("options", ""))
        ident = fields.get("id", "") or f"{trigger}#{line}"
        facts.append(Fact("rule", ident, "defines", RULES_PATH, line,
                          f"trigger={trigger} | conditions={conditions} | sig={payload}", "SAFE"))
    return facts


def _summary(value: object) -> str:
    if isinstance(value, dict):
        return f"dict:{len(value)} keys"
    if isinstance(value, list):
        return f"list:{len(value)} items"
    return json.dumps(value, ensure_ascii=False)[:VALUE_SUMMARY_LIMIT]


def _settings_facts(root: Path) -> list[Fact]:
    path = root / SETTINGS_PATH
    data = _load_lenient_json_file(path) if path.is_file() else None
    if not isinstance(data, dict):
        return []
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    facts = []
    for key, value in data.items():
        match = re.search(r'"' + re.escape(str(key)) + r'"\s*:', text)
        line = text.count("\n", 0, match.start()) + 1 if match else 0
        facts.append(Fact("setting", str(key), "sets", SETTINGS_PATH, line, _summary(value), "SAFE"))
        if isinstance(value, list):  # RC8 lists add to vanilla's (CLAUDE.md), so each element is an append, never an override
            facts += [Fact("setting-list", str(key), "appends", SETTINGS_PATH, line, json.dumps(item, ensure_ascii=False)[:VALUE_SUMMARY_LIMIT], "SAFE")
                      for item in value]
    graphics = data.get("graphics")
    terrain = graphics.get("terrain") if isinstance(graphics, dict) else None
    if isinstance(terrain, dict):  # settings.json graphics.terrain: the terrain sprite ids a terrain plugin draws with
        facts += [Fact("terrain", str(key), "defines", SETTINGS_PATH, 0, f"graphics.terrain sprite {_summary(value)}", "SAFE") for key, value in terrain.items()]
    return facts


def _file_id_facts(root: Path, folder: str, pattern: str, kind: str, id_key: str) -> list[Fact]:
    """One fact per `.ship`/`.wpn` file: the id inside the file (hullId / id), else the file stem."""
    directory = root / folder
    facts = []
    for path in sorted(directory.glob(pattern)) if directory.is_dir() else []:
        data = _load_lenient_json_file(path)
        ident = data.get(id_key) if isinstance(data, dict) else None
        facts.append(Fact(kind, ident if isinstance(ident, str) and ident else path.stem, "defines",
                          path.relative_to(root).as_posix(), 1, f"{pattern} file", "SAFE"))
    return facts


def _planet_facts(root: Path) -> list[Fact]:
    path = root / "data" / "config" / "planets.json"
    data = _load_lenient_json_file(path) if path.is_file() else None
    return [Fact("planet-type", str(key), "defines", "data/config/planets.json", 1, "planets.json key", "SAFE")
            for key, value in (data.items() if isinstance(data, dict) else []) if isinstance(value, dict)]


def _faction_facts(root: Path) -> list[Fact]:
    folder = root / "data" / "world" / "factions"
    facts = []
    for path in sorted(folder.glob("*.faction")) if folder.is_dir() else []:
        rel = path.relative_to(root).as_posix()
        data = _load_lenient_json_file(path)
        ident = data.get("id") if isinstance(data, dict) else None
        if isinstance(ident, str) and ident:
            facts.append(Fact("faction", ident, "defines", rel, 1, "faction file", "SAFE"))
        else:
            facts.append(Fact("faction", path.stem, "patches", rel, 1, "no id: merges into the faction named by the file", "SAFE"))
    return facts


def _folder_facts(root: Path) -> list[Fact]:
    facts = []
    missions = root / "data" / "missions"
    for path in sorted(missions.iterdir()) if missions.is_dir() else []:
        if path.is_dir():
            facts.append(Fact("mission", path.name, "defines", path.relative_to(root).as_posix(), 0, "mission folder", "SAFE"))
    variants = root / "data" / "variants"
    for path in sorted(variants.rglob("*.variant")) if variants.is_dir() else []:
        facts.append(Fact("variant", path.stem, "defines", path.relative_to(root).as_posix(), 0, "variant id = file stem", "SAFE"))
    skins = root / "data" / "hulls" / "skins"
    for path in sorted(skins.glob("*.skin")) if skins.is_dir() else []:
        data = _load_lenient_json_file(path)
        ident = data.get("skinHullId") if isinstance(data, dict) else None
        facts.append(Fact("hull", ident if isinstance(ident, str) and ident else path.stem, "defines",
                          path.relative_to(root).as_posix(), 1, "skin file", "SAFE"))
    return facts


def extract_data_facts(root: Path) -> list[Fact]:
    facts: list[Fact] = []
    for rel, kind in CSV_KINDS.items():
        facts.extend(_csv_facts(root, rel, kind))
    facts.extend(_rules_facts(root))
    facts.extend(_settings_facts(root))
    facts.extend(_faction_facts(root))
    facts.extend(_folder_facts(root))
    facts.extend(_file_id_facts(root, "data/hulls", "*.ship", "hull-file", "hullId"))
    facts.extend(_file_id_facts(root, "data/weapons", "*.wpn", "weapon-file", "id"))
    facts.extend(_planet_facts(root))
    return facts
