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
from bridgeforge.scan.scan_registry import REGISTRY_NAME, STATES

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
            if (candidate / "working" / "mod_info.json").is_file() or _latest_scan(candidate) is not None                     or (candidate / "reports" / REGISTRY_NAME).is_file():
                found.add(candidate)
    return sorted(found)


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


NOT_CURRENT = ("STALE", "UNKNOWN", "INCOMPLETE")


def _scan_and_register(workspace: Path, vanilla_core: Path | None) -> None:
    """Scan `working/` afresh and publish the result in the scan registry (item 75 R2), under a name of our own choosing."""
    import time

    from .report import write_artifacts
    from bridgeforge.scan.scanner import scan_mod

    working = workspace / "working"
    result = scan_mod(working, vanilla_core=vanilla_core, compile_check=vanilla_core is not None)
    stamp = time.strftime("%Y-%m-%d-%H%M%S", time.gmtime())
    write_artifacts(result, workspace / "reports" / f"scan-{stamp}-stats",
                    registry={"vanilla_core": vanilla_core, "compile_check": vanilla_core is not None})


def _fresh_context(vanilla_core: Path | None) -> dict:
    return {"vanilla_core": vanilla_core, "compile_check": vanilla_core is not None, "target": "0.98.x/java17"}


def _assessment(workspace: Path, scan: bool, vanilla_core: Path | None) -> tuple[dict, str | None]:
    """(freshness of the stored scan, key). The key identifies the content a record was computed from, so a checkpointed
    record is reused only for the same content (R2): the registry fingerprint, or for --scan the fingerprint of a fresh scan."""
    from bridgeforge.scan import scan_registry

    if scan:
        fp = scan_registry.fingerprint(workspace / "working", _fresh_context(vanilla_core))
        return {"state": "FRESH_UNREGISTERED", "detail": "scanned now; not published in the registry", "report": None,
                "fingerprint": fp["digest"]}, fp["digest"]
    assessment = scan_registry.assess(workspace)
    return assessment, _key(assessment)


def _key(assessment: dict) -> str | None:
    """The registry fingerprint; for a legacy scan (no fingerprint) the digest of its report, which is all that record depends on."""
    from bridgeforge.scan import scan_registry

    if assessment.get("fingerprint") or not isinstance(assessment.get("report"), Path):
        return assessment.get("fingerprint")
    try:
        return "legacy:" + scan_registry._sha256(assessment["report"])
    except OSError:
        return None


def _read_report(report: Path) -> list[dict]:
    data = json.loads(Path(report).read_text(encoding="utf-8-sig"))
    return list(data.get("findings", data) if isinstance(data, dict) else data)


def _workspace_record(workspace: Path, scan: bool, vanilla_core: Path | None, *, rescan_stale: bool = False,
                      assessment: dict | None = None) -> dict:
    """One workspace's result: a mod row with its finding-id counts, or an `unscanned` reason.
    Freshness (R2) comes from the scan registry: CURRENT, STALE, UNKNOWN or INCOMPLETE; `rescan_stale` scans afresh and
    registers every workspace that is not CURRENT and keeps the stored result of the rest."""
    from dataclasses import asdict

    from bridgeforge.scan import scan_registry
    from bridgeforge.scan.scanner import scan_mod

    working = workspace / "working"
    if assessment is None:
        assessment, _ = _assessment(workspace, scan, vanilla_core)
    rescanned = False
    findings, source = None, ""
    try:
        if scan:
            if not (working / "mod_info.json").is_file():
                return {"workspace": workspace.name, "unscanned": "no working/mod_info.json to scan"}
            result = scan_mod(working, vanilla_core=vanilla_core, compile_check=vanilla_core is not None)
            findings, source = [asdict(f) for f in result.findings], f"scanned {working}"
        else:
            if rescan_stale and assessment["state"] != "CURRENT" and (working / "mod_info.json").is_file():
                _scan_and_register(workspace, vanilla_core)
                rescanned = True
                assessment = scan_registry.assess(workspace)
            if assessment.get("report") is None:
                return {"workspace": workspace.name, "unscanned": assessment["detail"] + " (run `bridgeforge scan`, or pass --scan / --rescan-stale)",
                        "freshness": {"state": assessment["state"], "detail": assessment["detail"]}}
            findings, source = _read_report(assessment["report"]), str(assessment["report"])
    except (ValueError, OSError) as exc:
        return {"workspace": workspace.name, "unscanned": f"scan failed: {exc}",
                "freshness": {"state": "INCOMPLETE", "detail": str(exc)}}
    key = _key(assessment)
    accepted_keys = mod_baseline_keys(working)
    accepted = sum(1 for f in findings if finding_dict_baseline_key(f) in accepted_keys)
    findings = [f for f in findings if finding_dict_baseline_key(f) not in accepted_keys]
    ids = Counter(f.get("id", "?") for f in findings)
    tiers = {finding_id: tier_for(finding_id) for finding_id in ids}
    report = assessment.get("report")
    shown = report.relative_to(workspace).as_posix() if isinstance(report, Path) and workspace in report.parents else (str(report) if report else None)
    return {"workspace": workspace.name, "source": source, "bucket": bucket(list(tiers.values())),
            "projected_bucket": bucket(["auto" if t == "mechanical" else t for t in tiers.values()]),
            "blocking": sorted(i for i, t in tiers.items() if t not in ("none", "auto")),
            "accepted_by_baseline": accepted, "tiers": dict(Counter(tiers[i] for i in ids.elements())),
            "ids": dict(ids),
            "freshness": {"state": assessment["state"], "detail": assessment["detail"], "report": shown, "key": key,
                          "filter_digest": scan_registry.filter_digest(working), "rescanned": rescanned,
                          "report_mtime": assessment.get("report_mtime")}}


