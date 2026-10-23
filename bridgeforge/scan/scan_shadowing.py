"""Vanilla shadowing and override checks: preset entries, path shadowing, shared hooks, replace-drops."""
from __future__ import annotations

from ..models import ScanResult
from pathlib import Path
from .scan_classfile import NON_MOD_JAR_DIRS
from .scan_common import SHADOW_PATH_EXTENSIONS, _relative
from .scan_content import _registered_csv_ids
from .scan_json import _load_lenient_json_file
from .scan_settings import _mod_declared_script_rows


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
    from ..data_diff import _diff  # data_diff imports this module

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
