"""`probe-group live-queue`: install, play, report and (on the owner's standing word) record and archive each group of a plan
(ROADMAP-3 95.3, the live half; 96.2 lessons, 2026-11-19).

The 96.2 ports ran every group by hand: a task script per group (rig-doctor, install, live, report), then `record --archive
--refresh` as a separate step. This runs the groups of one plan in order, one game at a time:

- each group is installed with `--stage-providers --save-after-checks` and the plan's extra mods, then played (`live_run`);
- a run that ends LIVE_DONE is judged with `probe-group report`; with `archive`, `record_group(..., archive=True)` records
  and archives its PASS members (record itself skips any other verdict, and refuses a run not bound to its inputs);
- a run that does not end LIVE_DONE is never recorded: its stage and detail go to the summary's `attention` list, with the
  log and the harness's actions file (96.9) to triage (the `bridgeforge-live-triage` skill).

`archive` is the owner's standing permission for this batch (owner 2026-11-19, 96.2: "sure archive them if they pass"); without it
the queue only plays and reports, as `regress` does for validated mods. One progress line per group and a checkpoint, so an
interrupted queue resumes after the last finished group.
"""
from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path
from typing import Callable

from .live.pause import refusal
from .progress import Checkpoint, report
from .safeio import atomic_write_text

CONFIG_RELATIVE = Path("saves") / "common" / "bf_probe_config.data"


def _members(group: dict) -> list[str]:
    return [m["workspace"] for m in group["members"]]


def _summary(row: dict) -> str:
    if row.get("error"):
        return f"ERROR {row['error']}"
    live = row.get("live") or {}
    if live.get("verdict") != "LIVE_DONE":
        return f"{live.get('verdict')} at {live.get('stage')}"
    verdicts = ", ".join(f"{mod} {verdict}" for mod, verdict in sorted((row.get("verdicts") or {}).items()))
    archived = row.get("archived")
    text = verdicts + (f"; archived {', '.join(archived)}" if archived else "")
    if row.get("record_stopped"):
        text += f"; record stopped: {row['record_stopped'].get('why')}"
    for item in row.get("not_recorded") or []:
        text += f"; not archived: {item.get('mod_id')} ({item.get('archive') or item.get('verdict')})"
    return text


