"""Mission folder checks: required files, fleet references and variant assets."""
from __future__ import annotations

import csv
import json
import re
import zipfile
from ..models import ScanResult
from pathlib import Path
from .scan_campaign import _declared_spec_ids
from .scan_classfile import _loaded_mod_jars
from .scan_common import MISSION_FLEET_REFERENCE_PATTERN, _relative
from .scan_javatext import _blank_java_comments
from .scan_json import _load_lenient_json_file, _parse_json, _wing_ids_set
from .scan_ships import _resolve_hull_id, _skin_index


MISSION_REQUIRED_FILES = ("descriptor.json", "MissionDefinition.java", "mission_text.txt")


def _scan_mission_required_files(root: Path, result: ScanResult) -> None:
    """Every mission in mission_list.csv needs the files vanilla missions all ship (live bug PRB-MISSION-01).

    The game loads them when the Missions screen opens, so a missing one is a `Fatal: Error loading
    [data/missions/<id>/mission_text.txt]` dialog at startup, never a log line. An `icon` declared in
    descriptor.json must exist too.
    """
    mission_list = root / "data" / "missions" / "mission_list.csv"
    if not mission_list.is_file():
        return
    try:
        with mission_list.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle))
    except (OSError, csv.Error, UnicodeDecodeError):
        return
    mission_ids = [row[0].strip() for row in rows[1:] if row and row[0].strip() and not row[0].strip().startswith("#")]
    # Many mods compile MissionDefinition into their jar instead of shipping the loose .java (SEEKER's
    # missions ran live that way), so a compiled data/missions/<id>/MissionDefinition.class counts.
    compiled_entries: set[str] = set()
    for jar in _loaded_mod_jars(root):
        try:
            with zipfile.ZipFile(jar) as archive:
                compiled_entries.update(name for name in archive.namelist() if name.startswith("data/missions/"))
        except (OSError, zipfile.BadZipFile):
            continue
    for mission_id in mission_ids:
        mission_dir = root / "data" / "missions" / mission_id
        if not mission_dir.is_dir():
            result.add(
                id="mission-required-file-missing",
                category="missions",
                severity="high",
                classification="MANUAL",
                confidence="DETERMINISTIC",
                explanation="mission_list.csv lists this mission but the mod has no data/missions/<id>/ folder. Unless the id is a vanilla mission, the game shows a Fatal dialog when it loads the mission list.",
                file=_relative(root, mission_list),
                evidence=[f"mission:{mission_id}", "missing: folder"],
            )
            continue
        missing = [name for name in MISSION_REQUIRED_FILES if not (mission_dir / name).is_file()]
        if "MissionDefinition.java" in missing and f"data/missions/{mission_id}/MissionDefinition.class" in compiled_entries:
            missing.remove("MissionDefinition.java")
        descriptor = _load_lenient_json_file(mission_dir / "descriptor.json") if (mission_dir / "descriptor.json").is_file() else None
        icon = descriptor.get("icon") if isinstance(descriptor, dict) else None
        if isinstance(icon, str) and icon.strip() and not (mission_dir / icon.strip()).is_file():
            missing.append(f"{icon.strip()} (descriptor icon)")
        if missing:
            result.add(
                id="mission-required-file-missing",
                category="missions",
                severity="high",
                classification="MANUAL",
                confidence="DETERMINISTIC",
                explanation="A listed mission is missing a file that every vanilla mission ships. The game raises a Fatal dialog (\"Error loading [data/missions/<id>/...] resource, not found\") when it loads the mission list, so the game never reaches the main menu.",
                file=_relative(root, mission_dir),
                evidence=[f"mission:{mission_id}"] + [f"missing:{name}" for name in missing],
            )


def _scan_campaign_fleet_references(root: Path, result: ScanResult, vanilla_core: Path | None = None) -> None:
    """Variant and wing ids that campaign code builds fleets from must exist (Zorg18 spawner, 2026-09-14).

    Missions are covered by mission-local-fleet-reference-missing. Campaign spawners often keep ids in
    arrays and pick one at run time, so every string literal with this mod's prefix is checked in any
    source that uses FleetMemberType: "<prefix>..._wing" must be a wing, and a literal that starts with
    one of the mod's hull ids plus "_" must be a variant. A missing one fails only when that fleet spawns.

    A hull literal is resolved through any .skin chain first (BF-SKIN-01, docs/BUG_CLASSES.md): a
    campaign spawner commonly names a skin's id, not the underlying .ship's, same as a mission variant.
    """
    mod_id = str(result.metadata.get("id") or "").strip()
    if not mod_id:
        return
    prefix = f"{mod_id}_"
    variants = set(_declared_spec_ids(root / "data" / "variants", "*.variant", "variantId"))
    hulls = set(_declared_spec_ids(root / "data" / "hulls", "*.ship", "hullId"))
    wings = _wing_ids_set(root / "data" / "hulls" / "wing_data.csv")
    if not hulls and not wings:
        return
    skins = _skin_index(root, vanilla_core)

    def _is_known_hull(literal: str) -> bool:
        return literal in hulls or _resolve_hull_id(literal, skins) in hulls

    missing: list[str] = []
    for source in sorted(root.rglob("*.java")):
        parts = source.relative_to(root).parts
        if "disabled_files" in parts or "missions" in parts:
            continue
        try:
            text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if "FleetMemberType" not in text:
            continue
        for literal in sorted(set(re.findall(r'"(' + re.escape(prefix) + r'[A-Za-z0-9_]+)"', text))):
            if literal in variants or literal in wings or _is_known_hull(literal):
                continue
            if literal.endswith("_wing") or any(literal.startswith(hull + "_") for hull in hulls):
                missing.append(f"{_relative(root, source)}: {literal}")
    if missing:
        result.add(
            id="campaign-fleet-reference-missing",
            category="campaign",
            severity="high",
            classification="MANUAL",
            confidence="HIGH",
            explanation="Campaign code builds fleets from a variant or wing id that this mod doesn't define. createFleetMember fails (or the member is skipped) only when that fleet spawns, which can be hours into a game.",
            evidence=missing,
        )


