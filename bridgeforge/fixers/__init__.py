from __future__ import annotations
import difflib
from pathlib import Path
from ..build_tag import _NAME_PATTERN as _NAME_PATTERN, _STRING_LITERAL as _STRING_LITERAL, _find_top_level_key as _find_top_level_key, _string_literal_to_text as _string_literal_to_text, _structural_depths as _structural_depths, _text_to_string_literal as _text_to_string_literal
from ..safeio import WriteVerificationError as WriteVerificationError, verify_removed as verify_removed, verify_written as verify_written
from ..scanner import DESIGN_TYPE_CSV_TARGETS as DESIGN_TYPE_CSV_TARGETS, FACTION_SPECIAL_ROLE_KEYS as FACTION_SPECIAL_ROLE_KEYS, LEGACY_PERSONALITY_IDS as LEGACY_PERSONALITY_IDS, CUSTOM_UI_PLUGIN_PATTERN as CUSTOM_UI_PLUGIN_PATTERN, MOD_INFO_TRIAGE_BANNER_PATTERN as MOD_INFO_TRIAGE_BANNER_PATTERN, _FULLWIDTH_NUMBER_CHARS as _FULLWIDTH_NUMBER_CHARS, _NUMBER_CELL as _NUMBER_CELL, REMOVED_API_CALLS as REMOVED_API_CALLS, _blank_java_comments as _blank_java_comments, _load_lenient_json_file as _load_lenient_json_file, _parse_json as _parse_json, _read_csv_rows as _read_csv_rows, _read_csv_rows_lenient as _read_csv_rows_lenient, _relative as _relative, _removed_api_call_spans as _removed_api_call_spans, _SOURCE_SET_PERSONALITY as _SOURCE_SET_PERSONALITY, _wing_id_variant_map as _wing_id_variant_map, _wing_ids_set as _wing_ids_set
from .carrier_bays import _MAX_FIGHTER_BAYS as _MAX_FIGHTER_BAYS, _carrier_bays_edit as _carrier_bays_edit, _fix_carrier_bays_proposal as _fix_carrier_bays_proposal, _fix_ship_data_missing_fighter_bays_column as _fix_ship_data_missing_fighter_bays_column, _parse_hull_bay_assignments as _parse_hull_bay_assignments
from .common import FileChange as FileChange, FixPlan as FixPlan, FixerError as FixerError, SUPPORTED_FINDINGS as SUPPORTED_FINDINGS, _LINE_SPLIT_RE as _LINE_SPLIT_RE, _csv_escape as _csv_escape, _csv_records as _csv_records, _decode as _decode, _encode as _encode, _field_value as _field_value, _findings_of as _findings_of, _format_csv_row as _format_csv_row, _line_field_spans as _line_field_spans, _parse_rgb as _parse_rgb, _quote_like as _quote_like, _relative_path as _relative_path, _split_terminator as _split_terminator
from .conversion import SUPPLY_RATIOS as SUPPLY_RATIOS, _SHADOW_ID_KEYS as _SHADOW_ID_KEYS, _fix_conversion_faction_names_missing_content as _fix_conversion_faction_names_missing_content, _fix_conversion_faction_names_removed_hull as _fix_conversion_faction_names_removed_hull, _fix_conversion_vanilla_lifecycle_plugin as _fix_conversion_vanilla_lifecycle_plugin, _fix_dependency_version_major_mismatch as _fix_dependency_version_major_mismatch, _fix_factions_csv_relists_neutral as _fix_factions_csv_relists_neutral, _fix_ship_data_supplies_legacy_column as _fix_ship_data_supplies_legacy_column, _fix_vanilla_path_shadowing as _fix_vanilla_path_shadowing, _matching_brace as _matching_brace
from .csv_data import _add_design_type_color as _add_design_type_color, _fix_csv_fullwidth_number as _fix_csv_fullwidth_number, _fix_csv_missing_design_type_column as _fix_csv_missing_design_type_column, _fix_csv_row_extra_columns as _fix_csv_row_extra_columns, _fix_csv_slash_quote_escape as _fix_csv_slash_quote_escape, _fix_csv_vanilla_row_override as _fix_csv_vanilla_row_override, _fix_person_names_duplicate_row as _fix_person_names_duplicate_row, _fix_rules_csv_curly_quote_unreadable as _fix_rules_csv_curly_quote_unreadable, _fix_rules_csv_duplicate_id as _fix_rules_csv_duplicate_id, _fix_rules_csv_whitespace_only_line as _fix_rules_csv_whitespace_only_line, _fullwidth_cells as _fullwidth_cells
from .dependencies import _DEPENDENCY_ENTRY_ID_PATTERN as _DEPENDENCY_ENTRY_ID_PATTERN, _DEPENDENCY_ENTRY_PATTERN as _DEPENDENCY_ENTRY_PATTERN, _add_dependency_entry as _add_dependency_entry, _fix_revenantlib_fold_conflict as _fix_revenantlib_fold_conflict, _fix_undeclared_library_dependency as _fix_undeclared_library_dependency, _remove_dependency_entries as _remove_dependency_entries
from .encoding import NAMED_ENCODINGS_FILE as NAMED_ENCODINGS_FILE, _CP1252_TYPOGRAPHY as _CP1252_TYPOGRAPHY, _NAMEABLE_ENCODINGS as _NAMEABLE_ENCODINGS, _REFERENCE_SUFFIXES as _REFERENCE_SUFFIXES, _fix_data_file_not_utf8 as _fix_data_file_not_utf8, _invalid_utf8_offsets as _invalid_utf8_offsets, _named_encodings_path as _named_encodings_path, _reencode_invalid as _reencode_invalid, _referencing_bytes as _referencing_bytes, pending_named_encodings as pending_named_encodings, record_named_encodings as record_named_encodings
from .faction_weights import _ID_WEIGHT_KEY_VALUE_PATTERN as _ID_WEIGHT_KEY_VALUE_PATTERN, _SHIP_ROLES_KEY_PATTERN as _SHIP_ROLES_KEY_PATTERN, _TRAITS_KEY_PATTERN as _TRAITS_KEY_PATTERN, _fix_faction_trait_weight_legacy_personality_id as _fix_faction_trait_weight_legacy_personality_id, _fix_shippable_work_file as _fix_shippable_work_file, _fix_shiproles_wing_id as _fix_shiproles_wing_id, _format_weight_sum as _format_weight_sum, _matching_close_brace as _matching_close_brace, _rewrite_id_weight_object as _rewrite_id_weight_object
from .factions import _fix_faction_known_lists_missing as _fix_faction_known_lists_missing, _hull_ids as _hull_ids, _load_variant as _load_variant, _weapon_ids as _weapon_ids
from .interfaces import _HULL_MOD_EFFECT_DEFAULTS as _HULL_MOD_EFFECT_DEFAULTS, _SHIP_SYSTEM_DEFAULTS as _SHIP_SYSTEM_DEFAULTS, _fix_missing_custom_ui_button_pressed_callback as _fix_missing_custom_ui_button_pressed_callback, _fix_rc8_signature_changed as _fix_rc8_signature_changed, _fix_target_interface_method_missing as _fix_target_interface_method_missing, _insert_before_class_end as _insert_before_class_end
from .java_guards import _FIREBEST_POPULATE_OPTIONS_PATTERN as _FIREBEST_POPULATE_OPTIONS_PATTERN, _REMOVE_MARKET_LINE as _REMOVE_MARKET_LINE, _TEMP_MARKET as _TEMP_MARKET, _VOID_METHOD_HEADER as _VOID_METHOD_HEADER, _fix_campaign_lookup_guard as _fix_campaign_lookup_guard, _fix_lookup_dereferenced_unguarded as _fix_lookup_dereferenced_unguarded, _fix_nexerelin_corvus_mode_import as _fix_nexerelin_corvus_mode_import, _fix_personality_id_unknown as _fix_personality_id_unknown, _fix_rules_firebest_populate_options as _fix_rules_firebest_populate_options, _fix_temporary_market_fleet_source as _fix_temporary_market_fleet_source, _temporary_market_sources as _temporary_market_sources
from .json_data import _ObjectScan as _ObjectScan, _fix_json_duplicate_key as _fix_json_duplicate_key, _repeated_key_edits as _repeated_key_edits
from .mod_info import _GAME_VERSION_PATTERN as _GAME_VERSION_PATTERN, _LEADING_BANNER_PATTERN as _LEADING_BANNER_PATTERN, _fix_mod_info_game_version_inexact as _fix_mod_info_game_version_inexact, _fix_mod_info_triage_banner as _fix_mod_info_triage_banner
from .procgen import _GEN_ROW_KEYWORDS as _GEN_ROW_KEYWORDS, _fix_procgen_mod_body_leak as _fix_procgen_mod_body_leak, _fix_procgen_row_missing as _fix_procgen_row_missing, nearest_vanilla_gen_row as nearest_vanilla_gen_row
from .removed_api import _ADD_MESSAGE_TAIL_PATTERN as _ADD_MESSAGE_TAIL_PATTERN, _ADD_ORBITAL_STATION_SIGNATURE as _ADD_ORBITAL_STATION_SIGNATURE, _ADD_PLANET_SIGNATURE as _ADD_PLANET_SIGNATURE, _BF_CALL_SIGNATURES as _BF_CALL_SIGNATURES, _CALL_PREFIX_ADD_ORBITAL_STATION as _CALL_PREFIX_ADD_ORBITAL_STATION, _CALL_PREFIX_ADD_PLANET as _CALL_PREFIX_ADD_PLANET, _CREATE_FLEET_SIGNATURE as _CREATE_FLEET_SIGNATURE, _CREW_XP_LEVEL_DECLARATION_PATTERN as _CREW_XP_LEVEL_DECLARATION_PATTERN, _CREW_XP_LEVEL_MATCHER as _CREW_XP_LEVEL_MATCHER, _CREW_XP_LEVEL_SIGNATURE as _CREW_XP_LEVEL_SIGNATURE, _DEPENDENCIES_ARRAY_PATTERN as _DEPENDENCIES_ARRAY_PATTERN, _LEGACY_FLEETS_CALL as _LEGACY_FLEETS_CALL, _REMOVED_API_CALL_REWRITES as _REMOVED_API_CALL_REWRITES, _REVENANTLIB_DEPENDENCY_ENTRY as _REVENANTLIB_DEPENDENCY_ENTRY, _add_revenantlib_dependency as _add_revenantlib_dependency, _fix_removed_api_call as _fix_removed_api_call, _rewrite_add_message_span as _rewrite_add_message_span, _rewrite_add_orbital_station_span as _rewrite_add_orbital_station_span, _rewrite_add_planet_span as _rewrite_add_planet_span, _rewrite_create_fleet_span as _rewrite_create_fleet_span, _rewrite_crew_xp_level_span as _rewrite_crew_xp_level_span
from .runtime import _BF_SPAWN_CAPTAIN as _BF_SPAWN_CAPTAIN, _PLACEHOLDER_HOOKS as _PLACEHOLDER_HOOKS, _SPAWN_THREE_ARGS as _SPAWN_THREE_ARGS, _fix_black_hole_type_missing_flag as _fix_black_hole_type_missing_flag, _fix_hulk_death_effect_repeats as _fix_hulk_death_effect_repeats, _fix_hullmod_instance_state as _fix_hullmod_instance_state, _fix_runtime_placeholder_hooks as _fix_runtime_placeholder_hooks, _fix_spawned_ship_captain as _fix_spawned_ship_captain
from .variants import _STRING_PAIR_RE as _STRING_PAIR_RE, _enclosing_bracket as _enclosing_bracket, _fix_fleet_type_name_missing as _fix_fleet_type_name_missing, _fix_variant_op_over_budget as _fix_variant_op_over_budget, _fix_variant_weapon_slot_removed as _fix_variant_weapon_slot_removed, _fix_variant_wings_exceed_bays as _fix_variant_wings_exceed_bays, _fleet_type_display_name as _fleet_type_display_name, _matching_bracket as _matching_bracket, _remove_span_with_comma as _remove_span_with_comma
from .wing_costs import _approved_wing_costs as _approved_wing_costs, _fix_builtin_wing_is_hullmod as _fix_builtin_wing_is_hullmod, _fix_json_missing_comma as _fix_json_missing_comma, _fix_wing_op_cost_blank as _fix_wing_op_cost_blank, _raw_csv_spans as _raw_csv_spans
from .wing_data import _fix_wing_data_missing_role_desc_column as _fix_wing_data_missing_role_desc_column
from .wing_role import _fix_wing_role_assault_removed as _fix_wing_role_assault_removed
from .data import _fix_local_weapon_spec_unregistered as _fix_local_weapon_spec_unregistered
from .guards import _fix_orbit_period_computed_unguarded as _fix_orbit_period_computed_unguarded, _fix_system_generation_unguarded as _fix_system_generation_unguarded
from .presets import _fix_preset_entry_drops_vanilla_fields as _fix_preset_entry_drops_vanilla_fields
from .substitute import fix_content_reference_substitute as fix_content_reference_substitute


