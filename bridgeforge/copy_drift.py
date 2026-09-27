from __future__ import annotations

import fnmatch
import hashlib
import re
from pathlib import Path

INCLUDED_DIRS = ("data", "jars", "graphics", "sounds")  # always included; any other top-level folder is too (below)
# Top-level folders that never ship. Everything else is copied: the game loads resources by path from the mod
# root, and Flux Reticle keeps its sprites in `sun_fr/graphics/` (settings.json points there). The old fixed
# INCLUDED_DIRS list left that folder out, so the rig copy crashed at startup with "Error loading
# [sun_fr/graphics/half.png]" (GRP-3, 2026-09-27), and release/archive would have shipped it broken.
EXCLUDED_TOP_DIRS = ("scratch", "out", "build", "disabled_files", "bin", "gradle", "meta-inf", "production", "test")  # tool and build folders
# Every root file ships: mods load arbitrary names from the root (Transfer All Items reads
# "transfer_all_items_settings.json.default"; the old *.json-style allowlist dropped it, GRP-7 Fatal 2026-09-27).
INCLUDED_ROOT_FILE_GLOBS = ("*",)
# OS and VCS litter never ships: the game ignores it and it only bloats or confuses a release.
EXCLUDE_DIR_NAME_GLOBS = ("reports", "src*", "__MACOSX", ".git", ".svn", ".idea", ".vscode")
EXCLUDE_FILE_NAME_GLOBS = ("*.bak", "*.iml", "*.pre-*", "*orig-backup*", "src.zip", "Thumbs.db", "desktop.ini", ".DS_Store")


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
    extra = sorted(child.name for child in root.iterdir() if child.is_dir() and child.name not in INCLUDED_DIRS
                   and not child.name.startswith(".") and child.name.lower() not in EXCLUDED_TOP_DIRS
                   and not any(fnmatch.fnmatch(child.name, pattern) for pattern in EXCLUDE_DIR_NAME_GLOBS))
    for name in (*INCLUDED_DIRS, *extra):
        base = root / name
        if not base.is_dir():
            continue
        for item in base.rglob("*"):
            if not item.is_file():
                continue
            relative = item.relative_to(root).as_posix()
            if _is_excluded(relative) or _is_excluded(relative.split("/", 1)[-1]):
                continue
            files[relative] = item
    for item in root.iterdir():
        if not item.is_file() or not any(fnmatch.fnmatch(item.name.lower(), pattern) for pattern in INCLUDED_ROOT_FILE_GLOBS):
            continue
        if not _is_excluded(item.name):
            files[item.name] = item
    mod_info = root / "mod_info.json"
    if mod_info.is_file():
        files["mod_info.json"] = mod_info
        # Jars mod_info.json declares are runtime payload wherever they live. SEEKER loads
        # "jar/SEEKER.jar" (singular), which the fixed INCLUDED_DIRS never saw: drift reported PASS,
        # --sync never copied a patched jar, and a release would have shipped without its code
        # (live bug BF-DRIFT-01, 2026-09-13).
        for relative in _declared_jars(mod_info):
            item = root / relative
            if item.is_file() and not _is_excluded(relative):
                files[relative] = item
    return files


_JARS_ARRAY = re.compile(r'"jars"\s*:\s*\[([^\]]*)\]', re.DOTALL)


def _declared_jars(mod_info: Path) -> list[str]:
    """Relative jar paths from mod_info.json's "jars" array (tolerant of comments/odd JSON)."""
    try:
        text = mod_info.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return []
    match = _JARS_ARRAY.search(text)
    if not match:
        return []
    return [entry.replace("\\", "/").lstrip("./") for entry in re.findall(r'"([^"]+)"', match.group(1))]


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
