"""Content graph checks: assets, wing roles, configured class integrity, procgen rows, rules conditions."""
from __future__ import annotations

import csv
import json
import re
from .models import ScanResult
from pathlib import Path
from .scan_campaign import _declared_spec_ids
from .scan_common import _relative
from .scan_javatext import _blank_java_comments
from .scan_json import _csv_first_column_ids, _emit_json_tolerance_findings, _json_encoding_finding, _json_trailing_data_finding, _load_lenient_json_file, _parse_json, _repair_missing_commas, _unverified_json_syntax_finding
from .scan_missions import _is_mission_source


def _scan_assets(root: Path, result: ScanResult) -> None:
    for path in root.rglob("*.json"):
        if path.name == "mod_info.json":
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as exc:
            _json_encoding_finding(result, "assets", _relative(root, path), exc)
            continue
        except OSError as exc:
            result.add(id="unreadable-json", category="assets", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation=f"JSON could not be read: {exc}", file=_relative(root, path))
            continue
        try:
            _, tolerances = _parse_json(text)
        except json.JSONDecodeError as exc:
            repaired = _repair_missing_commas(text)
            if repaired:
                result.add(id="json-missing-comma", category="assets", severity="high", classification="REVIEW", confidence="DETERMINISTIC",
                           explanation="Two values sit on consecutive lines with no comma between them. Starsector's org.json loader rejects that (\"Expected a ',' or ']'\"), so the file fails to load. With a comma at the end of each listed line the file parses as RC8 reads it.",
                           file=_relative(root, path), evidence=[f"line:{n}" for n in repaired[1]])
            else:
                _unverified_json_syntax_finding(result, "assets", _relative(root, path), exc)
        else:
            _emit_json_tolerance_findings(result, "assets", _relative(root, path), tolerances)
    # Starsector's other JSON-like files: only the trailing-data result is reported here (content
    # after the root never loads); their other tolerances are routine and checked elsewhere.
    for suffix in ("*.faction", "*.ship", "*.skin", "*.variant", "*.wpn", "*.proj", "*.system"):
        for path in root.rglob(suffix):
            try:
                _, tolerances = _parse_json(path.read_text(encoding="utf-8-sig"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            if "trailing-data" in tolerances:
                _json_trailing_data_finding(result, "assets", _relative(root, path), tolerances)
    for path in root.rglob("*.csv"):
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = csv.reader(handle)
                header = next(rows, [])
                if not header or not any(cell.strip() for cell in header):
                    raise ValueError("CSV has no header row")
                for line_number, row in enumerate(rows, start=2):
                    if len(row) <= len(header) or not any(cell.strip() for cell in row):
                        continue
                    if row[0].lstrip().startswith("#"):
                        continue  # a comment row Starsector skips (Industrial Evolution's printing_whitelist.csv notes)
                    # Content beyond the header is a spilled row (loads into the wrong columns). Only
                    # empty trailing cells (spreadsheet padding; Mirfak's hull_mods rows reach 14,726
                    # cells) are ignored by Starsector but rejected by strict tools; that is SAFE to trim.
                    spilled = any(cell.strip() for cell in row[len(header):])
                    result.add(
                        id="csv-row-extra-columns",
                        category="assets",
                        severity="high" if spilled else "low",
                        classification="MANUAL" if spilled else "SAFE",
                        confidence="DETERMINISTIC",
                        explanation=(
                            "A CSV row has more fields than its header. Live revival testing showed that spilled description and hullmod rows can pass superficial parsing but load into the wrong columns; restore the intended row structure from authoritative data."
                            if spilled else
                            "A CSV row has empty cells beyond its header (spreadsheet padding). Starsector ignores them, but strict tools such as Project Go reject the file. `fix csv-row-extra-columns` trims them without changing any value."
                        ),
                        file=_relative(root, path),
                        evidence=[f"line:{line_number}", f"header-columns:{len(header)}", f"row-columns:{len(row)}", *[f"extra:{value}" for value in row[len(header):len(header) + 3]]],
                    )
        except UnicodeDecodeError as exc:
            result.add(id="csv-encoding-unverified", category="assets", severity="medium", classification="REVIEW", confidence="DETERMINISTIC", explanation=f"CSV could not be decoded as UTF-8 ({exc}). Encoding is separate from CSV structure; verify the target loader before conversion.", file=_relative(root, path))
        except (OSError, csv.Error, ValueError) as exc:
            result.add(id="invalid-csv", category="assets", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation=f"CSV could not be read: {exc}", file=_relative(root, path))
    _scan_wing_roles(root, result)
    _scan_content_graph(root, result)


def _scan_wing_roles(root: Path, result: ScanResult) -> None:
    """Validate the role field that makes a fighter wing loadable by the combat layer."""
    path = root / "data" / "hulls" / "wing_data.csv"
    if not path.is_file():
        return
    relative = _relative(root, path)
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except (OSError, UnicodeDecodeError, csv.Error):
        return
    # RC8's com.fs.starfarer.api.loading.WingRole enum (javap, 2026-09-14): BOMBER, FIGHTER, INTERCEPTOR,
    # ASSAULT, SUPPORT. ASSAULT was wrongly treated as removed; Vacuum's ASSAULT wings load live (VAC-R003).
    allowed = {"FIGHTER", "INTERCEPTOR", "BOMBER", "ASSAULT", "SUPPORT"}
    evidence: list[dict[str, str | int]] = []
    for index, row in enumerate(rows, start=2):
        wing_id = (row.get("id") or "").strip()
        if not wing_id or wing_id.startswith("#"):
            continue
        role = (row.get("role") or "").strip().upper()
        evidence.append({"line": index, "id": wing_id, "role": role})
        if not role:
            result.add(id="fighter-wing-role-missing", category="fighters", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation="A fighter wing has no role in data/hulls/wing_data.csv. Starsector requires a recognized role before the wing can load; choose the intended fighter, interceptor, bomber, or support behavior and runtime-test the wing.", file=relative, evidence=[f"line:{index}", f"wing:{wing_id}"])
        elif role not in allowed:
            result.add(id="fighter-wing-role-invalid", category="fighters", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation="A fighter wing role is not recognized by the target profile. Use a documented role and verify combat behavior; BridgeForge will not guess the intended tactical role.", file=relative, evidence=[f"line:{index}", f"wing:{wing_id}", f"role:{role}", f"allowed:{','.join(sorted(allowed))}"])
    result.migration_context["fighter_wing_roles"] = evidence


def _registered_csv_ids(path: Path) -> set[str] | None:
    if not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = csv.reader(handle)
            header = next(rows, [])
            normalized = [cell.strip().lower() for cell in header]
            if "id" not in normalized:
                return None
            id_index = normalized.index("id")
            registered: set[str] = set()
            for row in rows:
                first_value = next((cell.strip() for cell in row if cell.strip()), "")
                if first_value.startswith("#") or id_index >= len(row):
                    continue
                identifier = row[id_index].strip()
                if identifier:
                    registered.add(identifier)
            return registered
    except (OSError, UnicodeDecodeError, csv.Error):
        return None


def _scan_content_graph(root: Path, result: ScanResult) -> None:
    """Check local spec registrations and value kinds without inferring repairs."""
    weapons_root = root / "data" / "weapons"
    weapon_specs = _declared_spec_ids(weapons_root, "*.wpn", "id")
    registered_weapons = _registered_csv_ids(weapons_root / "weapon_data.csv")
    if registered_weapons is not None:
        for identifier, path in sorted(weapon_specs.items()):
            if identifier in registered_weapons:
                continue
            result.add(
                id="local-weapon-spec-unregistered",
                category="assets",
                severity="high",
                classification="REVIEW",
                confidence="DETERMINISTIC",
                explanation="A local .wpn file has no matching id row in this mod's weapon_data.csv. It may be an intentional override registered by another provider, unused content, or a load error; inspect the merged target registry and boot log before adding data or deleting the spec.",
                file=_relative(root, path),
                evidence=[f"weapon:{identifier}", "local-registration:missing"],
            )

    variants_root = root / "data" / "variants"
    variant_ids = set(_declared_spec_ids(variants_root, "*.variant", "variantId"))
    misplaced: list[dict[str, str]] = []
    for path in sorted(variants_root.glob("*.variant")):
        try:
            data, _ = _parse_json(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        weapon_groups = data.get("weaponGroups", [])
        if not isinstance(weapon_groups, list):
            continue
        for group_index, group in enumerate(weapon_groups):
            if not isinstance(group, dict) or not isinstance(group.get("weapons"), dict):
                continue
            for slot, assigned in sorted(group["weapons"].items()):
                if not isinstance(assigned, str) or assigned not in variant_ids or assigned in weapon_specs:
                    continue
                evidence = {
                    "file": _relative(root, path),
                    "slot": str(slot),
                    "variant": assigned,
                    "group": str(group_index),
                }
                misplaced.append(evidence)
                result.add(
                    id="variant-id-in-weapon-slot",
                    category="assets",
                    severity="critical",
                    classification="MANUAL",
                    confidence="DETERMINISTIC",
                    explanation="A weaponGroups assignment names a local ship variant rather than a local weapon spec. This caused a boot-fatal module-loading error in a real revival; verify that the hull slot is a station module and move the assignment to the target version's modules structure only when the hull evidence confirms it.",
                    file=evidence["file"],
                    evidence=[f"group:{group_index}", f"slot:{slot}", f"variant:{assigned}"],
                )

    result.migration_context["content_graph"] = {
        "local_weapon_specs": sorted(weapon_specs),
        "locally_registered_weapons": sorted(registered_weapons) if registered_weapons is not None else None,
        "local_variants": sorted(variant_ids),
        "variant_ids_in_weapon_slots": misplaced,
        "limitation": "Local registration and value-kind evidence does not establish merged target/provider ownership or intended balance.",
    }


def _source_class_index(root: Path) -> dict[str, str]:
    names: dict[str, str] = {}
    for path in root.rglob("*.java"):
        if "disabled_files" in path.relative_to(root).parts:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        package = re.search(r"^\s*package\s+([\w.]+)\s*;", text, re.M)
        # Comments blanked: "// Only class allowed to import ..." came before Flu-X NexCompat's declaration.
        declared = re.search(r"\b(?:public\s+)?(?:class|interface|enum)\s+(\w+)", _blank_java_comments(text, strings=True))
        if package and declared:
            names[f"{package.group(1)}.{declared.group(1)}"] = _relative(root, path)
    return names


def _scan_configured_class_integrity(root: Path, result: ScanResult) -> None:
    local_classes = _source_class_index(root)
    references: set[str] = set()
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".csv", ".json", ".faction", ".ship", ".variant", ".system"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        references.update(re.findall(r"\bdata(?:\.[A-Za-z_$][\w$]*)+", text))
    # Loose .java under data/ is compiled by the game at load (Janino), so it needs no jar: old mods such
    # as Gekelonians (0.53) ship only loose scripts and were all reported MANUAL (2026-09-14 batch).
    loose = {name for name, relative in local_classes.items() if str(relative).replace("\\", "/").startswith("data/")}
    source_only = sorted(set(local_classes) & references - result.compiled_class_names - loose)
    packaged = sorted(references & result.compiled_class_names)
    unresolved = sorted(references - set(local_classes) - result.compiled_class_names)
    entrypoint_sources = sorted(local_classes[name] for name in set(local_classes) & references)
    result.migration_context["configured_class_integrity"] = {
        "source_class_names": sorted(local_classes),
        "configured_references": sorted(references),
        "source_only": source_only,
        "loose_scripts": sorted(loose & references - result.compiled_class_names),
        "packaged": packaged,
        "unresolved": unresolved,
        "configured_entrypoint_sources": entrypoint_sources,
    }
    for finding in result.findings:
        if finding.file in entrypoint_sources and finding.id in {"runtime-placeholder-unsupported-operation", "campaign-spawn-registration-disabled", "missing-custom-ui-button-pressed-callback", "legacy-custom-dialog-delegate-signature"}:
            finding.evidence.append("reachability: configured-entrypoint")
        elif finding.id == "runtime-placeholder-unsupported-operation":
            finding.evidence.append("reachability: active-source-unconfigured")
    if source_only:
        result.add(id="configured-source-class-missing-from-jar", category="bytecode", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation="Mod data references active local source classes that are absent from every scanned JAR. Compile/package the active sources before runtime testing; this finding does not claim that every unresolved configured class belongs to this mod.", evidence=source_only)


def _scan_content_id_renamed_by_provider(root: Path, result: ScanResult, vanilla_core: Path | None, provider_roots: list[Path] | None) -> None:
    """An industry id the mod's code asks for that no installed table defines while a close sibling id exists (ROADMAP 60d;
    Tritachyon asked for BOGGLED_AI_STATION, Terraforming & Station Construction 10.0.9 calls it BOGGLED_REMNANT_STATION,
    New Game stopped in onNewGame). Only the vanilla table, the mod's own and its declared providers' are consulted."""
    from .provider_renamed_ids import renamed_industry_ids

    provider_dirs: list[Path] = []
    if provider_roots:
        from .java_toolchain import declared_dependencies
        from .substitutes import provider_index

        deps = set(declared_dependencies(root))
        provider_dirs = [Path(p.path) for p in provider_index([Path(r) for r in provider_roots], exclude=root) if p.mod_id in deps]
    hits = renamed_industry_ids(root, vanilla_core, provider_dirs)
    if not hits:
        return
    result.add(
        id="content-id-renamed-by-provider",
        category="campaign",
        severity="high",
        classification="REVIEW",
        confidence="MEDIUM",
        explanation="Code in this mod names industry id(s) " + ", ".join(h["used"] for h in hits) + " that no industries.csv this scan can see "
                    "defines, while a close id does (" + ", ".join(f"{h['used']} -> {h['suggestion']}" for h in hits) + "). A newer library or "
                    "RC8 may have renamed it; addIndustry then fails at New Game. Match is by name similarity only, so compare the two rows "
                    "(and the older provider copy, when you have one) before changing the id. Hull mod, commodity and condition ids are not checked.",
        file="data/campaign/industries.csv",
        evidence=[f"{h['used']}->{h['suggestion']} ratio {h['ratio']}" for h in hits] + [f"used-in:{w}" for h in hits for w in h["where"]],
    )


def _scan_star_type_undefined(root: Path, result: ScanResult, vanilla_core: Path | None) -> None:
    """A `star_*` type named in the mod's code that neither the mod's planets.json nor RC8's defines. StarSystem.initStar
    then builds a planet from a null spec: NullPointerException 'PlanetSpec.getPlanetType() because <parameter1> is null'
    (Ironclads' SystemComposer asked for 0.7's star_red and star_blue, which RC8 renamed star_red_dwarf/star_blue_giant;
    GRP10Q-20261005). Needs --vanilla-core: without RC8's planets.json nothing is claimed."""
    if vanilla_core is None:
        return
    defined: set[str] = set()
    for path in (root / "data" / "config" / "planets.json", vanilla_core / "data" / "config" / "planets.json"):
        data = _load_lenient_json_file(path)
        if isinstance(data, dict):
            defined.update(data)
    if not defined:
        return
    used: dict[str, list[str]] = {}
    for source in root.rglob("*.java"):
        try:
            text = source.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # Comments are not code: Neutrino's Exelion.java names star_blackhole only in a commented-out initStar (2026-10-11).
        for literal in set(re.findall(r'"(star_[a-z0-9_]+)"', _blank_java_comments(text))):
            if literal not in defined:
                used.setdefault(literal, []).append(_relative(root, source))
    if not used:
        return
    result.add(
        id="star-type-undefined",
        category="campaign",
        severity="critical",
        classification="REVIEW",
        confidence="HIGH",
        explanation="Code in this mod names star type(s) " + ", ".join(sorted(used)) + " that neither this mod's data/config/planets.json "
                    "nor RC8's defines. initStar() then builds the star from a null spec and New Game stops with a NullPointerException "
                    "(GRP10Q-20261005). RC8 renamed several 0.7-era stars (star_red -> star_red_dwarf, star_blue -> star_blue_giant): "
                    "restore the mod's own spec from its original planets.json, or point the code at RC8's id. A restored star also "
                    "needs a star_gen_data.csv row (procgen-star-row-missing).",
        file="data/config/planets.json",
        evidence=[f"type:{name}" for name in sorted(used)] + [f"used-in:{f}" for name in sorted(used) for f in sorted(set(used[name]))[:3]],
    )


def _scan_procgen_rows(root: Path, result: ScanResult, vanilla_core: Path | None) -> None:
    """Every campaign-placed planets.json type needs a procgen CSV row (crash if absent)."""
    planets_path = root / "data" / "config" / "planets.json"
    data = _load_lenient_json_file(planets_path)
    if not isinstance(data, dict):
        return

    campaign_ids_used: dict[str, list[str]] = {}
    mission_ids_used: set[str] = set()
    jar_present = bool(list(root.rglob("*.jar")))
    for source in root.rglob("*.java"):
        try:
            text = source.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        literals = set(re.findall(r'"([A-Za-z0-9_]+)"', text))
        matched = literals & data.keys()
        if not matched:
            continue
        if _is_mission_source(root, source):
            mission_ids_used.update(matched)
        else:
            relative = _relative(root, source)
            for type_id in matched:
                campaign_ids_used.setdefault(type_id, []).append(relative)

    star_csv = root / "data" / "campaign" / "procgen" / "star_gen_data.csv"
    planet_csv = root / "data" / "campaign" / "procgen" / "planet_gen_data.csv"
    mod_star_ids = _csv_first_column_ids(star_csv)
    mod_planet_ids = _csv_first_column_ids(planet_csv)
    vanilla_star_ids: set[str] = set()
    vanilla_planet_ids: set[str] = set()
    vanilla_note: str | None = None
    if vanilla_core is not None:
        vanilla_star_ids = _csv_first_column_ids(vanilla_core / "data" / "campaign" / "procgen" / "star_gen_data.csv")
        vanilla_planet_ids = _csv_first_column_ids(vanilla_core / "data" / "campaign" / "procgen" / "planet_gen_data.csv")
    else:
        vanilla_note = "vanilla-core:unavailable; vanilla-row exemption could not be checked"

    for type_id in sorted(campaign_ids_used):
        spec = data.get(type_id)
        is_star = bool(isinstance(spec, dict) and spec.get("isStar"))
        registered = mod_star_ids if is_star else mod_planet_ids
        vanilla_registered = vanilla_star_ids if is_star else vanilla_planet_ids
        if type_id in registered or type_id in vanilla_registered:
            continue
        csv_relative = "data/campaign/procgen/star_gen_data.csv" if is_star else "data/campaign/procgen/planet_gen_data.csv"
        spec_class = "StarGenDataSpec" if is_star else "PlanetGenDataSpec"
        used_files = sorted(set(campaign_ids_used[type_id]))
        evidence = [f"type:{type_id}", f"isStar:{is_star}", f"missing-row-in:{csv_relative}", *[f"used-in:{f}" for f in used_files[:5]]]
        if jar_present:
            evidence.append("class-file-constant-strings:not-scanned (java sources only)")
        if vanilla_note:
            evidence.append(vanilla_note)
        result.add(
            id="procgen-star-row-missing" if is_star else "procgen-planet-row-missing",
            category="campaign",
            severity="critical",
            classification="REVIEW",
            confidence="HIGH",
            explanation=(
                f"data/config/planets.json defines '{type_id}' and it is used from campaign code, but no row "
                f"with that id exists in {csv_relative} (locally or in vanilla). StarSystem."
                "autogenerateHyperspaceJumpPoints -> PlanetConditionGenerator throws a fatal "
                f"'Spec of class [...{spec_class}] with id [{type_id}] not found' during new-game generation. "
                "Clone the closest vanilla row, rename its id, and set the frequency columns "
                "(frequency for planets; freqYOUNG/freqAVERAGE/freqOLD for stars) to 0 if it should not be "
                "randomly generated."
            ),
            file=_relative(root, planets_path),
            evidence=evidence,
        )


def _vanilla_faction_ids(vanilla_core: Path) -> set[str]:
    ids: set[str] = set()
    faction_dir = vanilla_core / "data" / "world" / "factions"
    if not faction_dir.is_dir():
        return ids
    for path in faction_dir.glob("*.faction"):
        data = _load_lenient_json_file(path)
        if isinstance(data, dict):
            faction_id = data.get("id")
            if isinstance(faction_id, str) and faction_id:
                ids.add(faction_id)
    return ids


_RULES_MERGED_CONDITION = re.compile(r"[A-Za-z0-9_)]\$[A-Za-z_]")


_RULES_FACTION_ID_CONDITION = re.compile(r"\$faction\.id\s*==\s*([A-Za-z0-9_]+)")


def _scan_rules_condition_defects(root: Path, result: ScanResult, vanilla_core: Path | None) -> None:
    """rules.csv conditions that can never match as written (Flu-X greetings, found 2026-09-13).

    Each condition is its own line in the cell. "$faction.id == infected$faction.hostileToPlayer" lost its
    line break, so it compares the id with that whole string and the rule never fires (vanilla RC8: 0 of
    11107 rules have a variable glued to a preceding word). A `$faction.id ==` naming a faction neither
    vanilla nor the mod defines is usually copy-paste (Flu-X's "greetinginfectedTOffWeaker" tests
    templars); it can also be a deliberate cross-mod integration, hence REVIEW.
    """
    rules = root / "data" / "campaign" / "rules.csv"
    try:
        with rules.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
            rows = [row for row in csv.DictReader(handle) if not (row.get("id") or "").lstrip().startswith("#")]
    except OSError:
        return
    merged: list[str] = []
    faction_refs: list[tuple[str, str]] = []
    for row in rows:
        rule_id = (row.get("id") or "").strip() or "<no id>"
        conditions = row.get("conditions") or ""
        for line in conditions.splitlines():
            if _RULES_MERGED_CONDITION.search(line):
                merged.append(f"rule:{rule_id}: {line.strip()}")
        faction_refs.extend((rule_id, faction) for faction in _RULES_FACTION_ID_CONDITION.findall(conditions))
    relative = _relative(root, rules)
    if merged:
        result.add(
            id="rules-condition-merged-lines",
            category="rules",
            severity="medium",
            classification="REVIEW",
            confidence="DETERMINISTIC",
            explanation="A rules.csv condition has a variable glued to the previous word, so two conditions lost their line break and the rule compares against the joined string: it never fires as written. Fixing it changes live behaviour (the rule starts firing), so treat it as a decision, not a cleanup.",
            file=relative,
            evidence=merged,
        )
    if vanilla_core is None or not faction_refs:
        return
    known = _vanilla_faction_ids(vanilla_core)
    for path in (root / "data" / "world" / "factions").glob("*.faction"):
        data = _load_lenient_json_file(path)
        known.add(data["id"] if isinstance(data, dict) and isinstance(data.get("id"), str) else path.stem)
    unknown = sorted({f"rule:{rule_id} -> {faction}" for rule_id, faction in faction_refs if faction not in known})
    if unknown:
        result.add(
            id="rules-condition-unknown-faction",
            category="rules",
            severity="medium",
            classification="REVIEW",
            confidence="HIGH",
            explanation="A rules.csv condition tests $faction.id against a faction that neither vanilla nor this mod defines. Usually a copy-paste from another mod (the rule never fires for the intended faction and shows its text to the other one); confirm it is not a deliberate integration before changing it.",
            file=relative,
            evidence=unknown,
        )
