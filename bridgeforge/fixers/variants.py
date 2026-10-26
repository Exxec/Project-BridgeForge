from __future__ import annotations
import json
import re
from pathlib import Path
from ..build_tag import _STRING_LITERAL, _structural_depths
from bridgeforge.scan.scanner import _load_lenient_json_file
from .common import FileChange, FixerError, _decode, _encode, _findings_of


def _fleet_type_display_name(fleet_type: str) -> str:
    """"Zeta AI raid" -> "Zeta AI Raid"; camelCase ids split into words: "pathFleet" -> "Path Fleet"."""
    words = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", fleet_type).split(" ")
    return " ".join(w[:1].upper() + w[1:] for w in words if w)


def _fix_fleet_type_name_missing(root: Path, options: dict) -> list[FileChange]:
    """Add a `fleetTypeNames` entry per unnamed fleet type (P15 item 20.15), title-casing the type as Zorg18's
    hand fix did ("Zeta AI raid" -> "Zeta AI Raid"). Text insertion, so comments and formatting survive;
    `options["names"]` ({type: name}) overrides the proposed name. The check needs the vanilla core, so a
    fresh scan here passes `options["vanilla_core"]`."""
    if options.get("scan_findings") is None:
        from bridgeforge.scan.scanner import scan_mod

        vanilla = options.get("vanilla_core")
        findings = [f for f in scan_mod(root, vanilla_core=Path(vanilla) if vanilla else None).findings if f.id == "fleet-type-name-missing"]
    else:
        findings = _findings_of(root, options, "fleet-type-name-missing")
    by_file: dict[str, list[str]] = {}
    for finding in findings:
        fleet_type = next((e.split(":", 1)[1] for e in finding.evidence if e.startswith("type:")), None)
        if fleet_type and finding.file:
            by_file.setdefault(finding.file, []).append(fleet_type)
    names = options.get("names") or {}
    # A vanilla faction's type (The Mayorate's "pathFleet" for luddic_path): the mod has no faction file to edit,
    # so the name goes in its own data/world/factions/default_fleet_type_names.json, which RC8 merges with
    # vanilla's. Evidence: Broken Star and Nexerelin ship that file with only their own entries (2026-09-27), and
    # vanilla fleets keep their names with them enabled.
    defaults_relative = "data/world/factions/default_fleet_type_names.json"
    for relative in [r for r in by_file if not (root / r).is_file() and r != defaults_relative]:
        by_file.setdefault(defaults_relative, []).extend(by_file.pop(relative))
    changes = []
    for relative, types in sorted(by_file.items()):
        path = root / relative
        if relative == defaults_relative:
            raw = path.read_bytes() if path.is_file() else b""
            text, had_bom = _decode(raw) if raw else ("{\n}\n", False)
            newline = "\r\n" if "\r\n" in text else "\n"
            entries = "".join(newline + "\t" + json.dumps(t) + ":" + json.dumps(names.get(t) or _fleet_type_display_name(t)) + ","
                              for t in sorted(set(types)))
            brace = text.index("{")
            text = text[:brace + 1] + entries + text[brace + 1:]
            changes.append(FileChange(path=path, before=raw, after=_encode(text, had_bom), existed_before=path.is_file()))
            continue
        if not path.is_file():
            continue
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        newline = "\r\n" if "\r\n" in text else "\n"
        entries = "".join(
            newline + "\t\t" + json.dumps(t) + ":" + json.dumps(names.get(t) or _fleet_type_display_name(t)) + ","
            for t in sorted(set(types)))
        match = re.search(r'"fleetTypeNames"\s*:\s*\{', text)
        if match:
            text = text[:match.end()] + entries + text[match.end():]
        else:
            brace = text.index("{")
            text = text[:brace + 1] + newline + '\t"fleetTypeNames":{' + entries + newline + "\t}," + text[brace + 1:]
        changes.append(FileChange(path=path, before=raw, after=_encode(text, had_bom)))
    return changes


# ---------------------------------------------------------------------------
# Bracket-span helpers for the variant-fit fixers below. `.variant` files are lenient JSON (# / //
# comments, trailing commas), so edits stay surgical text-span rewrites, never a json.dumps
# round-trip that would reformat the file (as `_fix_variant_op_over_budget` above already does for
# flux numbers and hullMods entries). These three locate/remove spans inside "wings" and
# "weaponGroups" the same way, using `_structural_depths` (build_tag.py) so a `{`/`[`/`}`/`]`
# inside a string or a comment never miscounts.
# ---------------------------------------------------------------------------

