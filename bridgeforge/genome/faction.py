"""94.G2 slice 10: faction genes, described (2026-11-20). P3's star system needs `faction:EridaniCombine`.

**Boundary (advisor 2026-11-20, inside schema 4).** `faction:<id>` is a `.faction` file the mod ships whose id the core lacks;
a mod's file for a core faction id is a merge fragment, not a gene, and is refused by name. Members:
- the `.faction` file whole: identity then covers its lists, so a faction knowing one more ship is a new allele (element-level
  membership would need the array member kind schema 4 refuses: a recorded choice);
- its `data/world/factions/factions.csv` row, keyed by the table's `faction` column (RC7's SpecStore reads the table with
  that key: javap 2026-11-20), the registration that makes the game load the file;
- the mod files its scalar keys name (`logo`, `crest`, the `portraits` lists).

**Needs.** Each id the content lists (`save_doctor.FACTION_LISTS`), the weight maps (sell frequencies, `shipSellFrequency`,
`variantOverrides`, `hullFrequency.hulls`) and `shipRoles` name: one the mod defines is `needs.genes` (`hull:x`, `weapon:x`,
`wing:x`, `hullmod:x`, `variant:x`, each a gene of its own: the faction carries none of them), one the core defines is
`needs.vanilla`, one neither defines is missing, never dropped. A `shipRoles` variant nothing defines is Fatal at load
(RC8-46). Tags name sets (`tritachyon`, a mod's blueprint tag): recorded as suspects, not expanded. `illegalCommodities` are
`commodity:` needs. Every other key that is not plain display data (`music`, `voices`, `names`, `factionDoctrine`, ...) is a
suspect at its JSON pointer (advisor 2026-11-20). Eridani's faction needs 54 of the mod's own content genes (measured).

**Registrations.** Code that passes the id as a constant to `getFaction` or `addParticipatingFaction` is an element (call site,
hooks), not a member; `setRelationship` calls in those methods are recorded as an unknown (receiver tracking is not built).
**Saved state:** a saved `Faction` keeps its content lists (RC8_BEHAVIOUR RC8-43).
"""
from __future__ import annotations

from pathlib import Path

from bridgeforge.genome.gene import (GENE_SCHEMA, GENE_SCHEMA_VERSION, PHENOTYPE, GeneError, _file_member, _licence,
                                     _row_member, _version_text, identity, validate)
from bridgeforge.mod_files import read_mod_info

FACTIONS_CSV = "data/world/factions/factions.csv"
COMMODITIES_CSV = "data/campaign/commodities.csv"
LIST_FIELD = {"hull": "hulls", "weapon": "weapons", "wing": "fighters", "hullmod": "hullMods"}
# Maps from an id to a weight: the sell maps, `variantOverrides`, and `hullFrequency`'s `hulls` (its `tags` are tags).
SELL_LISTS = {"weaponSellFrequency": "weapon", "fighterSellFrequency": "wing", "hullmodSellFrequency": "hullmod",
              "shipSellFrequency": "hull", "variantOverrides": "variant"}
# `shipRoles` maps a role to {variant or wing id: weight}. RC7 builds it into the spec whose constructor asks each entry's
# fleet-point cost at load (RC8_BEHAVIOUR RC8-46). From javap of `loading.V` and `V$Oo` (2026-11-20): a role named `doctrine`
# is skipped; `includeDefault` (a boolean), `fallback` and `fallback2` (roles) are not entries; an id ending in `_wing` is a
# wing (`V$Oo.isFighterWing` is `id.endsWith("_wing")`), any other a variant.
ROLE_SKIPPED = frozenset({"doctrine"})
ROLE_NOT_VARIANTS = frozenset({"includeDefault", "fallback", "fallback2"})
# Keys that hold no ids: every key of RC7's 22 core .faction files and Eridani's was looked at (2026-11-20). Any other key
# this module does not read is a suspect, since it may name sounds, name sets, voices or skills the faction needs. Not
# `custom`: the core's pirates and Luddic Path name station hulls there (`pirateBaseStationTypes`, review 2026-11-20).
PLAIN_KEYS = frozenset({
    "id", "color", "baseUIColor", "brightUIColor", "darkUIColor", "gridUIColor", "secondaryUIColor", "secondarySegments",
    "description", "displayName", "displayNameWithArticle", "displayNameLong", "displayNameLongWithArticle",
    "displayNameIsOrAre", "entityNamePrefix", "personNamePrefix", "personNamePrefixAOrAn", "shipNamePrefix", "showInIntelTab",
    "fleetTypeNames", "ranks"})
_CALLS = {"getFaction", "addParticipatingFaction"}


