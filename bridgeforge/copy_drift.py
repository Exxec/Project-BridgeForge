from __future__ import annotations

import fnmatch
import hashlib
from pathlib import Path

INCLUDED_DIRS = ("data", "jars", "graphics", "sounds")
EXCLUDE_DIR_NAME_GLOBS = ("reports", "src*")
EXCLUDE_FILE_NAME_GLOBS = ("*.bak", "*.pre-*", "*orig-backup*", "src.zip")


def _is_excluded(relative_posix_path: str) -> bool:
    parts = relative_posix_path.split("/")
    for part in parts[:-1]:
        if any(fnmatch.fnmatch(part, pattern) for pattern in EXCLUDE_DIR_NAME_GLOBS):
            return True
    name = parts[-1]
    return any(fnmatch.fnmatch(name, pattern) for pattern in EXCLUDE_FILE_NAME_GLOBS)


def _find_mod_root(path: Path) -> Path:
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"{root} is not an existing directory.")
    if (root / "mod_info.json").is_file():
        return root
    candidates = sorted(child for child in root.iterdir() if child.is_dir() and (child / "mod_info.json").is_file())
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise ValueError(f"No mod_info.json found at {root} or one directory below it.")
    raise ValueError(f"Multiple mod_info.json candidates below {root}; ambiguous mod root.")


def _collect(root: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for name in INCLUDED_DIRS:
        base = root / name
        if not base.is_dir():
            continue
        for item in base.rglob("*"):
            if not item.is_file():
                continue
            relative = item.relative_to(root).as_posix()
            if _is_excluded(relative):
                continue
            files[relative] = item
    mod_info = root / "mod_info.json"
    if mod_info.is_file():
        files["mod_info.json"] = mod_info
    return files


def compare_copies(working_copy: Path, deployed_copy: Path) -> dict[str, object]:
    """Hash-compare a mod working copy against its deployed/test-rig copy; never modifies either side."""
    working_root = _find_mod_root(working_copy)
    deployed_root = _find_mod_root(deployed_copy)
    working_files = _collect(working_root)
    deployed_files = _collect(deployed_root)
    working_names = set(working_files)
    deployed_names = set(deployed_files)

    missing_in_deployed = sorted(working_names - deployed_names)
    extra_in_deployed = sorted(deployed_names - working_names)
    different: list[dict[str, str]] = []
    for name in sorted(working_names & deployed_names):
        working_path, deployed_path = working_files[name], deployed_files[name]
        working_hash = hashlib.sha256(working_path.read_bytes()).hexdigest()
        deployed_hash = hashlib.sha256(deployed_path.read_bytes()).hexdigest()
        if working_hash == deployed_hash:
            continue
        working_mtime, deployed_mtime = working_path.stat().st_mtime, deployed_path.stat().st_mtime
        if working_mtime > deployed_mtime:
            newer_side = "working"
        elif deployed_mtime > working_mtime:
            newer_side = "deployed"
        else:
            newer_side = "equal"
        different.append({"path": name, "newer_side": newer_side})

    drift_count = len(missing_in_deployed) + len(extra_in_deployed) + len(different)
    return {
        "schema_version": 1,
        "mode": "READ_ONLY_COPY_DRIFT",
        "working_root": str(working_root),
        "deployed_root": str(deployed_root),
        "missing_in_deployed": missing_in_deployed,
        "different": different,
        "extra_in_deployed": extra_in_deployed,
        "drift_count": drift_count,
        "status": "PASS" if drift_count == 0 else "DRIFT",
    }
