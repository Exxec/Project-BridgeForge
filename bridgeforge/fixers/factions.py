from __future__ import annotations
import json
import re
from pathlib import Path
from ..build_tag import _find_top_level_key, _structural_depths
from ..scanner import FACTION_SPECIAL_ROLE_KEYS, _load_lenient_json_file, _parse_json, _read_csv_rows, _wing_ids_set
from .common import FileChange, FixerError, _decode, _encode


def _hull_ids(root: Path) -> set[str]:
    ids: set[str] = set()
    for row in _read_csv_rows(root / "data" / "hulls" / "ship_data.csv") or []:
        hull_id = (row.get("id") or "").strip()
        if hull_id and not hull_id.startswith("#"):
            ids.add(hull_id)
    skins_dir = root / "data" / "hulls" / "skins"
    if skins_dir.is_dir():
        for path in skins_dir.glob("*.skin"):
            data = _load_lenient_json_file(path)
            if isinstance(data, dict):
                skin_hull_id = data.get("skinHullId")
                if isinstance(skin_hull_id, str) and skin_hull_id:
                    ids.add(skin_hull_id)
    return ids


def _weapon_ids(root: Path) -> set[str]:
    ids: set[str] = set()
    for row in _read_csv_rows(root / "data" / "weapons" / "weapon_data.csv") or []:
        weapon_id = (row.get("id") or "").strip()
        if weapon_id and not weapon_id.startswith("#"):
            ids.add(weapon_id)
    return ids


def _load_variant(search_roots: list[Path], variant_id: str) -> dict | None:
    for search_root in search_roots:
        direct = search_root / "data" / "variants" / f"{variant_id}.variant"
        if direct.is_file():
            data = _load_lenient_json_file(direct)
            if isinstance(data, dict):
                return data
    for search_root in search_roots:
        variants_root = search_root / "data" / "variants"
        if not variants_root.is_dir():
            continue
        for path in variants_root.rglob(f"{variant_id}.variant"):
            data = _load_lenient_json_file(path)
            if isinstance(data, dict):
                return data
    return None


