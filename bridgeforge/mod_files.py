"""Finding a mod's folder and reading its mod_info.json, for every module (ROADMAP-3 96.5 A4).

Before, each module wrote its own: four lenient mod_info readers and five folder resolvers in three shapes, two of each
shape identical but for the error they raised. These are those shapes, once:

- `read_mod_info(folder)`: the folder's mod_info.json as an object, read leniently (the game's own JSON dialect), or None.
- `find_mod_root(path)`: the folder holding mod_info.json, the path itself or its only child that does; raises
  ModRootError when there is none or more than one. `nearest_mod_root` is the same, returning None instead.
- `workspace_or_mod_root(path)`: a workspace's `working/`, else the path itself when it is a mod folder.

Resolvers with other rules stay where they are and say why: build_tag searches two levels down, supersession reads a
workspace's original/, target_impact follows Done/'s layout and master_log skips original/ and workspace/.
"""
from __future__ import annotations

from pathlib import Path

MOD_INFO = "mod_info.json"


class ModRootError(ValueError):
    """No mod folder where one was expected, or more than one."""


def read_mod_info(folder: Path) -> dict | None:
    """`folder/mod_info.json` as an object, or None when it is missing, unreadable or not an object."""
    from bridgeforge.scan.scanner import _load_lenient_json_file

    path = Path(folder) / MOD_INFO
    info = _load_lenient_json_file(path) if path.is_file() else None  # the lenient reader returns None on any read or parse error
    return info if isinstance(info, dict) else None


def _candidates(root: Path) -> list[Path]:
    return sorted(child for child in root.iterdir() if child.is_dir() and (child / MOD_INFO).is_file())


def find_mod_root(path: Path) -> Path:
    """The folder holding mod_info.json: `path` itself, or its only child that holds one (a zip's or a release's wrapper)."""
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        raise ModRootError(f"{root} is not an existing directory.")
    if (root / MOD_INFO).is_file():
        return root
    candidates = _candidates(root)
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise ModRootError(f"No mod_info.json found at {root} or one directory below it.")
    raise ModRootError(f"Multiple mod_info.json candidates below {root}; ambiguous mod root.")


def nearest_mod_root(path: Path) -> Path | None:
    """`find_mod_root` without raising: None when there is no mod folder or more than one. The path is not resolved."""
    folder = Path(path)
    if (folder / MOD_INFO).is_file():
        return folder
    nested = [p for p in folder.iterdir() if p.is_dir() and (p / MOD_INFO).is_file()] if folder.is_dir() else []
    return nested[0] if len(nested) == 1 else None


def workspace_or_mod_root(path: Path) -> Path:
    """A workspace's `working/` when it holds mod_info.json, else `path` itself when it does."""
    path = Path(path).expanduser().resolve()
    if (path / "working" / MOD_INFO).is_file():
        return path / "working"
    if (path / MOD_INFO).is_file():
        return path
    raise ModRootError(f"{path} is not a mod folder (no mod_info.json) or a workspace holding working/.")
