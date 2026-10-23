"""Ids a mod's code asks for that no installed table defines, but one close to them does (ROADMAP 60d, item 73 F3).

Found when Tritachyon asked for BOGGLED_AI_STATION and Terraforming & Station Construction 10.0.9 calls it
BOGGLED_REMNANT_STATION: New Game stopped in onNewGame. Four kinds are read from string constants in classes and loose
scripts that call an API method taking that kind of id: industries, hull mods, commodities and market conditions. The
suggestion always comes from a declared provider's own table, never from vanilla alone.
"""
from __future__ import annotations

import csv
import difflib
import re
import zipfile
from pathlib import Path

from bridgeforge.bytecode.jar_audit import ClassFileError, parse_constant_pool

# kind -> (API method names whose string argument is an id of that kind, table relative to the mod root)
KIND_APIS: dict[str, tuple[frozenset[str], str]] = {
    "industry": (frozenset({"addIndustry", "hasIndustry", "getIndustry", "removeIndustry", "isIndustry", "getIndustrySpec"}), "data/campaign/industries.csv"),
    "hullmod": (frozenset({"addMod", "addPermaMod", "hasHullMod", "removeMod", "removePermaMod", "getHullModSpec", "addSuppressedMod"}), "data/hullmods/hull_mods.csv"),
    "commodity": (frozenset({"addCommodity", "removeCommodity", "getCommodityQuantity", "getCommodityOnMarket", "getCommodityData", "getCommoditySpec"}), "data/campaign/commodities.csv"),
    "condition": (frozenset({"addCondition", "hasCondition", "removeCondition", "getCondition", "getSpecificCondition"}), "data/campaign/market_conditions.csv"),
}
INDUSTRY_API_NAMES = KIND_APIS["industry"][0]
# Tables whose ids are never a candidate of another kind (a weapon id beside an addMod call is not a renamed hull mod).
_OTHER_TABLES = ("data/weapons/weapon_data.csv", "data/hulls/wing_data.csv", "data/hulls/ship_data.csv", "data/campaign/special_items.csv",
                 "data/characters/skills/skill_data.csv")
_ID_SHAPE = re.compile(r"^[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+$")
_LITERAL = re.compile(r'"([A-Za-z][A-Za-z0-9_]{5,})"')
MIN_RATIO = 0.75


def ids_in_csv(path: Path) -> set[str]:
    try:
        with path.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except OSError:
        return set()
    return {(row.get("id") or "").strip() for row in rows if (row.get("id") or "").strip() and not (row.get("id") or "").startswith("#")}


industry_ids_in_csv = ids_in_csv


def _ids_from(table: str, vanilla_core: Path | None, own_root: Path, provider_dirs: list[Path]) -> set[str]:
    ids: set[str] = set()
    for folder in ([vanilla_core] if vanilla_core else []) + [own_root] + list(provider_dirs):
        ids |= ids_in_csv(Path(folder) / table)
    return ids


def known_industry_ids(vanilla_core: Path | None, own_root: Path, provider_dirs: list[Path]) -> set[str]:
    return _ids_from(KIND_APIS["industry"][1], vanilla_core, own_root, provider_dirs)


def _candidate(literal: str) -> bool:
    return len(literal) > 5 and _ID_SHAPE.match(literal) is not None


