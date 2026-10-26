"""`bridgeforge atlas exemplars FEATURE | --symbols a,b,c` (ROADMAP-3 81.5): working examples of a game feature, from the census.

A feature is a set of API symbols (a simple class name, a member name, or `Class.member`). A census row matches when its
dotted symbol equals the wanted text or ends with `.` plus it. Mods are ranked by how many of the feature's symbols they
reference, then by the number of classes/files that do; each matched symbol lists the first class or file of that mod that
references it. STATIC: this shows what code references, not that the feature works at runtime.
"""
from __future__ import annotations

import sqlite3

from .atlas import ORIGINAL_SUFFIX, latest_mods

FEATURES: dict[str, tuple[str, ...]] = {
    "raid-fgi": ("GenericRaidFGI", "FGRaidAction", "FleetGroupIntel"),
    "intel": ("BaseIntelPlugin", "IntelInfoPlugin"),
    "custom-entities": ("addCustomEntity", "CustomCampaignEntityPlugin"),
    "rings-orbits": ("addRingBand", "setCircularOrbit"),
    "station-modules": ("STATION_MODULE", "getChildModulesCopy", "ShipVariantAPI.setModuleVariant"),
    "market-industries": ("BaseMarketConditionPlugin", "BaseIndustry"),
    "rules-commands": ("BaseCommandPlugin",),
    "combat-plugins": ("BaseEveryFrameCombatPlugin",),
}
DEFAULT_TOP = 10


def parse_symbols(text: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(part.strip() for part in text.split(",") if part.strip()))


def _matching_rows(conn: sqlite3.Connection, wanted: str, latest: set[tuple[str, str]]) -> list[sqlite3.Row]:
    escaped = wanted.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    cursor = conn.execute("SELECT * FROM census WHERE area = 'api' AND (symbol = ? OR symbol LIKE ? ESCAPE '\\')",
                          (wanted, "%." + escaped))
    return [r for r in cursor if (r["mod"], r["version"]) in latest and not r["version"].endswith(ORIGINAL_SUFFIX)]


def exemplars(conn: sqlite3.Connection, symbols: tuple[str, ...], top: int = DEFAULT_TOP, feature: str = "") -> dict:
    latest = {(m["id"], m["version"]) for m in latest_mods(conn)}
    mods: dict[str, dict] = {}
    for wanted in symbols:
        for row in _matching_rows(conn, wanted, latest):
            entry = mods.setdefault(row["mod"], {"mod": row["mod"], "version": row["version"], "matched": {}, "refs": 0})
            hit = entry["matched"].setdefault(wanted, {"symbol": wanted, "count": 0, "examples": []})
            hit["count"] += row["count"]
            entry["refs"] += row["count"]
            if row["example"] not in hit["examples"] and len(hit["examples"]) < 3:
                hit["examples"].append(row["example"])
    ranked = []
    for entry in mods.values():
        matched = [entry["matched"][s] for s in symbols if s in entry["matched"]]
        ranked.append({"mod": entry["mod"], "version": entry["version"], "coverage": len(matched), "of": len(symbols),
                       "refs": entry["refs"], "matched": matched, "missing": [s for s in symbols if s not in entry["matched"]]})
    ranked.sort(key=lambda r: (-r["coverage"], -r["refs"], r["mod"]))
    return {"feature": feature or "ad-hoc", "symbols": list(symbols), "label": "STATIC", "mods_with_any": len(ranked), "shown": ranked[:top]}


def exemplars_text(data: dict) -> str:
    lines = [f"exemplars for {data['feature']} (STATIC): {', '.join(data['symbols'])}; {data['mods_with_any']} mod(s) reference at least one"]
    for entry in data["shown"]:
        lines.append(f"  {entry['mod']} {entry['version']}: {entry['coverage']}/{entry['of']} symbols, {entry['refs']} class/file ref(s)")
        for hit in entry["matched"]:
            lines.append(f"      {hit['symbol']} x{hit['count']}  e.g. {'; '.join(hit['examples'])}")
        if entry["missing"]:
            lines.append(f"      missing: {', '.join(entry['missing'])}")
    if not data["shown"]:
        lines.append("  no indexed mod references any of those symbols (run `atlas build`, or check the spelling)")
    return "\n".join(lines)


def run_exemplars(args, conn: sqlite3.Connection, emit) -> int:
    if args.symbols:
        data = exemplars(conn, parse_symbols(args.symbols), args.top)
    elif args.feature in FEATURES:
        data = exemplars(conn, FEATURES[args.feature], args.top, args.feature)
    else:
        raise ValueError(f"give a FEATURE ({', '.join(FEATURES)}) or --symbols a,b,c")
    emit(args, data, exemplars_text(data))
    return 0
