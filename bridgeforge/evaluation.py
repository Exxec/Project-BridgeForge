from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path

from .models import ScanResult, TargetProfile
from .scanner import scan_mod


def _tree_hashes(root: Path) -> dict[str, str]:
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(root.rglob("*")) if path.is_file()}


def _extension_counts(paths: set[str]) -> dict[str, int]:
    return dict(sorted(Counter(Path(path).suffix.lower() or "[no extension]" for path in paths).items()))


def _finding_keys(scan: ScanResult) -> set[tuple[str, str, str | None]]:
    return {(finding.id, finding.classification, finding.file) for finding in scan.findings}


def _finding_records(items: set[tuple[str, str, str | None]]) -> list[dict[str, str | None]]:
    return [{"id": identifier, "classification": classification, "file": file} for identifier, classification, file in sorted(items, key=lambda item: (item[0], item[1], item[2] or ""))]


def _release_inventory(scan: ScanResult) -> dict[str, object]:
    return {
        "file_count": len(scan.files),
        "java_source_count": sum(item["path"].endswith(".java") for item in scan.files),
        "jar_inventory": [{"path": item["path"], "class_file_majors": item["class_file_majors"], "java_levels": item["java_levels"]} for item in scan.jars],
        "estimated_original_environment": {"starsector": scan.estimated_starsector, "java": scan.estimated_java},
        "finding_count": len(scan.findings),
    }


def evaluate_releases(before_directory: Path, after_directory: Path, target: TargetProfile | None = None) -> dict[str, object]:
    """Compare two mod releases without changing either input or claiming runtime equivalence."""
    before, after = before_directory.expanduser().resolve(), after_directory.expanduser().resolve()
    if before == after:
        raise ValueError("Release evaluation requires two distinct mod directories.")
    if not before.is_dir() or not after.is_dir():
        raise ValueError("Release evaluation requires two existing mod directories.")
    if not (before / "mod_info.json").is_file() or not (after / "mod_info.json").is_file():
        raise ValueError("Release evaluation requires mod_info.json at both selected mod roots.")
    before_scan, after_scan = scan_mod(before, target), scan_mod(after, target)
    before_hashes, after_hashes = _tree_hashes(before), _tree_hashes(after)
    shared = set(before_hashes) & set(after_hashes)
    identical = {path for path in shared if before_hashes[path] == after_hashes[path]}
    changed = shared - identical
    before_only, after_only = set(before_hashes) - set(after_hashes), set(after_hashes) - set(before_hashes)
    before_findings, after_findings = _finding_keys(before_scan), _finding_keys(after_scan)
    same_mod_id = bool(before_scan.metadata.get("id")) and before_scan.metadata.get("id") == after_scan.metadata.get("id")
    return {
        "schema_version": 1,
        "mode": "READ_ONLY_RELEASE_EVALUATION",
        "assessment": "PARTIALLY_COMPARABLE" if same_mod_id and identical else "INSUFFICIENT_EVIDENCE",
        "comparability": {
            "same_declared_mod_id": same_mod_id,
            "content_continuity": "EVIDENCE_ONLY",
            "bytecode_comparison": "UNAVAILABLE" if not before_scan.jars or not after_scan.jars else "NOT_REQUESTED",
            "runtime_validation": "NOT_PERFORMED",
            "limitations": ["Matching files and scanner findings do not prove behavioral or save compatibility.", "Runtime validation requires an explicit game launch profile and controlled scenario."],
        },
        "before": _release_inventory(before_scan),
        "after": _release_inventory(after_scan),
        "content": {"shared_path_count": len(shared), "identical_file_count": len(identical), "changed_file_count": len(changed), "before_only_file_count": len(before_only), "after_only_file_count": len(after_only), "changed_paths": sorted(changed), "before_only_extensions": _extension_counts(before_only), "after_only_extensions": _extension_counts(after_only)},
        "finding_delta": {"resolved": _finding_records(before_findings - after_findings), "introduced": _finding_records(after_findings - before_findings), "shared_count": len(before_findings & after_findings)},
    }
