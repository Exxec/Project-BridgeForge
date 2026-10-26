from __future__ import annotations
import io
import json
import re
from pathlib import Path
from bridgeforge.scan.scanner import _load_lenient_json_file, _parse_json
from .common import FileChange, FixerError, _decode, _encode, _relative_path


def _matching_brace(text: str, open_at: int) -> int:
    """Index of the '}' closing the '{' at open_at, skipping strings; -1 when unbalanced."""
    depth, i, quote = 0, open_at, ""
    while i < len(text):
        c = text[i]
        if quote:
            if c == "\\":
                i += 1
            elif c == quote:
                quote = ""
        elif c in "\"'":
            quote = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _fix_dependency_version_major_mismatch(root: Path, options: dict) -> list[FileChange]:
    """Set each mismatched dependency's declared version to the provider's (RC8-23: a major mismatch disables the mod
    silently; zzz Bingus Sustem, GRP2C-20261005). Needs `options["provider_roots"]`. Only a string version is edited;
    a {"major":..} object is left for the owner."""
    from bridgeforge.scan.scanner import dependency_version_major_conflicts

    conflicts = dependency_version_major_conflicts(root, options.get("provider_roots"))
    if not conflicts:
        raise FixerError("No dependency-version-major-mismatch found (pass provider roots with --providers).")
    path = root / "mod_info.json"
    raw = path.read_bytes()
    text, had_bom = _decode(raw)
    refused = []
    version_value = re.compile(r'("version"\s*:\s*)(?:"[^"]*"|\{[^{}]*\})')
    for conflict in conflicts:
        id_match = re.search(r'"id"\s*:\s*"' + re.escape(conflict["id"]) + '"', text)
        open_at = text.rfind("{", 0, id_match.start()) if id_match else -1
        close_at = _matching_brace(text, open_at) if open_at >= 0 else -1
        entry = text[open_at:close_at + 1] if close_at > open_at else ""
        if not version_value.search(entry):
            refused.append(conflict["id"])
            continue
        text = (text[:open_at] + version_value.sub(lambda m: m.group(1) + json.dumps(conflict["provider"]), entry, count=1)
                + text[close_at + 1:])
    if text == _decode(raw)[0]:
        raise FixerError("Nothing edited: " + ", ".join(refused) + " (version is not a plain string in the dependency entry).")
    try:
        _parse_json(text)
    except json.JSONDecodeError as exc:
        raise FixerError(f"Edited {path} failed to re-parse: {exc}") from exc
    return [FileChange(path=path, before=raw, after=_encode(text, had_bom))]


def _fix_conversion_faction_names_removed_hull(root: Path, options: dict) -> list[FileChange]:
    """Replace each vanilla faction file that names variants of removed hulls with a copy lacking those lines, and list
    the copies in mod_info.json `replace` (Ironclads, GRP10B-GRP10F 2026-10-05; see bridgeforge.conversion_checks).
    Copies come from --vanilla-core (read only; the result stays in the mod's workspace, which is never committed). A
    mod overlay that holds more than a showInIntelTab stub is left for the owner."""
    from .. import conversion_checks as cc

    vanilla_core = options.get("vanilla_core")
    if not vanilla_core:
        raise FixerError("--vanilla-core is required for conversion-faction-names-removed-hull.")
    vanilla_core = Path(vanilla_core).expanduser().resolve()
    hits = cc.factions_naming_removed_hulls(root, vanilla_core)
    if not hits:
        raise FixerError("No faction file names a variant of a removed hull.")
    replaced = cc.replace_list(root)
    changes, listed, refused = [], [], []
    for name, variants in sorted(hits.items()):
        usable, hidden = cc.stub_value(root, name)
        if not usable:
            refused.append(f"{name} (the mod's own file holds more than a showInIntelTab stub)")
            continue
        relative = (cc.FACTION_DIR / name).as_posix()
        mine = root / cc.FACTION_DIR / name
        source = mine if relative.lower() in replaced and mine.is_file() else vanilla_core / "data" / "world" / "factions" / name
        import textwrap

        header = textwrap.wrap(f"BridgeForge: RC8's own {name}, REPLACED (mod_info replace) without the lines naming "
                               + ", ".join(variants) + ": their hulls are not in this mod's ship_data.csv, and RC8 prices every "
                               "variant a faction names at startup (conversion-faction-names-removed-hull).", 110)
        try:
            after = cc.faction_copy_without(source.read_bytes(), variants, header, hidden)
        except ValueError as exc:
            refused.append(f"{name} ({exc})")
            continue
        before = mine.read_bytes() if mine.is_file() else b""
        changes.append(FileChange(path=mine, before=before, after=after, existed_before=mine.is_file()))
        if relative.lower() not in replaced:
            listed.append(relative)
    if not changes:
        raise FixerError("Nothing written: " + "; ".join(refused))
    if listed:
        info = root / "mod_info.json"
        raw = info.read_bytes()
        text, had_bom = _decode(raw)
        try:
            new_text = cc.add_replace_entries(text, listed)
            _parse_json(new_text)
        except (ValueError, json.JSONDecodeError) as exc:
            raise FixerError(f"Could not add the files to mod_info.json replace: {exc}") from exc
        changes.append(FileChange(path=info, before=raw, after=_encode(new_text, had_bom)))
    return changes


