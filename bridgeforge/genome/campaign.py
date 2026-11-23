"""94.G2 P3: star-system genes, and the campaign ids a gene's code names (2026-11-20).

**Anchor.** `star-system:<name>` is the constant name a loaded mod class passes to `SectorAPI.createStarSystem`, as
`combat-plugin:<key>` is a key of settings.json's `plugins` map: the gene's closure starts from that one class. The name may
reach the call through a local (Eridani's `String systemName = <constant>; sector.createStarSystem(systemName)`), so the
call's argument is followed through a local assigned only from that one constant. A computed name, no such class, or several
are refused. Loose-script generators are not closed yet and are refused by name.

**Registration.** A generator is called from the mod plugin's hook beside other features: Eridani's `onNewGame` also sets
faction relations and a bounty entry, and the GR-2 census found 71% of measured plugins put two or more features in one
hook. So the plugin is not a member. Each call site is a `registrations` element naming the plugin hooks that reach it, and
a gene with no call site reachable from a hook is refused. Identity (kind and members) therefore does not cover where the
gene is registered: a recorded choice, unlike `combat-plugin`, whose registration is a member.

**Campaign ids.** A literal of the gene's code that is exactly an id a campaign table defines is typed by that table:
- industries, market conditions, submarkets, special items and commodities (CSV rows);
- planet, custom-entity and terrain types (JSON keys);
- factions (`.faction` ids);
- graphics keys of `settings.json`, only when the category is also a literal of the code
  (`setInteractionImage("intel", <key>)`). Without that rule `nav_buoy` read as a core graphics key in two
  categories the code never names.

The mod's own definitions are members: a CSV row with the classes and files its cells name, a JSON key as a json-entry, a
graphics key with its file. The core's are `needs.vanilla` (`industry:farming`, `graphics:misc/rings_ice0`). A faction is
`needs.genes`: a gene of its own, since its ship lists are not this gene and the plugin's relations statements must stay
separable. An id several tables define names every kind, as `closure.ids_named_by_code` does; when one of them is the mod's
(a member), that is also a suspect.
"""
from __future__ import annotations

import re
import struct
from pathlib import Path

from bridgeforge.genome.closure import SETTINGS_FILE, code_literals, pointer, value_sha256
from bridgeforge.genome.gene import GeneError, _file_member, _loaded_classes, _row_member
from bridgeforge.mod_files import read_mod_info
from bridgeforge.vendor_plan import _rows

CAMPAIGN_CSV = {
    "industry": "data/campaign/industries.csv",
    "condition": "data/campaign/market_conditions.csv",
    "submarket": "data/campaign/submarkets.csv",
    "special-item": "data/campaign/special_items.csv",
    "commodity": "data/campaign/commodities.csv",
}
CAMPAIGN_JSON = {
    "planet-type": "data/config/planets.json",
    "entity-type": "data/config/custom_entities.json",
    "terrain-type": "data/campaign/terrain.json",
}
FACTIONS = "data/world/factions"
_CREATE_SYSTEM = ("createStarSystem", "(Ljava/lang/String;)Lcom/fs/starfarer/api/campaign/StarSystemAPI;")
_ADD_MARKET = ("com/fs/starfarer/api/campaign/econ/EconomyAPI", "addMarket")
_DOTTED_CLASS = re.compile(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)+\Z")


# ---------------------------------------------------------------- the anchor: who creates the system

def system_names(code: bytes, pool, params: int = 0) -> list[str | None]:
    """The name each `createStarSystem` call in one method receives; None when it is computed."""
    from bridgeforge.atlas.atlas_classfile import last_argument_constants

    return [constant for _owner, _name, _desc, constant in
            last_argument_constants(code, pool, lambda _owner, name, desc: (name, desc) == _CREATE_SYSTEM, params)]


def star_system_generators(root: Path) -> dict[str | None, list[str]]:
    """{system name (None: computed): [dotted classes]} over the classes of the mod's loaded jars."""
    from bridgeforge.atlas.atlas_classfile import ClassFormatError, iter_method_code
    from bridgeforge.scan.scan_classfile import _loaded_mod_jars, iter_class_files_in_jars

    found: dict[str | None, set[str]] = {}
    for _jar, _member, data in iter_class_files_in_jars(_loaded_mod_jars(Path(root))):
        try:
            methods = iter_method_code(data)
            for owner, _method, code, pool, params in methods:
                for name in system_names(code, pool, params):
                    found.setdefault(name, set()).add(owner.replace("/", "."))
        except (ClassFormatError, struct.error, IndexError, KeyError):
            continue  # an unreadable class names no system
    return {name: sorted(classes) for name, classes in found.items()}


def resolve_star_system(root: Path, name: str) -> str:
    """The one loaded class that creates star system `name` by a constant name."""
    generators = star_system_generators(root)
    classes = generators.get(name, [])
    if len(classes) == 1:
        return classes[0]
    if classes:
        raise GeneError(f"star-system:{name}: several loaded classes create it ({', '.join(classes)}); a gene is one generator")
    computed = generators.get(None, [])
    hint = f"; classes creating a system under a computed name: {', '.join(computed)}" if computed else ""
    raise GeneError(f"star-system:{name}: no class in the mod's loaded jars passes the constant {name!r} to "
                    f"SectorAPI.createStarSystem (loose-script generators are not closed yet){hint}")


