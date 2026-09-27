"""`bridgeforge finding-stats`: how much of a queue could be revived unattended, and what to automate next.

ROADMAP P15 item 1 (2026-09-26). Reads each workspace's latest stored scan (`<ws>/reports/scan-*/
bridgeforge.compat.json`, newest by mtime, as `board` does) or, with `--scan`, scans `<ws>/working`
afresh. Every finding gets its tier from `automation_tiers.json`; a mod's bucket is its hardest tier.

It answers three questions with counts, not guesses:
- How many mods need nothing but fixers (`auto`) today, and how many would if every `mechanical`
  finding had a fixer?
- Which single finding id, if automated, would make the most mods fully automatic (`unlocks`)?
- Which ids has AI already fixed and BridgeForge verified several times (from each workspace's
  `reports/escalations/ledger.jsonl`)? Those are the next fixers to write, so the AI stops seeing them.
Findings a mod's own baseline accepts (`working/reports/baseline*.json`, from `scan
--write-baseline`) are left out and counted as `accepted_by_baseline`, as `corpus-recheck` does.
Read-only.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from .automation import ACTIONABLE, TIER_ORDER, bucket, tier_descriptions, tier_for
from .baseline import finding_dict_baseline_key, mod_baseline_keys
from .progress import Checkpoint

SCHEMA_VERSION = 1
PROMOTE_AFTER = 3  # verified AI fixes of one finding id, across at least two mods
VERIFIED_OUTCOMES = {"VERIFIED", "APPLIED"}


class FindingStatsError(ValueError):
    """Raised for a missing root."""


def _latest_scan(workspace: Path) -> Path | None:
    scans = sorted((workspace / "reports").glob("scan-*/bridgeforge.compat.json"), key=lambda p: (p.stat().st_mtime, str(p)))
    return scans[-1] if scans else None


def discover_workspaces(roots: list[Path]) -> list[Path]:
    """A workspace is a folder with a `working/mod_info.json` or a stored scan under `reports/`."""
    found: set[Path] = set()
    for root in roots:
        root = Path(root).expanduser().resolve()
        if not root.is_dir():
            raise FindingStatsError(f"{root} is not a directory.")
        for candidate in [root, *sorted(p for p in root.iterdir() if p.is_dir())]:
            if (candidate / "working" / "mod_info.json").is_file() or _latest_scan(candidate) is not None:
                found.add(candidate)
    return sorted(found)


def _findings(workspace: Path, scan: bool, vanilla_core: Path | None) -> tuple[list[dict] | None, str]:
    if scan:
        from dataclasses import asdict

        from .scanner import scan_mod

        working = workspace / "working"
        if not (working / "mod_info.json").is_file():
            return None, "no working/mod_info.json to scan"
        result = scan_mod(working, vanilla_core=vanilla_core, compile_check=vanilla_core is not None)
        return [asdict(f) for f in result.findings], f"scanned {working}"
    latest = _latest_scan(workspace)
    if latest is None:
        return None, "no stored scan (run `bridgeforge scan`, or pass --scan)"
    data = json.loads(latest.read_text(encoding="utf-8-sig"))
    return list(data.get("findings", data) if isinstance(data, dict) else data), str(latest)


def read_ledger(workspace: Path) -> list[dict]:
    ledger = workspace / "reports" / "escalations" / "ledger.jsonl"
    if not ledger.is_file():
        return []
    entries = []
    for line in ledger.read_text(encoding="utf-8").splitlines():
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


CHECKPOINT_NAME = "FINDING_STATS.partial.jsonl"


def _workspace_record(workspace: Path, scan: bool, vanilla_core: Path | None) -> dict:
    """One workspace's result: a mod row with its finding-id counts, or an `unscanned` reason."""
    findings, source = _findings(workspace, scan, vanilla_core)
    if findings is None:
        return {"workspace": workspace.name, "unscanned": source}
    accepted_keys = mod_baseline_keys(workspace / "working")
    accepted = sum(1 for f in findings if finding_dict_baseline_key(f) in accepted_keys)
    findings = [f for f in findings if finding_dict_baseline_key(f) not in accepted_keys]
    ids = Counter(f.get("id", "?") for f in findings)
    tiers = {finding_id: tier_for(finding_id) for finding_id in ids}
    return {"workspace": workspace.name, "source": source, "bucket": bucket(list(tiers.values())),
            "projected_bucket": bucket(["auto" if t == "mechanical" else t for t in tiers.values()]),
            "blocking": sorted(i for i, t in tiers.items() if t not in ("none", "auto")),
            "accepted_by_baseline": accepted, "tiers": dict(Counter(tiers[i] for i in ids.elements())),
            "ids": dict(ids)}