def _fix_conversion_faction_names_missing_content(root: Path, options: dict) -> list[FileChange]:
    """Replace each vanilla faction file that lists hulls, fighters or weapons the mod's replaced tables removed with a copy
    lacking those ids, and list the copies in mod_info.json `replace` (Ironclads, GRP10U/GRP10V 2026-10-05; see
    bridgeforge.conversion_checks). Copies come from --vanilla-core (read only). A mod overlay that holds more than a
    showInIntelTab stub is left for the owner."""
    import textwrap

    from .. import conversion_checks as cc

    vanilla_core = options.get("vanilla_core")
    if not vanilla_core:
        raise FixerError("--vanilla-core is required for conversion-faction-names-missing-content.")
    vanilla_core = Path(vanilla_core).expanduser().resolve()
    hits = cc.factions_naming_missing_content(root, vanilla_core)
    if not hits:
        raise FixerError("No faction file lists a hull, fighter or weapon the mod's replaced tables removed.")
    tables = cc.replaced_table_ids(root)
    replaced = cc.replace_list(root)
    changes, listed, refused = [], [], []
    for name, kinds in sorted(hits.items()):
        usable, hidden = cc.stub_value(root, name)
        if not usable:
            refused.append(f"{name} (the mod's own file holds more than a showInIntelTab stub)")
            continue
        relative = (cc.FACTION_DIR / name).as_posix()
        mine = root / cc.FACTION_DIR / name
        source = mine if relative.lower() in replaced and mine.is_file() else vanilla_core / "data" / "world" / "factions" / name
        header = textwrap.wrap(f"BridgeForge: RC8's own {name}, REPLACED (mod_info replace) without the "
                               + ", ".join(f"{sum(len(ids) for k, ids in kinds.items() if k == kind)} {kind}" for kind in sorted(kinds))
                               + " this mod's replaced tables removed: RC8 checks every id a faction knows when a game loads "
                               "(conversion-faction-names-missing-content).", 110)
        after, _dropped = cc.faction_copy_without_content(source.read_bytes(), tables, header, hidden)
        before = mine.read_bytes() if mine.is_file() else b""
        changes.append(FileChange(path=mine, before=before, after=after, existed_before=mine.is_file()))
        if relative.lower() not in replaced:
            listed.append(relative)
    if not changes:
        raise FixerError("Nothing written: " + "; ".join(refused))
    if listed:
        info = root / "mod_info.json"
        raw = info.read_bytes()
        text, had_bom = _decode(raw)
        try:
            new_text = cc.add_replace_entries(text, listed)
            _parse_json(new_text)
        except (ValueError, json.JSONDecodeError) as exc:
            raise FixerError(f"Could not add the files to mod_info.json replace: {exc}") from exc
        changes.append(FileChange(path=info, before=raw, after=_encode(new_text, had_bom)))
    return changes


