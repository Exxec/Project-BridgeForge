"""Java source scan: removed API calls, legacy API rules, build dependencies, custom UI plugins."""
from __future__ import annotations

import hashlib
import re
from .ashlib_compat import scan_ashlib_compat
from .graphicslib_compat import scan_graphicslib_compat
from .java_ast import AstUnavailable, analyze_sources
from .lazylib_compat import scan_lazylib_compat
from .magiclib_compat import scan_magiclib_compat
from .models import ScanResult
from pathlib import Path
from .scan_campaign import _lookup_null_guarded, _scan_core_campaign_plugin_reregistered, _scan_removed_market_condition_ids, _scan_system_generation_unguarded, _system_lookup_null_guarded
from .scan_combat import _scan_hulk_death_effect_repeats, _scan_hullmod_fleet_dereference, _scan_hullmod_instance_state, _scan_rules_firebest_populate_options, _scan_saved_object_holds_market_ref, _scan_weapon_effect_static_state
from .scan_common import CUSTOM_DIALOG_DELEGATE_PATTERN, CUSTOM_UI_PLUGIN_PATTERN, EXTERNAL_CAMPAIGN_MEMORY_PREFIXES, EXTERNAL_MOD_API_PACKAGES, HARDCODED_ENTITY_LOOKUP_PATTERN, HARDCODED_SYSTEM_LOOKUP_PATTERN, LEGACY_API_RULES, LIBRARY_PACKAGES, MEMORY_SELF_STORE_PATTERN, PERCENT_MULTIPLIER_PATTERN, RELEASE_BLOCKING_TODO_PATTERN, ROBOT_INPUT_INJECTION_PATTERN, RUNTIME_PLACEHOLDER_PATTERN, TARGET_INTERFACE_CONTRACTS, _INTERFACE_BASE_CLASSES, _relative
from .scan_compile import _scan_dependency_version_major, _scan_loose_script_janino_risk
from .scan_factions import _scan_faction_trait_weight_legacy_personality_ids, _scan_personality_ids
from .scan_fleets import _external_memory_keys_harmless, _scan_bare_market_fleet_source, _scan_legacy_event_report
from .scan_jarchecks import LEGACY_VANILLA_CLASSES, VANILLA_LOOSE_SCRIPT_CLASSES, _console_command_classes, _scan_jar_interface_methods, _scan_jar_linkage
from .scan_javatext import _blank_java_comments, _extract_call_arguments_text, _split_call_arguments
from .scan_libraries import _local_class_names, _mod_info_declares_dependency, _scan_aotd_toolbox_version, _sources_mentioning
from .scan_missions import _scan_campaign_fleet_references, _scan_mission_local_fleet_references, _scan_mission_required_files
from .scan_settings import _scan_fleet_type_names, _scan_procgen_mod_body_leak, _scan_replace_array
from .scan_shadowing import _scan_vanilla_script_shadow_repointable
from .scan_text import _scan_data_encoding, _scan_fullwidth_numbers, _scan_non_ascii_names, _scan_non_english_text, _scan_shippable_work_files


