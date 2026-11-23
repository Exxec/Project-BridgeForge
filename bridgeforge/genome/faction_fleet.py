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


def _split(value: object) -> set[str]:
    return {t.strip() for t in str(value or "").split(",") if t.strip()}


def tagged(index, kind: str) -> dict[str, set[str]]:
    """{id: tags} of one folder's hulls (ship_data.csv `tags`, comma-separated; a skin has only its own `.skin` `tags`) or
    wings (wing_data.csv `tags`). RC7 javap 2026-11-23: ShipHullSpreadsheetLoader splits the CSV column on ","; the skin
    loader clones its base hull's spec, clears its tags and adds the skin's `tags` array."""
    found = {ident: _split(row.get("tags")) for ident, row in index.rows.get(kind, {}).items()}
    if kind == "hull":
        for ident, path in index.skin.items():
            tags = _json_object(path).get("tags")
            found[ident] = {t.strip() for t in tags if isinstance(t, str) and t.strip()} if isinstance(tags, list) else set()
    return found


def known(faction: dict, mod_index=None, core_index=None) -> dict:
    """What the faction's known and priority lists name: {"hull": ids, "wing": ids} (named or reached through a tag),
    {"by_tag": {"hull": ids, "wing": ids}} (reached only through a tag), {"tags": {"hull": tags, "wing": tags}} and
    {"unmatched": tags no hull or wing carries}. RC7's faction loader (`SpecStore`, javap 2026-11-23) adds every hull whose
    spec `hasTag` any of the block's `tags`, then the block's named ids. Slice 24, the advisor's recommendation after the
    owner deferred (2026-11-23): hull and wing tags are expanded against the mod and the core; a mod's row wins over the
    core's for the same id."""
    from bridgeforge.genome.faction import LIST_FIELD

    found: dict = {"hull": set(), "wing": set(), "by_tag": {"hull": set(), "wing": set()},
                   "tags": {"hull": set(), "wing": set()}, "unmatched": set()}
    for key, kind in _KNOWN.items():
        block = faction.get(key)
        values = block.get(LIST_FIELD[kind]) if isinstance(block, dict) else None
        found[kind] |= {v for v in values if isinstance(v, str)} if isinstance(values, list) else set()
        tags = block.get("tags") if isinstance(block, dict) else None
        found["tags"][kind] |= {t for t in tags if isinstance(t, str)} if isinstance(tags, list) else set()
    matched: set[str] = set()
    for kind in ("hull", "wing"):
        wanted = found["tags"][kind]
        if not wanted:
            continue
        carriers = {**(tagged(core_index, kind) if core_index is not None else {}),
                    **(tagged(mod_index, kind) if mod_index is not None else {})}
        reached = {ident for ident, tags in carriers.items() if tags & wanted}
        found["by_tag"][kind] = reached - found[kind]
        found[kind] |= reached
        matched |= wanted & {t for ident in reached for t in carriers[ident]}
    # A tag both lists name (ships and fighters) is unmatched only when neither kind carries it.
    found["unmatched"] = (found["tags"]["hull"] | found["tags"]["wing"]) - matched
    return found


def fleet_needs(root: Path, faction: dict, mod_index, core_index) -> dict[str, list]:
    """{"donor", "genes", "vanilla", "missing", "suspects"}: the role entries of the donor's `default_ship_roles.json` that
    name a variant of a hull the faction knows, or a wing it knows, and what each entry names. A role block with a chosen
    entry also brings its `includeDefault`/`fallback` keys. Review of slice 23: a faction that knows hulls or wings by tag,
    and a role variant nothing defines (perhaps a dependency's), are suspects, never dropped silently."""
    from bridgeforge.genome.closure import pointer
    from bridgeforge.genome.faction import ROLE_NOT_VARIANTS, ROLE_SKIPPED

    roles = _json_object(Path(root) / ROLES_FILE)
    knows = known(faction, mod_index, core_index)
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
    # Slice 24: a hull or wing the faction knows only through a tag is a gene it needs when the mod defines it, as a named one
    # is (faction.py); one the core defines counts for role matching only.
    for kind in ("hull", "wing"):
        result["genes"] += [f"{kind}:{ident}" for ident in knows["by_tag"][kind] if mod_index.defines(kind, ident)]
    if knows["unmatched"]:
        result["suspects"].append({"path": ROLES_FILE if roles else "faction", "mentions": sorted(knows["unmatched"]),
                                   "reason": "faction tags that no hull or wing of the mod or the core carries (perhaps a "
                                   "dependency's): ships known through them are not carried, so its fleet may be partial (RC8-54)"})
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
