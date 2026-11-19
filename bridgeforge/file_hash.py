"""File and tree hashes, once for every module (ROADMAP-3 96.5 A10).

Before, 27 modules each wrote their own SHA-256 of a file or of every file in a tree: some streamed it in 1 MiB blocks, some
read it whole, some returned None for a missing file. All give the same digest, so they are these three now:

- `sha256_file(path)`: the hex digest, read in 1 MiB blocks (a jar or a save can be large).
- `sha256_file_or_none(path)`: the same, or None when `path` is not a file.
- `file_hashes(root)`: {posix path relative to root: digest} for every file under root, in sorted order.

Hashes with another shape stay where they are: provenance and scan_registry fold a tree into one digest that is stored
on disk; revival_audit hashes an open stream in upper case; content_diff, runtime and working_tree build other digests;
escalation's `_tree` skips `.pre-bf-` files; kit_resources/verify_kit ships in the kit and must not import bridgeforge. ROADMAP-3 93.27's per-rig cache of
(path, size, mtime, hash) is meant to sit behind `file_hashes`.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

CHUNK = 1024 * 1024


def sha256_file(path: Path | str) -> str:
    """The SHA-256 hex digest of the file at `path`; raises OSError as `open` does."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_file_or_none(path: Path | str) -> str | None:
    """`sha256_file`, or None when `path` is not a file."""
    return sha256_file(path) if Path(path).is_file() else None


def file_hashes(root: Path) -> dict[str, str]:
    """{posix path relative to `root`: SHA-256} for every file under `root`, sorted by path."""
    return {path.relative_to(root).as_posix(): sha256_file(path) for path in sorted(root.rglob("*")) if path.is_file()}
