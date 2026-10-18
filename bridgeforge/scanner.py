from __future__ import annotations

from .zipsafe import read_limited

import zipfile
from collections import Counter
from pathlib import Path
from pathlib import PurePosixPath

from .models import ScanResult, TargetProfile
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
from .scan_sources import (  # noqa: F401
    _scan_sources,
    _removed_api_call_spans,
    _LEGACY_ADD_PLANET_RECEIVER_PATTERN,
    _LEGACY_ADD_ORBITAL_STATION_RECEIVER_PATTERN,
    _LEGACY_WORLD_RECEIVER_NAME,
    _find_legacy_add_planet_calls,
    _find_legacy_add_orbital_station_calls,
    _CREW_XP_LEVEL_PATTERN,
    REMOVED_API_CALLS,
    _scan_removed_api_calls,
    _scan_source_build_dependencies,
    _custom_ui_plugins_missing_button_callback,
)
from .scan_missions import (  # noqa: F401
    MISSION_REQUIRED_FILES,
    _scan_mission_required_files,
    _scan_campaign_fleet_references,
    _scan_mission_local_fleet_references,
    _scan_mission_variant_assets,
    _is_mission_source,
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
from .scan_hyperspace_market import scan_market_on_hyperspace_entity  # noqa: F401
from .scan_mission_map import scan_mission_map_references  # noqa: F401
from .scan_mission_variants import scan_mission_variants_not_defined  # noqa: F401
from .scan_content import (  # noqa: F401
    _scan_assets,
    _scan_wing_roles,
    _registered_csv_ids,
    _scan_content_graph,
    _source_class_index,
    _scan_configured_class_integrity,
    _scan_content_id_renamed_by_provider,
    _scan_star_type_undefined,
    _scan_procgen_rows,
    _vanilla_faction_ids,
    _RULES_MERGED_CONDITION,
    _RULES_FACTION_ID_CONDITION,
    _scan_rules_condition_defects,
)
from .scan_libraries import (  # noqa: F401
    _scan_metadata,
    _scan_mod_info_jar_missing,
    _annotate_source_reachability,
    _local_class_names,
    _attribute_library_usage,
    _dependency_compatibility_context,
    _infer_environment,
    _base_game_version,
    _version_series,
    _scan_mod_info_game_version,
    TOOLBOX_ID,
    TOOLBOX_FORK_MINIMUM,
    _version_tuple,
    toolbox_version_gaps,
    _scan_aotd_toolbox_version,
    _mod_info_declares_dependency,
    _scan_revenantlib_fold_conflict,
    _drop_library_findings_judged_elsewhere,
    _nexerelin_custom_start_classes,
    _only_nexerelin_custom_starts,
    _sources_mentioning,
    _library_import_only,
    LIBRARY_PROBE_MARKERS,
    _PRESENCE_PROBE,
    _library_presence_probed,
    _unguarded_library_users,
    _GUARD_HEADER,
    _MOD_PLUGIN_CLASS,
    _probe_returns_early,
    _IMPORT_LINE,
    _library_call_outside_guard,
    _fails_fast_through_variable,
    _throws_without_library,
    _scan_library_required_by_throw,
    _scan_undeclared_library_dependency,
)
from .scan_factions import (  # noqa: F401
    _scan_faction_known_lists,
    _faction_market_evidence,
    _scan_shiproles,
    _scan_carrier_rework_gap,
    _scan_black_hole_flag,
    VANILLA_PERSONALITY_IDS,
    LEGACY_PERSONALITY_IDS,
    _SOURCE_SET_PERSONALITY,
    _mod_personality_ids,
    _scan_personality_ids,
    _scan_faction_trait_weight_legacy_personality_ids,
    _KNOWN_LISTS,
    _mod_items,
    _csv_tags,
    _scan_faction_known_tags,
)
from .scan_shadowing import (  # noqa: F401
    VANILLA_SHADOW_GROUP_THRESHOLD,
    PRESET_MERGE_FILES,
    _scan_preset_entry_overrides,
    _scan_vanilla_path_shadowing,
    _scan_vanilla_script_shadow_repointable,
    _NEW_GAME_PLUGIN_KEYS,
    _AOTD_REPLUGGED,
    _scan_shared_hook_overrides,
    _industry_plugins,
    _scan_replace_drops_rc8_entries,
    PRESET_WHOLE_ENTRY_REPLACE_FILES,
    _scan_preset_whole_entry_replace,
    _drop_vanilla_registered_weapon_specs,
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
    _scan_hullmod_fleet_dereference,
    unguarded_fleet_dereference_lines,
    _scan_rules_firebest_populate_options,
    _scan_weapon_effect_static_state,
)
from .scan_references import (  # noqa: F401
    _EXTERNAL_DEPENDENCY_PREFIXES,
    _RULE_COMMAND_PATTERN,
    _is_external_dependency_class,
    _collect_csv_column_class_refs,
    _scan_data_class_references_missing,
    _DEPENDENCY_ROOTS_CACHE,
    _dependency_roots,
    _dependency_content_ids,
    _scan_unresolved_content_references,
    _hull_hints,
    _first_value_commented,
    _scan_description_missing,
    _asset_exists,
    _report_asset_reference_missing,
    _walk_sounds_json_files,
    _scan_asset_reference_missing,
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
    _scan_obfuscated_internal_api_use(root, result, vanilla_root)
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
    scan_market_on_hyperspace_entity(root, result)
    scan_mission_map_references(root, result, vanilla_root)
    scan_mission_variants_not_defined(root, result, vanilla_root, provider_roots)
    if compile_check:
        _scan_compile_check(root, result, vanilla_root, provider_roots)
    return result
