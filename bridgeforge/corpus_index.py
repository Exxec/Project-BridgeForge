"""`bridgeforge corpus-index`: a one-time searchable index of a large mod archive (ROADMAP P14 item 18).

A `timeout 60 grep -rl "shieldbypass" Downloads` returned nothing because the timeout expired before
grep reached `Ship and Weapon Pack/data/hullmods/hull_mods.csv` (2026-09-20): a false "absent" that
looked like evidence. This walks a folder once, including inside `.zip` archives, and stores every
text-like file in an SQLite FTS5 table with the trigram tokenizer, so any substring of three or
more characters can be searched in milliseconds, case-insensitively, like grep.

Absence is only evidence when the index covered everything, so the index also records what it could
not read (other archive formats, zips inside zips, oversized or undecodable files) and every
search reports that alongside its hits. Re-running `build` re-reads only files whose size or
modification time changed, and forgets files that are gone.

Read-only on the archive; writes only the index database.
"""
from __future__ import annotations

import io
import sqlite3
import zipfile
from pathlib import Path

SCHEMA_VERSION = 1
DEFAULT_MAX_BYTES = 4 * 1024 * 1024
TEXT_SUFFIXES = frozenset({
    ".csv", ".json", ".ship", ".wpn", ".variant", ".skin", ".faction", ".system", ".proj", ".java",
    ".txt", ".md", ".ini", ".xml", ".log", ".properties", ".kt", ".groovy", ".cfg", ".data", ".shader", ".frag", ".vert",
})
UNINDEXED_ARCHIVES = frozenset({".7z", ".rar", ".tar", ".gz", ".bz2", ".xz"})
ZIP_SUFFIXES = frozenset({".zip", ".jar"})


class CorpusIndexError(ValueError):
    """Raised for a missing root/database, an unsupported SQLite build, or a too-short query."""