def _faction_lists() -> dict[str, str]:
    """save_doctor's FACTION_LISTS, imported late: save_doctor imports the scanner."""
    from bridgeforge.save.save_doctor import FACTION_LISTS

    return FACTION_LISTS


def _strings(value: object) -> list[str]:
    """The strings of a JSON list. Anything else names nothing: a bare string is not split into letters (review 2026-11-20)."""
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def _keys(value: object) -> list[str]:
    """The keys of a JSON object (an id -> weight map); anything else names nothing."""
    return [k for k in value if isinstance(k, str)] if isinstance(value, dict) else []


def _listed(faction: dict) -> tuple[list[tuple[str, str]], list[str]]:
    """([(kind, id)] the content lists, weight maps and ship roles name, [tags])."""
    ids, tags = [], []
    for key, kind in _faction_lists().items():
        block = faction.get(key)
        if isinstance(block, dict):
            ids += [(kind, i) for i in _strings(block.get(LIST_FIELD[kind]))]
            tags += _strings(block.get("tags"))
    for key, kind in SELL_LISTS.items():
        ids += [(kind, i) for i in _keys(faction.get(key))]
    frequency = faction.get("hullFrequency")
    if isinstance(frequency, dict):
        ids += [("hull", i) for i in _keys(frequency.get("hulls"))]
        tags += _keys(frequency.get("tags"))
    roles = faction.get("shipRoles")
    for role, block in (roles.items() if isinstance(roles, dict) else []):
        if role not in ROLE_SKIPPED:
            ids += [("wing" if i.endswith("_wing") else "variant", i) for i in _keys(block) if i not in ROLE_NOT_VARIANTS]
    return sorted(set(ids)), sorted(set(tags))


# The keys this module reads besides the content lists (`_faction_lists()`).
READ_KEYS = frozenset({*SELL_LISTS, "hullFrequency", "shipRoles", "illegalCommodities", "logo", "crest", "portraits"})


def _shape_read(key: str, value: object) -> bool:
    """Whether a key this module reads holds the shape it reads. Another shape is a suspect, not a silent skip (review
    2026-11-20): `"shipRoles": [...]` or a `hullFrequency` key besides `hulls` and `tags` would otherwise name nothing."""
    lists = _faction_lists()
    if key in lists:
        allowed = (LIST_FIELD[lists[key]], "tags")
        return isinstance(value, dict) and all(k in allowed and isinstance(v, list) for k, v in value.items())
    if key == "hullFrequency":
        return isinstance(value, dict) and all(k in ("hulls", "tags") and isinstance(v, dict) for k, v in value.items())
    if key in ("shipRoles", "portraits"):
        inner = dict if key == "shipRoles" else list
        return isinstance(value, dict) and all(isinstance(v, inner) for v in value.values())
    expected = {"illegalCommodities": list, "logo": str, "crest": str}.get(key, dict)  # the sell maps are objects
    return isinstance(value, expected)


def _leaves(value: object) -> set[str]:
    """The strings a value may name: string leaves, and the keys of id -> weight maps (all values numbers)."""
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        return set().union(*(_leaves(v) for v in value)) if value else set()
    if isinstance(value, dict):
        weights = bool(value) and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value.values())
        found = {k for k in value if isinstance(k, str)} if weights else set()
        return found.union(*(_leaves(v) for v in value.values()))
    return set()


def _unread(path: str, faction: dict) -> list[dict]:
    """One suspect per key that is neither read nor plain, or is read but in another shape (advisor 2026-11-20: never
    dropped). A key whose value holds no string names no id, so it is no suspect (review 2026-11-20)."""
    from bridgeforge.genome.closure import pointer

    read = READ_KEYS | set(_faction_lists())
    suspects = []
    for key in sorted(faction):
        if key in PLAIN_KEYS or (key in read and _shape_read(key, faction[key])):
            continue
        mentions = sorted(_leaves(faction[key]))
        if mentions:
            what = "is not in the shape this describe reads" if key in read else \
                "may name ids (sounds, name sets, voices, skills, station hulls) this describe does not type"
            suspects.append({"path": f"{path}#{pointer(key)}", "mentions": mentions, "reason": f"the faction's `{key}` {what}"})
    return suspects