def _scan_sources(root: Path, result: ScanResult, vanilla_core: Path | None = None, provider_roots: list[Path] | None = None) -> None:
    try:
        result.source_facts = analyze_sources(root)
    except AstUnavailable as exc:
        result.add(id="source-ast-unavailable", category="source", severity="medium", classification="UNKNOWN", confidence="DETERMINISTIC", explanation=f"Structured Java parsing was unavailable; import collection used a limited fallback: {exc}")
    imports: set[str] = set()
    import_locations: dict[str, tuple[str, int | None]] = {}
    content_owners: dict[str, list[str]] = {}
    for source in root.rglob("*.java"):
        relative = _relative(root, source)
        try:
            raw_bytes = source.read_bytes()
        except OSError as exc:
            result.add(id="unreadable-source", category="source", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation=str(exc), file=relative)
            continue
        text = raw_bytes.decode("utf-8", errors="replace")
        content_owners.setdefault(hashlib.sha256(raw_bytes).hexdigest(), []).append(relative)
        active_source = "disabled_files" not in source.relative_to(root).parts
        if result.source_facts:
            file_import_facts = [fact for fact in result.source_facts if fact["kind"] == "import" and fact["file"] == relative]
            imports.update(fact["value"] for fact in file_import_facts)
            for fact in file_import_facts:
                import_locations.setdefault(fact["value"], (relative, fact.get("line")))
        else:
            found_imports = re.findall(r"^\s*import\s+([\w.]+(?:\.\*)?)\s*;", text, re.M)
            imports.update(found_imports)
            for name in found_imports:
                import_locations.setdefault(name, (relative, None))
        for needle, (rule_id, explanation) in LEGACY_API_RULES.items():
            if needle in text:
                result.add(id=rule_id, category="source-api", severity="high", classification="REVIEW", confidence="HIGH", explanation=explanation, file=relative, evidence=[needle])
        # Comments blanked: Xenoargh-AI-Overhaul's IDE stubs keep the throw commented out (2026-09-28).
        if active_source and RUNTIME_PLACEHOLDER_PATTERN.search(_blank_java_comments(text)):
            result.add(
                id="runtime-placeholder-unsupported-operation",
                category="source",
                severity="high",
                classification="REVIEW",
                confidence="DETERMINISTIC",
                explanation="Active Java source explicitly throws UnsupportedOperationException. This commonly indicates an IDE-generated placeholder that will crash when the callback is invoked.",
                file=relative,
                evidence=["throw new UnsupportedOperationException"],
            )
        if active_source:
            for contract_id, contract in TARGET_INTERFACE_CONTRACTS.items():
                if contract["implements"].search(text) and not contract["method"].search(text):
                    interface = contract.get("interface", contract_id)
                    # A class extending RC8's base class inherits the method (javap 2026-10-05: BaseHullMod has
                    # showInRefitScreenModPickerFor/isSModEffectAPenalty, BaseShipSystemScript all six overrides).
                    # Grytpype & Moriarty's hull mods "extends BaseHullMod implements HullModEffect" were flagged.
                    base = _INTERFACE_BASE_CLASSES.get(interface)
                    if base and re.search(r"\bextends\s+(?:[\w.]+\.)?" + base + r"\b", text):
                        continue
                    result.add(
                        id="target-interface-method-missing",
                        category="source-api",
                        severity="critical",
                        classification="MANUAL",
                        confidence="DETERMINISTIC",
                        explanation=f"This source implements Starsector's {interface} but lacks the 0.98a-required {contract['signature']}. It will fail Janino/Javac loading before the mod can start. {contract['suggestion']}",
                        file=relative,
                        evidence=[interface, contract["signature"]],
                    )
        if active_source:
            missing_callbacks = _custom_ui_plugins_missing_button_callback(text)
            if missing_callbacks:
                result.add(
                    id="missing-custom-ui-button-pressed-callback",
                    category="source-api",
                    severity="high",
                    classification="REVIEW",
                    confidence="HIGH",
                    explanation="CustomUIPanelPlugin implementations in 0.98a require buttonPressed(Object). Add a no-op callback when the panel has no button handling, then runtime-test the UI.",
                    file=relative,
                    evidence=[f"{missing_callbacks} plugin block(s) missing buttonPressed(Object)"],
                )
        if active_source and CUSTOM_DIALOG_DELEGATE_PATTERN.search(text) and re.search(r"\bcreateCustomDialog\s*\(\s*CustomPanelAPI\s+\w+\s*\)", text):
            result.add(
                id="legacy-custom-dialog-delegate-signature",
                category="source-api",
                severity="high",
                classification="REVIEW",
                confidence="HIGH",
                explanation="CustomDialogDelegate#createCustomDialog now receives CustomDialogCallback in 0.98a. Update the signature and preserve any required callback behavior before runtime-testing the dialog.",
                file=relative,
                evidence=["createCustomDialog(CustomPanelAPI)"],
            )
        if active_source and RELEASE_BLOCKING_TODO_PATTERN.search(text):
            result.add(
                id="release-blocking-source-todo",
                category="source",
                severity="high",
                classification="REVIEW",
                confidence="HIGH",
                explanation="Active source contains a TODO/FIXME explicitly saying behavior must be removed, deleted, or disabled before release. Inspect it as a possible development-only gameplay or save-state leak.",
                file=relative,
                evidence=["TODO/FIXME release-removal marker"],
            )
        if active_source and ROBOT_INPUT_INJECTION_PATTERN.search(text):
            result.add(
                id="campaign-ui-robot-input-injection",
                category="campaign-ui",
                severity="medium",
                classification="REVIEW",
                confidence="DETERMINISTIC",
                explanation="Campaign UI code creates java.awt.Robot to synthesize operating-system input. This can fail under restricted desktops, overlays, focus changes, or platform-specific input handling; prefer an in-game UI transition when possible and runtime-test every affected dialog.",
                file=relative,
                evidence=["new Robot()"],
            )
        # A java.util.Random subclass holds only primitive state and serializes cleanly; stored in memory it keeps
        # its sequence across save and reload (anti-save-scum). KIND-STRANGER Vesperon's SequenceGenerator was flagged,
        # and an agent "fix" that passed the verifier changed behaviour (review 2026-09-29).
        if active_source and MEMORY_SELF_STORE_PATTERN.search(text) and not re.search(r"\bclass\s+\w+\s+extends\s+(?:java\.util\.)?Random\b", text):
            result.add(
                id="campaign-memory-live-object",
                category="save-risk",
                severity="medium",
                classification="REVIEW",
                confidence="HIGH",
                explanation="Campaign memory stores `this`, a live Java object. Persistent campaign memory should normally use primitive values, IDs, or serializable data; inspect save/load behavior and replace UI/runtime objects where practical.",
                file=relative,
                evidence=["MemoryAPI.set(..., this)"],
            )
        if active_source and PERCENT_MULTIPLIER_PATTERN.search(text):
            result.add(
                id="suspicious-percent-multiplier",
                category="combat-stats",
                severity="medium",
                classification="REVIEW",
                confidence="HIGH",
                explanation="modifyPercent() received a multiplier-shaped expression (for example, 1f - penalty * 0.01f). It will apply approximately +1 percent rather than the intended multiplier or negative percentage in Starsector's mutable-stat API.",
                file=relative,
                evidence=["modifyPercent(..., 1f - value * 0.01f)"],
            )
        if active_source:
            for system_name in HARDCODED_SYSTEM_LOOKUP_PATTERN.findall(text):
                # Zorg18's spawner and Flu-X's plugin both null-check the lookup (2026-09-14): a guarded
                # lookup already survives a missing system, so it isn't a review item.
                guarded = _system_lookup_null_guarded(_blank_java_comments(text), system_name)
                result.add(
                    id="hard-coded-campaign-system-reference",
                    category="campaign",
                    severity="low" if guarded else "medium",
                    classification="SAFE" if guarded else "REVIEW",
                    confidence="DETERMINISTIC",
                    explanation=("Campaign code looks up a star system using a literal string, and null-checks the result, so a missing system is handled. Confirm the ID is the stable system ID." if guarded else "Campaign code looks up a star system using a literal string. Verify that it is the stable system ID, that the target is guaranteed to exist, and that optional/total-conversion environments are guarded."),
                    file=relative,
                    evidence=[system_name] + (["null-guarded"] if guarded else []),
                )
            for entity_id in HARDCODED_ENTITY_LOOKUP_PATTERN.findall(text):
                guarded = _lookup_null_guarded(_blank_java_comments(text), "getEntityById", entity_id)
                result.add(
                    id="hard-coded-campaign-entity-reference",
                    category="campaign",
                    severity="low" if guarded else "medium",
                    classification="SAFE" if guarded else "REVIEW",
                    confidence="DETERMINISTIC",
                    explanation=("Campaign code looks up an entity by a fixed ID and null-checks the result, so a missing entity (a random sector, a total conversion) is handled." if guarded else "Campaign code looks up an entity by a fixed ID. Verify that the entity is created before this code runs and null-check optional or save-dependent entities before dereferencing them."),
                    file=relative,
                    evidence=[entity_id] + (["null-guarded"] if guarded else []),
                )
            for integration, prefix in EXTERNAL_CAMPAIGN_MEMORY_PREFIXES.items():
                keys = sorted(set(re.findall(rf'"({re.escape(prefix)}[A-Za-z0-9_]+)"', text)))
                if keys:
                    harmless = _external_memory_keys_harmless(text, keys, integration.lower())
                    result.add(
                        id="external-campaign-memory-key",
                        category="campaign",
                        severity="low" if harmless else "medium",
                        classification="SAFE" if harmless else "REVIEW",
                        confidence="DETERMINISTIC",
                        explanation=f"Campaign code reads {integration}-namespaced memory state directly. Verify the integration is optional, null-safe, and tested with {integration} disabled.",
                        file=relative,
                        evidence=[integration, *keys] + (["written-or-guarded"] if harmless else []),
                    )
        commented_spawns = re.findall(r"//[^\r\n]*\b(?:addSpawnPoint|spawnFleet)\s*\(", text)
        uncommented_text = re.sub(r"//[^\r\n]*", "", text)
        active_spawns = re.findall(r"\b(?:addSpawnPoint|spawnFleet)\s*\(", uncommented_text)
        if active_source and commented_spawns and not active_spawns:
            result.add(
                id="campaign-spawn-registration-disabled",
                category="campaign",
                severity="high",
                classification="REVIEW",
                confidence="HIGH",
                explanation="Campaign fleet-spawn calls are present only in comments. The mod may generate its system but will not create those fleets until the spawning code is ported and enabled.",
                file=relative,
                evidence=[f"{len(commented_spawns)} commented spawn call(s)"],
            )
    result.imports = sorted(imports)
    for paths in content_owners.values():
        if len(paths) > 1:
            result.add(id="duplicate-source-layout", category="source", severity="medium", classification="REVIEW", confidence="DETERMINISTIC", explanation="Identical Java source appears at multiple paths. Establish the authoritative source/JAR layout before compiling or modifying it.", evidence=sorted(paths))
    _scan_mission_local_fleet_references(root, result, vanilla_core)
    _scan_campaign_fleet_references(root, result, vanilla_core)
    _scan_jar_linkage(root, result, vanilla_core)
    _scan_jar_interface_methods(root, result, vanilla_core)
    _scan_core_campaign_plugin_reregistered(root, result)
    _scan_system_generation_unguarded(root, result)
    _scan_mission_required_files(root, result)
    _scan_loose_script_janino_risk(root, result, provider_roots)
    _scan_dependency_version_major(root, result, provider_roots)
    _scan_aotd_toolbox_version(root, result, provider_roots)
    _scan_weapon_effect_static_state(root, result)
    _scan_rules_firebest_populate_options(root, result)
    _scan_hullmod_instance_state(root, result)
    _scan_hulk_death_effect_repeats(root, result)
    _scan_hullmod_fleet_dereference(root, result)
    _scan_saved_object_holds_market_ref(root, result)
    _scan_personality_ids(root, result)
    _scan_faction_trait_weight_legacy_personality_ids(root, result)
    _scan_removed_market_condition_ids(root, result)
    _scan_vanilla_script_shadow_repointable(root, result, vanilla_core)
    _scan_replace_array(root, result, vanilla_core)
    _scan_fleet_type_names(root, result, vanilla_core)
    _scan_procgen_mod_body_leak(root, result)
    _scan_bare_market_fleet_source(root, result)
    _scan_legacy_event_report(root, result)
    _scan_non_english_text(root, result)
    _scan_shippable_work_files(root, result)
    _scan_non_ascii_names(root, result)
    _scan_data_encoding(root, result)
    _scan_fullwidth_numbers(root, result)
    _scan_source_build_dependencies(root, result, import_locations)
    _scan_removed_api_calls(root, result)

    scan_lazylib_compat(root, result)
    scan_magiclib_compat(result)
    scan_ashlib_compat(root, result)
    scan_graphicslib_compat(root, result)


