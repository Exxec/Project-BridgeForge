"""94.G1 WP2 (GR-1): the gene.json contract as files a sister repository pins by hash.

`gene contract --write` puts three things in `docs/contracts/gene/`:
- `gene.schema.json`: a JSON Schema (2020-12) of manifest schema 2, for repositories that validate with a library;
- `fixtures/`: manifests every consumer must judge as BridgeForge does: the `valid-*` ones pass, each `invalid-*` one
  fails, and `valid-*` identities must come out equal from the identity rule;
- `CONTRACT.json`: the schema id and version, the identity rule in words, every file's SHA-256 and each fixture's verdict;
- `evidence-header.schema.json` and `evidence/` (WP5): the header every evidence file about a gene carries, versioned apart
  from gene.json, with fixtures judged by `genome.evidence.check` against `fixtures/valid-hullmod.json`.

Schema 1 is withdrawn (2026-11-19, before any sister pinned it); CONTRACT.json says so.

A consumer copies the folder byte for byte and pins CONTRACT.json's SHA-256, as it pins `target export`'s registry; WP3's
cross-repository check reports a pin that no longer matches. `gene contract --check` fails when the committed folder
differs from what this code writes, so the contract cannot drift from `gene.py` without a deliberate rewrite.
"""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path

from bridgeforge.genome.gene import (ELEMENT_FIELDS, GENE_KINDS, GENE_SCHEMA, GENE_SCHEMA_VERSION, MEMBER_KINDS, PHENOTYPE, REQUIRED_KEYS,
                                     WITHDRAWN_VERSIONS, dumps, identity, validate)
from bridgeforge.genome import evidence as evidence_header

CONTRACT_RELATIVE = Path("docs") / "contracts" / "gene"
IDENTITY_RULE = ("identity = SHA-256 (lowercase hex) of the UTF-8 text: the kind and a line feed, then one line per member "
                 "sorted by (what, path): what, TAB, path, TAB, sha256, line feed. A text member's sha256 is of its "
                 "normalized bytes (no UTF-8 BOM, LF line ends, no trailing spaces or tabs, no trailing blank lines); a "
                 "csv-row's is of the JSON object of its named non-empty trimmed cells with sorted keys; a json-entry's is of "
                 "its parsed value as canonical JSON (sorted keys, ',' and ':' separators, UTF-8, integral numbers as "
                 "integers); a jar-class's and any other file's is of its bytes.")

_HASH = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
_STRINGS = {"type": "array", "items": {"type": "string"}}


def json_schema() -> dict:
    """Manifest schema 2 as a JSON Schema. The identity's agreement with the members, and local-only members being members,
    are checked by the identity rule and `validate`, not here. Elements allow more fields than they require."""
    member = {"type": "object", "required": ["what", "path", "sha256"],
              "properties": {"what": {"enum": list(MEMBER_KINDS)}, "path": {"type": "string", "minLength": 1},
                             "sha256": _HASH, "reason": {"type": "string"}}}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://github.com/Exxec/Project-BridgeForge/docs/contracts/gene/gene.schema.json#{GENE_SCHEMA_VERSION}",
        "title": f"{GENE_SCHEMA} schema {GENE_SCHEMA_VERSION}",
        "type": "object",
        "required": list(REQUIRED_KEYS),
        "properties": {
            "schema": {"const": GENE_SCHEMA},
            "schema_version": {"const": GENE_SCHEMA_VERSION},
            "identity": _HASH,
            "kind": {"enum": list(GENE_KINDS)},
            "anchors": {**_STRINGS, "minItems": 1},
            "provides": _STRINGS,
            "members": {"type": "array", "minItems": 1, "items": member},
            "needs": {"type": "object", "required": ["vanilla", "mods"], "properties": {"vanilla": _STRINGS, "mods": _STRINGS}},
            **{key: {"type": "array", "items": {"type": "object", "required": list(fields), "additionalProperties": True,
                                                "properties": {f: {"type": "string", "minLength": 1} for f in fields}}}
               for key, fields in ELEMENT_FIELDS.items()},
            "build": {"type": "object"}, "provenance": {"type": "object"},
            "derived_from": {"oneOf": [{"type": "null"}, {
                "type": "object", "required": ["identity", "by", "from_build"],
                "properties": {"identity": _HASH, "by": {"type": "string", "minLength": 1}, "from_build": {"type": ["string", "null"]}}}]},
            "licence": {"type": "object", "required": ["decision", "mod_decision", "local_only_members"],
                        "properties": {"decision": {"type": "string"}, "mod_decision": {"type": "string"}, "local_only_members": _STRINGS},
                        "if": {"properties": {"local_only_members": {"minItems": 1}}},
                        "then": {"properties": {"decision": {"const": "LOCAL_ONLY"}}}},
            "phenotype_obligations": _STRINGS,
            "unknowns": {"type": "object", "required": ["missing", "suspects"],
                         "properties": {"missing": {"type": "array"}, "suspects": {"type": "array"}}},
            "collected_from": _STRINGS,
        },
    }


