from __future__ import annotations

import json
import re
from pathlib import Path

from .workspace import workspace_paths

PERSISTENT_IDENTIFIERS = re.compile(r"\b(factionId|shipId|weaponId|industryId|conditionId|memoryKey|serializedClass|persistent\w*)\b", re.I)
IDENTIFIER_VALUES = re.compile(r"[\"']?\b(factionId|shipId|weaponId|industryId|conditionId|memoryKey|serializedClass|persistent\w*)\b[\"']?\s*[:=]\s*[\"']?([\w.-]+)", re.I)


def analyze_save_risk(workspace: Path) -> dict:
    workspace = workspace.expanduser().resolve()
    original, working, _ = workspace_paths(workspace)
    findings = []
    files = {path.relative_to(working) for path in working.rglob("*") if path.is_file()} | {path.relative_to(original) for path in original.rglob("*") if path.is_file()}
    for relative in sorted(files):
        current = working / relative
        baseline = original / relative
        if baseline.is_file() and current.is_file() and baseline.read_bytes() == current.read_bytes():
            continue
        try:
            before = baseline.read_text(encoding="utf-8", errors="replace") if baseline.is_file() else ""
            after = current.read_text(encoding="utf-8", errors="replace") if current.is_file() else ""
        except OSError:
            continue
        changed = set(IDENTIFIER_VALUES.findall(before)) ^ set(IDENTIFIER_VALUES.findall(after))
        if not changed:
            changed = {(identifier, "UNKNOWN") for identifier in set(PERSISTENT_IDENTIFIERS.findall(before)) ^ set(PERSISTENT_IDENTIFIERS.findall(after))}
        if changed:
            findings.append({"file": relative.as_posix(), "identifiers": [f"{key}={value}" for key, value in sorted(changed)], "severity": "high", "classification": "REVIEW", "explanation": "A persistent identifier or its value changed; preserve the old identifier or supply explicit save migration logic."})
    result = {"schema_version": 1, "risk": "HIGH" if findings else "UNKNOWN", "findings": findings, "scope": "Static diff only; absence of findings does not prove save compatibility."}
    (workspace / "save-risk.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result
