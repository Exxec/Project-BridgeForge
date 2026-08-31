from __future__ import annotations

import json
import zipfile
from collections import defaultdict
from pathlib import Path

from .workspace import workspace_paths


def detect_conflicts(workspace: Path) -> dict:
    workspace = workspace.expanduser().resolve()
    _, working, _ = workspace_paths(workspace)
    findings: list[dict[str, object]] = []
    plan_path = workspace / "migration-plan.json"
    if plan_path.is_file():
        for conflict in json.loads(plan_path.read_text(encoding="utf-8")).get("conflicts", []):
            findings.append({"kind": "planned-migration", **conflict})
    owners: dict[str, list[str]] = defaultdict(list)
    for jar in sorted(working.rglob("*.jar")):
        try:
            with zipfile.ZipFile(jar) as archive:
                for entry in archive.infolist():
                    if entry.filename.endswith(".class"):
                        owners[entry.filename].append(jar.relative_to(working).as_posix())
        except (OSError, zipfile.BadZipFile) as exc:
            findings.append({"kind": "unreadable-jar", "file": jar.relative_to(working).as_posix(), "detail": str(exc)})
    for class_name, jars in sorted(owners.items()):
        if len(jars) > 1:
            findings.append({"kind": "duplicate-class", "class": class_name, "jars": jars})
    result = {"schema_version": 1, "status": "CONFLICTS_FOUND" if findings else "PASS", "findings": findings}
    (workspace / "conflicts.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result