def _connect(db: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(str(db))
    try:
        connection.execute("CREATE VIRTUAL TABLE IF NOT EXISTS content USING fts5(location UNINDEXED, text, tokenize='trigram')")
    except sqlite3.OperationalError as exc:
        connection.close()
        raise CorpusIndexError(f"this Python's SQLite ({sqlite3.sqlite_version}) lacks FTS5 with the trigram tokenizer (needs 3.34+): {exc}") from None
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS sources (path TEXT PRIMARY KEY, size INTEGER, mtime_ns INTEGER);
        CREATE TABLE IF NOT EXISTS files (location TEXT PRIMARY KEY, source TEXT, size INTEGER);
        CREATE TABLE IF NOT EXISTS skipped (location TEXT PRIMARY KEY, source TEXT, reason TEXT);
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
    """)
    return connection


def _decode(data: bytes) -> str | None:
    if b"\x00" in data[:8192]:
        return None
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")  # vanilla's own CSVs carry CP-1252 bytes


def _forget(connection: sqlite3.Connection, source: str) -> None:
    connection.execute("DELETE FROM content WHERE location IN (SELECT location FROM files WHERE source = ?)", (source,))
    connection.execute("DELETE FROM files WHERE source = ?", (source,))
    connection.execute("DELETE FROM skipped WHERE source = ?", (source,))
    connection.execute("DELETE FROM sources WHERE path = ?", (source,))


def _add_text(connection, source: str, location: str, data: bytes, max_bytes: int) -> None:
    if len(data) > max_bytes:
        connection.execute("INSERT OR REPLACE INTO skipped VALUES (?, ?, ?)", (location, source, f"larger than {max_bytes} bytes"))
        return
    text = _decode(data)
    if text is None:
        connection.execute("INSERT OR REPLACE INTO skipped VALUES (?, ?, ?)", (location, source, "binary content"))
        return
    connection.execute("INSERT INTO content VALUES (?, ?)", (location, text))
    connection.execute("INSERT OR REPLACE INTO files VALUES (?, ?, ?)", (location, source, len(data)))


def _index_zip(connection, source: str, data: bytes, max_bytes: int) -> None:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            member = info.filename.replace("\\", "/")
            location = f"{source}!{member}"
            suffix = Path(member).suffix.lower()
            if suffix in ZIP_SUFFIXES or suffix in UNINDEXED_ARCHIVES:
                connection.execute("INSERT OR REPLACE INTO skipped VALUES (?, ?, ?)", (location, source, "archive inside an archive"))
            elif suffix in TEXT_SUFFIXES:
                if info.file_size > max_bytes:
                    connection.execute("INSERT OR REPLACE INTO skipped VALUES (?, ?, ?)", (location, source, f"larger than {max_bytes} bytes"))
                else:
                    _add_text(connection, source, location, archive.read(info), max_bytes)
            else:
                connection.execute("INSERT OR REPLACE INTO files VALUES (?, ?, ?)", (location, source, info.file_size))


def build_index(root: Path, db: Path, max_bytes: int = DEFAULT_MAX_BYTES) -> dict:
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise CorpusIndexError(f"{root} is not a folder.")
    db = Path(db).expanduser().resolve()
    if db == root or root in db.parents:
        raise CorpusIndexError(f"the index {db} must live outside the archive being indexed ({root}).")
    db.parent.mkdir(parents=True, exist_ok=True)
    connection = _connect(db)
    stats = {"reindexed": 0, "unchanged": 0, "forgotten": 0}
    try:
        with connection:
            previous_root = connection.execute("SELECT value FROM meta WHERE key = 'root'").fetchone()
            if previous_root and previous_root[0] != str(root):
                raise CorpusIndexError(f"{db} indexes {previous_root[0]}, not {root}; use another --db.")
            connection.execute("INSERT OR REPLACE INTO meta VALUES ('root', ?)", (str(root),))
            connection.execute("INSERT OR REPLACE INTO meta VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
            known = {row[0]: (row[1], row[2]) for row in connection.execute("SELECT path, size, mtime_ns FROM sources")}
            seen: set[str] = set()
            for path in sorted(root.rglob("*")):
                if not path.is_file() or path.is_symlink():
                    continue
                source = path.relative_to(root).as_posix()
                seen.add(source)
                stat = path.stat()
                if known.get(source) == (stat.st_size, stat.st_mtime_ns):
                    stats["unchanged"] += 1
                    continue
                _forget(connection, source)
                suffix = path.suffix.lower()
                try:
                    if suffix in ZIP_SUFFIXES:
                        _index_zip(connection, source, path.read_bytes(), max_bytes)
                    elif suffix in UNINDEXED_ARCHIVES:
                        connection.execute("INSERT OR REPLACE INTO skipped VALUES (?, ?, ?)", (source, source, f"{suffix} archives are not read"))
                    elif suffix in TEXT_SUFFIXES:
                        _add_text(connection, source, source, path.read_bytes(), max_bytes)
                    else:
                        connection.execute("INSERT OR REPLACE INTO files VALUES (?, ?, ?)", (source, source, stat.st_size))
                except (OSError, zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
                    connection.execute("INSERT OR REPLACE INTO skipped VALUES (?, ?, ?)", (source, source, f"unreadable: {exc}"))
                connection.execute("INSERT INTO sources VALUES (?, ?, ?)", (source, stat.st_size, stat.st_mtime_ns))
                stats["reindexed"] += 1
            for source in set(known) - seen:
                _forget(connection, source)
                stats["forgotten"] += 1
        return {**_coverage(connection), **stats, "db": str(db), "root": str(root)}
    finally:
        connection.close()


def _coverage(connection: sqlite3.Connection) -> dict:
    searched = connection.execute("SELECT COUNT(*) FROM content").fetchone()[0]
    listed = connection.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    reasons = dict(connection.execute("SELECT reason, COUNT(*) FROM skipped GROUP BY reason ORDER BY reason").fetchall())
    return {"text_files_searched": searched, "files_listed": listed, "not_searched": reasons}


def search_index(db: Path, text: str, limit: int = 50, names_only: bool = False) -> dict:
    db = Path(db).expanduser().resolve()
    if not db.is_file():
        raise CorpusIndexError(f"{db} does not exist; run `corpus-index build` first.")
    if len(text) < 3 and not names_only:
        raise CorpusIndexError("content search needs at least 3 characters (trigram index); use --names for shorter names.")
    connection = _connect(db)
    try:
        like = "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        name_hits = [row[0] for row in connection.execute(
            "SELECT location FROM files WHERE location LIKE ? ESCAPE '\\' UNION SELECT location FROM skipped WHERE location LIKE ? ESCAPE '\\' ORDER BY 1 LIMIT ?",
            (like, like, limit))]
        hits = []
        if not names_only:
            phrase = '"' + text.replace('"', '""') + '"'
            needle = text.lower()
            for location, body in connection.execute("SELECT location, text FROM content WHERE content MATCH ? ORDER BY location LIMIT ?", (phrase, limit)):
                lines = [f"{number}: {line.strip()[:200]}" for number, line in enumerate(body.splitlines(), 1) if needle in line.lower()]
                hits.append({"location": location, "lines": lines[:5], "line_count": len(lines)})
        root = connection.execute("SELECT value FROM meta WHERE key = 'root'").fetchone()
        return {"schema_version": SCHEMA_VERSION, "mode": "CORPUS_SEARCH", "query": text, "root": root[0] if root else None,
                "content_hits": hits, "name_hits": name_hits, "limit": limit, **_coverage(connection)}
    finally:
        connection.close()
