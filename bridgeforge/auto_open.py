"""`bridgeforge auto-open QUEUE`: why each open auto-tier finding is still open (ROADMAP item 73, A3).

An `auto`-tier finding has a fixer, so one that is still in a stored scan needs an explanation. Per workspace and finding id this
gives exactly one reason, first match wins:

- `STALE_SCAN` / `UNKNOWN_SCAN` / `INCOMPLETE_SCAN`: the scan registry (`scan_registry.assess`, item 75 R2) does not call the stored
  scan CURRENT: its inputs changed (STALE), it predates fingerprints (UNKNOWN) or cannot be verified (INCOMPLETE). The finding may
  be gone already, so no other reason is trusted; for UNKNOWN the reason the finding would otherwise have is kept in the detail.
- `NEVER_REVIVED`: no `reports/revive/REVIVE.json` and no escalation ledger: `revive` never ran on this workspace.
- `FIXER_REFUSED`: the fixer ran and refused. Read from the newest ledger entry for the id carrying that state, else from the
  workspace's escalation packets (`fixer.state`), which is where `revive` records a refusal today; the reason is quoted.
- `NOT_APPROVED`: not every finding of the id is SAFE and the id has no standing approval (`AUTOMATION_POLICY.json`) and was not
  given to `revive --approve`. Also when a packet carries the fixer's diff as AWAITING_APPROVAL.
- `UNEXPLAINED`: none of the above; a bug in the automation to fix.

Read-only. Findings the mod's own baseline accepts, and informational SAFE notes no fixer handles, are not counted.
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

from .automation import tier_for
from .baseline import finding_dict_baseline_key, mod_baseline_keys
from .finding_stats import read_ledger
from .progress import report
from .report_status import is_closed
from .scan_registry import assess

SCHEMA_VERSION = 1
POLICY_NAME = "AUTOMATION_POLICY.json"
REASONS = ("NOT_APPROVED", "FIXER_REFUSED", "NEVER_REVIVED", "STALE_SCAN", "UNKNOWN_SCAN", "INCOMPLETE_SCAN", "UNEXPLAINED")


class AutoOpenError(ValueError):
    """Raised for a missing queue."""


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def open_auto_findings(workspace: Path, report: Path | None) -> list[dict]:
    """Findings of the registered scan that are tier `auto`, not accepted by the mod's baseline and not informational."""
    from .revive import _informational

    if report is None:
        return []
    data = json.loads(Path(report).read_text(encoding="utf-8-sig"))
    findings = list(data.get("findings", data) if isinstance(data, dict) else data)
    accepted = mod_baseline_keys(workspace / "working")
    return [f for f in findings if tier_for(f.get("id", "?")) == "auto" and finding_dict_baseline_key(f) not in accepted
            and not _informational(f)]


def _packet_fixers(workspace: Path) -> dict[str, dict]:
    """Finding id -> the `fixer` record of its escalation packet (revive keeps a refusal or an unapproved diff there)."""
    found: dict[str, dict] = {}
    for path in sorted((workspace / "reports" / "escalations").glob("*.json")):
        packet = _read_json(path)
        fixer = packet.get("fixer")
        if isinstance(fixer, dict) and fixer.get("state"):
            for finding_id in packet.get("merged") or [packet.get("finding")]:
                found.setdefault(finding_id, fixer)
    return found


def _newest_refusal(ledger: list[dict], finding_id: str) -> dict | None:
    entries = [e for e in ledger if e.get("finding") == finding_id]
    if entries and "FIXER_REFUSED" in (entries[-1].get("state"), entries[-1].get("outcome")):
        return entries[-1]
    return None


def explain_workspace(workspace: Path, standing: set[str]) -> list[dict]:
    """One row per open auto-tier finding id: {id, reason, detail, files, count, scan_state}."""
    scan = assess(workspace)
    try:
        found = open_auto_findings(workspace, scan.get("report"))
    except (OSError, ValueError) as exc:
        return [{"id": "(scan report)", "reason": "INCOMPLETE_SCAN", "detail": f"report unreadable: {exc}", "count": 0, "files": [], "scan_state": "INCOMPLETE"}]
    by_id: dict[str, list[dict]] = {}
    for finding in found:
        by_id.setdefault(finding["id"], []).append(finding)
    if not by_id:
        return []
    ledger = read_ledger(workspace)
    revive = _read_json(workspace / "reports" / "revive" / "REVIVE.json")
    approved = standing | set(revive.get("approved") or [])
    packets = _packet_fixers(workspace)
    rows = []
    for finding_id, group in sorted(by_id.items()):
        all_safe = {f.get("classification") for f in group} == {"SAFE"}
        refusal = _newest_refusal(ledger, finding_id)
        fixer = packets.get(finding_id) or {}
        underlying = None
        if not revive and not ledger:
            underlying = ("NEVER_REVIVED", "no reports/revive/REVIVE.json and no escalation ledger")
        elif refusal or fixer.get("state") == "FIXER_REFUSED":
            underlying = ("FIXER_REFUSED", str((refusal or {}).get("reason") or fixer.get("reason") or "no reason recorded"))
        elif fixer.get("state") == "AWAITING_APPROVAL" or (not all_safe and finding_id not in approved):
            underlying = ("NOT_APPROVED", "classifications " + ", ".join(sorted({str(f.get("classification")) for f in group})))
        if scan["state"] == "CURRENT":
            reason, detail = underlying or ("UNEXPLAINED", "tier auto, no refusal, approval not needed or given, scan is current")
        else:
            reason, detail = f"{scan['state']}_SCAN", scan["detail"] + (f"; would otherwise be {underlying[0]}: {underlying[1]}" if underlying else "")
        rows.append({"id": finding_id, "reason": reason, "detail": detail, "count": len(group), "scan_state": scan["state"],
                     "files": sorted({f["file"] for f in group if f.get("file")})[:5]})
    return rows


