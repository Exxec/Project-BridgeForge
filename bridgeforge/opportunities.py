from __future__ import annotations

import json
from pathlib import Path

from .workspace import workspace_paths

SIGNALS = (
    ("magiclib", "custom-bounty-framework", ("bounty", "bounties"), "A custom bounty subsystem may be a MagicLib adoption candidate."),
    ("lunalib", "manual-settings-ui", ("settings", "custompanel"), "A manual settings UI may be a LunaLib adoption candidate."),
    ("ashlib", "custom-variant-infrastructure", ("variant", "hullmod"), "Custom variant infrastructure may be an AshLib adoption candidate."),
    ("lazylib", "custom-helper-math", ("vector2f", "mathutils"), "Custom helper/math code may be a LazyLib adoption candidate."),
)


def analyze_opportunities(workspace: Path) -> dict:
    workspace = workspace.expanduser().resolve()
    _, working, _ = workspace_paths(workspace)
    findings = []
    for source in working.rglob("*.java"):
        text = source.read_text(encoding="utf-8", errors="replace").lower()
        for library, kind, terms, explanation in SIGNALS:
            matched = [term for term in terms if term in text]
            if matched:
                findings.append({"candidate_library": library, "kind": kind, "file": source.relative_to(working).as_posix(), "evidence": matched, "maintenance_benefit": "UNKNOWN", "compatibility_benefit": "UNKNOWN", "dependency_cost": "REVIEW", "behavioral_risk": "HIGH", "save_risk": "REVIEW", "recommendation": "REVIEW ONLY — do not adopt automatically.", "explanation": explanation})
    result = {"schema_version": 1, "findings": findings, "scope": "Heuristic opportunity signals only; these are library-adoption suggestions, not library migrations or automatic changes."}
    (workspace / "modernization-opportunities.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result
