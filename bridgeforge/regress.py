"""Unattended regression pass over every live-validated workspace (ROADMAP 60g(1), 2026-10-11).

Clicks became reliable on 2026-10-11 (rig_prefs, screen_read), so every archived mod can get a current live result and a
probe 0.2.24+ `combat-perf` record without a person at the PC. The pass groups the LIVE_VALIDATED workspaces the way
`probe-group plan` groups new ones, then installs, plays (`probe-group live`) and reports each group. It never records:
statuses and archives stay as they are, and the result file lists what to look at (FAIL and UNCLEAR members, groups that
did not finish). One game at a time, so the run is long (about five minutes a group): one progress line per group and a
checkpoint, as every long-running command does.
"""
from __future__ import annotations

import json
import re
import time
from datetime import date
from pathlib import Path
from typing import Callable

from .progress import Checkpoint, report
from .safeio import atomic_write_text

LIVE_VALIDATED = "LIVE_VALIDATED"
_PERF = re.compile(r"BF-PROBE\|[^|]*\|combat-perf\|(?P<status>[^|]*)\|(?P<subject>[^|]*)\|(?P<detail>.*)$")
_SUPPLY_FAIL = re.compile(r"BF-PROBE\|[^|]*\|market-supply\|FAIL\|(?P<subject>[^|]*)\|")


def validated_workspaces(queue: Path) -> list[Path]:
    """Workspaces whose revival report's last status line is LIVE_VALIDATED."""
    from bridgeforge.probe.probe_group import _report_status

    queue = Path(queue).expanduser().resolve()
    return [ws for ws in sorted(p for p in queue.iterdir() if p.is_dir() and not p.name.startswith("_"))
            if (ws / "working" / "mod_info.json").is_file() and _report_status(ws) == LIVE_VALIDATED]


def perf_lines(log: Path) -> list[dict]:
    """The probe's combat-perf lines (frame times, peak hulks, runaway FAIL) from a run's log."""
    found = []
    try:
        text = Path(log).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return found
    for line in text.splitlines():
        match = _PERF.search(line)
        if match:
            found.append({"status": match["status"], "subject": match["subject"], "detail": match["detail"].strip()[:200]})
    return found


def _group_key(members: list[str]) -> str:
    return "+".join(sorted(members))


def run_regression(queue: Path, rig: Path, out: Path, *, bat: str | None = None, size: int = 8, limit: int | None = None,
                   only: list[str] | None = None, quiet: bool = False, test_prefix: str | None = None,
                   play: Callable | None = None, install: Callable | None = None, judge: Callable | None = None) -> dict:
    """Plan, install, play and report every group of live-validated workspaces; write the summary to `out`.
    `play`, `install` and `judge` default to live_run, install_group and group_report (tests pass stand-ins)."""
    from bridgeforge.probe.probe_group import accepted_probe_findings, group_report, install_group, plan_groups

    queue, rig, out = Path(queue).expanduser().resolve(), Path(rig).expanduser().resolve(), Path(out)
    if play is None:
        from bridgeforge.live.live_run import live_run as play
    install = install or (lambda plan, n: install_group(plan, n, queue, rig, stage=True))
    judge = judge or (lambda log, config: group_report(log, config, mods_dir=rig / "mods",
                                                       accepted=accepted_probe_findings(queue, rig / "mods")))
    workspaces = validated_workspaces(queue)
    if only:
        workspaces = [ws for ws in workspaces if ws.name in set(only)]
    plan = plan_groups(queue, rig, size=size, workspaces=workspaces)
    groups = plan.get("groups", [])[: limit or None]
    prefix = test_prefix or f"REG-{date.today():%Y%m%d}"
    header = {"command": "probe-group regress", "queue": str(queue), "rig": str(rig), "bat": bat, "size": size,
              "groups": [_group_key([m["workspace"] for m in g["members"]]) for g in groups]}
    rows: list[dict] = []
    checkpoint = Checkpoint(out.with_name(out.stem + ".partial.jsonl"), header)
    try:
        for index, group in enumerate(groups, 1):
            names = [m["workspace"] for m in group["members"]]
            key = _group_key(names)
            saved = checkpoint.get(key)
            if saved is not None:
                rows.append(saved)
                if not quiet:
                    report(index, len(groups), f"group {group['group']}", saved["summary"], None)
                continue
            started = time.monotonic()
            test_id = f"{prefix}-G{group['group']}"
            row: dict = {"group": group["group"], "members": names, "test_id": test_id}
            try:
                install(plan, group["group"])
                live = play(rig, test_id, bat_name=bat) if bat else play(rig, test_id)
                row["live"] = {"verdict": live.verdict, "stage": live.stage, "detail": live.detail, "rounds": live.rounds}
                config = json.loads((rig / "saves" / "common" / "bf_probe_config.data").read_text(encoding="utf-8"))
                if live.log and Path(live.log).is_file():
                    row["workspaces"] = names
                    _judge_row(row, judge(Path(live.log), config), Path(live.log))
                row["log"] = str(live.log) if live.log else None
            except Exception as exc:  # one broken group never stops the pass
                row["error"] = f"{type(exc).__name__}: {exc}"
            row["summary"] = _summary(row)
            rows.append(row)
            checkpoint.add(key, row)
            if not quiet:
                report(index, len(groups), f"group {group['group']}", row["summary"], time.monotonic() - started)
    finally:
        checkpoint.close()
    result = {"mode": "PROBE_GROUP_REGRESS", "date": f"{date.today():%Y-%m-%d}", "groups": rows,
              "unplaced": plan.get("unplaced", []), "attention": _attention(rows)}
    out.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out, json.dumps(result, indent=2, ensure_ascii=False))
    checkpoint.finish()
    return result


