"""`bridgeforge strip-plan`: the exact edit list for stripping unresolved content (ROADMAP P14 item 4, first slice).

When `dependency-substitutes` recommends STRIP_FROM_MOD, the unresolved hull mods, wings, weapons and
hulls a mod uses have to come out file by file. The scan's `content-reference-unresolved` finding
only counts them; this lists every place each id sits (a variant's weapon slot, a hull-mod list, a
built-in weapon, a faction known-list) and, for a weapon slot, the vanilla weapons that fit the same
slot type and size. A variant or skin whose own hull is unresolved cannot be stripped piecemeal, so
it is listed for deletion instead.

Nothing is edited: this is the reviewable plan, and choosing a substitute is a design decision.
Not yet here (item 4's later slices): generating the matching PROPOSED expected changes, and vendoring.
"""
from __future__ import annotations

from pathlib import Path

from .models import TargetProfile
from .scanner import (
    MOUNT_OVERRIDE_FITS,
    WEAPON_SLOT_SIZE_RANK,
    WEAPON_SLOT_SKIP_TYPES,
    _load_lenient_json_file,
    _resolve_hull_id,
    _ship_file_index,
    _skin_index,
    _weapon_slot_type_compatible,
    _wpn_type_size_index,
    scan_mod,
)

SCHEMA_VERSION = 1
MAX_SUBSTITUTES = 8
_LIST_KEYS = {
    "hullmod": ("hullMods", "permaMods", "sMods", "builtInMods", "removeBuiltInMods"),
    "wing": ("wings", "builtInWings"),
}
# .faction known-list layout, as `fix --finding faction-known-lists-missing` writes it.
_FACTION_LISTS = {"hull": ("knownShips", "hulls"), "weapon": ("knownWeapons", "weapons"), "wing": ("knownFighters", "fighters")}
_MOUNTABLE = {"BALLISTIC", "ENERGY", "MISSILE"}


class StripPlanError(ValueError):
    """Raised for a missing mod folder or vanilla core."""


def _substitutes(slot: dict | None, vanilla_weapons: dict[str, dict[str, str]]) -> dict:
    if not isinstance(slot, dict):
        return {"slot": None, "candidates": [], "note": "slot not found on the resolved hull; no substitute proposed"}
    slot_type = str(slot.get("type") or "").strip().upper()
    slot_size = str(slot.get("size") or "").strip().upper()
    if slot_type in WEAPON_SLOT_SKIP_TYPES or slot_size not in WEAPON_SLOT_SIZE_RANK:
        return {"slot": f"{slot_type} {slot_size}", "candidates": [], "note": "not a regular weapon slot; no substitute proposed"}
    fits = sorted(
        weapon_id for weapon_id, spec in vanilla_weapons.items()
        if spec.get("size") == slot_size and (
            (spec.get("type") in _MOUNTABLE and _weapon_slot_type_compatible(slot_type, spec["type"]))
            or slot_type in MOUNT_OVERRIDE_FITS.get(spec.get("mount_override", ""), set()))
    )
    return {"slot": f"{slot_type} {slot_size}", "candidates": fits[:MAX_SUBSTITUTES], "candidate_count": len(fits)}