_STRING_PAIR_RE = re.compile(r"(?:" + _STRING_LITERAL + r")\s*:\s*(?:" + _STRING_LITERAL + r")")


def _matching_bracket(text: str, depths: list[int], open_pos: int) -> int | None:
    """Position of the `]`/`}` that closes the `[`/`{` at `open_pos`."""
    target = depths[open_pos] + 1
    close_char = "]" if text[open_pos] == "[" else "}"
    for i in range(open_pos + 1, len(text)):
        if text[i] == close_char and depths[i] == target:
            return i
    return None


def _enclosing_bracket(text: str, depths: list[int], pos: int, open_char: str) -> int | None:
    """Position of the `open_char` one depth level up that directly encloses `pos` (also works when
    `pos` is itself another bracket's open position, since an open bracket char is recorded at the
    depth of its own context, same as any other content character there)."""
    target = depths[pos] - 1
    for i in range(pos - 1, -1, -1):
        if text[i] == open_char and depths[i] == target:
            return i
    return None


def _remove_span_with_comma(text: str, start: int, end: int) -> str:
    """Remove text[start:end] plus the one adjacent list/object comma: the one after it (with any
    whitespace) if there is more after, else the one before it (it was last). Mirrors
    `_fix_variant_op_over_budget`'s hullMods removal so a trimmed array/object still closes exactly
    like lenient JSON expects, without reformatting anything else."""
    after = text[end:]
    after_match = re.match(r"\s*,\s*", after)
    if after_match:
        return text[:start] + text[end + after_match.end():]
    before = text[:start]
    before_match = re.search(r",\s*\Z", before)
    if before_match:
        return text[:before_match.start()] + text[end:]
    return text[:start] + text[end:]


def _fix_variant_wings_exceed_bays(root: Path, options: dict) -> list[FileChange]:
    """Drop wings from the END of the variant's own "wings" list until the total (plus the hull's
    built-in wings, which live on the .ship and can never be removed here) fits its fighter bays
    (owner ruling 2026-09-29: drop only what RC8's changed hulls can no longer fit; keep everything
    else exactly as the mod author wrote it). The kept wings stay in the author's order; nothing else
    in the file changes. A variant whose built-in wings alone already exceed the bays has nothing in
    its own wings list left to trim, and is refused."""
    string_re = re.compile(_STRING_LITERAL)
    changes: list[FileChange] = []
    refused: list[str] = []
    for finding in _findings_of(root, options, "variant-wings-exceed-bays"):
        if not finding.file:
            continue
        values = {e.split(":", 1)[0]: e.split(":", 1)[1] for e in finding.evidence if ":" in e}
        try:
            wings_count = int(values.get("wings", ""))
            built_in = int(values.get("built-in-wings", ""))
            bays = int(values.get("fighter-bays", ""))
        except ValueError:
            refused.append(f"{finding.file}: wings/built-in-wings/fighter-bays evidence is not numeric")
            continue
        excess = wings_count + built_in - bays
        if excess <= 0:
            continue
        path = root / finding.file
        if not path.is_file():
            refused.append(f"{finding.file}: file not found")
            continue
        if excess > wings_count:
            refused.append(
                f"{finding.file}: built-in wings alone ({built_in}) already exceed {bays} bay(s); "
                "nothing in the variant's own wings list can fix this"
            )
            continue
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        match = re.search(r'"wings"\s*:\s*\[', text)
        if match is None:
            refused.append(f"{finding.file}: no \"wings\" array found")
            continue
        open_pos = match.end() - 1
        depths = _structural_depths(text)
        close_pos = _matching_bracket(text, depths, open_pos)
        if close_pos is None:
            refused.append(f"{finding.file}: \"wings\" array has no matching ']'")
            continue
        literals = list(string_re.finditer(text, open_pos + 1, close_pos))
        if len(literals) != wings_count:
            refused.append(
                f"{finding.file}: {len(literals)} wing entries found in the file but the scan saw {wings_count}; ambiguous, skipped"
            )
            continue
        for literal in reversed(literals[wings_count - excess:]):
            text = _remove_span_with_comma(text, literal.start(), literal.end())
        changes.append(FileChange(path=path, before=raw, after=_encode(text, had_bom)))
    if refused:
        if not changes:
            raise FixerError("No variant-wings-exceed-bays finding could be trimmed: " + "; ".join(refused))
        options.setdefault("partial_refusals", []).append("Not trimmed (variant-wings-exceed-bays): " + "; ".join(refused))
    return changes


