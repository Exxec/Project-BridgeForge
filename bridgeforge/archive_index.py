"""A one-time, incrementally-updatable content index of a mod-archive folder (ROADMAP P14 item 18).

Found 2026-09-20 investigating O2.2: `timeout 60 grep -rl "shieldbypass" "Downloads"` returned zero
matches - a false negative caused purely by the timeout, not by the string's absence (the file was
there, found immediately once searched directly). The Ironclads archive (item 8's ~264-mod intake
queue) is large enough that an unindexed live grep across the whole folder is not reliable evidence
of absence.

This builds a small sqlite3 database (stdlib only - no runtime dependency, and this Python build's
sqlite3 ships FTS5) indexing, per ZIP archive found under a root directory:
- every member's path and size (a fast, always-available filename index), and
- the text content of small, source/data-shaped members only (a `content_fts` FTS5 table) - binary
  assets (images, sounds, compiled classes) are skipped outright; they have no research value here
  and would bloat the index for nothing.

Re-running `build_index` on the same output only re-reads an archive whose size or mtime changed
since the last run, so this stays cheap to keep current as the archive folder grows.
"""

from __future__ import annotations

import sqlite3
import zipfile
from pathlib import Path

SCHEMA_VERSION = 1

# Starsector's own text/data file shapes, plus common project-source/docs extensions. Binary
# assets (.png, .jpg, .ogg, .wav, .class, .jar, .ttf...) are deliberately not read as content -
# only their filename is indexed.
TEXT_EXTENSIONS = frozenset({
    ".java", ".json", ".csv", ".xml", ".txt", ".md", ".ini", ".info", ".version", ".cfg",
    ".wpn", ".ship", ".variant", ".skin", ".system", ".hull", ".faction", ".properties", ".yml", ".yaml",
})
DEFAULT_MAX_CONTENT_BYTES = 5_000_000

_SCHEMA = """
CREATE TABLE IF NOT EXISTS archives (
    id INTEGER PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,
    size_bytes INTEGER NOT NULL,
    mtime REAL NOT NULL,
    entry_count INTEGER NOT NULL,
    content_indexed_count INTEGER NOT NULL,
    error TEXT
);
CREATE TABLE IF NOT EXISTS files (
    archive_id INTEGER NOT NULL REFERENCES archives(id) ON DELETE CASCADE,
    member_path TEXT NOT NULL,
    size_bytes INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS files_archive_id ON files(archive_id);
CREATE INDEX IF NOT EXISTS files_member_path ON files(member_path);
CREATE VIRTUAL TABLE IF NOT EXISTS content_fts USING fts5(archive_path, member_path, content);
"""


def _open_index(index_path: Path) -> sqlite3.Connection:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(index_path)
    connection.executescript(_SCHEMA)
    return connection


