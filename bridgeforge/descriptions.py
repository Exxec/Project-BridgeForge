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
_ROW = re.compile(r"\|\s*`([^`]+)`\s*\|\s*([A-Z_]+)\s*\|\s*(.+?)\s*\|\s*$")


class DescriptionsError(ValueError):
    pass


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
    if not target.is_file():
        raise DescriptionsError(f"{target} does not exist.")
    rows = parse_draft(draft)
    if not rows:
        raise DescriptionsError(f"{draft} has no `| \\`id\\` | TYPE | text |` rows.")
    backup = workspace / "scratch" / ORIGINAL_BACKUP
    if not backup.exists():
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, backup)
    raw = target.read_bytes()
    text = raw.decode("utf-8-sig")
    newline = "\r\n" if "\r\n" in text else "\n"
    header = next(csv.reader(io.StringIO(text)))
    existing = {r[0] for r in csv.reader(io.StringIO(text)) if r}
    out = io.StringIO()
    writer = csv.writer(out, lineterminator=newline)
    added = []
    for cid, kind, body in rows:
        if cid in existing:
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
    alt = workspace / "alt-original-descriptions" / workspace.name
    if alt.exists():
        shutil.rmtree(alt)
    for relative, source in _collect(working).items():
        if relative == CREDITS_FILE:
            continue
        (alt / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, alt / relative)
    shutil.copy2(backup, alt / "data" / "strings" / "descriptions.csv")
    return {"added": [cid for cid, _ in added], "skipped_existing": [cid for cid, _, _ in rows if cid in existing],
            "credits": str(working / CREDITS_FILE), "alternative": str(alt)}