_FIXER_FUNCS = {
    "system-generation-unguarded": _fix_system_generation_unguarded,
    "orbit-period-computed-unguarded": _fix_orbit_period_computed_unguarded,
    "local-weapon-spec-unregistered": _fix_local_weapon_spec_unregistered,
    "content-reference-substitute": fix_content_reference_substitute,
    "preset-entry-drops-vanilla-fields": _fix_preset_entry_drops_vanilla_fields,
    "hard-coded-campaign-system-reference": lambda root, options: _fix_campaign_lookup_guard(root, options, "hard-coded-campaign-system-reference"),
    "hard-coded-campaign-entity-reference": lambda root, options: _fix_campaign_lookup_guard(root, options, "hard-coded-campaign-entity-reference"),
    "csv-slash-quote-escape": _fix_csv_slash_quote_escape,
    "procgen-mod-body-leak": _fix_procgen_mod_body_leak,
    "fleet-type-name-missing": _fix_fleet_type_name_missing,
    "variant-op-over-budget": _fix_variant_op_over_budget,
    "variant-wings-exceed-bays": _fix_variant_wings_exceed_bays,
    "variant-weapon-slot-mismatch": lambda root, options: _fix_variant_weapon_slot_removed(root, options, "variant-weapon-slot-mismatch"),
    "variant-weapon-slot-missing": lambda root, options: _fix_variant_weapon_slot_removed(root, options, "variant-weapon-slot-missing"),
    "data-file-not-utf8": _fix_data_file_not_utf8,
    "shippable-work-file": _fix_shippable_work_file,
    "wing-role-assault-removed": _fix_wing_role_assault_removed,
    "mod-info-game-version-inexact": _fix_mod_info_game_version_inexact,
    "wing-data-missing-role-desc-column": _fix_wing_data_missing_role_desc_column,
    "target-interface-method-missing": _fix_target_interface_method_missing,
    "removed-api-call": _fix_removed_api_call,
    "csv-row-extra-columns": _fix_csv_row_extra_columns,
    "csv-missing-design-type-column": _fix_csv_missing_design_type_column,
    "procgen-planet-row-missing": lambda root, options: _fix_procgen_row_missing(root, "procgen-planet-row-missing", options),
    "procgen-star-row-missing": lambda root, options: _fix_procgen_row_missing(root, "procgen-star-row-missing", options),
    "faction-known-lists-missing": _fix_faction_known_lists_missing,
    "mod-info-triage-banner": _fix_mod_info_triage_banner,
    "carrier-bays-proposal": _fix_carrier_bays_proposal,
    "revenantlib-fold-conflict": _fix_revenantlib_fold_conflict,
    "undeclared-library-dependency": _fix_undeclared_library_dependency,
    "rules-firebest-populate-options": _fix_rules_firebest_populate_options,
    "personality-id-unknown": _fix_personality_id_unknown,
    "hullmod-instance-state": _fix_hullmod_instance_state,
    "runtime-placeholder-unsupported-operation": _fix_runtime_placeholder_hooks,
    "hulk-death-effect-repeats": _fix_hulk_death_effect_repeats,
    "black-hole-type-missing-flag": _fix_black_hole_type_missing_flag,
    "nexerelin-corvus-mode-import": _fix_nexerelin_corvus_mode_import,
    "spawned-ship-captain-personality-risk": _fix_spawned_ship_captain,
    "json-missing-comma": _fix_json_missing_comma,
    "builtin-wing-is-hullmod": _fix_builtin_wing_is_hullmod,
    "wing-op-cost-blank": _fix_wing_op_cost_blank,
    "campaign-lookup-dereferenced-unguarded": _fix_lookup_dereferenced_unguarded,
    "temporary-market-fleet-source": _fix_temporary_market_fleet_source,
    "person-names-duplicate-row": _fix_person_names_duplicate_row,
    "json-duplicate-key": _fix_json_duplicate_key,
    "dependency-version-major-mismatch": _fix_dependency_version_major_mismatch,
    "conversion-faction-names-removed-hull": _fix_conversion_faction_names_removed_hull,
    "conversion-faction-names-missing-content": _fix_conversion_faction_names_missing_content,
    "conversion-vanilla-lifecycle-plugin": _fix_conversion_vanilla_lifecycle_plugin,
    "factions-csv-relists-neutral": _fix_factions_csv_relists_neutral,
    "vanilla-path-shadowing": _fix_vanilla_path_shadowing,
    "ship-data-supplies-legacy-column": _fix_ship_data_supplies_legacy_column,
    "rules-csv-duplicate-id": _fix_rules_csv_duplicate_id,
    "rules-csv-whitespace-only-line": _fix_rules_csv_whitespace_only_line,
    "rules-csv-curly-quote-unreadable": _fix_rules_csv_curly_quote_unreadable,
    "csv-vanilla-row-override": _fix_csv_vanilla_row_override,
    "rc8-signature-changed": _fix_rc8_signature_changed,
    "faction-trait-weight-legacy-personality-id": _fix_faction_trait_weight_legacy_personality_id,
    "shiproles-wing-id": _fix_shiproles_wing_id,
    "csv-fullwidth-number": _fix_csv_fullwidth_number,
    "ship-data-missing-fighter-bays-column": _fix_ship_data_missing_fighter_bays_column,
    "missing-custom-ui-button-pressed-callback": _fix_missing_custom_ui_button_pressed_callback,
}


