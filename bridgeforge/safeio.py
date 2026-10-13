"""Atomic writes and guarded deletes (ROADMAP item 70, H1.1 and H1.2).

State and report files are written to a temp file in the same folder and swapped in with `os.replace`, so an interrupted run leaves
the old file or the new one, never half of either. 182 `write_text` call sites wrote in place before this module existed.

Deletes go through `safe_rmtree` / `safe_unlink`, which refuse any path outside the roots the caller names (the rig, `scratch/`,
`Done/_replaced-*`, a temp folder), refuse the roots themselves, and refuse to follow a link out of them: deleting through a
junction would have removed the real game install's files.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Iterable


class UnsafePathError(ValueError):
    """A delete was refused because the path is outside the allowed roots, is a root, or reaches outside through a link."""


def atomic_write_bytes(path: Path | str, data: bytes) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return path


def atomic_write_text(path: Path | str, text: str, encoding: str = "utf-8", newline: str | None = None) -> Path:
    """Write `text` to `path` atomically. `newline=""` writes the text as given (no translation); None keeps the platform default."""
    data = text.encode(encoding) if newline == "" else text.replace("\r\n", "\n").replace("\n", os.linesep).encode(encoding)
    return atomic_write_bytes(path, data)


def atomic_write_json(path: Path | str, data: object, **dumps: object) -> Path:
    dumps.setdefault("indent", 2)
    dumps.setdefault("ensure_ascii", False)
    return atomic_write_text(path, json.dumps(data, **dumps) + "\n", newline="")


def _resolved(path: Path | str) -> Path:
    return Path(path).expanduser().resolve()


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def check_deletable(path: Path | str, allowed_roots: Iterable[Path | str]) -> Path:
    """The resolved path if it may be deleted: strictly inside one allowed root (never a root itself), and, when it is itself a link,
    pointing at a place that is also inside that root. Raises UnsafePathError otherwise."""
    roots = [_resolved(r) for r in allowed_roots]
    if not roots:
        raise UnsafePathError("no allowed roots were given")
    raw = Path(path).expanduser()
    target = _resolved(raw)
    for root in roots:
        if target == root:
            raise UnsafePathError(f"{target} is an allowed root itself, not something inside one")
    # The path as written must itself be inside a root (a link inside the root is fine to remove as a link), and so must
    # where it leads: removing a tree through a junction deletes the target's files.
    lexical = Path(os.path.abspath(raw))
    if not any(_inside(lexical, root) or _inside(lexical, Path(os.path.abspath(root))) for root in roots):
        raise UnsafePathError(f"{lexical} is outside the allowed roots: {', '.join(str(r) for r in roots)}")
    if not any(_inside(target, root) for root in roots):
        raise UnsafePathError(f"{lexical} leads to {target}, which is outside the allowed roots (a link out of them)")
    return target


def _is_link(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    if is_junction is not None:
        return bool(is_junction())
    # Path.is_junction is Python 3.12+; on 3.10/3.11 a Windows junction is a reparse point that is not a symlink (Windows CI on 3.10
    # and 3.11 treated the rig's junction as a folder and refused it, 2026-10-13).
    try:
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT


def safe_unlink(path: Path | str, allowed_roots: Iterable[Path | str], missing_ok: bool = True) -> bool:
    """Delete one file (or remove one link). True when something was removed."""
    raw = Path(path)
    if _is_link(raw):
        _lexically_inside(raw, allowed_roots)
        if raw.is_symlink():
            raw.unlink()
        else:
            os.rmdir(raw)  # a junction: removes the link only
        return True
    if not raw.exists():
        if missing_ok:
            return False
        raise FileNotFoundError(str(raw))
    target = check_deletable(raw, allowed_roots)
    if target.is_dir():
        raise UnsafePathError(f"{target} is a folder; use safe_rmtree")
    target.unlink()
    return True


def _lexically_inside(raw: Path, allowed_roots: Iterable[Path | str]) -> None:
    lexical = Path(os.path.abspath(raw))
    roots = [Path(os.path.abspath(Path(r).expanduser())) for r in allowed_roots]
    if not any(_inside(lexical, root) and lexical != root for root in roots):
        raise UnsafePathError(f"{lexical} is outside the allowed roots")


def safe_rmtree(path: Path | str, allowed_roots: Iterable[Path | str], missing_ok: bool = True) -> bool:
    """Delete a folder tree. A link (symlink or junction) is removed as a link and its target is never entered. True when removed."""
    raw = Path(path)
    if _is_link(raw):
        _lexically_inside(raw, allowed_roots)
        if raw.is_symlink():
            raw.unlink()
        else:
            os.rmdir(raw)  # a junction: removes the link only
        return True
    if not raw.exists():
        if missing_ok:
            return False
        raise FileNotFoundError(str(raw))
    target = check_deletable(raw, allowed_roots)
    if not target.is_dir():
        raise UnsafePathError(f"{target} is a file; use safe_unlink")
    # Links inside the tree are removed as links, never followed (shutil.rmtree already does not follow symlinks; junctions are handled here).
    for current, dirs, _files in os.walk(target):
        for name in list(dirs):
            child = Path(current) / name
            if _is_link(child):
                if child.is_symlink():
                    child.unlink()
                else:
                    os.rmdir(child)
                dirs.remove(name)
    shutil.rmtree(target)
    return True