# A REMOVED_API_CALLS "matcher" (1st tuple element) is either a compiled regex (matched directly with
# .finditer) or a plain function text -> list[(start, end)] (for rules argument-count disambiguation
# alone can't express safely - see _find_legacy_add_planet_calls below). _removed_api_call_spans hides
# the difference from both this scanner and fixers._fix_removed_api_call.
def _removed_api_call_spans(matcher, text: str) -> list[tuple[int, int]]:
    if hasattr(matcher, "finditer"):
        return [(match.start(), match.end()) for match in matcher.finditer(text)]
    return matcher(text)


# 0.6-era LocationAPI.addPlanet(focus, name, type, angle, radius, orbitRadius, orbitDays) - 7 arguments,
# the location as the *receiver*. RC8's LocationAPI.addPlanet (javap, 2026-09-15) is id-first with 8
# arguments: addPlanet(String id, SectorEntityToken focus, String name, String type, float angle, float
# radius, float orbitRadius, float orbitDays) - same 7 trailing arguments, unchanged order (cross-checked
# against a real RC8 call site read off the install, data/scripts/world/corvus/Corvus.java:
# system.addPlanet("asharu", star, "Asharu", "desert", 55, 150, 2800, 100)). MissionDefinitionAPI also has
# an addPlanet (javap: 5- and 6-argument overloads, e.g. Gekelonians'/Batavia's own mission files:
# api.addPlanet(minX + width * 0.2f, minY + height * 0.2f, 300f, "cryovolcanic", 300f)) - a different,
# still-valid method on a different receiver type. Argument count (not receiver type, which can't be
# inferred from source text alone) is what tells all three apart; a receiver-type check isn't available
# from a lone regex, so this counts top-level arguments the same paren/quote-aware way
# _split_call_arguments does and only matches an exact 7 - "be conservative": a call whose argument count
# doesn't come out to exactly 7 (RC8's own 8, MissionDefinitionAPI's 5/6, or anything unexpected) is left
# alone, never guessed at.
_LEGACY_ADD_PLANET_RECEIVER_PATTERN = re.compile(r"\b([A-Za-z_]\w*)\s*\.\s*addPlanet\s*\(")


