"""One reader for a REVIVAL_REPORT.md's status line (ROADMAP P15 item 31.4).

`probe_group`, `archive` and the pre-push hook each parsed the status their own way, and a bold line
(**READY_FOR_LIVE_TEST**, RogueSynth) or the newer LIVE_VALIDATED each broke one of them (2026-09-28). This is the
workflow's reader: the last line that is exactly one known status, bold or not. `revival_audit`'s strict
single-final-line gate for releases is separate on purpose and unchanged.
"""
from __future__ import annotations

from pathlib import Path

from .revival_audit import COMPLETION_STATUSES

# Statuses the live-testing workflow adds after a report is first declared.
WORKFLOW_STATUSES = ("LIVE_VALIDATED", "SUPERSEDED", "ESCALATED", "NOT_REVIVABLE")
# Closed: no more revival work. Queue commands skip these (superseded mods still ran through every revive, 2026-10-01).
# NOT_REVIVABLE: the mod depends on something RC8 removed with no public replacement (More Combat Terrain Effects).
CLOSED_STATUSES = ("SUPERSEDED", "NOT_REVIVABLE")
REPORT_STATUSES = frozenset((*COMPLETION_STATUSES, *WORKFLOW_STATUSES))


def last_status(text: str) -> str | None:
    found = None
    for line in text.splitlines():
        candidate = line.strip().strip("*").strip()
        if candidate in REPORT_STATUSES:
            found = candidate
    return found


def report_status(report: Path) -> str | None:
    report = Path(report)
    if not report.is_file():
        return None
    return last_status(report.read_text(encoding="utf-8", errors="replace"))


def is_closed(workspace: Path) -> bool:
    return report_status(Path(workspace) / "working" / "reports" / "REVIVAL_REPORT.md") in CLOSED_STATUSES
