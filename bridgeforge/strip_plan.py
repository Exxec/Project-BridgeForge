"""Strip and vendor plans for a STRIP_FROM_MOD recommendation (ROADMAP P14 item 4).

`dependency-substitutes` can recommend STRIP_FROM_MOD, but only as a strategy name and a summary
reason - nothing generates the actual edit list (which `.variant`/`.ship`/`.skin`/`.faction` line
loses which id), or proposes a real vanilla substitute. This module does both:

- `strip_plan`: for every "hard" id (`substitutes.hard_to_cover_ids` - genuinely uncovered, or
  covered only by a provider too large to revive), the exact file+field reference list, plus - for
  weapons only - real vanilla substitute candidates "of the same slot type and size" (reusing the
  scanner's own slot-fit logic, `_weapon_slot_type_compatible`/`_override_fits`/
  `WEAPON_SLOT_SIZE_RANK` - never a second implementation, never an invented match). Hullmods/wings
  have no comparable "slot type and size" concept to substitute on, so those entries propose
  removal only, honestly.
- `write_expected_changes`: turns a strip plan into real `expect` PROPOSED entries
  (`behavior_discovery.add_expected_change`), so approval goes through the existing D4/D5 mechanism
  rather than a new one.
- `vendor_copy`: "where the licence allows, offer vendoring as an alternative: copy the one missing
  piece... instead of reviving a heavy provider" (the item's own example: Rebal's
  `shields_formshield` into Explorer Society). Scoped to hullmods only - a CSV row plus its
  declared script class is a single, well-defined unit to copy; a weapon/wing/hull involves sprite
  and balance data this command has no reliable way to locate or validate, so those kinds are
  refused outright rather than copied incompletely. A licence gate (`release._licence_gate`, the
  same one `release`/item 7 use) blocks vendoring from a local-only source. `--apply` is required
  to actually write; the default is a dry-run plan, matching `fold`'s own convention.

Read-only except `write_expected_changes` (only ever adds PROPOSED entries to an expected-changes
file) and `vendor_copy --apply` (only ever adds new files to the target mod, never touches the
source). Applying a strip (removing an id from a file) is a separate, deliberate step a person
takes after reviewing the plan, not this module's job.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from .models import TargetProfile
from .scanner import (
    WEAPON_SLOT_SIZE_RANK,
    _load_lenient_json_file,
    _override_fits,
    _read_csv_rows_lenient,
    _relative,
    _resolve_variant_hull_and_slots,
    _skin_index,
    _skin_weapon_slot_changes,
    _ship_file_index,
    _weapon_slot_type_compatible,
    _wpn_type_size_index,
    scan_mod,
)
from .java_toolchain import declared_dependencies
from .substitutes import (
    cover,
    hard_to_cover_ids,
    provider_index,
    rank,
    required_from_scan,
)

SCHEMA_VERSION = 1

_HULLMOD_FIELDS = ("hullMods", "permaMods", "sMods", "builtInMods", "removeBuiltInMods")
_WING_FIELDS = ("wings", "builtInWings")


def find_content_references(root: Path, kind: str, ident: str) -> list[dict]:
    """Every `.variant`/`.ship`/`.skin`/`.faction` file+field that references `ident` as `kind`.

    Reads every candidate file itself rather than trusting a scanner finding's evidence (which is
    id-only, capped, and never names the field) - this is the actual edit list item 4 asks for.
    """
    refs: list[dict] = []
    data = root / "data"
    if not data.is_dir():
        return refs
    for path in sorted(data.rglob("*")):
        suffix = path.suffix.lower()
        if suffix not in (".variant", ".ship", ".skin", ".faction"):
            continue
        spec = _load_lenient_json_file(path)
        if not isinstance(spec, dict):
            continue
        relative = _relative(root, path)
        if kind == "hullmod":
            for field in _HULLMOD_FIELDS:
                if ident in (spec.get(field) or []):
                    refs.append({"file": relative, "field": field})
            known = spec.get("knownHullMods")
            if suffix == ".faction" and isinstance(known, dict) and ident in (known.get("hullMods") or []):
                refs.append({"file": relative, "field": "knownHullMods.hullMods"})
        elif kind == "wing":
            for field in _WING_FIELDS:
                if ident in (spec.get(field) or []):
                    refs.append({"file": relative, "field": field})
            known = spec.get("knownFighters")
            if suffix == ".faction" and isinstance(known, dict) and ident in (known.get("fighters") or []):
                refs.append({"file": relative, "field": "knownFighters.fighters"})
        elif kind == "weapon":
            for group in spec.get("weaponGroups") or []:
                if isinstance(group, dict) and isinstance(group.get("weapons"), dict):
                    for slot_id, weapon_id in group["weapons"].items():
                        if weapon_id == ident:
                            refs.append({"file": relative, "field": f"weaponGroups.weapons.{slot_id}", "slot_id": slot_id, "hull_id": spec.get("hullId") if suffix == ".variant" else None})
            built_in = spec.get("builtInWeapons")
            if isinstance(built_in, dict):
                for slot_id, weapon_id in built_in.items():
                    if weapon_id == ident:
                        refs.append({"file": relative, "field": f"builtInWeapons.{slot_id}", "slot_id": slot_id, "hull_id": spec.get("hullId") if suffix == ".ship" else None})
            known = spec.get("knownWeapons")
            if suffix == ".faction" and isinstance(known, dict) and ident in (known.get("weapons") or []):
                refs.append({"file": relative, "field": "knownWeapons.weapons"})
        elif kind == "hull":
            if suffix == ".variant" and spec.get("hullId") == ident:
                refs.append({"file": relative, "field": "hullId"})
            if suffix == ".skin" and spec.get("baseHullId") == ident:
                refs.append({"file": relative, "field": "baseHullId"})
    return refs


def _weapon_fits_slot(slot_type: str, slot_size: str, weapon_spec: dict) -> bool:
    weapon_type = weapon_spec.get("type", "")
    weapon_size = weapon_spec.get("size", "")
    if WEAPON_SLOT_SIZE_RANK.get(weapon_size, 0) > WEAPON_SLOT_SIZE_RANK.get(slot_size, 0):
        return False
    return bool(weapon_type) and (
        _weapon_slot_type_compatible(slot_type, weapon_type)
        or _override_fits(slot_type, weapon_spec.get("mount_override", ""))
    )


def weapon_substitute_candidates(vanilla_core: Path, slot_type: str, slot_size: str, exclude_id: str | None = None) -> list[str]:
    """Real vanilla-only weapon ids that fit a slot of this type/size - never an invented match."""
    if not slot_type or not slot_size or vanilla_core is None:
        return []
    vanilla_weapons = _wpn_type_size_index(vanilla_core, None)  # root=vanilla_core, vanilla_core=None: vanilla-only
    return sorted(
        weapon_id for weapon_id, spec in vanilla_weapons.items()
        if weapon_id != exclude_id and _weapon_fits_slot(slot_type, slot_size, spec)
    )


def _slot_type_size_for_reference(root: Path, vanilla_core: Path | None, hull_id: str | None, slot_id: str | None) -> tuple[str, str]:
    if not hull_id or not slot_id or vanilla_core is None:
        return "", ""
    ship_files = _ship_file_index(root, vanilla_core)
    skins = _skin_index(root, vanilla_core)
    skin_slot_changes = _skin_weapon_slot_changes(root, vanilla_core)
    _resolved, _ship_json, slot_by_id = _resolve_variant_hull_and_slots(hull_id, ship_files, skins, skin_slot_changes)
    if not slot_by_id:
        return "", ""
    slot = slot_by_id.get(slot_id)
    if slot is None:
        return "", ""
    return str(slot.get("type") or "").strip().upper(), str(slot.get("size") or "").strip().upper()


def strip_plan(mod_dir: Path, provider_roots: list[Path] | None = None, vanilla_core: Path | None = None, ops: Path | None = None, policy_path: Path | None = None) -> dict:
    """The exact edit list for a STRIP_FROM_MOD recommendation: every hard id, every file/field
    that references it, and - for weapons - real vanilla substitute candidates.
    """
    mod_dir = Path(mod_dir).expanduser().resolve()
    from .java_toolchain import DEFAULT_PROVIDER_ROOTS

    roots = provider_roots or list(DEFAULT_PROVIDER_ROOTS)
    result = scan_mod(mod_dir, TargetProfile(), vanilla_core)
    needed, files_count = required_from_scan(result)
    declared = declared_dependencies(mod_dir)
    providers = provider_index(roots, exclude=mod_dir)
    ranked = rank(needed, providers)
    chosen_providers, uncovered = cover(needed, providers, preferred=set(declared))
    chosen = []
    for provider, hits in chosen_providers:
        item = {"mod_id": provider.mod_id, "name": provider.name, "game_version": provider.game_version, "targets_0.98a": provider.game_version.startswith("0.98"), "covers": sorted(hits)}
        chosen.append(item)
    # classify_chosen_providers needs each item's own workspace state for `revive` vs `heavy`;
    # reuse the same lookup dependency_substitutes does rather than a second implementation.
    from .substitutes import REPO_ROOT, _workspace_state
    ops_dir = Path(ops) if ops else REPO_ROOT / "In operation"
    for item in chosen:
        if not item["targets_0.98a"]:
            item["workspace"] = _workspace_state(ops_dir, item["mod_id"])
    hard = hard_to_cover_ids(chosen, uncovered)

    entries = []
    for key in sorted(hard):
        kind, ident = key.split(":", 1)
        refs = find_content_references(mod_dir, kind, ident)
        substitutes: list[dict] = []
        if kind == "weapon":
            seen_slots: set[tuple[str, str]] = set()
            for ref in refs:
                slot_type, slot_size = _slot_type_size_for_reference(mod_dir, vanilla_core, ref.get("hull_id"), ref.get("slot_id"))
                if not slot_type or (slot_type, slot_size) in seen_slots:
                    continue
                seen_slots.add((slot_type, slot_size))
                candidates = weapon_substitute_candidates(vanilla_core, slot_type, slot_size, exclude_id=ident)
                if candidates:
                    substitutes.append({"slot_type": slot_type, "slot_size": slot_size, "candidates": candidates})
        entries.append({
            "kind": kind, "id": ident,
            "references": refs,
            "substitute_candidates": substitutes,
            "action": "substitute" if substitutes else "strip",
        })

    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "strip-plan",
        "status": "OK",
        "mod": str(mod_dir),
        "hard_id_count": len(hard),
        "entries": entries,
        "candidates_considered": len(ranked),
    }


def write_expected_changes(plan: dict, expected_path: Path, mod_id: str, build: str, proposed_by: str = "strip-plan") -> list[dict]:
    """Record every strip-plan entry as a real `expect` PROPOSED entry (behavior_discovery's own
    mechanism - see its own `add_expected_change`), so approval goes through `expect` as usual.
    One entry per id, numbered EXP-<MOD>-9xx to keep this planner's entries visually distinct from
    hand-authored ones without colliding with them (never guessed at whether a lower number is free).
    """
    import re

    from .behavior_discovery import DiscoveryError, add_expected_change

    written = []
    base = 900
    # EXP-<MOD>-nnn requires MOD to be alphanumeric only (behavior_discovery's own id pattern);
    # a real mod_id often has underscores/mixed shapes ("xxx_ss_FX_mod_core"), so strip anything
    # else rather than let every real mod fail this with an opaque regex error.
    safe_mod_id = re.sub(r"[^A-Za-z0-9]", "", mod_id).upper() or "MOD"
    for offset, entry in enumerate(plan["entries"]):
        change_id = f"EXP-{safe_mod_id}-{base + offset}"
        file_list = ", ".join(sorted({ref["file"] for ref in entry["references"]})) or "no file found"
        if entry["action"] == "substitute":
            candidate_note = "; ".join(f"{sub['slot_type']}/{sub['slot_size']}: {', '.join(sub['candidates'][:5])}" for sub in entry["substitute_candidates"])
            summary = f"Strip {entry['kind']} '{entry['id']}' (no visible provider) from {file_list}, substituting a vanilla weapon of the same slot type/size: {candidate_note}"
        else:
            summary = f"Strip {entry['kind']} '{entry['id']}' (no visible provider) from {file_list}; no vanilla substitute of the same shape exists"
        try:
            result = add_expected_change(
                expected_path, mod_id=mod_id, change_id=change_id, build=build, layer="static",
                summary=summary, why="ROADMAP P14 item 4 strip plan: no visible provider covers this id.",
                match={"change": "removed", "kind": entry["kind"], "id": entry["id"]},
                proposed_by=proposed_by,
            )
        except DiscoveryError as exc:
            result = {"status": "ERROR", "id": change_id, "error": str(exc)}
        written.append(result)
    return written


_VENDOR_SUPPORTED_KINDS = {"hullmod"}
_SCRIPT_CLASS_REFERENCE_PATTERN = re.compile(r"\bimport\s+(data\.[\w.]+)\s*;|\bnew\s+([A-Z]\w*)\s*\(")


def _script_class_to_relative_path(root: Path, script_class: str) -> Path | None:
    """`data.hullmods.FormShield` -> `data/hullmods/FormShield.java`, if that loose file exists."""
    candidate = root / (script_class.replace(".", "/") + ".java")
    return candidate if candidate.is_file() else None


def _same_mod_script_dependencies(root: Path, script_path: Path) -> list[Path]:
    """Other loose `.java` files under `root` this script's own source text points at (one hop,
    same-package simple-name `new X(...)` calls or `import data....` statements) - best-effort, not
    a full dependency resolver, so `vendor_copy` always lists what it found and never claims this
    is exhaustive.
    """
    try:
        text = script_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    package_match = re.search(r"(?m)^\s*package\s+([\w.]+)\s*;", text)
    package = package_match.group(1) if package_match else None
    found: list[Path] = []
    for import_match, simple_name in _SCRIPT_CLASS_REFERENCE_PATTERN.findall(text):
        if import_match:
            candidate = root / (import_match.replace(".", "/") + ".java")
        elif package and simple_name:
            candidate = root / package.replace(".", "/") / f"{simple_name}.java"
        else:
            continue
        if candidate.is_file() and candidate != script_path and candidate not in found:
            found.append(candidate)
    return found


def vendor_copy(kind: str, ident: str, from_provider: Path, to_mod: Path, policy_path: Path | None = None, apply: bool = False) -> dict:
    """Copy one hullmod (its `hull_mods.csv` row, its declared script, and any same-mod loose
    script that script directly depends on) from `from_provider` into `to_mod` - vendoring a
    single piece instead of reviving or declaring a dependency on the whole provider mod.

    Refuses a local-only source (per `release_policy.json`, the same gate `release`/item 7 use) or
    a `kind` other than `hullmod` (see the module docstring for why weapon/wing/hull aren't
    supported here). Dry-run by default (`apply=False`): returns the plan without writing anything.
    A conflict (the target already declares this id, or already has a same-named script file with
    different content) refuses the whole copy rather than guessing which one is right.
    """
    from_provider = Path(from_provider).expanduser().resolve()
    to_mod = Path(to_mod).expanduser().resolve()
    if kind not in _VENDOR_SUPPORTED_KINDS:
        return {"schema_version": SCHEMA_VERSION, "mode": "vendor-copy", "status": "REFUSED", "reason": f"vendor_copy only supports 'hullmod' (not {kind!r}) - a weapon/wing/hull involves sprite/balance data this command has no reliable way to locate or validate."}

    provider_info = _load_lenient_json_file(from_provider / "mod_info.json")
    provider_id = provider_info.get("id") if isinstance(provider_info, dict) else None
    provider_name = provider_info.get("name") if isinstance(provider_info, dict) else None
    from .release import DEFAULT_POLICY_PATH, _licence_gate

    gate = _licence_gate(provider_id, provider_name, policy_path or DEFAULT_POLICY_PATH)
    if gate["local_only"]:
        return {"schema_version": SCHEMA_VERSION, "mode": "vendor-copy", "status": "REFUSED", "reason": f"{provider_name or provider_id} is local-only per release_policy.json: {gate.get('reason')}"}

    source_csv = from_provider / "data" / "hullmods" / "hull_mods.csv"
    rows = _read_csv_rows_lenient(source_csv) or []
    fieldnames = list(rows[0].keys()) if rows else []
    matching = [row for row in rows if (row.get("id") or "").strip() == ident]
    if not matching:
        return {"schema_version": SCHEMA_VERSION, "mode": "vendor-copy", "status": "NOT_FOUND", "reason": f"no id {ident!r} in {_relative(from_provider, source_csv)}"}
    row = matching[0]

    target_csv = to_mod / "data" / "hullmods" / "hull_mods.csv"
    target_rows = _read_csv_rows_lenient(target_csv) or []
    if any((existing.get("id") or "").strip() == ident for existing in target_rows):
        return {"schema_version": SCHEMA_VERSION, "mode": "vendor-copy", "status": "CONFLICT", "reason": f"{to_mod} already declares hullmod id {ident!r} in its own hull_mods.csv"}

    script_class = (row.get("script") or "").strip()
    files_to_copy: list[Path] = []
    if script_class:
        script_path = _script_class_to_relative_path(from_provider, script_class)
        if script_path is not None:
            files_to_copy.append(script_path)
            files_to_copy.extend(_same_mod_script_dependencies(from_provider, script_path))

    copy_plan = []
    for source_path in files_to_copy:
        relative = _relative(from_provider, source_path)
        target_path = to_mod / relative
        conflict = target_path.is_file() and target_path.read_bytes() != source_path.read_bytes()
        copy_plan.append({"relative": relative, "source": str(source_path), "target": str(target_path), "conflict": conflict})
    conflicts = [entry["relative"] for entry in copy_plan if entry["conflict"]]
    if conflicts:
        return {"schema_version": SCHEMA_VERSION, "mode": "vendor-copy", "status": "CONFLICT", "reason": f"{to_mod} already has different content at: {', '.join(conflicts)}"}

    missing_script = bool(script_class) and not files_to_copy
    result = {
        "schema_version": SCHEMA_VERSION, "mode": "vendor-copy", "status": "PLANNED" if not apply else "APPLIED",
        "kind": kind, "id": ident, "from_provider": str(from_provider), "to_mod": str(to_mod),
        "csv_row": row, "files": [entry["relative"] for entry in copy_plan],
        "script_not_vendored": script_class if missing_script else None,
        "note": (f"'{script_class}' is not a loose file under {from_provider} (jar-only or missing) - the CSV row can still be copied, but the script itself needs a separate manual port." if missing_script else None),
    }
    if not apply:
        return result

    for entry in copy_plan:
        target_path = Path(entry["target"])
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(Path(entry["source"]).read_bytes())
    target_csv.parent.mkdir(parents=True, exist_ok=True)
    write_fieldnames = fieldnames or (list(target_rows[0].keys()) if target_rows else list(row.keys()))
    dropped_columns = sorted(set(row) - set(write_fieldnames))
    if dropped_columns:
        result["dropped_csv_columns"] = dropped_columns
    with target_csv.open("a" if target_rows else "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=write_fieldnames, extrasaction="ignore")
        if not target_rows:
            writer.writeheader()
        writer.writerow({column: row.get(column, "") for column in write_fieldnames})
    return result