# RC8's LocationAPI/StarSystemAPI have no addOrbitalStation method at all (javap -p on both, 2026-09-15:
# no method of that name), so unlike addPlanet there is no RC8 form to avoid conflating with - any call
# is safe to flag/rewrite without an argument-count check. Every real 0.6 call site found (Cobalt Arms,
# Gekelonians, Independant Mining Faction, Batavia, Qualljom x2, Antediluvians) has the same 6-argument
# shape: addOrbitalStation(SectorEntityToken focus, float angle, float orbitRadius, float orbitDays,
# String name, String factionId).
_LEGACY_ADD_ORBITAL_STATION_RECEIVER_PATTERN = re.compile(r"\b([A-Za-z_]\w*)\s*\.\s*addOrbitalStation\s*\(")


# Neither finder must re-match its own fixer's output: the rewrite is
# `bf.legacyworld.LegacyWorld.addPlanet(...)`/`...addOrbitalStation(...)`, and `LegacyWorld` alone is a
# syntactically valid receiver for `\b([A-Za-z_]\w*)\s*\.\s*addPlanet\s*\(` - a real 0.6 script calling a
# receiver literally named `LegacyWorld` is not a real case this needs to support, so it's excluded
# outright rather than guessed at (addPlanet's 7-argument count check already prevents this by accident,
# since the rewritten call always has 8 arguments; addOrbitalStation has no such count check, so without
# this guard a fixed file would be re-flagged, and re-fixed, forever).
_LEGACY_WORLD_RECEIVER_NAME = "LegacyWorld"


