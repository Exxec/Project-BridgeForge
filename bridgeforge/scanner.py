from __future__ import annotations

from .zipsafe import read_limited

import csv
import hashlib
import json
import re
import zipfile
from collections import Counter
from pathlib import Path
from pathlib import PurePosixPath

from .models import ScanResult, TargetProfile
from .java_ast import AstUnavailable, analyze_sources
from .ashlib_compat import scan_ashlib_compat
from .graphicslib_compat import scan_graphicslib_compat
from .lazylib_compat import scan_lazylib_compat
from .magiclib_compat import scan_magiclib_compat
from .scan_common import (  # noqa: F401
    CLASS_MAJOR_TO_JAVA,
    MAX_JAR_ENTRIES,
    MAX_JAR_UNCOMPRESSED_BYTES,
    MAX_JAR_COMPRESSION_RATIO,
    LARGE_BUNDLED_JAR_BYTES,
    LIBRARY_PATTERNS,
    LIBRARY_PACKAGES,
    EXTERNAL_MOD_API_PACKAGES,
    EXTERNAL_CAMPAIGN_MEMORY_PREFIXES,
    LEGACY_API_RULES,
    RUNTIME_PLACEHOLDER_PATTERN,
    PERCENT_MULTIPLIER_PATTERN,
    HARDCODED_SYSTEM_LOOKUP_PATTERN,
    HARDCODED_ENTITY_LOOKUP_PATTERN,
    CAMPAIGN_SYSTEM_CREATION_PATTERN,
    CAMPAIGN_ENTITY_CREATION_PATTERN,
    MISSION_FLEET_REFERENCE_PATTERN,
    CUSTOM_UI_PLUGIN_PATTERN,
    CUSTOM_DIALOG_DELEGATE_PATTERN,
    RELEASE_BLOCKING_TODO_PATTERN,
    ROBOT_INPUT_INJECTION_PATTERN,
    _INTERFACE_BASE_CLASSES,
    TARGET_INTERFACE_CONTRACTS,
    MEMORY_SELF_STORE_PATTERN,
    FACTION_SPECIAL_ROLE_KEYS,
    OBSOLETE_FIGHTER_ROLE_NAMES,
    BLACK_HOLE_HINT_PATTERN,
    SHADOW_PATH_EXTENSIONS,
    GAME_VERSION_RC_PATTERN,
    FORBIDDEN_REFLECT_PREFIX,
    FORBIDDEN_NIO_FILE_PREFIX,
    FORBIDDEN_IO_CLASSES,
    FORBIDDEN_SANDBOX_SOURCE_PATTERN,
    BUNDLED_LIBRARY_PACKAGE_PREFIXES,
    LIBRARY_DEPENDENCY_IDS,
    SETTINGS_ACCEPT_LIMIT,
    SETTINGS_BASELINE_FILE,
    DESIGN_TYPE_CSV_TARGETS,
    _relative,
    _java_for_major,
)
from .scan_json import (  # noqa: F401
    _without_trailing_commas,
    _strip_line_comments,
    _convert_single_quoted_strings,
    _JSON_STRING_TOKEN_PATTERN,
    _JAVA_NUMBER_SUFFIX_PATTERN,
    _ORGJSON_UNQUOTED_RUN,
    _BAREWORD_TOKEN_PATTERN,
    _LOOSE_NUMBER_PATTERN,
    _HEX_NUMBER_PATTERN,
    _RAW_CONTROL_IN_STRING_PATTERN,
    _JSON_LITERAL_TOKENS,
    _normalize_string_contents,
    _fill_empty_array_elements,
    _strip_java_number_suffixes,
    _LENIENT_NUMBER_PATTERN,
    _normalize_lenient_numbers,
    _orgjson_separators,
    _quote_barewords_and_keys,
    _parse_json,
    _non_strict_json_finding,
    _hash_comment_json_finding,
    _slash_comment_json_finding,
    _single_quote_json_finding,
    _unquoted_key_json_finding,
    _bareword_value_json_finding,
    _java_number_suffix_json_finding,
    _lenient_number_json_finding,
    _json_trailing_data_finding,
    _emit_json_tolerance_findings,
    _JSON_VALUE_END,
    _repair_missing_commas,
    _unverified_json_syntax_finding,
    _json_encoding_finding,
    _load_lenient_json_file,
    _csv_header,
    _read_csv_rows,
    _read_csv_rows_lenient,
    _csv_first_column_ids,
    _wing_ids_set,
    _wing_id_variant_map,
)
from .scan_javatext import (  # noqa: F401
    _method_body,
    _method_body_with_helpers,
    _METHOD_SIGNATURE_PATTERN,
    _extract_call_arguments_text,
    _split_call_arguments,
    _enclosing_method_span,
    _blank_java_comments,
    _brace_body,
    _call_argument_count,
)
from .scan_classfile import (  # noqa: F401
    mod_jar_class_names,
    loose_script_jar_shadowed_class,
    _iter_class_files_in,
    _dependency_jar_class_names,
    _class_pool_u2,
    _class_pool_u4,
    _skip_attributes,
    _ClassFileInfo,
    _parse_class_file,
    _OPERAND_BYTES,
    _instance_fields_written_outside_constructors,
    NON_MOD_JAR_DIRS,
    _loaded_mod_jars,
    _iter_jar_class_files,
    iter_class_files_in_jars,
)
from .scan_text import (  # noqa: F401
    _DESIGN_TYPE_SOURCES,
    _design_type_color_keys,
    _scan_design_type_colors,
    _CJK_TEXT,
    _PLAYER_TEXT_SUFFIXES,
    _scan_non_english_text,
    _WORK_FILE_GLOBS,
    _scan_shippable_work_files,
    _SPEC_ID_KEYS,
    _scan_non_ascii_names,
    _scan_data_encoding,
    _FULLWIDTH_NUMBER_CHARS,
    _NUMBER_CELL,
    _scan_fullwidth_numbers,
    _scan_csv_design_type_column,
    CSV_SLASH_QUOTE,
    _scan_csv_slash_quote,
    _scan_working_copy_tool_debris,
)
from .scan_data_rules import (  # noqa: F401
    MOD_INFO_TRIAGE_BANNER_PATTERN,
    _person_names_duplicate_lines,
    _csv_first_cells,
    _rules_duplicate_id_cells,
    _scan_rules_csv_duplicate_id,
    _csv_record_cells,
    _rules_whitespace_only_line_cells,
    _scan_rules_csv_whitespace_only_line,
    _CURLY_OPEN,
    _CURLY_CLOSE,
    _OR_LINE,
    _alternative_needs_straight_quotes,
    _rules_curly_quote_cells,
    _scan_rules_csv_curly_quotes,
    _scan_person_names_duplicate_row,
    _DUPLICATE_KEY_SUFFIXES,
    _json_duplicate_keys,
    _loaded_faction_paths,
    _scan_json_duplicate_key,
    _scan_supplies_legacy_column,
    _scan_mod_info_triage_banner,
)
from .scan_compile import (  # noqa: F401
    LOOSE_SCRIPT_JANINO_PATTERNS,
    _version_major_of,
    dependency_version_major_conflicts,
    _scan_dependency_version_major,
    _scan_loose_script_janino_risk,
    _format_compile_error,
    _scan_compile_check,
    _apply_janino_outcome,
)
from .scan_campaign import (  # noqa: F401
    _declared_spec_ids,
    _scan_core_campaign_plugin_reregistered,
    _MEMORY_FLAG_CHECK,
    _PERSISTENT_FLAG_CHECK,
    _scan_system_generation_unguarded,
    _system_lookup_null_guarded,
    _lookup_null_guarded,
    _scan_campaign_identifier_context,
    REMOVED_MARKET_CONDITION_IDS,
    _CONDITIONS_FIELD_REF,
    _scan_removed_market_condition_ids,
    _VARIABLE_LOOKUP_DEREF,
    _scan_unguarded_variable_lookup,
    _NEX_SECTOR_MANAGER_IMPORT,
    _NEX_CORVUS_CALL,
    _scan_nexerelin_corvus_mode_import,
    _COORDINATE_NUMBER,
    _VECTOR_LITERAL_PATTERN,
    _HYPERSPACE_TOUCH_PATTERN,
    _TERRAIN_GRID_LITERAL_PATTERN,
    _scan_hardcoded_hyperspace_coordinates,
    _scan_hardcoded_terrain_grid_size,
    LEGACY_MARKET_CONDITIONS,
    _scan_legacy_market_conditions,
)
from .scan_fleets import (  # noqa: F401
    _FLEET_FACTORY_V3,
    _FLEET_SIZE_MULT_KEY,
    _SECTOR_API,
    _scan_legacy_event_report,
    _scan_bare_market_fleet_source,
    ORBIT_CALL_ARG_INDICES,
    _ORBIT_CALL_NAME_PATTERN,
    _ZERO_LITERAL_PATTERN,
    _ORBIT_GUARD_PATTERN,
    _looks_like_division,
    _classify_orbit_argument,
    _scan_orbit_period_hazards,
    _scan_module_captain_personality_risk,
    _external_memory_keys_harmless,
    _JDK_FOR_PROCGEN,
    _scan_procgen_call_arguments,
    _scan_temporary_market_fleet_source,
    _ADVANCE_RE,
    _MARKET_WORK_RE,
    _TIMER_GUARD_RE,
    _scan_per_frame_market_work,
    _SPAWN_SHIP_CALL_PATTERN,
    _scan_spawned_ship_captain_personality_risk,
)
from .scan_jarchecks import (  # noqa: F401
    _scan_jar_linkage,
    _scan_jar_interface_methods,
    _scan_script_sandbox_forbidden_api,
    _scan_bundled_library_classes,
    _vanilla_api_jar_class_info,
    _vanilla_loose_script_fqns,
    _scan_vanilla_duplicated_classes,
    _scan_obfuscated_internal_api_use,
    _REFERENCE_INSTALLS,
    _OLD_VANILLA_CLASSES,
    _old_vanilla_api_classes,
    _scan_retired_vanilla_class_copy,
    _SOURCE_ROOTS,
    _JAVA_METHOD,
    _scan_bundled_source_stale,
    _scan_rc8_signature_changed,
    LEGACY_VANILLA_CLASSES,
    _load_rc8_vanilla_loose_script_classes,
    VANILLA_LOOSE_SCRIPT_CLASSES,
    _console_command_classes,
)
from .scan_settings import (  # noqa: F401
    _REPOINTABLE_SCRIPT_CSVS,
    _mod_declared_script_rows,
    _REPLACE_IGNORED_SUFFIX,
    _CREATE_EMPTY_FLEET,
    _fleet_type_names,
    _scan_fleet_type_names,
    _scan_procgen_mod_body_leak,
    _scan_replace_array,
    _settings_value_changes,
    _scan_settings_keys_missing,
)
from .scan_combat import (  # noqa: F401
    PER_WEAPON_PLUGIN_INTERFACES,
    COMBAT_STATE_TYPES,
    _COMBAT_STATE_DESCRIPTORS,
    _SOURCE_STATIC_STATE,
    _HULLMOD_BASES,
    _SOURCE_HULLMOD_FIELD,
    _looks_like_constant,
    _HULK_SPAWN_CALLS,
    _HULK_IF,
    HULK_DEATH_GUARD_KEY_SUFFIX,
    _hulk_block_spawns,
    hulk_death_effect_sites,
    _scan_hulk_death_effect_repeats,
    _scan_saved_object_holds_market_ref,
    _scan_hullmod_instance_state,
    _scan_rules_firebest_populate_options,
    _scan_weapon_effect_static_state,
)
from .scan_ships import (  # noqa: F401
    _unregistered_skill_ids,
    _scan_unregistered_skill_set,
    WEAPON_SLOT_SKIP_TYPES,
    WEAPON_SLOT_SIZE_RANK,
    HULL_MOD_COST_COLUMN_BY_SIZE,
    _csv_id_index,
    _float_or,
    _ship_file_index,
    _skin_index,
    _skin_weapon_slot_changes,
    _resolve_hull_id,
    _wpn_type_size_index,
    MOUNT_OVERRIDE_FITS,
    BAY_ADDING_HULL_MODS,
    _override_fits,
    _weapon_slot_type_compatible,
    _system_type_index,
    carrier_bays_without_evidence,
    _scan_carrier_bays_proposal,
    _resolve_variant_hull_and_slots,
    _scan_variant_validity,
)


def _scan_metadata(root: Path, result: ScanResult) -> None:
    path = root / "mod_info.json"
    if not path.exists():
        result.add(id="missing-mod-info", category="metadata", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation="mod_info.json was not found at the mod root.")
        nested_roots = [child.name for child in root.iterdir() if child.is_dir() and (child / "mod_info.json").is_file()]
        if len(nested_roots) == 1:
            result.add(id="wrapper-directory-layout", category="metadata", severity="medium", classification="REVIEW", confidence="DETERMINISTIC", explanation="A single nested directory contains mod_info.json. Select that directory after extracting the release archive; Bridgeforge will not implicitly change the input root.", evidence=nested_roots)
        return
    try:
        metadata_text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        _json_encoding_finding(result, "metadata", "mod_info.json", exc)
        return
    except OSError as exc:
        result.add(id="unreadable-mod-info", category="metadata", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation=f"mod_info.json could not be read: {exc}", file="mod_info.json")
        return
    try:
        metadata, tolerances = _parse_json(metadata_text)
    except json.JSONDecodeError as exc:
        result.add(id="unverified-mod-info-syntax", category="metadata", severity="high", classification="UNKNOWN", confidence="DETERMINISTIC", explanation=f"A strict JSON parser rejected mod_info.json ({exc}). Metadata could not be trusted for environment inference.", file="mod_info.json")
        return
    if not isinstance(metadata, dict):
        result.add(id="invalid-mod-info", category="metadata", severity="critical", classification="MANUAL", confidence="DETERMINISTIC", explanation="mod_info.json must contain a JSON object.", file="mod_info.json")
        return
    result.metadata = metadata
    result.metadata_parse_mode = "STRICT" if not tolerances else "+".join(sorted(tolerances)).upper()
    _emit_json_tolerance_findings(result, "metadata", "mod_info.json", tolerances)
    game_version = metadata.get("gameVersion") or metadata.get("game_version")
    if game_version:
        result.declared_starsector = str(game_version)
        result.estimated_starsector = str(game_version)
    dependencies = metadata.get("dependencies") or metadata.get("requiredDependencies") or []
    if dependencies:
        result.add(id="declared-dependencies", category="dependencies", severity="info", classification="SAFE", confidence="DETERMINISTIC", explanation="Dependency declarations were found.", file="mod_info.json", evidence=[str(item) for item in dependencies])