def _fix_conversion_vanilla_lifecycle_plugin(root: Path, options: dict) -> list[FileChange]:
    """Write a coreLifecyclePlugin subclass that skips RC8's vanilla world generation and register it in settings.json
    (Ironclads, GRP10P/GRP10T-20261005; see bridgeforge.conversion_checks). Nothing is read from the game install."""
    from .. import conversion_checks as cc

    if not cc.lifecycle_plugin_missing(root):
        raise FixerError("This mod does not replace ship_data.csv, or already sets plugins.coreLifecyclePlugin.")
    class_name = cc.lifecycle_plugin_class_name(root)
    source = root / "data" / "scripts" / "plugins" / f"{class_name}.java"
    if source.exists():
        raise FixerError(f"{_relative_path(root, source)} already exists; register it in settings.json by hand.")
    class_path = f"data.scripts.plugins.{class_name}"
    settings = root / "data" / "config" / "settings.json"
    changes = [FileChange(path=source, before=b"", after=(cc.LIFECYCLE_PLUGIN_TEMPLATE % {"class_name": class_name}).encode("utf-8"),
                          existed_before=False)]
    if settings.is_file():
        raw = settings.read_bytes()
        text, had_bom = _decode(raw)
        new_text = cc.add_core_lifecycle_plugin_setting(text, class_path)
        after = _encode(new_text, had_bom)
    else:
        raw, new_text = b"", '{\n\t"plugins":{\n\t\t"coreLifecyclePlugin":"%s",\n\t},\n}\n' % class_path
        after = new_text.encode("utf-8")
    try:
        _parse_json(new_text)
    except (ValueError, json.JSONDecodeError) as exc:
        raise FixerError(f"Could not add the plugin to settings.json: {exc}") from exc
    changes.append(FileChange(path=settings, before=raw, after=after, existed_before=settings.is_file()))
    return changes


def _fix_factions_csv_relists_neutral(root: Path, options: dict) -> list[FileChange]:
    """Remove the neutral.faction row from the mod's factions.csv (Ironclads, GRP10D-20261005)."""
    from .. import conversion_checks as cc

    path = cc.listing_path(root)
    if not path.is_file():
        raise FixerError("No factions.csv in this mod.")
    raw = path.read_bytes()
    after = cc.remove_neutral_row(raw)
    if after == raw:
        raise FixerError("factions.csv does not list neutral.faction.")
    return [FileChange(path=path, before=raw, after=after)]


_SHADOW_ID_KEYS = {".system": "id", ".wpn": "id", ".proj": "id", ".variant": "variantId", ".ship": "hullId", ".skin": "skinHullId"}


def _fix_vanilla_path_shadowing(root: Path, options: dict) -> list[FileChange]:
    """Rename a data file saved at a vanilla path under another id to its own id: Vayra's Ship Pack saved its Shieldwall
    Drones system (id vayra_exemplardrones) as data/shipsystems/drone_pd.system, which replaced vanilla's drone_pd, so two
    vanilla hulls lost their system (GRP2C-20261005). Only a file whose content id differs from the vanilla file at the same
    path is moved; a file that carries vanilla's own id is a deliberate override and stays. Needs --vanilla-core.
    With a reference core (item 73 D3, shadow_triage) it also writes reports/SHADOW_TRIAGE.md and moves an old-vanilla copy
    to scratch/removed-shadow/ only when the owner approved that mod and path; unapproved copies stay."""
    vanilla_core = options.get("vanilla_core")
    if not vanilla_core:
        raise FixerError("--vanilla-core is required for vanilla-path-shadowing.")
    vanilla = Path(vanilla_core).expanduser().resolve()
    changes, refused = [], []
    data_dir = root / "data"
    for path in sorted(data_dir.rglob("*")) if data_dir.is_dir() else []:
        key = _SHADOW_ID_KEYS.get(path.suffix.lower())
        if key is None or not path.is_file() or "disabled_files" in path.relative_to(root).parts:
            continue
        counterpart = vanilla / path.relative_to(root)
        if not counterpart.is_file():
            continue
        mine, theirs = _load_lenient_json_file(path), _load_lenient_json_file(counterpart)
        own, vanilla_id = (mine or {}).get(key) if isinstance(mine, dict) else None, (theirs or {}).get(key) if isinstance(theirs, dict) else None
        if not isinstance(own, str) or not own or own == vanilla_id or own == path.stem:
            continue
        target = path.with_name(own + path.suffix)
        if target.exists():
            refused.append(f"{_relative_path(root, path)} (a file named {target.name} already exists)")
            continue
        raw = path.read_bytes()
        changes.append(FileChange(path=target, before=b"", after=raw, existed_before=False))
        changes.append(FileChange(path=path, before=raw, after=b"", removed=True))
    from ..shadow_triage import plan_changes

    changes += plan_changes(root, vanilla, options)
    if not changes:
        raise FixerError("No file saved at a vanilla path under another id" + (f" (refused: {'; '.join(refused)})" if refused else "."))
    return changes


