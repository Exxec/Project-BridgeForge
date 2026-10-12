"""Ship data checks: variant validity, weapon slots, carrier bays, skill sets."""
from __future__ import annotations

import re
from .models import ScanResult
from collections import Counter
from pathlib import Path
from .scan_classfile import _iter_jar_class_files, _parse_class_file
from .scan_common import _relative
from .scan_javatext import _blank_java_comments
from .scan_json import _csv_header, _load_lenient_json_file, _read_csv_rows, _read_csv_rows_lenient


def _unregistered_skill_ids(vanilla_core: Path | None) -> set[str]:
    """Skill ids RC8 ships a .skill file for, or comments out of skill_data.csv, but does not register. With the
    0.8.1a reference beside the RC8 install, its skill ids too (removed in 0.9's skill rework)."""
    if vanilla_core is None:
        return set()
    skills = Path(vanilla_core) / "data" / "characters" / "skills"
    rows = _read_csv_rows_lenient(skills / "skill_data.csv") or []
    registered = {(r.get("id") or "").strip() for r in rows if not (r.get("id") or "").strip().startswith("#")}
    known = {p.stem for p in skills.glob("*.skill")} | {(r.get("id") or "").strip().lstrip("#") for r in rows}
    reference = Path(vanilla_core).parent.parent / "Starsector8.1" / "starsector-core" / "data" / "characters" / "skills" / "skill_data.csv"
    known |= {(r.get("id") or "").strip() for r in _read_csv_rows_lenient(reference) or []}
    return {s for s in known - registered if s}


def _scan_unregistered_skill_set(root: Path, result: ScanResult, vanilla_core: Path | None) -> None:
    """RC8-18: setSkillLevel/increaseSkill with a skill RC8 does not register throws a NullPointerException in
    CharacterStats.refreshCharacterStatsEffects (FlowerGod's bounty officer, FG-SOLO2-20260928). Reads
    (getSkillLevel) are not flagged: nothing shows they fail."""
    bad = _unregistered_skill_ids(vanilla_core) - {
        (r.get("id") or "").strip() for r in _read_csv_rows_lenient(root / "data" / "characters" / "skills" / "skill_data.csv") or []}
    if not bad:
        return
    setters = ("setSkillLevel", "increaseSkill")
    hits: dict[str, set[str]] = {}
    for source in sorted(root.rglob("*.java")):
        parts = source.relative_to(root).parts
        if "disabled_files" in parts or "src-decompiled" in parts:
            continue
        try:
            text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        found = {m.group(2) for m in re.finditer(r"\b(setSkillLevel|increaseSkill)\s*\(\s*\"([A-Za-z0-9_]+)\"", text) if m.group(2) in bad}
        if found:
            hits[_relative(root, source)] = found
    for jar, member, data in _iter_jar_class_files(root):
        info = _parse_class_file(data)
        if info is None or not any(name in info.utf8_values for name in setters):
            continue
        found = bad & set(info.string_constants)
        if found:
            hits[f"{_relative(root, jar)}!{member}"] = found
    if not hits:
        return
    result.add(
        id="skill-unregistered",
        category="campaign",
        severity="high",
        classification="MANUAL",
        confidence="MEDIUM",
        explanation="Code sets a skill RC8 does not register (a 0.8 skill, or one RC8 comments out of skill_data.csv). "
                    "RC8 then throws a NullPointerException in CharacterStats.refreshCharacterStatsEffects, a Fatal when the "
                    "code runs. Pick the RC8 successor (a commented-out skill's .skill file names the scripts it runs) and "
                    "RC8's level range. In a jar, a class that also only reads the skill is included; confirm the set.",
        file=sorted(hits)[0],
        evidence=[f"{where}: {', '.join(sorted(found))}" for where, found in sorted(hits.items())][:10],
    )


WEAPON_SLOT_SKIP_TYPES = {"BUILT_IN", "DECORATIVE", "SYSTEM", "LAUNCH_BAY", "STATION_MODULE"}


WEAPON_SLOT_SIZE_RANK = {"SMALL": 1, "MEDIUM": 2, "LARGE": 3}