def _fix_variant_weapon_slot_removed(root: Path, options: dict, finding_id: str) -> list[FileChange]:
    """Shared by variant-weapon-slot-mismatch and variant-weapon-slot-missing (owner ruling
    2026-09-29): remove the one slot->weapon entry the finding names from its weapon group's
    "weapons"; if that empties the group's own weapons, remove the whole group object from
    "weaponGroups" too (rather than leave an empty group behind). Nothing else in the file changes.
    Several findings against the same file are applied in turn, each against the file as the
    previous one left it, so two bad weapons in the same group correctly empty (and remove) it.
    """
    by_file: dict[str, list] = {}
    for finding in _findings_of(root, options, finding_id):
        if finding.file:
            by_file.setdefault(finding.file, []).append(finding)
    changes: list[FileChange] = []
    refused: list[str] = []
    for relative in sorted(by_file):
        findings = by_file[relative]
        path = root / relative
        if not path.is_file():
            refused.append(f"{relative}: file not found")
            continue
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        for finding in findings:
            values = {e.split(":", 1)[0]: e.split(":", 1)[1] for e in finding.evidence if ":" in e}
            slot_id, weapon_id = values.get("slot"), values.get("weapon")
            if not slot_id or not weapon_id:
                refused.append(f"{relative}: {finding.id} evidence has no slot/weapon id")
                continue
            match = re.search(r'"' + re.escape(slot_id) + r'"\s*:\s*"' + re.escape(weapon_id) + r'"', text)
            if match is None:
                refused.append(f"{relative}: slot '{slot_id}' -> weapon '{weapon_id}' not found (already changed?)")
                continue
            depths = _structural_depths(text)
            weapons_open = _enclosing_bracket(text, depths, match.start(), "{")
            weapons_close = _matching_bracket(text, depths, weapons_open) if weapons_open is not None else None
            if weapons_open is None or weapons_close is None:
                refused.append(f"{relative}: could not locate the weapons object enclosing slot '{slot_id}'")
                continue
            remaining = len(_STRING_PAIR_RE.findall(text[weapons_open + 1:weapons_close]))
            if remaining <= 1:
                group_open = _enclosing_bracket(text, depths, weapons_open, "{")
                group_close = _matching_bracket(text, depths, group_open) if group_open is not None else None
                if group_open is None or group_close is None:
                    refused.append(f"{relative}: could not locate the weapon group enclosing slot '{slot_id}'")
                    continue
                text = _remove_span_with_comma(text, group_open, group_close + 1)
            else:
                text = _remove_span_with_comma(text, match.start(), match.end())
        changes.append(FileChange(path=path, before=raw, after=_encode(text, had_bom)))
    if refused:
        if not changes:
            raise FixerError(f"No {finding_id} finding could be fixed: " + "; ".join(refused))
        options.setdefault("partial_refusals", []).append(f"Not fixed ({finding_id}): " + "; ".join(refused))
    return changes


