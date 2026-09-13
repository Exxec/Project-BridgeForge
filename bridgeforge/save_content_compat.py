from __future__ import annotations

import csv
from pathlib import Path

from .save_compat import ModClassIndex, _mod_id, _resolve_save_path, check_save_compat
from .save_reader import iter_elements

"""Save/build **data id** compatibility check (roadmap P3b-E) and removal safety (P3b-I).

`save_compat` resolves *class* references. This module extends the same idea to the plain
**string data ids** a save stores directly -- hull, variant, wing, weapon, hullmod, faction,
commodity, industry, market-condition and special-item ids -- which `save_compat` correctly
reports `UNKNOWN` for (confirmed on the SEEKER save: its footprint there is text content, not
live class references; see `docs/REVIVAL_ASSURANCE_PLAN.md` P3b-B).

## Where these ids live in a real save (verified)

Two confirmed shapes, both from `save_TrangThisbe_*/campaign.xml` (a SEEKER save):
  - **Generic string-list entries**: `<st>ART_organicHull</st>`, `<st>threat_hullmod</st>`,
    `<st>dweller_hullmod</st>` -- XStream's tag for a `String` inside a `List`/array, used for
    hull ids, hullmod ids, and (per Starsector's own source layout) any other plain string id
    list a plugin stores.
  - **Fleet member attributes**: `<FMmbr ... sid="vanguard_Outdated" sN="CGR Bene Elohim" ...>`
    -- `sid` is the ship's *variant* id (confirmed against real `FMmbr` elements holding vanilla
    variant ids like `mudskipper_Standard`, `shepherd_Frontier`).

## Where a mod's own id universe comes from (verified against SEEKER, Exigency, and vanilla-core)

Each category is read from a fixed, confirmed file layout under `<mod_dir>/data/`:
  - hull ids: filename stems of `hulls/*.ship` (cross-checked against `.ship`'s own `"hullId"`
    field, e.g. `ART_armor.ship` declares `"hullId": "ART_armor"` -- filename stem is used
    directly rather than parsing every `.ship` file, since they agree).
  - variant and wing ids: filename stems of `variants/*.variant` (wings are stored as variant
    files too; this module does not try to tell a wing variant from a ship variant, since both
    share one id namespace in `FMmbr`-style references).
  - weapon ids: filename stems of `weapons/*.wpn`.
  - hullmod ids: the `id` column of `hullmods/hull_mods.csv`.
  - faction ids: the `id` field of each `world/factions/*.faction` file (lenient JSON, e.g.
    `id:"hegemony"` with an unquoted key -- confirmed readable by `scanner._load_lenient_json_file`).
  - commodity/industry/market-condition/special-item ids: the `id` column of
    `campaign/commodities.csv`, `campaign/industries.csv`, `campaign/market_conditions.csv`,
    `campaign/special_items.csv` respectively (all confirmed present with an `id` column in the
    real vanilla core install).
A directory or file that doesn't exist for a given mod (e.g. a mod with no factions) contributes
an empty set for that category rather than an error.

## Attribution discipline

Same principle as `save_compat`: a save token is only ever claimed as "this mod's" when it
exactly matches one of the mod's own collected ids. For a token that matches *neither* the mod's
nor (when `vanilla_core` is given) vanilla's id universe, this module falls back to a **prefix
heuristic** -- every distinct `foo_` prefix (up to and including the first `_`) seen among the
mod's own ids -- to catch an id the build has since **removed entirely** (so it has no surviving
id to match), the data-id analogue of `save_compat`'s surviving-package rule for removed classes.
A token matching no prefix either is not reported at all (most `<st>` strings are not data ids;
enumerating every unattributable string would be too noisy to be useful), which is a narrower
stance than `save_compat`'s `limitations` bucket and is intentional here.
"""

_CATEGORY_DIRS = {
    "hull": ("data", "hulls", ".ship"),
    "variant": ("data", "variants", ".variant"),
    "weapon": ("data", "weapons", ".wpn"),
}
_CATEGORY_CSVS = {
    "hullmod": ("data", "hullmods", "hull_mods.csv"),
    "commodity": ("data", "campaign", "commodities.csv"),
    "industry": ("data", "campaign", "industries.csv"),
    "market_condition": ("data", "campaign", "market_conditions.csv"),
    "special_item": ("data", "campaign", "special_items.csv"),
}


def _stems(directory: Path, suffix: str) -> set[str]:
    if not directory.is_dir():
        return set()
    return {path.stem for path in directory.rglob(f"*{suffix}") if path.is_file()}