HULL_MOD_COST_COLUMN_BY_SIZE = {
    "FRIGATE": "cost_frigate",
    "DESTROYER": "cost_dest",
    "CRUISER": "cost_cruiser",
    "CAPITAL": "cost_capital",
}


def _csv_id_index(mod_path: Path, vanilla_path: Path | None) -> dict[str, dict[str, str]]:
    """Merge a mod CSV's 'id'-keyed rows over the matching vanilla CSV (vanilla first, mod wins)."""
    index: dict[str, dict[str, str]] = {}
    for path in (vanilla_path, mod_path):
        if path is None or not path.is_file():
            continue
        for row in _read_csv_rows(path) or []:
            row_id = (row.get("id") or "").strip()
            if row_id and not row_id.startswith("#"):
                index[row_id] = row
    return index


def _float_or(value: object, default: float = 0.0) -> float:
    try:
        text = str(value).strip()
        if not text:
            return default
        return float(text)
    except (TypeError, ValueError):
        return default


def _ship_file_index(root: Path, vanilla_core: Path | None) -> dict[str, dict]:
    """hullId -> parsed .ship data, vanilla first so a mod's own hull of the same id wins."""
    index: dict[str, dict] = {}
    for base in (vanilla_core, root):
        if base is None or not base.is_dir():
            continue
        for path in base.rglob("*.ship"):
            data = _load_lenient_json_file(path)
            if not isinstance(data, dict):
                continue
            hull_id = data.get("hullId")
            if isinstance(hull_id, str) and hull_id.strip():
                index[hull_id.strip()] = data
            elif path.stem in index:
                # A .ship with no hullId is a partial file the game merges over the same-path vanilla one:
                # Militarized Odyssey's odyssey.ship adds only a decorative "WS 020" (2026-09-28), and replacing
                # vanilla's entry made every stock slot look missing. weaponSlots merge by id.
                base = index[path.stem]
                slots = {s.get("id"): s for s in base.get("weaponSlots") or [] if isinstance(s, dict)}
                slots.update({s.get("id"): s for s in data.get("weaponSlots") or [] if isinstance(s, dict)})
                index[path.stem] = {**base, **data, "weaponSlots": list(slots.values())}
            else:
                index[path.stem] = data
    return index


def _skin_index(root: Path, vanilla_core: Path | None) -> dict[str, str]:
    """skinHullId -> baseHullId, from .skin files in the mod and vanilla."""
    index: dict[str, str] = {}
    for base in (vanilla_core, root):
        if base is None or not base.is_dir():
            continue
        for path in base.rglob("*.skin"):
            data = _load_lenient_json_file(path)
            if not isinstance(data, dict):
                continue
            skin_id = data.get("skinHullId")
            base_id = data.get("baseHullId")
            if isinstance(skin_id, str) and skin_id.strip() and isinstance(base_id, str) and base_id.strip():
                index[skin_id.strip()] = base_id.strip()
    return index


def _skin_weapon_slot_changes(root: Path, vanilla_core: Path | None) -> dict[str, dict[str, dict]]:
    """skinHullId -> {slot id: partial field overrides}, from each .skin's own weaponSlotChanges.

    A weapon can be mounted in a slot whose type/size only the SKIN changes, not the underlying
    .ship (ROADMAP P14 item 28: brawler_tritachyon and buffalo_pirates both false-flagged
    `variant-weapon-slot-mismatch` because the fit check compared against the base hull's raw slot,
    never applying the skin's own override - verified directly against real .skin files, e.g.
    `"weaponSlotChanges": {"WS 001": {"type": "ENERGY"}}`, which overlays only the given fields onto
    that slot, the same "mod entries replace/extend core entries at a shared key" pattern the
    engine's JSON merging uses elsewhere).
    """
    index: dict[str, dict[str, dict]] = {}
    for base in (vanilla_core, root):
        if base is None or not base.is_dir():
            continue
        for path in base.rglob("*.skin"):
            data = _load_lenient_json_file(path)
            if not isinstance(data, dict):
                continue
            skin_id = data.get("skinHullId")
            changes = data.get("weaponSlotChanges")
            if isinstance(skin_id, str) and skin_id.strip() and isinstance(changes, dict):
                per_slot = {
                    slot_id: fields
                    for slot_id, fields in changes.items()
                    if isinstance(slot_id, str) and isinstance(fields, dict)
                }
                if per_slot:
                    index[skin_id.strip()] = per_slot
    return index