def _scan_mod_info_jar_missing(root: Path, result: ScanResult) -> None:
    """Each mod_info.json "jars" entry that doesn't exist under the mod root.

    Xenoargh's EZFaction and AI Overhaul originals both list "jars/LazyLib.jar" (read 2026-09-15:
    In operation/Xenoargh-EZFaction/original and In operation/Xenoargh-AI-Overhaul/original), and
    neither ships it. Starsector is asked to load a jar that isn't there; whether that is a Fatal
    dialog, a silent skip, or something else has not been confirmed in game, so this is reported as
    a launch blocker to verify, not a confirmed crash.
    """
    declared = result.metadata.get("jars")
    if not isinstance(declared, list):
        return
    missing = sorted(
        entry for entry in declared
        if isinstance(entry, str) and entry.strip() and not (root / entry).is_file()
    )
    if missing:
        result.add(
            id="mod-info-jar-missing",
            category="metadata",
            severity="high",
            classification="MANUAL",
            confidence="DETERMINISTIC",
            explanation="mod_info.json's \"jars\" list names a jar that does not exist under the mod root; Starsector is asked to load it at startup. Treat this as a launch blocker until verified in game.",
            file="mod_info.json",
            evidence=missing,
        )


def _scan_jars(root: Path, result: ScanResult) -> list[Path]:
    jars = _loaded_mod_jars(root)
    bundled: Counter[str] = Counter()
    for jar in jars:
        entry: dict[str, object] = {"path": _relative(root, jar), "class_file_majors": [], "java_levels": []}
        try:
            with zipfile.ZipFile(jar) as archive:
                entries = archive.infolist()
                uncompressed_bytes = sum(item.file_size for item in entries)
                compressed_bytes = sum(item.compress_size for item in entries)
                ratio = uncompressed_bytes / max(compressed_bytes, 1)
                if len(entries) > MAX_JAR_ENTRIES or uncompressed_bytes > MAX_JAR_UNCOMPRESSED_BYTES or ratio > MAX_JAR_COMPRESSION_RATIO:
                    result.add(id="jar-scan-limit", category="bytecode", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation=f"JAR exceeds safe scan limits ({len(entries)} entries, {uncompressed_bytes} uncompressed bytes, {ratio:.1f}:1 compression ratio).", file=_relative(root, jar))
                    result.jars.append(entry)
                    continue
                if jar.stat().st_size > LARGE_BUNDLED_JAR_BYTES:
                    result.add(id="large-bundled-archive", category="dependencies", severity="medium", classification="REVIEW", confidence="DETERMINISTIC", explanation=f"Archive is {jar.stat().st_size} bytes. Attribute its ownership and dependency role before changing or redistributing it.", file=_relative(root, jar))
                majors: set[int] = set()
                bad_entries: list[str] = []
                for item in entries:
                    member = PurePosixPath(item.filename.replace("\\", "/"))
                    if member.is_absolute() or ".." in member.parts:
                        result.add(id="jar-path-traversal", category="bytecode", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation="JAR contains an absolute or parent-directory member name; it was not opened.", file=_relative(root, jar))
                        continue
                    if item.is_dir():
                        continue
                    # Every entry is read so its CRC is checked: the Chinese Nightcross jar had entries
                    # whose CRC failed, which used to abort this jar's whole scan as "unreadable".
                    try:
                        entry_bytes = read_limited(archive, item)
                    except (zipfile.BadZipFile, OSError, NotImplementedError) as exc:
                        bad_entries.append(f"{item.filename}: {exc}")
                        continue
                    if item.filename.endswith(".class"):
                        class_bytes = entry_bytes
                        header = class_bytes[:8]
                        if header[:4] == b"\xca\xfe\xba\xbe" and len(header) == 8:
                            majors.add(int.from_bytes(header[6:8], "big"))
                            result.compiled_class_names.add(item.filename[:-6].replace("/", ".").replace("\\", "."))
                            for library, prefixes in LIBRARY_PACKAGES.items():
                                if any(prefix.replace(".", "/").encode() in class_bytes for prefix in prefixes):
                                    result.bytecode_library_references.add(library)
                            if b"Lkotlin/" in class_bytes or b"kotlin/jvm/" in class_bytes:
                                result.bytecode_library_references.add("LazyLib")  # the Kotlin runtime is LazyLib's
                            if b"java/lang/UnsupportedOperationException" in class_bytes:
                                result.add(
                                    id="bytecode-runtime-placeholder-reference",
                                    category="bytecode",
                                    severity="high",
                                    classification="REVIEW",
                                    confidence="HIGH",
                                    explanation="This compiled class references UnsupportedOperationException. It may be an unfinished callback implementation; inspect the class control flow before runtime testing.",
                                    file=_relative(root, jar),
                                    evidence=[item.filename[:-6].replace("/", ".").replace("\\", ".")],
                                )
                if bad_entries:
                    result.add(
                        id="jar-entry-unreadable",
                        category="bytecode",
                        severity="high",
                        classification="MANUAL",
                        confidence="DETERMINISTIC",
                        explanation="JAR entries fail their CRC check or cannot be decompressed. Java's class loader rejects a corrupt class the first time it is needed (a crash mid-game, not at boot); rebuild or re-download the jar. The rest of the jar was scanned.",
                        file=_relative(root, jar),
                        evidence=bad_entries[:25] + ([f"... {len(bad_entries) - 25} more"] if len(bad_entries) > 25 else []),
                    )
                entry["class_file_majors"] = sorted(majors)
                entry["java_levels"] = sorted({_java_for_major(major) for major in majors})
        except (OSError, zipfile.BadZipFile) as exc:
            result.add(id="unreadable-jar", category="bytecode", severity="high", classification="REVIEW", confidence="DETERMINISTIC", explanation=f"JAR could not be inspected: {exc}", file=_relative(root, jar))
        result.jars.append(entry)
        for library, pattern in LIBRARY_PATTERNS.items():
            if pattern.search(jar.name):
                bundled[library] += 1
                severity = "high" if library == "Kotlin runtime" else "info"
                result.add(id=f"bundled-{library.lower().replace(' ', '-')}", category="dependencies", severity=severity, classification="REVIEW", confidence="HIGH", explanation=f"Bundled {library} archive detected. Confirm it does not conflict with the target dependency strategy.", file=_relative(root, jar))
    for library, count in bundled.items():
        if count > 1:
            result.add(id=f"duplicate-{library.lower().replace(' ', '-')}", category="dependencies", severity="high", classification="REVIEW", confidence="DETERMINISTIC", explanation=f"{count} bundled archives match {library}; duplicate classes or versions are possible.")
    return jars


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


def _annotate_source_reachability(root: Path, result: ScanResult) -> None:
    """Resolve only unambiguous local class-qualified calls from configured roots."""
    integrity = result.migration_context.get("configured_class_integrity", {})
    entrypoints = set(integrity.get("configured_entrypoint_sources", []))
    source_index = _source_class_index(root)
    by_simple_name: dict[str, set[str]] = {}
    for class_name, file in source_index.items():
        by_simple_name.setdefault(class_name.rsplit(".", 1)[-1], set()).add(file)
    calls: dict[str, list[str]] = {}
    for fact in result.source_facts:
        if fact.get("kind") == "call_edge":
            calls.setdefault(str(fact["file"]), []).append(str(fact["value"]))
    reachable = set(entrypoints)
    pending = list(sorted(entrypoints))
    resolved_edges: list[dict[str, str]] = []
    uncertain_edges = 0
    while pending:
        source = pending.pop()
        for edge in calls.get(source, []):
            _, _, select = edge.partition("->")
            receiver, separator, _ = select.partition(".")
            candidates = by_simple_name.get(receiver, set()) if separator else set()
            if len(candidates) != 1:
                uncertain_edges += 1
                continue
            target = next(iter(candidates))
            resolved_edges.append({"from": source, "to": target, "call": select})
            if target not in reachable:
                reachable.add(target)
                pending.append(target)
    result.migration_context["source_reachability"] = {
        "configured_entrypoint_sources": sorted(entrypoints),
        "reachable_local_sources": sorted(reachable),
        "resolved_local_edges": sorted(resolved_edges, key=lambda item: (item["from"], item["to"], item["call"])),
        "uncertain_call_edge_count": uncertain_edges,
        "limitation": "Only unambiguous local class-qualified calls are followed; unqualified, instance, inherited, reflective, and dependency calls remain unresolved.",
    }
    tracked = {"runtime-placeholder-unsupported-operation", "campaign-spawn-registration-disabled", "missing-custom-ui-button-pressed-callback", "legacy-custom-dialog-delegate-signature"}
    for finding in result.findings:
        if finding.id not in tracked or not finding.file:
            continue
        if finding.file in entrypoints and "reachability: configured-entrypoint" not in finding.evidence:
            finding.evidence.append("reachability: configured-entrypoint")
        elif finding.file in reachable and "reachability: reachable-local-call" not in finding.evidence:
            finding.evidence.append("reachability: reachable-local-call")


def _local_class_names(root: Path) -> set[str]:
    """Classes the mod defines itself, in its loose sources or its jars (dotted names)."""
    names = set(_source_class_index(root))
    for _jar, _member, data in _iter_jar_class_files(root):
        info = _parse_class_file(data)
        if info is not None and info.this_class:
            names.add(info.this_class.replace("/", "."))
    return names


def _attribute_library_usage(result: ScanResult) -> None:
    dependencies = " ".join(map(str, result.metadata.get("dependencies") or result.metadata.get("requiredDependencies") or [])).lower()
    calls = [fact.get("value", "") for fact in result.source_facts if fact.get("kind") == "method_invocation"]
    # The mod's own classes are never a library's, even in a library-looking package.
    local_classes = _local_class_names(Path(result.input_path)) if result.input_path else set()
    for library, prefixes in LIBRARY_PACKAGES.items():
        imports = [item for item in result.imports if item not in local_classes and any(item.startswith(prefix) for prefix in prefixes)]
        simple_names = {item.rsplit(".", 1)[-1] for item in imports if not item.endswith(".*")}
        source_calls = [call for call in calls if call.split(".", 1)[0] in simple_names]
        # "Bundled" means a matching jar actually exists under the mod root, not merely that
        # mod_info.json's "jars" list names one: EZFaction and AI Overhaul (Xenoargh) both declare
        # "jars/LazyLib.jar" without shipping it (read 2026-09-15), which would hide their real,
        # undeclared LazyLib dependency (48 javac errors, found later by compile-check) if a
        # declared-but-absent entry counted as bundled. result.jars is already filtered to existing
        # files by _loaded_mod_jars()/_scan_jars(), but the existence check is repeated explicitly
        # here so this invariant holds even if that upstream filtering ever changes.
        bundled = any(
            LIBRARY_PATTERNS[library].search(str(item.get("path", "")))
            and (Path(result.input_path) / str(item.get("path", ""))).is_file()
            for item in result.jars
        )
        declared = library.lower() in dependencies or library.replace("Lib", "").lower() in dependencies
        bytecode_referenced = library in result.bytecode_library_references
        if declared or bundled or imports:
            result.library_usage.append({"library": library, "declared": declared, "bundled": bundled, "imported": bool(imports), "source_called": bool(source_calls), "bytecode_referenced": bytecode_referenced, "evidence": {"imports": imports, "source_calls": source_calls}})
            # A jar's own bytecode references count too: ClearCommands' jar calls org.lazywizard 42
            # times with no loose source, so revive's undeclared-library-dependency fix declared
            # LazyLib and this check then called it unreferenced (found 2026-09-27, P15 item 14).
            if declared and not bundled and not imports and not bytecode_referenced:
                result.add(id="declared-library-unreferenced", category="dependencies", severity="medium", classification="REVIEW", confidence="DETERMINISTIC", explanation="A declared library has no bundled, import, or source-call evidence. Confirm whether it is required before removing or changing it.", evidence=[library])
            if imports and not declared and not bundled and not bytecode_referenced and _library_import_only(Path(result.input_path), result, [prefix.replace(".", "/") for prefix in prefixes]):
                pass  # an unused import compiled away; reported once as library-import-unused-in-jar
            elif imports and library == "Nexerelin" and _only_nexerelin_custom_starts(Path(result.input_path), prefixes):
                pass  # reported once as optional-library-integration (registered:customStarts.json)
            elif imports and not declared and not bundled:
                result.add(
                    id="source-library-dependency-undeclared",
                    category="dependencies",
                    severity="high",
                    classification="REVIEW",
                    confidence="DETERMINISTIC",
                    explanation=f"Source imports {library}, but mod_info.json does not declare it and no bundled {library} JAR was found. Determine whether the library is mandatory or an optional integration before changing metadata or source.",
                    file="mod_info.json",
                    evidence=[library, *imports],
                )


def _dependency_compatibility_context(result: ScanResult) -> None:
    """Record dependency evidence without guessing API replacements or versions."""
    raw_declared = result.metadata.get("dependencies") or result.metadata.get("requiredDependencies") or []
    declared: list[dict[str, str | None]] = []
    normalized: set[str] = set()
    for item in raw_declared:
        if isinstance(item, dict):
            dependency_id = str(item.get("id") or "").strip() or None
            dependency_name = str(item.get("name") or "").strip() or None
        else:
            dependency_id = str(item).strip() or None
            dependency_name = None
        declared.append({"id": dependency_id, "name": dependency_name})
        normalized.update(re.sub(r"[^a-z0-9]", "", value.lower()) for value in (dependency_id, dependency_name) if value)
    direct_apis: list[dict[str, object]] = []
    for finding in result.findings:
        # external-mod-api-import-declared (SAFE): the same direct-API-usage evidence, just for a
        # dependency mod_info.json already declares - still real for a consumer reasoning about
        # cross-mod integration, so both ids are harvested here.
        if finding.id not in ("external-mod-api-import", "external-mod-api-import-declared") or not finding.evidence:
            continue
        dependency = finding.evidence[0]
        key = re.sub(r"[^a-z0-9]", "", dependency.lower())
        finding_imports = [item for item in finding.evidence[1:] if not item.startswith("line:")]
        direct_apis.append({"dependency": dependency, "declared": key in normalized, "imports": finding_imports})
    result.migration_context["dependency_compatibility"] = {
        "declared_dependencies": declared,
        "direct_api_dependencies": direct_apis,
        "library_usage": result.library_usage,
        "limitation": "Static evidence does not establish an installed dependency version or API-symbol compatibility.",
    }


