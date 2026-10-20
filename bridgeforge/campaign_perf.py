"""Campaign frame time under load (ROADMAP 77.17b; Templar Crusade plan section 4 point 4).

The probe's `CampaignPerfScript` logs one line per in-game day:
    BF-PROBE|<ver>|campaign-perf|INFO|day=N|frames=..,mean_ms=..,p95_ms=..,max_ms=..,gaps=..,fleets_here=..,fleets_busiest=..,busiest=<location id>
(WARN instead of INFO when the day's p95 passed the config's `campaign_perf_p95_ms`, default 0 = off). `campaign_perf_summary` folds them
into the run record's `campaign_perf`. A slow day is information, never a verdict: the threshold only flags it.

Workbench mapping (read-only look, 2026-10-20): the Starsector project workbench's performance report is not edited from here; the
natural fit is its per-session frame-time block: `mean_ms`/`p95_ms`/`max_ms` per day plus `fleets_here`/`fleets_busiest` as the load axis.
"""
from __future__ import annotations

import re
from pathlib import Path

_PERF_LINE = re.compile(r"BF-PROBE\|[^|]*\|campaign-perf\|(?P<status>[^|]*)\|day=(?P<day>\d+)\|(?P<detail>.*)$")


def parse_campaign_perf(log: Path) -> list[dict]:
    """One dict per logged day, in log order: day, status, numeric fields, busiest location."""
    days: list[dict] = []
    for line in Path(log).read_text(encoding="utf-8", errors="replace").splitlines():
        match = _PERF_LINE.search(line)
        if not match:
            continue
        entry: dict = {"day": int(match["day"]), "status": match["status"]}
        for pair in match["detail"].split(","):
            key, _, value = pair.partition("=")
            key = key.strip()
            try:
                entry[key] = float(value) if "." in value else int(value)
            except ValueError:
                entry[key] = value.strip()
        days.append(entry)
    return days


def campaign_perf_summary(log: Path, *, slow_p95_ms: float | None = None) -> dict | None:
    """The run's summary, or None when the log holds no campaign-perf line. `slow_days` lists days whose p95 passed
    `slow_p95_ms` (or that the probe itself flagged WARN)."""
    days = parse_campaign_perf(log)
    if not days:
        return None
    worst = max(days, key=lambda d: d.get("p95_ms", 0))
    busiest = max(days, key=lambda d: d.get("fleets_busiest", 0))
    slow = sorted({d["day"] for d in days if d["status"] == "WARN" or (slow_p95_ms and d.get("p95_ms", 0) > slow_p95_ms)})
    total_frames = sum(int(d.get("frames", 0)) for d in days)
    return {
        "days": len(days),
        "frames": total_frames,
        "mean_ms": round(sum(d.get("mean_ms", 0) * d.get("frames", 0) for d in days) / total_frames, 2) if total_frames else 0.0,
        "worst_p95_ms": worst.get("p95_ms", 0), "worst_p95_day": worst["day"],
        "max_ms": max(d.get("max_ms", 0) for d in days),
        "max_fleets_busiest": busiest.get("fleets_busiest", 0), "busiest_location": busiest.get("busiest", ""),
        "max_fleets_here": max(d.get("fleets_here", 0) for d in days),
        "slow_p95_threshold_ms": slow_p95_ms, "slow_days": slow,
    }
