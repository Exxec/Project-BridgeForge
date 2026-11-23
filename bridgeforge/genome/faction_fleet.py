"""A faction's fleet: the shared ship-role entries that give its known hulls and wings something to field (94.G2 slice 23).

Owner 2026-11-23 ("Yes, as needs"): a faction's fleet is part of its gene.
- **Needs:** the donor's `data/world/factions/default_ship_roles.json` entries for the variants of the hulls, and the wings,
  the faction knows are `needs.donor`. The variants and wings those entries name are genes the faction needs, as a custom
  start's ship is.
- **Why:** P3B-CAR3-20261123 loaded and fought, but its carried faction fielded no fleet (the probe's `faction-fleet-gen`
  FAIL). It knew 21 hulls and carried 6 variants and no role entries.

The role file's shape follows RC8_BEHAVIOUR RC8-46 (javap of `loading.V`, 2026-11-20):
- a role maps variant or wing ids (a wing's ends in `_wing`) to weights;
- `includeDefault`, `fallback` and `fallback2` are not entries, and a role named `doctrine` is skipped;
- every id the file names must exist when content loads, or the game is Fatal.

So the carrier check reports a role entry whose variant or wing nothing defines (`ship-role-variant-missing`). That check
runs on the carrier only: a variant gene's subtraction rightly leaves its role entries in the donor (a recorded dependent,
`loaded: always`).
"""
from __future__ import annotations

from pathlib import Path

from bridgeforge.genome.combat_needs import _json_object

ROLES_FILE = "data/world/factions/default_ship_roles.json"
_KNOWN = {"knownShips": "hull", "priorityShips": "hull", "knownFighters": "wing", "priorityFighters": "wing"}


def known(faction: dict) -> dict[str, set[str]]:
    """{"hull": ids, "wing": ids, "tags": tags} the faction's known and priority lists name. Tags are not expanded (a slice-10
    decision); `fleet_needs` flags them."""
    from bridgeforge.genome.faction import LIST_FIELD

    found: dict[str, set[str]] = {"hull": set(), "wing": set(), "tags": set()}
    for key, kind in _KNOWN.items():
        block = faction.get(key)
        values = block.get(LIST_FIELD[kind]) if isinstance(block, dict) else None
        found[kind] |= {v for v in values if isinstance(v, str)} if isinstance(values, list) else set()
        tags = block.get("tags") if isinstance(block, dict) else None
        found["tags"] |= {t for t in tags if isinstance(t, str)} if isinstance(tags, list) else set()
    return found


def fleet_needs(root: Path, faction: dict, mod_index, core_index) -> dict[str, list]:
    """{"donor", "genes", "vanilla", "missing", "suspects"}: the role entries of the donor's `default_ship_roles.json` that
    name a variant of a hull the faction knows, or a wing it knows, and what each entry names. A role block with a chosen
    entry also brings its `includeDefault`/`fallback` keys. Review of slice 23: a faction that knows hulls or wings by tag,
    and a role variant nothing defines (perhaps a dependency's), are suspects, never dropped silently."""
    from bridgeforge.genome.closure import pointer
    from bridgeforge.genome.faction import ROLE_NOT_VARIANTS, ROLE_SKIPPED

    roles = _json_object(Path(root) / ROLES_FILE)
    knows = known(faction)
    result: dict[str, list] = {"donor": [], "genes": [], "vanilla": [], "missing": [], "suspects": []}
    undefined = []
    for role, block in sorted(roles.items()):
        if role in ROLE_SKIPPED or not isinstance(block, dict):
            continue
        chosen = []
        for key in block:
            if key in ROLE_NOT_VARIANTS or not isinstance(key, str):
                continue
            kind = "wing" if key.endswith("_wing") else "variant"
            if not (mod_index.defines(kind, key) or core_index.defines(kind, key)):
                undefined.append(key)
                continue
            if key not in knows["wing"] if kind == "wing" else _hull_of(key, mod_index, core_index) not in knows["hull"]:
                continue
            chosen.append(key)
            result["genes" if mod_index.defines(kind, key) else "vanilla"].append(f"{kind}:{key}")
        if chosen:
            result["donor"] += [f"{ROLES_FILE}#{pointer(role)}{pointer(key)}" for key in [*chosen, *(k for k in block if k in ROLE_NOT_VARIANTS)]]
    if knows["tags"] and roles:
        result["suspects"].append({"path": ROLES_FILE, "mentions": sorted(knows["tags"]), "reason": "the faction knows hulls or "
                                   "wings by tag, which is not expanded: role entries for them are not carried, so its fleet "
                                   "may be partial or empty (RC8-54)"})
    if undefined:
        result["suspects"].append({"path": ROLES_FILE, "mentions": sorted(set(undefined)), "reason": "role entries whose variant "
                                   "or wing neither the mod nor the core defines (perhaps a dependency's): not judged"})
    return {key: values if key == "suspects" else sorted(set(values)) for key, values in result.items()}


def _hull_of(variant: str, mod_index, core_index) -> str | None:
    path = mod_index.variant.get(variant) or core_index.variant.get(variant)
    spec = _json_object(path) if path is not None else {}
    hull = spec.get("hullId")
    return hull if isinstance(hull, str) else None


def role_gaps(carrier: Path, others: list[Path]) -> list[dict]:
    """`ship-role-variant-missing`: an entry of the carrier's `default_ship_roles.json`, or of a carried `.faction`'s
    `shipRoles`, whose variant or wing neither the carrier, a declared dependency nor the core defines (RC8-46). The
    check runs on the carrier only."""
    from bridgeforge.genome.faction import ROLE_NOT_VARIANTS, ROLE_SKIPPED
    from bridgeforge.vendor_plan import _rows, _specs

    from bridgeforge.scan.scanner import _load_lenient_json_file

    carrier = Path(carrier)
    roots = [carrier, *others]
    variants = {v for root in roots for v in _specs(root, "data/variants", "*.variant", "variantId")}
    wings = {w for root in roots for w in _rows(root, "data/hulls/wing_data.csv")}
    gaps, sources = [], []
    factions = carrier / "data" / "world" / "factions"
    for path in [carrier / ROLES_FILE, *(sorted(factions.glob("*.faction")) if factions.is_dir() else [])]:
        if not path.is_file():
            continue
        data = _load_lenient_json_file(path)
        relative = path.relative_to(carrier).as_posix()
        if not isinstance(data, dict):  # fail closed, as `hull-styles-unreadable` does (review of slice 23)
            gaps.append({"finding": "ship-roles-unreadable", "file": relative})
            continue
        roles = data if relative == ROLES_FILE else data.get("shipRoles")
        sources.append((relative, roles if isinstance(roles, dict) else {}))
    for file, roles in sources:
        for role, block in sorted(roles.items()):
            if role in ROLE_SKIPPED or not isinstance(block, dict):
                continue
            for key in block:
                if key in ROLE_NOT_VARIANTS or not isinstance(key, str):
                    continue
                if key not in (wings if key.endswith("_wing") else variants):
                    gaps.append({"finding": "ship-role-variant-missing", "file": file, "role": role, "id": key})
    return gaps


__all__ = ["ROLES_FILE", "fleet_needs", "known", "role_gaps"]