def _csv_ids(path: Path, id_column: str = "id") -> set[str]:
    if not path.is_file():
        return set()
    try:
        with path.open("r", encoding="utf-8-sig", newline="", errors="replace") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or id_column not in reader.fieldnames:
                return set()
            return {row[id_column].strip() for row in reader if row.get(id_column) and row[id_column].strip()}
    except (OSError, csv.Error):
        return set()


def _faction_ids(directory: Path) -> set[str]:
    if not directory.is_dir():
        return set()
    from .scanner import _load_lenient_json_file

    ids: set[str] = set()
    for path in directory.glob("*.faction"):
        try:
            data = _load_lenient_json_file(path)
        except (ValueError, OSError):
            continue
        if isinstance(data, dict) and isinstance(data.get("id"), str):
            ids.add(data["id"])
    return ids


def collect_mod_id_universe(mod_dir: Path) -> dict[str, set[str]]:
    """A mod's declared ids, grouped by category. See module docstring for the file layout."""
    mod_dir = Path(mod_dir).expanduser().resolve()
    universe: dict[str, set[str]] = {}
    for category, (sub1, sub2, suffix) in _CATEGORY_DIRS.items():
        universe[category] = _stems(mod_dir / sub1 / sub2, suffix)
    # Wing ids are the `id` column of wing_data.csv (e.g. exigency_azata_wing), not variant file
    # stems; using variants flagged every knownFighters entry as missing (PRB-2, 2026-09-13).
    universe["wing"] = _csv_ids(mod_dir / "data" / "hulls" / "wing_data.csv")
    for category, (sub1, sub2, filename) in _CATEGORY_CSVS.items():
        universe[category] = _csv_ids(mod_dir / sub1 / sub2 / filename)
    universe["faction"] = _faction_ids(mod_dir / "data" / "world" / "factions")
    return universe


def _all_ids(universe: dict[str, set[str]]) -> set[str]:
    result: set[str] = set()
    for ids in universe.values():
        result |= ids
    return result


def _categorize(token: str, universe: dict[str, set[str]]) -> str:
    for category, ids in universe.items():
        if token in ids:
            return category
    return "unknown"


def _prefixes(ids: set[str]) -> set[str]:
    prefixes = set()
    for id_ in ids:
        if "_" in id_:
            prefixes.add(id_.split("_", 1)[0] + "_")
    return prefixes


# Path segments under which a save stores real data ids (known lists, hullmods, wings). A prefix-only
# token counts as MISSING (a load failure) only here; elsewhere it is often an id the mod's own code
# creates at runtime (markets, memory keys), reported as unattributed instead of failing the check.
_DATA_ID_PATH_SEGMENTS = {
    "knownShips", "knownFighters", "knownWeapons", "knownHullMods", "knownIndustries",
    "priorityShips", "priorityFighters", "priorityWeapons", "hullMods", "sMods", "permaMods",
    "wings", "variant", "hullSpec",
}
# Faction relations are stored as "<factionA>_<factionB>" keys (e.g. exigency_hegemony), which look
# like mod-prefixed ids but are not data ids at all (PRB-2: 50+ false "missing" entries).
_SKIP_PATH_SEGMENTS = {"relations"}


def _candidate_tokens(campaign_xml: Path):
    """Yield (token, sample_path, in_data_id_list) for the confirmed data-id shapes (see module docstring)."""
    for element in iter_elements(campaign_xml):
        if element.tag == "st" and element.text:
            if _SKIP_PATH_SEGMENTS.intersection(element.path):
                continue
            yield element.text, "/" + "/".join(element.path), bool(_DATA_ID_PATH_SEGMENTS.intersection(element.path))
        elif element.tag == "FMmbr":
            sid = element.attrs.get("sid")
            if sid:
                yield sid, "/" + "/".join(element.path), True