def _member(what: str, path: str, text: str, reason: str) -> dict:
    return {"what": what, "path": path, "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "reason": reason}


def _base() -> dict:
    members = [_member("file", "data/hullmods/example.java", "fixture hull mod script", "the hull mod's script"),
               _member("csv-row", "data/hullmods/hull_mods.csv [example_mod]", "fixture hull mod row", "anchor row")]
    members.sort(key=lambda m: (m["what"], m["path"]))
    return {
        "schema": GENE_SCHEMA, "schema_version": GENE_SCHEMA_VERSION, "identity": identity("hullmod", members),
        "kind": "hullmod", "anchors": ["hullmod:example_mod"], "provides": ["hullmod:example_mod"], "members": members,
        "needs": {"vanilla": [], "mods": []},
        "registrations": [{"locus": "data/hullmods/hull_mods.csv [example_mod]", "statement": "hull mod row example_mod"}],
        "conditions": [], "persistent_state": [],
        "build": {"game_version": "0.98.5a-RC7", "mod_version": "1.0.0"},
        "provenance": {"mod_id": "fixture_mod", "mod_name": "Fixture Mod", "author": "BridgeForge"},
        "derived_from": None,
        "licence": {"decision": "LOCAL_ONLY", "reason": "fixture", "mod_decision": "LOCAL_ONLY", "local_only_members": []},
        "phenotype_obligations": list(PHENOTYPE["hullmod"]),
        "unknowns": {"missing": [], "suspects": []}, "collected_from": ["vendor-plan"],
    }


def fixtures() -> dict[str, dict]:
    """{file name: manifest}. Each invalid one breaks exactly one rule of the valid base."""
    base = _base()
    moved = copy.deepcopy(base)  # the same gene from another mod and build: identity must not change
    moved["provenance"] = {"mod_id": "another_mod", "mod_name": "Another", "author": "someone"}
    moved["build"] = {"game_version": "0.97a-RC11", "mod_version": "0.3"}
    moved["members"] = list(reversed(moved["members"]))
    adapted = copy.deepcopy(base)  # a gene G4 adapted, from a releasable mod with one member under a local-only path
    adapted["members"][0]["sha256"] = "1" * 64
    adapted["identity"] = identity(adapted["kind"], adapted["members"])
    adapted["derived_from"] = {"identity": base["identity"], "by": "jar-call-signature-changed", "from_build": "0.98a-RC8"}
    adapted["conditions"] = [{"kind": "mod-enabled", "subject": "nexerelin", "note": "extra fields are allowed"}]
    adapted["persistent_state"] = [{"name": "data.hullmods.Example", "via": "xstream"}]
    adapted["licence"] = {"decision": "LOCAL_ONLY", "reason": "a member under a local-only path", "mod_decision": "RELEASABLE",
                          "local_only_members": [adapted["members"][1]["path"]]}
    settings = copy.deepcopy(base)  # a gene that reads two settings keys (P1's shape)
    settings["members"] = sorted(settings["members"] + [
        {"what": "json-entry", "path": "data/config/settings.json#/example_mod_rate", "sha256": hashlib.sha256(b"5").hexdigest(),
         "reason": "settings key a member script reads"},
        {"what": "json-entry", "path": "data/config/settings.json#/example_mod_sfx", "sha256": hashlib.sha256(b"true").hexdigest(),
         "reason": "settings key a member script reads"}], key=lambda m: (m["what"], m["path"]))
    settings["identity"] = identity(settings["kind"], settings["members"])
    plugin = copy.deepcopy(base)  # a combat plugin: its registration is a nested settings.json key (P2's shape)
    registration = "data/config/settings.json#/plugins/example_CombatPlugin"
    plugin["members"] = sorted([
        {"what": "jar-class", "path": "jars/example.jar!data/scripts/example_CombatPlugin.class",
         "sha256": hashlib.sha256(b"fixture class").hexdigest(), "reason": "the plugin class"},
        {"what": "json-entry", "path": registration, "sha256": hashlib.sha256(b"registration").hexdigest(),
         "reason": "the plugin's registration in settings.json's plugins map"}], key=lambda m: (m["what"], m["path"]))
    plugin.update(kind="combat-plugin", anchors=["combat-plugin:example_CombatPlugin"], provides=["combat-plugin:example_CombatPlugin"],
                  registrations=[{"locus": registration, "statement": "data.scripts.example_CombatPlugin"}],
                  phenotype_obligations=list(PHENOTYPE["combat-plugin"]))
    plugin["identity"] = identity(plugin["kind"], plugin["members"])
    out = {"valid-hullmod.json": base, "valid-same-gene-other-mod.json": moved, "valid-adapted-gene.json": adapted,
           "valid-settings-entries.json": settings, "valid-combat-plugin.json": plugin}

    def broken(name: str, change) -> None:
        gene = copy.deepcopy(base)
        change(gene)
        out[f"invalid-{name}.json"] = gene

    broken("identity-mismatch", lambda g: g.update(identity="0" * 64))
    broken("missing-members", lambda g: g.pop("members"))
    broken("empty-members", lambda g: g.update(members=[]))
    broken("schema-version-bool", lambda g: g.update(schema_version=True))
    def unknown_kind(gene: dict) -> None:
        gene.update(kind="planet", anchors=["planet:example_mod"], provides=["planet:example_mod"])
        gene["identity"] = identity("planet", gene["members"])  # so only the kind rule is broken

    broken("unknown-kind", unknown_kind)
    broken("anchor-of-other-kind", lambda g: g.update(anchors=["weapon:example_mod"]))
    broken("member-hash-uppercase", lambda g: g["members"][0].update(sha256=g["members"][0]["sha256"].upper()))
    def duplicated(gene: dict) -> None:
        gene["members"] = gene["members"] + [dict(gene["members"][0])]
        gene["identity"] = identity(gene["kind"], gene["members"])  # so only the duplicate rule is broken

    broken("duplicate-member", duplicated)
    broken("licence-without-decision", lambda g: g.update(licence={}))
    broken("registration-without-locus", lambda g: g["registrations"][0].pop("locus"))
    broken("derived-from-short-identity", lambda g: g.update(derived_from={"identity": "abc", "by": "fixer", "from_build": None}))
    broken("local-only-member-not-local-only", lambda g: g["licence"].update(
        decision="RELEASABLE", mod_decision="RELEASABLE", local_only_members=[g["members"][0]["path"]]))
    broken("local-only-member-not-a-member", lambda g: g["licence"].update(local_only_members=["graphics/not_a_member.png"]))

    def entry(path: str):
        def change(gene: dict) -> None:
            gene["members"] = gene["members"] + [{"what": "json-entry", "path": path, "sha256": "0" * 64}]
            gene["identity"] = identity(gene["kind"], gene["members"])  # so only the path rule is broken
        return change

    broken("json-entry-without-pointer", entry("data/config/settings.json"))
    broken("json-entry-pointer-without-slash", entry("data/config/settings.json#example_mod_rate"))
    broken("json-entry-array-element", entry("data/config/settings.json#/ruleCommandPackages/0"))
    return out


def evidence_schema() -> dict:
    """The evidence header (WP5) as a JSON Schema. The gene it names, and its inputs' hashes, are checked by `gene evidence
    check`, not here. A producer may add fields."""
    path = {"type": "string", "minLength": 1, "not": {"pattern": "(^/|\\\\|:|(^|/)\\.{1,2}(/|$)|//|^\\s|\\s$)"}}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://github.com/Exxec/Project-BridgeForge/docs/contracts/gene/evidence-header.schema.json#{evidence_header.EVIDENCE_SCHEMA_VERSION}",
        "title": f"{evidence_header.EVIDENCE} schema {evidence_header.EVIDENCE_SCHEMA_VERSION}",
        "type": "object",
        "required": list(evidence_header.REQUIRED_KEYS),
        "properties": {
            "evidence": {"const": evidence_header.EVIDENCE},
            "schema_version": {"const": evidence_header.EVIDENCE_SCHEMA_VERSION},
            "kind": {"type": "string", "minLength": 1},
            "gene": {"type": "object", "required": ["identity", "schema_version"],
                     "properties": {"identity": _HASH, "schema_version": {"type": "integer",
                                                                         "not": {"enum": list(evidence_header.WITHDRAWN_GENE_VERSIONS)}}}},
            "produced_by": {"type": "object", "required": ["tool", "version"],
                            "properties": {"tool": {"type": "string", "minLength": 1}, "version": {"type": "string", "minLength": 1}}},
            "created_at": {"type": "string", "format": "date-time"},
            "build": {"type": "object", "properties": {"game_version": {"type": ["string", "null"]}}},
            "inputs": {"type": "array", "items": {"type": "object", "required": ["role", "path", "sha256"],
                                                  "properties": {"role": {"type": "string", "minLength": 1}, "path": path, "sha256": _HASH}}},
            "verdict": {"enum": list(evidence_header.VERDICTS)},
        },
    }


