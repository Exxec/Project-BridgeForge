"""94.G1: the gene contract and identity, read-only (docs/FEATURE_GENOME_ROADMAP.md sections 2 and 6, WP1).

A gene is the minimal closed set of parts that gives one player-observable capability. `describe(mod, "kind:id")` writes
its manifest, `gene.json` schema 3, from `vendor-plan`'s closure: the six content kinds it covers (hull mod, weapon, wing,
hull, variant, ship system). Campaign features, registration slicing and the archaeology fields (registrations,
conditions, persistent state) came with G2: since slice 15 `conditions` holds the ids a gene's code only checks for
(`checks-for`, closure.mention_findings). Schema 2 fixed the shape of each element before a sister repository pinned the
contract (advisor review 2026-11-19):
- a registration is `{locus, statement}`: where the gene is registered (a member path, or `Class#method`) and what it adds;
- a condition is `{kind, subject}`: what must hold for the gene to exist (`mod-enabled` / `nexerelin`, a setting key);
- a persistent-state entry is `{name, via}`: a class or key that reaches saves, and how (`xstream`, `memory`, ...).
Each element may carry more fields; only these are required, so G2 can add detail without a new schema version.

`derived_from` is null for a gene described from its mod, or `{identity, by, from_build}` for one that G4 adapted: the
identity it came from, the fixer or packet that changed it, and the build it was adapted from. Adapting changes the
members' bytes, so it changes the identity; this field keeps the lineage. Like provenance and licence, it is not part of
the identity.

`licence` is the licence ledger's answer (94.G1 WP4): `mod_decision` for the whole mod, `local_only_members` for the
members a local-only path exception covers, and `decision`, which is LOCAL_ONLY whenever that list is not empty.

Schema 4 (94.G2, 2026-11-19) names every kind G2 needs (`GENE_KINDS`); `describe` closes the content kinds and
`combat-plugin` and, since P3 (2026-11-20), `star-system` (genome/campaign.py), and refuses the rest until their pilot.
`needs.genes` (P3, additive within schema 4: optional, so earlier manifests stay valid) lists the genes of the same
donor this one needs and does not carry, such as a star system's owning faction. Schema 3 (the same day) added one member kind, `json-entry`: a key of a JSON file, `<file>#<JSON Pointer>` such as
`data/config/settings.json#/sa_lobster_tanks_growth_rate`, hashed as its parsed value in canonical JSON (genome/closure.py).
For now only object keys: a pointer ending in an array index or `-` is refused, and array membership (a hull added to a
list) stays an unknown until a pilot needs it. Schemas 1-3 are withdrawn; no sister repository had pinned any.

Identity is the SHA-256 of the kind and the normalized members, so the same feature copied into another mod or another
folder gets the same identity (one allele): a text file's line endings are normalized, a CSV row is its non-empty cells,
a class is its bytes. Paths of the machine, dates and the mod's own name are not part of it.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import zipfile
from pathlib import Path

from bridgeforge.file_hash import sha256_file
from bridgeforge.mod_files import read_mod_info
from bridgeforge.vendor_plan import _TEXT_SUFFIXES, KINDS, _rows, vendor_plan
from bridgeforge.zipsafe import MAX_CLASS_BYTES, read_limited

GENE_SCHEMA = "bridgeforge-gene"
GENE_SCHEMA_VERSION = 4
WITHDRAWN_VERSIONS = (1, 2, 3)  # the one list: contract.py and evidence.py import it
MEMBER_KINDS = ("file", "csv-row", "jar-class", "json-entry")
# Schema 4 (94.G2, 2026-11-19): every kind G2 needs, so G2 needs no further bump (advisor review). Kinds are named by how the
# game registers them. `describe` closes the content kinds and `combat-plugin` (a key of settings.json's `plugins` map);
# the others are refused with a clear message until their pilot closes them.
CAMPAIGN_KINDS = ("faction", "star-system", "market", "industry", "condition", "ability", "rule", "combat-plugin",
                  "campaign-plugin", "custom-start")
GENE_KINDS = (*KINDS, *CAMPAIGN_KINDS)
CLOSABLE_KINDS = (*KINDS, "combat-plugin", "star-system", "faction")
COLLECTED_FROM = ["vendor-plan"]
# What the player sees each kind do: the phenotype a live run must observe (S3 makes these real obligations, G6).
PHENOTYPE = {
    "hull": ["the hull spawns in a fleet and enters combat"],
    "variant": ["the variant loads with its hull and fits"],
    "weapon": ["the weapon fires in combat"],
    "wing": ["the wing launches from a carrier in combat"],
    "hullmod": ["the hull mod applies to a ship and shows its effect"],
    "shipsystem": ["the ship system activates in combat"],
    "faction": ["the faction is listed and its fleets spawn"],
    "star-system": ["the star system generates once in a new sector"],
    "market": ["the market exists and opens its trade dialog"],
    "industry": ["the industry is on its market and applies its effect"],
    "condition": ["the market condition applies to its market"],
    "ability": ["the ability is available and activates"],
    "rule": ["the dialog option appears and its script runs"],
    "combat-plugin": ["the combat plugin runs in combat and its effect is seen"],
    "campaign-plugin": ["the campaign plugin runs and its effect is seen"],
    "custom-start": ["the custom start is offered and starts a game"],
}
REQUIRED_KEYS = ("schema", "schema_version", "identity", "kind", "anchors", "provides", "members", "needs", "registrations",
                 "conditions", "persistent_state", "build", "provenance", "derived_from", "licence", "phenotype_obligations",
                 "unknowns", "collected_from")
# The fields each archaeology element must carry (schema 2); an element may carry more.
ELEMENT_FIELDS = {"registrations": ("locus", "statement"), "conditions": ("kind", "subject"), "persistent_state": ("name", "via")}
DERIVED_FIELDS = ("identity", "by", "from_build")


class GeneError(ValueError):
    """A malformed anchor, a mod folder that is not one, or a closure that names no part."""


MAX_TEXT_BYTES = 64 * 1024 * 1024  # a text member larger than this is refused, not read whole (untrusted mod files)


def _normalized_text(data: bytes) -> bytes:
    """The same text whatever the editor did: no UTF-8 BOM, LF line ends, no trailing spaces or tabs, no trailing blank lines."""
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    lines = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n").split(b"\n")
    return b"\n".join(line.rstrip(b" \t") for line in lines).rstrip(b"\n")


def _file_member(root: Path, relative: str) -> dict:
    path = root / relative
    if Path(relative).suffix.lower() in _TEXT_SUFFIXES:
        if path.stat().st_size > MAX_TEXT_BYTES:
            raise GeneError(f"{relative} is over {MAX_TEXT_BYTES // (1024 * 1024)} MB; not a text member a gene can carry")
        digest = hashlib.sha256(_normalized_text(path.read_bytes())).hexdigest()
    else:
        digest = sha256_file(path)
    return {"what": "file", "path": relative, "sha256": digest}


# The column a table's rows are keyed by, when it is not `id`: RC7's SpecStore reads factions.csv through LoadingUtils with the
# key `faction`, the .faction file's path (javap of com.fs.starfarer.loading.SpecStore, 2026-11-20).
TABLE_KEYS = {"data/world/factions/factions.csv": "faction"}


def keyed_rows(root: Path, table: str) -> dict[str, dict[str, str]]:
    """{key: row} for `table`, keyed by its key column (TABLE_KEYS, else `id`)."""
    key = TABLE_KEYS.get(table)
    if key is None:
        return _rows(root, table)
    from bridgeforge.vendor_plan import _read_csv_rows_lenient

    rows: dict[str, dict[str, str]] = {}
    for row in _read_csv_rows_lenient(Path(root) / table) or []:
        value = (row.get(key) or "").strip()
        if value and not value.startswith("#"):
            rows.setdefault(value, row)
    return rows


def _row_member(root: Path, entry_path: str) -> dict:
    table, _, rest = entry_path.partition(" [")
    ident = rest.rstrip("]")
    row = keyed_rows(root, table).get(ident)
    if row is None:
        raise GeneError(f"{table} has no row {ident!r} although the closure names it")
    # Only named, non-empty cells, trimmed: cells past the header (DictReader's None key) are not part of the row the game reads.
    cells = {column.strip(): value.strip() for column, value in row.items()
             if isinstance(column, str) and column.strip() and isinstance(value, str) and value.strip()}
    return {"what": "csv-row", "path": entry_path, "sha256": hashlib.sha256(json.dumps(cells, sort_keys=True).encode("utf-8")).hexdigest()}


def _plain_files(root: Path, name: str) -> list[Path]:
    """Files called exactly `name` under `root`, not following links or junctions out of the mod."""
    found = []
    for folder, folders, files in os.walk(root):
        folders[:] = sorted(d for d in folders if not (Path(folder, d).is_symlink() or Path(folder, d).is_junction()))
        found += [Path(folder, f) for f in files if f == name and not Path(folder, f).is_symlink()]
    return sorted(found, key=lambda path: path.relative_to(root).as_posix())


def _jar_member(root: Path, member: str) -> dict:
    """A class in one of the mod's jars, named by the jar's path in the mod: two jars of one name stay apart."""
    jar_name, _, entry = member.partition("!")
    for jar in _plain_files(root, jar_name):
        try:
            with zipfile.ZipFile(jar) as archive:
                if entry not in archive.namelist():
                    continue
                data = read_limited(archive, entry, MAX_CLASS_BYTES)
        except (OSError, zipfile.BadZipFile, ValueError):
            continue  # an unreadable or oversized jar is not this member's home
        relative = f"{jar.relative_to(root).as_posix()}!{entry}"
        return {"what": "jar-class", "path": relative, "sha256": hashlib.sha256(data).hexdigest()}
    raise GeneError(f"{member}: the jar entry the closure names was not found in a readable jar of the mod")


_PACKAGE_DECL = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.MULTILINE)


def _loaded_classes(root: Path) -> dict[str, str]:
    """{entry `a/B.class`: the loaded jar's path in the mod} for the jars the game loads (a jar class beats a loose script)."""
    from bridgeforge.scan.scan_classfile import _loaded_mod_jars, iter_class_files_in_jars

    found: dict[str, str] = {}
    for jar, member, _data in iter_class_files_in_jars(_loaded_mod_jars(root)):  # the canonical walk (WP6)
        found.setdefault(member, Path(jar).relative_to(root).as_posix())
    return found


def _loaded_member(root: Path, entry: dict, loaded: dict[str, str]) -> dict | None:
    """What the game loads for a `.java` vendor-plan names (94.G2, P2 2026-11-19): the class from a loaded jar when one has
    it; else the file, only when it sits at its package path (the loose-script loader resolves `a.b.C` to `a/b/C.java`);
    else nothing. vendor-plan prefers the source on purpose (RevenantLib rebuilds from it); a gene names what runs."""
    path = entry["path"]
    text = (root / path).read_text(encoding="utf-8-sig", errors="replace")
    package = _PACKAGE_DECL.search(text)
    stem = Path(path).stem
    expected = (package.group(1).replace(".", "/") + "/" if package else "") + stem
    if f"{expected}.class" in loaded:
        member = _jar_member(root, f"{Path(loaded[expected + '.class']).name}!{expected}.class")
        return {**member, "reason": f"{entry['reason']}; the game loads the jar class (source {path} is not a member)"}
    if path == f"{expected}.java":
        return _file_member(root, path)
    return None


def identity(kind: str, members: list[dict]) -> str:
    """The gene's identity: the kind and its members (what, path, content hash), in a fixed order."""
    lines = [f"{kind}\n"] + [f"{m['what']}\t{m['path']}\t{m['sha256']}\n" for m in sorted(members, key=lambda m: (m["what"], m["path"]))]
    return hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()


def describe(mod: Path, anchor: str, *, vanilla_core: Path | None = None, policy_path: Path | None = None) -> dict:
    """The gene manifest for one content piece (`kind:id`) of a mod folder or workspace."""
    kind, _, ident = anchor.partition(":")
    if kind not in GENE_KINDS or not ident:
        raise GeneError(f"a gene anchor is kind:id with kind one of {', '.join(GENE_KINDS)}; got {anchor!r}")
    if kind not in CLOSABLE_KINDS:
        raise GeneError(f"{kind} genes cannot be closed yet: G2 adds each campaign kind with its pilot "
                        f"(closable now: {', '.join(CLOSABLE_KINDS)})")
    if kind == "faction":
        from bridgeforge.genome.faction import describe_faction

        return describe_faction(mod, ident, vanilla_core, policy_path)  # 94.G2 slice 10: the file, its row, its lists as needs
    registration, system = None, None
    seeds, classes = ([], [])
    if kind == "combat-plugin":
        plugin_class, registration = _combat_plugin(mod, ident)
        classes = [plugin_class]
    elif kind == "star-system":
        from bridgeforge.genome.campaign import star_system

        system = star_system(mod, ident)  # 94.G2 P3: the generator class; its call sites are elements, not members
        classes = [system["generator"]]
    else:
        seeds = [anchor]
    plan, campaign = _closed_plan(mod, anchor, seeds, classes, vanilla_core, policy_path)
    root = Path(plan["provider"])
    if kind not in ("combat-plugin", "star-system") and anchor not in plan["closure_ids"]:
        raise GeneError(f"{anchor} is not defined by {root} (missing: {', '.join(plan['missing']) or 'nothing'})")
    members = ([registration["member"]] if registration else []) + campaign["members"]
    loaded = _loaded_classes(root)
    missing_classes = []
    for entry in plan["include"]:
        if entry["what"] == "file" and entry["path"].endswith(".java"):
            member = _loaded_member(root, entry, loaded)
            if member is None:
                missing_classes.append(f"class source {entry['path']} ({entry['reason']}): not at its package path and in no "
                                       "loaded jar, so the game never loads it")
                continue
        elif entry["what"] == "file":
            member = _file_member(root, entry["path"])
        elif entry["what"] == "csv-row":
            member = _row_member(root, entry["path"])
        elif entry["what"] == "jar-class":
            member = _jar_member(root, entry["path"])
        else:
            raise GeneError(f"vendor-plan named a part of an unknown kind: {entry['what']!r}")
        members.append({**member, "reason": member.pop("reason", None) or entry["reason"]})
    members = list({(m["what"], m["path"]): m for m in members}.values())  # a jar class reached twice is one member
    from bridgeforge.genome.closure import SETTINGS_FILE, extend, mods_needed

    extra = extend(root, members, vanilla_core, [closure_id.split(":", 1)[1] for closure_id in plan["closure_ids"]])
    members += extra["members"]
    members.sort(key=lambda m: (m["what"], m["path"]))
    # The whole-file settings.json SUSPECT is replaced by key-level ones (a key no member reads), or by nothing.
    from bridgeforge.genome.closure import mention_findings

    mentioned, conditions = mention_findings(root, _code_members(root, plan), vanilla_core,
                                             {p.split(":", 1)[1] for p in {anchor, *plan["closure_ids"], *campaign["provides"]}})
    suspects = ([s for s in plan["suspects"] if s["path"] != SETTINGS_FILE] + extra["suspects"] + campaign["suspects"]
                + (system["suspects"] if system else []) + mentioned)
    info = read_mod_info(root) or {}
    licence = _licence(plan["licence"], info, [m["path"] for m in members], policy_path)
    dependencies = sorted(d["id"] for d in info.get("dependencies") or [] if isinstance(d, dict) and isinstance(d.get("id"), str))
    registrations = [registration["element"]] if registration else system["registrations"] if system else []
    gene = {
        "schema": GENE_SCHEMA, "schema_version": GENE_SCHEMA_VERSION,
        "identity": identity(kind, members),
        "kind": kind, "anchors": [anchor], "provides": sorted({anchor, *plan["closure_ids"], *campaign["provides"]}),
        "members": members,
        "needs": {"vanilla": sorted(set(plan["provided_by_vanilla"]) | set(extra["vanilla"]) | set(campaign["vanilla"])),
                  "mods": mods_needed(root, members, dependencies),
                  "genes": [g for g in campaign["genes"] if g != anchor]},
        "registrations": registrations, "conditions": conditions, "persistent_state": _saved_state(system, campaign, members),
        "build": {"game_version": info.get("gameVersion"), "mod_version": _version_text(info.get("version"))},
        "provenance": {"mod_id": info.get("id"), "mod_name": info.get("name"), "author": info.get("author")},
        "derived_from": None,
        "licence": licence,
        "phenotype_obligations": list(PHENOTYPE[kind]),
        "unknowns": {"missing": plan["missing"] + missing_classes + extra["missing"], "suspects": suspects},
        "collected_from": list(COLLECTED_FROM),
    }
    problems = validate(gene)
    if problems:
        raise GeneError(f"the manifest does not meet schema {GENE_SCHEMA_VERSION}: " + "; ".join(problems))
    return gene


def _closed_plan(mod: Path, anchor: str, seeds: list[str], classes: list[str], vanilla_core: Path | None,
                 policy_path: Path | None) -> tuple[dict, dict]:
    """vendor-plan's closure, run again until the gene's code names nothing new: content ids its literals name (94.G2: a
    combat plugin's spawned variants are its gene) and the classes the campaign rows it names point at (P3: an industry's
    plugin). Returns the plan and the campaign ids of its final code (`campaign.campaign_ids`)."""
    from bridgeforge.genome.campaign import campaign_ids
    from bridgeforge.genome.closure import ids_named_by_code

    plan = vendor_plan(mod, seeds, vanilla_core=vanilla_core, policy_path=policy_path, classes=classes)
    for _round in range(8):
        root = Path(plan["provider"])
        code = _code_members(root, plan)
        named = [i for i in ids_named_by_code(root, code, vanilla_core) if i not in seeds and i != anchor]
        campaign = campaign_ids(root, code, vanilla_core)
        more = [c for c in campaign["classes"] if c not in classes]
        if not named and not more:
            return plan, campaign
        seeds, classes = sorted({*seeds, *named}), [*classes, *more]
        plan = vendor_plan(mod, seeds, vanilla_core=vanilla_core, policy_path=policy_path, classes=classes)
    root = Path(plan["provider"])
    campaign = campaign_ids(root, _code_members(root, plan), vanilla_core)
    campaign["suspects"].append({"path": anchor, "mentions": [], "reason": "the closure still named new ids or classes "
                                 "after 8 rounds: it may be incomplete"})
    return plan, campaign


def _saved_state(system: dict | None, campaign: dict, members: list[dict]) -> list[dict]:
    """What the gene leaves in a save: a star system and its markets, and each industry it owns, saved by class name with
    every market that has it (removing the gene then breaks such a save). Evidence, Test1 rig save LeonardCallisto
    (G1R-LIVE-0985a-20261117, Eridani enabled), read 2026-11-20: `<cL cl="Sstm" ... bN="Pantheon">`, `<Market><id>
    ECE_planet3_market</id>`, and `<data.scripts.campaign.ECE__PlanetaryCommandCenter id="ECE_PlanetaryCommandCenter">`
    inside the market's `<industries>` (XStream writes `_` in a class name as `__`)."""
    state = list(system["persistent_state"]) if system else []
    rows = {m["path"] for m in members if m["what"] == "csv-row"}
    for ident in campaign["industries"]:
        if f"data/campaign/industries.csv [{ident}]" in rows:
            state.append({"name": f"industry {ident}",
                          "via": "its plugin class, saved by class name as an element of every market's industries"})
    return state


def _code_members(root: Path, plan: dict) -> list[dict]:
    """The code a plan names, as the members the game loads (a jar class beats its source)."""
    loaded = _loaded_classes(root)
    found = []
    for entry in plan["include"]:
        if entry["what"] == "file" and entry["path"].endswith(".java"):
            member = _loaded_member(root, entry, loaded)
            if member is not None:
                found.append(member)
        elif entry["what"] == "jar-class":
            # vendor-plan names a jar class by the jar's file name (`x.jar!a/B.class`); the readers open it from the mod root,
            # so resolve the jar's path in the mod. Before P3 (2026-11-20) a class with no source under src/ was skipped
            # silently and its literals named nothing.
            found.append(_jar_member(root, entry["path"]))
    return found


def _combat_plugin(mod: Path, key: str) -> tuple[str, dict]:
    """(the plugin's class, its registration) for `combat-plugin:<key>`: the key of settings.json's `plugins` map."""
    from bridgeforge.genome.closure import SETTINGS_FILE, _settings, pointer, value_sha256
    from bridgeforge.vendor_plan import _mod_root

    root = _mod_root(mod)
    plugins = _settings(root).get("plugins")
    plugin_class = plugins.get(key) if isinstance(plugins, dict) else None
    if not isinstance(plugin_class, str) or not plugin_class.strip():
        raise GeneError(f"combat-plugin:{key}: {root / SETTINGS_FILE} registers no plugin under that key in its plugins map")
    path = f"{SETTINGS_FILE}#/plugins{pointer(key)}"
    member = {"what": "json-entry", "path": path, "sha256": value_sha256(plugin_class),
              "reason": "the plugin's registration in settings.json's plugins map"}
    return plugin_class.strip(), {"member": member, "element": {"locus": path, "statement": plugin_class.strip()}}


def _licence(mod_licence: dict, info: dict, member_paths: list[str], policy_path: Path | None) -> dict:
    """The gene's licence from the ledger: the mod's decision, narrowed to LOCAL_ONLY when a member is under a local-only path."""
    from bridgeforge.licence_ledger import local_only_paths

    restricted = local_only_paths(info.get("id"), info.get("name"), member_paths, policy_path)
    if not restricted:
        return {"decision": mod_licence["decision"], "reason": mod_licence.get("reason"), "mod_decision": mod_licence["decision"],
                "local_only_members": []}
    first = restricted[0]
    return {"decision": "LOCAL_ONLY",
            "reason": f"{len(restricted)} member(s) under local-only paths, first {first['path']} ({first['prefix']}: {first['reason']})",
            "mod_decision": mod_licence["decision"], "local_only_members": [hit["path"] for hit in restricted]}


def _version_text(version: object) -> str | None:
    if isinstance(version, dict):  # mod_info's {"major", "minor", "patch"} form
        return ".".join(str(version.get(part, 0)) for part in ("major", "minor", "patch"))
    return str(version) if version is not None else None


_HEX64 = frozenset("0123456789abcdef")


def _is_hash(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= _HEX64


def _member_problem(member: object) -> str | None:
    if not isinstance(member, dict):
        return "a member is an object"
    if member.get("what") not in MEMBER_KINDS:
        return f"member kind {member.get('what')!r} is not one of {', '.join(MEMBER_KINDS)}"
    if not isinstance(member.get("path"), str) or not member["path"]:
        return "a member's path is a non-empty string"
    if member["what"] == "json-entry":
        problem = _json_entry_problem(member["path"])
        if problem:
            return problem
    if not _is_hash(member.get("sha256")):
        return f"{member['path']}: sha256 is 64 lowercase hex digits"
    return None


def _json_entry_problem(path: str) -> str | None:
    """A json-entry path is `<file>#<JSON Pointer>` to an object key: the pointer starts with `/` and its last token is
    not an array index or `-` (array membership is not a member kind yet)."""
    file, sep, pointer = path.partition("#")
    if not sep or not file:
        return f"{path}: a json-entry path is <file>#<JSON Pointer>"
    if not pointer.startswith("/"):
        return f"{path}: the JSON Pointer starts with '/'"
    last = pointer.rsplit("/", 1)[-1]
    if last == "-" or last.isdigit():
        return f"{path}: a json-entry points at an object key, not an array element"
    return None


def _element_problem(key: str, element: object) -> str | None:
    fields = ELEMENT_FIELDS[key]
    if not isinstance(element, dict) or not all(isinstance(element.get(f), str) and element[f] for f in fields):
        return f"each of {key} is an object with non-empty strings {', '.join(fields)}"
    return None


def _derived_problem(derived: object) -> str | None:
    if derived is None:
        return None
    if (not isinstance(derived, dict) or not _is_hash(derived.get("identity")) or not isinstance(derived.get("by"), str)
            or not derived["by"] or "from_build" not in derived
            or not (derived["from_build"] is None or isinstance(derived["from_build"], str))):
        return "derived_from is null or {identity: 64 hex digits, by: non-empty string, from_build: string or null}"
    return None


def _licence_problem(licence: object, member_paths: set[str] | None) -> str | None:
    if not isinstance(licence, dict) or not isinstance(licence.get("decision"), str) or not isinstance(licence.get("mod_decision"), str):
        return "licence is an object with a decision and a mod_decision"
    local = licence.get("local_only_members")
    if not isinstance(local, list) or not all(isinstance(path, str) for path in local):
        return "licence.local_only_members is a list of member paths"
    if local and licence["decision"] != "LOCAL_ONLY":
        return "a gene with local-only members has the decision LOCAL_ONLY"
    if member_paths is not None and not set(local) <= member_paths:
        return "licence.local_only_members names a path that is not a member"
    return None


def validate(gene: object) -> list[str]:
    """What keeps `gene` from being a schema-2 manifest; empty when it is one. Sister repositories read these files, so
    every field's shape is checked, and malformed input gives problems, never an exception."""
    if not isinstance(gene, dict):
        return ["a manifest is a JSON object"]
    problems = [f"missing {key}" for key in REQUIRED_KEYS if key not in gene]
    if problems:
        return problems
    version = gene["schema_version"]
    if gene["schema"] != GENE_SCHEMA or type(version) is not int or version != GENE_SCHEMA_VERSION:
        problems.append(f"schema is {gene['schema']!r} {version!r}, not {GENE_SCHEMA!r} {GENE_SCHEMA_VERSION}")
    if gene["kind"] not in GENE_KINDS:
        problems.append(f"kind {gene['kind']!r} is not one of {', '.join(GENE_KINDS)}")
    for key in ("anchors", "provides", "registrations", "conditions", "persistent_state", "phenotype_obligations", "collected_from"):
        if not isinstance(gene[key], list):
            problems.append(f"{key} is a list")
    if isinstance(gene["anchors"], list):
        if not gene["anchors"] or not all(isinstance(a, str) and a.startswith(f"{gene['kind']}:") for a in gene["anchors"]):
            problems.append(f"anchors are one or more '{gene['kind']}:<id>' strings")
    for key, fields in (("needs", ("vanilla", "mods")), ("unknowns", ("missing", "suspects"))):
        value = gene[key]
        if not isinstance(value, dict) or not all(isinstance(value.get(field), list) for field in fields):
            problems.append(f"{key} is an object with lists {', '.join(fields)}")
        elif key == "needs" and "genes" in value and not (
                isinstance(value["genes"], list) and all(isinstance(g, str) and ":" in g for g in value["genes"])):
            problems.append("needs.genes, when present, is a list of 'kind:id' anchors")
    for key in ("build", "provenance"):
        if not isinstance(gene[key], dict):
            problems.append(f"{key} is an object")
    for key in ELEMENT_FIELDS:
        if isinstance(gene[key], list):
            problems += sorted({p for p in (_element_problem(key, e) for e in gene[key]) if p})
    derived = _derived_problem(gene["derived_from"])
    if derived:
        problems.append(derived)
    members = gene["members"]
    member_paths = ({m["path"] for m in members if isinstance(m, dict) and isinstance(m.get("path"), str)}
                    if isinstance(members, list) else None)
    licence = _licence_problem(gene["licence"], member_paths)
    if licence:
        problems.append(licence)
    if not isinstance(members, list) or not members:
        problems.append("members is a non-empty list")
    else:
        member_problems = [p for p in map(_member_problem, members) if p]
        problems += member_problems[:3]
        if not member_problems:
            keys = [(m["what"], m["path"]) for m in members]
            if len(set(keys)) != len(keys):
                problems.append("a member is listed twice")
            if not _is_hash(gene["identity"]) or gene["identity"] != identity(gene["kind"], members):
                problems.append("identity does not match the members")
    return problems


def dumps(gene: dict) -> str:
    return json.dumps(gene, indent=2, ensure_ascii=False) + "\n"


__all__ = ["CLOSABLE_KINDS", "DERIVED_FIELDS", "ELEMENT_FIELDS", "GENE_KINDS", "GENE_SCHEMA", "GENE_SCHEMA_VERSION", "GeneError", "describe", "dumps", "identity",
           "validate"]
