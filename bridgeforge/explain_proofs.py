"""Proofs `audit-explain --auto` uses beyond the file contents themselves (ROADMAP item 60b), and the copy ledger (60c).

Each proof reads a record BridgeForge already leaves on disk and checks it against the files; none of them trusts the record
alone, and nothing here edits a mod:

- `descriptions_applied`: a descriptions.csv written by `descriptions apply` (the author's file kept once in
  scratch/descriptions.csv.pre-bf-crafted, the credits file beside it, the rows only added).
- `kept_elsewhere`: a file the original shipped is gone from working/ and a byte-identical copy sits under one of the
  scratch folders the fixers move files to (`work-files`, `translator-workspace`, `removed-src`).
- the copy ledger (`reports/COPIES.json`): files copied into working/ from another mod (`vendor-copy`, the sibling-pack fixer).
  A shipped file is proven when it is absent from the original, its SHA-256 is the recorded one, and the recorded source still
  holds the same bytes (or is gone, which the explanation then says).
- `prepare_for_audit`: the two archive steps that only copy: extract a zip original into scratch/original-extracted/ and copy
  scratch/translation/*.json to reports/translation/. Neither overwrites anything.
"""
from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import date
from pathlib import Path

CREDITS_FILE = "BRIDGEFORGE_CREDITS.txt"
DESCRIPTIONS_RELATIVE = "data/strings/descriptions.csv"
DESCRIPTIONS_BACKUP = "descriptions.csv.pre-bf-crafted"
MOVED_FOLDERS = ("work-files", "translator-workspace", "removed-src", "removed-shadow")
COPIES_FILE = "COPIES.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---- descriptions apply -----------------------------------------------------------------------------------------

def descriptions_applied(workspace: Path, relative: str, before: Path, after: Path) -> bool:
    """True when `after` is the descriptions.csv `descriptions apply` wrote: the saved author file is what the original
    holds (or the original has none and the saved file is header-only), credits exist, and `after` only gained rows."""
    from .live_trust import _only_rows_added, _text

    if relative != DESCRIPTIONS_RELATIVE or not after.is_file():
        return False
    workspace = Path(workspace)
    backup = workspace / "scratch" / DESCRIPTIONS_BACKUP
    if not backup.is_file() or not (workspace / "working" / CREDITS_FILE).is_file():
        return False
    if before.is_file():
        if sha256(before) != sha256(backup):
            return False
    elif len([line for line in _text(backup).splitlines() if line.strip()]) > 1:
        return False  # the original had no file but the saved one holds rows: not the header-only start apply writes
    return _only_rows_added(backup, after)


# ---- files moved out of the shipped copy ------------------------------------------------------------------------

def kept_elsewhere(workspace: Path, relative: str, original: Path) -> str | None:
    """The scratch folder that holds a byte-identical copy of an original file now missing from working/, else None."""
    scratch = Path(workspace) / "scratch"
    try:
        wanted = sha256(original)
    except OSError:
        return None
    for folder in MOVED_FOLDERS:
        base = scratch / folder
        if not base.is_dir():
            continue
        direct = base / relative
        candidates = [direct] if direct.is_file() else [p for p in base.rglob(Path(relative).name) if p.is_file()]
        for candidate in candidates:
            try:
                if sha256(candidate) == wanted:
                    return folder
            except OSError:
                continue
    return None


# ---- the copy ledger --------------------------------------------------------------------------------------------

def _ledger_path(workspace: Path) -> Path:
    return Path(workspace) / "reports" / COPIES_FILE


