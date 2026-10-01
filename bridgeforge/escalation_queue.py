"""`bridgeforge escalation queue`: what the escalated mods across a queue are waiting on (2026-09-27).

After the first batch revive, 227 of 235 mods came back ESCALATED. Deciding one mod at a time hides that a
few findings block most of them (description-missing 123 mods, undeclared-library-dependency 98, ...), and
that a decision on one finding id can clear every mod it is the only blocker for. This groups every ESCALATED
workspace's packets by finding and tier, counts the mods each blocks and the mods it alone blocks, and writes
ESCALATIONS_BY_FINDING.json/.md into the queue. Read-only apart from those two files and its checkpoint.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .progress import Checkpoint, report
from .report_status import is_closed

SCHEMA_VERSION = 1
RESULT_JSON = "ESCALATIONS_BY_FINDING.json"
RESULT_MD = "ESCALATIONS_BY_FINDING.md"
CHECKPOINT_FILE = "ESCALATIONS_BY_FINDING.partial.jsonl"


def _workspace_packets(workspace: Path) -> dict | None:
    revive = workspace / "reports" / "revive" / "REVIVE.json"
    if not revive.is_file():
        return None
    data = json.loads(revive.read_text(encoding="utf-8"))
    if data.get("status") != "ESCALATED":
        return {"status": data.get("status"), "blockers": []}
    blockers = sorted({(finding, p.get("tier"), p.get("kind")) for p in data.get("packets") or [] if p.get("finding")
                       for finding in p.get("merged") or [p["finding"]]})
    return {"status": "ESCALATED", "blockers": [list(b) for b in blockers]}


def summarize_queue(queue: Path, quiet: bool = False) -> dict:
    queue = Path(queue).expanduser().resolve()
    workspaces = sorted(p for p in queue.iterdir() if p.is_dir() and not p.name.startswith("_") and (p / "reports" / "revive" / "REVIVE.json").is_file() and not is_closed(p))
    header = {"schema_version": SCHEMA_VERSION, "queue": str(queue),
              "revive_mtimes": {w.name: (w / "reports" / "revive" / "REVIVE.json").stat().st_mtime for w in workspaces}}
    by_finding: dict[tuple, dict] = {}
    escalated = 0
    with Checkpoint(queue / CHECKPOINT_FILE, header) as checkpoint:
        for number, workspace in enumerate(workspaces, 1):
            started = time.perf_counter()
            cached = checkpoint.get(workspace.name)
            record = cached if cached is not None else _workspace_packets(workspace)
            if cached is None:
                checkpoint.add(workspace.name, record)
            if not quiet:
                detail = f"{len(record['blockers'])} blocker(s)" if record["status"] == "ESCALATED" else record["status"] or "?"
                report(number, len(workspaces), workspace.name, detail, None if cached is not None else time.perf_counter() - started)
            if record["status"] != "ESCALATED":
                continue
            escalated += 1
            ids = {b[0] for b in record["blockers"]}
            for finding, tier, kind in record["blockers"]:
                entry = by_finding.setdefault((finding, tier, kind), {"finding": finding, "tier": tier, "kind": kind, "mods": [], "only_blocker": []})
                entry["mods"].append(workspace.name)
                if len(ids) == 1:
                    entry["only_blocker"].append(workspace.name)
        rows = sorted(by_finding.values(), key=lambda e: (-len(e["only_blocker"]), -len(e["mods"]), e["finding"]))
        result = {"schema_version": SCHEMA_VERSION, "mode": "ESCALATION_QUEUE", "queue": str(queue), "escalated": escalated, "findings": rows,
                  "result_json": str(queue / RESULT_JSON), "result_md": str(queue / RESULT_MD)}
        (queue / RESULT_JSON).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        (queue / RESULT_MD).write_text(render(result), encoding="utf-8")
        checkpoint.finish()
    return result


def render(result: dict) -> str:
    lines = [f"# What the escalated mods are waiting on ({result['escalated']} mods)", "",
             "One decision on a finding id can clear every mod it is the only blocker for. Sorted by that, then by mods blocked.", "",
             "| Finding | Tier | Kind | Mods blocked | Only blocker for |", "|---|---|---|---|---|"]
    for row in result["findings"]:
        lines.append(f"| `{row['finding']}` | {row['tier']} | {row['kind']} | {len(row['mods'])} | {len(row['only_blocker'])} |")
    lines += ["", "## Mods one decision would clear", ""]
    for row in result["findings"]:
        if row["only_blocker"]:
            lines.append(f"- `{row['finding']}`: " + ", ".join(row["only_blocker"]))
    return "\n".join(lines) + "\n"


def rule(queue: Path, finding_id: str, *, accept: bool = False, approve_fixer: bool = False, reason: str, policy: Path | None = None,
         today: str | None = None) -> dict:
    """Record one owner ruling for a finding id across the queue (ROADMAP P15 31.12), instead of rulings typed into
    chat and applied by hand. `accept`: add the finding's packet entries to every ESCALATED mod's accepted-findings
    baseline, with the reason in ESCALATION_RULINGS.jsonl. `approve_fixer`: add the fixer to AUTOMATION_POLICY.json's
    standing approvals (revive then applies it)."""
    from datetime import date

    from .baseline import accept_findings
    from .fixers import SUPPORTED_FINDINGS

    if accept == approve_fixer:
        raise ValueError("choose exactly one of accept or approve_fixer.")
    if not reason.strip():
        raise ValueError("a ruling needs a reason.")
    queue = Path(queue).expanduser().resolve()
    today = today or date.today().isoformat()
    touched = []
    if approve_fixer:
        if finding_id not in SUPPORTED_FINDINGS:
            raise ValueError(f"{finding_id} has no fixer to approve; use accept.")
        policy = Path(policy or queue / "AUTOMATION_POLICY.json")
        data = json.loads(policy.read_text(encoding="utf-8")) if policy.is_file() else {"approved_fixers": {}}
        data.setdefault("approved_fixers", {})[finding_id] = {"reason": reason, "recorded_on": today}
        body = "{\n  \"approved_fixers\": {\n" + ",\n".join(f"    {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}" for k, v in data["approved_fixers"].items()) + "\n  }\n}\n"
        policy.write_text(body, encoding="utf-8")
    else:
        for workspace in sorted(p for p in queue.iterdir() if p.is_dir() and not p.name.startswith("_") and not is_closed(p)):
            record = _workspace_packets(workspace)
            if not record or record["status"] != "ESCALATED":
                continue
            keys = []
            for path in (workspace / "reports" / "escalations").glob("*--*.json"):
                packet = json.loads(path.read_text(encoding="utf-8"))
                if finding_id not in (packet.get("merged") or [packet.get("finding") or path.name.split("--", 1)[0]]):
                    continue
                for finding in packet.get("findings") or []:
                    if finding.get("id") != finding_id:
                        continue
                    evidence = finding.get("evidence") or []
                    keys.append(f"{finding.get('id')}|{finding.get('file') or ''}|{evidence[0] if evidence else ''}")
            if keys:
                accept_findings(workspace / "working", keys)
                touched.append(workspace.name)
    entry = {"date": today, "finding": finding_id, "ruling": "accept" if accept else "approve-fixer", "reason": reason, "mods": touched}
    with (queue / "ESCALATION_RULINGS.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry
