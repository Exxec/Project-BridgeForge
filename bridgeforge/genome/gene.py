"""94.G1: the gene contract and identity, read-only (docs/FEATURE_GENOME_ROADMAP.md sections 2 and 6, WP1).

A gene is the minimal closed set of parts that gives one player-observable capability. `describe(mod, "kind:id")` writes
its manifest, `gene.json` schema 1, from `vendor-plan`'s closure: the six content kinds it covers (hull mod, weapon, wing,
hull, variant, ship system). Campaign features, registration slicing and the archaeology fields (registrations,
conditions, persistent state) come with G2; in schema 1 they are present and empty, and `collected_from` says so.

Identity is the SHA-256 of the kind and the normalized members, so the same feature copied into another mod or another
folder gets the same identity (one allele): a text file's line endings are normalized, a CSV row is its non-empty cells,
a class is its bytes. Paths of the machine, dates and the mod's own name are not part of it.
"""
from __future__ import annotations

import hashlib
import json
import os
import zipfile
from pathlib import Path

from bridgeforge.file_hash import sha256_file
from bridgeforge.mod_files import read_mod_info
from bridgeforge.vendor_plan import _TEXT_SUFFIXES, KINDS, _rows, vendor_plan
from bridgeforge.zipsafe import MAX_CLASS_BYTES, read_limited

GENE_SCHEMA = "bridgeforge-gene"
GENE_SCHEMA_VERSION = 1
COLLECTED_FROM = ["vendor-plan"]
# What the player sees each kind do: the phenotype a live run must observe (S3 makes these real obligations, G6).
PHENOTYPE = {
    "hull": ["the hull spawns in a fleet and enters combat"],
    "variant": ["the variant loads with its hull and fits"],
    "weapon": ["the weapon fires in combat"],
    "wing": ["the wing launches from a carrier in combat"],
    "hullmod": ["the hull mod applies to a ship and shows its effect"],
    "shipsystem": ["the ship system activates in combat"],
}
REQUIRED_KEYS = ("schema", "schema_version", "identity", "kind", "anchors", "provides", "members", "needs", "registrations",
                 "conditions", "persistent_state", "build", "provenance", "licence", "phenotype_obligations", "unknowns",
                 "collected_from")


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


def _row_member(root: Path, entry_path: str) -> dict:
    table, _, rest = entry_path.partition(" [")
    ident = rest.rstrip("]")
    row = _rows(root, table).get(ident)
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


def identity(kind: str, members: list[dict]) -> str:
    """The gene's identity: the kind and its members (what, path, content hash), in a fixed order."""
    lines = [f"{kind}\n"] + [f"{m['what']}\t{m['path']}\t{m['sha256']}\n" for m in sorted(members, key=lambda m: (m["what"], m["path"]))]
    return hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()


def describe(mod: Path, anchor: str, *, vanilla_core: Path | None = None, policy_path: Path | None = None) -> dict:
    """The gene manifest for one content piece (`kind:id`) of a mod folder or workspace."""
    kind, _, ident = anchor.partition(":")
    if kind not in KINDS or not ident:
        raise GeneError(f"a gene anchor is kind:id with kind one of {', '.join(KINDS)}; got {anchor!r}")
    plan = vendor_plan(mod, [anchor], vanilla_core=vanilla_core, policy_path=policy_path)
    root = Path(plan["provider"])
    if anchor not in plan["closure_ids"]:
        raise GeneError(f"{anchor} is not defined by {root} (missing: {', '.join(plan['missing']) or 'nothing'})")
    members = []
    for entry in plan["include"]:
        if entry["what"] == "file":
            member = _file_member(root, entry["path"])
        elif entry["what"] == "csv-row":
            member = _row_member(root, entry["path"])
        elif entry["what"] == "jar-class":
            member = _jar_member(root, entry["path"])
        else:
            raise GeneError(f"vendor-plan named a part of an unknown kind: {entry['what']!r}")
        members.append({**member, "reason": entry["reason"]})
    members.sort(key=lambda m: (m["what"], m["path"]))
    info = read_mod_info(root) or {}
    dependencies = sorted(d["id"] for d in info.get("dependencies") or [] if isinstance(d, dict) and isinstance(d.get("id"), str))
    gene = {
        "schema": GENE_SCHEMA, "schema_version": GENE_SCHEMA_VERSION,
        "identity": identity(kind, members),
        "kind": kind, "anchors": [anchor], "provides": plan["closure_ids"],
        "members": members,
        "needs": {"vanilla": plan["provided_by_vanilla"], "mods": dependencies},
        "registrations": [], "conditions": [], "persistent_state": [],
        "build": {"game_version": info.get("gameVersion"), "mod_version": _version_text(info.get("version"))},
        "provenance": {"mod_id": info.get("id"), "mod_name": info.get("name"), "author": info.get("author")},
        "licence": plan["licence"],
        "phenotype_obligations": list(PHENOTYPE[kind]),
        "unknowns": {"missing": plan["missing"], "suspects": plan["suspects"]},
        "collected_from": list(COLLECTED_FROM),
    }
    problems = validate(gene)
    if problems:
        raise GeneError("the manifest does not meet schema 1: " + "; ".join(problems))
    return gene


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
    if member.get("what") not in ("file", "csv-row", "jar-class"):
        return f"member kind {member.get('what')!r} is not file, csv-row or jar-class"
    if not isinstance(member.get("path"), str) or not member["path"]:
        return "a member's path is a non-empty string"
    if not _is_hash(member.get("sha256")):
        return f"{member['path']}: sha256 is 64 lowercase hex digits"
    return None


def validate(gene: object) -> list[str]:
    """What keeps `gene` from being a schema-1 manifest; empty when it is one. Sister repositories read these files, so
    every field's shape is checked, and malformed input gives problems, never an exception."""
    if not isinstance(gene, dict):
        return ["a manifest is a JSON object"]
    problems = [f"missing {key}" for key in REQUIRED_KEYS if key not in gene]
    if problems:
        return problems
    version = gene["schema_version"]
    if gene["schema"] != GENE_SCHEMA or type(version) is not int or version != GENE_SCHEMA_VERSION:
        problems.append(f"schema is {gene['schema']!r} {version!r}, not {GENE_SCHEMA!r} {GENE_SCHEMA_VERSION}")
    if gene["kind"] not in KINDS:
        problems.append(f"kind {gene['kind']!r} is not one of {', '.join(KINDS)}")
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
    for key in ("build", "provenance"):
        if not isinstance(gene[key], dict):
            problems.append(f"{key} is an object")
    if not isinstance(gene["licence"], dict) or not isinstance(gene["licence"].get("decision"), str):
        problems.append("licence is an object with a decision")
    members = gene["members"]
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


__all__ = ["GENE_SCHEMA", "GENE_SCHEMA_VERSION", "GeneError", "describe", "dumps", "identity", "validate"]