def _read_ledger(workspace: Path) -> dict:
    try:
        data = json.loads(_ledger_path(workspace).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = None
    data = data if isinstance(data, dict) else {}
    files, rows = data.get("files"), data.get("rows")
    return {"schema_version": 1, "files": files if isinstance(files, dict) else {}, "rows": rows if isinstance(rows, list) else []}


def _write_ledger(workspace: Path, ledger: dict) -> Path:
    path = _ledger_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def read_copies(workspace: Path) -> dict[str, dict]:
    return _read_ledger(workspace)["files"]


def record_copies(workspace: Path, entries: dict[str, dict], by: str, today: str | None = None) -> Path:
    """Add {relative path: {"source": path, "sha256": digest}} to reports/COPIES.json; `by` names the tool."""
    ledger = _read_ledger(workspace)
    for relative, entry in entries.items():
        ledger["files"][relative.replace("\\", "/")] = {"source": str(entry["source"]), "sha256": entry["sha256"], "by": by,
                                                       "date": today or date.today().isoformat()}
    return _write_ledger(workspace, ledger)


def record_copied_rows(workspace: Path, file: str, rows: list[dict], by: str, today: str | None = None) -> Path:
    """Add copied CSV rows, each {"id", "type", "source", "cells": [...]}, to reports/COPIES.json."""
    ledger = _read_ledger(workspace)
    for row in rows:
        ledger["rows"].append({"file": file, "id": row["id"], "type": row.get("type", ""), "source": str(row["source"]),
                               "cells": list(row["cells"]), "by": by, "date": today or date.today().isoformat()})
    return _write_ledger(workspace, ledger)


def _row_cells(row: list[str]) -> list[str]:
    trimmed = [cell.strip() for cell in row]
    while trimmed and not trimmed[-1]:
        trimmed.pop()
    return trimmed


def copied_rows_proof(workspace: Path, relative: str, before: Path, after: Path) -> str | None:
    """The reason a CSV is the original plus recorded copied rows, else None: same header, every original row kept, and
    every new row is one the ledger recorded with exactly those cells."""
    from .live_trust import _text

    recorded = [_row_cells(r["cells"]) for r in _read_ledger(workspace)["rows"] if r.get("file") == relative]
    if not recorded or not after.is_file():
        return None
    import csv
    import io

    try:
        old = list(csv.reader(io.StringIO(_text(before)))) if before.is_file() else []
        new = list(csv.reader(io.StringIO(_text(after))))
    except csv.Error:
        return None
    if not new or (old and _row_cells(old[0]) != _row_cells(new[0])):
        return None
    remaining = [_row_cells(r) for r in new[1:] if any(c.strip() for c in r)]
    for row in old[1:]:
        if any(c.strip() for c in row):
            if _row_cells(row) not in remaining:
                return None
            remaining.remove(_row_cells(row))
    if not remaining or any(row not in recorded for row in remaining):
        return None
    return f"{len(remaining)} CSV row(s) copied from sibling mods of the same pack; each is recorded in reports/{COPIES_FILE}"


def workspace_of_working(target: Path) -> Path | None:
    """The workspace when `target` is a workspace's working/ folder (or the workspace itself), else None."""
    target = Path(target).resolve()
    if target.name == "working" and (target.parent / "reports").exists() | (target.parent / "original").exists():
        return target.parent
    if (target / "working" / "mod_info.json").is_file():
        return target
    return None


def copy_proof(workspace: Path, relative: str, after: Path) -> str | None:
    """The reason a shipped file is a recorded copy, else None. The file must be what was copied and the source (when still
    there) must still hold the same bytes."""
    entry = read_copies(workspace).get(relative)
    if not entry or not after.is_file() or sha256(after) != entry.get("sha256"):
        return None
    source = Path(str(entry.get("source", "")))
    if source.is_file() and sha256(source) != entry["sha256"]:
        return None
    where = f"still byte-identical at {source}" if source.is_file() else f"the source {source} is no longer on disk"
    return f"copied byte for byte from another mod by {entry.get('by')} on {entry.get('date')} ({where}); recorded in reports/{COPIES_FILE}"


# ---- jar patch records ------------------------------------------------------------------------------------------

def patched_jar_names(workspace: Path) -> dict[str, str]:
    """{jar file name: record folder} from scratch/jar-patch-*/ and scratch/*anchor-fix*/ JSON records that name a jar."""
    found: dict[str, str] = {}
    scratch = Path(workspace) / "scratch"
    if not scratch.is_dir():
        return found
    records = list(scratch.glob("jar-patch-*/*.json")) + list(scratch.glob("*anchor-fix*/*.json"))
    for record in records:
        try:
            data = json.loads(record.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        jar = data.get("jar") if isinstance(data, dict) else None
        if isinstance(jar, str) and jar.lower().endswith(".jar") and (data.get("installed") or "anchor" in record.parent.name):
            found.setdefault(Path(jar.replace("\\", "/")).name, record.parent.name)
    return found


# ---- archive preparation ----------------------------------------------------------------------------------------

def _safe_extract(archive: zipfile.ZipFile, destination: Path) -> int:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    count = 0
    for info in archive.infolist():
        target = (destination / info.filename).resolve()
        if root != target and root not in target.parents:
            continue  # zip-slip: never write outside the destination
        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(archive.read(info))
        count += 1
    return count


def prepare_for_audit(workspace: Path) -> list[str]:
    """Do the copy-only archive steps once and say what was done. original/ is never touched."""
    workspace = Path(workspace)
    done: list[str] = []
    original = workspace / "original"
    extracted = workspace / "scratch" / "original-extracted"
    if original.is_dir() and not extracted.exists() and not any(original.rglob("mod_info.json")):
        zips = sorted(p for p in original.rglob("*.zip") if p.is_file())
        for archive_path in zips:
            try:
                with zipfile.ZipFile(archive_path) as archive:
                    if not any(Path(n).name == "mod_info.json" for n in archive.namelist()):
                        continue
                    count = _safe_extract(archive, extracted / archive_path.stem)
                done.append(f"extracted {archive_path.name} ({count} files) into scratch/original-extracted/{archive_path.stem}/")
            except (OSError, zipfile.BadZipFile):
                continue
    source = workspace / "scratch" / "translation"
    target = workspace / "reports" / "translation"
    if source.is_dir():
        for item in sorted(source.glob("*.json")):
            destination = target / item.name
            if not destination.exists():
                target.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(item.read_bytes())
                done.append(f"copied scratch/translation/{item.name} to reports/translation/")
    return done
