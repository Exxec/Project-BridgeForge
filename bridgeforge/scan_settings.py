"""settings.json replace-array, fleet type names and missing settings key checks."""
from __future__ import annotations

import csv
import re
from .models import ScanResult
from pathlib import Path
from .scan_common import SETTINGS_ACCEPT_LIMIT, SETTINGS_BASELINE_FILE, _relative
from .scan_fleets import _JDK_FOR_PROCGEN
from .scan_javatext import _blank_java_comments
from .scan_json import _load_lenient_json_file


# A mod that ships a modified copy of a vanilla *script* at vanilla's own path (Rebal's 47 hullmod
# scripts) usually doesn't have to. Starsector resolves a hullmod/shipsystem script by the class
# name in a CSV row's `script` column (or a `.system` file's `statsScript` key), and those CSVs
# merge by row id - so a mod that already ships the row can rename its own class and repoint the
# row at it, leaving vanilla's file untouched. Same behaviour, no shadow, and it survives the next
# vanilla update instead of silently reverting it. Found designing Rebal's rebuild (2026-09-22);
# corpus-wide prevalence before building this: 9 mods shadow a vanilla .java, 3 of them (49
# instances - Rebal 47, Mountain-and-Sea 1, Shielded-Holds-For-All 1) are repointable this way.
_REPOINTABLE_SCRIPT_CSVS = (
    ("data/hullmods/hull_mods.csv", "script"),
    ("data/shipsystems/ship_systems.csv", "script"),
)


def _mod_declared_script_rows(root: Path) -> dict[str, str]:
    """simple class name -> the mod's own row/file that names it (CSV `script`, `.system` statsScript)."""
    declared: dict[str, str] = {}
    for relative, column in _REPOINTABLE_SCRIPT_CSVS:
        path = root / relative
        if not path.is_file():
            continue
        try:
            with path.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
                for row in csv.DictReader(handle):
                    script = (row.get(column) or "").strip()
                    if not script:
                        continue
                    row_id = (row.get("id") or "").strip() or "?"
                    declared.setdefault(script.rsplit(".", 1)[-1], f"{relative} id={row_id}")
        except OSError:
            continue
    for path in sorted((root / "data" / "shipsystems").glob("*.system")):
        data = _load_lenient_json_file(path)
        if not isinstance(data, dict):
            continue
        script = data.get("statsScript")
        if isinstance(script, str) and script.strip():
            declared.setdefault(script.strip().rsplit(".", 1)[-1], f"{_relative(root, path)} statsScript")
    return declared


# mod_info.json's "replace" array is live in RC8: ModManager reads it with optJSONArray("replace")
# into ModSpec.getFullOverrides() ("do not merge this file, replace it wholesale"), and **silently
# drops any entry ending in settings.json** - so settings.json always merges and can never be fully
# replaced by any mod (bytecode-verified against starfarer_obf.jar, 2026-09-22; see ESCALATIONS E13
# Finding 1 / E15). Both facts are invisible to a mod author: a declaration that does nothing, and
# a file that cannot be made authoritative however it is declared.
_REPLACE_IGNORED_SUFFIX = "settings.json"


_CREATE_EMPTY_FLEET = re.compile(r'createEmptyFleet\(\s*"([^"]+)"\s*,\s*"([^"]+)"')


def _fleet_type_names(path: Path) -> set[str]:
    data = _load_lenient_json_file(path)
    if not isinstance(data, dict):
        return set()
    names = data.get("fleetTypeNames", data)  # a .faction nests them; default_fleet_type_names.json is the map itself
    return set(names) if isinstance(names, dict) else set()


