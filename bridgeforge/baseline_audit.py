"""Accepted-finding baselines expire when the mod's version changes (ROADMAP 70, H1.5; owner decision 2026-10-12).

A baseline hides findings someone accepted. Zorg18's scanner findings for two real star-system bugs sat in its accepted baseline while
V18+bf.7 shipped without the fixes that existed for them: an accepted finding was never looked at again. A baseline now carries a
stamp (the mod version it was accepted at and the date) and optional reasons per key. Any version change makes the stamp stale and
`baseline-audit` lists it; `record --archive` refuses a stale baseline unless the caller gives a written reason.

The file format stays `{"findings": [...]}` with two optional extra keys, so every reader of baselines keeps working:
    "stamp":   {"version": "V18+bf.8", "date": "2026-10-12"}
    "reasons": {"<finding key>": "why this was accepted"}
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from .baseline import mod_baseline_path
from .safeio import atomic_write_text
from .scanner import _load_lenient_json_file

STATUSES = ("OK", "STALE_VERSION", "UNSTAMPED", "NO_BASELINE")


def mod_version(working: Path) -> str:
    info = _load_lenient_json_file(Path(working) / "mod_info.json")
    version = info.get("version") if isinstance(info, dict) else None
    if isinstance(version, dict):
        version = ".".join(str(version.get(k, "")) for k in ("major", "minor", "patch") if version.get(k, "") != "")
    return str(version) if version not in (None, "") else ""


def _load(path: Path) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def stamp_baseline(path: Path, working: Path, reason: str | None = None, today: str | None = None) -> dict:
    """Record the mod's current version and today's date on the baseline; `reason` is kept for every key that has none."""
    payload = _load(path)
    payload.setdefault("findings", [])
    payload["stamp"] = {"version": mod_version(working), "date": today or date.today().isoformat()}
    if reason:
        reasons = payload.setdefault("reasons", {})
        for key in payload["findings"]:
            reasons.setdefault(key, reason)
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def audit_workspace(workspace: Path) -> dict:
    working = Path(workspace) / "working"
    path = mod_baseline_path(working) if working.is_dir() else None
    row = {"workspace": Path(workspace).name, "baseline": str(path) if path else None, "status": "NO_BASELINE", "entries": 0,
           "without_reason": 0, "stamped_version": None, "current_version": mod_version(working) if working.is_dir() else ""}
    if path is None:
        return row
    try:
        payload = _load(path)
    except (OSError, ValueError):
        row["status"] = "UNSTAMPED"
        return row
    findings = payload.get("findings", [])
    row["entries"] = len(findings)
    row["without_reason"] = sum(1 for key in findings if not (payload.get("reasons") or {}).get(key))
    stamp = payload.get("stamp")
    if not isinstance(stamp, dict) or "version" not in stamp:
        row["status"] = "UNSTAMPED"
        return row
    row["stamped_version"], row["stamped_on"] = stamp["version"], stamp.get("date")
    row["status"] = "OK" if stamp["version"] == row["current_version"] else "STALE_VERSION"
    return row


def audit_queue(queue: Path) -> list[dict]:
    queue = Path(queue)
    return [audit_workspace(ws) for ws in sorted(p for p in queue.iterdir() if p.is_dir() and not p.name.startswith("_"))
            if (ws / "working" / "mod_info.json").is_file()]


def accept_workspace(workspace: Path, reason: str) -> dict:
    """Re-stamp a workspace's baseline at the mod's current version with a written reason (the owner's re-justification)."""
    if not reason.strip():
        raise ValueError("a reason is required to accept a baseline again")
    working = Path(workspace) / "working"
    path = mod_baseline_path(working)
    if path is None:
        raise ValueError(f"{workspace} has no baseline to accept")
    stamp_baseline(path, working, reason.strip())
    return audit_workspace(workspace)


def summary(rows: list[dict]) -> dict[str, int]:
    counts = {status: 0 for status in STATUSES}
    for row in rows:
        counts[row["status"]] += 1
    return counts


def add_parser(subcommands) -> None:
    audit = subcommands.add_parser("baseline-audit", help="list accepted-finding baselines by status: OK, STALE_VERSION (the mod's version changed since it was accepted), UNSTAMPED (older than stamping), NO_BASELINE")
    audit.add_argument("--queue", type=Path, default=Path("In operation"), help="default: In operation")
    audit.add_argument("--only", choices=STATUSES, help="list only this status")
    audit.add_argument("--json", action="store_true")
    accept = subcommands.add_parser("baseline-accept", help="re-stamp a workspace's baseline at the mod's current version with a written reason (or every UNSTAMPED one with --all-unstamped)")
    accept.add_argument("workspace", nargs="?", type=Path)
    accept.add_argument("--all-unstamped", action="store_true", help="stamp every UNSTAMPED baseline in --queue (the one-time start of the clock)")
    accept.add_argument("--queue", type=Path, default=Path("In operation"))
    accept.add_argument("--reason", required=True, help="why these accepted findings still stand")
    accept.add_argument("--json", action="store_true")


def run_cli(args: argparse.Namespace) -> int:
    try:
        if args.command == "baseline-audit":
            rows = audit_queue(args.queue)
            counts = summary(rows)
            shown = [r for r in rows if not args.only or r["status"] == args.only]
            if args.json:
                print(json.dumps({"summary": counts, "rows": shown}, indent=2))
            else:
                print("Baselines: " + ", ".join(f"{n} {s}" for s, n in counts.items()))
                for row in shown:
                    if row["status"] in ("STALE_VERSION", "UNSTAMPED") or args.only:
                        print(f"  {row['status']:<13} {row['workspace']}: {row['entries']} entr(ies), {row['without_reason']} without a reason"
                              + (f"; accepted at {row['stamped_version']}, now {row['current_version']}" if row["status"] == "STALE_VERSION" else ""))
            return 0
        if args.all_unstamped:
            done = []
            for row in audit_queue(args.queue):
                if row["status"] == "UNSTAMPED":
                    done.append(accept_workspace(args.queue / row["workspace"], args.reason))
            print(json.dumps(done, indent=2) if args.json else f"Stamped {len(done)} baseline(s) at their current versions.")
            return 0
        if args.workspace is None:
            print("bridgeforge: give a workspace or --all-unstamped", file=sys.stderr)
            return 2
        row = accept_workspace(args.workspace, args.reason)
        print(json.dumps(row, indent=2) if args.json else f"{row['workspace']}: {row['status']} at {row['current_version']}")
        return 0
    except (OSError, ValueError) as exc:
        print(f"bridgeforge: {exc}", file=sys.stderr)
        return 2