def _fix_faction_known_lists_missing(root: Path, options: dict) -> list[FileChange]:
    faction_file = options.get("faction_file")
    vanilla_core = options.get("vanilla_core")
    if not faction_file:
        raise FixerError("--faction-file is required for faction-known-lists-missing.")
    if not vanilla_core:
        raise FixerError("--vanilla-core is required for faction-known-lists-missing.")

    faction_path = Path(faction_file)
    if not faction_path.is_absolute():
        faction_path = root / faction_path
    faction_path = faction_path.resolve()
    if not faction_path.is_file():
        raise FixerError(f"{faction_path} does not exist.")
    vanilla_root = Path(vanilla_core).expanduser().resolve()

    raw = faction_path.read_bytes()
    text, had_bom = _decode(raw)
    data = _load_lenient_json_file(faction_path)
    if not isinstance(data, dict):
        raise FixerError(f"{faction_path} could not be parsed as JSON.")
    ship_roles = data.get("shipRoles")
    variant_ids: set[str] = set()
    if isinstance(ship_roles, dict):
        for block in ship_roles.values():
            if not isinstance(block, dict):
                continue
            for key in block:
                if key in FACTION_SPECIAL_ROLE_KEYS:
                    continue
                variant_ids.add(key)
    else:
        # A 0.6-era faction lists its fleets in fleetCompositions[*].ships ({"atol_Wayfarer":[1, 1], ...}) instead
        # of shipRoles (Antediluvians, Batavia, Qualljom and six more, 2026-09-30): the same variant and wing ids.
        for composition in (data.get("fleetCompositions") or {}).values():
            if isinstance(composition, dict) and isinstance(composition.get("ships"), dict):
                variant_ids.update(key for key in composition["ships"] if isinstance(key, str) and key)
    if not variant_ids:
        raise FixerError(f"{faction_path} has no shipRoles or fleetCompositions ships to derive known lists from.")

    search_roots = [root, vanilla_root]
    valid_hull_ids = _hull_ids(root) | _hull_ids(vanilla_root)
    valid_weapon_ids = _weapon_ids(root) | _weapon_ids(vanilla_root)
    valid_wing_ids = _wing_ids_set(root / "data" / "hulls" / "wing_data.csv") | _wing_ids_set(
        vanilla_root / "data" / "hulls" / "wing_data.csv"
    )

    known_hulls: set[str] = set()
    known_weapons: set[str] = set()
    known_fighters: set[str] = set()
    unresolved: list[str] = []

    for variant_id in sorted(variant_ids):
        if variant_id in valid_wing_ids and _load_variant(search_roots, variant_id) is None:
            # Pre-0.65 role and fleet lists named wings directly ("broadsword_wing"): a known fighter, not a variant.
            known_fighters.add(variant_id)
            continue
        variant_data = _load_variant(search_roots, variant_id)
        if variant_data is None:
            unresolved.append(f"variant:{variant_id} (not found)")
            continue
        hull_id = variant_data.get("hullId")
        if isinstance(hull_id, str) and hull_id:
            if hull_id not in valid_hull_ids:
                unresolved.append(f"hull:{hull_id} (from variant {variant_id})")
            else:
                known_hulls.add(hull_id)
        for group in variant_data.get("weaponGroups", []) or []:
            if not isinstance(group, dict):
                continue
            assigned = group.get("weapons", {})
            if isinstance(assigned, dict):
                for weapon_id in assigned.values():
                    if not isinstance(weapon_id, str) or not weapon_id:
                        continue
                    if weapon_id not in valid_weapon_ids:
                        unresolved.append(f"weapon:{weapon_id} (from variant {variant_id})")
                    else:
                        known_weapons.add(weapon_id)
        for wing_id in variant_data.get("wings", []) or []:
            if not isinstance(wing_id, str) or not wing_id:
                continue
            if wing_id not in valid_wing_ids:
                unresolved.append(f"wing:{wing_id} (from variant {variant_id})")
            else:
                known_fighters.add(wing_id)

    if unresolved:
        raise FixerError("Refusing to derive known-lists: unresolved id(s): " + "; ".join(sorted(set(unresolved))))

    # Only the lists the faction lacks: RC8 refuses a repeated key (Fatal 'Duplicate key "knownFighters"', Ironclads
    # pirates.faction, GRP10E-20261005), and Python's json keeps the last copy silently, so the re-parse below hid it.
    lists = (("knownShips", "hulls", known_hulls), ("knownWeapons", "weapons", known_weapons), ("knownFighters", "fighters", known_fighters))
    insertion = "".join(f'"{key}":{{"{inner}":[' + ",".join(json.dumps(item) for item in sorted(items)) + "]},"
                        for key, inner, items in lists if key not in data)
    if not insertion:
        raise FixerError(f"{faction_path} already declares knownShips, knownWeapons and knownFighters.")

    depths = _structural_depths(text)
    match = None
    # Before the top-level key the lists were derived from: shipRoles, or a 0.6-era fleetCompositions.
    for key in ("shipRoles", "fleetCompositions"):
        match = _find_top_level_key(text, re.compile(r"(?P<key>['\"]?" + key + r"['\"]?)\s*:"), depths)
        if match is not None:
            break
    if match is None:
        raise FixerError(f"{faction_path} has no top-level 'shipRoles' or 'fleetCompositions' key to insert before.")
    insert_at = match.start()
    new_text = text[:insert_at] + insertion + text[insert_at:]
    try:
        parsed, _tolerances = _parse_json(new_text)
    except json.JSONDecodeError as exc:
        raise FixerError(f"Edited {faction_path} failed to re-parse: {exc}") from exc
    if not isinstance(parsed, dict) or "knownShips" not in parsed:
        raise FixerError(f"Edited {faction_path} did not round-trip knownShips as expected.")
    return [FileChange(path=faction_path, before=raw, after=_encode(new_text, had_bom))]
