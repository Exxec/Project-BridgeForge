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


def mod_baseline_path(working: Path) -> Path | None:
    """The mod's own accepted-findings baseline (`working/reports/baseline*.json`), if it keeps one.

    A mod whose findings are reviewed and deliberately accepted (Xenoargh-FX-Example's preset
    overrides are intentional custom content, owner call 2026-09-22) otherwise keeps reporting them
    forever. `scan --write-baseline` produces the file; `scan --baseline`, `corpus-recheck`, `revive`
    and `finding-stats` honour it.
    """
    reports = Path(working) / "reports"
    if not reports.is_dir():
        return None
    candidates = sorted(reports.glob("baseline*.json"))
    return candidates[-1] if candidates else None


def mod_baseline_keys(working: Path) -> set[str]:
    """Accepted finding keys for a working copy; empty when it keeps no (readable) baseline."""
    path = mod_baseline_path(working)
    if path is None:
        return set()
    try:
        return load_baseline_keys(path)
    except (OSError, ValueError):
        return set()


def finding_dict_baseline_key(finding: dict) -> str:
    """`finding_baseline_key` for a finding already turned into a dict (scan JSON, asdict)."""
    evidence = finding.get("evidence") or []
    return f"{finding.get('id')}|{finding.get('file') or ''}|{evidence[0] if evidence else ''}"


def accept_findings(working: Path, keys: list[str]) -> Path:
    """Add finding keys to the mod's accepted-findings baseline (the one `mod_baseline_path` reads, else
    working/reports/baseline.json), keeping every key already there. Used for owner rulings that accept a
    finding as authored (variant-op-over-budget, option 2, 2026-09-27)."""
    path = mod_baseline_path(working) or Path(working) / "reports" / "baseline.json"
    existing = load_baseline_keys(path) if path.is_file() else set()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"findings": sorted(existing | set(keys))}, indent=2) + "\n", encoding="utf-8")
    return path