def _fix_variant_op_over_budget(root: Path, options: dict) -> list[FileChange]:
    """Trim an over-budget variant to its hull's ordnance points (owner ruling 2026-09-27: "trim to fit if
    possible, best estimate"). Order: flux capacitors, then flux vents (1 OP each, the least character-changing),
    then non-built-in hull mods, costliest first. If even that cannot fit the budget the variant is refused and left
    as it is, because the only step left would be removing weapons. Aims at the raw budget, no tolerance. Edits are
    surgical: only the two flux numbers and the removed hullMods entries change. Needs `options["vanilla_core"]`."""
    from bridgeforge.scan.scanner import (HULL_MOD_COST_COLUMN_BY_SIZE, _csv_id_index, _float_or, _resolve_variant_hull_and_slots,
                          _ship_file_index, _skin_index, _skin_weapon_slot_changes, scan_mod)

    vanilla = options.get("vanilla_core")
    if not vanilla:
        raise FixerError("variant-op-over-budget needs --vanilla-core (vanilla weapon, hull mod and hull costs).")
    vanilla = Path(vanilla)
    if options.get("scan_findings") is None:
        findings = [f for f in scan_mod(root, vanilla_core=vanilla).findings if f.id == "variant-op-over-budget"]
    else:
        findings = _findings_of(root, options, "variant-op-over-budget")
    reference = options.get("reference_core")
    if reference:
        # Owner ruling 2026-09-27 (option 2): trim only variants that fit under the reference game's costs, i.e.
        # the ones RC8's cost changes pushed over; a variant over budget there too was authored that way (as RC8's
        # own 12 over-budget variants are) and is left alone.
        from ..models import ScanResult, TargetProfile
        from bridgeforge.scan.scanner import _scan_variant_validity

        ref_result = ScanResult(input_path=root, target=TargetProfile())
        _scan_variant_validity(root, ref_result, Path(reference))
        authored = {f.file for f in ref_result.findings if f.id == "variant-op-over-budget"}
        findings = [f for f in findings if f.file not in authored]
    ship_files, skins, skin_slots = _ship_file_index(root, vanilla), _skin_index(root, vanilla), _skin_weapon_slot_changes(root, vanilla)
    hull_mod_costs = _csv_id_index(root / "data" / "hullmods" / "hull_mods.csv", vanilla / "data" / "hullmods" / "hull_mods.csv")
    changes, refused = [], []
    for finding in findings:
        values = {e.split(":", 1)[0]: e.split(":", 1)[1] for e in finding.evidence if ":" in e}
        excess = _float_or(values.get("total-op")) - _float_or(values.get("budget"))
        path = root / finding.file
        if excess <= 0 or not path.is_file():
            continue
        raw = path.read_bytes()
        text, had_bom = _decode(raw)

        data = _load_lenient_json_file(path) or {}
        _hull, ship_json, _slots = _resolve_variant_hull_and_slots(str(data.get("hullId") or ""), ship_files, skins, skin_slots)
        cost_column = HULL_MOD_COST_COLUMN_BY_SIZE.get(str((ship_json or {}).get("hullSize") or "").upper(), "cost_cruiser")
        built_in = set((ship_json or {}).get("builtInMods") or []) | {m for key in ("sMods", "permaMods") for m in (data.get(key) or []) if isinstance(m, str)}
        caps, vents = int(_float_or(data.get("fluxCapacitors"))), int(_float_or(data.get("fluxVents")))
        cut_caps = min(caps, int(-(-excess // 1)))
        excess -= cut_caps
        cut_vents = min(vents, max(0, int(-(-excess // 1))))
        excess -= cut_vents
        removed_mods = []
        mods = [m for m in data.get("hullMods") or [] if isinstance(m, str) and m not in built_in and m in hull_mod_costs]
        for mod_id in sorted(mods, key=lambda m: -_float_or(hull_mod_costs[m].get(cost_column))):
            if excess <= 0:
                break
            cost = _float_or(hull_mod_costs[mod_id].get(cost_column))
            if cost > 0:
                removed_mods.append(mod_id)
                excess -= cost
        if excess > 0:
            refused.append(f"{finding.file} ({excess:.0f} OP over even without flux and hull mods; weapons would have to go)")
            continue
        for key, new in (("fluxCapacitors", caps - cut_caps), ("fluxVents", vents - cut_vents)):
            text = re.sub(r'("' + key + r'"\s*:\s*)-?\d+(\.\d+)?', lambda m, n=new: m.group(1) + str(n), text, count=1)
        for mod_id in removed_mods:
            text = re.sub(r'\s*"' + re.escape(mod_id) + r'"\s*,', "", text, count=1) if re.search(r'"' + re.escape(mod_id) + r'"\s*,', text) \
                else re.sub(r',?\s*"' + re.escape(mod_id) + r'"', "", text, count=1)
        changes.append(FileChange(path=path, before=raw, after=_encode(text, had_bom)))
    if refused:
        if not changes:
            raise FixerError("No over-budget variant can be trimmed to fit without removing weapons: " + "; ".join(refused))
        options.setdefault("partial_refusals", []).append("Not trimmed (weapons would have to go): " + "; ".join(refused))
    return changes
