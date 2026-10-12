"""`bridgeforge revive-queue`: run `revive` across a queue (ROADMAP P15 item 31.2).

The 2026-09-27/28 sessions drove the batch revive and three re-runs with shell scripts and a stamp file for resume.
This walks the queue's workspaces (all of them, those never revived, or those whose last REVIVE.json status is in
`only_status`), prints one progress line per mod, keeps a checkpoint so an interrupted run resumes, and writes
REVIVE_QUEUE.json with every mod's status.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .progress import Checkpoint, report
from .report_status import is_closed

SCHEMA_VERSION = 1
RESULT_FILE = "REVIVE_QUEUE.json"
CHECKPOINT_FILE = "REVIVE_QUEUE.partial.jsonl"


def _last_status(workspace: Path) -> str | None:
    path = workspace / "reports" / "revive" / "REVIVE.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("status")
    except (OSError, ValueError):
        return None


def select_workspaces(queue: Path, only_status: set[str] | None = None, never_revived: bool = False) -> list[Path]:
    chosen = []
    for workspace in sorted(p for p in Path(queue).iterdir() if p.is_dir() and not p.name.startswith("_") and not is_closed(p)):
        if not (workspace / "working" / "mod_info.json").is_file():
            continue
        status = _last_status(workspace)
        if never_revived and status is not None:
            continue
        if only_status and status not in only_status:
            continue
        chosen.append(workspace)
    return chosen


def revive_queue(queue: Path, *, only_status: set[str] | None = None, never_revived: bool = False, apply: bool = False,
                 draft_report: bool = False, vanilla_core: Path | None = None, quiet: bool = False, restart: bool = False,
                 revive_one=None, jobs: int = 1) -> dict:
    from .revive import ReviveError, revive

    revive_one = revive_one or revive
    queue = Path(queue).expanduser().resolve()
    workspaces = select_workspaces(queue, only_status, never_revived)
    header = {"schema_version": SCHEMA_VERSION, "queue": str(queue), "only_status": sorted(only_status or ()),
              "never_revived": never_revived, "apply": apply, "workspaces": [w.name for w in workspaces]}
    if restart and (queue / CHECKPOINT_FILE).is_file():
        (queue / CHECKPOINT_FILE).unlink()
    records = []
    with Checkpoint(queue / CHECKPOINT_FILE, header) as checkpoint:
        if jobs > 1 and revive_one is revive:
            # ROADMAP 49: each workspace's revive writes only inside that workspace, so they run side by side.
            from concurrent.futures import ProcessPoolExecutor, as_completed

            pending = [w for w in workspaces if checkpoint.get(w.name) is None]
            by_name = {}
            for w in workspaces:
                if checkpoint.get(w.name) is not None:
                    by_name[w.name] = checkpoint.get(w.name)
            done = len(by_name)
            with ProcessPoolExecutor(max_workers=jobs) as pool:
                futures = {pool.submit(_revive_worker, str(w), str(vanilla_core) if vanilla_core else None, apply, draft_report): w
                           for w in pending}
                for future in as_completed(futures):
                    cached, seconds = future.result()
                    checkpoint.add(cached["workspace"], cached)
                    by_name[cached["workspace"]] = cached
                    done += 1
                    if not quiet:
                        report(done, len(workspaces), cached["workspace"], cached["status"] or "?", seconds)
            records = [by_name[w.name] for w in workspaces]
            workspaces = []
        for number, workspace in enumerate(workspaces, 1):
            cached = checkpoint.get(workspace.name)
            started = time.perf_counter()
            if cached is None:
                try:
                    result = revive_one(workspace, vanilla_core=vanilla_core, apply=apply, draft_report=draft_report)
                    cached = {"workspace": workspace.name, "status": result.get("status"),
                              "blockers": sorted({f for p in result.get("packets") or [] if p.get("finding") for f in p.get("merged") or [p["finding"]]})}
                except (ReviveError, OSError, ValueError) as exc:
                    cached = {"workspace": workspace.name, "status": "ERROR", "error": str(exc), "blockers": []}
                checkpoint.add(workspace.name, cached)
                seconds = time.perf_counter() - started
            else:
                seconds = None
            records.append(cached)
            if not quiet:
                report(number, len(workspaces), workspace.name, cached["status"] or "?", seconds)
        counts: dict[str, int] = {}
        for record in records:
            counts[record["status"]] = counts.get(record["status"], 0) + 1
        result = {"schema_version": SCHEMA_VERSION, "mode": "REVIVE_QUEUE", "queue": str(queue), "counts": counts, "mods": records,
                  "result_path": str(queue / RESULT_FILE)}
        (queue / RESULT_FILE).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        checkpoint.finish()
    return result


def _revive_worker(workspace: str, vanilla_core: str | None, apply: bool, draft_report: bool) -> tuple[dict, float]:
    """One workspace in a worker process (revive_queue jobs > 1)."""
    from .revive import ReviveError, revive

    started = time.perf_counter()
    name = Path(workspace).name
    try:
        result = revive(Path(workspace), vanilla_core=Path(vanilla_core) if vanilla_core else None, apply=apply,
                        draft_report=draft_report)
        cached = {"workspace": name, "status": result.get("status"),
                  "blockers": sorted({f for p in result.get("packets") or [] if p.get("finding") for f in p.get("merged") or [p["finding"]]})}
    except (ReviveError, OSError, ValueError) as exc:
        cached = {"workspace": name, "status": "ERROR", "error": str(exc), "blockers": []}
    return cached, time.perf_counter() - started
