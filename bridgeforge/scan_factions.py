"""Faction checks: known lists, ship roles, personality ids, known tags, carrier rework gap."""
from __future__ import annotations

import csv
import re
from .models import ScanResult
from pathlib import Path
from .scan_classfile import NON_MOD_JAR_DIRS, _iter_jar_class_files, _parse_class_file
from .scan_common import BLACK_HOLE_HINT_PATTERN, FACTION_SPECIAL_ROLE_KEYS, OBSOLETE_FIGHTER_ROLE_NAMES, _relative
from .scan_content import _vanilla_faction_ids
from .scan_javatext import _blank_java_comments
from .scan_json import _csv_header, _load_lenient_json_file, _read_csv_rows, _wing_ids_set


def _scan_faction_known_lists(root: Path, result: ScanResult, vanilla_core: Path | None) -> None:
    """A new faction missing known* lists gets silently empty markets/fleets since 0.8a."""
    faction_dir = root / "data" / "world" / "factions"
    if not faction_dir.is_dir():
        return
    vanilla_ids: set[str] | None = _vanilla_faction_ids(vanilla_core) if vanilla_core is not None else None
    for path in sorted(faction_dir.glob("*.faction")):
        data = _load_lenient_json_file(path)
        if not isinstance(data, dict):
            # Never skip silently: an unchecked faction file must not read as a clean one.
            result.add(
                id="faction-file-unparsed",
                category="factions",
                severity="medium",
                classification="UNKNOWN",
                confidence="DETERMINISTIC",
                explanation="BridgeForge's legacy-JSON parser could not read this faction file, so the known-lists check did not run on it. This is not proof the game rejects the file; inspect it manually.",
                file=_relative(root, path),
            )
            continue
        faction_id = data.get("id")
        if not isinstance(faction_id, str) or not faction_id:
            continue
        if vanilla_ids is not None and faction_id in vanilla_ids:
            continue
        missing = [key for key in ("knownShips", "knownWeapons", "knownFighters") if not data.get(key)]
        if not missing:
            continue
        ship_roles = data.get("shipRoles")
        role_variant_count = 0
        if isinstance(ship_roles, dict):
            for block in ship_roles.values():
                if isinstance(block, dict):
                    role_variant_count += sum(1 for key in block if key not in FACTION_SPECIAL_ROLE_KEYS)
        evidence = [f"missing:{','.join(missing)}", f"shipRoles-present:{isinstance(ship_roles, dict)}", f"role-variant-keys:{role_variant_count}"]
        if vanilla_ids is None:
            evidence.append("vanilla-faction-list:unavailable; merge-fragment exemption could not be checked")
        # Zorg18 (2026-09-14): no markets, no shipRoles, fleets assembled member by member. Nothing reads
        # its known lists, so HIGH overstated it. Keep HIGH whenever market use can't be ruled out.
        market_use = _faction_market_evidence(root, faction_id)
        compositions = data.get("fleetCompositions") if isinstance(data.get("fleetCompositions"), dict) else {}
        fleet_ships = sum(len(c["ships"]) for c in compositions.values() if isinstance(c, dict) and isinstance(c.get("ships"), dict))
        unused = role_variant_count == 0 and fleet_ships == 0 and market_use == "none"
        evidence.append(f"market-evidence:{market_use}")
        if unused:
            # Nothing to derive lists from and nothing reads them: a note, not work (hvb_hostile in Kadur Remnant,
            # The Exalted and Vayra's Ship Pack, a utility faction spawner code hands whole fleets; 2026-09-30).
            evidence.append("nothing-reads-lists")
        result.add(
            id="faction-known-lists-missing",
            category="factions",
            severity="low" if unused else "high",
            classification="SAFE" if unused else "REVIEW",
            confidence="HIGH",
            explanation=(
                "This faction is missing one or more of knownShips/knownWeapons/knownFighters. Since 0.8a, "
                "market stocking (BaseSubmarketPlugin.addWeapons/addFighters/addShips) and fleet generation "
                "(FleetFactoryV3) only draw from a faction's known lists, so a missing list silently produces "
                "empty market stock or empty fleets instead of an error."
                + (" This faction has no shipRoles and no market was found in its data or sources, so nothing obvious reads the lists; add them if it gains markets, FleetFactoryV3 fleets or a Nexerelin config." if unused else "")
            ),
            file=_relative(root, path),
            evidence=evidence,
        )