def discover(queue: Path) -> list[Path]:
    queue = Path(queue).expanduser().resolve()
    if not queue.is_dir():
        raise AutoOpenError(f"{queue} is not a directory.")
    return sorted(p for p in queue.iterdir() if p.is_dir() and not p.name.startswith("_") and (p / "reports").is_dir() and not is_closed(p))


def auto_open(queue: Path, *, policy: Path | None = None, progress=None) -> dict:
    queue = Path(queue).expanduser().resolve()
    policy = Path(policy) if policy else queue / POLICY_NAME
    standing = set(_read_json(policy).get("approved_fixers") or {})
    workspaces = discover(queue)
    mods: dict[str, list[dict]] = {}
    counts: dict[str, Counter] = {}
    for index, workspace in enumerate(workspaces, 1):
        started = time.monotonic()
        rows = explain_workspace(workspace, standing)
        if rows:
            mods[workspace.name] = rows
            for row in rows:
                counts.setdefault(row["id"], Counter())[row["reason"]] += 1
        if progress:
            progress(index, len(workspaces), workspace.name, rows, time.monotonic() - started)
    totals = Counter(row["reason"] for rows in mods.values() for row in rows)
    return {"schema_version": SCHEMA_VERSION, "mode": "AUTO_OPEN", "queue": str(queue), "workspaces": len(workspaces),
            "mods_with_open_auto_findings": len(mods), "totals": {r: totals.get(r, 0) for r in REASONS},
            "by_finding": {fid: {r: c.get(r, 0) for r in REASONS if c.get(r)} for fid, c in sorted(counts.items())},
            "mods": mods}


def render(result: dict) -> str:
    lines = [f"# Open auto-tier findings ({result['mods_with_open_auto_findings']} of {result['workspaces']} workspaces)", "",
             "Totals: " + ", ".join(f"{r} {n}" for r, n in result["totals"].items()), "",
             "| Finding id | " + " | ".join(REASONS) + " |", "|---|" + "---|" * len(REASONS)]
    for finding_id, reasons in sorted(result["by_finding"].items(), key=lambda kv: -sum(kv[1].values())):
        lines.append(f"| `{finding_id}` | " + " | ".join(str(reasons.get(r, "")) for r in REASONS) + " |")
    lines += ["", "## Per mod", ""]
    for name, rows in result["mods"].items():
        lines.append(f"- {name}")
        lines += [f"  - `{row['id']}` x{row['count']}: {row['reason']} ({row['detail']})" for row in rows]
    unexplained = [name for name, rows in result["mods"].items() if any(r["reason"] == "UNEXPLAINED" for r in rows)]
    if unexplained:
        lines += ["", f"UNEXPLAINED is an automation bug: {', '.join(unexplained)}"]
    return "\n".join(lines) + "\n"


def add_parser(subcommands) -> None:
    cmd = subcommands.add_parser("auto-open", help="why each open auto-tier finding stays open: NOT_APPROVED, FIXER_REFUSED, NEVER_REVIVED, STALE_SCAN/UNKNOWN_SCAN/INCOMPLETE_SCAN (scan registry freshness) or UNEXPLAINED (roadmap item 73 A3); read-only")
    cmd.add_argument("queue", type=Path, help="the queue folder (In operation)")
    cmd.add_argument("--policy", type=Path, help="standing fixer approvals (default <queue>/AUTOMATION_POLICY.json)")
    cmd.add_argument("--quiet", action="store_true", help="no per-workspace progress lines on stderr")
    cmd.add_argument("--json", action="store_true")


def run_cli(args: argparse.Namespace) -> int:
    import sys

    def progress(done: int, total: int, name: str, rows: list[dict], seconds: float) -> None:
        report(done, total, name, f"{len(rows)} open auto-tier id(s)", seconds)

    try:
        result = auto_open(args.queue, policy=args.policy, progress=None if args.quiet else progress)
    except (AutoOpenError, OSError) as exc:
        print(f"bridgeforge: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False) if args.json else render(result), end="\n" if args.json else "")
    return 0
