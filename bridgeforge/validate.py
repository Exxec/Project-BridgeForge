from __future__ import annotations

import json
from pathlib import Path

from .models import TargetProfile
from .scanner import scan_mod
from .workspace import sha256_file, workspace_paths


def _tree_hashes(root: Path) -> dict[str, str]:
    return {path.relative_to(root).as_posix(): sha256_file(path) for path in sorted(root.rglob("*")) if path.is_file()}


def _active_java_sources(root: Path) -> set[str]:
    excluded_directories = {".git", ".idea", "build", "disabled_files", "jar", "out"}
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*.java")
        if not any(part in excluded_directories for part in path.relative_to(root).parts)
    }


def _compile_validation(workspace: Path, working: Path) -> dict:
    """Assess whether the recorded compile covered every active source file.

    A successful one-file probe is useful while diagnosing a crash, but it is
    not release-level evidence. Validation therefore exposes partial coverage
    as REVIEW instead of treating any successful javac invocation as a full
    source-compatibility pass.
    """
    compile_result_path = workspace / "build-result.json"
    active_sources = _active_java_sources(working)
    if not compile_result_path.is_file():
        return {
            "status": "REQUIRED_NOT_RUN" if active_sources else "NOT_APPLICABLE",
            "result_path": None,
            "active_source_count": len(active_sources),
            "compiled_source_count": 0,
            "missing_sources": sorted(active_sources),
            "reason": "Active Java sources require a complete, explicit classpath and full-project compilation before a revival can claim source compatibility." if active_sources else "No active Java sources were found.",
        }
    compile_result = json.loads(compile_result_path.read_text(encoding="utf-8"))
    if compile_result.get("status") == "UNAVAILABLE":
        return {
            "status": "UNAVAILABLE",
            "result_path": str(compile_result_path),
            "active_source_count": len(active_sources),
            "compiled_source_count": 0,
            "missing_sources": sorted(active_sources),
            "reason": compile_result.get("reason", "The requested compile classpath is unavailable."),
        }
    compiled_sources: set[str] = set()
    for argument in compile_result.get("command", []):
        if not isinstance(argument, str) or not argument.endswith(".java"):
            continue
        try:
            compiled_sources.add(Path(argument).resolve().relative_to(working).as_posix())
        except ValueError:
            continue
    missing_sources = sorted(active_sources - compiled_sources)
    if not compile_result.get("success"):
        status = "FAILED"
    elif missing_sources:
        status = "PARTIAL"
    else:
        status = "PASS"
    return {
        "status": status,
        "result_path": str(compile_result_path),
        "active_source_count": len(active_sources),
        "compiled_source_count": len(compiled_sources),
        "missing_sources": missing_sources,
        "reason": "Successful compilation did not include every active Java source file." if status == "PARTIAL" else None,
    }


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
    compile_validation = _compile_validation(workspace, working)
    result = {
        "schema_version": 1,
        "reference_integrity": {"status": "PASS" if reference_intact else "FAILED", "original_file_count": len(original_hashes), "baseline_file_count": len(baseline_hashes)},
        "structural_validation": structural,
        "compile_validation": compile_validation,
        "runtime_validation": {"status": "NOT_CONFIGURED", "reason": "Bridgeforge will not launch Starsector or execute mod code until an explicit runtime profile is supplied."},
    }
    (workspace / "validation.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = ["# Bridgeforge validation report", "", f"- Original reference integrity: {result['reference_integrity']['status']}", f"- Structural validation: {structural['status']}", f"- Compile validation: {result['compile_validation']['status']}", f"- Compile source coverage: {compile_validation['compiled_source_count']}/{compile_validation['active_source_count']}", f"- Runtime validation: {result['runtime_validation']['status']}", ""]
    if compile_validation["status"] in {"REQUIRED_NOT_RUN", "UNAVAILABLE", "PARTIAL"}:
        report.extend(["## Compile-evidence gap", "", compile_validation["reason"] or "Compile validation is incomplete.", ""])
    report.extend(["Runtime validation was not performed; this report does not claim the mod loads or behaves correctly.", ""])
    (workspace / "VALIDATION_REPORT.md").write_text("\n".join(report), encoding="utf-8")
    return result
