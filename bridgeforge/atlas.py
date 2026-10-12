"""Mod Atlas storage and build (ROADMAP item 67, phases 1-3): one SQLite index of what every mod defines, reads,
mutates and hooks, so mods can be judged against each other (`atlas_rules`, `atlas_report`). Plan: docs/MOD_ATLAS_PLAN.md.

Tables: mods(id, version, name, path, hash, folder), facts(mod, version, kind, id, action, file, line, evidence,
confidence) and literals (string literals in code that may name an id, resolved after every mod is read).
A mod is re-read only when its hash (relative path, size and mtime of its data, scripts and jars) changes.
"""
from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import time
from pathlib import Path

from . import progress
from .atlas_code import CALLS, extract_code
from .atlas_data import DATA_KINDS, Fact, extract_data_facts
from .scanner import _load_lenient_json_file

VANILLA_ID = "vanilla"
SCHEMA_VERSION = 1
DEFAULT_DB = Path("reports") / "atlas.sqlite"
HASHED_SUFFIXES = {".csv", ".json", ".java", ".faction", ".jar", ".variant", ".skin", ".ship", ".wpn", ".kt"}
SKIPPED_DIRS = {"graphics", "sounds", ".git", "__pycache__", "native"}
REFERENCE_KINDS = ("hull", "weapon", "wing", "hullmod", "system", "commodity", "industry", "condition",
                   "special_item", "submarket", "ability", "skill", "faction")
SCHEMA = """
CREATE TABLE IF NOT EXISTS mods (id TEXT, version TEXT, name TEXT, path TEXT, hash TEXT, folder TEXT, PRIMARY KEY (id, version));
CREATE TABLE IF NOT EXISTS facts (mod TEXT, version TEXT, kind TEXT, id TEXT, action TEXT, file TEXT, line INTEGER, evidence TEXT, confidence TEXT);
CREATE TABLE IF NOT EXISTS literals (mod TEXT, version TEXT, file TEXT, line INTEGER, value TEXT, ctx TEXT);
CREATE INDEX IF NOT EXISTS facts_by_id ON facts (kind, id);
CREATE INDEX IF NOT EXISTS facts_by_mod ON facts (mod, version);
CREATE INDEX IF NOT EXISTS literals_by_value ON literals (value);
CREATE INDEX IF NOT EXISTS literals_by_mod ON literals (mod, version);
"""


class AtlasError(Exception):
    pass


def connect(db: Path, create: bool = False) -> sqlite3.Connection:
    if not create and not db.is_file():
        raise AtlasError(f"no atlas at {db}; run `bridgeforge atlas build` first")
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


# ---------------------------------------------------------------- discovery

def default_roots(base: Path) -> list[Path]:
    roots = [base / "Done"]
    roots += sorted(base.glob("In operation/*/working"))
    roots += [base / "In operation" / "_rig" / "mods", base / "In operation" / "_rig" / "starsector-core"]
    return [root for root in roots if root.is_dir()]


def _is_vanilla(path: Path) -> bool:
    return path.name.lower() == "starsector-core" and (path / "data").is_dir() and not (path / "mod_info.json").is_file()


def discover_mods(root: Path, depth: int = 2) -> list[Path]:
    """The mod folders at or under `root` (a folder holding mod_info.json), looking at most `depth` levels down."""
    if _is_vanilla(root) or (root / "mod_info.json").is_file():
        return [root]
    if depth <= 0 or not root.is_dir():
        return []
    found: list[Path] = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and not child.name.startswith("."):
            found.extend(discover_mods(child, depth - 1))
    return found


def _version_text(value: object) -> str:
    if isinstance(value, dict):
        return ".".join(str(value.get(key, "")) for key in ("major", "minor", "patch") if value.get(key, "") != "")
    return str(value) if value not in (None, "") else "0"


def mod_identity(path: Path) -> tuple[str, str, str] | None:
    if _is_vanilla(path):
        return VANILLA_ID, "RC8", "Starsector (vanilla)"
    info = _load_lenient_json_file(path / "mod_info.json")
    if not isinstance(info, dict) or not isinstance(info.get("id"), str) or not info["id"]:
        return None
    return info["id"], _version_text(info.get("version")), str(info.get("name") or info["id"])


def mod_hash(path: Path) -> str:
    digest = hashlib.sha1()
    for current, dirs, files in os.walk(path):
        dirs[:] = sorted(d for d in dirs if d.lower() not in SKIPPED_DIRS)
        for name in sorted(files):
            if Path(name).suffix.lower() in HASHED_SUFFIXES:
                full = Path(current) / name
                try:
                    stat = full.stat()
                except OSError:
                    continue
                digest.update(f"{full.relative_to(path).as_posix()}|{stat.st_size}|{stat.st_mtime_ns}\n".encode("utf-8", "replace"))
    return digest.hexdigest()