def _checkpoint_header(roots: list[Path], scan: bool, vanilla_core: Path | None) -> dict:
    return {"checkpoint": SCHEMA_VERSION, "roots": [str(Path(r).expanduser().resolve()) for r in roots],
            "scan": scan, "vanilla_core": str(vanilla_core) if vanilla_core else None}


def finding_stats(roots: list[Path], *, scan: bool = False, vanilla_core: Path | None = None,
                  checkpoint: Path | None = None, progress=None) -> dict:
    """`checkpoint`: a JSONL file each workspace's record is appended to as it finishes, so an
    interrupted run resumes where it stopped (same roots and options only). `progress(done, total,
    record, seconds, resumed)` is called after each workspace."""
    import time

    workspaces = discover_workspaces(roots)
    mods, unscanned = [], []
    occurrences: Counter[str] = Counter()
    mods_with: dict[str, set[str]] = defaultdict(set)
    ai_verified: dict[str, list[str]] = defaultdict(list)
    with Checkpoint(checkpoint, _checkpoint_header(roots, scan, vanilla_core)) as saved:
        for index, workspace in enumerate(workspaces, 1):
            for entry in read_ledger(workspace):
                if entry.get("outcome") in VERIFIED_OUTCOMES and entry.get("runner") == "agent" and entry.get("finding"):
                    ai_verified[entry["finding"]].append(workspace.name)
            started = time.monotonic()
            record = saved.get(workspace.name)
            resumed = record is not None
            if record is None:
                record = _workspace_record(workspace, scan, vanilla_core)
                saved.add(workspace.name, record)
            if progress:
                progress(index, len(workspaces), record, time.monotonic() - started, resumed)
            if "unscanned" in record:
                unscanned.append({"workspace": record["workspace"], "reason": record["unscanned"]})
                continue
            for finding_id, count in record.pop("ids").items():
                occurrences[finding_id] += count
                mods_with[finding_id].add(workspace.name)
            mods.append(record)
    unlocks = Counter(mod["blocking"][0] for mod in mods if len(mod["blocking"]) == 1)
    by_id = [{"id": finding_id, "tier": tier_for(finding_id), "occurrences": occurrences[finding_id],
              "mods": len(mods_with[finding_id]), "unlocks": unlocks.get(finding_id, 0)}
             for finding_id in occurrences if tier_for(finding_id) in ACTIONABLE]
    by_id.sort(key=lambda row: (-row["unlocks"], -row["mods"], row["id"]))
    buckets = Counter(mod["bucket"] for mod in mods)
    projected = Counter(mod["projected_bucket"] for mod in mods)
    promote = [{"id": finding_id, "verified_fixes": len(names), "mods": sorted(set(names)), "tier": tier_for(finding_id)}
               for finding_id, names in ai_verified.items() if len(names) >= PROMOTE_AFTER and len(set(names)) >= 2]
    promote.sort(key=lambda row: (-row["verified_fixes"], row["id"]))
    return {
        "schema_version": SCHEMA_VERSION, "mode": "FINDING_STATS", "source": "fresh scan" if scan else "latest stored scan",
        "workspaces": len(workspaces), "scanned": len(mods), "unscanned": unscanned,
        "buckets": {tier: buckets.get(tier, 0) for tier in TIER_ORDER},
        "projected_buckets": {tier: projected.get(tier, 0) for tier in TIER_ORDER},
        "unattended_now": buckets.get("none", 0) + buckets.get("auto", 0),
        "unattended_with_mechanical_fixers": projected.get("none", 0) + projected.get("auto", 0),
        "by_finding": by_id, "unclassified_ids": sorted(i for i in occurrences if tier_for(i) == "unclassified"),
        "promote_to_fixer": promote, "mods": mods,
        "note": "A mod's bucket is its hardest tier. 'unlocks' counts mods for which this is the only finding id standing between them and an unattended revival. Unattended means up to the live test, which stays manual.",
    }


