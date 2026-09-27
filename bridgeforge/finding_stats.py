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
Read-only.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from .automation import ACTIONABLE, TIER_ORDER, bucket, tier_descriptions, tier_for

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


def finding_stats(roots: list[Path], *, scan: bool = False, vanilla_core: Path | None = None) -> dict:
    workspaces = discover_workspaces(roots)
    mods, unscanned = [], []
    occurrences: Counter[str] = Counter()
    mods_with: dict[str, set[str]] = defaultdict(set)
    ai_verified: dict[str, list[str]] = defaultdict(list)
    for workspace in workspaces:
        for entry in read_ledger(workspace):
            if entry.get("outcome") in VERIFIED_OUTCOMES and entry.get("runner") == "agent" and entry.get("finding"):
                ai_verified[entry["finding"]].append(workspace.name)
        findings, source = _findings(workspace, scan, vanilla_core)
        if findings is None:
            unscanned.append({"workspace": workspace.name, "reason": source})
            continue
        ids = Counter(f.get("id", "?") for f in findings)
        for finding_id, count in ids.items():
            occurrences[finding_id] += count
            mods_with[finding_id].add(workspace.name)
        tiers = {finding_id: tier_for(finding_id) for finding_id in ids}
        blocking = sorted(i for i, t in tiers.items() if t not in ("none", "auto"))
        mods.append({"workspace": workspace.name, "source": source, "bucket": bucket(list(tiers.values())),
                     "projected_bucket": bucket(["auto" if t == "mechanical" else t for t in tiers.values()]),
                     "blocking": blocking, "tiers": dict(Counter(tiers[i] for i in ids.elements()))})
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