# ---------------------------------------------------------------- registration and saved state

def _reach(classes: dict, plugin: str) -> dict[tuple[str, str], list[str]]:
    """{(class, method): [plugin hooks that reach it]} through calls among the mod's own loaded classes, by method name (as
    the census walks). Lambdas (invokedynamic) and reflection are not followed."""
    from bridgeforge.behavior_discovery import LIFECYCLE_HOOKS

    calls: dict[tuple[str, str], set[tuple[str, str]]] = {}
    for owner, info in classes.items():
        for name, targets in zip(info.code_methods, info.method_targets):
            calls.setdefault((owner, name), set()).update(t for t in targets if t[0] in classes)
    reached: dict[tuple[str, str], list[str]] = {}
    info = classes.get(plugin)
    for hook in LIFECYCLE_HOOKS if info else ():
        if hook not in info.methods:
            continue
        seen, frontier = {(plugin, hook)}, [(plugin, hook)]
        while frontier:
            frontier = [callee for caller in frontier for callee in calls.get(caller, ()) if callee not in seen]
            seen.update(frontier)
        for node in seen:
            reached.setdefault(node, []).append(hook)
    return reached


def registrations(root: Path, generator: str) -> list[dict]:
    """Every call into `generator` from the mod's other loaded classes, as `registrations` elements; refused when no call is
    reachable from a lifecycle hook of the mod plugin."""
    from bridgeforge.genome.census import _mod_classes

    internal = generator.replace(".", "/")
    plugin_name = (read_mod_info(Path(root)) or {}).get("modPlugin")
    plugin = plugin_name.strip().replace(".", "/") if isinstance(plugin_name, str) else ""
    if internal == plugin:
        raise GeneError(f"{generator} is the mod plugin itself: its system is built inside the plugin's hook beside the "
                        "plugin's other features, so it is not a separable gene")
    classes = _mod_classes(Path(root))
    reached = _reach(classes, plugin)
    elements = []
    for owner, info in sorted(classes.items()):
        if owner == internal:
            continue
        for method, targets in zip(info.code_methods, info.method_targets):
            called = sorted({name for target, name in targets if target == internal})
            if called:
                elements.append({"locus": f"{owner.replace('/', '.')}.{method}", "statement": f"{generator}: {', '.join(called)}",
                                 "hooks": sorted(set(reached.get((owner, method), [])))})
    if not any(element["hooks"] for element in elements):
        sites = ", ".join(element["locus"] for element in elements) or "none"
        raise GeneError(f"{generator}: no call to it is reachable from a lifecycle hook of the mod plugin {plugin_name!r} "
                        f"through the mod's own classes (call sites: {sites}; lambdas and reflection are not followed); "
                        "a star system nothing generates is not a gene")
    return elements


def adds_markets(root: Path, generator: str) -> bool:
    """True when the generator class itself calls `EconomyAPI.addMarket`."""
    from bridgeforge.genome.census import _mod_classes

    info = _mod_classes(Path(root)).get(generator.replace(".", "/"))
    return bool(info) and any(target == _ADD_MARKET for targets in info.method_targets for target in targets)


def star_system(mod: Path, name: str) -> dict:
    """{generator, registrations, persistent_state, suspects} for `star-system:<name>`."""
    from bridgeforge.vendor_plan import _mod_root

    root = _mod_root(mod)
    generator = resolve_star_system(root, name)
    state = [{"name": f"star system {name}", "via": f"SectorAPI.createStarSystem in {generator}: saved with the sector"}]
    suspects = []
    if adds_markets(root, generator):
        state.append({"name": f"the markets {generator} adds", "via": "EconomyAPI.addMarket: saved with the economy"})
        suspects.append({"path": generator, "mentions": [], "reason": "builds markets whose ids are computed at run time: "
                         "no market: id is claimed as provided; they come with the generator"})
    return {"generator": generator, "registrations": registrations(root, generator), "persistent_state": state,
            "suspects": suspects}


# ---------------------------------------------------------------- campaign ids the code names

def _json_object(path: Path) -> dict:
    from bridgeforge.scan.scan_json import _parse_json

    if not path.is_file():
        return {}
    try:
        data, _tolerances = _parse_json(path.read_text(encoding="utf-8-sig", errors="replace"))
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