def _resolve_hull_id(hull_id: str, skins: dict[str, str]) -> str:
    """Chase a skin's baseHullId chain to the underlying hull id (cycle-safe)."""
    seen: set[str] = set()
    current = hull_id
    while current in skins and current not in seen:
        seen.add(current)
        current = skins[current]
    return current


def _wpn_type_size_index(root: Path, vanilla_core: Path | None) -> dict[str, dict[str, str]]:
    """weapon id -> {'type':..., 'size':...} parsed from the actual .wpn spec files."""
    index: dict[str, dict[str, str]] = {}
    for base in (vanilla_core, root):
        if base is None or not base.is_dir():
            continue
        for path in base.rglob("*.wpn"):
            data = _load_lenient_json_file(path)
            if not isinstance(data, dict):
                continue
            weapon_id = data.get("id")
            if isinstance(weapon_id, str) and weapon_id.strip():
                index[weapon_id.strip()] = {
                    "type": str(data.get("type") or "").strip().upper(),
                    "size": str(data.get("size") or "").strip().upper(),
                    # mountTypeOverride lets a weapon fit other slot types (e.g. an ENERGY weapon with
                    # HYBRID fits BALLISTIC slots); ignoring it produced false slot mismatches.
                    "mount_override": str(data.get("mountTypeOverride") or "").strip().upper(),
                }
    return index


# Slot types a weapon's mountTypeOverride lets it occupy, on top of its base type.
MOUNT_OVERRIDE_FITS = {
    "HYBRID": {"BALLISTIC", "ENERGY", "HYBRID", "UNIVERSAL"},
    "COMPOSITE": {"BALLISTIC", "MISSILE", "COMPOSITE", "UNIVERSAL"},
    "SYNERGY": {"ENERGY", "MISSILE", "SYNERGY", "UNIVERSAL"},
    "UNIVERSAL": {"BALLISTIC", "ENERGY", "MISSILE", "HYBRID", "COMPOSITE", "SYNERGY", "UNIVERSAL"},
}


# Hull mods that add fighter bays when present (built-in or installed), e.g. vanilla converted_hangar.
BAY_ADDING_HULL_MODS = {"converted_hangar": 1}


def _override_fits(slot_type: str, mount_override: str) -> bool:
    return bool(mount_override) and slot_type in MOUNT_OVERRIDE_FITS.get(mount_override, {mount_override})


def _weapon_slot_type_compatible(slot_type: str, weapon_type: str) -> bool:
    if slot_type == "UNIVERSAL":
        return True
    if slot_type == "HYBRID":
        return weapon_type in {"BALLISTIC", "ENERGY"}
    if slot_type == "COMPOSITE":
        return weapon_type in {"BALLISTIC", "MISSILE"}
    if slot_type == "SYNERGY":
        return weapon_type in {"ENERGY", "MISSILE"}
    if slot_type in {"BALLISTIC", "ENERGY", "MISSILE"}:
        return weapon_type == slot_type
    # Unrecognized slot type (e.g. a modded enum BridgeForge does not know): do not guess.
    return True


def _system_type_index(root: Path, vanilla_core: Path | None) -> dict[str, str]:
    """ship system id -> .system "type" (e.g. DRONE_LAUNCHER), vanilla first so the mod wins."""
    index: dict[str, str] = {}
    for base in ([vanilla_core] if vanilla_core else []) + [root]:
        folder = base / "data" / "shipsystems"
        for path in sorted(folder.glob("*.system")) if folder.is_dir() else []:
            spec = _load_lenient_json_file(path)
            if isinstance(spec, dict) and isinstance(spec.get("id"), str):
                index[spec["id"]] = str(spec.get("type") or "")
    return index