def _commodities(root: Path, core_root: Path, faction: dict, path: str) -> tuple[list[str], list[str], list[dict]]:
    """(vanilla needs, missing, suspects) for `illegalCommodities`: the core's are `commodity:` needs; a commodity the mod
    defines is a suspect (a commodity is not a gene kind yet); one neither defines is missing."""
    from bridgeforge.genome.gene import _rows

    listed = sorted(set(_strings(faction.get("illegalCommodities"))))
    core, own = set(_rows(core_root, COMMODITIES_CSV)), set(_rows(root, COMMODITIES_CSV))
    vanilla = [f"commodity:{c}" for c in listed if c in core]
    mine = [c for c in listed if c not in core and c in own]
    missing = [f"commodity:{c} (an illegal commodity of the faction; neither the mod nor the core defines it)" for c in listed
               if c not in core and c not in own]
    suspects = ([{"path": f"{path}#/illegalCommodities", "mentions": mine,
                  "reason": "commodities the mod defines: a commodity is not a gene kind yet"}] if mine else [])
    return vanilla, missing, suspects


def _files_named(root: Path, core_root: Path, faction: dict) -> tuple[list[str], list[str], list[str]]:
    """(mod files, core files, paths in neither) that the logo, crest and portraits name. A path must stay inside its folder:
    `../other_mod/x.png`, an absolute path or a backslash path is in neither (review 2026-11-20)."""
    from bridgeforge.genome.campaign import _inside_file

    values = [faction.get("logo"), faction.get("crest")]
    portraits = faction.get("portraits")
    for group in (portraits.values() if isinstance(portraits, dict) else []):
        values += _strings(group)
    mine, core, absent = set(), set(), set()
    for value in (v.strip() for v in values if isinstance(v, str) and v.strip()):
        found = _inside_file(root, value)
        in_core = None if found else _inside_file(core_root, value)
        if found:
            mine.add(found)
        elif in_core:
            core.add(in_core)
        else:
            absent.add(value)
    return sorted(mine), sorted(core), sorted(absent)


def _jar_entry(root: Path, jar: object, member: str) -> str:
    """`<jar, relative to the mod>!<entry>`, the form vendor-plan and the closure give a class (a dependent check skips it)."""
    try:
        return f"{Path(jar).resolve().relative_to(root.resolve()).as_posix()}!{member}"
    except ValueError:
        return f"{Path(jar).name}!{member}"


def _registrations(root: Path, ident: str) -> tuple[list[dict], list[dict]]:
    """(elements for each call site passing `ident` to getFaction/addParticipatingFaction, setRelationship suspects)."""
    import struct

    from bridgeforge.atlas.atlas_classfile import ClassFormatError, iter_method_code, last_argument_constants
    from bridgeforge.genome.campaign import _reach
    from bridgeforge.genome.census import _mod_classes
    from bridgeforge.scan.scan_classfile import _loaded_mod_jars, iter_class_files_in_jars

    plugin_name = (read_mod_info(root) or {}).get("modPlugin")
    plugin = plugin_name.strip().replace(".", "/") if isinstance(plugin_name, str) else ""
    reached = _reach(_mod_classes(root), plugin)
    elements, notes = [], []
    for jar, member, data in iter_class_files_in_jars(_loaded_mod_jars(root)):
        try:
            methods = iter_method_code(data)
        except ClassFormatError:
            continue
        for owner, method, code, pool, params in methods:
            try:
                calls = last_argument_constants(code, pool, lambda _o, name, _d: name in _CALLS or name == "setRelationship", params)
            except (ClassFormatError, struct.error, IndexError, KeyError):
                continue
            named = sorted({name for _o, name, _d, constant in calls if name in _CALLS and constant == ident})
            if named:
                locus = f"{owner.replace('/', '.')}.{method}"
                elements.append({"locus": locus, "statement": f"{', '.join(named)}(\"{ident}\")",
                                 "hooks": sorted(set(reached.get((owner, method), [])))})
                if any(name == "setRelationship" for _o, name, _d, _c in calls):
                    notes.append({"path": _jar_entry(root, jar, member), "mentions": [ident],
                                  "reason": f"{locus} also calls setRelationship: which faction's relations it sets is not tracked"})
    return sorted(elements, key=lambda e: e["locus"]), sorted(notes, key=lambda n: n["reason"])


DESCRIPTIONS_CSV = "data/strings/descriptions.csv"


def _description(root: Path, ident: str) -> tuple[dict | None, dict | None]:
    """(member, suspect) for the faction's FACTION row in descriptions.csv. The intel screen reads it:
    `SelectedFactionInfo` calls `SpecStore.super(faction.getId(), Description.Type.FACTION)` (javap RC7 2026-11-22; a
    code-set `descIdOverride` is read the same way and is not followed). A csv-row path names the first row with an id, so
    when that row has another type the FACTION row cannot be a member: it is a suspect (94.G2 slice 16)."""
    from bridgeforge.game_csv import game_rows

    rows = [row for row in game_rows(root / DESCRIPTIONS_CSV) or [] if (row.get("id") or "").strip() == ident]
    if not any((row.get("type") or "").strip() == "FACTION" for row in rows):
        return None, None
    if (rows[0].get("type") or "").strip() != "FACTION":
        return None, {"path": DESCRIPTIONS_CSV, "mentions": [ident], "reason": "the faction's FACTION description follows a "
                      "row of another type with the same id; a csv-row member names only the first"}
    return {**_row_member(root, f"{DESCRIPTIONS_CSV} [{ident}]"), "reason": "the faction's description (intel screen)"}, None


