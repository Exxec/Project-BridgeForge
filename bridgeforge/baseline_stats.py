"""`bridgeforge baseline-stats`: which checks get accepted as harmless most (ROADMAP 48, owner request 2026-10-05).

Every key in a workspace's `working/reports/baseline*.json` is a finding someone reviewed and accepted (the key is
`<finding id>|<file>|<first evidence>`, bridgeforge.baseline). Counted per finding id across the queue, the top of
the list is where a check needs refining: on 2026-10-04/05 most escalations were accepted false positives in about ten
checks (faction tags, interface methods, settings keys, system generation, entity references). Read-only.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path


def baseline_stats(queue: Path) -> dict:
    by_id: Counter[str] = Counter()
    mods_by_id: dict[str, set[str]] = defaultdict(set)
    workspaces = 0
    for working in sorted(Path(queue).glob("*/working")):
        files = sorted((working / "reports").glob("baseline*.json")) if (working / "reports").is_dir() else []
        if not files:
            continue
        workspaces += 1
        for path in files:
            try:
                keys = json.loads(path.read_text(encoding="utf-8")).get("findings") or []
            except (OSError, ValueError):
                continue
            for key in keys:
                finding_id = str(key).split("|", 1)[0]
                by_id[finding_id] += 1
                mods_by_id[finding_id].add(working.parent.name)
    rows = [{"id": finding_id, "accepted": count, "mods": len(mods_by_id[finding_id]),
             "examples": sorted(mods_by_id[finding_id])[:5]} for finding_id, count in by_id.most_common()]
    return {"schema_version": 1, "mode": "BASELINE_STATS", "queue": str(queue), "workspaces_with_baseline": workspaces,
            "accepted_total": sum(by_id.values()), "checks": rows}


def render(result: dict, top: int = 25) -> str:
    lines = [f"{result['accepted_total']} accepted finding(s) in {result['workspaces_with_baseline']} workspace baseline(s).",
             "", "| Check | Accepted | Mods | e.g. |", "|---|---:|---:|---|"]
    for row in result["checks"][:top]:
        lines.append(f"| `{row['id']}` | {row['accepted']} | {row['mods']} | {', '.join(row['examples'][:3])} |")
    return "\n".join(lines)
