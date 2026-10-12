"""Reference checks: data class references, unresolved content ids, asset references, descriptions."""
from __future__ import annotations

import re
from .models import ScanResult
from collections import Counter
from pathlib import Path
from .scan_classfile import _dependency_jar_class_names
from .scan_common import _relative
from .scan_content import _source_class_index
from .scan_jarchecks import _vanilla_api_jar_class_info, _vanilla_loose_script_fqns
from .scan_json import _csv_header, _load_lenient_json_file, _read_csv_rows, _read_csv_rows_lenient
from .scan_ships import _csv_id_index, _ship_file_index, _skin_index, _wpn_type_size_index


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
