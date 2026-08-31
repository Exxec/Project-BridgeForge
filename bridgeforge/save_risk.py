from __future__ import annotations

import json
import re
from pathlib import Path

from .workspace import workspace_paths

PERSISTENT_IDENTIFIERS = re.compile(r"\b(factionId|shipId|weaponId|industryId|conditionId|memoryKey|serializedClass|persistent\w*)\b", re.I)


def analyze_save_risk(workspace: Path) -> dict:
    workspace = workspace.expanduser().resolve()
    original, working, _ = workspace_paths(workspace)
    findings = []
    for current in sorted(path for path in working.rglob("*") if path.is_file()):
        relative = current.relative_to(working)
        baseline = original / relative
        if not baseline.is_file() or baseline.read_bytes() == current.read_bytes():
            continue
        try:
            before = baseline.read_text(encoding="utf-8", errors="replace") if baseline.is_file() else ""
            after = current.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        changed = set(PERSISTENT_IDENTIFIERS.findall(before)) ^ set(PERSISTENT_IDENTIFIERS.findall(after))
        if changed:
            findings.append({"file": relative.as_posix(), "identifiers": sorted(changed), "severity": "high", "classification": "REVIEW", "explanation": "A persistent-identifier-shaped field changed; preserve the old identifier or supply explicit save migration logic."})
    result = {"schema_version": 1, "risk": "HIGH" if findings else "UNKNOWN", "findings": findings, "scope": "Static diff only; absence of findings does not prove save compatibility."}
    (workspace / "save-risk.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result
