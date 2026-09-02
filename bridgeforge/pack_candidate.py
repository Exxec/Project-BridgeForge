from __future__ import annotations

import json
from pathlib import Path


REQUIRED_EVIDENCE = (
    "provenance",
    "before_fixture",
    "after_fixture",
    "compile_validation",
    "idempotence",
    "conflict_review",
    "save_risk_assessment",
)


def create_migration_pack_candidate(library_id: str, mapping_id: str, from_symbol: str, to_symbol: str, output: Path) -> Path:
    """Create a non-loadable research contract for a proposed library mapping.

    It intentionally is not a migration pack: blank evidence fields make it
    invalid for ``plan``. This prevents API-name similarity from becoming an
    executable source rewrite before a maintainer-backed example proves it.
    """
    if not all(value.strip() for value in (library_id, mapping_id, from_symbol, to_symbol)):
        raise ValueError("Library ID, mapping ID, source symbol, and target symbol are required.")
    output = output.expanduser().resolve()
    if output.exists():
        raise ValueError(f"Refusing to overwrite existing candidate: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "mode": "RESEARCH_CANDIDATE_NOT_A_MIGRATION_PACK",
        "library_id": library_id,
        "mapping_id": mapping_id,
        "proposed_mapping": {"from": from_symbol, "to": to_symbol},
        "evidence_required": list(REQUIRED_EVIDENCE),
        "evidence": {field: "" for field in REQUIRED_EVIDENCE},
        "automatic_modification": "FORBIDDEN_UNTIL_EVIDENCE_COMPLETE",
        "next_step": "Supply a release-specific old/new example and fixture evidence; then create a separately reviewed migration pack rule.",
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output