class _CampaignIndex:
    """The campaign definitions of one root (the mod or the core); an absent root defines nothing."""

    def __init__(self, root: Path | None) -> None:
        self.root = root
        self.rows = {kind: _rows(root, table) for kind, table in CAMPAIGN_CSV.items()} if root else {}
        self.keys = {kind: _json_object(root / rel) for kind, rel in CAMPAIGN_JSON.items()} if root else {}
        self.factions: dict[str, str] = {}
        for path in sorted((root / FACTIONS).glob("*.faction")) if root and (root / FACTIONS).is_dir() else []:
            ident = _json_object(path).get("id")
            if isinstance(ident, str) and ident:
                self.factions.setdefault(ident, path.relative_to(root).as_posix())
        graphics = _json_object(root / SETTINGS_FILE).get("graphics") if root else None
        self.graphics = {(category, key): value for category, keys in (graphics if isinstance(graphics, dict) else {}).items()
                         if isinstance(keys, dict) for key, value in keys.items()}

    def hits(self, literal: str, literals: set[str]) -> list[tuple[str, str]]:
        """(kind, detail) for each definition of `literal`: detail is the table, the JSON file or the graphics category."""
        found = [(kind, CAMPAIGN_CSV[kind]) for kind, rows in self.rows.items() if literal in rows]
        found += [(kind, CAMPAIGN_JSON[kind]) for kind, keys in self.keys.items() if literal in keys]
        if literal in self.factions:
            found.append(("faction", self.factions[literal]))
        found += [("graphics", category) for category, key in self.graphics if key == literal and category in literals]
        return found


def _inside_file(root: Path, value: str) -> str | None:
    """`value` as a file path relative to the mod, when it names a file inside it."""
    if "/" not in value or "\\" in value or "\x00" in value:
        return None
    try:
        path, base = (root / value).resolve(), root.resolve()
        return path.relative_to(base).as_posix() if path.is_relative_to(base) and path.is_file() else None
    except (OSError, ValueError):
        return None


def _row_parts(root: Path, table: str, ident: str, loaded: dict) -> tuple[list[dict], list[str]]:
    """The row member, the files its cells name and the mod classes its cells name (an industry's plugin and icon)."""
    members = [{**_row_member(root, f"{table} [{ident}]"), "reason": f"{table} row the gene's code names"}]
    classes: list[str] = []
    for value in (v.strip() for v in _rows(root, table)[ident].values() if isinstance(v, str)):
        internal = value.replace(".", "/")
        if _DOTTED_CLASS.match(value) and (f"{internal}.class" in loaded or (root / f"{internal}.java").is_file()):
            classes.append(value)
        elif (relative := _inside_file(root, value)) is not None:
            members.append({**_file_member(root, relative), "reason": f"file the {table} row {ident} names"})
    return members, classes


def _mod_parts(root: Path, index: _CampaignIndex, literal: str, kind: str, detail: str, loaded: dict) -> dict:
    """What one mod definition of `literal` adds to the gene."""
    if kind in CAMPAIGN_CSV:
        members, classes = _row_parts(root, detail, literal, loaded)
        return {"members": members, "classes": classes, "provides": [f"{kind}:{literal}"]}
    if kind in CAMPAIGN_JSON:
        value = index.keys[kind][literal]
        member = {"what": "json-entry", "path": f"{detail}#{pointer(literal)}", "sha256": value_sha256(value),
                  "reason": f"{kind} the gene's code names"}
        return {"members": [member], "provides": [f"{kind}:{literal}"]}
    if kind == "faction":
        return {"genes": [f"faction:{literal}"]}
    value = index.graphics[(detail, literal)]
    members = [{"what": "json-entry", "path": f"{SETTINGS_FILE}#/graphics{pointer(detail)}{pointer(literal)}",
                "sha256": value_sha256(value), "reason": f"graphics key {detail}/{literal} the gene's code names"}]
    relative = _inside_file(root, value) if isinstance(value, str) else None
    if relative is not None:
        members.append({**_file_member(root, relative), "reason": f"file the graphics key {detail}/{literal} names"})
    return {"members": members}


def campaign_ids(root: Path, code_members: list[dict], vanilla_core: Path | None) -> dict:
    """{members, classes, provides, vanilla, genes, suspects, industries} for the campaign ids the gene's code names."""
    root = Path(root)
    literals = code_literals(root, code_members)
    mod = _CampaignIndex(root)
    core = _CampaignIndex(Path(vanilla_core).expanduser().resolve() if vanilla_core else None)
    loaded = _loaded_classes(root)
    result: dict[str, list] = {key: [] for key in ("members", "classes", "provides", "vanilla", "genes", "suspects", "industries")}
    for literal in sorted(literals):
        own, core_hits = mod.hits(literal, literals), core.hits(literal, literals)
        for kind, detail in own:
            for key, values in _mod_parts(root, mod, literal, kind, detail, loaded).items():
                result[key] += values
            if kind == "industry":
                result["industries"].append(literal)
        own_kinds = {kind for kind, _ in own}
        result["vanilla"] += [f"graphics:{detail}/{literal}" if kind == "graphics" else f"{kind}:{literal}"
                              for kind, detail in core_hits if kind not in own_kinds]
        if own and len({kind for kind, _ in own + core_hits}) > 1:
            result["suspects"].append({"path": literal, "mentions": sorted({kind for kind, _ in own + core_hits}),
                                       "reason": "a literal several campaign tables define: every kind is named; check "
                                                 "which one the code means"})
    for key in ("classes", "provides", "vanilla", "genes", "industries"):
        result[key] = sorted(set(result[key]))
    return result


__all__ = ["CAMPAIGN_CSV", "CAMPAIGN_JSON", "campaign_ids", "registrations", "resolve_star_system", "star_system",
           "star_system_generators", "system_names"]
