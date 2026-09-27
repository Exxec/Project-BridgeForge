"""`bridgeforge content-diff`: content ids vanilla removed between two game versions (ROADMAP P14 item 8).

`content-reference-unresolved` says a hull, weapon, wing or hull mod is "defined nowhere". For an old
mod that is often because vanilla itself dropped the id (Vacuum's `thruster_fighter_sm`, Rebal's
`shields_formshield`, both now carried by RevenantLib), which calls for a different fix than a missing
dependency. Comparing the install a mod was made for with RC8, once, turns "defined nowhere" into
"removed in RC8", with RC8 ids of the same display name as successor candidates (leads, not claims).

Ids are read with the scanner's own indexes, so "defined" means the same here as in the scan.
Read-only on both cores.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from .models import ScanResult
from .scanner import (
    _csv_id_index,
    _load_lenient_json_file,
    _ship_file_index,
    _skin_index,
    _wpn_type_size_index,
)

SCHEMA_VERSION = 1
MAX_CANDIDATES = 5
# kind -> the CSV (relative to the core) whose "name" column gives a display name for successor matching
_NAME_TABLES = {
    "hull": "data/hulls/ship_data.csv",
    "weapon": "data/weapons/weapon_data.csv",
    "hullmod": "data/hullmods/hull_mods.csv",
    "shipsystem": "data/shipsystems/ship_systems.csv",
}


class ContentDiffError(ValueError):
    """Raised when a core folder is missing or holds no recognisable data."""


def _variant_ids(core: Path) -> set[str]:
    ids: set[str] = set()
    root = core / "data" / "variants"
    for path in root.rglob("*.variant") if root.is_dir() else []:
        data = _load_lenient_json_file(path)
        declared = data.get("variantId") if isinstance(data, dict) else None
        ids.add(declared.strip() if isinstance(declared, str) and declared.strip() else path.stem)
    return ids


def content_ids(core: Path) -> dict[str, set[str]]:
    data = core / "data"
    return {
        "hull": set(_ship_file_index(core, None)) | set(_skin_index(core, None)),
        "variant": _variant_ids(core),
        "weapon": set(_csv_id_index(data / "weapons" / "weapon_data.csv", None)) | set(_wpn_type_size_index(core, None)),
        "wing": set(_csv_id_index(data / "hulls" / "wing_data.csv", None)),
        "hullmod": set(_csv_id_index(data / "hullmods" / "hull_mods.csv", None)),
        "shipsystem": set(_csv_id_index(data / "shipsystems" / "ship_systems.csv", None)),
    }


def _names(core: Path, kind: str) -> dict[str, str]:
    table = _NAME_TABLES.get(kind)
    if table is None:
        return {}
    return {row_id: (row.get("name") or "").strip() for row_id, row in _csv_id_index(core / table, None).items() if (row.get("name") or "").strip()}


def _fingerprint(core: Path) -> str:
    digest = hashlib.sha256()
    for table in sorted(set(_NAME_TABLES.values()) | {"data/hulls/wing_data.csv"}):
        path = core / table
        digest.update(table.encode() + (path.read_bytes() if path.is_file() else b"<absent>"))
    return digest.hexdigest()


def diff_content(reference_core: Path, current_core: Path) -> dict:
    reference_core, current_core = (Path(p).expanduser().resolve() for p in (reference_core, current_core))
    for label, core in (("reference core", reference_core), ("RC8 core", current_core)):
        if not (core / "data").is_dir():
            raise ContentDiffError(f"{label} {core} has no data/ folder; pass a starsector-core folder.")
    old, new = content_ids(reference_core), content_ids(current_core)
    removed: dict[str, list[dict]] = {}
    added: dict[str, int] = {}
    for kind in old:
        gone = sorted(old[kind] - new[kind])
        added[kind] = len(new[kind] - old[kind])
        if not gone:
            continue
        old_names, new_names = _names(reference_core, kind), _names(current_core, kind)
        by_name: dict[str, list[str]] = {}
        for ident, name in new_names.items():
            if ident not in old[kind]:
                by_name.setdefault(name.lower(), []).append(ident)
        removed[kind] = [{
            "id": ident,
            **({"name": old_names[ident]} if ident in old_names else {}),
            "same_name_in_rc8": sorted(by_name.get(old_names.get(ident, "").lower(), []))[:MAX_CANDIDATES],
        } for ident in gone]
    return {
        "schema_version": SCHEMA_VERSION, "mode": "CONTENT_DIFF",
        "reference_core": str(reference_core), "rc8_core": str(current_core),
        "reference_fingerprint": _fingerprint(reference_core), "rc8_fingerprint": _fingerprint(current_core),
        "counts": {kind: {"reference": len(old[kind]), "rc8": len(new[kind]), "removed": len(removed.get(kind, [])), "added": added[kind]} for kind in old},
        "removed": removed,
        "note": "same_name_in_rc8 lists RC8-only ids with the removed id's display name: leads to verify, not proof of a rename.",
    }


def annotate_removed_content(result: ScanResult, catalogue: dict) -> int:
    """Add `content-reference-removed-in-vanilla` for unresolved ids the older vanilla defined; return how many."""
    unresolved = result.migration_context.get("unresolved_content_references") or {}
    removed = {kind: {entry["id"]: entry for entry in entries} for kind, entries in (catalogue.get("removed") or {}).items()}
    evidence = []
    for kind, table in sorted(unresolved.items()):
        for ident, files in sorted(table.items()):
            entry = removed.get(kind, {}).get(ident)
            if entry is None:
                continue
            leads = entry.get("same_name_in_rc8") or []
            evidence.append(f"{kind}:{ident} ({len(files)} file(s)) removed from vanilla"
                            + (f"; same name in RC8: {', '.join(leads)}" if leads else "; no same-named RC8 id"))
    if evidence:
        result.add(
            id="content-reference-removed-in-vanilla",
            category="dependencies",
            severity="high",
            classification="MANUAL",
            confidence="HIGH",
            explanation="These ids are unresolved because vanilla removed them after the version this mod was made for (per the supplied content-diff catalogue), not because a dependency is missing. Choose per id: an RC8 successor (the same-named candidates are leads to verify), a copy carried by RevenantLib, or removing the reference.",
            evidence=evidence[:25] + ([f"... {len(evidence) - 25} more"] if len(evidence) > 25 else []),
        )
    return len(evidence)
