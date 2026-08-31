from __future__ import annotations

import difflib
import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import TargetProfile
from .java_ast import AstUnavailable, analyze_sources
from .workspace import checkpoint, sha256_file, workspace_paths


@dataclass(frozen=True)
class MigrationRule:
    pack_id: str
    id: str
    classification: str
    confidence: str
    description: str
    file: str = ""
    json_key: str = ""
    value_from_target: str = ""
    action: str = "set-json-value"
    from_import: str = ""
    to_import: str = ""


@dataclass
class PlannedMigration:
    rule_id: str
    pack_id: str
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


def load_rules(paths: list[Path] | None = None) -> list[MigrationRule]:
    rules: list[MigrationRule] = []
    seen_ids: set[str] = set()
    for path in paths or [_rules_path()]:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            pack = raw["pack"]
            if pack["schema_version"] != 1 or not pack["id"]:
                raise ValueError("unsupported schema version or missing pack id")
            entries = raw["rules"]
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid migration pack {path}: {exc}") from exc
        for entry in entries:
            try:
                rule = MigrationRule(pack_id=pack["id"], **entry)
            except TypeError as exc:
                raise ValueError(f"Invalid rule in migration pack {path}: {exc}") from exc
            if rule.id in seen_ids:
                raise ValueError(f"Duplicate migration rule ID across packs: {rule.id}")
            if rule.classification not in {"SAFE", "REVIEW", "MANUAL", "UNKNOWN"}:
                raise ValueError(f"Invalid classification for rule {rule.id}: {rule.classification}")
            seen_ids.add(rule.id)
            rules.append(rule)
    return rules


def _value_for(rule: MigrationRule, target: TargetProfile) -> str:
    if rule.value_from_target == "starsector":
        return target.starsector
    raise ValueError(f"Unsupported rule value source: {rule.value_from_target}")


def _render_json(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _planned(rule: MigrationRule, file: str, before: str, after: str, path: Path) -> PlannedMigration:
    return PlannedMigration(
        rule_id=rule.id, pack_id=rule.pack_id, classification=rule.classification, confidence=rule.confidence,
        description=rule.description, file=file, before_sha256=sha256_file(path),
        after_sha256=__import__("hashlib").sha256(after.encode("utf-8")).hexdigest(), before_content=before,
        after_content=after, diff="".join(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True), fromfile=f"a/{file}", tofile=f"b/{file}")),
    )


def build_plan(workspace: Path, target: TargetProfile, rules_paths: list[Path] | None = None) -> dict[str, Any]:
    workspace = workspace.expanduser().resolve()
    _, working, _ = workspace_paths(workspace)
    migrations: list[PlannedMigration] = []
    rules = load_rules(rules_paths)
    planned_files: set[str] = set()
    try:
        source_facts = analyze_sources(working)
    except AstUnavailable:
        source_facts = []
    for rule in rules:
        if rule.action == "replace-import":
            if not rule.from_import or not rule.to_import:
                raise ValueError(f"Import rule {rule.id} must provide from_import and to_import")
            for fact in source_facts:
                if fact["kind"] != "import" or fact["value"] != rule.from_import or fact["file"] in planned_files:
                    continue
                relative = str(fact["file"])
                path = working / relative
                before = path.read_text(encoding="utf-8")
                lines = before.splitlines(keepends=True)
                line_index = int(fact["line"]) - 1
                marker = f"import {rule.from_import};"
                if line_index < 0 or line_index >= len(lines) or marker not in lines[line_index]:
                    continue
                after_lines = list(lines)
                after_lines[line_index] = after_lines[line_index].replace(marker, f"import {rule.to_import};", 1)
                after = "".join(after_lines)
                migrations.append(_planned(rule, relative, before, after, path))
                planned_files.add(relative)
            continue
        if rule.action != "set-json-value":
            raise ValueError(f"Unsupported migration action for rule {rule.id}: {rule.action}")
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
        migrations.append(_planned(rule, rule.file, original, updated, path))
        planned_files.add(rule.file)
    plan = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "target": asdict(target),
        "working_copy": str(working),
        "rule_packs": sorted({rule.pack_id for rule in rules}),
        "migrations": [asdict(migration) for migration in migrations],
    }
    (workspace / "migration-plan.json").write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    checkpoint(workspace, "01-scanned", "plan-created")
    return plan


def apply_plan(workspace: Path, approved_rule_ids: set[str], apply_safe: bool = False) -> dict[str, Any]:
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
        approved = migration["rule_id"] in approved_rule_ids or (apply_safe and migration["classification"] == "SAFE")
        if not approved:
            skipped.append({"rule_id": migration["rule_id"], "reason": "not explicitly approved"})
            continue
        path = working / migration["file"]
        if not path.is_file() or sha256_file(path) != migration["before_sha256"]:
            raise ValueError(f"Working copy changed since planning: {migration['file']}. Re-plan before applying.")
        temp_path = path.with_suffix(path.suffix + ".bridgeforge-tmp")
        temp_path.write_text(migration["after_content"], encoding="utf-8")
        os.replace(temp_path, path)
        applied.append({key: migration[key] for key in ("rule_id", "pack_id", "classification", "confidence", "file", "before_sha256", "after_sha256")})
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
