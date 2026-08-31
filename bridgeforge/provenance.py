from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from .workspace import sha256_file, workspace_paths


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def write_provenance(workspace: Path) -> dict:
    workspace = workspace.expanduser().resolve()
    original, working, manifest = workspace_paths(workspace)
    artifacts: dict[str, str] = {}
    for name in ("migration-plan.json", "migration-manifest.json", "build-profile.json", "build-result.json"):
        path = workspace / name
        if path.is_file():
            artifacts[name] = sha256_file(path)
    result = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "workspace": str(workspace),
        "source_tree_sha256": manifest.get("source_tree_sha256"),
        "original_reference_tree_sha256": _tree_hash(original),
        "working_copy_tree_sha256": _tree_hash(working),
        "artifacts": artifacts,
    }
    (workspace / "provenance.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result
