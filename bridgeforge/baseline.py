from __future__ import annotations

from .safeio import atomic_write_text

import json
import re
from pathlib import Path

from .models import Finding


_LINE_NUMBER = re.compile(r":\d+(?=[:\s]|$)")


def stable_evidence(evidence: str) -> str:
    """Evidence without line numbers (`Carinasystem.java:31: Carina` -> `Carinasystem.java:#: Carina`): an accepted finding
    must survive an edit that only moves lines. Navarchy of Tania's accepted system-generation-unguarded came back after an
    agent fix shifted Carinasystem.java and had to be accepted again (ROADMAP-3 item 92.29, 2026-11-16)."""
    return _LINE_NUMBER.sub(":#", evidence)


def stable_key(key: str) -> str:
    """A stored `id|file|evidence` key with its evidence part made line-number free, so older baselines still match."""
    parts = key.split("|", 2)
    return key if len(parts) < 3 else f"{parts[0]}|{parts[1]}|{stable_evidence(parts[2])}"


def finding_baseline_key(finding: Finding) -> str:
    """A finding's identity for baseline comparison: id + file + first evidence item (line numbers removed)."""
    first_evidence = finding.evidence[0] if finding.evidence else ""
    return f"{finding.id}|{finding.file or ''}|{stable_evidence(first_evidence)}"


def load_baseline_keys(path: Path) -> set[str]:
    """Read a `scan --write-baseline` file and return its accepted finding keys (line-number free, see `stable_key`)."""
    payload = json.loads(Path(path).expanduser().resolve().read_text(encoding="utf-8"))
    return {stable_key(key) for key in payload.get("findings", []) if isinstance(key, str)}


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
    return f"{finding.get('id')}|{finding.get('file') or ''}|{stable_evidence(evidence[0]) if evidence else ''}"


def accept_findings(working: Path, keys: list[str], reason: str | None = None) -> Path:
    """Add finding keys to the mod's accepted-findings baseline (the one `mod_baseline_path` reads, else
    working/reports/baseline.json), keeping every key already there. Used for owner rulings that accept a
    finding as authored (variant-op-over-budget, option 2, 2026-09-27)."""
    path = mod_baseline_path(working) or Path(working) / "reports" / "baseline.json"
    existing = load_baseline_keys(path) if path.is_file() else set()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    payload = payload if isinstance(payload, dict) else {}  # keeps a stamp and reasons already there
    payload["findings"] = sorted(existing | set(keys))
    atomic_write_text(path, json.dumps(payload, indent=2) + "\n")
    from .baseline_audit import stamp_baseline  # lazy: baseline_audit imports this module

    stamp_baseline(path, working, reason)
    return path


def remove_findings(working: Path, keys: list[str]) -> Path | None:
    """Take finding keys (and their reasons) out of the mod's accepted-findings baseline: the ruling that put them there was
    revoked (item 73 R4). Keys not in the baseline are ignored; returns the baseline path, or None when the mod keeps none."""
    path = mod_baseline_path(working)
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload = payload if isinstance(payload, dict) else {}
    drop = set(keys)
    payload["findings"] = sorted(set(payload.get("findings", [])) - drop)
    if isinstance(payload.get("reasons"), dict):
        payload["reasons"] = {k: v for k, v in payload["reasons"].items() if k not in drop}
    atomic_write_text(path, json.dumps(payload, indent=2) + "\n")
    return path