def carrier_bays_without_evidence(root: Path, vanilla_core: Path | None) -> list[str]:
    """Hull ids of a pre-0.8 ship_data.csv that carry a `hangar` value (or variant wings) but no LAUNCH_BAY slot in the hull's
    .ship file and no wings in any of the mod's variants for that hull. Nothing can launch from such a hull, so 0 is the one
    bay count the data supports (Yellowjackets Mining Conglomerate, 2026-10-10: three hulls with hangar 5/4/3 copied from the
    modding template, no bay slots, no wing_data). Same inputs as carrier-bays-proposal; hulls it would number are not here."""
    path = root / "data" / "hulls" / "ship_data.csv"
    header = _csv_header(path) if path.is_file() else None
    if not header:
        return []
    columns = [cell.strip().lower() for cell in header]
    if "fighter bays" in columns and "hangar" not in columns:
        return []
    ships = _ship_file_index(root, None)
    wings_by_hull: Counter[str] = Counter()
    variants_root = root / "data" / "variants"
    for variant in sorted(variants_root.rglob("*.variant")) if variants_root.is_dir() else []:
        spec = _load_lenient_json_file(variant)
        if isinstance(spec, dict) and isinstance(spec.get("hullId"), str) and isinstance(spec.get("wings"), list):
            wings_by_hull[spec["hullId"]] = max(wings_by_hull[spec["hullId"]], len(spec["wings"]))
    found = []
    for row in _read_csv_rows_lenient(path) or []:
        normalized = {str(key).strip().lower(): (value or "").strip() for key, value in row.items() if key}
        hull_id = normalized.get("id", "")
        if not hull_id or hull_id.startswith("#") or normalized.get("fighter bays"):
            continue
        spec = ships.get(hull_id) or {}
        if not spec or str(spec.get("hullSize") or "").upper() == "FIGHTER":
            continue
        slots = sum(1 for slot in spec.get("weaponSlots") or [] if isinstance(slot, dict) and slot.get("type") == "LAUNCH_BAY")
        if (_float_or(normalized.get("hangar")) or wings_by_hull.get(hull_id, 0)) and not slots and not wings_by_hull.get(hull_id, 0):
            found.append(hull_id)
    return found


def _scan_carrier_bays_proposal(root: Path, result: ScanResult, vanilla_core: Path | None) -> None:
    """Pre-0.8 mods: propose fighter bays per hull from the evidence the old data still carries.

    The owner asked whether a description saying "carrier" is enough (2026-09-14). Across 25 mods it is
    not: descriptions mention carriers on non-carriers, and modern hulls use LAUNCH_BAY slots for drone
    launchers. The pre-0.8 `hangar` column (the author's own carrier record) and variant wings are what
    make a carrier; the LAUNCH_BAY slot count gives the number. Only runs on pre-0.8 ship_data.
    """
    path = root / "data" / "hulls" / "ship_data.csv"
    header = _csv_header(path) if path.is_file() else None
    if not header:
        return
    columns = [cell.strip().lower() for cell in header]
    if "fighter bays" in columns and "hangar" not in columns:
        return  # 0.8+ schema: a blank bay count there is the author's choice
    rows = _read_csv_rows_lenient(path) or []
    ships = _ship_file_index(root, None)
    systems = _system_type_index(root, vanilla_core)
    wings_by_hull: Counter[str] = Counter()
    variants_root = root / "data" / "variants"
    for variant in sorted(variants_root.rglob("*.variant")) if variants_root.is_dir() else []:
        spec = _load_lenient_json_file(variant)
        if isinstance(spec, dict) and isinstance(spec.get("hullId"), str) and isinstance(spec.get("wings"), list):
            wings_by_hull[spec["hullId"]] = max(wings_by_hull[spec["hullId"]], len(spec["wings"]))
    proposals: list[str] = []
    hints_only: list[str] = []
    for row in rows:
        normalized = {str(key).strip().lower(): (value or "").strip() for key, value in row.items() if key}
        hull_id = normalized.get("id", "")
        if not hull_id or hull_id.startswith("#"):
            continue
        if normalized.get("fighter bays"):
            continue  # already set (e.g. by `fix ... --finding carrier-bays-proposal --hull`); don't re-propose it
        spec = ships.get(hull_id) or {}
        if str(spec.get("hullSize") or "").upper() == "FIGHTER":
            continue
        hangar = _float_or(normalized.get("hangar"))
        wings = wings_by_hull.get(hull_id, 0)
        slots = sum(1 for slot in spec.get("weaponSlots") or [] if isinstance(slot, dict) and slot.get("type") == "LAUNCH_BAY")
        drones = systems.get(normalized.get("system id", ""), "") == "DRONE_LAUNCHER"
        evidence = [f"hangar:{int(hangar)}" if hangar else "", f"variant-wings:{wings}" if wings else "", f"launch-bays:{slots}" if slots else "", "system:DRONE_LAUNCHER (slots may be for drones)" if drones else ""]
        evidence = [item for item in evidence if item]
        if hangar or wings:
            proposed = slots or wings
            proposals.append(f"{hull_id}: {f'{proposed} bay(s)' if proposed else 'choose a number (no launch-bay slots)'} [{', '.join(evidence)}]")
        elif "CARRIER" in normalized.get("hints", "").upper() or "carrier" in normalized.get("designation", "").lower():
            hints_only.append(f"{hull_id}: hint only ({', '.join(evidence + ['CARRIER hint/designation'])})")
    if proposals or hints_only:
        result.add(
            id="carrier-bays-proposal",
            category="hulls",
            severity="medium",
            classification="REVIEW",
            confidence="MEDIUM",
            explanation="Pre-0.8a data: these hulls carried fighters under the old system (a `hangar` value or wings in the mod's variants), but 0.8a+ needs a `fighter bays` count. Proposed counts come from each hull's LAUNCH_BAY slots, or its variants' wings. A description mentioning carriers is not treated as evidence, and hint-only hulls get no number. Approve per hull before applying.",
            file=_relative(root, path),
            evidence=proposals + hints_only,
        )


