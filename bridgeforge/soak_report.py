"""`bridgeforge soak-report`: judge a long-run (soak) campaign session from its log (ROADMAP item 5 of the 2026-10-06 ideas).

Several failures show up only after many in-game days: a station relocating (Exigency's Avesta needed about 60 days),
raids, economy ticks, fleet managers. The probe (0.2.17) logs a `campaign-day` heartbeat each time its checks run; this
reads the log, takes the largest day count, and combines it with `log-triage`: FATAL and MOD-ERROR events, the probe's
FAIL lines and the caught exceptions (errors the game logged and survived).

Verdicts:
- `INCOMPLETE`: the run covered fewer campaign days than asked for (or the probe never reported a day).
- `ATTENTION`: it covered enough days but something needs a look (a FATAL, a MOD-ERROR, a probe FAIL, a caught exception).
- `PASS`: enough days, none of those.

A PASS is evidence that nothing logged went wrong over those days, not proof the mod behaves: unlogged behaviour
(for example whether a raid ever happened) is not covered, so read the probe's tracked entities as well.
Read-only on the log.
"""
from __future__ import annotations

import re
from pathlib import Path

from .log_triage import triage_log

_DAY_RE = re.compile(r"BF-PROBE\|[^|]*\|campaign-day\|INFO\|clock\|daysSinceStart=(?P<days>-?\d+(?:\.\d+)?)")


def soak_report(log_path: Path | str, days: float, mods_dir: Path | None = None) -> dict[str, object]:
    path = Path(log_path).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"{path} is not an existing log file.")
    if days <= 0:
        raise ValueError("--days must be positive.")
    covered = 0.0
    heartbeats = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = _DAY_RE.search(line)
        if match is not None:
            heartbeats += 1
            covered = max(covered, float(match.group("days")))
    triage = triage_log(path, mods_dir=mods_dir)
    probe_fail = triage["probe"]["counts_by_status"].get("FAIL", 0)
    caught = triage["caught_exceptions"]
    findings: list[str] = []
    if triage["counts"]["FATAL"]:
        findings.append(f"{triage['counts']['FATAL']} FATAL event(s)")
    if triage["counts"]["MOD-ERROR"]:
        findings.append(f"{triage['counts']['MOD-ERROR']} MOD-ERROR event(s)")
    if probe_fail:
        findings.append(f"{probe_fail} probe FAIL line(s)")
    if caught["distinct"]:
        findings.append(f"{caught['total_events']} caught exception(s), {caught['distinct']} distinct")
    if heartbeats == 0:
        verdict = "INCOMPLETE"
        reason = "the probe logged no campaign-day heartbeat (probe older than 0.2.17, or no campaign ran)"
    elif covered < days:
        verdict = "INCOMPLETE"
        reason = f"covered {covered:g} campaign days of the {days:g} asked for"
    elif findings:
        verdict = "ATTENTION"
        reason = "; ".join(findings)
    else:
        verdict = "PASS"
        reason = f"{covered:g} campaign days, no FATAL, MOD-ERROR, probe FAIL or caught exception"
    return {
        "schema_version": 1,
        "mode": "READ_ONLY_SOAK_REPORT",
        "log": str(path),
        "requested_days": days,
        "campaign_days_covered": covered,
        "heartbeats": heartbeats,
        "verdict": verdict,
        "reason": reason,
        "findings": findings,
        "triage_counts": triage["counts"],
        "caught_exceptions": caught,
        "caveat": "Only what the game logged is judged; behaviour that never logs (for example whether a raid happened) is not covered.",
    }