def render(stats: dict) -> str:
    scanned = stats["scanned"] or 1
    lines = [f"# Finding stats ({stats['scanned']} of {stats['workspaces']} workspaces, {stats['source']})", "",
             f"Unattended now (fixers only): {stats['unattended_now']} ({100 * stats['unattended_now'] // scanned}%)",
             f"Unattended if every `mechanical` finding had a fixer: {stats['unattended_with_mechanical_fixers']} "
             f"({100 * stats['unattended_with_mechanical_fixers'] // scanned}%)", "",
             "| Hardest tier | Mods now | Mods with mechanical fixers | Meaning |", "|---|---|---|---|"]
    meanings = tier_descriptions()
    for tier in TIER_ORDER:
        if stats["buckets"][tier] or stats["projected_buckets"][tier]:
            lines.append(f"| {tier} | {stats['buckets'][tier]} | {stats['projected_buckets'][tier]} | {meanings.get(tier, 'not in automation_tiers.json yet')} |")
    lines += ["", "## What to automate next", "", "| Finding id | Tier | Unlocks | Mods | Occurrences |", "|---|---|---|---|---|"]
    lines += [f"| `{row['id']}` | {row['tier']} | {row['unlocks']} | {row['mods']} | {row['occurrences']} |" for row in stats["by_finding"][:40]]
    if stats["promote_to_fixer"]:
        lines += ["", f"## AI-verified {PROMOTE_AFTER}+ times: write a fixer", ""]
        lines += [f"- `{row['id']}` ({row['tier']}): {row['verified_fixes']} verified fixes in {', '.join(row['mods'])}" for row in stats["promote_to_fixer"]]
    if stats["unclassified_ids"]:
        lines += ["", "## Not in automation_tiers.json", "", ", ".join(f"`{i}`" for i in stats["unclassified_ids"])]
    if stats["unscanned"]:
        lines += ["", f"## Not counted ({len(stats['unscanned'])})", ""]
        lines += [f"- {row['workspace']}: {row['reason']}" for row in stats["unscanned"]]
    return "\n".join(lines) + "\n"


def delta(previous: dict, current: dict) -> dict:
    """What moved between two runs (P15 item 20.3): unattended counts, mods whose bucket changed, and finding
    ids whose occurrence count changed, so the effect of a new fixer or check fix is measured, not recomputed."""
    before = {m["workspace"]: m["bucket"] for m in previous.get("mods", [])}
    after = {m["workspace"]: m["bucket"] for m in current.get("mods", [])}
    moved = sorted((name, before[name], after[name]) for name in before.keys() & after.keys() if before[name] != after[name])
    old_ids = {r["id"]: r["occurrences"] for r in previous.get("by_finding", [])}
    new_ids = {r["id"]: r["occurrences"] for r in current.get("by_finding", [])}
    changed = sorted(((i, old_ids.get(i, 0), new_ids.get(i, 0)) for i in old_ids.keys() | new_ids.keys()
                      if old_ids.get(i, 0) != new_ids.get(i, 0)), key=lambda row: -abs(row[2] - row[1]))
    return {"unattended": (previous.get("unattended_now"), current.get("unattended_now")),
            "moved": [{"workspace": n, "from": a, "to": b} for n, a, b in moved],
            "added": sorted(after.keys() - before.keys()), "removed": sorted(before.keys() - after.keys()),
            "finding_changes": [{"id": i, "from": a, "to": b} for i, a, b in changed]}


def render_delta(change: dict) -> str:
    was, now = change["unattended"]
    lines = ["", "## Since the last run", "", f"Unattended now: {was} -> {now}", ""]
    if change["moved"]:
        lines += ["| Mod | From | To |", "|---|---|---|"] + [f"| {m['workspace']} | {m['from']} | {m['to']} |" for m in change["moved"][:60]]
        lines.append("")
    if change["added"] or change["removed"]:
        lines.append(f"New workspaces: {', '.join(change['added']) or 'none'}; gone: {', '.join(change['removed']) or 'none'}")
        lines.append("")
    if change["finding_changes"]:
        lines += ["| Finding id | Occurrences before | After |", "|---|---|---|"] + [
            f"| `{c['id']}` | {c['from']} | {c['to']} |" for c in change["finding_changes"][:25]]
    return "\n".join(lines) + "\n"
