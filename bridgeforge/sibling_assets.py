"""`bridgeforge sibling-assets WORKSPACE`: fill missing sprites and description rows from sibling mods of the same pack
(ROADMAP item 60c).

`yunrucore` was done by hand: 41 missing ship sprites whose copies sat in different sibling mods (checked byte-identical)
and 18 description rows. Rules, all enforced here:

- A file is copied only when every copy found in the other workspaces' `working/` and `original/` roots is byte-identical.
  Differing copies are refused and reported with each variant's hash; nothing is picked for you.
- A description row is copied only when every sibling row for that id and type holds the same cells, and only into columns
  the mod's own descriptions.csv already has (or vanilla's header when the mod has none).
- It never writes text or colours that no mod holds: what no sibling has stays reported as unresolved.
- Dry run unless `apply`. Each copy is recorded in the workspace's reports/COPIES.json (explain_proofs), so
  `audit-explain --auto` can prove it. Missing references come from the scanner's `asset-reference-missing` and
  `description-missing` findings, so vanilla and declared dependencies already count as holding a file.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

from .explain_proofs import record_copied_rows, record_copies, sha256

SCHEMA_VERSION = 1
COPYABLE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".ogg", ".wav", ".mp3"}
DESCRIPTION_TYPES = {"hull": "SHIP", "weapon": "WEAPON", "ship-system": "SHIP_SYSTEM"}
DESCRIPTIONS_RELATIVE = "data/strings/descriptions.csv"
VANILLA_DESCRIPTIONS_HEADER = "id,type,text1,text2,text3,text4,text5,notes"


class SiblingAssetsError(ValueError):
    pass


def sibling_roots(workspace: Path) -> list[Path]:
    """Mod roots of the other workspaces beside this one: working/, and original/ (unpacked, nested or extracted/)."""
    workspace = Path(workspace).resolve()
    roots: list[Path] = []
    for other in sorted(p for p in workspace.parent.iterdir() if p.is_dir() and not p.name.startswith("_") and p.resolve() != workspace):
        candidates = [other / "working", other / "original"]
        for base in (other / "original", other / "original" / "extracted"):
            if base.is_dir():
                candidates += [p for p in base.iterdir() if p.is_dir()]
        roots += [p for p in candidates if (p / "mod_info.json").is_file()]
    return roots


def _normalize(path: str) -> str | None:
    cleaned = path.strip().replace("\\", "/").lstrip("/")
    return cleaned if cleaned and ".." not in cleaned.split("/") else None


def _find_asset(relative: str, roots: list[Path]) -> dict:
    """{"status": FOUND|CONFLICT|MISSING, "source": first path, "variants": {sha: [paths]}} over every sibling root."""
    variants: dict[str, list[str]] = {}
    for root in roots:
        candidate = root / relative
        if candidate.is_file():
            variants.setdefault(sha256(candidate), []).append(str(candidate))
    if not variants:
        return {"status": "MISSING", "variants": {}}
    status = "FOUND" if len(variants) == 1 else "CONFLICT"
    first = next(iter(variants.values()))[0]
    return {"status": status, "source": first, "variants": variants}


def _read_rows(path: Path) -> list[dict[str, str]]:
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        return [{(k or "").strip(): (v or "").strip() for k, v in row.items()} for row in csv.DictReader(io.StringIO(text))]
    except (OSError, csv.Error):
        return []


def _find_description(cid: str, kind: str, roots: list[Path]) -> dict:
    variants: list[tuple[dict[str, str], str]] = []
    for root in roots:
        for row in _read_rows(root / DESCRIPTIONS_RELATIVE):
            if row.get("id") == cid and row.get("type", "").upper() == kind:
                variants.append((row, str(root / DESCRIPTIONS_RELATIVE)))
    if not variants:
        return {"status": "MISSING"}
    distinct = {tuple(sorted(row.items())) for row, _ in variants}
    return {"status": "FOUND" if len(distinct) == 1 else "CONFLICT", "row": variants[0][0], "source": variants[0][1],
            "variants": len(distinct)}


def _append_rows(target: Path, rows: list[dict[str, str]]) -> list[list[str]]:
    """Append rows to the mod's descriptions.csv under its own header, keeping its line endings; returns each row's cells."""
    existing = target.read_bytes() if target.is_file() else b""
    text = existing.decode("utf-8-sig") if existing else VANILLA_DESCRIPTIONS_HEADER + "\n"
    newline = "\r\n" if "\r\n" in text else "\n"
    header = next(csv.reader(io.StringIO(text)))
    out = io.StringIO()
    writer = csv.writer(out, lineterminator=newline)
    cells = []
    for row in rows:
        line = [row.get(column.strip(), "") for column in header]
        writer.writerow(line)
        cells.append(line)
    joined = text + ("" if text.endswith(("\n", "\r\n")) else newline) + out.getvalue()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((b"\xef\xbb\xbf" if existing.startswith(b"\xef\xbb\xbf") else b"") + joined.encode("utf-8"))
    return cells


def _target_header(target: Path) -> list[str]:
    text = target.read_text(encoding="utf-8-sig", errors="replace") if target.is_file() else VANILLA_DESCRIPTIONS_HEADER
    return [c.strip() for c in next(csv.reader(io.StringIO(text)), [])]


def _plan_findings(working: Path, vanilla_core: Path | None) -> tuple[list[str], list[tuple[str, str]]]:
    from bridgeforge.scan.scanner import scan_mod

    result = scan_mod(working, vanilla_core=vanilla_core)
    assets, descriptions = [], []
    for finding in result.findings:
        if finding.id == "asset-reference-missing":
            assets += [e[len("path:"):] for e in finding.evidence if e.startswith("path:")]
        elif finding.id == "description-missing":
            for item in finding.evidence:
                kind, _, cid = item.partition(":")
                if kind in DESCRIPTION_TYPES and cid:
                    descriptions.append((cid, DESCRIPTION_TYPES[kind]))
    return sorted(set(assets)), sorted(set(descriptions))


def fix_sibling_assets(workspace: Path, vanilla_core: Path | None = None, *, apply: bool = False, roots: list[Path] | None = None,
                       today: str | None = None) -> dict:
    workspace = Path(workspace).expanduser().resolve()
    working = workspace / "working"
    if not (working / "mod_info.json").is_file():
        raise SiblingAssetsError(f"{workspace} has no working/mod_info.json.")
    roots = list(roots) if roots is not None else sibling_roots(workspace)
    assets, descriptions = _plan_findings(working, vanilla_core)
    copies, refused, unresolved = [], [], []
    for reference in assets:
        relative = _normalize(reference)
        if relative is None or Path(relative).suffix.lower() not in COPYABLE_SUFFIXES:
            unresolved.append({"path": reference, "reason": "not a copyable image or sound path"})
            continue
        found = _find_asset(relative, roots)
        if found["status"] == "MISSING":
            unresolved.append({"path": relative, "reason": "no sibling mod holds it"})
        elif found["status"] == "CONFLICT":
            refused.append({"path": relative, "reason": "sibling copies differ; none was chosen", "variants": found["variants"]})
        else:
            copies.append({"path": relative, "source": found["source"], "sha256": next(iter(found["variants"])),
                           "copies_found": len(next(iter(found["variants"].values())))})
    target_csv = working / DESCRIPTIONS_RELATIVE
    header = _target_header(target_csv)
    rows, row_refused, row_unresolved = [], [], []
    for cid, kind in descriptions:
        found = _find_description(cid, kind, roots)
        if found["status"] == "MISSING":
            row_unresolved.append({"id": cid, "type": kind, "reason": "no sibling mod has a row"})
        elif found["status"] == "CONFLICT":
            row_refused.append({"id": cid, "type": kind, "reason": f"{found['variants']} different sibling rows; none was chosen"})
        elif any(value and column not in header for column, value in found["row"].items()):
            row_refused.append({"id": cid, "type": kind, "reason": "the sibling row fills a column this mod's descriptions.csv lacks"})
        else:
            rows.append({"id": cid, "type": kind, "source": found["source"], "row": found["row"]})
    result = {"schema_version": SCHEMA_VERSION, "mode": "SIBLING_ASSETS", "workspace": str(workspace), "apply": apply,
              "siblings_searched": len(roots), "files": copies, "files_refused": refused, "files_unresolved": unresolved,
              "rows": [{k: v for k, v in r.items() if k != "row"} for r in rows], "rows_refused": row_refused,
              "rows_unresolved": row_unresolved}
    if not apply:
        return result
    for entry in copies:
        destination = working / entry["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(Path(entry["source"]).read_bytes())
    if copies:
        record_copies(workspace, {c["path"]: {"source": c["source"], "sha256": c["sha256"]} for c in copies}, "sibling-assets", today)
    if rows:
        cells = _append_rows(target_csv, [r["row"] for r in rows])
        record_copied_rows(workspace, DESCRIPTIONS_RELATIVE,
                           [{"id": r["id"], "type": r["type"], "source": r["source"], "cells": c} for r, c in zip(rows, cells)],
                           "sibling-assets", today)
    return result