def compute_fix(mod_dir: Path, finding_id: str, options: dict | None = None) -> FixPlan:
    """Compute (never write) the surgical edit(s) for one supported finding id."""
    if finding_id not in SUPPORTED_FINDINGS:
        raise FixerError(f"Unsupported finding id '{finding_id}'. Supported: {', '.join(SUPPORTED_FINDINGS)}")
    root = Path(mod_dir).expanduser().resolve()
    if not root.is_dir():
        raise FixerError(f"{root} is not an existing directory.")
    options = options or {}
    handler = _FIXER_FUNCS[finding_id]
    try:
        changes = [change for change in handler(root, options) if change.changed]
    except UnicodeDecodeError as exc:
        # _decode is strict on purpose: a lossy read would write U+FFFD back (seen in Molecular Replicator, 2026-10-04).
        raise FixerError(f"A file this fix reads is not valid UTF-8 ({exc.reason} at byte {exc.start}); run the data-file-not-utf8 fix first.") from exc
    if not changes:
        raise FixerError(f"No change was computed for finding '{finding_id}'.")
    if not options.get("allow_shadowed_edit"):
        _refuse_shadowed_edits(root, changes, options.get("provider_roots"))
    return FixPlan(finding_id=finding_id, mod_root=root, changes=changes)