def _faction_market_evidence(root: Path, faction_id: str) -> str:
    """'found' when the faction owns or configures a market, 'none' when sources rule it out, else 'unknown'."""
    quoted = f'"{faction_id}"'
    econ = root / "data" / "campaign" / "econ"
    for path in econ.rglob("*.json") if econ.is_dir() else []:
        data = _load_lenient_json_file(path)
        if isinstance(data, dict) and data.get("faction") == faction_id:
            return "found"
    if (root / "data" / "config" / "exerelinFactionConfig" / f"{faction_id}.json").is_file():
        return "found"
    sources = [path for path in root.rglob("*.java") if "disabled_files" not in path.relative_to(root).parts]
    for path in sources:
        try:
            text = _blank_java_comments(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if quoted in text and re.search(r"\b(?:setFactionId|createMarket|addMarket|createEmptyFleet|createFleet)\s*\(", text):
            if re.search(r"\b(?:setFactionId|createMarket|addMarket)\s*\(", text):
                return "found"
    # Shipped jars often differ from bundled sources, so the bytecode is checked too: a class holding the
    # faction id as a string constant and calling a market-ownership method.
    has_classes = False
    for _jar, _member, data in _iter_jar_class_files(root):
        has_classes = True
        info = _parse_class_file(data)
        if info is None or faction_id not in (info.string_constants or set()):
            continue
        if {"setFactionId", "createMarket", "addMarket"} & set(info.utf8_values or ()):
            return "found"
    # Compiled code without any sources could still build markets in ways we can't read.
    return "unknown" if has_classes and not sources else "none"


def _scan_shiproles(root: Path, result: ScanResult, vanilla_core: Path | None) -> None:
    """0.8a carrier rework: shipRoles keys must be variant ids, not wing ids or fighter-role names."""
    faction_dir = root / "data" / "world" / "factions"
    if not faction_dir.is_dir():
        return
    wing_ids = _wing_ids_set(root / "data" / "hulls" / "wing_data.csv")
    if vanilla_core is not None:
        wing_ids |= _wing_ids_set(vanilla_core / "data" / "hulls" / "wing_data.csv")
    for path in sorted(faction_dir.glob("*.faction")):
        data = _load_lenient_json_file(path)
        if not isinstance(data, dict):
            continue
        ship_roles = data.get("shipRoles")
        if not isinstance(ship_roles, dict):
            continue
        relative = _relative(root, path)
        for role_name, block in sorted(ship_roles.items()):
            if role_name.lower() in OBSOLETE_FIGHTER_ROLE_NAMES:
                result.add(
                    id="shiproles-obsolete-fighter-role",
                    category="factions",
                    severity="medium",
                    classification="REVIEW",
                    confidence="HIGH",
                    explanation="This shipRoles block name (interceptor/fighter/bomber) was removed in the 0.8a carrier rework; its entries are not used by 0.98a fleet generation.",
                    file=relative,
                    evidence=[f"role:{role_name}"],
                )
            if not isinstance(block, dict):
                continue
            for key in sorted(block):
                if key in FACTION_SPECIAL_ROLE_KEYS:
                    continue
                if key.endswith("_wing") or key in wing_ids:
                    result.add(
                        id="shiproles-wing-id",
                        category="factions",
                        severity="critical",
                        classification="MANUAL",
                        confidence="HIGH",
                        explanation="0.98a resolves every shipRoles entry through a variant-only lookup. This key looks like a fighter wing id (the pre-0.8a convention), which is fatal at load rather than being ignored.",
                        file=relative,
                        evidence=[f"role:{role_name}", f"key:{key}"],
                    )


def _scan_carrier_rework_gap(root: Path, result: ScanResult) -> None:
    """ship_data/wing_data structural symptoms of the 0.8a carrier rework."""
    ship_data_path = root / "data" / "hulls" / "ship_data.csv"
    wing_data_path = root / "data" / "hulls" / "wing_data.csv"
    ship_rows: list[dict[str, str]] = []
    if ship_data_path.is_file():
        header = _csv_header(ship_data_path)
        if header is not None:
            normalized = [cell.strip().lower() for cell in header]
            if "fighter bays" not in normalized:
                result.add(
                    id="ship-data-missing-fighter-bays-column",
                    category="hulls",
                    severity="high",
                    classification="REVIEW",
                    confidence="DETERMINISTIC",
                    explanation="data/hulls/ship_data.csv has no 'fighter bays' column. This mod predates the 0.8a carrier rework; every carrier hull will silently load with 0 fighter bays.",
                    file=_relative(root, ship_data_path),
                    evidence=[f"columns:{len(header)}"],
                )
        ship_rows = _read_csv_rows(ship_data_path) or []

    variant_wings_by_hull: dict[str, bool] = {}
    variants_root = root / "data" / "variants"
    if variants_root.is_dir():
        for path in variants_root.rglob("*.variant"):
            data = _load_lenient_json_file(path)
            if not isinstance(data, dict):
                continue
            hull_id = data.get("hullId")
            if not isinstance(hull_id, str) or not hull_id:
                continue
            wings = data.get("wings")
            has_wings = isinstance(wings, list) and len(wings) > 0
            variant_wings_by_hull[hull_id] = variant_wings_by_hull.get(hull_id, False) or has_wings

    if wing_data_path.is_file():
        header = _csv_header(wing_data_path)
        if header is not None:
            normalized = [cell.strip().lower() for cell in header]
            if "role desc" not in normalized:
                result.add(
                    id="wing-data-missing-role-desc-column",
                    category="hulls",
                    severity="critical",
                    classification="MANUAL",
                    confidence="DETERMINISTIC",
                    explanation="data/hulls/wing_data.csv has no 'role desc' column, which the 0.98a loader requires; the file fails to load.",
                    file=_relative(root, wing_data_path),
                    evidence=[f"columns:{len(header)}"],
                )
        for index, row in enumerate(_read_csv_rows(wing_data_path) or [], start=2):
            wing_id = (row.get("id") or "").strip()
            if not wing_id or wing_id.startswith("#"):
                continue
            # `wing-role-assault-removed` retired 2026-09-14: ASSAULT is still a valid RC8 WingRole, and
            # rewriting it to FIGHTER silently changed the wing's AI behaviour.
            op_cost = (row.get("op cost") or "").strip()
            if not op_cost:
                result.add(
                    id="wing-op-cost-blank",
                    category="hulls",
                    severity="medium",
                    classification="REVIEW",
                    confidence="DETERMINISTIC",
                    explanation="This wing_data.csv row has a blank 'op cost' value.",
                    file=_relative(root, wing_data_path),
                    evidence=[f"line:{index}", f"wing:{wing_id}"],
                )

    for row in ship_rows:
        hull_id = (row.get("id") or "").strip()
        if not hull_id or hull_id.startswith("#"):
            continue
        hints = (row.get("hints") or "").upper()
        if "CARRIER" not in hints:
            continue
        bays_raw = (row.get("fighter bays") or "").strip()
        try:
            bays = int(float(bays_raw)) if bays_raw else 0
        except ValueError:
            bays = 0
        has_wings = variant_wings_by_hull.get(hull_id, False)
        if bays <= 0 and not has_wings:
            result.add(
                id="carrier-without-bays-or-wings",
                category="hulls",
                severity="high",
                classification="REVIEW",
                confidence="HIGH",
                explanation="This hull is tagged CARRIER in ship_data.csv hints but has 0/absent fighter bays and none of its variants declare a non-empty wings array, so it cannot deploy fighters.",
                file=_relative(root, ship_data_path),
                evidence=[f"hull:{hull_id}", f"fighter-bays:{bays_raw or '0'}", f"variants-with-wings:{has_wings}"],
            )


def _scan_black_hole_flag(root: Path, result: ScanResult) -> None:
    planets_path = root / "data" / "config" / "planets.json"
    data = _load_lenient_json_file(planets_path)
    if not isinstance(data, dict):
        return
    for type_id, spec in sorted(data.items()):
        if not isinstance(spec, dict) or not spec.get("isStar") or spec.get("isBlackHole"):
            continue
        name = str(spec.get("name") or "")
        texture = str(spec.get("texture") or "")
        if not (BLACK_HOLE_HINT_PATTERN.search(type_id) or BLACK_HOLE_HINT_PATTERN.search(name) or BLACK_HOLE_HINT_PATTERN.search(texture)):
            continue
        result.add(
            id="black-hole-type-missing-flag",
            category="campaign",
            severity="low",
            classification="REVIEW",
            confidence="HIGH",
            explanation="This star type's id/name/texture indicates a black hole, but isBlackHole:true is not set, so 0.98a renders it as a plain star instead of a black hole.",
            file=_relative(root, planets_path),
            evidence=[f"type:{type_id}", f"name:{name}", f"texture:{texture}"],
        )


# Personality ids RC8 defines (starsector-core data/characters/personalities.csv; 0.7.2 already lacked
# the legacy ones). 0.6.x also had cowardly/suicidal/fearless: setPersonality() with one of those now
# leaves the officer's personality null, and the ship AI built on deploy NPEs in Ship.getPersonality ->
# Fatal dialog (live run SK13-1d, SEEKER's missions).
VANILLA_PERSONALITY_IDS = frozenset({"timid", "cautious", "steady", "aggressive", "reckless"})


LEGACY_PERSONALITY_IDS = {"cowardly": "timid", "suicidal": "reckless", "fearless": "reckless"}


_SOURCE_SET_PERSONALITY = re.compile(r'\bsetPersonality\s*\(\s*"([^"\\]+)"\s*\)')


def _mod_personality_ids(root: Path) -> set[str]:
    """Ids the mod adds itself: data/characters/personalities.csv merges into vanilla's by id (Vacuum does this)."""
    path = root / "data" / "characters" / "personalities.csv"
    try:
        with path.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
            return {(row.get("id") or "").strip() for row in csv.DictReader(handle) if (row.get("id") or "").strip()}
    except OSError:
        return set()


def _scan_personality_ids(root: Path, result: ScanResult) -> None:
    valid = VANILLA_PERSONALITY_IDS | _mod_personality_ids(root)
    explanation = (
        "This code gives an officer a personality id that Starsector 0.98a does not define (only timid, cautious, "
        "steady, aggressive and reckless exist, plus any this mod adds in data/characters/personalities.csv). The "
        "officer's personality is left empty, and the game crashes with a Fatal dialog when that ship deploys. "
        "SEEKER's missions used 0.6-era 'suicidal'/'fearless'. Use a valid id (suggested: "
        + ", ".join(f"{old}->{new}" for old, new in LEGACY_PERSONALITY_IDS.items()) + ")."
    )
    for jar, member, data in _iter_jar_class_files(root):
        info = _parse_class_file(data)
        if info is None or "setPersonality" not in info.utf8_values:
            continue
        # Bytecode can't tie a literal to its call, so only exact legacy ids count (not briefing text).
        unknown = sorted(value for value in info.string_constants if value in LEGACY_PERSONALITY_IDS and value not in valid)
        if unknown:
            result.add(id="personality-id-unknown", category="scripts", severity="high", classification="MANUAL", confidence="HIGH", explanation=explanation, file=f"{_relative(root, jar)}!{member}", evidence=[f"personality:{value}" for value in unknown])
    for source in sorted(root.rglob("*.java")):
        if any(part in NON_MOD_JAR_DIRS or part.startswith("src-decompiled") for part in source.relative_to(root).parts):
            continue
        try:
            text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        unknown = sorted({match.group(1) for match in _SOURCE_SET_PERSONALITY.finditer(text) if match.group(1) not in valid})
        if unknown:
            result.add(id="personality-id-unknown", category="scripts", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation=explanation, file=_relative(root, source), evidence=[f"personality:{value}" for value in unknown])


def _scan_faction_trait_weight_legacy_personality_ids(root: Path, result: ScanResult) -> None:
    """A `.faction`'s `traits.<role>` block weights personality ids for random officer generation.

    Real case (Zorg18, found 2026-09-21 investigating a report's own "flagged for a future pass"
    note): `zorg.faction`'s `traits.captain` weights `cowardly`/`suicidal`/`fearless` (0.6-era ids,
    `LEGACY_PERSONALITY_IDS`) alongside the four real RC8 ones - the exact same crash class as
    `personality-id-unknown` (SK13-1d: an officer drawn with an unrecognized id gets a null
    personality, Fatal dialog on deploy), just reached through faction-level random generation
    instead of a hard-coded `setPersonality()` call. `"traits"` is not dead legacy content: no
    vanilla faction file uses the key (checked directly), but RC8's own `Faction`/`SpecStore`
    classes reference the string `"traits"` in their constant pool (javap, 2026-09-21) - it is read,
    just never populated by any vanilla faction.
    """
    faction_dir = root / "data" / "world" / "factions"
    if not faction_dir.is_dir():
        return
    valid = VANILLA_PERSONALITY_IDS | _mod_personality_ids(root)
    explanation = (
        "This faction's traits block weights a personality id that Starsector 0.98a does not define "
        "(only timid, cautious, steady, aggressive and reckless exist, plus any this mod adds in "
        "data/characters/personalities.csv). An officer randomly generated with this id gets a null "
        "personality, and the game crashes with a Fatal dialog when that officer's ship deploys - the "
        "same crash class as personality-id-unknown, reached through faction generation instead of a "
        "hard-coded setPersonality() call. Rename the key (suggested: "
        + ", ".join(f"{old}->{new}" for old, new in LEGACY_PERSONALITY_IDS.items()) + ")."
    )
    for path in sorted(faction_dir.glob("*.faction")):
        data = _load_lenient_json_file(path)
        if not isinstance(data, dict):
            continue
        traits = data.get("traits")
        if not isinstance(traits, dict):
            continue
        relative = _relative(root, path)
        for role_name, block in sorted(traits.items()):
            if not isinstance(block, dict):
                continue
            unknown = sorted(key for key in block if key in LEGACY_PERSONALITY_IDS and key not in valid)
            if unknown:
                result.add(
                    id="faction-trait-weight-legacy-personality-id",
                    category="factions",
                    severity="high",
                    classification="MANUAL",
                    confidence="DETERMINISTIC",
                    explanation=explanation,
                    file=relative,
                    evidence=[f"role:{role_name}", *(f"personality:{value}" for value in unknown)],
                )


_KNOWN_LISTS = {"knownShips": ("data/hulls/ship_data.csv",), "priorityShips": ("data/hulls/ship_data.csv",),
                "knownWeapons": ("data/weapons/weapon_data.csv",), "knownFighters": ("data/hulls/wing_data.csv",)}


def _mod_items(root: Path, key: str) -> tuple[set[str], set[str]]:
    """(ids, tags) of the mod's own hulls, weapons or wings for one known-list key."""
    import csv as _csv
    import io as _io

    ids: set[str] = set()
    tags: set[str] = set()
    for rel in _KNOWN_LISTS[key]:
        path = root / rel
        if not path.is_file():
            continue
        try:
            for row in _csv.DictReader(_io.StringIO(path.read_text(encoding="utf-8-sig", errors="replace"))):
                item = (row.get("id") or "").strip()
                if item and not item.startswith("#"):
                    ids.add(item)
                    tags |= {t.strip() for t in (row.get("tags") or "").split(",") if t.strip()}
        except _csv.Error:
            continue
    return ids, tags


def _csv_tags(path: Path) -> set[str]:
    import csv as _csv
    import io as _io

    if not path.is_file():
        return set()
    try:
        rows = _csv.DictReader(_io.StringIO(path.read_text(encoding="utf-8-sig", errors="replace")))
        return {t.strip() for r in rows for t in (r.get("tags") or "").split(",") if t.strip()}
    except _csv.Error:
        return set()


def _scan_faction_known_tags(root: Path, result: ScanResult, vanilla_core: Path | None) -> None:
    """A faction's knownShips/priorityShips/knownWeapons/knownFighters names a tag no hull/weapon/wing of the mod,
    RC8 or a declared dependency carries: the faction then knows none of those items, so its markets cannot sell them
    and its fleets cannot field them. Exigency's knownShips {tags: [exigency_bp]} matched no hull (only its wings were
    tagged), so its ships could not be bought (owner report 2026-10-04)."""
    if vanilla_core is None:
        return
    factions = sorted((root / "data" / "world" / "factions").glob("*.faction")) if (root / "data" / "world" / "factions").is_dir() else []
    if not factions:
        return
    bases = [root, vanilla_core, *[Path(d) for d in result.migration_context.get("dependency_roots") or []]]
    carried = {key: set().union(*(_csv_tags(b / rel) for b in bases for rel in files)) for key, files in _KNOWN_LISTS.items()}
    # Skins carry tags too: RC8's XIV_bp and heg_aux_bp are only on data/hulls/skins/*.skin (dominator_xiv.skin).
    for base in bases:
        skins = base / "data" / "hulls" / "skins"
        for skin in sorted(skins.glob("*.skin")) if skins.is_dir() else []:
            spec = _load_lenient_json_file(skin)
            if isinstance(spec, dict) and isinstance(spec.get("tags"), list):
                tags = {t for t in spec["tags"] if isinstance(t, str)}
                carried["knownShips"] |= tags
                carried["priorityShips"] |= tags
    # A tag RC8's own factions list in the same block is harmless however little it matches (hegemony.faction's
    # knownWeapons tag "hegemony", omega.faction's knownFighters tag "omega"; their explicit lists do the work).
    vanilla_dir = vanilla_core / "data" / "world" / "factions"
    for vanilla in sorted(vanilla_dir.glob("*.faction")) if vanilla_dir.is_dir() else []:
        spec = _load_lenient_json_file(vanilla)
        for key in _KNOWN_LISTS:
            block = spec.get(key) if isinstance(spec, dict) else None
            if isinstance(block, dict) and isinstance(block.get("tags"), list):
                carried[key] |= {t for t in block["tags"] if isinstance(t, str)}
    for path in factions:
        spec = _load_lenient_json_file(path)
        if not isinstance(spec, dict):
            continue
        for key in _KNOWN_LISTS:
            block = spec.get(key)
            tags = block.get("tags") if isinstance(block, dict) else None
            # A dead tag only costs something when the block gives the faction none of this mod's own items (by id or
            # by a tag a mod item carries): 28 queue mods held 156 findings, mostly dead fighter/weapon tags beside
            # lists that already cover the mod's items (2026-10-05). Exigency's knownShips [exigency_bp, base_bp]
            # still counts: base_bp matched only vanilla hulls, none of Exigency's.
            own_ids, own_tags = _mod_items(root, key)
            listed = {v for k, vals in (block or {}).items() if k != "tags" and isinstance(vals, list) for v in vals if isinstance(v, str)} if isinstance(block, dict) else set()
            if own_ids and (listed & own_ids or any(isinstance(t, str) and t in own_tags for t in tags or [])):
                continue
            # Otherwise a dead tag matters when it looks like the mod's own (kadur_theocracy beside kadur_* tags: a
            # renamed tag) or the list gives the faction nothing at all. A tag naming another mod's content (Vayra's
            # Sector lists mayasura_bp, kazeron, westernesse: optional integration) is not flagged (2026-10-05).
            yields = bool(listed) or any(isinstance(t, str) and t in carried[key] for t in tags or [])
            own_prefixes = {n.split("_")[0].lower() for n in own_ids | own_tags if "_" in n}
            for tag in tags or []:
                if not (isinstance(tag, str) and tag.strip() and tag not in carried[key]):
                    continue
                if yields and tag.split("_")[0].lower() not in own_prefixes:
                    continue
                if isinstance(tag, str) and tag.strip() and tag not in carried[key]:
                    result.add(
                        id="faction-known-tag-unmatched",
                        category="factions",
                        severity="high",
                        classification="REVIEW",
                        confidence="HIGH",
                        explanation=(f"{key} lists tag '{tag}', but no {'hull' if 'Ships' in key else 'weapon' if 'Weapons' in key else 'wing'} "
                                     "in this mod, RC8 or a declared dependency carries it, so the faction knows none of "
                                     "them: its markets cannot sell them and its fleets cannot field them (Exigency's "
                                     "exigency_bp was on its wings only, 2026-10-04)."),
                        file=_relative(root, path),
                        evidence=[f"list:{key}", f"tag:{tag}"],
                    )