# Owner rule 2026-10-05 ("Vanilla ratio per hull"): the median of RC8 supplies/rec over 0.6.2 supplies/day on the hulls both
# versions share, by hull size (14 frigates, 13 destroyers, 8 cruisers, 7 capitals). The old x30 gave SEEKER 150-600 DP hulls
# that could never deploy (RC8 vanilla tops out at 100; maxBattleSize is 400).
SUPPLY_RATIOS = {"FRIGATE": 3.0, "DESTROYER": 2.0, "CRUISER": 2.65, "CAPITAL_SHIP": 2.67}


def _fix_ship_data_supplies_legacy_column(root: Path, options: dict) -> list[FileChange]:
    """Add `supplies/rec` and `supplies/mo` to a 0.6-era ship_data.csv that has only `supplies/day`: day x the ratio for the
    hull's size (from its .ship file), rounded and at least 1; rec = mo. Rows without a positive day, fighters and hulls with no
    readable size are left blank. `supplies/day` stays, as in the revived SEEKER."""
    import csv as csv_module

    path = root / "data" / "hulls" / "ship_data.csv"
    if not path.is_file():
        raise FixerError("No data/hulls/ship_data.csv in this mod.")
    raw = path.read_bytes()
    text, had_bom = _decode(raw)
    rows = list(csv_module.reader(io.StringIO(text, newline="")))
    if not rows or "supplies/day" not in rows[0]:
        raise FixerError("ship_data.csv has no supplies/day column.")
    header = rows[0]
    if "supplies/rec" in header or "supplies/mo" in header:
        raise FixerError("ship_data.csv already has supplies/rec or supplies/mo; nothing to convert.")
    id_at, day_at = header.index("id"), header.index("supplies/day")
    width = len(header)
    sizes = {}
    for ship in (root / "data" / "hulls").glob("*.ship"):
        data = _load_lenient_json_file(ship)
        if isinstance(data, dict) and isinstance(data.get("hullId"), str):
            sizes[data["hullId"]] = data.get("hullSize")
    newline = "\r\n" if "\r\n" in text else "\n"
    out_rows, converted, skipped = [header + ["supplies/rec", "supplies/mo"]], 0, []
    for row in rows[1:]:
        if not row or not any(cell.strip() for cell in row):
            out_rows.append(row)
            continue
        row = row + [""] * (width - len(row))
        value = ""
        try:
            day = float(row[day_at]) if row[day_at].strip() else 0.0
        except ValueError:
            day = 0.0
        if day > 0:
            ratio = SUPPLY_RATIOS.get(sizes.get(row[id_at].strip()) or "")
            if ratio is None:
                skipped.append(row[id_at])
            else:
                value = str(max(1, round(day * ratio)))
                converted += 1
        out_rows.append(row[:width] + [value, value])
    if not converted:
        raise FixerError("No hull row could be converted" + (f" (no readable hull size for: {', '.join(skipped[:8])})" if skipped else "."))
    buffer = io.StringIO()
    csv_module.writer(buffer, lineterminator=newline).writerows(out_rows)
    return [FileChange(path=path, before=raw, after=_encode(buffer.getvalue(), had_bom))]
