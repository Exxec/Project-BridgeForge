from __future__ import annotations

import json
import shutil
from pathlib import Path

from .workspace import workspace_paths


def inspect_workspace(workspace: Path) -> dict:
    workspace = workspace.expanduser().resolve()
    original, working, manifest = workspace_paths(workspace)
    plan_path = workspace / "migration-plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8")) if plan_path.is_file() else {"migrations": []}
    return {"workspace": str(workspace), "original_reference": str(original), "working_copy": str(working), "checkpoints": manifest["checkpoints"], "planned_migrations": [{key: item[key] for key in ("rule_id", "classification", "file", "diff")} for item in plan["migrations"]]}


def export_patch(workspace: Path, output: Path) -> Path:
    workspace = workspace.expanduser().resolve()
    original, _, _ = workspace_paths(workspace)
    output = output.expanduser().resolve()
    if output.exists():
        raise ValueError(f"Patch export destination already exists: {output}")
    try:
        output.relative_to(original)
        raise ValueError("Patch export must not be written inside the original reference.")
    except ValueError as exc:
        if str(exc).startswith("Patch export"):
            raise
    output.mkdir(parents=True)
    for name in ("migration-manifest.json", "migration-plan.json"):
        source = workspace / name
        if source.is_file():
            shutil.copy2(source, output / name)
    diff = workspace / "patches" / "modernization.diff"
    if diff.is_file():
        shutil.copy2(diff, output / "modernization.diff")
    (output / "README.md").write_text("# Bridgeforge patch package\n\nThis package contains only migration metadata and a diff. Apply it to a copy of the mod after reviewing every change; it does not include the original mod.\n", encoding="utf-8")
    return output
