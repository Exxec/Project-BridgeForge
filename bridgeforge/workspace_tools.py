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

from bridgeforge.scan.scanner import _load_lenient_json_file


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


ARCHIVE_OWN_FOLDERS = ("original", "workspace")  # what `archive` writes beside the shipped mod folder
PREVIOUS_BUILD_REPORTS = ("REVIVAL_REPORT.md", "REVIVAL_PLAN.md")


def _shipped_folder(done_mod: Path) -> Path:
    """The archive's shipped mod folder: `Done/<X>/<X>`, or else its one other folder holding a mod_info.json. Station Augments
    ships "Station Augments" in `Done/Station.Augments-2.4.3+bf.1` (ROADMAP-3 96.10)."""
    named = done_mod / done_mod.name
    if (named / "mod_info.json").is_file():
        return named
    found = [d for d in sorted(done_mod.iterdir()) if d.is_dir() and not d.is_symlink() and d.name not in ARCHIVE_OWN_FOLDERS
             and (d / "mod_info.json").is_file()]
    if len(found) == 1:
        return found[0]
    detail = f"{len(found)} folders with a mod_info.json ({', '.join(d.name for d in found)})" if found else "no mod folder"
    raise ValueError(f"{done_mod}: {detail}; not an archive made by `bridgeforge archive`.")


def _move_aside(ws: Path, day: str) -> Path:
    """Move an existing workspace to `<queue>/_stale-<day>/<name>` (a free name), never deleting it (DOC-001)."""
    holder = ws.parent / f"_stale-{day}"
    target = holder / ws.name
    n = 2
    while target.exists():
        target, n = holder / f"{ws.name}-{n}", n + 1
    holder.mkdir(parents=True, exist_ok=True)
    shutil.move(str(ws), str(target))
    return target