def evidence_fixtures() -> dict[str, dict]:
    """{file name: evidence header} about `fixtures/valid-hullmod.json`. Each invalid one breaks exactly one rule."""
    gene = _base()
    base = {"evidence": evidence_header.EVIDENCE, "schema_version": evidence_header.EVIDENCE_SCHEMA_VERSION,
            "kind": "subtraction-proof", "gene": {"identity": gene["identity"], "schema_version": GENE_SCHEMA_VERSION},
            "produced_by": {"tool": "bridgeforge", "version": "0.4.2"}, "created_at": "2026-11-19T18:00:00+00:00",
            "build": {"game_version": "0.98.5a-RC7"},
            "inputs": [{"role": "donor", "path": "data/hullmods/hull_mods.csv",
                        "sha256": hashlib.sha256(b"fixture hull mod row").hexdigest()}],
            "verdict": "PASS"}
    extra = copy.deepcopy(base)  # a producer's own fields are allowed
    extra.update(kind="phenotype-run", verdict="NOT_RUN", spw={"frame_ms_p95": None})
    out = {"valid-subtraction-proof.json": base, "valid-producer-fields.json": extra}

    def broken(name: str, change) -> None:
        made = copy.deepcopy(base)
        change(made)
        out[f"invalid-{name}.json"] = made

    broken("other-gene", lambda e: e["gene"].update(identity="f" * 64))
    broken("absolute-input-path", lambda e: e["inputs"][0].update(path="/home/someone/mod/data/hullmods/hull_mods.csv"))
    broken("input-without-hash", lambda e: e["inputs"][0].pop("sha256"))
    broken("withdrawn-gene-schema", lambda e: e["gene"].update(schema_version=1))
    broken("unknown-verdict", lambda e: e.update(verdict="OK"))
    broken("time-without-offset", lambda e: e.update(created_at="2026-11-19T18:00:00"))
    return out


