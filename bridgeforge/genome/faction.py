"""94.G2 slice 10: faction genes, described (2026-11-20). P3's star system needs `faction:EridaniCombine`.

**Boundary (advisor 2026-11-20, inside schema 4).** `faction:<id>` is a `.faction` file the mod ships whose id the core lacks;
a mod's file for a core faction id is a merge fragment, not a gene, and is refused by name. Members:
- the `.faction` file whole: identity then covers its lists, so a faction knowing one more ship is a new allele (element-level
  membership would need the array member kind schema 4 refuses: a recorded choice);
- its `data/world/factions/factions.csv` row, keyed by the table's `faction` column (RC7's SpecStore reads the table with
  that key: javap 2026-11-20), the registration that makes the game load the file;
- the mod files its scalar keys name (`logo`, `crest`, the `portraits` lists).

**Needs.** Each id the content lists name (`save_doctor.FACTION_LISTS`, and the sell-frequency maps): one the mod defines is
`needs.genes` (`hull:x`, `weapon:x`, `wing:x`, `hullmod:x`, each a gene of its own: the faction carries none of them), one the
core defines is `needs.vanilla`, one neither defines is missing, never dropped. Tags name sets (`tritachyon`, a mod's
blueprint tag): recorded as suspects, not expanded. Eridani's faction needs 54 of the mod's own content genes (measured).

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
LIST_FIELD = {"hull": "hulls", "weapon": "weapons", "wing": "fighters", "hullmod": "hullMods"}
SELL_LISTS = {"weaponSellFrequency": "weapon", "fighterSellFrequency": "wing", "hullmodSellFrequency": "hullmod"}
_CALLS = {"getFaction", "addParticipatingFaction"}


def _strings(value: object) -> list[str]:
    """The strings of a JSON list. Anything else names nothing: a bare string is not split into letters (review 2026-11-20)."""
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def _listed(faction: dict) -> tuple[list[tuple[str, str]], list[str]]:
    """([(kind, id)] the content lists and sell maps name, [tags])."""
    from bridgeforge.save.save_doctor import FACTION_LISTS

    ids, tags = [], []
    for key, kind in FACTION_LISTS.items():
        block = faction.get(key)
        if isinstance(block, dict):
            ids += [(kind, i) for i in _strings(block.get(LIST_FIELD[kind]))]
            tags += _strings(block.get("tags"))
    for key, kind in SELL_LISTS.items():
        block = faction.get(key)
        ids += [(kind, i) for i in (block if isinstance(block, dict) else {}) if isinstance(i, str)]
    return sorted(set(ids)), sorted(set(tags))


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
    registrations, notes = _registrations(root, ident)
    suspects = ([{"path": path, "mentions": tags, "reason": "the faction's lists name tags: sets of hulls, weapons or wings, "
                  "recorded and not expanded"}] if tags else [])
    suspects += notes
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