def _refuse_shadowed_edits(root: Path, changes: list[FileChange], provider_roots: list[Path] | None = None) -> None:
    """Refuse a plan that edits a loose script one of this mod's own jars already shadows (ROADMAP
    P14 item 14). `loose-script-shadowed-by-jar` already says editing such a file has no effect - the
    game loads the jar class and never compiles the loose one - but nothing previously stopped a
    fixer writing the edit anyway. Found 2026-09-20: a task converted six `setPersonality(...)` calls
    in Thule-Legacy's `MissionDefinition.java` with a full evidence trail, and it changed nothing
    in-game, because `ThuleLegacy.jar` shipped that exact class. Pass `allow_shadowed_edit: True` in
    `compute_fix`'s `options` only when the jar is also being rebuilt from the patched source in the
    same pass (as this exact case was, once caught) - otherwise the edit is dead on arrival.

    ROADMAP P14 item 12 extends the same guard to a *declared dependency's* jar (Maelstrom
    Interstellar Imperium Unofficial Expansion, escalation E8) - all mod jars share one classloader,
    so the rule is identical either way. `options["provider_roots"]` (default: the same
    `<repo>/In operation` + rig mods default `compile-check`/`dependency-substitutes` use) can
    override which providers are searched.
    """
    from ..scanner import _dependency_jar_class_names, loose_script_jar_shadowed_class

    dependency_classes = None  # computed lazily, once, only if a candidate script needs it
    for change in changes:
        if change.path.suffix.lower() != ".java":
            continue
        try:
            relative = change.path.relative_to(root)
        except ValueError:
            continue
        if "data" not in relative.parts:
            continue
        shadowing_class = loose_script_jar_shadowed_class(root, change.path)
        if shadowing_class is not None:
            raise FixerError(
                f"{change.path} is shadowed by a class already compiled into one of this mod's own jars "
                f"({shadowing_class}): the game loads the jar's class and never compiles this loose script, "
                "so editing it has no effect. Rebuild the jar from the patched source (or strip the class "
                "so the loose script compiles), or pass allow_shadowed_edit=True if that is already planned "
                "as part of this same fix."
            )
        if dependency_classes is None:
            dependency_classes = _dependency_jar_class_names(root, provider_roots)
        class_name = ".".join(relative.with_suffix("").parts)
        provider_name = dependency_classes.get(class_name)
        if provider_name is not None:
            raise FixerError(
                f"{change.path} is shadowed by a class already compiled into the declared dependency "
                f"{provider_name}'s own jar ({class_name}): the game loads {provider_name}'s class and never "
                "compiles this loose script, so editing it has no effect. Patch the dependency's jar (or its "
                "source, if you can rebuild it) instead, or pass allow_shadowed_edit=True if that is already "
                "planned as part of this same fix."
            )