def _resolve_variant_hull_and_slots(raw_hull_id: str, ship_files: dict[str, dict], skins: dict[str, str], skin_slot_changes: dict[str, dict[str, dict]]) -> tuple[str | None, dict | None, dict[str, dict] | None]:
    """(resolved_hull_id, ship_json, slot_by_id) for a variant's raw hullId, with a `.skin`'s own
    `weaponSlotChanges` applied over the base `.ship`'s `weaponSlots` (ROADMAP P14 item 28).

    Extracted from `_scan_variant_validity` (ROADMAP P14 item 4's strip/vendor planner needs the
    exact same slot-by-id resolution to propose a vanilla substitute "of the same slot type and
    size" - reusing this, not a second implementation). Returns `(None, None, None)` when the hull
    can't be resolved to a real `.ship` file; the caller decides what that means for its own case.
    """
    raw_hull_id = raw_hull_id.strip()
    if not raw_hull_id:
        return None, None, None
    resolved_hull_id = _resolve_hull_id(raw_hull_id, skins)
    ship_json = ship_files.get(resolved_hull_id)
    if ship_json is None:
        return None, None, None
    slot_by_id: dict[str, dict] = {}
    for slot in ship_json.get("weaponSlots") or []:
        if isinstance(slot, dict) and isinstance(slot.get("id"), str):
            slot_by_id[slot["id"]] = slot
    # Apply each skin's own weaponSlotChanges along the same baseHullId chain _resolve_hull_id just
    # walked, so a skin can retype/resize a slot the base .ship never touched. Collected
    # outermost-first, then applied in reverse (most-specific-skin-last) so a skin closer to
    # raw_hull_id wins over one further down the chain on the rare case both touch the same slot.
    chain_id = raw_hull_id
    seen_chain: set[str] = set()
    chain_skin_ids: list[str] = []
    while chain_id in skin_slot_changes and chain_id not in seen_chain:
        seen_chain.add(chain_id)
        chain_skin_ids.append(chain_id)
        chain_id = skins.get(chain_id, chain_id)
    for skin_id in reversed(chain_skin_ids):
        for slot_id, overrides in skin_slot_changes[skin_id].items():
            base_slot = slot_by_id.get(slot_id)
            if base_slot is not None:
                slot_by_id[slot_id] = {**base_slot, **overrides}
    return resolved_hull_id, ship_json, slot_by_id


