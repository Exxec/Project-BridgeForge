"""Workspace steps the 2026-09-30 session did by hand (ROADMAP P15 item 33).

- `bump_version` (`bridgeforge bump-version`): a shipped mod changed after archiving gets `+bf.N` (owner rule
  2026-09-30), a dated section in its revival report ending READY_FOR_LIVE_TEST (compiled or content changes need a
  new live check), and a MOD_CHANGELOG.md line, in one step.
- `restore_from_done` (`bridgeforge restore-from-done`): rebuild an `In operation/` workspace from a `Done/` archive
  (shipped folder -> working/, original/, reports and baseline back into working/reports), as done for Arkgneisis.
- `review_applied` (`bridgeforge revive-review`): every fix revive applied since a date, as diffs against the first
  backup, with placement checks for the lookup guard (the CRLF bug put 12 guards in comments; 2026-09-30).
"""
from __future__ import annotations

import difflib
import json
import re
import shutil
from datetime import date
from pathlib import Path

from .scanner import _load_lenient_json_file


def next_version(version: str) -> str:
    found = re.search(r"\+bf\.(\d+)$", version)
    return version[: found.start()] + f"+bf.{int(found.group(1)) + 1}" if found else version + "+bf.1"


def bump_version(workspace: Path, note: str, *, day: str | None = None, changelog: Path | None = None) -> dict:
    from .mod_changelog import add_entry

    working = Path(workspace).expanduser().resolve() / "working"
    info_path = working / "mod_info.json"
    info = _load_lenient_json_file(info_path) or {}
    old = info.get("version")
    if not isinstance(old, str) or not old:
        raise ValueError(f"{info_path}: version is not a plain string ({old!r}); set it by hand.")
    new = next_version(old)
    text = info_path.read_text(encoding="utf-8")
    if text.count(json.dumps(old)) != 1:
        raise ValueError(f"{info_path}: the version string appears {text.count(json.dumps(old))} times; set it by hand.")
    info_path.write_text(text.replace(json.dumps(old), json.dumps(new), 1), encoding="utf-8")
    day = day or date.today().isoformat()
    report = working / "reports" / "REVIVAL_REPORT.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    body = report.read_text(encoding="utf-8").rstrip() if report.is_file() else "# Revival report"
    report.write_text(body + f"\n\n## {new} ({day}) (BridgeForge by Exxec)\n\n{note.strip()}\n\nVersion {old} -> {new}.\n\n"
                      "READY_FOR_LIVE_TEST\n", encoding="utf-8")
    name = str(info.get("name") or Path(workspace).name)
    line = add_entry(name, note.strip().split("\n")[0], version=new, day=day, path=changelog)
    return {"workspace": str(workspace), "old": old, "new": new, "report": str(report), "changelog": line}


def restore_from_done(done_mod: Path, queue: Path) -> dict:
    done_mod = Path(done_mod).expanduser().resolve()
    name = done_mod.name
    ws = Path(queue).expanduser().resolve() / name
    if ws.exists():
        raise ValueError(f"{ws} already exists.")
    shipped = done_mod / name
    if not (shipped / "mod_info.json").is_file():
        raise ValueError(f"{shipped} has no mod_info.json (not an archive made by `bridgeforge archive`).")
    shutil.copytree(shipped, ws / "working")
    if (done_mod / "original").is_dir():
        shutil.copytree(done_mod / "original", ws / "original")
    reports = ws / "working" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    kept = sorted((done_mod / "workspace").glob("*")) if (done_mod / "workspace").is_dir() else []
    for item in kept:
        if item.is_file():
            shutil.copy2(item, reports / item.name)
    baseline = any(i.name.startswith("baseline") for i in kept)
    return {"workspace": str(ws), "restored_reports": [i.name for i in kept if i.is_file()], "baseline": baseline,
            "note": None if baseline else "the archive kept no baseline: findings accepted before archiving will reappear; "
                                          "accept them again only if the content is unchanged from the archived copy"}


def _guard_misplaced(lines: list[str]) -> list[int]:
    bad = []
    for i, line in enumerate(lines):
        found = re.search(r"if \((\w+) == null\) \{ // BridgeForge: guard a missing", line)
        if found and not (i and re.search(rf"\b{found.group(1)}\s*=\s*[^;]*\.(getStarSystem|getEntityById)\(", lines[i - 1])):
            bad.append(i + 1)
    return bad


def review_applied(queue: Path, since: str) -> dict:
    """Applied fixes from each REVIVE.json, diffed against the earliest backup written on or after `since`."""
    rows = []
    for record in sorted(Path(queue).glob("*/reports/revive/REVIVE.json")):
        ws = record.parents[2]
        data = json.loads(record.read_text(encoding="utf-8"))
        for applied in data.get("applied") or []:
            for name in applied.get("files") or []:
                current = ws / "working" / name.replace(" (removed)", "")
                backups = sorted(current.parent.glob(current.name + f".pre-bf-fix-{applied['finding']}*"), key=lambda p: p.stat().st_mtime)
                backups = [b for b in backups if date.fromtimestamp(b.stat().st_mtime).isoformat() >= since]
                row = {"workspace": ws.name, "finding": applied["finding"], "file": name, "flags": []}
                if name.endswith(" (removed)") or name.startswith("../"):
                    row["kind"] = "moved"  # shippable-work-file moves a file to scratch; nothing to diff
                    rows.append(row)
                    continue
                if not current.is_file():
                    row["flags"].append("file-gone")
                    rows.append(row)
                    continue
                if not backups:
                    row["kind"] = "created"  # a fixer wrote a new file (e.g. planet_gen_data.csv): diff against nothing
                before = backups[0].read_text(encoding="utf-8", errors="replace").splitlines() if backups else []
                after = current.read_text(encoding="utf-8", errors="replace").splitlines()
                row["diff"] = [line for line in difflib.unified_diff(before, after, lineterm="", n=1) if not line.startswith(("+++", "---"))][:60]
                if applied["finding"].startswith("hard-coded-campaign-"):
                    if _guard_misplaced(after):
                        row["flags"].append("guard-misplaced")
                    if name.replace("\\", "/").startswith(("src/", "jars/src/", "jar/src/")):
                        row["flags"].append("jar-source-edit (no effect until the jar is patched: patch-jar-sources)")
                rows.append(row)
    return {"since": since, "applied": len(rows), "flagged": [r for r in rows if r["flags"]], "rows": rows}


def close_workspace(workspace: Path, status: str, reason: str, *, day: str | None = None) -> str:
    """End revival work on a mod: a dated revival-report section ending in SUPERSEDED or NOT_REVIVABLE, which every
    queue command then skips (report_status.CLOSED_STATUSES). Nothing is moved or deleted."""
    from .report_status import CLOSED_STATUSES

    if status not in CLOSED_STATUSES:
        raise ValueError(f"status must be one of {', '.join(CLOSED_STATUSES)}")
    report = Path(workspace).expanduser().resolve() / "working" / "reports" / "REVIVAL_REPORT.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    body = report.read_text(encoding="utf-8").rstrip() if report.is_file() else "# Revival report"
    title = "Superseded" if status == "SUPERSEDED" else "Not revivable for RC8"
    report.write_text(body + f"\n\n## {title} ({day or date.today().isoformat()})\n\n{reason.strip()}\n\n{status}\n", encoding="utf-8")
    return str(report)