def live_queue(plan_path: Path, queue: Path, rig: Path, out: Path, *, groups: list[int] | None = None, archive: bool = False,
               refresh: bool = False, note: str = "", test_prefix: str | None = None, bat: str | None = None,
               also_enable: list[str] | None = None, quiet: bool = False, play: Callable | None = None,
               install: Callable | None = None, judge: Callable | None = None, record: Callable | None = None,
               direct=None) -> dict:
    """Run the plan's groups (all, or the numbers in `groups`) and write the summary to `out`. `play`, `install`, `judge` and
    `record` default to live_run, install_group, group_report and record_group (tests pass stand-ins)."""
    from bridgeforge.probe.probe_group import install_group
    from bridgeforge.probe.probe_record import accepted_probe_findings, group_report, record_group

    queue, rig, out = Path(queue).expanduser().resolve(), Path(rig).expanduser().resolve(), Path(out)
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    if play is None:
        import functools

        from bridgeforge.live.live_run import live_run
        # 95.4: a direct start (no launcher, window placed) passes through to every group's run.
        play = functools.partial(live_run, direct=direct) if direct is not None else live_run
    install = install or (lambda plan, n: install_group(plan, n, queue, rig, stage=True, save_after_checks=True,
                                                        also_enable=list(also_enable or [])))
    judge = judge or (lambda log, config: group_report(log, config, mods_dir=rig / "mods",
                                                       accepted=accepted_probe_findings(queue, rig / "mods")))
    record = record or (lambda log, config, test_id: record_group(log, config, queue, rig, test_id=test_id, archive=True,
                                                                  refresh=refresh, accept=True, note=note or None))
    chosen = [g for g in plan.get("groups", []) if not groups or g["group"] in set(groups)]
    prefix = test_prefix or f"LQ-{date.today():%Y%m%d}"
    header = {"command": "probe-group live-queue", "plan": str(Path(plan_path).resolve()), "rig": str(rig), "archive": archive,
              "groups": [f"G{g['group']}:" + "+".join(_members(g)) for g in chosen]}
    rows: list[dict] = []
    checkpoint = Checkpoint(out.with_name(out.stem + ".partial.jsonl"), header)
    try:
        for index, group in enumerate(chosen, 1):
            key = f"G{group['group']}:" + "+".join(_members(group))
            saved = checkpoint.get(key)
            if saved is not None:
                rows.append(saved)
                if not quiet:
                    report(index, len(chosen), f"group {group['group']}", saved["summary"], None)
                continue
            started = time.monotonic()
            test_id = f"{prefix}-G{group['group']}"
            row: dict = {"group": group["group"], "members": _members(group), "test_id": test_id}
            refused = refusal()
            if refused:  # paused (98.16): the group is not installed either
                row["live"] = {"verdict": "LIVE_STUCK", "stage": "refused", "detail": refused, "log": None}
            else:
                try:
                    _run_group(row, plan, group["group"], rig, test_id, bat, archive, play, install, judge, record)
                except Exception as exc:  # one broken group never stops the queue; it is never recorded
                    row["error"] = f"{type(exc).__name__}: {exc}"
            row["summary"] = _summary(row)
            rows.append(row)
            if (row.get("live") or {}).get("stage") == "refused":
                # Not checkpointed, so a resumed queue plays it once live testing is back; the rest wait too (review, 2026-11-27).
                if not quiet:
                    report(index, len(chosen), f"group {group['group']}", f"{row['summary']}: live testing is paused, queue stopped", None)
                break
            checkpoint.add(key, row)
            if not quiet:
                report(index, len(chosen), f"group {group['group']}", row["summary"], time.monotonic() - started)
    finally:
        checkpoint.close()
    paused = bool(rows) and (rows[-1].get("live") or {}).get("stage") == "refused"
    result = {"mode": "PROBE_GROUP_LIVE_QUEUE", "date": f"{date.today():%Y-%m-%d}", "archive": archive, "groups": rows,
              "attention": [r for r in rows if _needs_a_look(r, archive)]}
    if paused:
        result["stopped"] = "live testing is paused: run the same command again after `live resume` to play the rest"
    out.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out, json.dumps(result, indent=2, ensure_ascii=False))
    if not paused:  # a paused queue keeps its checkpoint, so the groups it played are not played again
        checkpoint.finish()
    return result


def _needs_a_look(row: dict, archive: bool) -> bool:
    """A group a person must look at: an error, a run that did not finish, a member that did not PASS, or (with archive) a PASS
    member left unarchived. Record and archive stop on an uncovered caught exception, an unexplained shipped change, a junk
    file or a stale live result (Vayra's Sector, 2026-11-19, passed live and needed all four explained by hand)."""
    if row.get("error") or (row.get("live") or {}).get("verdict") != "LIVE_DONE":
        return True
    verdicts = row.get("verdicts") or {}
    if any(v != "PASS" for v in verdicts.values()):
        return True
    return archive and (bool(row.get("record_stopped")) or len(row.get("archived") or []) < len(verdicts))


def _run_group(row: dict, plan: dict, number: int, rig: Path, test_id: str, bat: str | None, archive: bool,
               play: Callable, install: Callable, judge: Callable, record: Callable) -> None:
    """Install, play and judge one group into `row`; record it only after LIVE_DONE, and only with `archive`."""
    install(plan, number)
    live = play(rig, test_id, bat_name=bat) if bat else play(rig, test_id)
    row["live"] = {"verdict": live.verdict, "stage": live.stage, "detail": live.detail, "log": live.log,
                   "prepatcher": getattr(live, "prepatcher", None)}  # 98.18; a stubbed play may return an older shape
    if live.verdict != "LIVE_DONE":
        actions = Path(f"{live.log}.actions.json") if live.log else None
        row["triage"] = {"log": live.log, "actions": str(actions) if actions and actions.is_file() else None}
        return
    config = json.loads((rig / CONFIG_RELATIVE).read_text(encoding="utf-8"))
    verdicts = judge(Path(live.log), config)
    row["verdicts"] = {mod: v.get("verdict") for mod, v in verdicts["members"].items()}
    if not archive:
        return
    recorded = record(Path(live.log), config, test_id)
    row["recorded"] = list(recorded.get("recorded") or [])
    row["archived"] = list(recorded.get("archived") or [])
    row["not_recorded"] = list(recorded.get("skipped") or [])
    if recorded.get("stopped"):
        row["record_stopped"] = recorded["stopped"]