def _judge_row(row: dict, verdicts: dict, log: Path) -> None:
    """Put a group report's verdicts into a regress row (shared by a live pass and a re-judge)."""
    row["members"] = {mod: v.get("verdict") for mod, v in verdicts["members"].items()}
    row["failures"] = {mod: v["failures"] + v["crashes"] for mod, v in verdicts["members"].items() if v["failures"] or v["crashes"]}
    row["unattributed"] = verdicts["unattributed"]
    text = Path(log).read_text(encoding="utf-8", errors="replace")
    row["combat_perf"] = perf_lines(Path(log))
    row["supply_failures"] = sorted({m["subject"] for m in map(_SUPPLY_FAIL.search, text.splitlines()) if m})


def rejudge(queue: Path, rig: Path, source: Path, out: Path) -> dict:
    """Judge the saved logs of a finished (or running) pass again with the current group report, no game started. The report's attribution
    improved after REG-20261012-G1 (mission and class-sweep lines had no owner, so every member read UNCLEAR); a pass already run is
    re-read here instead of replayed. `source` is the pass's summary JSON or its partial checkpoint; a group's config is rebuilt from the
    workspaces that own its mod ids."""
    from bridgeforge.probe.probe_config import build_probe_config
    from bridgeforge.probe.probe_group import _workspaces_by_mod_id, accepted_probe_findings, group_report, merge_configs

    queue, rig = Path(queue).expanduser().resolve(), Path(rig).expanduser().resolve()
    source = Path(source)
    if source.suffix == ".jsonl":
        rows = [json.loads(line)["value"] for line in source.read_text(encoding="utf-8").splitlines()[1:] if line.strip()]
    else:
        rows = json.loads(source.read_text(encoding="utf-8"))["groups"]
    owners = _workspaces_by_mod_id(queue, rig / "mods")
    accepted = accepted_probe_findings(queue, rig / "mods")
    out_rows: list[dict] = []
    for row in rows:
        row = dict(row)
        members = row.get("members")
        log = row.get("log")
        if isinstance(members, dict) and log and Path(log).is_file():
            workspaces = [owners.get(mod) for mod in members]
            if all(w is not None for w in workspaces):
                config = merge_configs([build_probe_config(Path(w) / "working") for w in workspaces])
                _judge_row(row, group_report(Path(log), config, mods_dir=rig / "mods", accepted=accepted), Path(log))
                row["summary"] = _summary(row)
        out_rows.append(row)
    result = {"mode": "PROBE_GROUP_REGRESS_REJUDGED", "date": f"{date.today():%Y-%m-%d}", "source": str(source), "groups": out_rows,
              "unplaced": [], "attention": _attention(out_rows)}
    atomic_write_text(out, json.dumps(result, indent=2, ensure_ascii=False))
    return result

def _summary(row: dict) -> str:
    if "error" in row:
        return f"ERROR {row['error'][:120]}"
    live = row.get("live", {})
    if live.get("verdict") != "LIVE_DONE":
        return f"{live.get('verdict')} at {live.get('stage')}"
    members = row.get("members") or {}
    counts: dict[str, int] = {}
    for verdict in members.values() if isinstance(members, dict) else []:
        counts[verdict] = counts.get(verdict, 0) + 1
    worst = next((p["detail"] for p in row.get("combat_perf", []) if p["status"] == "FAIL"), None)
    return ", ".join(f"{n} {v}" for v, n in sorted(counts.items())) + (f"; RUNAWAY {worst}" if worst else "")


def _attention(rows: list[dict]) -> list[dict]:
    """What a person should look at: members that did not PASS, and groups that never reached a verdict."""
    found = []
    for row in rows:
        members = row.get("members")
        if "error" in row or row.get("live", {}).get("verdict") != "LIVE_DONE" or not isinstance(members, dict):
            found.append({"group": row["group"], "members": members if isinstance(members, list) else sorted(members or {}),
                          "why": row["summary"]})
            continue
        for mod, verdict in members.items():
            if verdict != "PASS":
                found.append({"group": row["group"], "mod": mod, "why": verdict,
                              "detail": (row.get("failures") or {}).get(mod, row.get("unattributed", []))[:5]})
    return found
