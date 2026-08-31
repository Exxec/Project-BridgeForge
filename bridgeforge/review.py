from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .workspace import workspace_paths


def _read_json(path: Path, default: dict) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def create_review_bundle(workspace: Path) -> Path:
    workspace = workspace.expanduser().resolve()
    _, working, _ = workspace_paths(workspace)
    plan = _read_json(workspace / "migration-plan.json", {"migrations": []})
    feedback = _read_json(workspace / "compile-feedback.json", {"findings": []})
    affected = sorted({entry["file"] for entry in plan["migrations"]} | {candidate for finding in feedback["findings"] for candidate in finding.get("planned_rule_candidates", []) if "/" in candidate})
    # Compiler candidates are rule IDs, not paths; planned files remain the authoritative scope.
    affected = sorted({entry["file"] for entry in plan["migrations"]})
    bundle = workspace / "review-bundles" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bundle.mkdir(parents=True)
    (bundle / "findings.json").write_text(json.dumps({"plan": plan["migrations"], "compile_feedback": feedback["findings"]}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (bundle / "affected-files.txt").write_text("\n".join(affected) + ("\n" if affected else ""), encoding="utf-8")
    (bundle / "acceptance-criteria.md").write_text("# Acceptance criteria\n\n- Change only files in `affected-files.txt`.\n- Preserve persistent IDs, memory keys, reward formulas, and serialized class names unless an explicit migration says otherwise.\n- Do not modify the original reference or input mod.\n- Explain every semantic change and leave unresolved ambiguity for review.\n- Run the recorded build profile when available.\n", encoding="utf-8")
    (bundle / "prompt.md").write_text("# Bridgeforge scoped review task\n\nUse `findings.json` and the included affected working-copy files to resolve only the documented REVIEW/MANUAL issues. Do not broaden the change set. Return a patch and an explanation of any behavior-sensitive decision.\n", encoding="utf-8")
    (bundle / "context.md").write_text(f"# Context\n\n- Workspace: `{workspace}`\n- Working copy: `{working}`\n- Created: {datetime.now(timezone.utc).isoformat()}\n- Original source remains outside this bundle and must not be modified.\n", encoding="utf-8")
    files_dir = bundle / "working-copy-files"
    for relative in affected:
        source = working / relative
        if source.is_file():
            destination = files_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    return bundle