def describe_faction(mod: Path, ident: str, vanilla_core: Path | None, policy_path: Path | None = None) -> dict:
    """The gene manifest of `faction:<ident>`."""
    from bridgeforge.genome.campaign import _CampaignIndex, _json_object
    from bridgeforge.substitutes import revival_licence
    from bridgeforge.vendor_plan import KINDS, _Index, _mod_root

    root = _mod_root(mod)
    own = _CampaignIndex(root)
    if ident not in own.factions:
        raise GeneError(f"faction:{ident}: {root} ships no .faction file with that id")
    if not vanilla_core:  # without the core a merge fragment would pass for a gene (review 2026-11-20)
        raise GeneError(f"faction:{ident}: give --vanilla-core, which tells a new faction from a core one the mod merges into")
    core_root = Path(vanilla_core).expanduser().resolve()
    if ident in _CampaignIndex(core_root).factions:
        raise GeneError(f"faction:{ident} is a core faction: the mod's file merges into it, so it is not a gene")
    path = own.factions[ident]
    faction = _json_object(root / path)
    members = [_file_member(root, path)]
    missing = []
    try:
        members.append({**_row_member(root, f"{FACTIONS_CSV} [{path}]"), "reason": "the faction's registration in factions.csv"})
    except GeneError:
        missing.append(f"{FACTIONS_CSV} row for {path} (the game loads a .faction only when factions.csv lists it)")
    description, description_suspect = _description(root, ident)
    members += [description] if description else []
    files, core_files, absent = _files_named(root, core_root, faction)
    members += [{**_file_member(root, f), "reason": "a file the faction names (logo, crest, portraits)"} for f in files]
    mod_index, core_index = _Index(root), _Index(core_root)
    genes, vanilla = [], []
    listed, tags = _listed(faction)
    for kind, item in listed:
        if kind not in KINDS:
            continue
        if mod_index.defines(kind, item):
            genes.append(f"{kind}:{item}")
        elif core_index.defines(kind, item):
            vanilla.append(f"{kind}:{item}")
        else:
            missing.append(f"{kind}:{item} (listed by the faction; neither the mod nor the core defines it)")
    vanilla += [f"file:{f}" for f in core_files]
    missing += [f"file:{f} (named by the faction; in neither the mod nor the core)" for f in absent]
    commodity_needs, commodity_missing, commodity_suspects = _commodities(root, core_root, faction, path)
    vanilla += commodity_needs
    missing += commodity_missing
    registrations, notes = _registrations(root, ident)
    suspects = ([{"path": path, "mentions": tags, "reason": "the faction's lists name tags: sets of hulls, weapons or wings, "
                  "recorded and not expanded"}] if tags else [])
    suspects += commodity_suspects + _unread(path, faction) + notes + ([description_suspect] if description_suspect else [])
    members.sort(key=lambda m: (m["what"], m["path"]))
    info = read_mod_info(root) or {}
    licence = _licence(revival_licence(info.get("id"), info.get("name"), policy_path), info, [m["path"] for m in members], policy_path)
    anchor = f"faction:{ident}"
    gene = {
        "schema": GENE_SCHEMA, "schema_version": GENE_SCHEMA_VERSION, "identity": identity("faction", members),
        "kind": "faction", "anchors": [anchor], "provides": [anchor], "members": members,
        "needs": {"vanilla": sorted(set(vanilla)), "mods": [], "genes": sorted(set(genes))},
        "registrations": registrations, "conditions": [],
        "persistent_state": [{"name": f"faction {ident}", "via": "saved with its content lists (RC8_BEHAVIOUR RC8-43)"}],
        "build": {"game_version": info.get("gameVersion"), "mod_version": _version_text(info.get("version"))},
        "provenance": {"mod_id": info.get("id"), "mod_name": info.get("name"), "author": info.get("author")},
        "derived_from": None, "licence": licence, "phenotype_obligations": list(PHENOTYPE["faction"]),
        "unknowns": {"missing": missing, "suspects": suspects}, "collected_from": ["faction-file"],
    }
    problems = validate(gene)
    if problems:
        raise GeneError(f"the manifest does not meet schema {GENE_SCHEMA_VERSION}: " + "; ".join(problems))
    return gene


__all__ = ["FACTIONS_CSV", "describe_faction"]