def restore_from_done(done_mod: Path, queue: Path, *, for_retarget: bool = False, day: str | None = None) -> dict:
    """Rebuild `<queue>/<archive name>` from a Done/ archive. With `for_retarget` (ROADMAP-3 96.10), a workspace of that name is
    moved to `<queue>/_stale-<day>/` first, and the archived report and plan are kept as `*.previous-build.md`: they describe
    the build the archive was validated on, and revive drafts the new build's."""
    done_mod = Path(done_mod).expanduser().resolve()
    name = done_mod.name
    ws = Path(queue).expanduser().resolve() / name
    shipped = _shipped_folder(done_mod)
    moved = None
    if ws.exists():
        if not for_retarget:
            raise ValueError(f"{ws} already exists (with --for-retarget it is moved to _stale-<date>/ first).")
        moved = _move_aside(ws, day or date.today().isoformat())
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
    kept_as_previous = []
    if for_retarget:
        for report in PREVIOUS_BUILD_REPORTS:
            if (reports / report).is_file():
                previous = reports / report.replace(".md", ".previous-build.md")
                (reports / report).replace(previous)
                kept_as_previous.append(previous.name)
    return {"workspace": str(ws), "restored_reports": [i.name for i in kept if i.is_file()], "baseline": baseline,
            "shipped_folder": shipped.name, "moved_aside": str(moved) if moved else None, "previous_build_reports": kept_as_previous,
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
    return {"since": since, "applied": len(rows), "flagged": [r for r in rows if r["flags"]], "rows": rows,
            "auto_accepted": _auto_accepted_since(queue, since)}


def _auto_accepted_since(queue: Path, since: str) -> list[dict]:
    """Escalation attempts applied without a person (`escalation run --auto-accept`, ROADMAP 73 E2), from each ledger."""
    found = []
    for ledger in sorted(Path(queue).glob("*/reports/escalations/ledger.jsonl")):
        for line in ledger.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if entry.get("auto_accepted") and str(entry.get("at", ""))[:10] >= since:
                found.append({"workspace": ledger.parents[2].name, "packet": entry.get("packet"), "finding": entry.get("finding"),
                              "at": entry.get("at"), "changed": entry.get("changed") or [], "checks": entry.get("auto_accept_checks") or {}})
    return found


def close_workspace(workspace: Path, status: str, reason: str, *, day: str | None = None) -> str:
    """End revival work on a mod: a dated revival-report section ending in SUPERSEDED or NOT_REVIVABLE, which every
    queue command then skips (report_status.CLOSED_STATUSES). Nothing is moved or deleted. A `Done/<Mod>` archive is closed
    the same way, in its `workspace/REVIVAL_REPORT.md`, and done-audit and target-impact then list it instead of checking it
    (ROADMAP-3 item 95.15)."""
    from .report_status import CLOSED_STATUSES, archive_report

    if status not in CLOSED_STATUSES:
        raise ValueError(f"status must be one of {', '.join(CLOSED_STATUSES)}")
    root = Path(workspace).expanduser().resolve()
    if not (root / "working").is_dir() and root.name == root.parent.name and archive_report(root.parent).is_file():
        root = root.parent  # the Done/<Mod>/<Mod> copy target-impact names: close its archive, Done/<Mod>
    if (root / "working").is_dir():
        report = root / "working" / "reports" / "REVIVAL_REPORT.md"
    elif archive_report(root).is_file():
        report = archive_report(root)
    else:  # writing a report nothing reads would look like a close and change nothing (review 2026-11-17)
        raise ValueError(f"{root} is neither a queue workspace (working/) nor a Done/<Mod> archive (workspace/REVIVAL_REPORT.md)")
    report.parent.mkdir(parents=True, exist_ok=True)
    body = report.read_text(encoding="utf-8").rstrip() if report.is_file() else "# Revival report"
    title = "Superseded" if status == "SUPERSEDED" else "Not revivable"  # the reason names the build (96.5 A1: it said RC8 for every build)
    report.write_text(body + f"\n\n## {title} ({day or date.today().isoformat()})\n\n{reason.strip()}\n\n{status}\n", encoding="utf-8")
    return str(report)


def declare_providers(workspace: Path, *, apply: bool = False) -> dict:
    """Apply a `content-reference-unresolved` packet whose recommended strategy is SWAP: every needed id is provided
    by visible 0.98 mods, so the fix is declaring them as dependencies and nothing else changes (2026-10-01: 9 of the
    21 mods it blocked). Any other strategy (ESCALATE, STRIP_FROM_MOD) is left for a person."""
    from .fixers import _add_dependency_entry
    from bridgeforge.scan.scanner import _parse_json

    workspace = Path(workspace).expanduser().resolve()
    info_path = workspace / "working" / "mod_info.json"
    result = {"workspace": workspace.name, "state": "NO_PACKET", "declared": []}
    for packet_path in sorted((workspace / "reports" / "escalations").glob("content-reference-unresolved--*.json")):
        subs = (json.loads(packet_path.read_text(encoding="utf-8")).get("options") or {}).get("substitutes") or {}
        if subs.get("strategy") != "SWAP" or subs.get("uncovered"):
            result.update({"state": "NOT_SWAP", "strategy": subs.get("strategy"), "reason": subs.get("reason")})
            return result
        raw = info_path.read_text(encoding="utf-8")
        info, _ = _parse_json(raw)
        have = {str(d.get("id") if isinstance(d, dict) else d).lower() for d in (info.get("dependencies") or [])}
        text = raw
        for provider in subs.get("providers") or []:
            if provider.get("mod_id") and provider["mod_id"].lower() not in have:
                text = _add_dependency_entry(text, provider["mod_id"], provider.get("name") or provider["mod_id"])
                result["declared"].append(f"{provider['mod_id']} ({provider.get('name')}, {provider.get('game_version')})")
        _parse_json(text)  # must still parse
        result["state"] = "DECLARED" if result["declared"] else "ALREADY_DECLARED"
        if apply and text != raw:
            backup = info_path.with_name("mod_info.json.pre-bf-declare-providers.bak")
            if not backup.exists():
                shutil.copy2(info_path, backup)
            info_path.write_text(text, encoding="utf-8")
    return result