def version_key(version: str) -> tuple:
    return tuple(int(part) for part in re.findall(r"\d+", version)), version


# ---------------------------------------------------------------- build

def _store(conn: sqlite3.Connection, ident: tuple[str, str, str], path: Path, digest: str, facts: list[Fact],
           literals: list[tuple[str, int, str, str]]) -> None:
    mod_id, version, name = ident
    with conn:
        for table in ("facts", "literals"):
            conn.execute(f"DELETE FROM {table} WHERE mod = ? AND version = ?", (mod_id, version))
        conn.execute("DELETE FROM mods WHERE id = ? AND version = ?", (mod_id, version))
        conn.execute("INSERT INTO mods VALUES (?, ?, ?, ?, ?, ?)", (mod_id, version, name, str(path), digest, path.name))
        conn.executemany("INSERT INTO facts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", [(mod_id, version, *fact) for fact in facts])
        conn.executemany("INSERT INTO literals VALUES (?, ?, ?, ?, ?, ?)", [(mod_id, version, *item) for item in literals])


def index_mod(path: Path) -> tuple[list[Fact], list[tuple[str, int, str, str]]]:
    facts = extract_data_facts(path)
    if _is_vanilla(path):
        return facts, []
    code = extract_code(path)
    return facts + code.facts, code.literals


def _method_kinds() -> dict[str, dict[str, set[str]]]:
    table: dict[str, dict[str, set[str]]] = {}
    for method, (kind, action) in CALLS.items():
        table.setdefault(kind, {}).setdefault(action, set()).add(method)
    return table


def resolve_references(conn: sqlite3.Connection) -> int:
    """Recompute the facts that depend on other mods: `overrides` (same id as vanilla) and literal-based
    `references`/`reads`/`mutates` (a string constant in code equal to a known id). Returns the literal facts written."""
    kinds = ",".join(f"'{kind}'" for kind in sorted(DATA_KINDS))
    with conn:
        conn.execute("DELETE FROM facts WHERE evidence LIKE 'literal:%'")
        conn.execute("UPDATE facts SET action = 'defines' WHERE action = 'overrides'")
        conn.execute(
            f"UPDATE facts SET action = 'overrides' WHERE action = 'defines' AND mod != ? AND kind IN ({kinds}) AND EXISTS ("
            "SELECT 1 FROM facts v WHERE v.mod = ? AND v.action = 'defines' AND v.kind = facts.kind AND v.id = facts.id)",
            (VANILLA_ID, VANILLA_ID))
    known: dict[str, set[str]] = {}
    for row in conn.execute("SELECT DISTINCT kind, id FROM facts WHERE action IN ('defines', 'overrides', 'patches') "
                            f"AND kind IN ({','.join(repr(k) for k in REFERENCE_KINDS)})"):
        known.setdefault(row["id"], set()).add(row["kind"])
    own = {(r["mod"], r["version"], r["kind"], r["id"]) for r in conn.execute(
        "SELECT mod, version, kind, id FROM facts WHERE action IN ('defines', 'overrides', 'patches')")}
    direct = {(r["mod"], r["version"], r["file"], r["kind"], r["id"]) for r in conn.execute(
        "SELECT mod, version, file, kind, id FROM facts WHERE action IN ('reads', 'mutates') AND evidence LIKE 'method=%'")}
    methods = _method_kinds()
    out = []
    for row in conn.execute("SELECT mod, version, file, line, value, ctx FROM literals"):
        for kind in known.get(row["value"], ()):
            if (row["mod"], row["version"], kind, row["value"]) in own or (row["mod"], row["version"], row["file"], kind, row["value"]) in direct:
                continue
            out += _literal_facts(row, kind, methods.get(kind, {}), set(filter(None, row["ctx"].split(","))))
    with conn:
        conn.executemany("INSERT INTO facts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", out)
    return len(out)


def _literal_facts(row: sqlite3.Row, kind: str, by_action: dict[str, set[str]], ctx: set[str]) -> list[tuple]:
    base = (row["mod"], row["version"], kind, row["value"])
    mutating, reading = sorted(ctx & by_action.get("mutates", set())), sorted(ctx & by_action.get("reads", set()))
    if mutating:
        return [(*base, "mutates", row["file"], row["line"], f"literal: class-level co-occurrence with {m}", "REVIEW") for m in mutating]
    if reading:
        return [(*base, "reads", row["file"], row["line"], f"literal: class-level co-occurrence with {reading[0]}", "REVIEW")]
    return [(*base, "references", row["file"], row["line"], "literal: string constant equal to a known id", "REVIEW")]