def _infer_environment(result: ScanResult) -> None:
    majors = [major for jar in result.jars for major in jar.get("class_file_majors", [])]
    if majors:
        result.estimated_java = _java_for_major(max(majors))
        if max(majors) > 61:
            result.add(id="target-bytecode-exceeds-profile", category="java", severity="high", classification="REVIEW", confidence="DETERMINISTIC", explanation=f"Detected {_java_for_major(max(majors))} bytecode exceeds target Java {result.target.java}.")
    if result.estimated_starsector == "UNKNOWN":
        result.add(id="version-inference-blocked", category="environment", severity="medium", classification="UNKNOWN", confidence="DETERMINISTIC", explanation="No trustworthy declared Starsector version was available. Do not make confident compatibility or migration claims until metadata or independent target evidence is supplied.")


def _is_mission_source(root: Path, path: Path) -> bool:
    parts = path.relative_to(root).parts
    if "data" in parts:
        index = parts.index("data")
        if index + 1 < len(parts) and parts[index + 1] == "missions":
            return True
    return False


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


def _base_game_version(version: str) -> str:
    """'0.98a-RC8' -> '0.98a'. The launcher accepts any RC of the same base version."""
    return re.sub(r"-RC\d+$", "", version.strip(), flags=re.I).lower()


def _version_series(version: str) -> str:
    """'0.98a-RC8' -> '0.98', '0.9.1a' -> '0.9.1', '0.98.x' -> '0.98'."""
    base = _base_game_version(version)
    return re.sub(r"(?:\.x|[a-z]+)$", "", base)


def _scan_mod_info_game_version(result: ScanResult) -> None:
    target_version = result.target.starsector
    declared = result.declared_starsector
    if not target_version or not declared or declared == target_version:
        return
    # A generic target ('0.98.x', the default) used to skip this check entirely, so the 2026-09-14 batch
    # of 0.53a-0.9.1a mods never heard that the launcher would untick every one of them.
    if not GAME_VERSION_RC_PATTERN.match(target_version):
        if not re.fullmatch(r"\d+(?:\.\d+)*\.x", target_version.strip()) or _version_series(declared) == _version_series(target_version):
            return
        target_version = f"{_version_series(target_version)}a"
    # The launcher matches on the BASE version: mods declaring 0.98a-RC5 / 0.98a-RC7 loaded and ran
    # all week in an RC8 rig (LazyLib, LunaLib, Console Commands, MagicLib), so an older RC is fine.
    if _base_game_version(declared) == _base_game_version(target_version):
        return
    result.add(
        id="mod-info-game-version-inexact",
        category="metadata",
        severity="high",
        classification="REVIEW",
        confidence="DETERMINISTIC",
        explanation=f"mod_info.json gameVersion ('{declared}') targets a different base game version than the configured target ({target_version}). The Starsector launcher unchecks a mod whose base version differs. An older release candidate of the same version (e.g. 0.98a-RC5 on RC8) is accepted, so only the base version matters.",
        file="mod_info.json",
        evidence=[f"declared:{declared}", f"target:{target_version}"],
    )


VANILLA_SHADOW_GROUP_THRESHOLD = 5


# Files whose entries the game merges by whole-entry replace, not per field (ROADMAP P14 item 15;
# Starsector wiki: "any mod added entries with keys ... the same as core game entries will see the mod
# entries replace the core game entries"). planets.json and sounds.json are read from data/config by
# the checks above; the other three are the files item 15 names (Zorg18's was engine_styles.json).
PRESET_MERGE_FILES = ("engine_styles.json", "hull_styles.json", "custom_entities.json", "sounds.json", "planets.json")


def _scan_preset_entry_overrides(root: Path, result: ScanResult, vanilla_core: Path | None) -> None:
    """A mod entry keyed like a vanilla entry replaces it for the whole game, every mod included.

    Zorg18 redefined vanilla's LOW_TECH/MIDLINE/HIGH_TECH engine styles with an old copy missing
    `contrailCampaignColor` (2026-09-20), stripping it from every ship of those styles while enabled.
    Missing fields are MANUAL; only different values are REVIEW (the override may be intended, but it
    still applies game-wide). Identical entries and mod-only ids report nothing.
    """
    if vanilla_core is None:
        return
    from .data_diff import _diff  # data_diff imports this module

    for name in PRESET_MERGE_FILES:
        mod_path, vanilla_path = root / "data" / "config" / name, vanilla_core / "data" / "config" / name
        if not (mod_path.is_file() and vanilla_path.is_file()):
            continue
        mod_data, vanilla_data = _load_lenient_json_file(mod_path), _load_lenient_json_file(vanilla_path)
        if not (isinstance(mod_data, dict) and isinstance(vanilla_data, dict)):
            continue
        if name == "sounds.json":
            # sounds.json's top-level keys are categories ("music"); the entries replaced whole are one level down,
            # and only the ids the mod names. Live evidence 2026-09-28: every Exigency session (EX-2..EX-10) loaded its
            # sounds.json, which defines 3 of vanilla's music ids, and still played vanilla's title, Corvus campaign and
            # neutral-encounter music. So compare "<category>.<id>" entries, not whole categories.
            def entries(data: dict, names: dict | None = None) -> dict:
                flat = {}
                for key, value in data.items():
                    inner = (names or data).get(key)
                    if isinstance(value, dict) and isinstance(inner, dict):
                        flat.update({f"{key}.{sub}": sub_value for sub, sub_value in value.items()})
                    else:
                        flat[key] = value
                return flat
            mod_data, vanilla_data = entries(mod_data, vanilla_data), entries(vanilla_data, mod_data)
        dropped: list[str] = []
        changed: list[str] = []
        for key in sorted(set(mod_data) & set(vanilla_data)):
            changes: list[dict] = []
            _diff(vanilla_data[key], mod_data[key], "", changes)
            lost = [c["path"] or "<whole entry>" for c in changes if c["change"] == "removed"]
            differ = [c["path"] or "<value>" for c in changes if c["change"] in ("changed", "reordered")]
            if lost:
                dropped.append(f"{key}: loses {', '.join(lost[:10])}" + (f" (+{len(lost) - 10} more)" if len(lost) > 10 else "")
                               + (f"; also changes {', '.join(differ[:5])}" if differ else ""))
            elif differ:
                changed.append(f"{key}: changes {', '.join(differ[:10])}" + (f" (+{len(differ) - 10} more)" if len(differ) > 10 else ""))
        relative = _relative(root, mod_path)
        if dropped:
            result.add(
                id="preset-entry-drops-vanilla-fields",
                category="assets",
                severity="high",
                classification="MANUAL",
                confidence="DETERMINISTIC",
                explanation=f"{name} entries replace vanilla's entry of the same id whole, for the entire game (every other mod too). These entries redefine vanilla ids without fields vanilla's current copy has, so those fields are lost game-wide while this mod is enabled; usually an old copy used as a template. Remove the entries or bring them up to date with vanilla.",
                file=relative,
                evidence=dropped[:25] + ([f"... {len(dropped) - 25} more"] if len(dropped) > 25 else []),
            )
        if changed:
            result.add(
                id="preset-entry-overrides-vanilla",
                category="assets",
                severity="medium",
                classification="REVIEW",
                confidence="DETERMINISTIC",
                explanation=f"{name} entries replace vanilla's entry of the same id whole, for the entire game. These redefine vanilla ids with different values; confirm the mod means to change them for every ship/entity in the game, not only its own.",
                file=relative,
                evidence=changed[:25] + ([f"... {len(changed) - 25} more"] if len(changed) > 25 else []),
            )