def unified_diff_for_change(change: FileChange) -> str:
    """A unified diff for one FileChange, decoding best-effort for display only (never affects the write)."""
    if change.removed:
        return f"--- {change.path}\n+++ /dev/null\n@@ removed ({len(change.before)} bytes) @@\n"
    if not change.existed_before and b"\x00" in change.after[:8192]:
        return f"--- /dev/null\n+++ {change.path}\n@@ new binary file ({len(change.after)} bytes) @@\n"
    try:
        before_text = change.before.decode("utf-8-sig")
    except UnicodeDecodeError:
        before_text = repr(change.before)
    try:
        after_text = change.after.decode("utf-8-sig")
    except UnicodeDecodeError:
        after_text = repr(change.after)
    diff = difflib.unified_diff(
        before_text.splitlines(keepends=True),
        after_text.splitlines(keepends=True),
        fromfile=str(change.path) if change.existed_before else "/dev/null",
        tofile=str(change.path),
    )
    return "".join(diff)


def _backup_path(path: Path, finding_id: str) -> Path:
    base = path.with_name(f"{path.name}.pre-bf-fix-{finding_id}.bak")
    if not base.exists():
        return base
    counter = 2
    while True:
        candidate = path.with_name(f"{path.name}.pre-bf-fix-{finding_id}.bak.{counter}")
        if not candidate.exists():
            return candidate
        counter += 1