def _canonical_bytes(data: dict) -> bytes:
    return dumps(data).encode("utf-8")


def contract_files() -> dict[str, bytes]:
    """{posix path in the contract folder: bytes}, CONTRACT.json included."""
    files = {"gene.schema.json": _canonical_bytes(json_schema())}
    verdicts = {}
    for name, gene in sorted(fixtures().items()):
        files[f"fixtures/{name}"] = _canonical_bytes(gene)
        problems = validate(gene)
        if name.startswith("valid-") == bool(problems):
            raise AssertionError(f"fixture {name} is judged {'invalid' if problems else 'valid'}: {problems}")
        verdicts[name] = {"valid": not problems, "identity": gene.get("identity") if not problems else None}
    files["evidence-header.schema.json"] = _canonical_bytes(evidence_schema())
    gene = fixtures()["valid-hullmod.json"]
    evidence_verdicts = {}
    for name, made in sorted(evidence_fixtures().items()):
        files[f"evidence/{name}"] = _canonical_bytes(made)
        problems = evidence_header.check(made, gene)
        if name.startswith("valid-") == bool(problems):
            raise AssertionError(f"evidence fixture {name} is judged {'invalid' if problems else 'valid'}: {problems}")
        evidence_verdicts[name] = {"valid": not problems}
    contract = {"contract": GENE_SCHEMA, "schema_version": GENE_SCHEMA_VERSION, "withdrawn_versions": list(WITHDRAWN_VERSIONS),
                "evidence_header": {"name": evidence_header.EVIDENCE, "schema_version": evidence_header.EVIDENCE_SCHEMA_VERSION,
                                    "judged_against": "fixtures/valid-hullmod.json", "fixtures": evidence_verdicts},
                "identity_rule": IDENTITY_RULE,
                "files": {path: hashlib.sha256(data).hexdigest() for path, data in sorted(files.items())},
                "fixtures": verdicts}
    files["CONTRACT.json"] = _canonical_bytes(contract)
    return files


def contract_sha256(files: dict[str, bytes] | None = None) -> str:
    """What a consumer pins: the SHA-256 of CONTRACT.json."""
    return hashlib.sha256((files or contract_files())["CONTRACT.json"]).hexdigest()


def write_contract(folder: Path) -> str:
    from bridgeforge.safeio import atomic_write_bytes

    for relative, data in contract_files().items():
        target = Path(folder) / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(target, data)
    return contract_sha256()


def check_contract(folder: Path) -> list[str]:
    """What differs between `folder` and the contract this code writes; empty when they are equal."""
    folder = Path(folder)
    expected = contract_files()
    problems = []
    for relative, data in expected.items():
        path = folder / relative
        if not path.is_file():
            problems.append(f"{relative} is missing")
        elif path.read_bytes() != data:
            problems.append(f"{relative} differs from the contract gene.py defines")
    present = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()} if folder.is_dir() else set()
    problems += [f"{extra} is not part of the contract" for extra in sorted(present - set(expected))]
    return problems
