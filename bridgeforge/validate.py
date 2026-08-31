from __future__ import annotations

import json
from pathlib import Path

from .models import TargetProfile
from .scanner import scan_mod
from .workspace import sha256_file, workspace_paths


def _tree_hashes(root: Path) -> dict[str, str]:
    return {path.relative_to(root).as_posix(): sha256_file(path) for path in sorted(root.rglob("*")) if path.is_file()}


def validate_workspace(workspace: Path, target: TargetProfile) -> dict:
    workspace = workspace.expanduser().resolve()
    original, working, manifest = workspace_paths(workspace)
    baseline = workspace / "checkpoints" / "00-original"
    original_hashes = _tree_hashes(original)
    baseline_hashes = _tree_hashes(baseline) if baseline.is_dir() else {}
    reference_intact = original_hashes == baseline_hashes
    scan = scan_mod(working, target)
    structural = {
        "status": "PASS" if not any(f.severity in {"critical", "high"} for f in scan.findings) else "REVIEW",
        "findings": [f.__dict__ for f in scan.findings],
    }
    compile_result_path = workspace / "build-result.json"
    compile_result = json.loads(compile_result_path.read_text(encoding="utf-8")) if compile_result_path.is_file() else None
    result = {
        "schema_version": 1,
        "reference_integrity": {"status": "PASS" if reference_intact else "FAILED", "original_file_count": len(original_hashes), "baseline_file_count": len(baseline_hashes)},
        "structural_validation": structural,
        "compile_validation": {"status": "NOT_RUN" if compile_result is None else ("PASS" if compile_result["success"] else "FAILED"), "result_path": str(compile_result_path) if compile_result else None},
        "runtime_validation": {"status": "NOT_CONFIGURED", "reason": "Bridgeforge will not launch Starsector or execute mod code until an explicit runtime profile is supplied."},
    }
    (workspace / "validation.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = ["# Bridgeforge validation report", "", f"- Original reference integrity: {result['reference_integrity']['status']}", f"- Structural validation: {structural['status']}", f"- Compile validation: {result['compile_validation']['status']}", f"- Runtime validation: {result['runtime_validation']['status']}", "", "Runtime validation was not performed; this report does not claim the mod loads or behaves correctly.", ""]
    (workspace / "VALIDATION_REPORT.md").write_text("\n".join(report), encoding="utf-8")
    return result
