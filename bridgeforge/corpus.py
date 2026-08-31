from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .scanner import scan_mod


def compare_corpus(mod_directory: Path, baseline_path: Path) -> dict:
    baseline_path = baseline_path.expanduser().resolve()
    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid corpus baseline: {baseline_path}: {exc}") from exc
    if baseline.get("schema_version") != 1 or not isinstance(baseline.get("expected_findings"), list):
        raise ValueError(f"Invalid corpus baseline: {baseline_path}")
    mod_directory = mod_directory.expanduser().resolve()
    metadata = mod_directory / "mod_info.json"
    if not metadata.is_file():
        raise ValueError("Corpus comparison requires mod_info.json at the selected mod root.")
    scan = scan_mod(mod_directory)
    finding_key = lambda item: tuple("" if value is None else str(value) for value in item)
    actual_findings = sorted({(finding.id, finding.classification, finding.file) for finding in scan.findings}, key=finding_key)
    expected_findings = sorted({(item.get("id"), item.get("classification"), item.get("file")) for item in baseline["expected_findings"]}, key=finding_key)
    actual_fingerprint = {"file_count": len(scan.files), "mod_info_sha256": hashlib.sha256(metadata.read_bytes()).hexdigest()}
    expected_fingerprint = {key: baseline.get(key) for key in actual_fingerprint}
    result = {
        "schema_version": 1,
        "baseline": baseline["name"],
        "status": "PASS" if actual_fingerprint == expected_fingerprint and actual_findings == expected_findings else "MISMATCH",
        "fingerprint": {"expected": expected_fingerprint, "actual": actual_fingerprint},
        "missing_findings": [dict(id=item[0], classification=item[1], file=item[2]) for item in expected_findings if item not in actual_findings],
        "unexpected_findings": [dict(id=item[0], classification=item[1], file=item[2]) for item in actual_findings if item not in expected_findings],
    }
    return result
