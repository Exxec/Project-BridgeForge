"""`bridgeforge check-impact`: what a scanner change does to one finding across the queue (ROADMAP P15 31.10).

After each false-positive fix on 2026-09-28 (hullmod-instance-state, runtime placeholders, sounds.json) the effect
was measured with a hand-written loop. This rescans the workspaces whose escalation packets hold the finding
(`reports/escalations/<id>--*.json`, the "before") and reports which are now cleared, reduced or unchanged; with
`all_workspaces` it also scans the rest for mods newly flagged. Read-only apart from its result and checkpoint.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .progress import Checkpoint, report

SCHEMA_VERSION = 1


def _before(workspace: Path, finding_id: str) -> int:
    count = 0
    for path in (workspace / "reports" / "escalations").glob(f"{finding_id}--*.json"):
        try:
            count += len(json.loads(path.read_text(encoding="utf-8")).get("findings") or [])
        except (OSError, ValueError):
            continue
    return count


def check_impact(queue: Path, finding_id: str, *, vanilla_core: Path | None = None, all_workspaces: bool = False,
                 quiet: bool = False, scan=None) -> dict:
    from .scanner import scan_mod

    scan = scan or (lambda working: scan_mod(working, vanilla_core=vanilla_core).findings)
    queue = Path(queue).expanduser().resolve()
    candidates = sorted(p for p in queue.iterdir() if p.is_dir() and not p.name.startswith("_") and (p / "working" / "mod_info.json").is_file())
    if not all_workspaces:
        candidates = [w for w in candidates if _before(w, finding_id)]
    header = {"schema_version": SCHEMA_VERSION, "queue": str(queue), "finding": finding_id, "all": all_workspaces,
              "workspaces": [w.name for w in candidates]}
    result_path = queue / f"CHECK_IMPACT_{finding_id}.json"
    rows = []
    with Checkpoint(queue / f"CHECK_IMPACT_{finding_id}.partial.jsonl", header) as checkpoint:
        for number, workspace in enumerate(candidates, 1):
            cached = checkpoint.get(workspace.name)
            started = time.perf_counter()
            if cached is None:
                before = _before(workspace, finding_id)
                now = sum(1 for f in scan(workspace / "working") if f.id == finding_id)
                verdict = ("CLEARED" if now == 0 else "REDUCED" if now < before else "UNCHANGED") if before else ("NEW" if now else "NONE")
                cached = {"workspace": workspace.name, "before": before, "now": now, "verdict": verdict}
                checkpoint.add(workspace.name, cached)
            rows.append(cached)
            if not quiet:
                report(number, len(candidates), workspace.name, f"{cached['verdict']} ({cached['before']} -> {cached['now']})",
                       None if checkpoint.get(workspace.name) is not cached else time.perf_counter() - started)
        counts: dict[str, int] = {}
        for row in rows:
            counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
        result = {"schema_version": SCHEMA_VERSION, "mode": "CHECK_IMPACT", "finding": finding_id, "counts": counts,
                  "mods": rows, "result_path": str(result_path)}
        result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        checkpoint.finish()
    return result