def _find_legacy_add_planet_calls(text: str) -> list[tuple[int, int]]:
    """(start, end) spans for `receiver.addPlanet(` calls with exactly 7 top-level arguments."""
    spans: list[tuple[int, int]] = []
    for match in _LEGACY_ADD_PLANET_RECEIVER_PATTERN.finditer(text):
        if match.group(1) == _LEGACY_WORLD_RECEIVER_NAME:
            continue
        open_paren = match.end() - 1
        args_text = _extract_call_arguments_text(text, open_paren)
        if args_text is None:
            continue
        if len(_split_call_arguments(args_text)) != 7:
            continue
        spans.append((match.start(1), open_paren + 1 + len(args_text) + 1))
    return spans


def _find_legacy_add_orbital_station_calls(text: str) -> list[tuple[int, int]]:
    """(start, end) spans for every `receiver.addOrbitalStation(...)` call (whole span, any arg count)."""
    spans: list[tuple[int, int]] = []
    for match in _LEGACY_ADD_ORBITAL_STATION_RECEIVER_PATTERN.finditer(text):
        if match.group(1) == _LEGACY_WORLD_RECEIVER_NAME:
            continue
        open_paren = match.end() - 1
        args_text = _extract_call_arguments_text(text, open_paren)
        if args_text is None:
            continue
        spans.append((match.start(1), open_paren + 1 + len(args_text) + 1))
    return spans


# 0.6-era CargoAPI.CrewXPLevel, per owner decision 2026-09-15 (crew quality no longer exists in RC8; crew
# counts are kept): three alternatives, all deleted outright by the fixer (see
# _rewrite_crew_xp_level_span) - the now-unresolvable import line; CrewXPLevel.X, as addCrew's first
# argument (addCrew(CrewXPLevel.X, n) -> addCrew(n)); and , CrewXPLevel.X as addToFleet's trailing
# argument (addToFleet(..., CrewXPLevel.X) -> addToFleet(...)). Every real call site found across all six
# mods (Cobalt Arms, Gekelonians, Independant Mining Faction, Batavia, Qualljom, Antediluvians - 11 files)
# matches one of these three shapes exactly; nothing else in CargoAPI/MissionDefinitionAPI ever took a
# CrewXPLevel (javap of RC8's starfarer.api.jar, 2026-09-14: CargoAPI has only addCrew(int); a jar-wide
# search finds no CrewXPLevel/XPLevel anywhere in RC8, confirming the type itself is gone, not just moved).
_CREW_XP_LEVEL_PATTERN = re.compile(
    r"import\s+com\.fs\.starfarer\.api\.campaign\.CargoAPI\.CrewXPLevel\s*;[ \t]*\r?\n?"
    # The CargoAPI. qualifier is part of the span (Ironclads' FleetSpawner wrote addCrew(CargoAPI.CrewXPLevel.REGULAR,
    # n); leaving the qualifier produced addCrew(CargoAPI.(int)...), 2026-10-04).
    # A tier read, getCrew(CrewXPLevel.X) (ROADMAP 40; Ironclads' salvage scripts, 2026-10-05): owner decision "one
    # crew" -- REGULAR (the tier hired crew came in) reads all crew, other tiers read 0, so tier sums stay right.
    r"|getCrew\s*\(\s*(?:(?:com\.fs\.starfarer\.api\.campaign\.)?CargoAPI\s*\.\s*)?CrewXPLevel\s*\.\s*\w+\s*\)"
    r"|(?:(?:com\.fs\.starfarer\.api\.campaign\.)?CargoAPI\s*\.\s*)?CrewXPLevel\s*\.\s*\w+\s*,\s*"
    r"|,\s*(?:(?:com\.fs\.starfarer\.api\.campaign\.)?CargoAPI\s*\.\s*)?CrewXPLevel\s*\.\s*\w+"
)