def apply_fix(plan: FixPlan) -> list[dict[str, object]]:
    """Write every planned change, keeping a `.pre-bf-fix-<id>.bak` backup per pre-existing file."""
    applied: list[dict[str, object]] = []
    copies = {change.after for change in plan.changes if not change.existed_before and not change.removed}
    for change in plan.changes:
        backup: Path | None = None
        if change.removed:
            # A move's new copy is its backup; a bare removal keeps the usual .bak next to it.
            if change.before not in copies:
                backup = _backup_path(change.path, plan.finding_id)
                backup.write_bytes(change.before)
            change.path.unlink()
            applied.append({"path": str(change.path), "backup": str(backup) if backup is not None else None, "removed": True})
            continue
        if change.existed_before:
            backup = _backup_path(change.path, plan.finding_id)
            backup.write_bytes(change.before)
        change.path.parent.mkdir(parents=True, exist_ok=True)
        change.path.write_bytes(change.after)
        applied.append({"path": str(change.path), "backup": str(backup) if backup is not None else None})
    _verify_applied(plan)
    return applied


def _verify_applied(plan: FixPlan) -> None:
    """Re-read every written path: each changed file must hold the planned bytes, each removed one must be gone.

    A fixer's backup is kept either way, so a failure here loses nothing (BUGS.md FIX-001: a data-file-not-utf8 fix
    once left only `rules.csv.pre-bf-fix-data-file-not-utf8.bak` behind).
    """
    problems = []
    for change in plan.changes:
        try:
            if change.removed:
                verify_removed(change.path)
            else:
                verify_written(change.path, change.after)
        except WriteVerificationError as exc:
            problems.append(str(exc))
    if problems:
        raise FixerError(f"Fix '{plan.finding_id}' did not leave the planned files; the .pre-bf-fix backups were kept: " + "; ".join(problems))