def strip_plan(mod_dir: Path, vanilla_core: Path, only: list[str] | None = None) -> dict:
    mod_dir, vanilla_core = Path(mod_dir).expanduser().resolve(), Path(vanilla_core).expanduser().resolve()
    if not (mod_dir / "mod_info.json").is_file():
        raise StripPlanError(f"{mod_dir} has no mod_info.json.")
    if not (vanilla_core / "data").is_dir():
        raise StripPlanError(f"{vanilla_core} has no data/ folder; pass a starsector-core folder.")
    scan = scan_mod(mod_dir, TargetProfile(), vanilla_core)
    unresolved: dict[str, dict[str, list[str]]] = scan.migration_context.get("unresolved_content_references") or {}
    wanted = {tuple(item.split(":", 1)) for item in only or [] if ":" in item}
    targets = {kind: set(ids) for kind, ids in unresolved.items()}
    if wanted:
        targets = {kind: {ident for ident in ids if (kind, ident) in wanted} for kind, ids in targets.items()}
    ships, skins = _ship_file_index(mod_dir, vanilla_core), _skin_index(mod_dir, vanilla_core)
    vanilla_weapons = _wpn_type_size_index(vanilla_core, None)

    edits: list[dict] = []
    files = sorted({path for kind, ids in unresolved.items() for ident, paths in ids.items() if ident in targets.get(kind, set()) for path in paths})
    factions = mod_dir / "data" / "world" / "factions"
    files += sorted(path.relative_to(mod_dir).as_posix() for path in factions.glob("*.faction")) if factions.is_dir() else []
    for relative in files:
        spec = _load_lenient_json_file(mod_dir / relative)
        if not isinstance(spec, dict):
            continue
        suffix = Path(relative).suffix.lower()
        if suffix == ".faction":
            for kind, (outer, inner) in _FACTION_LISTS.items():
                block = spec.get(outer)
                for ident in (block.get(inner) or []) if isinstance(block, dict) else []:
                    if ident in targets.get(kind, set()):
                        edits.append({"file": relative, "kind": kind, "id": ident, "action": f"remove from {outer}.{inner}"})
            continue
        hull_key = "hullId" if suffix == ".variant" else "baseHullId" if suffix == ".skin" else None
        if hull_key and spec.get(hull_key) in targets.get("hull", set()):
            edits.append({"file": relative, "kind": "hull", "id": spec[hull_key],
                          "action": f"delete this {suffix[1:]}: its {hull_key} is unresolved, so nothing in it can load"})
            continue
        for kind, keys in _LIST_KEYS.items():
            for key in keys:
                for ident in spec.get(key) or []:
                    if ident in targets.get(kind, set()):
                        edits.append({"file": relative, "kind": kind, "id": ident, "action": f"remove from {key}"})
        own_hull = spec.get("hullId") if suffix == ".variant" else spec.get("skinHullId") if suffix == ".skin" else spec.get("hullId")
        hull_spec = ships.get(_resolve_hull_id(own_hull, skins)) if isinstance(own_hull, str) else None
        if suffix == ".ship":
            hull_spec = spec
        slots = {slot["id"]: slot for slot in (hull_spec or {}).get("weaponSlots") or [] if isinstance(slot, dict) and isinstance(slot.get("id"), str)}
        for index, group in enumerate(spec.get("weaponGroups") or []):
            for slot_id, ident in (group.get("weapons") or {}).items() if isinstance(group, dict) and isinstance(group.get("weapons"), dict) else []:
                if ident in targets.get("weapon", set()):
                    edits.append({"file": relative, "kind": "weapon", "id": ident, "action": f"empty slot {slot_id} (weaponGroups[{index}])",
                                  "substitutes": _substitutes(slots.get(slot_id), vanilla_weapons)})
        for slot_id, ident in (spec.get("builtInWeapons") or {}).items() if isinstance(spec.get("builtInWeapons"), dict) else []:
            if ident in targets.get("weapon", set()):
                edits.append({"file": relative, "kind": "weapon", "id": ident, "action": f"remove built-in weapon at {slot_id}",
                              "substitutes": _substitutes(slots.get(slot_id), vanilla_weapons)})

    by_id: dict[str, int] = {}
    for edit in edits:
        by_id[f"{edit['kind']}:{edit['id']}"] = by_id.get(f"{edit['kind']}:{edit['id']}", 0) + 1
    return {
        "schema_version": SCHEMA_VERSION, "mode": "STRIP_PLAN", "mod": str(mod_dir), "vanilla_core": str(vanilla_core),
        "unresolved": {kind: sorted(ids) for kind, ids in unresolved.items()},
        "planned": sorted(by_id), "edits": edits, "edit_count_by_id": by_id,
        "note": "A plan only: nothing was edited. Substitutes fit the slot's type and size; picking one (or leaving the slot empty) is a design decision.",
    }