def _scan_fleet_type_names(root: Path, result: ScanResult, vanilla_core: Path | None) -> None:
    """A fleet created with a type its faction has no display name for (P15 item 20.15).

    Zorg18's live run (2026-09-27): encounters read "Zorg Hive no name for type [Zeta AI raid]" because
    `createEmptyFleet("zorg", "Zeta AI raid", null)` named a type absent from `zorg.faction`'s
    `fleetTypeNames`. Names come from the faction file, then `data/world/factions/default_fleet_type_names.json`
    (vanilla's, and a mod's own). Source literals only (loose scripts and jar sources); needs the vanilla core.
    """
    if vanilla_core is None:
        return
    factions_dir = Path(vanilla_core) / "data" / "world" / "factions"
    defaults = _fleet_type_names(factions_dir / "default_fleet_type_names.json") | _fleet_type_names(root / "data" / "world" / "factions" / "default_fleet_type_names.json")
    missing: dict[tuple[str, str], list[str]] = {}
    for source in sorted(root.rglob("*.java")):
        if "disabled_files" in source.relative_to(root).parts:
            continue
        try:
            text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        for faction_id, fleet_type in _CREATE_EMPTY_FLEET.findall(text):
            faction_file = root / "data" / "world" / "factions" / f"{faction_id}.faction"
            if not faction_file.is_file():
                faction_file = factions_dir / f"{faction_id}.faction"
            if fleet_type in defaults or fleet_type in _fleet_type_names(faction_file):
                continue
            missing.setdefault((faction_id, fleet_type), []).append(_relative(root, source))
    for (faction_id, fleet_type), files in sorted(missing.items()):
        result.add(
            id="fleet-type-name-missing",
            category="campaign",
            severity="low",
            classification="REVIEW",
            confidence="DETERMINISTIC",
            explanation=f"Fleets are created with type \"{fleet_type}\" for faction \"{faction_id}\", but neither the faction file's fleetTypeNames nor default_fleet_type_names.json names it, so every encounter shows \"no name for type [{fleet_type}]\". Add a fleetTypeNames entry to the faction file.",
            file=f"data/world/factions/{faction_id}.faction",
            evidence=[f"type:{fleet_type}", f"faction:{faction_id}", *sorted(set(files))[:5]],
        )


def _scan_procgen_mod_body_leak(root: Path, result: ScanResult) -> None:
    """A star/planet type the mod places itself by id that also has a procgen weight (P15 item 25).

    Zorg18 (2026-09-27): `star_zorg` carried vanilla `star_yellow`'s weights (40/35/30) and `zorg_planet` weight 10,
    so the artificial star meant for Zorg Zeta also appeared in random systems (owner saw one in Johannam). A
    type the mod places by id and also weights in `star_gen_data.csv`/`planet_gen_data.csv` spawns in both
    places; REVIEW because a planet pack may want that.
    """
    from .campaign_layout import mod_body_types, mod_placed_types

    types = mod_body_types(root)
    weighted = {t for t, facts in types.items() if facts["procgen_weight"] > 0}
    if not weighted:
        return
    placed = mod_placed_types(root, weighted)
    for type_id in sorted(placed):
        result.add(
            id="procgen-mod-body-leak",
            category="campaign",
            severity="medium",
            classification="REVIEW",
            confidence="HIGH",
            explanation=f"The mod places \"{type_id}\" itself by id and also gives it a procedural-generation weight ({types[type_id]['procgen_weight']:g}), so it also appears in random systems of every new sector. If it is meant to be unique to the mod's own system, set its frequency to 0.",
            file="data/campaign/procgen/" + ("star_gen_data.csv" if types[type_id]["star"] else "planet_gen_data.csv"),
            evidence=[f"type:{type_id}", f"weight:{types[type_id]['procgen_weight']:g}"],
        )


def _scan_replace_array(root: Path, result: ScanResult, vanilla_core: Path | None) -> None:
    """`replace` entries RC8 ignores or that name a file the mod does not ship, plus settings breadth."""
    mod_info = _load_lenient_json_file(root / "mod_info.json")
    if not isinstance(mod_info, dict):
        return
    entries = mod_info.get("replace")
    normalized: list[str] = []
    if isinstance(entries, list):
        normalized = [item.replace("\\", "/").lstrip("/") for item in entries if isinstance(item, str) and item.strip()]
    ignored = sorted({item for item in normalized if item.endswith(_REPLACE_IGNORED_SUFFIX)})
    if ignored:
        result.add(
            id="replace-entry-ignored",
            category="metadata",
            severity="medium",
            classification="REVIEW",
            confidence="DETERMINISTIC",
            explanation=(
                "mod_info.json's \"replace\" array lists a settings.json, but RC8's own mod loader skips exactly "
                "those entries (ModManager drops any entry ending in settings.json before building the mod's "
                "full-override set, javap-verified). The declaration has no effect and never will: settings.json "
                "always merges key-by-key, so vanilla keys this mod does not name survive, and a key cannot be "
                "removed this way. Apply anything merge cannot express at runtime instead - SettingsAPI has "
                "setFloat/setBoolean, and getSettingsJSON() for the rest."
            ),
            file="mod_info.json",
            evidence=ignored,
        )
    stale = sorted({item for item in normalized if not (root / item).is_file()})
    if stale:
        result.add(
            id="replace-entry-stale",
            category="metadata",
            severity="low",
            classification="REVIEW",
            confidence="DETERMINISTIC",
            explanation=(
                "mod_info.json's \"replace\" array names files this mod does not ship. Each entry is dead "
                "metadata: it declares a full override of a file that is not there, so nothing is overridden. "
                "Usually left behind when content was dropped or renamed. Harmless at runtime, but it makes the "
                "declared override set untrustworthy as a record of what the mod actually replaces."
            ),
            file="mod_info.json",
            evidence=[f"count:{len(stale)}", *stale[:25]],
        )
    if vanilla_core is None:
        return
    mod_settings = _load_lenient_json_file(root / "data" / "config" / "settings.json")
    vanilla_settings = _load_lenient_json_file(Path(vanilla_core) / "data" / "config" / "settings.json")
    if not isinstance(mod_settings, dict) or not isinstance(vanilla_settings, dict):
        return
    overridden = sorted(_settings_value_changes(mod_settings, vanilla_settings))
    if not overridden:
        return
    # Owner's held rule (ROADMAP item 19, 2026-09-27; cleared once list merging was settled the same day): a small,
    # deliberate set of up to SETTINGS_ACCEPT_LIMIT changed values is accepted, recorded per mod with the exact keys
    # in <workspace>/SETTINGS_BASELINE.json (revive writes it) so any later change shows. Larger sets stay REVIEW.
    baseline_path = root.parent / SETTINGS_BASELINE_FILE if root.name == "working" else None
    baseline = None
    if baseline_path is not None and baseline_path.is_file():
        loaded = _load_lenient_json_file(baseline_path) or {}
        baseline = sorted(loaded.get("keys") or []) if isinstance(loaded, dict) else None
    if len(overridden) <= SETTINGS_ACCEPT_LIMIT and (baseline is None or baseline == overridden):
        result.add(
            id="settings-json-override-accepted", category="metadata", severity="info", classification="SAFE", confidence="DETERMINISTIC",
            explanation=(f"data/config/settings.json changes {len(overridden)} vanilla value(s), within the owner's accepted limit of "
                         f"{SETTINGS_ACCEPT_LIMIT} for a deliberate tuning set. The exact keys are " + ("recorded in the workspace's "
                         f"{SETTINGS_BASELINE_FILE}, and match." if baseline is not None else f"listed here; revive records them in {SETTINGS_BASELINE_FILE}.")),
            file="data/config/settings.json", evidence=[f"overridden:{len(overridden)}", *overridden])
        return
    baseline_note = ""
    if baseline is not None and baseline != overridden:
        added, dropped = sorted(set(overridden) - set(baseline)), sorted(set(baseline) - set(overridden))
        baseline_note = (f" The keys changed since {SETTINGS_BASELINE_FILE} was recorded: added {', '.join(added[:10]) or 'none'}; "
                         f"no longer changed {', '.join(dropped[:10]) or 'none'}.")
    result.add(
        id="settings-json-override-breadth",
        category="metadata",
        severity="medium" if len(overridden) > 100 else "low",
        classification="REVIEW",
        confidence="DETERMINISTIC",
        explanation=(
            f"This mod's data/config/settings.json changes {len(overridden)} value(s) vanilla already sets "
            f"(vanilla has {len(vanilla_settings)} top-level keys; entries a mod only adds are not counted). settings.json always merges (it cannot be fully replaced), so each of these silently "
            "wins over the current game's value for every mod and the base game alike. A small, deliberate tuning "
            "set is normal; a large one usually means a near-complete copy of an older settings.json, which "
            "reverts the game's own tuning across four versions with no error. Review the list, not the count - "
            "this is blast radius, not a verdict."
        ) + baseline_note,
        file="data/config/settings.json",
        evidence=[f"overridden:{len(overridden)}", f"vanilla-keys:{len(vanilla_settings)}", *overridden[:25]],
    )