def _index_one_archive(connection: sqlite3.Connection, archive: Path, root: Path, max_content_bytes: int, extensions: frozenset[str]) -> dict:
    relative = str(archive.relative_to(root)).replace("\\", "/")
    stat = archive.stat()
    existing = connection.execute("SELECT id, size_bytes, mtime FROM archives WHERE path = ?", (relative,)).fetchone()
    if existing is not None and existing[1] == stat.st_size and existing[2] == stat.st_mtime:
        return {"archive": relative, "status": "UNCHANGED"}
    if existing is not None:
        connection.execute("DELETE FROM archives WHERE id = ?", (existing[0],))
        connection.execute("DELETE FROM files WHERE archive_id = ?", (existing[0],))
        connection.execute("DELETE FROM content_fts WHERE archive_path = ?", (relative,))
    try:
        with zipfile.ZipFile(archive) as bundle:
            entries = [item for item in bundle.infolist() if not item.is_dir()]
            content_indexed = 0
            file_rows = [(item.filename.replace("\\", "/"), item.file_size) for item in entries]
            cursor = connection.execute(
                "INSERT INTO archives (path, size_bytes, mtime, entry_count, content_indexed_count, error) VALUES (?, ?, ?, ?, 0, NULL)",
                (relative, stat.st_size, stat.st_mtime, len(entries)),
            )
            archive_id = cursor.lastrowid
            connection.executemany(
                "INSERT INTO files (archive_id, member_path, size_bytes) VALUES (?, ?, ?)",
                [(archive_id, name, size) for name, size in file_rows],
            )
            for item in entries:
                suffix = "." + item.filename.rsplit(".", 1)[-1].lower() if "." in item.filename.rsplit("/", 1)[-1] else ""
                if suffix not in extensions or item.file_size > max_content_bytes:
                    continue
                try:
                    with bundle.open(item) as handle:
                        data = handle.read()
                except (OSError, zipfile.BadZipFile, KeyError, NotImplementedError, RuntimeError):
                    # RuntimeError: zipfile's own exception for a password-protected member (real
                    # case, 2026-09-21: a password-protected entry in the actual Downloads
                    # archive) - stdlib zipfile does not give this its own exception type.
                    continue
                text = data.decode("utf-8", errors="replace")
                connection.execute(
                    "INSERT INTO content_fts (archive_path, member_path, content) VALUES (?, ?, ?)",
                    (relative, item.filename.replace("\\", "/"), text),
                )
                content_indexed += 1
            connection.execute("UPDATE archives SET content_indexed_count = ? WHERE id = ?", (content_indexed, archive_id))
        return {"archive": relative, "status": "INDEXED", "entry_count": len(entries), "content_indexed_count": content_indexed}
    except (zipfile.BadZipFile, OSError) as exc:
        connection.execute(
            "INSERT INTO archives (path, size_bytes, mtime, entry_count, content_indexed_count, error) VALUES (?, ?, ?, 0, 0, ?)",
            (relative, stat.st_size, stat.st_mtime, str(exc)),
        )
        return {"archive": relative, "status": "ERROR", "error": str(exc)}


def build_index(root: Path, index_path: Path, extensions: frozenset[str] = TEXT_EXTENSIONS, max_content_bytes: int = DEFAULT_MAX_CONTENT_BYTES) -> dict:
    """Index every `*.zip` under `root` into the sqlite3 database at `index_path`.

    Incremental: an archive whose size and mtime haven't changed since the last run is skipped.
    """
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"{root} is not an existing directory.")
    index_path = index_path.expanduser().resolve()
    connection = _open_index(index_path)
    try:
        results = [_index_one_archive(connection, archive, root, max_content_bytes, extensions) for archive in sorted(root.rglob("*.zip"))]
        connection.commit()
    finally:
        connection.close()
    counts = {status: sum(1 for r in results if r["status"] == status) for status in ("INDEXED", "UNCHANGED", "ERROR")}
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "archive-index",
        "status": "OK",
        "root": str(root),
        "index_path": str(index_path),
        "archive_count": len(results),
        "counts": counts,
        "errors": [r for r in results if r["status"] == "ERROR"],
    }


def search_index(index_path: Path, query: str, mode: str = "content", limit: int = 50) -> dict:
    """Search a previously built index. `mode`: "content" (FTS5 MATCH) or "filename" (substring)."""
    index_path = index_path.expanduser().resolve()
    if not index_path.is_file():
        raise ValueError(f"{index_path} is not an existing index; run archive-index first.")
    connection = sqlite3.connect(index_path)
    try:
        if mode == "filename":
            rows = connection.execute(
                "SELECT a.path, f.member_path, f.size_bytes FROM files f JOIN archives a ON a.id = f.archive_id "
                "WHERE f.member_path LIKE ? ORDER BY a.path, f.member_path LIMIT ?",
                (f"%{query}%", limit),
            ).fetchall()
            matches = [{"archive": path, "member": member, "size_bytes": size} for path, member, size in rows]
        elif mode == "content":
            rows = connection.execute(
                "SELECT archive_path, member_path, snippet(content_fts, 2, '[', ']', '...', 12) "
                "FROM content_fts WHERE content_fts MATCH ? LIMIT ?",
                (query, limit),
            ).fetchall()
            matches = [{"archive": archive, "member": member, "snippet": snippet} for archive, member, snippet in rows]
        else:
            raise ValueError(f"Unknown search mode: {mode!r} (expected 'content' or 'filename')")
    finally:
        connection.close()
    return {"schema_version": SCHEMA_VERSION, "mode": "archive-search", "status": "OK", "query": query, "search_mode": mode, "match_count": len(matches), "matches": matches}
