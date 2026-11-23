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

ROLES_FILE = "data/world/factions/default_ship_roles.json"
_KNOWN = {"knownShips": "hull", "priorityShips": "hull", "knownFighters": "wing", "priorityFighters": "wing"}


def _json_object(path: Path) -> dict:
    from bridgeforge.scan.scanner import _load_lenient_json_file

    data = _load_lenient_json_file(path) if path.is_file() else None
    return data if isinstance(data, dict) else {}


def known(faction: dict) -> dict[str, set[str]]:
    """{"hull": ids, "wing": ids} the faction's known and priority lists name."""
    from bridgeforge.genome.faction import LIST_FIELD

    found: dict[str, set[str]] = {"hull": set(), "wing": set()}
    for key, kind in _KNOWN.items():
        block = faction.get(key)
        values = block.get(LIST_FIELD[kind]) if isinstance(block, dict) else None
        found[kind] |= {v for v in values if isinstance(v, str)} if isinstance(values, list) else set()
    return found


def fleet_needs(root: Path, faction: dict, mod_index, core_index) -> dict[str, list[str]]:
    """{"donor", "genes", "vanilla", "missing"}: the role entries of the donor's `default_ship_roles.json` that name a
    variant of a hull the faction knows, or a wing it knows, and what each entry names. A role block with a chosen entry
    also brings its `includeDefault`/`fallback` keys."""
    from bridgeforge.genome.closure import pointer
    from bridgeforge.genome.faction import ROLE_NOT_VARIANTS, ROLE_SKIPPED

    roles = _json_object(Path(root) / ROLES_FILE)
    knows = known(faction)
    result: dict[str, list[str]] = {"donor": [], "genes": [], "vanilla": [], "missing": []}
    for role, block in sorted(roles.items()):
        if role in ROLE_SKIPPED or not isinstance(block, dict):
            continue
        chosen = []
        for key in block:
            if key in ROLE_NOT_VARIANTS or not isinstance(key, str):
                continue
            kind = "wing" if key.endswith("_wing") else "variant"
            if kind == "wing" and key not in knows["wing"]:
                continue
            if kind == "variant" and _hull_of(key, mod_index, core_index) not in knows["hull"]:
                continue
            chosen.append(key)
            if mod_index.defines(kind, key):
                result["genes"].append(f"{kind}:{key}")
            elif core_index.defines(kind, key):
                result["vanilla"].append(f"{kind}:{key}")
            else:
                result["missing"].append(f"{kind}:{key} ({ROLES_FILE} role {role}; neither the mod nor the core defines it)")
        if chosen:
            result["donor"] += [f"{ROLES_FILE}#{pointer(role)}{pointer(key)}" for key in [*chosen, *(k for k in block if k in ROLE_NOT_VARIANTS)]]
    return {key: sorted(set(values)) for key, values in result.items()}


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

    carrier = Path(carrier)
    roots = [carrier, *others]
    variants = {v for root in roots for v in _specs(root, "data/variants", "*.variant", "variantId")}
    wings = {w for root in roots for w in _rows(root, "data/hulls/wing_data.csv")}
    sources = [(ROLES_FILE, _json_object(carrier / ROLES_FILE))]
    factions = carrier / "data" / "world" / "factions"
    for path in sorted(factions.glob("*.faction")) if factions.is_dir() else []:
        roles = _json_object(path).get("shipRoles")
        sources.append((path.relative_to(carrier).as_posix(), roles if isinstance(roles, dict) else {}))
    gaps = []
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