# API calls the target no longer has, matched only on receivers whose type is certain. Each entry needs
# javap evidence from the target's starfarer.api.jar.
REMOVED_API_CALLS = (
    (
        re.compile(
            r"\b(?:Global\s*\.\s*)?getSector\s*\(\s*\)\s*\.\s*createFleet\s*\("
            r"|\bGlobal\s*\.\s*getSectorAPI\s*\(\s*\)\s*\.\s*createFleet\s*\("
        ),
        "SectorAPI.createFleet(factionId, fleetTypeId)",
        # javap of RC8 starfarer.api.jar: SectorAPI has no createFleet (2026-09-14). The 0.6 BaseSpawnPoint
        # spawners (Gekelonians, Cobalt-Arms, Batavia, ...) built fleets from faction fleet types with it.
        # Global.getSectorAPI() is also confirmed (javap) to return SectorAPI, same as Global.getSector(), so
        # the same removed call through that receiver is caught too (2026-09-14).
        "0.6-era fleet creation from a faction's fleet types; RC8's SectorAPI has no createFleet. Build the fleet "
        "with FleetFactoryV3.createFleet(FleetParamsV3) (see Zorg18 r1's ZorgFleetSpawner) and keep the spawn point.",
    ),
    (
        re.compile(r"\b(?:Global\s*\.\s*)?getSector(?:API)?\s*\(\s*\)\s*\.\s*addMessage\s*\("),
        "SectorAPI.addMessage(String)",
        # javap of RC8 starfarer.api.jar (2026-09-14): SectorAPI has no addMessage (Global.getSector() and
        # Global.getSectorAPI() both still exist and both return SectorAPI). SectorAPI.getCampaignUI()
        # returns CampaignUIAPI, which has addMessage(String), addMessage(String, java.awt.Color) and further
        # IntelInfoPlugin overloads. Real 0.6 convoy spawn points (Cobalt-Arms, Independant-Mining-Faction,
        # Batavia, Qualljom, Antediluvians) call Global.getSectorAPI().addMessage(String) to post a comm message.
        "0.6-era comm-message posting; RC8's SectorAPI has no addMessage. Insert .getCampaignUI() before "
        ".addMessage( on the same receiver: CampaignUIAPI is where RC8 kept the method.",
    ),
    (
        _CREW_XP_LEVEL_PATTERN,
        "CargoAPI.CrewXPLevel",
        # javap of RC8 starfarer.api.jar (2026-09-14): CargoAPI no longer nests a CrewXPLevel enum (a
        # jar-wide search for CrewXPLevel/XPLevel across starfarer.api.jar finds nothing); CargoAPI now has
        # only addCrew(int) (a plain headcount, no quality level) and gainCrewXP(float).
        # Owner decision 2026-09-15 (coordinator's recommendation; RC8 has no crew quality): drop the
        # level, keep the counts. addCrew(CrewXPLevel.X, n) -> addCrew(n); MissionDefinitionAPI.addToFleet's
        # trailing CrewXPLevel argument is dropped the same way (RC8's addToFleet overloads, javap-confirmed,
        # take no crew-quality argument at all). Recorded as the expected change "crew quality no longer
        # exists in RC8; crew counts are kept."
        "0.6-era CargoAPI.CrewXPLevel (used with an addCrew(CrewXPLevel, int) overload, and/or "
        "MissionDefinitionAPI.addToFleet's trailing CrewXPLevel argument); RC8's CargoAPI has no nested "
        "CrewXPLevel and no overload that takes one. Owner decision 2026-09-15: drop the crew-quality level, "
        "keep the crew counts (addCrew(CrewXPLevel.X, n) -> addCrew(n); addToFleet's trailing CrewXPLevel "
        "argument is dropped).",
    ),
    (
        _find_legacy_add_planet_calls,
        "LocationAPI.addPlanet(focus, name, type, angle, radius, orbitRadius, orbitDays)",
        # javap of RC8 starfarer.api.jar (2026-09-15): LocationAPI.addPlanet is now id-first, 8 arguments
        # (String id, SectorEntityToken focus, String name, String type, float angle, float radius, float
        # orbitRadius, float orbitDays); the removed 0.6 form took the same 7 trailing arguments with the
        # location itself as the receiver. bf.legacyworld.LegacyWorld.addPlanet (RevenantLib) generates the
        # missing id and forwards to RC8's method.
        "0.6-era LocationAPI.addPlanet(focus, name, type, angle, radius, orbitRadius, orbitDays) (7 "
        "arguments, the location as the receiver); RC8's LocationAPI.addPlanet needs a leading String id "
        "(8 arguments total) that the 0.6 call never supplied. Rewritten to "
        "bf.legacyworld.LegacyWorld.addPlanet(<receiver>, <same 7 arguments>), which generates a "
        "deterministic id and forwards to RC8's method.",
    ),
    (
        _find_legacy_add_orbital_station_calls,
        "LocationAPI.addOrbitalStation(focus, angle, orbitRadius, orbitDays, name, factionId)",
        # javap of RC8 starfarer.api.jar (2026-09-15): LocationAPI/StarSystemAPI have no addOrbitalStation
        # method at all. Owner decision 2026-09-15 ("option A"): 0.6 orbital stations become real, dockable
        # RC8 markets. bf.legacyworld.LegacyWorld.addOrbitalStation (RevenantLib) builds the station entity,
        # a real market (open/black-market/storage submarkets, economy registration), and a one-shot script
        # that moves whatever the caller stocks into the returned token's cargo into the market's open
        # submarket cargo.
        "0.6-era LocationAPI.addOrbitalStation(focus, angle, orbitRadius, orbitDays, name, factionId); RC8's "
        "LocationAPI/StarSystemAPI have no method of that name at all. Rewritten to "
        "bf.legacyworld.LegacyWorld.addOrbitalStation(<receiver>, <same 6 arguments>), which creates a real, "
        "dockable RC8 market in place of the old token (owner decision 2026-09-15, option A).",
    ),
)