def used_ids_by_kind(root: Path) -> dict[str, dict[str, list[str]]]:
    """{kind: {candidate id: where}} from classes in jars and loose .java files that call an API method of that kind."""
    used: dict[str, dict[str, list[str]]] = {kind: {} for kind in KIND_APIS}
    for source in root.rglob("*.java"):
        try:
            text = source.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        kinds = [kind for kind, (names, _) in KIND_APIS.items() if any(name in text for name in names)]
        if not kinds:
            continue
        where = str(source.relative_to(root)).replace("\\", "/")
        for kind in kinds:
            if kind == "industry":  # the original class-level rule, kept as it was swept clean over 312 workspaces
                literals = set(_LITERAL.findall(text))
            else:  # a file that calls addMod also holds tag and weapon ids (Magellan-Shenanigans): only a call's own argument counts
                call = re.compile(r"\b(?:" + "|".join(sorted(KIND_APIS[kind][0])) + r')\s*\(\s*"([A-Za-z][A-Za-z0-9_]{5,})"')
                literals = set(call.findall(text))
            for literal in literals:
                if _candidate(literal):
                    used[kind].setdefault(literal, []).append(where)
    for jar in root.rglob("*.jar"):
        try:
            with zipfile.ZipFile(jar) as archive:
                for item in archive.infolist():
                    if not item.filename.endswith(".class"):
                        continue
                    try:
                        pool = parse_constant_pool(archive.read(item))
                    except (ClassFileError, OSError, zipfile.BadZipFile):
                        continue
                    utf8 = {i: e[1] for i, e in enumerate(pool) if e is not None and e[0] == 1}
                    values = set(utf8.values())
                    kinds = [kind for kind, (names, _) in KIND_APIS.items() if names & values]
                    if not kinds:
                        continue
                    for entry in pool:
                        if entry is not None and entry[0] == 8 and entry[1] in utf8 and _candidate(utf8[entry[1]]):
                            for kind in kinds:
                                used[kind].setdefault(utf8[entry[1]], []).append(f"{jar.name}!{item.filename}")
        except (OSError, zipfile.BadZipFile):
            continue
    return used


def used_industry_ids(root: Path) -> dict[str, list[str]]:
    return used_ids_by_kind(root)["industry"]


def closest_known(candidate: str, known: set[str]) -> tuple[str, float] | None:
    """The known id most like the candidate that shares its first token (BOGGLED_...), if close enough."""
    head = candidate.split("_", 1)[0].lower()
    best: tuple[str, float] | None = None
    for other in known:
        if other.split("_", 1)[0].lower() != head:
            continue
        ratio = difflib.SequenceMatcher(None, candidate, other).ratio()
        if ratio >= MIN_RATIO and (best is None or ratio > best[1]):
            best = (other, ratio)
    return best


def renamed_ids(root: Path, vanilla_core: Path | None, provider_dirs: list[Path]) -> list[dict]:
    """[{kind, used, suggestion, ratio, where}] for each used id absent from every table that has a close sibling.

    Suggestions come only from a declared provider's own table: a vanilla-only match was pure noise in a sweep of 312
    workspaces (station_side05 -> station_base, an entity id beside an industry call). An id that any other kind's table
    defines (a market condition beside an industry call: population_5 beside population; a weapon beside an addMod) is
    not a candidate, nor is one ending in _<digits>."""
    root = Path(root)
    tables = {kind: spec[1] for kind, spec in KIND_APIS.items()}
    known = {kind: _ids_from(table, vanilla_core, root, provider_dirs) for kind, table in tables.items()}
    provider_only = {kind: _ids_from(table, None, root / "_none_", provider_dirs) - known_ids_without_providers(table, vanilla_core, root)
                     for kind, table in tables.items()}
    if not any(provider_only.values()):
        return []
    foreign = set().union(*known.values())
    for table in _OTHER_TABLES:
        foreign |= _ids_from(table, vanilla_core, root, provider_dirs)
    used = used_ids_by_kind(root)
    out = []
    for kind in KIND_APIS:
        if not provider_only[kind]:
            continue
        for candidate, where in sorted(used[kind].items()):
            if candidate in foreign or re.search(r"_\d+$", candidate):
                continue
            near = closest_known(candidate, provider_only[kind])
            if near:
                out.append({"kind": kind, "used": candidate, "suggestion": near[0], "ratio": round(near[1], 2), "where": sorted(set(where))[:3]})
    return out


def known_ids_without_providers(table: str, vanilla_core: Path | None, root: Path) -> set[str]:
    return _ids_from(table, vanilla_core, root, [])


def renamed_industry_ids(root: Path, vanilla_core: Path | None, provider_dirs: list[Path]) -> list[dict]:
    return [hit for hit in renamed_ids(root, vanilla_core, provider_dirs) if hit["kind"] == "industry"]
