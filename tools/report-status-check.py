"""Pre-push check: every REVIVAL_REPORT.md under the checkout names a known status (96.5 A9).

The pre-push script kept its own copy of the status list, and it lacked NOT_REVIVABLE (95.15's `close --status`). The list is report_status.REPORT_STATUSES now.
As before, a status word anywhere in the report counts; `report_status.last_status`, the workflow's stricter reader, is
not this check's job.
Usage: python tools/report-status-check.py [ROOT]; prints each bad report and exits 1 when there is one.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bridgeforge.report_status import REPORT_STATUSES  # noqa: E402

STATUS_WORD = re.compile(r"\b(" + "|".join(sorted(REPORT_STATUSES, key=len, reverse=True)) + r")\b")


def reports_without_status(root: Path) -> list[Path]:
    bad = []
    for report in sorted(Path(root).rglob("REVIVAL_REPORT.md")):
        try:
            text = report.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not STATUS_WORD.search(text):
            bad.append(report)
    return bad


def main(argv: list[str]) -> int:
    root = Path(argv[0]) if argv else Path.cwd()
    bad = reports_without_status(root)
    for report in bad:
        print(f"Invalid report status: {report}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