def _scan_removed_api_calls(root: Path, result: ScanResult) -> None:
    """Calls to API methods the target removed, in loose scripts and bundled sources."""
    for pattern, signature, explanation in REMOVED_API_CALLS:
        hits: list[str] = []
        for source in sorted(root.rglob("*.java")):
            if "disabled_files" in source.relative_to(root).parts:
                continue  # never loaded by the game
            try:
                text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            for start, _end in _removed_api_call_spans(pattern, text):
                hits.append(f"{_relative(root, source)}:{text.count(chr(10), 0, start) + 1}")
        if hits:
            result.add(
                id="removed-api-call",
                category="source-api",
                severity="critical",
                classification="MANUAL",
                confidence="DETERMINISTIC",
                explanation=f"Source calls {signature}, which the target API no longer has: {explanation} A loose script with this call fails to compile at load, so the game doesn't start.",
                evidence=[f"{signature}: {len(hits)} call(s)"] + hits[:12] + (["..."] if len(hits) > 12 else []),
            )


def _scan_source_build_dependencies(root: Path, result: ScanResult, import_locations: dict[str, tuple[str, int | None]] | None = None) -> None:
    lombok_imports = sorted(item for item in result.imports if item == "lombok" or item.startswith("lombok."))
    if lombok_imports:
        build_files = [name for name in ("pom.xml", "build.gradle", "build.gradle.kts") if (root / name).is_file()]
        detail = " Build metadata was not found." if not build_files else f" Build metadata found: {', '.join(build_files)}."
        result.add(
            id="source-lombok-annotation-processing",
            category="build",
            severity="high",
            classification="MANUAL",
            confidence="DETERMINISTIC",
            explanation="Source imports Lombok, which generates methods and constructors during compilation. A plain javac rebuild will fail or produce missing members unless Lombok is supplied as an annotation processor." + detail,
            evidence=lombok_imports,
        )
    # An import of one of the mod's own classes needs no library, even inside a library-named package:
    # Blackrock ships its own data.scripts.util.AnamorphicFlare / BRDYMulti / I18nUtil, which is
    # MagicLib's legacy package prefix.
    local_classes = _local_class_names(root)
    # Imports of mod-style classes (data.*) that this mod defines nowhere and no known library provides:
    # another mod's classes. FX Example imports FX Core's data.scripts.fx_Particle / fx_SharedLib /
    # fx_Trail but declared no dependency on it (2026-09-14).
    # MagicLib's legacy packages (data.scripts.util.Magic*, data.scripts.plugins.Magic*) count as a library.
    known_prefixes = tuple(prefix for prefixes in (*LIBRARY_PACKAGES.values(), *EXTERNAL_MOD_API_PACKAGES.values()) for prefix in prefixes) + ("data.scripts.plugins.Magic",)
    active_imports: dict[str, set[str]] = {}
    # A script in the removed class's own package uses it without an import: Antediluvians'
    # data.scripts.world.AntediluvianSpawnPoint extends BaseSpawnPoint directly (2026-09-14).
    same_package_uses: dict[str, set[str]] = {}
    for source in sorted(root.rglob("*.java")):
        if "disabled_files" in source.relative_to(root).parts:
            continue  # never loaded by the game (Zorg18 keeps its 0.6 spawn points there)
        try:
            text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        for imported in re.findall(r"(?m)^\s*import\s+([\w.]+)\s*;", text):
            active_imports.setdefault(imported, set()).add(_relative(root, source))
        package = re.search(r"(?m)^\s*package\s+([\w.]+)\s*;", text)
        if package:
            for name in LEGACY_VANILLA_CLASSES:
                owner, simple = name.rsplit(".", 1)
                if owner == package.group(1) and re.search(rf"\b{re.escape(simple)}\b", text):
                    same_package_uses.setdefault(name, set()).add(_relative(root, source))
    # A mod that ships its own copy of the class (Vacuum's earlier BaseSpawnPoint shim) is not affected.
    legacy = {name: set(files) for name, files in active_imports.items() if name in LEGACY_VANILLA_CLASSES and name not in local_classes}
    for name, files in same_package_uses.items():
        if name not in local_classes:
            legacy.setdefault(name, set()).update(files)
    if legacy:
        result.add(
            id="legacy-vanilla-class-import",
            category="source-api",
            severity="critical",
            classification="MANUAL",
            confidence="DETERMINISTIC",
            explanation="Source uses a vanilla class that no longer exists in 0.98a, by import or by simple name from the same package. A loose script using it fails to compile at load; a jar class fails when it loads. Port the code to the current API (e.g. BaseSpawnPoint fleets to an EveryFrameScript that builds fleets, as Zorg18 did).",
            evidence=[f"{name}: {LEGACY_VANILLA_CLASSES[name]} ({len(files)} file(s): {', '.join(sorted(files)[:6])}{' ...' if len(files) > 6 else ''})" for name, files in sorted(legacy.items())],
        )
    foreign = sorted(
        item for item in active_imports
        if item.startswith("data.") and item not in LEGACY_VANILLA_CLASSES and item not in VANILLA_LOOSE_SCRIPT_CLASSES
        and item not in local_classes and item.rsplit(".", 1)[0] not in local_classes
        and not item.startswith(known_prefixes)
    )
    if foreign:
        declared = bool(result.metadata.get("dependencies") or result.metadata.get("requiredDependencies"))
        # The finding's own evidence is capped at 20 (a human-readable summary); the full list
        # survives here for the same reason unresolved_content_references does (ROADMAP P14 item
        # 4/substitutes.required_from_scan) - a mod with more than 20 unresolved imports would
        # otherwise silently understate what dependency-substitutes/the strip planner see as needed.
        result.migration_context["unresolved_foreign_class_imports"] = foreign
        result.add(
            id="source-import-unresolved",
            category="dependencies",
            severity="high",
            classification="REVIEW",
            confidence="HIGH",
            explanation="Source imports mod classes that this mod defines nowhere (no source, no jar class) and no known library provides. They belong to another mod, which must be installed and declared in mod_info.json, or the importing class fails when it loads." + (" The mod declares dependencies that may provide them; confirm." if declared else " The mod declares no dependency."),
            evidence=foreign[:20] + ([f"... {len(foreign) - 20} more"] if len(foreign) > 20 else []),
        )
    console_commands = _console_command_classes(root)
    for dependency, prefixes in EXTERNAL_MOD_API_PACKAGES.items():
        imports = sorted(item for item in result.imports if item not in local_classes and any(item == prefix.rstrip(".") or item.startswith(prefix) for prefix in prefixes))
        if imports and dependency == "Console Commands" and console_commands:
            # Console Commands loads command classes only from data/console/commands.csv, so without it
            # they are never loaded (Bionic Alteration's four commands, 2026-09-14).
            importing = _sources_mentioning(root, [prefix.rstrip(".") for prefix in prefixes])
            if importing and all(name in console_commands for name in importing.values()):
                result.add(
                    id="console-command-optional",
                    category="dependencies",
                    severity="info",
                    classification="SAFE",
                    confidence="HIGH",
                    explanation="Every class that uses Console Commands' API is registered in data/console/commands.csv, which only Console Commands reads, so the classes load only when it is installed. An optional integration; no dependency needed.",
                    evidence=sorted(importing)[:10],
                )
                continue
        if imports:
            first_file: str | None = None
            first_line: int | None = None
            if import_locations:
                locations = [import_locations[name] for name in imports if name in import_locations]
                if locations:
                    first_file, first_line = min(locations, key=lambda loc: (loc[0], loc[1] if loc[1] is not None else -1))
            evidence = [dependency, *imports]
            if first_line is not None:
                evidence.append(f"line:{first_line}")
            if _mod_info_declares_dependency(result, dependency):
                # A declared dependency in mod_info.json is hard-required: Starsector itself refuses
                # to enable this mod without it, so direct API use needs no shim or optionality
                # guard - this isn't a "might not be there at runtime" risk at all. Real case
                # (Arkgneisis, found 2026-09-21): mod_info.json declares MagicLib, and the mod's own
                # description says "Requires MagicLib" - flagging this MANUAL asked for work (a
                # compatibility shim) that would be actively wrong to add.
                result.add(
                    id="external-mod-api-import-declared",
                    category="dependencies",
                    severity="info",
                    classification="SAFE",
                    confidence="DETERMINISTIC",
                    explanation=f"Source imports {dependency}'s API directly, and mod_info.json declares {dependency} as a dependency - Starsector refuses to enable this mod without it, so no compatibility shim or optionality guard is needed.",
                    file=first_file,
                    evidence=evidence,
                )
                continue
            result.add(
                id="external-mod-api-import",
                category="dependencies",
                severity="high",
                classification="MANUAL",
                confidence="DETERMINISTIC",
                explanation=f"Source imports {dependency}'s API directly, but mod_info.json does not declare {dependency} as a dependency. Compile and runtime compatibility require that optional mod, or an explicit source-level compatibility shim/removal.",
                file=first_file,
                evidence=evidence,
            )


def _custom_ui_plugins_missing_button_callback(text: str) -> int:
    """Return plugin blocks that lack the 0.98a button callback.

    This is deliberately brace-aware rather than file-wide: an anonymous
    plugin can be missing the callback even when another implementation in the
    same source file defines one. Java parsing is not required for this narrow
    structural check, and an unmatched brace simply leaves that block for
    manual review.
    """
    missing = 0
    for match in CUSTOM_UI_PLUGIN_PATTERN.finditer(text):
        opening = match.end() - 1 if text[match.end() - 1] == "{" else text.find("{", match.end())
        if opening < 0:
            missing += 1
            continue
        depth = 0
        closing = -1
        for index in range(opening, len(text)):
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
                if depth == 0:
                    closing = index
                    break
        block = text[opening: closing + 1] if closing >= 0 else text[opening:]
        if not re.search(r"\bbuttonPressed\s*\(", block):
            missing += 1
    return missing
