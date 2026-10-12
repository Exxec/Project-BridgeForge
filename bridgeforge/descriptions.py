"""`bridgeforge descriptions sheet|apply` (ROADMAP P15 item 31.5).

The owner writes (or reviews drafted) codex descriptions for entries a mod never had. 2026-09-28 did it with
scratchpad scripts; this is that workflow:

- `sheet QUEUE` writes DESCRIPTIONS_NEEDED.csv: every hull, weapon and ship system still missing a description,
  checked live against the current files, with the name, role/size and tech/manufacturer from the mod's own data.
- `apply WORKSPACE DRAFT.md` adds the rows of a reviewed draft table (`| \\`id\\` | TYPE | text |`) to
  working/data/strings/descriptions.csv, keeping its line endings. Owner request 2026-09-28: crafted text is never
  passed off as the author's, so it also writes working/BRIDGEFORGE_CREDITS.txt (original author first, every crafted
  id listed) and alt-original-descriptions/<Mod>/, the mod with only the author's descriptions (the author's
  descriptions.csv is kept once in scratch/descriptions.csv.pre-bf-crafted).
"""
from __future__ import annotations

import csv
import io
import re
import shutil
from pathlib import Path

from .copy_drift import _collect
from .scanner import _load_lenient_json_file

SHEET_FILE = "DESCRIPTIONS_NEEDED.csv"
CREDITS_FILE = "BRIDGEFORGE_CREDITS.txt"
ORIGINAL_BACKUP = "descriptions.csv.pre-bf-crafted"
# RC8 starsector-core/data/strings/descriptions.csv header (read 2026-09-29).
VANILLA_DESCRIPTIONS_HEADER = "id,type,text1,text2,text3,text4,text5,notes"
_ROW = re.compile(r"\|\s*`([^`]+)`\s*\|\s*([A-Z_]+)\s*\|\s*(.+?)\s*\|\s*$")


class DescriptionsError(ValueError):
    pass


def rebuild_original_descriptions_copy(workspace: Path) -> Path | None:
    """alt-original-descriptions/<Mod>/: the current working copy with the author's own descriptions.csv (from
    scratch/descriptions.csv.pre-bf-crafted) and no credits file. Rebuilt from working/ every time, so a later fix
    reaches it: Broken Star r2's jar fix (2026-09-29) was missing from the author-only zip because the copy had
    been taken once, when the descriptions were applied. None when no crafted descriptions were ever applied."""
    workspace = Path(workspace)
    working = workspace / "working"
    backup = workspace / "scratch" / ORIGINAL_BACKUP
    if not backup.is_file() or not working.is_dir():
        return None
    alt = workspace / "alt-original-descriptions" / workspace.name
    if alt.exists():
        shutil.rmtree(alt)
    for relative, source in _collect(working).items():
        if relative == CREDITS_FILE:
            continue
        (alt / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, alt / relative)
    (alt / "data" / "strings").mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup, alt / "data" / "strings" / "descriptions.csv")
    return alt


def _index(path: Path) -> dict[str, dict]:
    try:
        return {r.get("id", ""): r for r in csv.DictReader(open(path, encoding="utf-8", errors="replace"))}
    except OSError:
        return {}


def build_sheet(queue: Path, vanilla_core: Path | None) -> dict:
    from .models import ScanResult, TargetProfile
    from .report_status import report_status
    from .scanner import _scan_description_missing

    queue = Path(queue).expanduser().resolve()
    rows = []
    for workspace in sorted(p for p in queue.iterdir() if p.is_dir() and not p.name.startswith("_") and (p / "working" / "mod_info.json").is_file()):
        working = workspace / "working"
        if report_status(working / "reports" / "REVIVAL_REPORT.md") == "SUPERSEDED":
            continue
        result = ScanResult(input_path=working, target=TargetProfile())
        _scan_description_missing(working, result, vanilla_core)
        sources = {**_index(working / "data" / "shipsystems" / "ship_systems.csv"), **_index(working / "data" / "weapons" / "weapon_data.csv"),
                   **_index(working / "data" / "hulls" / "ship_data.csv")}
        for finding in result.findings:
            if finding.id != "description-missing":
                continue
            for item in finding.evidence:
                if ":" not in item:
                    continue
                kind, cid = item.split(":", 1)
                source = sources.get(cid) or {}
                rows.append({"mod": workspace.name, "kind": kind, "id": cid, "name": source.get("name", ""),
                             "role/size": source.get("designation") or source.get("size") or "",
                             "tech/manufacturer": source.get("tech/manufacturer", ""), "description": ""})
    out = queue / SHEET_FILE
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["mod", "kind", "id", "name", "role/size", "tech/manufacturer", "description"])
        writer.writeheader()
        writer.writerows(rows)
    return {"entries": len(rows), "mods": len({r["mod"] for r in rows}), "path": str(out)}