def _reusable(record: dict, workspace: Path, scan: bool, vanilla_core: Path | None) -> tuple[bool, dict | None]:
    """A checkpointed record is reused only when the workspace's content and baseline filter are the ones it was computed from."""
    from bridgeforge.scan import scan_registry

    freshness = record.get("freshness") or {}
    assessment, key = _assessment(workspace, scan, vanilla_core)
    same = bool(key) and freshness.get("key") == key and freshness.get("filter_digest") == scan_registry.filter_digest(workspace / "working")
    return same or ("unscanned" in record and not key and assessment["state"] == "NONE"), assessment


def _checkpoint_header(roots: list[Path], scan: bool, vanilla_core: Path | None, rescan_stale: bool = False) -> dict:
    from bridgeforge.scan.scan_registry import EXCLUSION_VERSION, SCHEMA_VERSION as REGISTRY_SCHEMA

    return {"checkpoint": SCHEMA_VERSION, "roots": [str(Path(r).expanduser().resolve()) for r in roots],
            "scan": scan, "vanilla_core": str(vanilla_core) if vanilla_core else None, "rescan_stale": rescan_stale,
            "registry": [REGISTRY_SCHEMA, EXCLUSION_VERSION]}


def finding_stats(roots: list[Path], *, scan: bool = False, vanilla_core: Path | None = None,
                  checkpoint: Path | None = None, progress=None, rescan_stale: bool = False) -> dict:
    """`checkpoint`: a JSONL file each workspace's record is appended to as it finishes, so an
    interrupted run resumes where it stopped (same roots and options only). `progress(done, total,
    record, seconds, resumed)` is called after each workspace."""
    import time

    workspaces = discover_workspaces(roots)
    mods, unscanned, stale_rows = [], [], []
    freshness_counts: Counter[str] = Counter()
    occurrences: Counter[str] = Counter()
    mods_with: dict[str, set[str]] = defaultdict(set)
    ai_verified: dict[str, list[str]] = defaultdict(list)
    with Checkpoint(checkpoint, _checkpoint_header(roots, scan, vanilla_core, rescan_stale)) as saved:
        for index, workspace in enumerate(workspaces, 1):
            for entry in read_ledger(workspace):
                if entry.get("outcome") in VERIFIED_OUTCOMES and entry.get("runner") == "agent" and entry.get("finding"):
                    ai_verified[entry["finding"]].append(workspace.name)
            started = time.monotonic()
            record = saved.get(workspace.name)
            assessment = None
            if record is not None:
                reusable, assessment = _reusable(record, workspace, scan, vanilla_core)
                record = record if reusable else None
            resumed = record is not None
            if record is None:
                record = _workspace_record(workspace, scan, vanilla_core, rescan_stale=rescan_stale, assessment=assessment)
                saved.add(workspace.name, record)
            if progress:
                progress(index, len(workspaces), record, time.monotonic() - started, resumed)
            freshness = record.get("freshness") or {"state": "NONE", "detail": "no stored scan"}
            freshness_counts[freshness["state"]] += 1
            if freshness["state"] in NOT_CURRENT:
                stale_rows.append({"workspace": record["workspace"], **freshness})
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
        "schema_version": SCHEMA_VERSION, "mode": "FINDING_STATS", "source": "fresh scan" if scan else ("registered scans, non-current ones rescanned" if rescan_stale else "latest registered scan"),
        "freshness": {state: freshness_counts.get(state, 0) for state in (*STATES, "FRESH_UNREGISTERED", "NONE")},
        "not_current": stale_rows,
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
    fresh = stats.get("freshness") or {}
    lines += ["", "## Scan freshness", "", ", ".join(f"{state} {n}" for state, n in fresh.items() if n) or "no scans",
              "", "CURRENT = the registered scan read these exact inputs, dependencies, options and checks. Anything else is a count to "
              "re-measure (`--rescan-stale`), not a result to trust."]
    if stats.get("not_current"):
        lines += ["", f"### Not current ({len(stats['not_current'])})", "", "| Mod | State | Why | Report | Rescanned |", "|---|---|---|---|---|"]
        lines += [f"| {r['workspace']} | {r['state']} | {r['detail']} | `{r.get('report') or '-'}` | {'yes' if r.get('rescanned') else 'no'} |" for r in stats["not_current"]]
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