def _settings_value_changes(mod: dict, vanilla: dict, prefix: str = "") -> list[str]:
    """Dotted paths where the mod's settings.json changes a value vanilla already has.

    settings.json merges objects key by key, so an entry a mod only adds inside `plugins`, `graphics` or
    `designTypeColors` leaves vanilla's own entries alone: SEEKER, Exigency and Flu-X all do this and ran
    normally on the RC8 rig (live runs 2026-09-24). Comparing whole top-level keys counted those additions
    as overriding the whole block (14 mods blocked, 9 by additions alone; 2026-09-27). Lists and scalars
    still count as a change when they differ: how a list merges is not evidenced."""
    changes: list[str] = []
    for key, value in mod.items():
        if key not in vanilla:
            continue
        path = f"{prefix}{key}"
        if isinstance(value, dict) and isinstance(vanilla[key], dict):
            changes.extend(_settings_value_changes(value, vanilla[key], path + "."))
        elif value != vanilla[key]:
            changes.append(path)
    return changes


def _scan_settings_keys_missing(root: Path, result: ScanResult, vanilla_core: Path | None) -> None:
    """Literal settings reads whose key no settings.json defines (bridgeforge.settings_keys; Exigency 0.8 crashed on
    opening a market reading blackMarketMinSupplies, 2026-10-04). Needs the vanilla core to know RC8's keys."""
    if vanilla_core is None:
        return
    from .settings_keys import guarded_keys, jar_reads, settings_keys, source_reads

    known = settings_keys(vanilla_core / "data" / "config" / "settings.json", root / "data" / "config" / "settings.json",
                          *[Path(d) / "data" / "config" / "settings.json" for d in result.migration_context.get("dependency_roots") or []])
    if not known:
        return
    reads: list[tuple[str, str, str, str]] = []
    guarded_by_path: dict[str, set[str]] = {}
    for source in sorted(root.rglob("*.java")):
        if "disabled_files" in source.relative_to(root).parts:
            continue
        try:
            text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if "getSettings" in text:
            reads += [(_relative(root, source), f"line:{line}", getter, key) for line, getter, key in source_reads(text)]
            guarded_by_path[_relative(root, source)] = guarded_keys(text)
    jars = [p for p in root.rglob("*.jar") if "disabled_files" not in p.relative_to(root).parts]
    if jars:
        if not _JDK_FOR_PROCGEN:
            from .java_toolchain import find_jdk

            _JDK_FOR_PROCGEN.append(find_jdk())
        if _JDK_FOR_PROCGEN[0] is not None:
            for jar in jars:
                for cls, getter, key in jar_reads(jar, _JDK_FOR_PROCGEN[0].javap):
                    # The class's bundled source shows this read behind an isModEnabled guard (Kadur Remnant).
                    stem = cls.split("$", 1)[0].removesuffix(".class") + ".java"
                    if any(path.endswith(stem) and key in keys for path, keys in guarded_by_path.items()):
                        continue
                    reads.append((f"{_relative(root, jar)}!{cls}", "jar", getter, key))
    for file, where, getter, key in reads:
        if key in known:
            continue
        result.add(
            id="settings-key-missing",
            category="config",
            severity="high",
            classification="REVIEW",
            confidence="HIGH",
            explanation=(f"Global.getSettings().{getter}(\"{key}\") reads a key that neither RC8's settings.json, this "
                         "mod's nor a declared dependency's defines: RC8 throws JSONException when the line runs "
                         "(Exigency 0.8's black market read blackMarketMinSupplies, which vanilla dropped in 0.9a, "
                         "2026-10-04). Define the key in the mod's settings.json, or read it with "
                         "getSettingsJSON().optDouble(key, default) using the old vanilla value."),
            file=file,
            evidence=[f"key:{key}", f"call:{getter}", where],
        )
