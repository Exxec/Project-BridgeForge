from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .build import compile_feedback, create_build_profile, run_compile
from .migrate import apply_plan, build_plan
from .models import TargetProfile
from .review import create_review_bundle
from .save_risk import analyze_save_risk
from .validate import validate_workspace
from .report import write_artifacts
from .scanner import scan_mod
from .workspace import workspace_paths


def run_pipeline(workspace: Path, target: TargetProfile, rules: list[Path] | None = None, approved: set[str] | None = None, apply_safe: bool = False, jdk: Path | None = None, api_jars: list[Path] | None = None, dependency_jars: list[Path] | None = None, compile_requested: bool = False) -> dict:
    workspace = workspace.expanduser().resolve()
    _, working, _ = workspace_paths(workspace)
    scan = scan_mod(working, target)
    scan_report, scan_manifest = write_artifacts(scan, workspace / "scan-artifacts")
    plan = build_plan(workspace, target, rules)
    applied = apply_plan(workspace, approved or set(), apply_safe)
    build = None
    compile_result = None
    feedback = None
    if jdk is not None:
        build = asdict(create_build_profile(workspace, target, jdk, api_jars or [], dependency_jars or []))
    if compile_requested:
        if build is None:
            raise ValueError("Pipeline compile requires --jdk and a generated build profile.")
        compile_result = run_compile(workspace)
        feedback = compile_feedback(workspace)
    validation = validate_workspace(workspace, target)
    save_risk = analyze_save_risk(workspace)
    bundle = create_review_bundle(workspace)
    result = {"schema_version": 1, "target": asdict(target), "scan": {"report": str(scan_report), "manifest": str(scan_manifest), "finding_count": len(scan.findings)}, "plan": {"migration_count": len(plan["migrations"])}, "apply": {"applied_count": len(applied["applied"])}, "build_profile": build is not None, "compile": None if compile_result is None else compile_result["success"], "compile_feedback": None if feedback is None else len(feedback["findings"]), "validation": validation, "save_risk": save_risk, "review_bundle": str(bundle)}
    (workspace / "pipeline-result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = ["# Bridgeforge V1.0 modernization report", "", f"- Target: Starsector {target.starsector}, Java {target.java}", f"- Planned migrations: {len(plan['migrations'])}", f"- Applied migrations: {len(applied['applied'])}", f"- Compile: {'NOT RUN' if compile_result is None else ('PASS' if compile_result['success'] else 'FAILED')}", f"- Structural validation: {validation['structural_validation']['status']}", f"- Runtime validation: {validation['runtime_validation']['status']}", f"- Save risk: {save_risk['risk']}", "", "## Scope boundary", "", "This pipeline preserves the original reference, applies only explicitly authorized changes, and does not claim runtime or behavioral correctness when runtime validation is unconfigured.", ""]
    (workspace / "MODERNIZATION_REPORT.md").write_text("\n".join(report), encoding="utf-8")
    return result