def check_save_content(save: Path, mod_dir: Path, *, vanilla_core: Path | None = None) -> dict:
    """Check whether a save's referenced data ids for `mod_dir`'s mod are present in its data.

    Returns `status` (LOADS / WILL_FAIL / UNKNOWN), `present` (ids matched to the mod, by
    category), and `missing` (ids attributable to the mod by prefix but absent from its current
    data -- the id-level analogue of `save_compat`'s `missing`). Complements `save_compat`.
    """
    campaign_xml = _resolve_save_path(Path(save))
    mod_dir = Path(mod_dir).expanduser().resolve()
    universe = collect_mod_id_universe(mod_dir)
    mod_all = _all_ids(universe)
    vanilla_all: set[str] = set()
    if vanilla_core is not None:
        vanilla_all = _all_ids(collect_mod_id_universe(Path(vanilla_core).expanduser().resolve()))
    mod_prefixes = _prefixes(mod_all)

    present: dict[str, dict[str, object]] = {}
    missing: dict[str, dict[str, object]] = {}
    unattributed: dict[str, dict[str, object]] = {}

    for token, sample_path, in_data_id_list in _candidate_tokens(campaign_xml):
        if token in mod_all:
            entry = present.setdefault(
                token, {"category": _categorize(token, universe), "occurrences": 0, "sample_path": sample_path}
            )
            entry["occurrences"] += 1
            continue
        if token in vanilla_all:
            continue
        if any(token.startswith(prefix) for prefix in mod_prefixes):
            bucket = missing if in_data_id_list else unattributed
            entry = bucket.setdefault(token, {"occurrences": 0, "sample_path": sample_path})
            entry["occurrences"] += 1

    if missing:
        status = "WILL_FAIL"
    elif present:
        status = "LOADS"
    else:
        status = "UNKNOWN"

    return {
        "schema_version": 1,
        "mode": "READ_ONLY_SAVE_CONTENT_COMPAT",
        "save": str(campaign_xml),
        "mod_dir": str(mod_dir),
        "mod_id": _mod_id(mod_dir),
        "status": status,
        "present": {
            "count": len(present),
            "ids": [
                {"id": token, "category": entry["category"], "occurrences": entry["occurrences"], "sample_path": entry["sample_path"]}
                for token, entry in sorted(present.items())
            ],
        },
        "missing": [
            {"id": token, "occurrences": entry["occurrences"], "sample_path": entry["sample_path"]}
            for token, entry in sorted(missing.items())
        ],
        # Mod-prefixed strings outside data-id lists (runtime-created market ids, memory keys...):
        # reported for review, never a load failure on their own.
        "unattributed_prefix_matches": [
            {"id": token, "occurrences": entry["occurrences"], "sample_path": entry["sample_path"]}
            for token, entry in sorted(unattributed.items())
        ],
    }


def removal_safety(save: Path, mod_dir: Path, *, vanilla_core: Path | None = None) -> dict:
    """Everything a save still depends on for one mod: classes, content ids, and memory keys.

    **Internal-only tooling.** Whether a "can I remove this mod mid-campaign?" answer should ever
    be exposed to players is an open question noted in
    `docs/P3B_SAVE_TOOLING_RECOMMENDATIONS.md` (#3) -- this function is for BridgeForge's own use
    (understanding what a mod really leaves in a campaign) until the owner decides otherwise.

    Verdict is `SAFE_TO_REMOVE` only when `save_compat` finds no referenced classes and no
    class-level breakage, `check_save_content` finds no present/missing content ids, and no
    memory key in the save carries `$<mod_id>` as a prefix (Starsector's own convention for a
    plugin's memory keys); otherwise `UNSAFE`, with `reasons` listing exactly what still depends
    on the mod.
    """
    campaign_xml = _resolve_save_path(Path(save))
    mod_dir = Path(mod_dir).expanduser().resolve()

    compat = check_save_compat(campaign_xml, mod_dir, vanilla_core=vanilla_core)
    content = check_save_content(campaign_xml, mod_dir, vanilla_core=vanilla_core)

    mod_id = compat.get("mod_id")
    memory_hits: list[dict[str, object]] = []
    if mod_id:
        needle = f"${mod_id}"
        for element in iter_elements(campaign_xml):
            if element.text and needle in element.text:
                memory_hits.append({"field": element.tag, "value": element.text, "path": "/" + "/".join(element.path)})

    reasons: list[str] = []
    if compat["referenced"]["count"] > 0:
        reasons.append(f"{compat['referenced']['count']} referenced class(es) still present in the save")
    if compat["missing"]:
        reasons.append(f"{len(compat['missing'])} class reference(s) the save needs are already missing from this build")
    if content["present"]["count"] > 0:
        reasons.append(f"{content['present']['count']} content id(s) still referenced (hulls/variants/weapons/hullmods/factions/...)")
    if content["missing"]:
        reasons.append(f"{len(content['missing'])} content id(s) the save needs are already missing from this build")
    if memory_hits:
        reasons.append(f"{len(memory_hits)} memory key(s) carrying the mod's id prefix")

    return {
        "schema_version": 1,
        "mode": "READ_ONLY_SAVE_REMOVAL_SAFETY",
        "internal_only": True,
        "save": str(campaign_xml),
        "mod_dir": str(mod_dir),
        "mod_id": mod_id,
        "class_compat": compat,
        "content_compat": content,
        "memory_keys": memory_hits,
        "reasons": reasons,
        "status": "UNSAFE" if reasons else "SAFE_TO_REMOVE",
    }
