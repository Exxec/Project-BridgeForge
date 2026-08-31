from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _inside(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _copy_tree(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination, symlinks=True)


def _manifest_path(workspace: Path) -> Path:
    return workspace / "workspace-manifest.json"


def _read_manifest(workspace: Path) -> dict:
    path = _manifest_path(workspace)
    if not path.is_file():
        raise ValueError(f"Not a Bridgeforge workspace: {workspace}")
    return json.loads(path.read_text(encoding="utf-8"))


def _write_manifest(workspace: Path, manifest: dict) -> None:
    _manifest_path(workspace).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def create_workspace(source: Path, destination: Path) -> Path:
    source = source.expanduser().resolve()
    destination = destination.expanduser().resolve()
    if not source.is_dir():
        raise ValueError(f"Input mod directory does not exist: {source}")
    if destination.exists():
        raise ValueError(f"Workspace destination already exists: {destination}")
    if _inside(destination, source):
        raise ValueError("Workspace must not be created inside the input mod directory.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    original = destination / "original-reference"
    working = destination / "working-copy"
    _copy_tree(source, original)
    _copy_tree(source, working)
    checkpoints = destination / "checkpoints"
    checkpoints.mkdir()
    _copy_tree(working, checkpoints / "00-original")
    manifest = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "source_path": str(source),
        "original_reference": "original-reference",
        "working_copy": "working-copy",
        "checkpoints": ["00-original"],
        "events": [{"type": "workspace-created", "checkpoint": "00-original"}],
    }
    _write_manifest(destination, manifest)
    return destination


def workspace_paths(workspace: Path) -> tuple[Path, Path, dict]:
    workspace = workspace.expanduser().resolve()
    manifest = _read_manifest(workspace)
    original = workspace / manifest["original_reference"]
    working = workspace / manifest["working_copy"]
    if not original.is_dir() or not working.is_dir():
        raise ValueError("Workspace is missing its original reference or working copy.")
    return original, working, manifest


def checkpoint(workspace: Path, name: str, event_type: str) -> Path:
    _, working, manifest = workspace_paths(workspace)
    if not name or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for char in name):
        raise ValueError("Checkpoint names may contain only lowercase letters, numbers, hyphens, and underscores.")
    target = workspace.expanduser().resolve() / "checkpoints" / name
    if target.exists():
        raise ValueError(f"Checkpoint already exists: {name}")
    _copy_tree(working, target)
    manifest["checkpoints"].append(name)
    manifest["events"].append({"type": event_type, "checkpoint": name, "at": datetime.now(UTC).isoformat()})
    _write_manifest(workspace.expanduser().resolve(), manifest)
    return target


def rollback(workspace: Path, checkpoint_name: str) -> None:
    workspace = workspace.expanduser().resolve()
    _, working, manifest = workspace_paths(workspace)
    if checkpoint_name not in manifest["checkpoints"]:
        raise ValueError(f"Unknown checkpoint: {checkpoint_name}")
    checkpoint_path = workspace / "checkpoints" / checkpoint_name
    if not checkpoint_path.is_dir():
        raise ValueError(f"Checkpoint contents unavailable: {checkpoint_name}")
    shutil.rmtree(working)
    _copy_tree(checkpoint_path, working)
    manifest["events"].append({"type": "rollback", "checkpoint": checkpoint_name, "at": datetime.now(UTC).isoformat()})
    _write_manifest(workspace, manifest)

