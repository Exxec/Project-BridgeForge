from __future__ import annotations

import shutil
from pathlib import Path

from .packs import compatible, discover_packs
from .workspace import workspace_paths


def doctor(workspace: Path | None = None) -> dict:
    packs = discover_packs()
    incompatible = [pack.id for pack in packs if not compatible(pack)]
    checks = [
        {"id": "python", "status": "PASS"},
        {"id": "java", "status": "PASS" if shutil.which("java") else "UNKNOWN"},
        {"id": "javac", "status": "PASS" if shutil.which("javac") else "UNKNOWN"},
        {"id": "migration-packs", "status": "PASS" if not incompatible else "FAILED", "count": len(packs), "incompatible": incompatible},
    ]
    if workspace is not None:
        try:
            workspace_paths(workspace)
            checks.append({"id": "workspace", "status": "PASS"})
        except ValueError as exc:
            checks.append({"id": "workspace", "status": "FAILED", "detail": str(exc)})
    return {"schema_version": 1, "status": "PASS" if all(item["status"] == "PASS" for item in checks) else "REVIEW", "checks": checks}
