"""94.G1 WP2 (GR-1): the gene.json contract as files a sister repository pins by hash.

`gene contract --write` puts three things in `docs/contracts/gene/`:
- `gene.schema.json`: a JSON Schema (2020-12) of manifest schema 1, for repositories that validate with a library;
- `fixtures/`: manifests every consumer must judge as BridgeForge does: the `valid-*` ones pass, each `invalid-*` one
  fails, and `valid-*` identities must come out equal from the identity rule;
- `CONTRACT.json`: the schema id and version, the identity rule in words, every file's SHA-256 and each fixture's verdict.

A consumer copies the folder byte for byte and pins CONTRACT.json's SHA-256, as it pins `target export`'s registry; WP3's
cross-repository check reports a pin that no longer matches. `gene contract --check` fails when the committed folder
differs from what this code writes, so the contract cannot drift from `gene.py` without a deliberate rewrite.
"""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path

from bridgeforge.genome.gene import (GENE_SCHEMA, GENE_SCHEMA_VERSION, PHENOTYPE, REQUIRED_KEYS, dumps, identity,
                                     validate)
from bridgeforge.vendor_plan import KINDS

CONTRACT_RELATIVE = Path("docs") / "contracts" / "gene"
IDENTITY_RULE = ("identity = SHA-256 (lowercase hex) of the UTF-8 text: the kind and a line feed, then one line per member "
                 "sorted by (what, path): what, TAB, path, TAB, sha256, line feed. A text member's sha256 is of its "
                 "normalized bytes (no UTF-8 BOM, LF line ends, no trailing spaces or tabs, no trailing blank lines); a "
                 "csv-row's is of the JSON object of its named non-empty trimmed cells with sorted keys; a jar-class's and "
                 "any other file's is of its bytes.")

_HASH = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
_STRINGS = {"type": "array", "items": {"type": "string"}}


def json_schema() -> dict:
    """Manifest schema 1 as a JSON Schema. The identity's agreement with the members is checked by the identity rule, not here."""
    member = {"type": "object", "required": ["what", "path", "sha256"],
              "properties": {"what": {"enum": ["file", "csv-row", "jar-class"]}, "path": {"type": "string", "minLength": 1},
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
            "kind": {"enum": list(KINDS)},
            "anchors": {**_STRINGS, "minItems": 1},
            "provides": _STRINGS,
            "members": {"type": "array", "minItems": 1, "items": member},
            "needs": {"type": "object", "required": ["vanilla", "mods"], "properties": {"vanilla": _STRINGS, "mods": _STRINGS}},
            "registrations": {"type": "array"}, "conditions": {"type": "array"}, "persistent_state": {"type": "array"},
            "build": {"type": "object"}, "provenance": {"type": "object"},
            "licence": {"type": "object", "required": ["decision"], "properties": {"decision": {"type": "string"}}},
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
        "needs": {"vanilla": [], "mods": []}, "registrations": [], "conditions": [], "persistent_state": [],
        "build": {"game_version": "0.98.5a-RC7", "mod_version": "1.0.0"},
        "provenance": {"mod_id": "fixture_mod", "mod_name": "Fixture Mod", "author": "BridgeForge"},
        "licence": {"decision": "LOCAL_ONLY"}, "phenotype_obligations": list(PHENOTYPE["hullmod"]),
        "unknowns": {"missing": [], "suspects": []}, "collected_from": ["vendor-plan"],
    }


def fixtures() -> dict[str, dict]:
    """{file name: manifest}. Each invalid one breaks exactly one rule of the valid base."""
    base = _base()
    moved = copy.deepcopy(base)  # the same gene from another mod and build: identity must not change
    moved["provenance"] = {"mod_id": "another_mod", "mod_name": "Another", "author": "someone"}
    moved["build"] = {"game_version": "0.97a-RC11", "mod_version": "0.3"}
    moved["members"] = list(reversed(moved["members"]))
    out = {"valid-hullmod.json": base, "valid-same-gene-other-mod.json": moved}

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
    contract = {"contract": GENE_SCHEMA, "schema_version": GENE_SCHEMA_VERSION, "identity_rule": IDENTITY_RULE,
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
