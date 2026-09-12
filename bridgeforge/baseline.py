from __future__ import annotations

import json
from pathlib import Path

from .models import Finding


def finding_baseline_key(finding: Finding) -> str:
    """A finding's identity for baseline comparison: id + file + first evidence item."""
    first_evidence = finding.evidence[0] if finding.evidence else ""
    return f"{finding.id}|{finding.file or ''}|{first_evidence}"


def load_baseline_keys(path: Path) -> set[str]:
    """Read a `scan --write-baseline` file and return its accepted finding keys."""
    payload = json.loads(Path(path).expanduser().resolve().read_text(encoding="utf-8"))
    return set(payload.get("findings", []))


def split_by_baseline(findings: list[Finding], baseline_keys: set[str]) -> tuple[list[Finding], int]:
    """Return (findings not in the baseline, count of baseline keys no longer produced)."""
    current_keys = {finding_baseline_key(finding) for finding in findings}
    new_findings = [finding for finding in findings if finding_baseline_key(finding) not in baseline_keys]
    resolved_count = len(baseline_keys - current_keys)
    return new_findings, resolved_count
