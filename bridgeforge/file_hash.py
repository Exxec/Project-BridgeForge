"""File and tree hashes, once for every module (ROADMAP-3 96.5 A10).

Before, 27 modules each wrote their own SHA-256 of a file or of every file in a tree: some streamed it in 1 MiB blocks, some
read it whole, some returned None for a missing file. All give the same digest, so they are these three now:

- `sha256_file(path)`: the hex digest, read in 1 MiB blocks (a jar or a save can be large).
- `sha256_file_or_none(path)`: the same, or None when `path` is not a file.
- `file_hashes(root)`: {posix path relative to root: digest} for every file under root, in sorted order.

Hashes with another shape stay where they are: provenance and scan_registry fold a tree into one digest that is stored
on disk; revival_audit hashes an open stream in upper case; content_diff, runtime and working_tree build other digests;
escalation's `_tree` skips `.pre-bf-` files; kit_resources/verify_kit ships in the kit and must not import bridgeforge.

ROADMAP-3 95.5 / 93.27: a live run hashed every enabled mod's shipped files before launch and again at evaluation (about
5 minutes on Test1 with GraphicsLib and Scrapyard). Inside `cached_hashes(cache_file)`, `sha256_cached` and
`sha256_many` reuse a digest while the file's size and modification time are unchanged, hash the rest in parallel, and
save the cache when the scope ends. Outside a scope they are `sha256_file`.
"""
from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Iterator

CHUNK = 1024 * 1024
HASH_WORKERS = 8  # threads: hashlib releases the GIL while it hashes, and disks overlap reads
CACHE_SCHEMA = 1


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


class HashCache:
    """Digests of files keyed by resolved path, valid while the file's size and modification time are unchanged."""

    def __init__(self, cache_file: Path) -> None:
        self.cache_file = Path(cache_file)
        self.entries: dict[str, list] = {}
        self.hits = self.misses = 0
        self._dirty = False
        try:
            data = json.loads(self.cache_file.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("schema") == CACHE_SCHEMA and isinstance(data.get("files"), dict):
                self.entries = {k: v for k, v in data["files"].items() if isinstance(v, list) and len(v) == 3}
        except (OSError, ValueError):
            pass  # no cache, or an unreadable one: start empty

    @staticmethod
    def _stamp(path: Path) -> tuple[str, int, int]:
        stat = path.stat()
        return str(path.resolve()), stat.st_size, stat.st_mtime_ns

    def lookup(self, path: Path) -> tuple[str | None, tuple[str, int, int]]:
        key, size, mtime = self._stamp(path)
        entry = self.entries.get(key)
        return (entry[2] if entry and entry[0] == size and entry[1] == mtime else None), (key, size, mtime)

    def store(self, stamp: tuple[str, int, int], digest: str) -> None:
        key, size, mtime = stamp
        self.entries[key] = [size, mtime, digest]
        self._dirty = True

    def save(self) -> None:
        if not self._dirty:
            return
        from .safeio import atomic_write_json

        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.cache_file, {"schema": CACHE_SCHEMA, "files": dict(sorted(self.entries.items()))})
        self._dirty = False


_active: ContextVar[HashCache | None] = ContextVar("hash_cache", default=None)


@contextmanager
def cached_hashes(cache_file: Path) -> Iterator[HashCache]:
    """Reuse digests from `cache_file` inside the block and save it afterwards; an enclosing scope is kept."""
    enclosing = _active.get()
    if enclosing is not None:
        yield enclosing
        return
    cache = HashCache(cache_file)
    token = _active.set(cache)
    try:
        yield cache
    finally:
        _active.reset(token)
        cache.save()


def sha256_many(paths: list[Path]) -> dict[Path, str]:
    """{path: SHA-256} for every path: unchanged files from the active cache, the rest hashed in parallel."""
    cache = _active.get()
    result: dict[Path, str] = {}
    todo: list[tuple[Path, tuple | None]] = []
    for path in paths:
        if cache is None:
            todo.append((path, None))
            continue
        digest, stamp = cache.lookup(path)
        if digest is None:
            todo.append((path, stamp))
            cache.misses += 1
        else:
            result[path] = digest
            cache.hits += 1
    if todo:
        with ThreadPoolExecutor(max_workers=min(HASH_WORKERS, len(todo))) as pool:
            digests = list(pool.map(lambda item: sha256_file(item[0]), todo))
        for (path, stamp), digest in zip(todo, digests):
            result[path] = digest
            if cache is not None and stamp is not None:
                cache.store(stamp, digest)
    return result


def sha256_cached(path: Path) -> str:
    """`sha256_file`, through the active cache when there is one."""
    return sha256_many([Path(path)])[Path(path)]