def _scan_variant_validity(root: Path, result: ScanResult, vanilla_core: Path | None) -> None:
    """Cross-check .variant files against their resolved hull's bays, OP budget, and slot rules.

    hullId is resolved through .skin baseHullId chains first (a variant commonly targets a skin's
    id, not the underlying hull's). A hull that cannot be resolved to both a .ship file and a
    ship_data.csv row (mod or vanilla) is left alone entirely: BridgeForge does not have enough
    evidence to compute a bay/OP budget or slot compatibility for it, and reports UNKNOWN, not a
    finding, for such gaps elsewhere; it stays silent here rather than guessing.
    """
    variants_root = root / "data" / "variants"
    if not variants_root.is_dir():
        return

    ship_files = _ship_file_index(root, vanilla_core)
    skins = _skin_index(root, vanilla_core)
    skin_slot_changes = _skin_weapon_slot_changes(root, vanilla_core)
    ship_data = _csv_id_index(
        root / "data" / "hulls" / "ship_data.csv",
        (vanilla_core / "data" / "hulls" / "ship_data.csv") if vanilla_core else None,
    )
    weapon_data = _csv_id_index(
        root / "data" / "weapons" / "weapon_data.csv",
        (vanilla_core / "data" / "weapons" / "weapon_data.csv") if vanilla_core else None,
    )
    weapon_specs = _wpn_type_size_index(root, vanilla_core)
    hull_mod_costs = _csv_id_index(
        root / "data" / "hullmods" / "hull_mods.csv",
        (vanilla_core / "data" / "hullmods" / "hull_mods.csv") if vanilla_core else None,
    )
    wing_data = _csv_id_index(
        root / "data" / "hulls" / "wing_data.csv",
        (vanilla_core / "data" / "hulls" / "wing_data.csv") if vanilla_core else None,
    )

    for path in sorted(variants_root.rglob("*.variant")):
        data = _load_lenient_json_file(path)
        if not isinstance(data, dict):
            continue
        relative = _relative(root, path)
        variant_id = data.get("variantId") or path.stem
        raw_hull_id = data.get("hullId")
        if not isinstance(raw_hull_id, str) or not raw_hull_id.strip():
            continue
        resolved_hull_id, ship_json, slot_by_id = _resolve_variant_hull_and_slots(raw_hull_id, ship_files, skins, skin_slot_changes)
        row = ship_data.get(resolved_hull_id) if resolved_hull_id else None
        if ship_json is None or row is None:
            continue  # Unresolvable hull: UNKNOWN, handled elsewhere; no finding fabricated here.
        if str(ship_json.get("hullSize") or "").strip().upper() == "FIGHTER":
            # Fighter-size hulls are not refit through the OP-budget/bays system: their ship_data.csv
            # "ordnance points" is almost always 0 (verified against vanilla: 30/32 fighter hulls), and
            # any hullMods/wings on a fighter variant are baked into its fixed design, not player-fitted.
            # Checking them against a budget/bay count that does not apply produces false positives.
            continue

        wings = data.get("wings")
        wing_list = [w for w in wings if isinstance(w, str)] if isinstance(wings, list) else []
        built_in_wings = ship_json.get("builtInWings")
        built_in_wing_count = len(built_in_wings) if isinstance(built_in_wings, list) else 0
        fighter_bays = int(_float_or(row.get("fighter bays")))
        # Bays can also come from hull mods (e.g. converted_hangar), built in or installed by the variant.
        bay_mods = set(ship_json.get("builtInMods") or []) | {
            mod for key in ("hullMods", "permaMods") for mod in (data.get(key) or []) if isinstance(mod, str)
        }
        fighter_bays += sum(BAY_ADDING_HULL_MODS.get(mod, 0) for mod in bay_mods)
        total_wings = len(wing_list) + built_in_wing_count
        if total_wings > fighter_bays and not wing_list:
            # Only the hull's built-in wings exceed the bays and the variant lists none of its own: nothing in the
            # variant can change, so it is reported as authored (All the Domain Drones' drone modules, 2026-09-30;
            # owner rule 2026-09-29: drop only what no longer fits, keep the rest as authored).
            result.add(
                id="variant-built-in-wings-exceed-bays",
                category="variants",
                severity="low",
                classification="SAFE",
                confidence="DETERMINISTIC",
                explanation=(
                    f"Hull '{resolved_hull_id}' has {built_in_wing_count} built-in wing(s) but {fighter_bays} fighter bay(s), "
                    f"and variant '{variant_id}' adds none of its own. As authored; the extra built-in wings may not deploy."
                ),
                file=relative,
                evidence=[f"variant:{variant_id}", f"hull:{resolved_hull_id}", f"built-in-wings:{built_in_wing_count}", f"fighter-bays:{fighter_bays}"],
            )
        elif total_wings > fighter_bays:
            result.add(
                id="variant-wings-exceed-bays",
                category="variants",
                severity="high",
                classification="REVIEW",
                confidence="DETERMINISTIC",
                explanation=(
                    f"Variant '{variant_id}' equips {len(wing_list)} wing(s) plus {built_in_wing_count} "
                    f"built-in wing(s) ({total_wings} total) but hull '{resolved_hull_id}' has only "
                    f"{fighter_bays} fighter bay(s) in ship_data.csv. Extra wings will not deploy."
                ),
                file=relative,
                evidence=[f"variant:{variant_id}", f"hull:{resolved_hull_id}", f"wings:{len(wing_list)}", f"built-in-wings:{built_in_wing_count}", f"fighter-bays:{fighter_bays}"],
            )

        built_in_weapon_slots = ship_json.get("builtInWeapons")
        built_in_weapon_slot_ids = set(built_in_weapon_slots.keys()) if isinstance(built_in_weapon_slots, dict) else set()

        weapon_op_total = 0.0
        weapon_groups = data.get("weaponGroups") if isinstance(data.get("weaponGroups"), list) else []
        for group in weapon_groups:
            if not isinstance(group, dict):
                continue
            weapons = group.get("weapons")
            if not isinstance(weapons, dict):
                continue
            for slot_id, weapon_id in weapons.items():
                if slot_id in built_in_weapon_slot_ids or not isinstance(weapon_id, str):
                    continue
                w_row = weapon_data.get(weapon_id)
                if w_row is None:
                    continue
                weapon_op_total += _float_or(w_row.get("OPs"))

        # S-mods and permanent mods (d-mods) cost no OP; RC8 variants may list them in hullMods too (9 of 696
        # over-budget queue variants did, 2026-09-27, e.g. brdy_stenos_event), which overcounted them.
        built_in_mods = set(ship_json.get("builtInMods") or []) | {m for key in ("sMods", "permaMods") for m in (data.get(key) or []) if isinstance(m, str)}
        hull_size = str(ship_json.get("hullSize") or "").strip().upper()
        cost_column = HULL_MOD_COST_COLUMN_BY_SIZE.get(hull_size, "cost_cruiser")
        hull_mod_total = 0.0
        hull_mods = data.get("hullMods") if isinstance(data.get("hullMods"), list) else []
        for mod_id in hull_mods:
            if not isinstance(mod_id, str) or mod_id in built_in_mods:
                continue
            hm_row = hull_mod_costs.get(mod_id)
            if hm_row is None:
                continue
            hull_mod_total += _float_or(hm_row.get(cost_column))

        flux_vents = _float_or(data.get("fluxVents"))
        flux_caps = _float_or(data.get("fluxCapacitors"))

        wing_op_total = 0.0
        for wing_id in wing_list:
            w_row = wing_data.get(wing_id)
            if w_row is None:
                continue
            wing_op_total += _float_or(w_row.get("op cost"))

        ordnance_points = _float_or(row.get("ordnance points"))
        total_op = weapon_op_total + hull_mod_total + flux_vents + flux_caps + wing_op_total
        # Skill/hullmod OP-cost modifiers (e.g. Ordnance Expert, Weapon/Field Modulation) legitimately
        # let a live loadout exceed the *raw* budget in-game; a small tolerance keeps this check from
        # flagging those borderline, still-in-game-valid loadouts instead of genuine authoring bugs.
        tolerance = max(3.0, ordnance_points * 0.05)
        if total_op > ordnance_points + tolerance:
            result.add(
                id="variant-op-over-budget",
                category="variants",
                severity="high",
                classification="REVIEW",
                confidence="DETERMINISTIC",
                explanation=(
                    f"Variant '{variant_id}' costs {total_op:.1f} raw OP (weapons {weapon_op_total:.1f} + "
                    f"hullmods {hull_mod_total:.1f} + flux vents {flux_vents:.1f} + flux capacitors "
                    f"{flux_caps:.1f} + wings {wing_op_total:.1f}) against hull '{resolved_hull_id}''s "
                    f"{ordnance_points:.1f} ordnance points, beyond a {tolerance:.1f} OP tolerance for "
                    "skill/hullmod OP modifiers. Non-built-in costs only; verify in the refit screen."
                ),
                file=relative,
                evidence=[
                    f"variant:{variant_id}",
                    f"hull:{resolved_hull_id}",
                    f"weapons-op:{weapon_op_total:.1f}",
                    f"hullmods-op:{hull_mod_total:.1f}",
                    f"flux-vents:{flux_vents:.1f}",
                    f"flux-capacitors:{flux_caps:.1f}",
                    f"wings-op:{wing_op_total:.1f}",
                    f"total-op:{total_op:.1f}",
                    f"budget:{ordnance_points:.1f}",
                ],
            )

        for group in weapon_groups:
            if not isinstance(group, dict):
                continue
            weapons = group.get("weapons")
            if not isinstance(weapons, dict):
                continue
            for slot_id, weapon_id in weapons.items():
                if not isinstance(weapon_id, str):
                    continue
                slot = slot_by_id.get(slot_id)
                if slot is None:
                    # RC8-17: a weapon in a slot the hull lacks is a Fatal when the ship is drawn ("Slot id [WS 006]
                    # not found on hull [hyperion]", FlowerGod's FGV_hyperion_Attack, FG-SOLO3-20260928). RC8
                    # redesigned vanilla hulls (the Hyperion went from six weapon slots to three), so old variants
                    # of vanilla hulls hit this. The probe builds the variant without error; drawing it fails.
                    if slot_by_id:
                        result.add(
                            id="variant-weapon-slot-missing",
                            category="variants",
                            severity="high",
                            classification="REVIEW",
                            confidence="DETERMINISTIC",
                            explanation=(
                                f"Variant '{variant_id}' puts weapon '{weapon_id}' in slot '{slot_id}', which hull "
                                f"'{resolved_hull_id}' does not have. RC8 throws \"Slot id [...] not found on hull\" when "
                                "the ship is drawn (a fleet screen, a mission): a Fatal. Refit the variant to the hull's "
                                f"current slots ({', '.join(sorted(slot_by_id))})."
                            ),
                            file=relative,
                            evidence=[f"variant:{variant_id}", f"hull:{resolved_hull_id}", f"slot:{slot_id}", f"weapon:{weapon_id}"],
                        )
                    continue
                slot_type = str(slot.get("type") or "").strip().upper()
                if slot_type in WEAPON_SLOT_SKIP_TYPES:
                    continue
                spec = weapon_specs.get(weapon_id)
                if spec is None:
                    continue
                slot_size = str(slot.get("size") or "").strip().upper()
                weapon_size = spec.get("size", "")
                weapon_type = spec.get("type", "")
                size_mismatch = WEAPON_SLOT_SIZE_RANK.get(weapon_size, 0) > WEAPON_SLOT_SIZE_RANK.get(slot_size, 0)
                type_mismatch = weapon_type and not (
                    _weapon_slot_type_compatible(slot_type, weapon_type)
                    or _override_fits(slot_type, spec.get("mount_override", ""))
                )
                if size_mismatch or type_mismatch:
                    reasons = []
                    if size_mismatch:
                        reasons.append(f"weapon size {weapon_size} exceeds slot size {slot_size}")
                    if type_mismatch:
                        reasons.append(f"weapon type {weapon_type} incompatible with slot type {slot_type}")
                    result.add(
                        id="variant-weapon-slot-mismatch",
                        category="variants",
                        severity="high",
                        classification="REVIEW",
                        confidence="DETERMINISTIC",
                        explanation=(
                            f"Variant '{variant_id}' puts weapon '{weapon_id}' in slot '{slot_id}' on hull "
                            f"'{resolved_hull_id}': {'; '.join(reasons)}."
                        ),
                        file=relative,
                        evidence=[f"variant:{variant_id}", f"hull:{resolved_hull_id}", f"slot:{slot_id}", f"slot-type:{slot_type}", f"slot-size:{slot_size}", f"weapon:{weapon_id}", f"weapon-type:{weapon_type}", f"weapon-size:{weapon_size}"],
                    )