def build_atlas(roots: list[Path], db: Path, quiet: bool = False) -> dict:
    started = time.monotonic()
    folders = [folder for root in roots for folder in discover_mods(root)]
    conn = connect(db, create=True)
    header = {"atlas": SCHEMA_VERSION, "roots": [str(root) for root in roots], "mods": [str(f) for f in folders]}
    stats = {"mods": 0, "indexed": 0, "unchanged": 0, "duplicates": 0, "skipped": 0, "facts": 0}
    seen: set[tuple[str, str]] = set()
    with progress.Checkpoint(db.with_suffix(".partial.jsonl"), header) as checkpoint:
        for number, folder in enumerate(folders, 1):
            _build_one(conn, checkpoint, folder, number, len(folders), seen, stats, quiet)
        literal_facts = resolve_references(conn)
        stats["facts"] = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
        stats["literal_facts"] = literal_facts
    checkpoint.finish()
    conn.close()
    stats.update(seconds=round(time.monotonic() - started, 1), db=str(db))
    return stats


def _build_one(conn, checkpoint, folder: Path, number: int, total: int, seen: set, stats: dict, quiet: bool) -> None:
    def say(name: str, detail: str, seconds: float | None) -> None:
        if not quiet:
            progress.report(number, total, name, detail, seconds)

    ident = mod_identity(folder)
    if ident is None:
        stats["skipped"] += 1
        say(folder.name, "skipped: mod_info.json has no id", 0.0)
        return
    if ident[:2] in seen:
        stats["duplicates"] += 1
        say(f"{ident[0]} {ident[1]}", f"duplicate copy at {folder} ignored", 0.0)
        return
    seen.add(ident[:2])
    stats["mods"] += 1
    began, digest = time.monotonic(), mod_hash(folder)
    row = conn.execute("SELECT hash FROM mods WHERE id = ? AND version = ?", (ident[0], ident[1])).fetchone()
    label = f"{ident[2]} {ident[1]}"
    if row and row["hash"] == digest:
        stats["unchanged"] += 1
        previous = checkpoint.get(f"{ident[0]}@{ident[1]}")
        say(label, "unchanged", None if previous and previous.get("hash") == digest else time.monotonic() - began)
        return
    facts, literals = index_mod(folder)
    _store(conn, ident, folder, digest, facts, literals)
    checkpoint.add(f"{ident[0]}@{ident[1]}", {"hash": digest, "facts": len(facts)})
    stats["indexed"] += 1
    say(label, f"{len(facts)} fact(s), {len(literals)} literal(s)", time.monotonic() - began)


# ---------------------------------------------------------------- lookup

def latest_mods(conn: sqlite3.Connection) -> list[dict]:
    """One row per mod id: the highest indexed version."""
    best: dict[str, dict] = {}
    for row in conn.execute("SELECT id, version, name, path, folder FROM mods"):
        mod = dict(row)
        if mod["id"] not in best or version_key(mod["version"]) > version_key(best[mod["id"]]["version"]):
            best[mod["id"]] = mod
    return sorted(best.values(), key=lambda m: m["id"])


def _acronym(text: str) -> str:
    return "".join(word[0] for word in re.findall(r"[A-Za-z0-9]+", text.replace("'", ""))).lower()


def match_mods(mods: list[dict], query: str) -> list[dict]:
    """Mods named by `query`: exact id, then exact name or folder, then acronym of the name (DNEEP), then substring."""
    needle = query.strip().lower()
    tiers = (
        lambda m: m["id"].lower() == needle,
        lambda m: needle in (m["name"].lower(), m["folder"].lower()),
        lambda m: needle == _acronym(m["name"]) or needle == _acronym(m["folder"]),
        lambda m: needle in m["id"].lower() or needle in m["name"].lower() or needle in m["folder"].lower(),
    )
    for tier in tiers:
        hits = [m for m in mods if tier(m)]
        if hits:
            return hits
    return []


def resolve_mods(conn: sqlite3.Connection, queries: list[str]) -> list[dict]:
    mods, chosen = latest_mods(conn), []
    for query in queries:
        hits = match_mods(mods, query)
        if not hits:
            raise AtlasError(f"no indexed mod matches {query!r}")
        for hit in hits:
            if hit not in chosen:
                chosen.append(hit)
    return chosen


GROUPS = {"aotd": ("aotd", ("ashes of the domain", "aotd"))}


def group_mods(conn: sqlite3.Connection, group: str) -> list[dict]:
    """Every indexed mod of a family treated as one set (`aotd`: id starts with aotd, or name says Ashes of the Domain)."""
    prefix, names = GROUPS.get(group.lower(), (group.lower(), (group.lower(),)))
    return [m for m in latest_mods(conn)
            if m["id"].lower().startswith(prefix) or any(n in m["name"].lower() for n in names)]