def parse_draft(path: Path) -> list[tuple[str, str, str]]:
    return [(m.group(1), m.group(2), m.group(3)) for line in Path(path).read_text(encoding="utf-8").splitlines() if (m := _ROW.match(line))]


def _credits(working: Path, crafted: list[tuple[str, str]]) -> None:
    info = _load_lenient_json_file(working / "mod_info.json") or {}
    lines = [f"{info.get('name', working.parent.name)}: BridgeForge revival credits", "",
             f"Original mod: {info.get('author') or 'see the mod itself'}. All original art, code and text belong to the original author(s).",
             "Revival for Starsector 0.98a-RC8: BridgeForge by Exxec.", "",
             "Crafted descriptions (not original)", "-----------------------------------",
             "The codex descriptions for the entries below were missing from the original mod. They were written for",
             "this revival from the mod's own lore, names and roles, and are not the author's text.",
             "A copy of the mod with only the author's original descriptions is kept beside this revival",
             "(alt-original-descriptions/).", ""]
    lines += [f"- {kind:12} {cid}" for cid, kind in crafted] + [""]
    (working / CREDITS_FILE).write_text("\r\n".join(lines), encoding="utf-8")


def _crafted_from_credits(working: Path) -> list[tuple[str, str]]:
    path = working / CREDITS_FILE
    if not path.is_file():
        return []
    return [(m.group(2), m.group(1)) for line in path.read_text(encoding="utf-8").splitlines() if (m := re.match(r"- (\S+)\s+(\S+)$", line))]


def apply_draft(workspace: Path, draft: Path) -> dict:
    workspace = Path(workspace).expanduser().resolve()
    working = workspace / "working"
    target = working / "data" / "strings" / "descriptions.csv"
    rows = parse_draft(draft)
    if not rows:
        raise DescriptionsError(f"{draft} has no `| \\`id\\` | TYPE | text |` rows.")
    if not target.is_file():
        # A mod with no descriptions.csv (8 of 62 on 2026-09-29, e.g. OMEGAslaught): RC8 merges mods'
        # descriptions.csv by id, so start one with vanilla's own header. The author's version is then that
        # header-only file, exactly what the author shipped: no descriptions.
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(VANILLA_DESCRIPTIONS_HEADER + "\n", encoding="utf-8")
    backup = workspace / "scratch" / ORIGINAL_BACKUP
    if not backup.exists():
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, backup)
    raw = target.read_bytes()
    text = raw.decode("utf-8-sig")
    newline = "\r\n" if "\r\n" in text else "\n"
    header = next(csv.reader(io.StringIO(text)))
    # Keyed by id AND type: Junk Pirates' drone ids are both a hull (SHIP row) and a ship system (2026-09-29).
    type_col = header.index("type") if "type" in header else 1
    existing = {(r[0], r[type_col].strip().upper() if len(r) > type_col else "") for r in csv.reader(io.StringIO(text)) if r}
    out = io.StringIO()
    writer = csv.writer(out, lineterminator=newline)
    added = []
    for cid, kind, body in rows:
        if (cid, kind) in existing:
            continue
        row = [""] * len(header)
        row[header.index("id")], row[header.index("type")], row[header.index("text1")] = cid, kind, body
        writer.writerow(row)
        added.append((cid, kind))
    joined = text + ("" if text.endswith(("\n", "\r\n")) else newline) + out.getvalue()
    target.write_bytes((b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b"") + joined.encode("utf-8"))
    crafted = _crafted_from_credits(working)
    crafted += [item for item in added if item not in crafted]
    _credits(working, crafted)
    alt = rebuild_original_descriptions_copy(workspace)
    return {"added": [cid for cid, _ in added], "skipped_existing": [cid for cid, kind, _ in rows if (cid, kind) in existing],
            "credits": str(working / CREDITS_FILE), "alternative": str(alt)}