def _scan_vanilla_path_shadowing(root: Path, result: ScanResult, vanilla_core: Path | None) -> None:
    if vanilla_core is None:
        return
    data_root = root / "data"
    if not data_root.is_dir():
        return
    mod_info = _load_lenient_json_file(root / "mod_info.json")
    total_conversion = isinstance(mod_info, dict) and mod_info.get("totalConversion") is True
    shadowed: dict[str, list[tuple[Path, Path]]] = {}
    identical: list[str] = []
    for path in data_root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SHADOW_PATH_EXTENSIONS:
            continue
        relative = path.relative_to(root)
        vanilla_path = vanilla_core / relative
        if not vanilla_path.is_file():
            continue
        try:
            mod_bytes = path.read_bytes()
            vanilla_bytes = vanilla_path.read_bytes()
        except OSError:
            continue
        if mod_bytes == vanilla_bytes:
            # Byte-identical: not a shadow in any meaningful sense, it overrides vanilla with
            # vanilla. Collected here (this loop already has both files' bytes, so it is free)
            # rather than in a second walk. Real case: Rebal shipped 14 such .java copies that
            # looked like hullmod overrides and changed nothing (E14 stage 0, 2026-09-22).
            identical.append(_relative(root, path))
            continue
        shadowed.setdefault(_relative(root, path.parent), []).append((path, vanilla_path))
    if identical:
        result.migration_context["vanilla_identical_copies"] = identical
        result.add(
            id="vanilla-file-identical-copy",
            category="assets",
            severity="low",
            classification="REVIEW",
            confidence="DETERMINISTIC",
            explanation=(
                "These files are byte-identical to the vanilla file at the same data-relative path, so they "
                "override vanilla with vanilla and change nothing. A script copy is the misleading case: it "
                "looks like the mod customises that hullmod/system and it does not. Dropping them is safe and "
                "removes a file that would otherwise silently freeze vanilla's version if vanilla later changes it."
            ),
            evidence=[f"count:{len(identical)}", *identical[:25]],
        )
    # A per-folder rollup's own `count:N` evidence is easy to undercount from: E3's original "~79
    # files" estimate for Rebal counted *findings*, not the sum of every folder's own count - the
    # real number was 642 (P14 item 20). One grand total, independent of how many findings the
    # >VANILLA_SHADOW_GROUP_THRESHOLD grouping produces, is exposed here so a future investigation
    # doesn't need to re-add every finding's evidence by hand to learn the true scope.
    total_shadowed_files = sum(len(files) for files in shadowed.values())
    if total_shadowed_files:
        result.migration_context["vanilla_path_shadowing_total_files"] = total_shadowed_files
    severity = "low" if total_conversion else "critical"
    classification = "REVIEW" if total_conversion else "MANUAL"
    for folder, files in sorted(shadowed.items()):
        # A rebalance that replaces a whole vanilla folder (Xenoargh's Rebal: 498 hullmod/weapon scripts)
        # reads as one decision, not hundreds of findings burying the rest of the report.
        if len(files) > VANILLA_SHADOW_GROUP_THRESHOLD:
            listed = sorted(_relative(root, path) for path, _vanilla in files)
            result.add(
                id="vanilla-path-shadowing",
                category="assets",
                severity=severity,
                classification=classification,
                confidence="DETERMINISTIC",
                explanation=f"{len(files)} files in this folder shadow vanilla files at the same data-relative paths with different bytes. Confirm the override is intentional (a rebalance mod does this on purpose); every shadow replaces core game content, and old copies of vanilla scripts can break against the current API.",
                file=folder,
                evidence=[f"count:{len(files)}", *(["mod_info:totalConversion=true"] if total_conversion else []), *listed[:25]],
            )
            continue
        for path, vanilla_path in files:
            evidence = [f"vanilla-path:{vanilla_path.as_posix()}"]
            if total_conversion:
                evidence.append("mod_info:totalConversion=true")
            result.add(
                id="vanilla-path-shadowing",
                category="assets",
                severity=severity,
                classification=classification,
                confidence="DETERMINISTIC",
                explanation=(
                    "This total-conversion mod replaces a vanilla file at the same data-relative path; overrides are expected for a total conversion, so spot-check rather than treat as a defect."
                    if total_conversion
                    else "This mod file shadows a vanilla file at the same data-relative path with different bytes. Confirm the override is intentional; an unintended shadow silently replaces core game content."
                ),
                file=_relative(root, path),
                evidence=evidence,
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


def _scan_vanilla_script_shadow_repointable(root: Path, result: ScanResult, vanilla_core: Path | None) -> None:
    """A vanilla-path .java shadow the mod could repoint via its own CSV row instead (see above)."""
    if vanilla_core is None:
        return
    core = Path(vanilla_core)
    declared = _mod_declared_script_rows(root)
    if not declared:
        return
    for path in sorted(root.rglob("*.java")):
        relative = path.relative_to(root)
        if any(part in NON_MOD_JAR_DIRS or part.startswith("src-decompiled") for part in relative.parts):
            continue
        vanilla_path = core / relative
        if not vanilla_path.is_file():
            continue
        try:
            if path.read_bytes() == vanilla_path.read_bytes():
                # Identical to vanilla: nothing to repoint, the file simply does nothing.
                # `vanilla-file-identical-copy` reports it, and the fix there is to drop it, not
                # rename it. Without this the check told Rebal to repoint 14 no-op copies
                # (found executing E14 stage 0, 2026-09-22).
                continue
        except OSError:
            continue
        where = declared.get(path.stem)
        if where is None:
            continue
        result.add(
            id="vanilla-script-shadow-repointable",
            category="assets",
            severity="medium",
            classification="REVIEW",
            confidence="DETERMINISTIC",
            explanation=(
                "This mod replaces a vanilla script at vanilla's own path, but it does not have to: the mod already "
                "ships the row that names the class, and those CSVs merge by row id. Rename this class (e.g. "
                f"{path.stem} -> <ModPrefix>_{path.stem}) and repoint that row at the new name; vanilla's own file is "
                "then left intact, the behaviour is identical, and the override survives the next vanilla update "
                "instead of silently reverting it. Shipping the shadow keeps a copy of vanilla's script frozen at the "
                "version it was forked from."
            ),
            file=_relative(root, path),
            evidence=[f"declared-in:{where}", f"vanilla-path:{(core / relative).as_posix()}"],
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


_NEW_GAME_PLUGIN_KEYS = ("newGameSectorProcGen", "newGameCreationEntryPoint")


# RC8 industries whose plugin AoTD sets at load (javap of each mod plugin, 2026-10-04: IndustrySpecAPI.setPluginClass).
_AOTD_REPLUGGED = {"population": "AoTD Theory of Toolbox", "heavyindustry": "AoTD Vaults of Knowledge",
                   "orbitalworks": "AoTD Vaults of Knowledge", "patrolhq": "AoTD Seats of Power",
                   "militarybase": "AoTD Seats of Power", "highcommand": "AoTD Seats of Power"}


def _scan_shared_hook_overrides(root: Path, result: ScanResult, vanilla_core: Path | None) -> None:
    """Hooks only one mod can own (owner question 2026-10-04, AoTD compatibility):

    - industry-plugin-override: an industries.csv row for an RC8 industry with another plugin class. Whichever mod
      sets it last wins, silently: AoTD Theory of Toolbox sets population's plugin at load
      (AoTDToolboxTheoryPlugin: getIndustrySpec(POPULATION).setPluginClass), dropping DNEEP's
      PopulationAndInfrastructureDNEEP. Compatible form: a market condition adding to the industry through
      Industry.getDemand/getSupply.
    - new-game-plugin-override: settings.json plugins.newGameSectorProcGen / newGameCreationEntryPoint (Adjusted
      Sector); Nexerelin, Random Assortment of Things and Wide Horizons set the same keys and only one is used.
    """
    if vanilla_core is not None:
        vanilla_rows = _industry_plugins(vanilla_core / "data" / "campaign" / "industries.csv")
        for industry_id, plugin in sorted(_industry_plugins(root / "data" / "campaign" / "industries.csv").items()):
            original = vanilla_rows.get(industry_id)
            if original and plugin and plugin != original:
                result.add(
                    id="industry-plugin-override",
                    category="compatibility",
                    severity="medium",
                    classification="REVIEW",
                    confidence="HIGH",
                    explanation=(f"industries.csv gives RC8's '{industry_id}' the plugin {plugin.split('.')[-1]} (RC8: "
                                 f"{original.split('.')[-1]}). Only one plugin can run per industry; another mod that sets "
                                 "it silently replaces this one"
                                 + (f" ({_AOTD_REPLUGGED[industry_id]} sets '{industry_id}' at load)" if industry_id in _AOTD_REPLUGGED else "")
                                 + ". A market condition that adds through Industry.getDemand/getSupply works with any plugin."),
                    file="data/campaign/industries.csv",
                    evidence=[f"industry:{industry_id}", f"plugin:{plugin}", f"rc8:{original}"],
                )
    settings = root / "data" / "config" / "settings.json"
    spec = _load_lenient_json_file(settings) if settings.is_file() else None
    plugins = spec.get("plugins") if isinstance(spec, dict) else None
    for key in _NEW_GAME_PLUGIN_KEYS:
        if isinstance(plugins, dict) and isinstance(plugins.get(key), str):
            result.add(
                id="new-game-plugin-override",
                category="compatibility",
                severity="medium",
                classification="REVIEW",
                confidence="HIGH",
                explanation=(f"settings.json sets plugins.{key} to {plugins[key]}. The game uses one value for it; "
                             "Nexerelin, Random Assortment of Things and Wide Horizons set it too, so with any of them "
                             "enabled one generator is silently not used."),
                file="data/config/settings.json",
                evidence=[f"key:{key}", f"plugin:{plugins[key]}"],
            )


def _industry_plugins(path: Path) -> dict[str, str]:
    import csv as _csv
    import io as _io

    if not path.is_file():
        return {}
    try:
        rows = _csv.DictReader(_io.StringIO(path.read_text(encoding="utf-8-sig", errors="replace")))
        return {r["id"].strip(): (r.get("plugin") or "").strip() for r in rows if (r.get("id") or "").strip()
                and not r["id"].strip().startswith("#")}
    except (_csv.Error, KeyError):
        return {}


TOOLBOX_ID = "aotd_theory_of_toolbox"


TOOLBOX_FORK_MINIMUM = (1, 0, 14)  # the Scheduler Fork installed 2026-10-10 is 1.0.14-spp13 (docs/AOTD_COMPAT_PLAN.md)


def _version_tuple(text: object) -> tuple[int, ...]:
    """Leading numeric dotted part of a version string: `1.0.14-spp13` -> (1, 0, 14); no digits -> ()."""
    match = re.match(r"\s*v?(\d+(?:\.\d+)*)", str(text or ""))
    return tuple(int(p) for p in match.group(1).split(".")) if match else ()


def toolbox_version_gaps(root: Path, provider_roots: list[Path] | None) -> list[dict]:
    """Declared Toolbox dependency versions below the installed provider, or below the fork's minimum when no
    provider is found. Seats of Power and Vaults of Knowledge declare 1.0.11; the fork is 1.0.14-spp13."""
    info = _load_lenient_json_file(Path(root) / "mod_info.json") if (Path(root) / "mod_info.json").is_file() else None
    declared = [d for d in (info.get("dependencies") if isinstance(info, dict) else None) or [] if isinstance(d, dict) and d.get("id") == TOOLBOX_ID]
    if not declared:
        return []
    installed: tuple[int, ...] = ()
    if provider_roots:
        from .substitutes import provider_index

        versions = [_version_tuple(p.version) for p in provider_index([Path(e) for e in provider_roots], exclude=Path(root)) if p.mod_id == TOOLBOX_ID]
        installed = max(versions, default=())
    required = installed or TOOLBOX_FORK_MINIMUM
    gaps = []
    for dep in declared:
        wanted = _version_tuple(dep.get("version") if not isinstance(dep.get("version"), dict) else ".".join(str(dep["version"].get(k, 0)) for k in ("major", "minor", "patch")))
        if wanted and wanted < required:
            gaps.append({"declared": ".".join(map(str, wanted)), "required": ".".join(map(str, required)), "source": "installed provider" if installed else "fork minimum"})
    return gaps


def _scan_aotd_toolbox_version(root: Path, result: ScanResult, provider_roots: list[Path] | None) -> None:
    for gap in toolbox_version_gaps(root, provider_roots):
        result.add(
            id="aotd-toolbox-version-below-minimum",
            category="dependencies",
            severity="medium",
            classification="REVIEW",
            confidence="MEDIUM",
            explanation=(f"mod_info.json asks for Theory of Toolbox {gap['declared']}, below {gap['required']} ({gap['source']}). "
                         "The Scheduler Fork replaces Kaysaar's Toolbox and rewrites the economy refresh path; whether this mod "
                         "was tested against it is unproven. Re-test with the fork before raising the declared version."),
            file="mod_info.json",
            evidence=[f"dependency:{TOOLBOX_ID}", f"declared:{gap['declared']}", f"required:{gap['required']}", f"source:{gap['source']}"],
        )


def _scan_replace_drops_rc8_entries(root: Path, result: ScanResult, vanilla_core: Path | None) -> None:
    """A mod_info `replace` entry for an RC8 file the mod's copy does not fully restate (ROADMAP 42). Ironclads
    replaced commodities.csv, market_conditions.csv and hull_mods.csv with 0.7 copies, dropping `crew`, AI cores, every
    deposit condition and 92 hull mods (64 used by RC8's own code); nothing flagged it (2026-10-05)."""
    if vanilla_core is None:
        return
    import csv as _csv
    import io as _io

    info = _load_lenient_json_file(root / "mod_info.json") if (root / "mod_info.json").is_file() else None
    replaced = info.get("replace") if isinstance(info, dict) else None
    for rel in replaced if isinstance(replaced, list) else []:
        if not isinstance(rel, str):
            continue
        ours, theirs = root / rel, vanilla_core / rel
        if not theirs.is_file():
            continue

        def ids(path: Path) -> set[str]:
            if not path.is_file():
                return set()
            if path.suffix.lower() == ".csv":
                text = path.read_text(encoding="utf-8-sig", errors="replace")
                rows = list(_csv.DictReader(_io.StringIO(text)))
                key = "id" if rows and "id" in rows[0] else (next(iter(rows[0])) if rows else None)
                return {(r.get(key) or "").strip() for r in rows if key and (r.get(key) or "").strip()
                        and not (r.get(key) or "").strip().startswith("#")}
            spec = _load_lenient_json_file(path)
            return set(spec) if isinstance(spec, dict) else set()

        lost = sorted(ids(theirs) - ids(ours))
        if not lost:
            continue
        result.add(
            id="replace-drops-rc8-entries",
            category="compatibility",
            severity="high",
            classification="REVIEW",
            confidence="HIGH",
            explanation=(f"mod_info.json replaces {rel}, and the mod's copy lacks {len(lost)} entr"
                         f"{'y' if len(lost) == 1 else 'ies'} RC8's has. RC8's own code may look them up by id "
                         "(Ironclads' hull_mods.csv dropped 64 hull mods RC8 uses). Unless the mod deliberately "
                         "removes them, add its rows instead of replacing the file."),
            file="mod_info.json",
            evidence=[f"replace:{rel}", f"lost:{len(lost)}", *[f"id:{i}" for i in lost[:5]]],
        )


_EXTERNAL_DEPENDENCY_PREFIXES = ("org.lazywizard", "org.magiclib", "org.dark", "lunalib", "exerelin")


_RULE_COMMAND_PATTERN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)")


def _is_external_dependency_class(fqn: str) -> bool:
    """True when a FQN matches a known third-party library/mod API package we cannot see the jar for."""
    lower = fqn.lower()
    if lower.startswith(_EXTERNAL_DEPENDENCY_PREFIXES):
        return True
    if lower.startswith("data.scripts.util."):
        simple_name = fqn.rsplit(".", 1)[-1]
        if simple_name.lower().startswith("magic"):
            return True
    return False


def _collect_csv_column_class_refs(path: Path, column: str, root: Path, references: list[tuple[str, str, str]]) -> None:
    header = _csv_header(path)
    if not header or column not in header:
        return
    rows = _read_csv_rows(path)
    if not rows:
        return
    relative = _relative(root, path)
    for row in rows:
        values = list(row.values())
        if values and str(values[0] or "").strip().startswith("#"):
            continue
        value = (row.get(column) or "").strip()
        if not value or value.startswith("#"):
            continue
        references.append((relative, column, value))


def _scan_data_class_references_missing(root: Path, result: ScanResult, vanilla_core: Path | None, provider_roots: list[Path] | None = None) -> None:
    """Every fully qualified class named in mod data must resolve to a class Starsector can actually load.

    Checked against: this mod's loaded jars (result.compiled_class_names), a loose data/scripts .java source
    (FQN via package+class name), vanilla (when vanilla_core is supplied), or a known third-party library
    package (classified UNKNOWN/external, since that dependency's jar is not visible to BridgeForge). A row
    or line commented out with '#' is skipped, so it never fires for a deliberately disabled reference (e.g.
    Exigency's commented-out exigency_RepulsorRenderer combat_radar_plugins.csv row).
    """
    references: list[tuple[str, str, str]] = []

    _collect_csv_column_class_refs(root / "data" / "hullmods" / "hull_mods.csv", "script", root, references)
    _collect_csv_column_class_refs(root / "data" / "shipsystems" / "ship_systems.csv", "script", root, references)
    _collect_csv_column_class_refs(root / "data" / "campaign" / "submarkets.csv", "script", root, references)
    _collect_csv_column_class_refs(root / "data" / "campaign" / "industries.csv", "plugin", root, references)

    weapon_data_path = root / "data" / "weapons" / "weapon_data.csv"
    weapon_header = _csv_header(weapon_data_path) or []
    for column in weapon_header:
        if column and "script" in column.lower():
            _collect_csv_column_class_refs(weapon_data_path, column, root, references)

    for suffix in ("*.system",):
        for path in (root / "data" / "shipsystems").rglob(suffix) if (root / "data" / "shipsystems").is_dir() else []:
            data = _load_lenient_json_file(path)
            if not isinstance(data, dict):
                continue
            for field in ("statsScript", "aiScript"):
                value = data.get(field)
                if isinstance(value, str) and value.strip() and not value.strip().startswith("#"):
                    references.append((_relative(root, path), field, value.strip()))

    for suffix in ("*.wpn", "*.proj"):
        for path in root.rglob(suffix):
            data = _load_lenient_json_file(path)
            if not isinstance(data, dict):
                continue
            for field in ("onHitEffect", "everyFrameEffect", "onFireEffect"):
                value = data.get(field)
                if isinstance(value, str) and value.strip() and not value.strip().startswith("#"):
                    references.append((_relative(root, path), field, value.strip()))

    # .skill files name their effect classes under effectGroups[].effects[].script (Ironclads' ordnance_expert.skill named
    # data.characters.skills.scripts.OrdnanceExpertEffect1, a 0.7.2 vanilla loose script RC8 no longer has: Fatal
    # 'Error loading [...]' at startup, GRP10L-20261005).
    for skill in root.rglob("*.skill"):
        if "disabled_files" in skill.relative_to(root).parts:
            continue
        spec = _load_lenient_json_file(skill)
        for group in (spec.get("effectGroups") if isinstance(spec, dict) else None) or []:
            for effect in (group.get("effects") if isinstance(group, dict) else None) or []:
                script = effect.get("script") if isinstance(effect, dict) else None
                if isinstance(script, str) and script.strip() and not script.strip().startswith("#"):
                    references.append((_relative(root, skill), "skill-effect-script", script.strip()))

    rules_path = root / "data" / "campaign" / "rules.csv"
    rules_header = _csv_header(rules_path) or []
    if "script" in rules_header and vanilla_core is not None:
        rules_rows = _read_csv_rows(rules_path) or []
        relative = _relative(root, rules_path)
        for row in rules_rows:
            values = list(row.values())
            if values and str(values[0] or "").strip().startswith("#"):
                continue
            script_text = row.get("script") or ""
            for line in script_text.splitlines():
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("$"):
                    continue
                match = _RULE_COMMAND_PATTERN.match(line)
                if not match:
                    continue
                command = match.group(1)
                references.append((relative, "script(rule-command)", f"com.fs.starfarer.api.impl.campaign.rulecmd.{command}"))
            # Conditions run commands too ("!Nex_Commission hasFactionCommission"), resolved at load like scripts:
            # Hiver Swarm's Nexerelin-only condition stopped RC8 at startup without Nexerelin (GRP8B-20261005).
            for line in (row.get("conditions") or "").splitlines():
                line = line.strip().lstrip("!").strip()
                if not line or line.startswith("#") or line.startswith("$"):
                    continue
                match = _RULE_COMMAND_PATTERN.match(line)
                if match:
                    references.append((relative, "script(rule-command)", f"com.fs.starfarer.api.impl.campaign.rulecmd.{match.group(1)}"))

    settings_path = root / "data" / "config" / "settings.json"
    settings = _load_lenient_json_file(settings_path)
    if isinstance(settings, dict):
        plugins = settings.get("plugins")
        relative = _relative(root, settings_path)
        if isinstance(plugins, dict):
            for key, value in plugins.items():
                if isinstance(value, str) and value.strip():
                    references.append((relative, f"plugins.{key}", value.strip()))
        elif isinstance(plugins, list):
            for value in plugins:
                if isinstance(value, str) and value.strip():
                    references.append((relative, "plugins", value.strip()))

    mod_info_path = root / "mod_info.json"
    mod_info = _load_lenient_json_file(mod_info_path)
    if isinstance(mod_info, dict):
        mod_plugin = mod_info.get("modPlugin")
        if isinstance(mod_plugin, str) and mod_plugin.strip():
            references.append((_relative(root, mod_info_path), "modPlugin", mod_plugin.strip()))

    local_source_fqns = set(_source_class_index(root))
    vanilla_jar_classes = _vanilla_api_jar_class_info(vanilla_core) if vanilla_core is not None else {}
    vanilla_loose_fqns = _vanilla_loose_script_fqns(vanilla_core) if vanilla_core is not None else set()
    local_simple_names = {name.rsplit(".", 1)[-1] for name in result.compiled_class_names} | {
        name.rsplit(".", 1)[-1] for name in local_source_fqns
    }
    # Vanilla rule commands also live in rulecmd sub-packages (e.g. rulecmd.salvage.AddBarEvent), so a bare
    # rules.csv command resolves by simple name against any vanilla class under a ".rulecmd." package.
    vanilla_rulecmd_simple_names = {
        name.rsplit(".", 1)[-1] for name in (set(vanilla_jar_classes) | vanilla_loose_fqns) if ".rulecmd." in name
    }

    # A declared dependency's own jar (SEEKER 0.6.6's weapons name MagicLib's data.scripts.weapons.MagicVectorThruster,
    # which MagicLib 1.5.6 still ships for compatibility; 2026-09-28). Needs explicit provider_roots.
    dependency_classes = _dependency_jar_class_names(root, provider_roots)

    def resolve(fqn: str, is_rule_command: bool) -> str:
        if fqn in result.compiled_class_names or fqn in local_source_fqns or fqn in dependency_classes:
            return "resolved"
        if vanilla_core is not None and (fqn in vanilla_jar_classes or fqn in vanilla_loose_fqns):
            return "resolved"
        if is_rule_command and fqn.rsplit(".", 1)[-1] in local_simple_names:
            return "resolved"
        if is_rule_command and fqn.rsplit(".", 1)[-1] in vanilla_rulecmd_simple_names:
            return "resolved"
        if _is_external_dependency_class(fqn):
            return "external"
        if vanilla_core is None and (fqn.startswith("com.fs.starfarer.") or fqn.startswith("com.fs.")):
            # This is plausibly a vanilla engine class; without vanilla_core we cannot tell a genuine
            # vanilla reference (normal) from a removed/renamed API (a real bug) apart.
            return "vanilla-unverified"
        return "missing"

    seen: set[tuple[str, str, str]] = set()
    for file, field, class_name in references:
        key = (file, field, class_name)
        if key in seen:
            continue
        seen.add(key)
        status = resolve(class_name, field == "script(rule-command)")
        if status == "resolved":
            continue
        if status == "external":
            result.add(
                id="data-class-reference-missing",
                category="content",
                severity="low",
                classification="UNKNOWN",
                confidence="LOW",
                explanation="This class reference matches a known third-party library/mod API package (LazyLib, MagicLib, org.dark, LunaLib, Nexerelin). BridgeForge cannot see that dependency's jar, so this cannot be verified as present; treat it as an external dependency reference, unverified, not a defect.",
                file=file,
                evidence=[f"field:{field}", f"class:{class_name}", "external dependency, unverified"],
            )
            continue
        if status == "vanilla-unverified":
            result.add(
                id="data-class-reference-missing",
                category="content",
                severity="low",
                classification="UNKNOWN",
                confidence="LOW",
                explanation="This class reference is under com.fs.* (Starsector's own package namespace) and could not be checked against the mod's jars or sources. No --vanilla-core was supplied, so BridgeForge cannot distinguish an ordinary vanilla-engine class reference from a genuinely removed/renamed API; supply --vanilla-core to verify.",
                file=file,
                evidence=[f"field:{field}", f"class:{class_name}", "vanilla class, unverified (no vanilla core supplied)"],
            )
            continue
        result.add(
            id="data-class-reference-missing",
            category="content",
            severity="critical",
            classification="MANUAL",
            confidence="HIGH" if vanilla_core is not None else "MEDIUM",
            explanation="A fully qualified class named in mod data does not resolve to any class in this mod's loaded jars, a loose data/scripts source file, or (when supplied) the vanilla core. Loading this row/field at runtime throws a class-not-found-class crash. Confirm whether the class was removed, renamed, or simply not rebuilt into the jar, then restore it or remove the reference.",
            file=file,
            evidence=[f"field:{field}", f"class:{class_name}"],
        )


def _mod_info_declares_dependency(result: ScanResult, dependency_id: str) -> bool:
    dependencies = result.metadata.get("dependencies") or result.metadata.get("requiredDependencies") or []
    target = dependency_id.strip().lower()
    for item in dependencies:
        if isinstance(item, dict):
            candidates = (str(item.get("id") or ""), str(item.get("name") or ""))
        else:
            candidates = (str(item),)
        if any(candidate.strip().lower() == target for candidate in candidates):
            return True
    return False


def _scan_revenantlib_fold_conflict(result: ScanResult) -> None:
    """MANUAL: mod_info.json declares both revenantlib and an id `dependency_successors.json` records
    as folded into it (`bridgeforge fold`, roadmap P14 item 10; docs/DEPENDENCY_STRATEGY.md).

    Folding keeps the original mod's ids and class names unchanged, so enabling the original mod
    alongside RevenantLib double-registers the same ids and classes. Local imports: fold.py and
    substitutes.py both import this module at load time, so importing either back at module scope
    here would cycle; deferring to call time (after both are fully loaded) avoids that, the same way
    `_scan_compile_check` defers its import of compile_check.
    """
    if not _mod_info_declares_dependency(result, "revenantlib"):
        return
    from .fold import FOLD_KIND
    from .substitutes import load_successors

    folded_ids = {
        str(entry.get("match") or "").strip().lower()
        for entry in load_successors()
        if entry.get("kind") == FOLD_KIND and entry.get("match")
    }
    if not folded_ids:
        return
    dependencies = result.metadata.get("dependencies") or result.metadata.get("requiredDependencies") or []
    conflicts: list[str] = []
    for item in dependencies:
        candidate = str(item.get("id") or "").strip() if isinstance(item, dict) else str(item).strip()
        if candidate and candidate.lower() != "revenantlib" and candidate.lower() in folded_ids:
            conflicts.append(candidate)
    if not conflicts:
        return
    result.add(
        id="revenantlib-fold-conflict",
        category="dependencies",
        severity="high",
        classification="MANUAL",
        confidence="DETERMINISTIC",
        explanation=(
            f"mod_info.json declares both revenantlib and {', '.join(sorted(set(conflicts)))}, which "
            "RevenantLib has folded in with the same ids and class names; enabling both together "
            "double-registers them. Declare only revenantlib."
        ),
        file="mod_info.json",
        evidence=sorted(set(conflicts)),
    )


def _drop_library_findings_judged_elsewhere(result: ScanResult) -> None:
    """source-library-dependency-undeclared says only "source imports it"; undeclared-library-dependency (declare it:
    standing approval) and optional-library-integration (guarded, no dependency) judge the same library with more
    evidence. Where either exists, the source finding is a duplicate that blocked 38 mods on a question already
    answered (owner ruling 2026-09-29: treat it like the existing rule)."""
    judged = {e.split(":", 1)[1] for f in result.findings if f.id in ("undeclared-library-dependency", "optional-library-integration")
              for e in f.evidence if e.startswith("library:")}
    if judged:
        result.findings[:] = [f for f in result.findings
                              if not (f.id == "source-library-dependency-undeclared" and f.evidence and f.evidence[0] in judged)]


def _nexerelin_custom_start_classes(root: Path) -> set[str]:
    """Classes named by "className" in data/config/exerelin/customStarts.json (loaded only by Nexerelin)."""
    data = _load_lenient_json_file(root / "data" / "config" / "exerelin" / "customStarts.json")
    starts = data.get("starts") if isinstance(data, dict) else None
    return {s["className"].strip() for s in starts or [] if isinstance(s, dict) and isinstance(s.get("className"), str) and s["className"].strip()}


def _only_nexerelin_custom_starts(root: Path, prefixes) -> bool:
    """True when every source using these packages is a class registered in customStarts.json."""
    registered = _nexerelin_custom_start_classes(root)
    users = set(_sources_mentioning(root, [prefix.rstrip(".") for prefix in prefixes]).values()) if registered else set()
    return bool(users) and users <= registered


def _sources_mentioning(root: Path, dotted: list[str]) -> dict[str, str]:
    """{relative source path: class name} for .java files that mention any dotted package."""
    found: dict[str, str] = {}
    for source in sorted(root.rglob("*.java")):
        if "disabled_files" in source.relative_to(root).parts:
            continue
        try:
            text = source.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if any(needle in text for needle in dotted):
            package = re.search(r"(?m)^\s*package\s+([\w.]+)\s*;", text)
            found[_relative(root, source)] = f"{package.group(1)}.{source.stem}" if package else source.stem
    return found


def _library_import_only(root: Path, result: ScanResult, slash_prefixes: tuple[str, ...] | list[str]) -> list[str]:
    """Source files that mention a library although the shipped jar never references it.

    Returns the mentioning sources when every one of them compiles into a loaded jar class and no loaded
    jar class references the library's packages; otherwise []. Bionic Alteration imports Nexerelin's
    StringHelper but never calls it, so its jar has no exerelin/ reference and it runs without
    Nexerelin: an unused import is not a dependency (2026-09-14).
    """
    if not result.compiled_class_names:
        return []
    dotted = [prefix.replace("/", ".").rstrip(".") for prefix in slash_prefixes]
    mentioning: list[str] = []
    for source in sorted(root.rglob("*.java")):
        if "disabled_files" in source.relative_to(root).parts:
            continue
        try:
            text = source.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not any(needle in text for needle in dotted):
            continue
        package = re.search(r"(?m)^\s*package\s+([\w.]+)\s*;", text)
        class_name = f"{package.group(1)}.{source.stem}" if package else source.stem
        if class_name not in result.compiled_class_names:
            return []  # a loose or uncompiled source: its import may be live
        mentioning.append(_relative(root, source))
    if not mentioning:
        return []
    for _jar, _member, data in _iter_jar_class_files(root):
        info = _parse_class_file(data)
        if info is not None and any(ref.startswith(prefix) for ref in info.referenced_classes for prefix in slash_prefixes):
            return []
    return mentioning


# Names a mod probes for with loadClass/Class.forName to detect a library at runtime (the library is then optional).
# Exigency 0.8.01a probes "data.scripts.world.ExerelinGen", Nexerelin's class outside its own package (2026-09-28).
LIBRARY_PROBE_MARKERS = {
    "Nexerelin": ("exerelin", "ExerelinGen"),
    "Console Commands": ("lazywizard.console",),
    "LunaLib": ("lunalib",),
    "MagicLib": ("magiclib", "data.scripts.util.Magic", "org.magiclib"),
    "GraphicsLib": ("dark.shaders", "org.dark."),
    "LazyLib": ("lazywizard.lazylib",),
}


_PRESENCE_PROBE = re.compile(r'\b(?:loadClass|forName)\s*\(\s*"([^"]+)"')


def _library_presence_probed(root: Path, library: str) -> bool:
    """A source file or jar class probes for this library by class name (loadClass/Class.forName)."""
    markers = LIBRARY_PROBE_MARKERS.get(library, ())
    if not markers:
        return False
    for source in root.rglob("*.java"):
        if "disabled_files" in source.relative_to(root).parts:
            continue
        try:
            text = source.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if any(any(m.lower() in name.lower() for m in markers) for name in _PRESENCE_PROBE.findall(text)):
            return True
    for _jar, _member, data in _iter_jar_class_files(root):
        info = _parse_class_file(data)
        if info is None or not ({"loadClass", "forName"} & set(info.utf8_values)):
            continue
        if any(any(m.lower() in value.lower() for m in markers) and "." in value for value in info.string_constants):
            return True
    return False


def _unguarded_library_users(root: Path, source_hits: list[str], library: str, dependency_id: str) -> list[str]:
    """Source files that use a library with no sign of a guard: no isModEnabled(<id>), no loadClass/forName probe, no catch of
    NoClassDefFoundError/LinkageError/Throwable, and no `if (...)` condition naming the library or its id (a flag the plugin
    set from its own probe). A probe elsewhere in the mod does not protect such a file: Free Stars Union's AicModPlugin probes
    ShaderLib in a try/catch, yet aic_temporalstats built a StandardLight in combat and stopped the game with
    NoClassDefFoundError (GRP3A-20261006)."""
    id_guard = re.compile(r'\bisModEnabled\s*\(\s*"' + re.escape(dependency_id) + r'"\s*\)', re.IGNORECASE)
    catches = re.compile(r"catch\s*\(\s*(?:final\s+)?(?:\w+\s*\|\s*)*(?:NoClassDefFoundError|LinkageError|Throwable|Error)\b")
    names = sorted({re.escape(dependency_id.lower()), re.escape(library.lower().replace(" ", ""))})
    flag = re.compile(r"\bif\s*\(\s*!?\s*[\w.]*(?:" + "|".join(names) + r")", re.IGNORECASE)
    markers = LIBRARY_PROBE_MARKERS.get(library, ())
    unguarded = []
    for relative in source_hits:
        try:
            text = _blank_java_comments((root / relative).read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        probes = any(any(m.lower() in name.lower() for m in markers) for name in _PRESENCE_PROBE.findall(text))
        if not (id_guard.search(text) or probes or catches.search(text) or flag.search(text)):
            unguarded.append(relative)
        elif (not id_guard.search(text) and _MOD_PLUGIN_CLASS.search(text) and not _probe_returns_early(text, markers)
              and _library_call_outside_guard(text, markers, flag)):
            # A probe in the mod plugin does not cover a call outside any guarding block: onApplicationLoad runs at every start.
            # Only the mod plugin: a helper class's call is usually guarded by its caller, which this textual check cannot see
            # (a sweep of 300 workspaces found 3 such false hits in shader and ship system classes, 2026-10-11).
            unguarded.append(relative)
    return unguarded


_GUARD_HEADER = re.compile(r"\b(?:try|catch|synchronized)\b")


_MOD_PLUGIN_CLASS = re.compile(r"\bextends\s+BaseModPlugin\b")


def _probe_returns_early(text: str, markers: tuple[str, ...]) -> bool:
    """`try { loadClass("<library class>") } catch (...) { return; }`: everything after the probe runs only with the library
    (Upgraded Rotary Weapons' URW_modPlugin, 2026-10-11)."""
    for match in re.finditer(r'(?:loadClass|forName)\s*\(\s*"([^"]+)"[^{}]*\}\s*catch\s*\([^)]*\)\s*\{\s*return\s*;', text):
        if any(m.lower() in match.group(1).lower() for m in markers):
            return True
    return False


_IMPORT_LINE = re.compile(r"^\s*import\s+([\w.]+)\.(\w+)\s*;", re.M)


def _library_call_outside_guard(text: str, markers: tuple[str, ...], flag: re.Pattern) -> bool:
    """A direct use of a class the file imports from the library (`ShaderLib.init()`, `new StandardLight(...)`) that is not inside
    a `try` block, a catch, or an `if` whose condition names the library (a flag set from the probe). Neutrino's NCModPlugin
    probed ShaderLib in a static block yet called ShaderLib.init() unguarded in onApplicationLoad, which stopped the game at
    startup without GraphicsLib (SMOKE-neu-20261011). Brace tracking is textual; a guard in a caller is not seen."""
    simple = sorted({m.group(2) for m in _IMPORT_LINE.finditer(text) if any(mk.lower() in (m.group(1) + ".").lower() for mk in markers)})
    if not simple:
        return False
    names = "|".join(re.escape(name) for name in simple)
    usage = re.compile(r"(?<![\w.])(?:" + names + r")\s*\.|\bnew\s+(?:" + names + r")\b")
    stack: list[str] = []
    last_boundary = 0
    for i, ch in enumerate(text):
        if ch == "{":
            stack.append(text[last_boundary:i])
            last_boundary = i + 1
        elif ch == "}":
            if stack:
                stack.pop()
            last_boundary = i + 1
        elif ch == ";":
            statement = text[last_boundary:i]
            if not statement.lstrip().startswith("import") and usage.search(statement):
                if not any(_GUARD_HEADER.search(header) or flag.search(header) for header in stack):
                    return True
            last_boundary = i + 1
    return False


def _fails_fast_through_variable(text: str, dependency_id: str) -> bool:
    """`boolean has = ...isModEnabled("<id>"); ... if (!has) { throw` -- a required library, not an optional one.
    Hiigaran Descendants 2.1 (HiiModPlugin.onApplicationLoad, shaderLib) stopped at startup this way, GRP7B-20261005."""
    for name in re.findall(r'\b(\w+)\s*=\s*[\w.()\s]*isModEnabled\s*\(\s*"' + re.escape(dependency_id) + r'"\s*\)', text, re.IGNORECASE):
        if re.search(r'if\s*\(\s*!\s*' + re.escape(name) + r'\s*\)\s*\{?\s*throw\b', text):
            return True
    return False


def _throws_without_library(text: str, dependency_id: str) -> bool:
    direct = re.compile(r'!\s*[\w.()\s]*isModEnabled\s*\(\s*"' + re.escape(dependency_id) + r'"\s*\)\s*\)\s*\{?\s*throw\b', re.IGNORECASE)
    return bool(direct.search(text)) or _fails_fast_through_variable(text, dependency_id)


def _scan_library_required_by_throw(root: Path, result: ScanResult) -> None:
    """A plugin that throws when a library is missing needs that library whether or not it reaches the library's
    package: HullMods Expansion's "MagicLib is Required to run this mod" and P9 Colony Group's, neither declared.
    Emits the same finding the fixer reads (no guard evidence, so `fix` declares it)."""
    already = {f.evidence[0] for f in result.findings if f.id == "undeclared-library-dependency" and f.evidence}
    for library, dependency_id in LIBRARY_DEPENDENCY_IDS.items():
        if f"library:{library}" in already or _mod_info_declares_dependency(result, dependency_id):
            continue
        for source in sorted(root.rglob("*.java")):
            if "disabled_files" in source.relative_to(root).parts:
                continue
            try:
                text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            if "isModEnabled" in text and _throws_without_library(text, dependency_id):
                result.add(
                    id="undeclared-library-dependency",
                    category="dependencies",
                    severity="high",
                    classification="REVIEW",
                    confidence="HIGH",
                    explanation=f"{_relative(root, source)} throws when {library} is not enabled, so the mod needs {library}, but "
                                "mod_info.json does not declare it; the game's launcher then does not enable it first.",
                    file="mod_info.json",
                    evidence=[f"library:{library}", f"dependency-id:{dependency_id}", "required:throws-without", _relative(root, source)],
                )
                break


def _scan_undeclared_library_dependency(root: Path, result: ScanResult) -> None:
    """Code that reaches a known library's package without mod_info.json declaring that dependency."""
    own_info = _load_lenient_json_file(root / "mod_info.json")
    own_id = str(own_info.get("id", "")).strip().lower() if isinstance(own_info, dict) else ""
    for library, dependency_id in LIBRARY_DEPENDENCY_IDS.items():
        if _mod_info_declares_dependency(result, dependency_id):
            continue
        if own_id and own_id == dependency_id.lower():
            continue  # the mod IS this library: Combat-Misc-Utils (cmutils) was told to depend on itself (2026-10-11)
        prefixes = BUNDLED_LIBRARY_PACKAGE_PREFIXES[library]
        import_only = _library_import_only(root, result, prefixes)
        if import_only:
            result.add(
                id="library-import-unused-in-jar",
                category="dependencies",
                severity="info",
                classification="SAFE",
                confidence="HIGH",
                explanation=f"Source files mention {library}, but they all compile into the shipped jar and no jar class references {library}'s packages (an unused import). The mod runs without {library}; no dependency is needed.",
                file="mod_info.json",
                evidence=[f"library:{library}", *import_only[:5]],
            )
            continue
        # Kotlin is compiled, never a .java import: matching the word "kotlin" in Java text would be noise.
        dotted_needles = [prefix.replace("/", ".").rstrip(".") for prefix in prefixes if not prefix.startswith("kotlin")]
        source_hits: list[str] = []
        guarded = False
        # Optional integration: every referencing source checks isModEnabled("<this library's id>") and none
        # fails fast (throws) when it is missing. RC8 runs with -noverify (CLAUDE.md), so a library class resolves
        # only when code using it runs, which the guard prevents when the library is absent.
        id_guard = re.compile(r'\bisModEnabled\s*\(\s*"' + re.escape(dependency_id) + r'"\s*\)', re.IGNORECASE)
        fail_fast = re.compile(r'!\s*[\w.()\s]*isModEnabled\s*\(\s*"' + re.escape(dependency_id) + r'"\s*\)\s*\)\s*\{?\s*throw\b', re.IGNORECASE)
        every_hit_id_guarded = True
        fails_fast_hit = False
        for source in sorted(root.rglob("*.java")):
            if "disabled_files" in source.relative_to(root).parts:
                continue
            try:
                # Comments are not code: DNEEP was flagged for Nexerelin by a BridgeForge comment naming
                # "a Nexerelin random sector" (2026-10-05).
                text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            if not any(needle in text for needle in dotted_needles):
                continue
            source_hits.append(_relative(root, source))
            if re.search(r"\bisModEnabled\s*\(", text):
                guarded = True
            if fail_fast.search(text) or _fails_fast_through_variable(text, dependency_id):
                fails_fast_hit = True
            if not id_guard.search(text) or fail_fast.search(text) or _fails_fast_through_variable(text, dependency_id):
                every_hit_id_guarded = False
        bytecode_hits: list[str] = []
        referencing_classes: set[str] = set()
        if not source_hits:
            for jar, member, data in _iter_jar_class_files(root):
                info = _parse_class_file(data)
                if info is None:
                    continue
                if any(ref.startswith(prefix) for ref in info.referenced_classes for prefix in prefixes):
                    relative_jar = _relative(root, jar)
                    if relative_jar not in bytecode_hits:
                        bytecode_hits.append(relative_jar)
                    if info.this_class:
                        referencing_classes.add(info.this_class.split("$", 1)[0].replace("/", "."))
                # Bytecode-only mods (no source, e.g. Nightcross): a loaded class that calls
                # isModEnabled and carries this mod id as a string literal is the same guard.
                if "isModEnabled" in info.utf8_values and any(value.strip().lower() == dependency_id.lower() for value in info.string_constants):
                    guarded = True
        if not source_hits and not bytecode_hits:
            continue
        if library == "Console Commands":
            # Classes registered in data/console/commands.csv load only through Console Commands, so an
            # addon made of them needs no declared dependency (the source-side console-command-optional rule).
            registered = _console_command_classes(root)
            users = set(_sources_mentioning(root, dotted_needles).values()) if source_hits else referencing_classes
            if registered and users and users <= registered:
                if any(f.id == "console-command-optional" for f in result.findings):
                    continue  # already reported from the source imports
                result.add(id="console-command-optional", category="dependencies", severity="info", classification="SAFE", confidence="HIGH",
                           explanation="Every class that uses Console Commands' API is registered in data/console/commands.csv, which only Console Commands reads, so the classes load only when it is installed. An optional integration; no dependency needed.",
                           evidence=sorted(users)[:10])
                continue
        if library == "Nexerelin":
            # Nexerelin's exerelin.campaign.customstart.CustomStartDefs loads each "className" listed in
            # data/config/exerelin/customStarts.json (ExerelinCore.jar 0.12.2c, 2026-09-28), so classes registered
            # only there load only with Nexerelin (SEEKER 0.6.6's six SKR_*Start classes).
            registered = _nexerelin_custom_start_classes(root)
            users = set(_sources_mentioning(root, dotted_needles).values()) if source_hits else referencing_classes
            if registered and users and users <= registered:
                result.add(id="optional-library-integration", category="dependencies", severity="info", classification="SAFE", confidence="HIGH",
                           explanation="Every class that uses Nexerelin is a custom start registered in data/config/exerelin/customStarts.json, which only Nexerelin reads, so the classes load only when it is installed. An optional integration; no dependency needed.",
                           file="mod_info.json", evidence=[f"library:{library}", f"dependency-id:{dependency_id}", "registered:customStarts.json", *sorted(users)[:5]])
                continue
        probed = _library_presence_probed(root, library)
        unguarded_users = _unguarded_library_users(root, source_hits, library, dependency_id) if probed and not every_hit_id_guarded else []
        if unguarded_users:
            probed = False
        if (source_hits and every_hit_id_guarded) or probed:
            result.add(id="optional-library-integration", category="dependencies", severity="info", classification="SAFE", confidence="MEDIUM",
                       explanation=("The mod probes for " + library + " at runtime (loadClass/Class.forName of its classes) before using it" if probed else f"Every source file that uses {library} checks isModEnabled(\"{dependency_id}\")") + f" and none throws when it is missing: an optional integration. RC8 runs with -noverify, so {library}'s classes are resolved only when that guarded code runs. No dependency needed; the mod works with or without {library}.",
                       file="mod_info.json", evidence=[f"library:{library}", f"dependency-id:{dependency_id}", *source_hits[:5]])
            continue
        # Owner ruling 2026-09-27: an unguarded use of a known, maintained library is fixed by declaring it (the
        # library's own mod id, from LIBRARY_DEPENDENCY_IDS), which is deterministic, so it is REVIEW, not MANUAL,
        # and the fixer is a standing approval in AUTOMATION_POLICY.json. Before: 88 MANUAL findings in 229 mods.
        classification = "REVIEW"
        result.add(
            id="undeclared-library-dependency",
            category="dependencies",
            severity="high",
            classification=classification,
            confidence="HIGH",
            explanation=(
                f"Code references {library}'s package(s) ({', '.join(prefixes)}), but mod_info.json does not "
                f"declare a matching '{dependency_id}' dependency. An undeclared mandatory dependency lets the "
                f"mod load and crash later, the first time it calls {library}."
                + (
                    " An isModEnabled(...) guard was found (in a referencing source file, or in a loaded class "
                    "that checks this mod id), suggesting an optional integration rather than a hard dependency. "
                    "A plugin may also use that check to fail fast when a required library is missing, so confirm."
                    if guarded and not unguarded_users
                    else ""
                )
            ),
            file="mod_info.json",
            evidence=[f"library:{library}", f"dependency-id:{dependency_id}", *(["guard:present"] if guarded and not unguarded_users else []), *(["required:throws-without"] if fails_fast_hit else []), *[f"probe-present-but-unguarded-use:{u}" for u in unguarded_users[:5]], *source_hits[:5], *bytecode_hits[:5]],
        )


_DEPENDENCY_ROOTS_CACHE: dict[tuple, list[Path]] = {}


def _dependency_roots(root: Path, provider_roots: list[Path] | None) -> list[Path]:
    """Every folder, in any provider root, that provides one of the mod's declared dependencies. All copies count
    (ROADMAP 34.25, 2026-10-04): the queue's revived Scy Nation lacked ids the modpack's newer copy defines, and
    keeping one copy per id hid them; 16 addons' content and 6 mods' art were in installed providers."""
    if not provider_roots:
        return []
    key = (str(Path(root).resolve()), tuple(str(Path(r)) for r in provider_roots))
    if key not in _DEPENDENCY_ROOTS_CACHE:
        from .java_toolchain import declared_dependencies
        from .substitutes import provider_index

        deps = set(declared_dependencies(root) or [])
        _DEPENDENCY_ROOTS_CACHE[key] = [Path(p.path) for p in provider_index([Path(r) for r in provider_roots], exclude=root)
                                        if p.mod_id in deps] if deps else []
    return _DEPENDENCY_ROOTS_CACHE[key]


def _dependency_content_ids(root: Path, provider_roots: list[Path] | None) -> dict[str, set[str]]:
    """Hull mod, weapon, wing and hull ids a declared dependency defines (SEEKER 0.6.6 builds MagicLib's
    ML_interferenceWarning into its hulls; 2026-09-28). Explicit provider_roots only, like _dependency_jar_class_names;
    the union over every copy of each dependency (_dependency_roots)."""
    found: dict[str, set[str]] = {"hullmod": set(), "weapon": set(), "wing": set(), "hull": set()}
    for dep in _dependency_roots(root, provider_roots):
        found["hullmod"] |= set(_csv_id_index(dep / "data" / "hullmods" / "hull_mods.csv", None))
        found["weapon"] |= set(_csv_id_index(dep / "data" / "weapons" / "weapon_data.csv", None))
        found["wing"] |= set(_csv_id_index(dep / "data" / "hulls" / "wing_data.csv", None))
        found["hull"] |= {p.stem for p in (dep / "data" / "hulls").rglob("*.ship")} if (dep / "data" / "hulls").is_dir() else set()
    return found


def _scan_unresolved_content_references(root: Path, result: ScanResult, vanilla_core: Path | None, provider_roots: list[Path] | None = None) -> None:
    """Hull mods, wings, weapons and hulls used by the mod's data but defined by neither it nor vanilla.

    Communist Clouds builds `vayra_red_army` into its hulls and fields `vayra_*` wings and weapons: it
    is a Vayra's Sector add-on, which its mod_info didn't declare and no check noticed (2026-09-14).
    """
    if vanilla_core is None:
        return
    weapons = set(_csv_id_index(root / "data" / "weapons" / "weapon_data.csv", vanilla_core / "data" / "weapons" / "weapon_data.csv")) | set(_wpn_type_size_index(root, vanilla_core))
    hull_mods = set(_csv_id_index(root / "data" / "hullmods" / "hull_mods.csv", vanilla_core / "data" / "hullmods" / "hull_mods.csv"))
    wings = set(_csv_id_index(root / "data" / "hulls" / "wing_data.csv", vanilla_core / "data" / "hulls" / "wing_data.csv"))
    skins = _skin_index(root, vanilla_core)
    hulls = set(_ship_file_index(root, vanilla_core)) | set(skins)
    if not (weapons and hull_mods and wings and hulls):
        return
    from_dependencies = _dependency_content_ids(root, provider_roots)
    weapons |= from_dependencies["weapon"]
    hull_mods |= from_dependencies["hullmod"]
    wings |= from_dependencies["wing"]
    hulls |= from_dependencies["hull"]
    missing: dict[str, dict[str, set[str]]] = {"hullmod": {}, "wing": {}, "weapon": {}, "hull": {}}
    misplaced: list[tuple[str, str]] = []

    def check(kind: str, ident: object, known: set[str], where: str) -> None:
        if isinstance(ident, str) and ident.strip() and ident not in known:
            missing[kind].setdefault(ident, set()).add(where)

    data = root / "data"
    for path in sorted(data.rglob("*")) if data.is_dir() else []:
        if path.suffix.lower() not in (".variant", ".ship", ".skin"):
            continue
        spec = _load_lenient_json_file(path)
        if not isinstance(spec, dict):
            continue
        where = _relative(root, path)
        for key in ("hullMods", "permaMods", "sMods", "builtInMods", "removeBuiltInMods"):
            for ident in spec.get(key) or []:
                check("hullmod", ident, hull_mods, where)
        for key in ("wings", "builtInWings"):
            for ident in spec.get(key) or []:
                if key == "builtInWings" and isinstance(ident, str) and ident not in wings and ident in hull_mods:
                    misplaced.append((where, ident))  # a hull mod under the wings key (The Nomads' nom_komodo_p)
                    continue
                check("wing", ident, wings, where)
        for group in spec.get("weaponGroups") or []:
            if isinstance(group, dict) and isinstance(group.get("weapons"), dict):
                for ident in group["weapons"].values():
                    check("weapon", ident, weapons, where)
        if isinstance(spec.get("builtInWeapons"), dict):
            for ident in spec["builtInWeapons"].values():
                check("weapon", ident, weapons, where)
        if path.suffix.lower() == ".variant":
            check("hull", spec.get("hullId"), hulls, where)
        if path.suffix.lower() == ".skin":
            check("hull", spec.get("baseHullId"), hulls, where)
    for where, ident in misplaced:
        result.add(
            id="builtin-wing-is-hullmod",
            category="hulls",
            severity="high",
            classification="REVIEW",
            confidence="DETERMINISTIC",
            explanation=(f"builtInWings lists '{ident}', which is a hull mod, not a wing (The Nomads' nom_komodo_p.ship listed "
                         "the vanilla advancedcore there, 2026-10-04). RC8 looks it up as a wing and does not find it. It "
                         "belongs under builtInMods."),
            file=where,
            evidence=[f"hullmod:{ident}", "key:builtInWings"],
        )
    unresolved = [(kind, ident, files) for kind, table in missing.items() for ident, files in sorted(table.items())]
    if not unresolved:
        return
    # The finding's evidence collapses this to counts and truncates at 25 (a human-readable
    # summary). The full per-id file list survives here for callers that need the exact edit list
    # (ROADMAP P14 item 4, the strip/vendor planner): which .variant/.ship/.skin loses which id.
    result.migration_context["unresolved_content_references"] = {
        kind: {ident: sorted(files) for ident, files in table.items()} for kind, table in missing.items() if table
    }
    prefixes = Counter(ident.split("_", 1)[0] + "_" for _kind, ident, _files in unresolved if "_" in ident)
    prefix_note = [f"common prefix: {prefix} ({count} ids)" for prefix, count in prefixes.most_common(3) if count > 1]
    declares = bool(result.metadata.get("dependencies") or result.metadata.get("requiredDependencies"))
    # ROADMAP P14 item 8: "defined nowhere" becomes "removed in a historical vanilla version; use
    # X" when the id is a known, catalogued removal (dependency_successors.json's own
    # removed-vanilla-content entries - the same catalogue dependency-substitutes already reads,
    # so a plain scan gets the same evidence a person running dependency-substitutes separately
    # would have had to look up by hand otherwise). Local import: substitutes.py imports from
    # scanner.py, so a module-level import here would be circular.
    from .substitutes import load_successors

    known_removed = {entry.get("match"): entry for entry in load_successors() if entry.get("kind") == "removed-vanilla-content"}

    def describe(kind: str, ident: str, files: set[str]) -> str:
        base = f"{kind}:{ident} ({len(files)} file(s))"
        entry = known_removed.get(ident)
        if entry is not None:
            base += f" [removed-vanilla-content, not just missing: {entry.get('successor', '')}]"
        return base

    any_known = any(ident in known_removed for _kind, ident, _files in unresolved)
    explanation = "The mod's hulls, skins or variants use hull mods, wings, weapons or hulls that neither the mod nor vanilla defines. They must come from another mod, which then has to be installed (and declared in mod_info.json), or the specs fail to load." + (" The mod declares dependencies that may provide them; confirm." if declares else " The mod declares no dependency.")
    # Live RC8 evidence (P15 item 18, 2026-09-27): a variant naming a missing weapon stopped the game at
    # New Game with "Fatal: Weapon spec [...] not found!" (PRB-CID-FAIL-20260927); a missing hull mod was
    # dropped without a log line and the built variant no longer listed it (CID-FAIL2-20260927).
    kinds = {kind for kind, _ident, _files in unresolved}
    if "weapon" in kinds:
        explanation += " A missing weapon in a variant stops RC8 with a Fatal dialog at New Game (live run, 2026-09-27)."
    if "hullmod" in kinds:
        explanation += " A missing hull mod in a variant is dropped silently by RC8, so the ship loses its effect with no error (live run, 2026-09-27)."
    if any_known:
        explanation += " At least one of these ids is a known vanilla-content removal with a catalogued successor (see the evidence below, and `dependency_successors.json`) - this is not just 'defined nowhere'."
    result.add(
        id="content-reference-unresolved",
        category="dependencies",
        # Severity from the live consequence (P15 item 22.3): weapon -> New Game fatal; hull mods alone ->
        # dropped silently; wings/hulls not yet observed live, so they keep "high".
        severity="critical" if "weapon" in kinds else ("medium" if kinds == {"hullmod"} else "high"),
        classification="REVIEW" if declares else "MANUAL",
        confidence="HIGH",
        explanation=explanation,
        evidence=prefix_note + [describe(kind, ident, files) for kind, ident, files in unresolved[:25]] + ([f"... {len(unresolved) - 25} more"] if len(unresolved) > 25 else []),
    )


def _hull_hints(row: dict[str, str]) -> set[str]:
    return {token.strip().upper() for token in (row.get("hints") or "").split(",") if token.strip()}


def _first_value_commented(row: dict) -> bool:
    """Starsector skips a CSV row whose first column starts with '#' (Exigency 0.8.01a keeps a commented copy of the
    header, "#name,id,...", as row 2, which read as a hull and a weapon named "id"; 2026-09-28)."""
    first = next(iter(row.values()), "") if row else ""
    return str(first or "").strip().startswith("#")


def _scan_description_missing(root: Path, result: ScanResult, vanilla_core: Path | None = None) -> None:
    """A mod hull/weapon/ship-system id with no matching descriptions.csv row of the right type.

    descriptions.csv rows are keyed by id, and Starsector does not require a mod to redeclare a row
    for an id it did not otherwise remove: a mod that reuses/rebalances a vanilla id (in weapon_data,
    ship_data, or ship_systems) inherits vanilla's description for that id unless it overrides it. So
    an id is "described" if it has a row in the mod's OWN descriptions.csv OR (when vanilla_core is
    given) vanilla's.
    """
    descriptions_path = root / "data" / "strings" / "descriptions.csv"
    described: dict[str, set[str]] = {}
    vanilla_descriptions_path = (vanilla_core / "data" / "strings" / "descriptions.csv") if vanilla_core else None
    if vanilla_descriptions_path is not None:
        for row in _read_csv_rows_lenient(vanilla_descriptions_path) or []:
            row_id = (row.get("id") or "").strip()
            row_type = (row.get("type") or "").strip().upper()
            if row_id and not row_id.startswith("#"):
                described.setdefault(row_id, set()).add(row_type)
    for row in _read_csv_rows(descriptions_path) or []:
        row_id = (row.get("id") or "").strip()
        row_type = (row.get("type") or "").strip().upper()
        if row_id and not row_id.startswith("#"):
            described.setdefault(row_id, set()).add(row_type)

    ship_files = _ship_file_index(root, None)
    # RC8's SpecStore applies weapon_data.csv / ship_systems.csv rows only to specs loaded from .wpn / .system
    # files, and skips the rest: "Ship system [ART_weaponPlatform] from ship_systems.csv not found in store"
    # (SEEKER-SOLO-20260928). A row with no spec, or a DECORATIVE weapon, is never shown, so it needs no
    # description (9 of 474 drafted rows were such, 2026-09-29).
    weapon_specs: dict[str, str] = {}
    system_specs: set[str] = set()
    # Only the mod's own specs: a row for a spec vanilla defines is a vanilla override, and vanilla owns its
    # description (Communist Clouds' skimmer_drone and traveldrive, 2026-09-29).
    for base in (root,):
        if base is None or not Path(base).is_dir():
            continue
        for path in Path(base).rglob("*.wpn"):
            spec = _load_lenient_json_file(path)
            spec_id = spec.get("id") if isinstance(spec, dict) and isinstance(spec.get("id"), str) else path.stem
            weapon_specs[spec_id] = str(spec.get("type", "")).upper() if isinstance(spec, dict) else ""
        for path in Path(base).rglob("*.system"):
            spec = _load_lenient_json_file(path)
            system_specs.add(spec["id"] if isinstance(spec, dict) and isinstance(spec.get("id"), str) else path.stem)

    ship_data_path = root / "data" / "hulls" / "ship_data.csv"
    for row in _read_csv_rows(ship_data_path) or []:
        hull_id = (row.get("id") or "").strip()
        if not hull_id or hull_id.startswith("#") or _first_value_commented(row):
            continue
        hints = _hull_hints(row)
        if "HIDE_IN_CODEX" in hints or "MODULE" in hints:
            continue
        ship_json = ship_files.get(hull_id)
        if isinstance(ship_json, dict) and str(ship_json.get("hullSize") or "").strip().upper() == "FIGHTER":
            continue
        if "SHIP" in described.get(hull_id, set()):
            continue
        result.add(
            id="description-missing",
            category="content",
            severity="low",
            classification="REVIEW",
            confidence="DETERMINISTIC",
            explanation=f"Hull '{hull_id}' has no SHIP-type row in data/strings/descriptions.csv; the codex/refit screen will show a blank description.",
            file=_relative(root, ship_data_path),
            evidence=[f"hull:{hull_id}"],
        )

    weapon_data_path = root / "data" / "weapons" / "weapon_data.csv"
    for row in _read_csv_rows(weapon_data_path) or []:
        weapon_id = (row.get("id") or "").strip()
        if not weapon_id or weapon_id.startswith("#") or _first_value_commented(row):
            continue
        hints = {token.strip().upper() for token in (row.get("hints") or "").split(",") if token.strip()}
        if "SYSTEM" in hints:
            continue
        if not (row.get("OPs") or "").strip():
            continue
        if weapon_id == "id" or weapon_id not in weapon_specs or weapon_specs[weapon_id] == "DECORATIVE":
            continue  # a repeated header row, a CSV row with no loaded spec, or a decorative fixture: never shown
        if "WEAPON" in described.get(weapon_id, set()):
            continue
        result.add(
            id="description-missing",
            category="content",
            severity="low",
            classification="REVIEW",
            confidence="DETERMINISTIC",
            explanation=f"Weapon '{weapon_id}' has no WEAPON-type row in data/strings/descriptions.csv; the codex/refit screen will show a blank description.",
            file=_relative(root, weapon_data_path),
            evidence=[f"weapon:{weapon_id}"],
        )

    ship_systems_path = root / "data" / "shipsystems" / "ship_systems.csv"
    for row in _read_csv_rows(ship_systems_path) or []:
        system_id = (row.get("id") or "").strip()
        if _first_value_commented(row) or not system_id or system_id.startswith("#"):
            continue
        if system_id not in system_specs:
            continue  # no .system spec: RC8 skips the CSV row ("not found in store"), so nothing is shown
        if "SHIP_SYSTEM" in described.get(system_id, set()):
            continue
        result.add(
            id="description-missing",
            category="content",
            severity="low",
            classification="REVIEW",
            confidence="DETERMINISTIC",
            explanation=f"Ship system '{system_id}' has no SHIP_SYSTEM-type row in data/strings/descriptions.csv; the codex will show a blank description.",
            file=_relative(root, ship_systems_path),
            evidence=[f"ship-system:{system_id}"],
        )


def _asset_exists(candidate: str, root: Path, vanilla_core: Path | None) -> bool:
    normalized = candidate.strip().lstrip("/\\").replace("\\", "/")
    if not normalized:
        return True
    if (root / normalized).is_file():
        return True
    if vanilla_core is not None and (vanilla_core / normalized).is_file():
        return True
    return False


def _report_asset_reference_missing(result: ScanResult, root: Path, vanilla_core: Path | None, file: str, field: str, candidate: str) -> None:
    if _asset_exists(candidate, root, vanilla_core):
        return
    # RC8 resolves graphics and sounds across every enabled mod: a declared dependency's file is found (34.25,
    # 2026-10-04: the Interstellar Imperium and Mayasuran expansions' art was in the installed base mods).
    if any((Path(dep) / candidate).is_file() for dep in result.migration_context.get("dependency_roots") or []):
        return
    if vanilla_core is None:
        result.add(
            id="asset-reference-missing",
            category="assets",
            severity="low",
            classification="UNKNOWN",
            confidence="LOW",
            explanation=f"'{field}' references '{candidate}', which is not present in this mod. No --vanilla-core was supplied, so BridgeForge cannot tell this apart from a legitimate vanilla asset path.",
            file=file,
            evidence=[f"field:{field}", f"path:{candidate}", "no vanilla core supplied"],
        )
        return
    result.add(
        id="asset-reference-missing",
        category="assets",
        severity="medium",
        classification="REVIEW",
        confidence="DETERMINISTIC",
        explanation=f"'{field}' references '{candidate}', which exists in neither this mod nor the supplied vanilla core. The asset will fail to load.",
        file=file,
        evidence=[f"field:{field}", f"path:{candidate}"],
    )


def _walk_sounds_json_files(node: object) -> list[tuple[str, str | None]]:
    """Every ('file', 'source'-or-None) pair found anywhere in a sounds.json structure."""
    found: list[tuple[str, str | None]] = []
    if isinstance(node, dict):
        file_value = node.get("file")
        if isinstance(file_value, str) and file_value.strip():
            source_value = node.get("source")
            found.append((file_value.strip(), source_value.strip() if isinstance(source_value, str) and source_value.strip() else None))
        for value in node.values():
            found.extend(_walk_sounds_json_files(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_walk_sounds_json_files(item))
    return found


def _scan_asset_reference_missing(root: Path, result: ScanResult, vanilla_core: Path | None) -> None:
    """A sprite/sound path named in mod data that resolves to no file in the mod or vanilla."""
    for path in sorted(root.rglob("*.ship")):
        data = _load_lenient_json_file(path)
        if not isinstance(data, dict):
            continue
        sprite = data.get("spriteName")
        if isinstance(sprite, str) and sprite.strip():
            _report_asset_reference_missing(result, root, vanilla_core, _relative(root, path), "spriteName", sprite)

    wpn_fields = ("turretSprite", "hardpointSprite", "turretUnderSprite", "hardpointUnderSprite", "turretGunSprite", "hardpointGunSprite")
    for path in sorted(root.rglob("*.wpn")):
        data = _load_lenient_json_file(path)
        if not isinstance(data, dict):
            continue
        for field in wpn_fields:
            value = data.get(field)
            if isinstance(value, str) and value.strip():
                _report_asset_reference_missing(result, root, vanilla_core, _relative(root, path), field, value)

    for path in sorted(root.rglob("*.proj")):
        data = _load_lenient_json_file(path)
        if not isinstance(data, dict):
            continue
        for field in ("sprite", "bulletSprite"):
            value = data.get(field)
            if isinstance(value, str) and value.strip():
                _report_asset_reference_missing(result, root, vanilla_core, _relative(root, path), field, value)

    sounds_path = root / "data" / "config" / "sounds.json"
    if sounds_path.is_file():
        data = _load_lenient_json_file(sounds_path)
        if isinstance(data, dict):
            relative = _relative(root, sounds_path)
            for file_value, source_value in _walk_sounds_json_files(data):
                if source_value and not source_value.lower().endswith((".bin", ".zip", ".jar")):
                    candidate = f"{source_value.rstrip('/')}/{file_value.lstrip('/')}"
                elif source_value:
                    continue  # Packed inside a binary/archive container; not independently verifiable.
                else:
                    candidate = file_value
                _report_asset_reference_missing(result, root, vanilla_core, relative, "sounds.json:file", candidate)

    # settings.json "graphics": {category: {key: path}} is loaded at startup; a missing file is a Fatal before the
    # main menu (GRP-9, 2026-09-28: Maelstrom Superweapons Arsenal Older Version registered sw_shields256.png, the
    # current release's name, while shipping the same sprites as swo_shields256.png).
    settings_path = root / "data" / "config" / "settings.json"
    if settings_path.is_file():
        data = _load_lenient_json_file(settings_path)
        graphics = data.get("graphics") if isinstance(data, dict) else None
        if isinstance(graphics, dict):
            relative = _relative(root, settings_path)
            for category, entries in graphics.items():
                if not isinstance(entries, dict):
                    continue
                for key, value in entries.items():
                    if isinstance(value, str) and value.strip().lower().endswith((".png", ".jpg", ".jpeg", ".gif")):
                        _report_asset_reference_missing(result, root, vanilla_core, relative, f"settings.json:graphics.{category}.{key}", value.strip())


# ROADMAP P14 item 15: engine_styles.json, hull_styles.json, custom_entities.json and planets.json
# are merged by whole-entry replace, not a per-field merge (Starsector wiki: "any mod added
# entries with keys ... the same as core game entries will see the mod entries replace the core
# game entries"). Found on Zorg18 (2026-09-20): engine_styles.json redefined vanilla's LOW_TECH/
# MIDLINE/HIGH_TECH as an older, incomplete copy - missing a contrailCampaignColor key vanilla's
# current file has - silently stripping that colour from every LOW_TECH/MIDLINE/HIGH_TECH-styled
# ship in the player's entire game (vanilla and every other enabled mod) while enabled.
# sounds.json is deliberately excluded here: its top-level keys are categories (music/etc.), not
# entry ids, and its per-category values are often lists rather than dicts - the id-keyed,
# dict-valued whole-entry-replace semantics confirmed for the other four files have not been
# verified for sounds.json's nested structure, and this check does not guess.
PRESET_WHOLE_ENTRY_REPLACE_FILES = (
    "data/config/engine_styles.json",
    "data/config/hull_styles.json",
    "data/config/custom_entities.json",
    "data/config/planets.json",
)


def _scan_preset_whole_entry_replace(root: Path, result: ScanResult, vanilla_core: Path | None) -> None:
    """A mod redefining a vanilla id in one of these files replaces it whole-game, not per-field."""
    if vanilla_core is None:
        return
    for relative in PRESET_WHOLE_ENTRY_REPLACE_FILES:
        mod_data = _load_lenient_json_file(root / relative)
        if not isinstance(mod_data, dict) or not mod_data:
            continue
        vanilla_data = _load_lenient_json_file(vanilla_core / relative)
        if not isinstance(vanilla_data, dict) or not vanilla_data:
            continue
        for entry_id, mod_entry in sorted(mod_data.items()):
            if not isinstance(entry_id, str) or not isinstance(mod_entry, dict):
                continue
            vanilla_entry = vanilla_data.get(entry_id)
            if not isinstance(vanilla_entry, dict) or mod_entry == vanilla_entry:
                continue
            missing = sorted(set(vanilla_entry) - set(mod_entry))
            changed = sorted(key for key in set(vanilla_entry) & set(mod_entry) if vanilla_entry[key] != mod_entry[key])
            if not missing and not changed:
                continue
            evidence = [f"id:{entry_id}"] + [f"missing:{key}" for key in missing] + [f"changed:{key}" for key in changed]
            explanation = (
                f"'{entry_id}' also exists in vanilla's own {relative}. The game merges this file by whole-entry "
                f"replace, not a per-field merge (Starsector wiki), so this mod's copy silently overrides vanilla's "
                "for every ship/entity using this id, in vanilla AND every other enabled mod, for as long as this "
                "mod is enabled - not just this mod's own content."
                + (f" Field(s) present in vanilla's entry but missing from this mod's copy are lost entirely: {', '.join(missing)}." if missing else "")
                + (f" Field(s) present in both with a different value: {', '.join(changed)}." if changed else "")
            )
            if missing:
                result.add(id="preset-whole-entry-replace-loses-vanilla-fields", category="assets", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation=explanation, file=relative, evidence=evidence)
            else:
                result.add(id="preset-whole-entry-replace-changes-vanilla-fields", category="assets", severity="medium", classification="REVIEW", confidence="DETERMINISTIC", explanation=explanation, file=relative, evidence=evidence)


def _drop_vanilla_registered_weapon_specs(result: ScanResult, vanilla_core: Path | None) -> None:
    """A local .wpn whose id vanilla's weapon_data.csv registers is an override, not unregistered.

    Blackrock's blinker_green.wpn replaces vanilla's own; vanilla-path-shadowing already reports the
    override (critical), so also calling it 'unregistered' is noise.
    """
    if vanilla_core is None:
        return
    vanilla_ids = _registered_csv_ids(vanilla_core / "data" / "weapons" / "weapon_data.csv") or set()
    if not vanilla_ids:
        return

    def overrides_vanilla(finding) -> bool:
        return finding.id == "local-weapon-spec-unregistered" and any(
            str(item).startswith("weapon:") and str(item)[len("weapon:"):] in vanilla_ids for item in finding.evidence
        )

    result.findings[:] = [finding for finding in result.findings if not overrides_vanilla(finding)]


def scan_mod(input_path: Path, target: TargetProfile | None = None, vanilla_core: Path | None = None, compile_check: bool = False, provider_roots: list[Path] | None = None) -> ScanResult:
    root = input_path.expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Input mod directory does not exist: {root}")
    if not (root / "mod_info.json").is_file() and (root / "original").is_dir() and (root / "working" / "mod_info.json").is_file():
        # ROADMAP P14 item 30: this is a workspace root (In operation/<Mod>/), not the mod itself.
        # Scanning it walks into the untouched `original/` copy alongside `working/` and reports
        # original's findings as if they were live on the revived mod - found 2026-09-21 doing
        # item 23's own corpus recheck by hand: BF-Legacy-Fleets and Leon-Heavy-Industries were
        # each scanned this way, misattributing 7 findings from Leon's frozen `original/` to its
        # actual revived `working/` copy, which was in fact clean.
        raise ValueError(f"{root} looks like a workspace root (holds original/ and working/, not its own mod_info.json) - scan {root / 'working'} instead.")
    vanilla_root = vanilla_core.expanduser().resolve() if vanilla_core is not None else None
    if vanilla_root is not None and not vanilla_root.is_dir():
        vanilla_root = None
    result = ScanResult(input_path=root, target=target or TargetProfile())
    # Declared dependencies' folders, for asset and content references they supply (ROADMAP 34.25).
    result.migration_context["dependency_roots"] = [str(p) for p in _dependency_roots(root, provider_roots)]
    for path in sorted(root.rglob("*")):
        if path.is_file():
            result.files.append({"path": _relative(root, path), "size_bytes": path.stat().st_size})
    _scan_working_copy_tool_debris(root, result)
    _scan_metadata(root, result)
    _scan_mod_info_jar_missing(root, result)
    _scan_jars(root, result)
    _scan_sources(root, result, vanilla_core, provider_roots)
    _scan_assets(root, result)
    _scan_configured_class_integrity(root, result)
    _annotate_source_reachability(root, result)
    _scan_campaign_identifier_context(root, result)
    _attribute_library_usage(result)
    _dependency_compatibility_context(result)
    _scan_revenantlib_fold_conflict(result)
    _infer_environment(result)
    _scan_procgen_rows(root, result, vanilla_root)
    _scan_star_type_undefined(root, result, vanilla_root)
    _scan_content_id_renamed_by_provider(root, result, vanilla_root, provider_roots)
    _scan_faction_known_lists(root, result, vanilla_root)
    _scan_rules_condition_defects(root, result, vanilla_root)
    _scan_design_type_colors(root, result, vanilla_root)
    _scan_shiproles(root, result, vanilla_root)
    _scan_carrier_rework_gap(root, result)
    _scan_black_hole_flag(root, result)
    _scan_legacy_market_conditions(root, result)
    _scan_unregistered_skill_set(root, result, vanilla_root)
    _scan_csv_slash_quote(root, result)
    _scan_mod_info_game_version(result)
    _scan_vanilla_path_shadowing(root, result, vanilla_root)
    _scan_preset_entry_overrides(root, result, vanilla_root)
    _drop_vanilla_registered_weapon_specs(result, vanilla_root)
    _scan_script_sandbox_forbidden_api(root, result)
    _scan_bundled_library_classes(root, result)
    _scan_vanilla_duplicated_classes(root, result, vanilla_root)
    _scan_obfuscated_internal_api_use(root, result)
    _scan_csv_design_type_column(root, result)
    _scan_undeclared_library_dependency(root, result)
    _scan_library_required_by_throw(root, result)
    _drop_library_findings_judged_elsewhere(result)
    _scan_orbit_period_hazards(root, result)
    _scan_module_captain_personality_risk(root, result)
    _scan_spawned_ship_captain_personality_risk(root, result)
    _scan_nexerelin_corvus_mode_import(root, result)
    _scan_unguarded_variable_lookup(root, result)
    _scan_procgen_call_arguments(root, result)
    _scan_settings_keys_missing(root, result, vanilla_root)
    _scan_faction_known_tags(root, result, vanilla_root)
    _scan_shared_hook_overrides(root, result, vanilla_root)
    _scan_temporary_market_fleet_source(root, result)
    _scan_per_frame_market_work(root, result)
    _scan_rc8_signature_changed(root, result)
    _scan_replace_drops_rc8_entries(root, result, vanilla_root)
    _scan_retired_vanilla_class_copy(root, result, vanilla_root)
    _scan_bundled_source_stale(root, result)
    _scan_mod_info_triage_banner(root, result)
    _scan_person_names_duplicate_row(root, result)
    _scan_rules_csv_duplicate_id(root, result)
    _scan_rules_csv_whitespace_only_line(root, result)
    _scan_rules_csv_curly_quotes(root, result)
    _scan_supplies_legacy_column(root, result)
    _scan_json_duplicate_key(root, result, vanilla_root)
    from .conversion_checks import (
        scan_factions_csv_relists_neutral,
        scan_factions_naming_missing_content,
        scan_factions_naming_removed_hulls,
        scan_lifecycle_plugin_missing,
        scan_vanilla_row_overrides,
    )

    scan_factions_naming_removed_hulls(root, result, vanilla_root)
    scan_factions_naming_missing_content(root, result, vanilla_root)
    scan_lifecycle_plugin_missing(root, result)
    scan_vanilla_row_overrides(root, result, vanilla_root)
    scan_factions_csv_relists_neutral(root, result, vanilla_root)
    _scan_data_class_references_missing(root, result, vanilla_root, provider_roots)
    _scan_hardcoded_hyperspace_coordinates(root, result)
    _scan_hardcoded_terrain_grid_size(root, result)
    _scan_variant_validity(root, result, vanilla_root)
    _scan_unresolved_content_references(root, result, vanilla_root, provider_roots)
    _scan_carrier_bays_proposal(root, result, vanilla_root)
    _scan_description_missing(root, result, vanilla_root)
    _scan_asset_reference_missing(root, result, vanilla_root)
    _scan_preset_whole_entry_replace(root, result, vanilla_root)
    if compile_check:
        _scan_compile_check(root, result, vanilla_root, provider_roots)
    return result
