"""Strip and vendor plans for a STRIP_FROM_MOD recommendation (ROADMAP P14 item 4).

`dependency-substitutes` can recommend STRIP_FROM_MOD, but only as a strategy name and a summary
reason - nothing generates the actual edit list (which `.variant`/`.ship`/`.skin`/`.faction` line
loses which id), or proposes a real vanilla substitute. This module does both:

- `strip_plan`: for every content id the mod uses and nothing defines (optionally one `--id kind:id`),
  every file and field it sits in (variant slots, hull-mod and wing lists, built-in weapons, faction
  known-lists), with vanilla weapons that fit each emptied slot, using the scanner's own slot-fit
  logic. Hullmods and wings have no slot to substitute into, so those entries propose removal only.
- `propose_expected_changes`: adds a PROPOSED static-layer expected change per file the plan
  deletes, so approval goes through the existing `expect approve` mechanism rather than a new one.
- `vendor_copy`: "where the licence allows, offer vendoring as an alternative: copy the one missing
  piece... instead of reviving a heavy provider" (the item's own example: Rebal's
  `shields_formshield` into Explorer Society). Scoped to hullmods only - a CSV row plus its
  declared script class is a single, well-defined unit to copy; a weapon/wing/hull involves sprite
  and balance data this command has no reliable way to locate or validate, so those kinds are
  refused outright rather than copied incompletely. A licence gate (`release._licence_gate`, the
  same one `release`/item 7 use) blocks vendoring from a local-only source. `--apply` is required
  to actually write; the default is a dry-run plan, matching `fold`'s own convention.

Read-only except `propose_expected_changes` (only ever adds PROPOSED entries to an expected-changes
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
    MOUNT_OVERRIDE_FITS,
    WEAPON_SLOT_SIZE_RANK,
    WEAPON_SLOT_SKIP_TYPES,
    _load_lenient_json_file,
    _read_csv_rows_lenient,
    _relative,
    _resolve_hull_id,
    _skin_index,
    _ship_file_index,
    _weapon_slot_type_compatible,
    _wpn_type_size_index,
    scan_mod,
)

SCHEMA_VERSION = 1

_HULLMOD_FIELDS = ("hullMods", "permaMods", "sMods", "builtInMods", "removeBuiltInMods")
_WING_FIELDS = ("wings", "builtInWings")


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


SCHEMA_VERSION = 1
MAX_SUBSTITUTES = 8
_LIST_KEYS = {
    "hullmod": ("hullMods", "permaMods", "sMods", "builtInMods", "removeBuiltInMods"),
    "wing": ("wings", "builtInWings"),
}
# .faction known-list layout, as `fix --finding faction-known-lists-missing` writes it.
_FACTION_LISTS = {"hull": ("knownShips", "hulls"), "weapon": ("knownWeapons", "weapons"), "wing": ("knownFighters", "fighters")}
_MOUNTABLE = {"BALLISTIC", "ENERGY", "MISSILE"}


class StripPlanError(ValueError):
    """Raised for a missing mod folder or vanilla core."""


def _substitutes(slot: dict | None, vanilla_weapons: dict[str, dict[str, str]]) -> dict:
    if not isinstance(slot, dict):
        return {"slot": None, "candidates": [], "note": "slot not found on the resolved hull; no substitute proposed"}
    slot_type = str(slot.get("type") or "").strip().upper()
    slot_size = str(slot.get("size") or "").strip().upper()
    if slot_type in WEAPON_SLOT_SKIP_TYPES or slot_size not in WEAPON_SLOT_SIZE_RANK:
        return {"slot": f"{slot_type} {slot_size}", "candidates": [], "note": "not a regular weapon slot; no substitute proposed"}
    fits = sorted(
        weapon_id for weapon_id, spec in vanilla_weapons.items()
        if spec.get("size") == slot_size and (
            (spec.get("type") in _MOUNTABLE and _weapon_slot_type_compatible(slot_type, spec["type"]))
            or slot_type in MOUNT_OVERRIDE_FITS.get(spec.get("mount_override", ""), set()))
    )
    return {"slot": f"{slot_type} {slot_size}", "candidates": fits[:MAX_SUBSTITUTES], "candidate_count": len(fits)}


def strip_plan(mod_dir: Path, vanilla_core: Path, only: list[str] | None = None) -> dict:
    mod_dir, vanilla_core = Path(mod_dir).expanduser().resolve(), Path(vanilla_core).expanduser().resolve()
    if not (mod_dir / "mod_info.json").is_file():
        raise StripPlanError(f"{mod_dir} has no mod_info.json.")
    if not (vanilla_core / "data").is_dir():
        raise StripPlanError(f"{vanilla_core} has no data/ folder; pass a starsector-core folder.")
    scan = scan_mod(mod_dir, TargetProfile(), vanilla_core)
    unresolved: dict[str, dict[str, list[str]]] = scan.migration_context.get("unresolved_content_references") or {}
    wanted = {tuple(item.split(":", 1)) for item in only or [] if ":" in item}
    targets = {kind: set(ids) for kind, ids in unresolved.items()}
    if wanted:
        targets = {kind: {ident for ident in ids if (kind, ident) in wanted} for kind, ids in targets.items()}
    ships, skins = _ship_file_index(mod_dir, vanilla_core), _skin_index(mod_dir, vanilla_core)
    vanilla_weapons = _wpn_type_size_index(vanilla_core, None)

    edits: list[dict] = []
    files = sorted({path for kind, ids in unresolved.items() for ident, paths in ids.items() if ident in targets.get(kind, set()) for path in paths})
    factions = mod_dir / "data" / "world" / "factions"
    files += sorted(path.relative_to(mod_dir).as_posix() for path in factions.glob("*.faction")) if factions.is_dir() else []
    for relative in files:
        spec = _load_lenient_json_file(mod_dir / relative)
        if not isinstance(spec, dict):
            continue
        suffix = Path(relative).suffix.lower()
        if suffix == ".faction":
            for kind, (outer, inner) in _FACTION_LISTS.items():
                block = spec.get(outer)
                for ident in (block.get(inner) or []) if isinstance(block, dict) else []:
                    if ident in targets.get(kind, set()):
                        edits.append({"file": relative, "kind": kind, "id": ident, "action": f"remove from {outer}.{inner}"})
            continue
        hull_key = "hullId" if suffix == ".variant" else "baseHullId" if suffix == ".skin" else None
        if hull_key and spec.get(hull_key) in targets.get("hull", set()):
            edits.append({"file": relative, "kind": "hull", "id": spec[hull_key],
                          "action": f"delete this {suffix[1:]}: its {hull_key} is unresolved, so nothing in it can load"})
            continue
        for kind, keys in _LIST_KEYS.items():
            for key in keys:
                for ident in spec.get(key) or []:
                    if ident in targets.get(kind, set()):
                        edits.append({"file": relative, "kind": kind, "id": ident, "action": f"remove from {key}"})
        own_hull = spec.get("hullId") if suffix == ".variant" else spec.get("skinHullId") if suffix == ".skin" else spec.get("hullId")
        hull_spec = ships.get(_resolve_hull_id(own_hull, skins)) if isinstance(own_hull, str) else None
        if suffix == ".ship":
            hull_spec = spec
        slots = {slot["id"]: slot for slot in (hull_spec or {}).get("weaponSlots") or [] if isinstance(slot, dict) and isinstance(slot.get("id"), str)}
        for index, group in enumerate(spec.get("weaponGroups") or []):
            for slot_id, ident in (group.get("weapons") or {}).items() if isinstance(group, dict) and isinstance(group.get("weapons"), dict) else []:
                if ident in targets.get("weapon", set()):
                    edits.append({"file": relative, "kind": "weapon", "id": ident, "action": f"empty slot {slot_id} (weaponGroups[{index}])",
                                  "substitutes": _substitutes(slots.get(slot_id), vanilla_weapons)})
        for slot_id, ident in (spec.get("builtInWeapons") or {}).items() if isinstance(spec.get("builtInWeapons"), dict) else []:
            if ident in targets.get("weapon", set()):
                edits.append({"file": relative, "kind": "weapon", "id": ident, "action": f"remove built-in weapon at {slot_id}",
                              "substitutes": _substitutes(slots.get(slot_id), vanilla_weapons)})

    by_id: dict[str, int] = {}
    for edit in edits:
        by_id[f"{edit['kind']}:{edit['id']}"] = by_id.get(f"{edit['kind']}:{edit['id']}", 0) + 1
    return {
        "schema_version": SCHEMA_VERSION, "mode": "STRIP_PLAN", "mod": str(mod_dir), "vanilla_core": str(vanilla_core),
        "unresolved": {kind: sorted(ids) for kind, ids in unresolved.items()},
        "planned": sorted(by_id), "edits": edits, "edit_count_by_id": by_id,
        "note": "A plan only: nothing was edited. Substitutes fit the slot's type and size; picking one (or leaving the slot empty) is a design decision.",
    }


def propose_expected_changes(plan: dict, expected_path: Path, *, build: str, links: dict[str, list[str]], mod_id: str | None = None) -> list[str]:
    """Add a PROPOSED static-layer expected change for each file the plan deletes; return the new ids."""
    from .behavior_discovery import add_expected_change
    from .scanner import _load_lenient_json_file

    if not any(links.get(kind) for kind in ("risk", "hyp", "test")):
        raise StripPlanError("expected changes need at least one --link risk=|hyp=|test= id (expect check requires it)")
    if mod_id is None:
        info = _load_lenient_json_file(Path(plan["mod"]) / "mod_info.json")
        mod_id = info.get("id") if isinstance(info, dict) else None
    if not mod_id:
        raise StripPlanError("the mod's mod_info.json has no id")
    existing = _load_lenient_json_file(expected_path) if Path(expected_path).is_file() else None
    ids = [str(item.get("id")) for item in (existing or {}).get("changes", []) if isinstance(item, dict)] if isinstance(existing, dict) else []
    prefixes = sorted({m.group(1) for m in (re.fullmatch(r"EXP-([A-Za-z0-9]+)-(\d+)", i) for i in ids) if m})
    prefix = prefixes[0] if prefixes else (re.sub(r"[^A-Za-z0-9]", "", mod_id).upper()[:8] or "MOD")
    number = max([int(m.group(1)) for m in (re.fullmatch(rf"EXP-{re.escape(prefix)}-(\d+)", i) for i in ids) if m] + [0])
    added = []
    deletions = {}
    for edit in plan["edits"]:
        if edit["action"].startswith("delete this"):
            deletions.setdefault(edit["file"], edit)
    for relative, edit in sorted(deletions.items()):
        number += 1
        change_id = f"EXP-{prefix}-{number:03d}"
        add_expected_change(
            Path(expected_path), mod_id=mod_id, change_id=change_id, build=build, layer="static",
            summary=f"Remove {relative}",
            why=f"Its {edit['kind']} '{edit['id']}' is defined by no installed mod or vanilla (content-reference-unresolved), so nothing in the file can load; stripped per strip-plan.",
            match={"observation": "static.data", "subject": relative, "field": "present", "change": "removed"},
            links={kind: list(values) for kind, values in links.items() if values}, proposed_by="strip-plan",
        )
        added.append(change_id)
    return added