def _scan_mission_local_fleet_references(root: Path, result: ScanResult, vanilla_core: Path | None = None) -> None:
    mod_id = str(result.metadata.get("id") or "").strip()
    if not mod_id:
        return
    prefix = f"{mod_id}_"
    variants = set(_declared_spec_ids(root / "data" / "variants", "*.variant", "variantId"))
    hulls = set(_declared_spec_ids(root / "data" / "hulls", "*.ship", "hullId"))
    weapons = set(_declared_spec_ids(root / "data" / "weapons", "*.wpn", "id"))
    # A mission variant's hullId commonly targets a .skin's id rather than a bare .ship's, the
    # same pattern _scan_variant_validity already resolves (Leon-Heavy-Industries' four
    # `*_pirate_raider` missions, found 2026-09-20: real, art-backed, campaign-wired content, not
    # a gap). Built lazily below, only if a local variant actually needs checking.
    skins: dict[str, str] | None = None
    wing_data = root / "data" / "hulls" / "wing_data.csv"
    wings: set[str] = set()
    if wing_data.is_file():
        try:
            with wing_data.open("r", encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    wing_id = row.get("id")
                    if wing_id:
                        wings.add(wing_id)
        except (OSError, csv.Error, UnicodeDecodeError):
            return
    mission_sources = {
        * (root / "src").glob("data/missions/*/MissionDefinition.java"),
        * (root / "data").glob("missions/*/MissionDefinition.java"),
    }
    references: list[dict[str, str]] = []
    inspected_variants: set[str] = set()
    for source in sorted(mission_sources):
        try:
            text = source.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for fleet_id, member_type in MISSION_FLEET_REFERENCE_PATTERN.findall(_blank_java_comments(text)):
            resolution = "external-or-core"
            if fleet_id.startswith(prefix):
                resolution = "resolved-local" if fleet_id in (variants if member_type == "SHIP" else wings) else "missing-local"
            references.append({"file": _relative(root, source), "kind": member_type, "id": fleet_id, "resolution": resolution})
            if not fleet_id.startswith(prefix):
                continue
            expected = variants if member_type == "SHIP" else wings
            if fleet_id not in expected:
                result.add(
                    id="mission-local-fleet-reference-missing",
                    category="missions",
                    severity="high",
                    classification="MANUAL",
                    confidence="DETERMINISTIC",
                    explanation="A mission references a fleet member with this mod's ID prefix, but the corresponding local variant or fighter wing was not found.",
                    file=_relative(root, source),
                    evidence=[f"{member_type}:{fleet_id}", "resolution: missing-local"],
                )
            elif member_type == "SHIP" and fleet_id not in inspected_variants:
                inspected_variants.add(fleet_id)
                if skins is None:
                    skins = _skin_index(root, vanilla_core)
                _scan_mission_variant_assets(root, result, fleet_id, prefix, hulls, weapons, skins)
    result.migration_context["mission_fleet_references"] = references


def _scan_mission_variant_assets(
    root: Path, result: ScanResult, variant_id: str, prefix: str, hulls: set[str], weapons: set[str], skins: dict[str, str] | None = None
) -> None:
    path = root / "data" / "variants" / f"{variant_id}.variant"
    try:
        data, _ = _parse_json(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return
    if not isinstance(data, dict):
        return
    hull_id = data.get("hullId")
    if isinstance(hull_id, str) and hull_id.startswith(prefix):
        resolved_hull_id = _resolve_hull_id(hull_id, skins or {})
        if resolved_hull_id not in hulls:
            evidence = [f"variant:{variant_id}", f"hull:{hull_id}", "resolution: missing-local"]
            if resolved_hull_id != hull_id:
                evidence.append(f"resolved-via-skin:{resolved_hull_id}")
            result.add(
                id="mission-local-variant-hull-missing",
                category="missions",
                severity="high",
                classification="MANUAL",
                confidence="DETERMINISTIC",
                explanation="A locally referenced mission variant uses a hull with this mod's ID prefix, but no matching local .ship definition was found, even after resolving the id through any .skin chain.",
                file=_relative(root, path),
                evidence=evidence,
            )
    weapon_ids: set[str] = set()
    for group in data.get("weaponGroups", []):
        if not isinstance(group, dict):
            continue
        assigned = group.get("weapons", {})
        if isinstance(assigned, dict):
            weapon_ids.update(value for value in assigned.values() if isinstance(value, str))
    missing_weapons = sorted(weapon_id for weapon_id in weapon_ids if weapon_id.startswith(prefix) and weapon_id not in weapons)
    if missing_weapons:
        result.add(
            id="mission-local-variant-weapon-missing",
            category="missions",
            severity="high",
            classification="MANUAL",
            confidence="DETERMINISTIC",
            explanation="A locally referenced mission variant uses weapon IDs with this mod's prefix, but matching local .wpn definitions were not found.",
            file=_relative(root, path),
            evidence=[f"variant:{variant_id}", *[f"weapon:{weapon_id}" for weapon_id in missing_weapons], "resolution: missing-local"],
        )


def _is_mission_source(root: Path, path: Path) -> bool:
    parts = path.relative_to(root).parts
    if "data" in parts:
        index = parts.index("data")
        if index + 1 < len(parts) and parts[index + 1] == "missions":
            return True
    return False
