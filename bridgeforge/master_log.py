"""`Done/MASTER_LOG.md` and `.csv`, regenerated after `record --archive` / `archive` (ROADMAP item 65).

This is `Done/make_master_log.py` (a gitignored local script, 2026-10-11) as a package function. Read-only on every archive.
Sources, per archived mod folder: ARCHIVE_NOTE.md (author, status, archived date, live-validated date and test id,
changed-file counts), the mod folder's own mod_info.json (name and release version), the release zips beside it, and
workspace/REVIVAL_REPORT.md (the version headlines). The dated timeline is the repo's MOD_CHANGELOG.md, and the sets-aside
(`Done/_*` folders, including `_replaced-<date>`). Nothing is guessed: a field the archive does not record is a dash.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from bridgeforge.scan.scan_json import _load_lenient_json_file

DASH = "-"
FIELDS = ["mod", "release_version", "archived", "live_validated", "status", "author", "policy", "files_vs_original",
          "what_was_done", "release_zips", "folder"]
GENERIC = re.compile(r"revived for RC8 and archived", re.I)
_STATUS = re.compile(r"Revival report status: \*\*([A-Z_]+)\*\* \(archived (\d{4}-\d\d-\d\d)\)")
_LIVE = re.compile(r"(?i)live-validated (\d{4}-\d\d-\d\d)(?: \(test ([\w.-]+)\))?")


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""


def _version_shown(version) -> str:
    """A mod_info `version`: a string as written, or the {major, minor, patch} object joined with dots."""
    if isinstance(version, str):
        return version
    if isinstance(version, dict):
        parts = {key: str(value).strip("\"' ") for key, value in version.items() if key in ("major", "minor", "patch")}
        return ".".join(parts[key] for key in ("major", "minor", "patch") if key in parts) or DASH
    return DASH


def _mod_info(folder: Path) -> tuple[str, str]:
    """(name, version) from the first mod_info.json one or two levels down."""
    found = sorted(folder.glob("*/mod_info.json")) or sorted(folder.glob("*/*/mod_info.json"))
    for path in found:
        if "original" in path.parts or "workspace" in path.parts:
            continue
        # The file's own top-level fields: a regex over the text took the first "name" and "version" anywhere, which in a mod_info that lists
        # its dependencies first is LazyLib's (17 archives were shown as "LazyLib" with LazyLib's version, found 2026-10-12).
        info = _load_lenient_json_file(path)
        if not isinstance(info, dict):
            continue
        name = info.get("name") if isinstance(info.get("name"), str) else None
        shown = _version_shown(info.get("version"))
        return (name.strip() if name else DASH), shown
    return DASH, DASH


def _headlines(folder: Path) -> list[str]:
    text = _read(folder / "workspace" / "REVIVAL_REPORT.md")
    out = []
    for match in re.finditer(r"^## ([^\n]+?) \((\d{4}-\d\d-\d\d)\)[^\n]*\n+(.+?)(?:\n\n|\Z)", text, re.M | re.S):
        body = " ".join(match.group(3).split())
        if body and not body.startswith(("Version ", "READY_FOR", "LIVE_")):
            out.append(f"{match.group(1)} ({match.group(2)}): {body}")
    return out


def _live_record(operation: Path, folder_name: str) -> tuple[str, str]:
    """(date, test id) of the last PASS in In operation/<folder>/reports/live_runs.jsonl, or ('', '')."""
    last = ("", "")
    for line in _read(operation / folder_name / "reports" / "live_runs.jsonl").splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("verdict") == "PASS":
            last = (str(entry.get("date", "")), str(entry.get("test_id", "")))
    return last


def _norm(text: str) -> str:
    text = re.sub(r"\[BF[^\]]*\]|\(.*?\)", " ", text)
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _changelog_notes(mod: str, folder: str, version: str, events: list[tuple[str, str]]) -> list[str]:
    keys = {_norm(mod), _norm(folder)} - {""}
    notes = []
    for day, text in events:
        match = re.match(r"\*\*(.+?)\*\*\s+(\S+?):\s*(.*)$", text)
        if match and not GENERIC.search(match.group(3)) and _norm(match.group(1)) in keys and match.group(2) == version:
            notes.append(f"{day}: {match.group(3)}")
    return notes


def _files_vs_original(note: str) -> str:
    counts = re.search(r"(\d+) shipped file\(s\) changed and (\d+) added", note)
    removed = len(re.findall(r"^- removed: ", note, re.M))
    if counts:
        return f"{counts.group(1)} changed, {counts.group(2)} added" + (f", {removed} removed" if removed else "")
    return "none (author's files byte for byte)" if "byte-identical" in note or "byte for byte" in note else DASH


def _live_text(note: str, status: re.Match | None, recorded: tuple[str, str]) -> str:
    if recorded[0]:
        return f"{recorded[0]} ({recorded[1]})"
    live = _LIVE.search(note)
    if live:
        return f"{live.group(1)} ({live.group(2)})" if live.group(2) else f"{live.group(1)} (archive note)"
    if status and status.group(1) == "LIVE_VALIDATED":
        return "yes (date not recorded)"
    return "not recorded" if status else DASH


def archive_row(folder: Path, events: list[tuple[str, str]], operation: Path) -> dict | None:
    note = _read(folder / "ARCHIVE_NOTE.md")
    if not note:
        return None
    heading = note.splitlines()[0].lstrip("# ").strip()
    title = re.sub(r":\s*archive (note|snapshot).*$", "", heading)
    name, version = _mod_info(folder)
    author = re.search(r"\*\*Original author: (.+?)\.\*\*", note)
    status = _STATUS.search(note)
    policy = re.search(r"`release_policy\.json` as `([A-Z_]+)`", note)
    snapshot = re.search(r"archive snapshot \((\d{4}-\d\d-\d\d)\)", heading)
    mod_name = name if name != DASH else title
    done = _changelog_notes(mod_name, folder.name, version, events) or _headlines(folder)
    return {
        "folder": folder.name, "mod": mod_name, "release_version": version,
        "release_zips": "; ".join(sorted(p.name for p in folder.glob("*.zip") if "-with-readme" not in p.name)) or DASH,
        "archived": status.group(2) if status else (snapshot.group(1) if snapshot else DASH),
        "live_validated": _live_text(note, status, _live_record(operation, folder.name)),
        "status": status.group(1) if status else DASH, "author": author.group(1) if author else DASH,
        "policy": policy.group(1) if policy else DASH, "files_vs_original": _files_vs_original(note),
        "what_was_done": " | ".join(done) if done else "Revived for RC8 (see workspace/REVIVAL_REPORT.md)",
    }


def _set_aside(done: Path) -> list[dict]:
    rows = []
    for parent in sorted(p for p in done.glob("_*") if p.is_dir()):
        for item in sorted(parent.iterdir()):
            note = _read(item / "ARCHIVE_NOTE.md") if item.is_dir() else ""
            title = re.sub(r":\s*archive (note|snapshot).*$", "", note.splitlines()[0].lstrip("# ").strip()) if note else DASH
            status = _STATUS.search(note)
            rows.append({"where": f"{parent.name}/{item.name}", "archive_note_title": title,
                         "archived": status.group(2) if status else DASH, "status": status.group(1) if status else DASH})
    return rows


def _timeline(changelog: Path) -> list[tuple[str, str]]:
    day, out = "", []
    for line in _read(changelog).splitlines():
        if line.startswith("## "):
            day = line[3:].strip()
        elif line.startswith("- ") and day:
            out.append((day, line[2:].strip()))
    return out


def _render(rows: list[dict], events: list[tuple[str, str]], old: list[dict]) -> str:
    live = sum(1 for r in rows if r["status"] == "LIVE_VALIDATED")
    lines = ["# Done/ master log", "",
             "Every mod archived here: its release version, when it was archived and live-validated, what was done to it, and how far its",
             "files differ from the author's. Regenerated by `bridgeforge` after `record --archive` and `archive` (`master_log.py`), from",
             "each archive's own `ARCHIVE_NOTE.md`, mod folder and revival report; a dash means the archive does not record it.", "",
             f"**{len(rows)} archived mods**, {live} live-validated, {len(rows) - live} archived before a live run (status shows which).",
             "A sortable copy with every column is in `MASTER_LOG.csv`.", "", "## 1. Archived mods (A to Z)", "",
             "| Mod | Release version | Archived | Live-validated (last PASS) | Status at archiving | Files vs original | What was done |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        done = r["what_was_done"].replace("|", "/")
        lines.append(f"| {r['mod']} | {r['release_version']} | {r['archived']} | {r['live_validated']} | {r['status']} | "
                     f"{r['files_vs_original']} | {done[:600]} |")
    lines += ["", "## 2. Timeline of bigger updates (from MOD_CHANGELOG.md, newest first)", ""]
    current = ""
    for day, text in events:
        if day != current:
            lines += ["", f"### {day}", ""]
            current = day
        lines.append(f"- {text}")
    lines += ["", "## 3. Earlier archives set aside (kept, not deleted)", "",
              "| Where | What it was | Archived | Status |", "| --- | --- | --- | --- |"]
    lines += [f"| `{r['where']}` | {r['archive_note_title']} | {r['archived']} | {r['status']} |" for r in old]
    lines.append("")
    return "\n".join(lines)


def write_master_log(done: Path, changelog: Path | None = None, operation: Path | None = None) -> dict:
    """Rewrite MASTER_LOG.md and MASTER_LOG.csv in `done`. `changelog` defaults to MOD_CHANGELOG.md beside Done/, `operation`
    to In operation/ beside it. Returns the counts."""
    done = Path(done)
    changelog = Path(changelog) if changelog else done.parent / "MOD_CHANGELOG.md"
    operation = Path(operation) if operation else done.parent / "In operation"
    events = _timeline(changelog)
    rows = [r for r in (archive_row(p, events, operation) for p in sorted(done.iterdir()) if p.is_dir() and not p.name.startswith("_")) if r]
    rows.sort(key=lambda r: (r["mod"].lower(), r["archived"]))
    old = _set_aside(done)
    with (done / "MASTER_LOG.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    (done / "MASTER_LOG.md").write_text(_render(rows, events, old), encoding="utf-8")
    return {"mods": len(rows), "live_validated": sum(1 for r in rows if r["status"] == "LIVE_VALIDATED"),
            "timeline": len(events), "set_aside": len(old)}
