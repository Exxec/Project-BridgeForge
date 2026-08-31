from __future__ import annotations

import difflib
import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import TargetProfile
from .workspace import checkpoint, sha256_file, workspace_paths


@dataclass(frozen=True)
class MigrationRule:
    id: str
    classification: str
    confidence: str
    description: str
    file: str
    json_key: str
    value_from_target: str


@dataclass
class PlannedMigration:
    rule_id: str
    classification: str
    confidence: str
    description: str
    file: str
    before_sha256: str
    after_sha256: str
    before_content: str
    after_content: str
    diff: str


def _rules_path() -> Path:
    return Path(__file__).with_name("rules") / "v0_2.json"


def load_rules(path: Path | None = None) -> list[MigrationRule]:
    raw = json.loads((path or _rules_path()).read_text(encoding="utf-8"))
    return [MigrationRule(**entry) for entry in raw["rules"]]


def _value_for(rule: MigrationRule, target: TargetProfile) -> str:
    if rule.value_from_target == "starsector":
        return target.starsector
    raise ValueError(f"Unsupported rule value source: {rule.value_from_target}")


def _render_json(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def build_plan(workspace: Path, target: TargetProfile, rules_path: Path | None = None) -> dict[str, Any]:
    workspace = workspace.expanduser().resolve()
    _, working, _ = workspace_paths(workspace)
    migrations: list[PlannedMigration] = []
    for rule in load_rules(rules_path):
        path = working / rule.file
        if not path.is_file():
            continue
        try:
            original = path.read_text(encoding="utf-8-sig")
            document = json.loads(original)
        except (OSError, json.JSONDecodeError):
            continue
        desired = _value_for(rule, target)
        if document.get(rule.json_key) == desired:
            continue
        document[rule.json_key] = desired
        updated = _render_json(document)
        migrations.append(PlannedMigration(
            rule_id=rule.id, classification=rule.classification, confidence=rule.confidence,
            description=rule.description, file=rule.file,
            before_sha256=sha256_file(path),
            after_sha256=__import__("hashlib").sha256(updated.encode("utf-8")).hexdigest(),
            before_content=original, after_content=updated,
            diff="".join(difflib.unified_diff(original.splitlines(keepends=True), updated.splitlines(keepends=True), fromfile=f"a/{rule.file}", tofile=f"b/{rule.file}")),
        ))
    plan = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "target": asdict(target),
        "working_copy": str(working),
        "migrations": [asdict(migration) for migration in migrations],
    }
    (workspace / "migration-plan.json").write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    checkpoint(workspace, "01-scanned", "plan-created")
    return plan


def apply_plan(workspace: Path, approved_rule_ids: set[str]) -> dict[str, Any]:
    workspace = workspace.expanduser().resolve()
    _, working, _ = workspace_paths(workspace)
    plan_path = workspace / "migration-plan.json"
    if not plan_path.is_file():
        raise ValueError("No migration plan found. Run `bridgeforge plan` first.")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    applied: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    diff_chunks: list[str] = []
    for migration in plan["migrations"]:
        if migration["rule_id"] not in approved_rule_ids:
            skipped.append({"rule_id": migration["rule_id"], "reason": "not explicitly approved"})
            continue
        path = working / migration["file"]
        if not path.is_file() or sha256_file(path) != migration["before_sha256"]:
            raise ValueError(f"Working copy changed since planning: {migration['file']}. Re-plan before applying.")
        temp_path = path.with_suffix(path.suffix + ".bridgeforge-tmp")
        temp_path.write_text(migration["after_content"], encoding="utf-8")
        os.replace(temp_path, path)
        applied.append({key: migration[key] for key in ("rule_id", "classification", "confidence", "file", "before_sha256", "after_sha256")})
        diff_chunks.append(migration["diff"])
    if applied:
        checkpoint(workspace, "02-approved-fixes", "migrations-applied")
    manifest = {
        "schema_version": 1,
        "applied_at": datetime.now(UTC).isoformat(),
        "applied": applied,
        "skipped": skipped,
        "working_copy": str(working),
    }
    (workspace / "migration-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (workspace / "patches").mkdir(exist_ok=True)
    (workspace / "patches" / "modernization.diff").write_text("".join(diff_chunks), encoding="utf-8")
    report = ["# Bridgeforge V0.2 apply report", "", f"- Applied migrations: {len(applied)}", f"- Skipped migrations: {len(skipped)}", "", "## Scope boundary", "", "Only explicitly approved rules were applied to the working copy. The original reference and input mod remain untouched.", ""]
    (workspace / "APPLY_REPORT.md").write_text("\n".join(report), encoding="utf-8")
    return manifest
