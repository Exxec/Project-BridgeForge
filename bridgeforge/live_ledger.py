"""`live-ledger`: every recorded live run and regression pass in one list (ROADMAP 70 H3.2).

The data already exists: `probe-group record` writes `In operation/_live/<TESTID>.json` (members with versions, shipped hashes and
verdicts, probe config hash, triage), and `probe-group regress` writes `In operation/_regress/*.json`. Results were scattered across
those files, logs and roadmap prose; this reads them together so "what was the last good run of this mod, at which version, and has
anything run it since" has one answer.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _version(value: object) -> str | None:
    if isinstance(value, dict):  # mod_info.json's {"major": "0", "minor": "3", "patch": "3"} form
        return ".".join(str(value[k]) for k in ("major", "minor", "patch") if value.get(k) not in (None, ""))
    return str(value) if value not in (None, "") else None


def _load(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def read_runs(queue: Path) -> list[dict]:
    """One row per (run, mod): {"source", "test_id", "date", "mod", "workspace", "version", "verdict"}, oldest first."""
    queue = Path(queue)
    rows: list[dict] = []
    for path in sorted((queue / "_live").glob("*.json")):
        data = _load(path)
        if not data or not isinstance(data.get("members"), list):
            continue
        for member in data["members"]:
            rows.append({"source": "record", "test_id": data.get("test_id") or path.stem, "date": data.get("date") or "",
                         "mod": member.get("mod_id"), "workspace": member.get("workspace"), "version": _version(member.get("version")),
                         "verdict": member.get("verdict")})
    for path in sorted((queue / "_regress").glob("*.json")):
        data = _load(path)
        if not data or not isinstance(data.get("groups"), list):
            continue
        for group in data["groups"]:
            members = group.get("members")
            if isinstance(members, dict):
                for mod, verdict in members.items():
                    rows.append({"source": "regress", "test_id": group.get("test_id") or "", "date": data.get("date") or "",
                                 "mod": mod, "workspace": None, "version": None, "verdict": verdict})
    return sorted(rows, key=lambda r: (r["date"], r["test_id"]))


def last_runs(rows: list[dict]) -> dict[str, dict]:
    """Per mod: its last PASS, its last run of any kind, and whether a later run was not a PASS."""
    out: dict[str, dict] = {}
    for row in rows:
        entry = out.setdefault(row["mod"], {"last_pass": None, "last_run": None, "runs": 0})
        entry["runs"] += 1
        entry["last_run"] = row
        if row["verdict"] == "PASS":
            entry["last_pass"] = row
    for entry in out.values():
        entry["attention"] = entry["last_run"] is not None and entry["last_run"]["verdict"] != "PASS"
    return out


def add_parser(subcommands) -> None:
    ledger = subcommands.add_parser("live-ledger", help="list recorded live runs and regression passes per mod: last PASS, last run, mods whose latest run did not PASS")
    ledger.add_argument("--queue", type=Path, default=Path("In operation"))
    ledger.add_argument("--mod", help="only this mod id")
    ledger.add_argument("--attention", action="store_true", help="only mods whose latest run was not a PASS")
    ledger.add_argument("--json", action="store_true")


def run_cli(args: argparse.Namespace) -> int:
    rows = read_runs(args.queue)
    per_mod = {m: e for m, e in last_runs(rows).items() if (not args.mod or m == args.mod) and (not args.attention or e["attention"])}
    if args.json:
        print(json.dumps({"mods": per_mod, "runs": len(rows)}, indent=2))
        return 0
    print(f"{len(rows)} run row(s) for {len(last_runs(rows))} mod(s); showing {len(per_mod)}")
    for mod, entry in sorted(per_mod.items()):
        last, good = entry["last_run"], entry["last_pass"]
        print(f"  {mod}: last PASS {good['test_id'] + ' ' + str(good['version'] or '') if good else 'none'}; last run {last['test_id']} {last['verdict']}"
              + ("  <- needs a look" if entry["attention"] else ""))
    return 0
