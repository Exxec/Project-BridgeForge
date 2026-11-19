"""94.G1 WP5: the header every evidence file about a gene carries (docs/FEATURE_GENOME_ROADMAP.md section 14).

A gene's evidence is the files that show something about it: G2's subtraction and isolation proofs, G6's phenotype runs,
Salvor's save add/remove results, SPW's cost. They come from several repositories, so each starts with the same header,
which says which gene and which inputs the evidence is about. The header is its own small schema, versioned apart from
`gene.json`, and part of the same pinned contract (`docs/contracts/gene/`, GR-1). It points at a gene by
`{identity, schema_version}`; it never copies the manifest.

Field names follow what the suite already writes: `schema_version` and `kind` as in `gates.json` and the run manifests,
`created_at` as `run_manifest` (UTC, seconds), `sha256` as lowercase hex, `build.game_version` as in `gene.json`, and the
gate states `PASS`, `FAIL`, `NOT_RUN` and `UNKNOWN` of docs/SISTER_REPO_INTEROPERABILITY_DESIGN.md section 3. Only the
core below is required; a producer may add fields.

    {"evidence": "bridgeforge-gene-evidence", "schema_version": 1, "kind": "subtraction-proof",
     "gene": {"identity": <64 hex>, "schema_version": 2},
     "produced_by": {"tool": "bridgeforge", "version": "0.4.2"},
     "created_at": "2026-11-19T18:00:00+00:00", "build": {"game_version": "0.98.5a-RC7"},
     "inputs": [{"role": "donor", "path": "data/hullmods/hull_mods.csv", "sha256": <64 hex>}],
     "verdict": "PASS"}

An input's path is relative to the folder the evidence was made from (a mod or workspace), in posix form: the repository
is public, and like `gene.json` the header names no machine path. `check` recomputes each input's SHA-256 under a root
the reader gives, so stale evidence (an input changed since) is caught.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from bridgeforge.genome.gene import GENE_SCHEMA_VERSION, _is_hash

EVIDENCE = "bridgeforge-gene-evidence"
EVIDENCE_SCHEMA_VERSION = 1
VERDICTS = ("PASS", "FAIL", "NOT_RUN", "UNKNOWN")
WITHDRAWN_GENE_VERSIONS = (1,)
REQUIRED_KEYS = ("evidence", "schema_version", "kind", "gene", "produced_by", "created_at", "build", "inputs", "verdict")


def path_problem(path: object) -> str | None:
    """Why `path` is not a relative posix path inside its root, or None."""
    if not isinstance(path, str) or not path or path != path.strip():
        return "an input path is a non-empty string without surrounding spaces"
    segments = path.split("/")
    if "\\" in path or path.startswith("/") or ":" in path or any(s in ("", ".", "..") for s in segments):
        return f"input path {path!r} must be relative, in posix form, without '.', '..' or empty segments"
    return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def header(kind: str, gene: dict, *, root: Path, inputs: list[tuple[str, str]], verdict: str, tool: str = "bridgeforge",
           version: str | None = None, game_version: str | None = None, created_at: str | None = None) -> dict:
    """The header for evidence about `gene`, made from the files `inputs` ((role, path relative to `root`)) as they are now."""
    if version is None:
        from bridgeforge import __version__ as version
    rows = []
    for role, path in inputs:
        problem = path_problem(path)
        if problem:
            raise ValueError(problem)
        rows.append({"role": role, "path": path, "sha256": _sha256(Path(root) / path)})
    made = {"evidence": EVIDENCE, "schema_version": EVIDENCE_SCHEMA_VERSION, "kind": kind,
            "gene": {"identity": gene["identity"], "schema_version": gene["schema_version"]},
            "produced_by": {"tool": tool, "version": version},
            "created_at": created_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "build": {"game_version": game_version if game_version is not None else (gene.get("build") or {}).get("game_version")},
            "inputs": rows, "verdict": verdict}
    problems = validate(made)
    if problems:
        raise ValueError("the header does not meet its schema: " + "; ".join(problems))
    return made


def _created_at_problem(value: object) -> str | None:
    try:
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        parsed = None
    if parsed is None or parsed.utcoffset() is None:
        return "created_at is an ISO 8601 time with its UTC offset"
    return None


def validate(evidence: object) -> list[str]:
    """What keeps `evidence` from carrying a schema-1 header; empty when it does. Malformed input gives problems, never an
    exception: sister repositories write these files."""
    if not isinstance(evidence, dict):
        return ["an evidence file is a JSON object"]
    problems = [f"missing {key}" for key in REQUIRED_KEYS if key not in evidence]
    if problems:
        return problems
    version = evidence["schema_version"]
    if evidence["evidence"] != EVIDENCE or type(version) is not int or version != EVIDENCE_SCHEMA_VERSION:
        problems.append(f"header is {evidence['evidence']!r} {version!r}, not {EVIDENCE!r} {EVIDENCE_SCHEMA_VERSION}")
    if not isinstance(evidence["kind"], str) or not evidence["kind"]:
        problems.append("kind is a non-empty string")
    gene = evidence["gene"]
    if not isinstance(gene, dict) or not _is_hash(gene.get("identity")) or type(gene.get("schema_version")) is not int:
        problems.append("gene is {identity: 64 hex digits, schema_version: integer}")
    elif gene["schema_version"] in WITHDRAWN_GENE_VERSIONS:
        problems.append(f"gene schema {gene['schema_version']} is withdrawn")
    produced = evidence["produced_by"]
    if not isinstance(produced, dict) or not all(isinstance(produced.get(f), str) and produced[f] for f in ("tool", "version")):
        problems.append("produced_by is {tool, version} as non-empty strings")
    created = _created_at_problem(evidence["created_at"])
    if created:
        problems.append(created)
    build = evidence["build"]
    if not isinstance(build, dict) or not (build.get("game_version") is None or isinstance(build.get("game_version"), str)):
        problems.append("build is an object whose game_version is a string or null")
    inputs = evidence["inputs"]
    if not isinstance(inputs, list):
        problems.append("inputs is a list")
    else:
        for row in inputs:
            if not isinstance(row, dict) or not isinstance(row.get("role"), str) or not row["role"] or not _is_hash(row.get("sha256")):
                problems.append("each input is {role, path, sha256: 64 lowercase hex digits}")
                break
            problem = path_problem(row.get("path"))
            if problem:
                problems.append(problem)
                break
    if evidence["verdict"] not in VERDICTS:
        problems.append(f"verdict is one of {', '.join(VERDICTS)}")
    return problems


def check(evidence: dict, gene: dict, root: Path | None = None) -> list[str]:
    """What makes `evidence` not evidence about `gene` as it stands: a malformed header, another gene, a gene schema other
    than the manifest's, or (with `root`) an input that changed since or is gone."""
    problems = validate(evidence)
    if problems:
        return problems
    if evidence["gene"]["identity"] != gene.get("identity"):
        problems.append("the evidence is about another gene (identity differs)")
    if evidence["gene"]["schema_version"] != gene.get("schema_version"):
        problems.append(f"the evidence names gene schema {evidence['gene']['schema_version']}, the manifest is {gene.get('schema_version')}")
    if root is not None:
        for row in evidence["inputs"]:
            path = Path(root) / row["path"]
            if not path.is_file():
                problems.append(f"input {row['path']} is gone")
            elif _sha256(path) != row["sha256"]:
                problems.append(f"input {row['path']} changed since the evidence was made")
    return problems


__all__ = ["EVIDENCE", "EVIDENCE_SCHEMA_VERSION", "GENE_SCHEMA_VERSION", "REQUIRED_KEYS", "VERDICTS", "WITHDRAWN_GENE_VERSIONS",
           "check", "header", "path_problem", "validate"]
