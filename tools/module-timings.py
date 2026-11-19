"""Write tests/module_timings.json, the weights CI's time-balanced shards use (ROADMAP-3 96.5 C2), from timed runs.

Usage: python tools/module-timings.py REPORT [REPORT ...]
Each REPORT is the JSON `tests/run_partitioned.py --timings` writes. A module's weight is the sum of its cases' seconds; with
several reports (machines or runs) the largest sum wins, so a module slow anywhere is not under-weighted. Refresh it when a
shard's time drifts well away from the others.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "module_timings.json"


def module_weights(reports: list[dict]) -> dict[str, float]:
    best: dict[str, float] = {}
    for report in reports:
        sums: dict[str, float] = defaultdict(float)
        for case_id, seconds in report.get("seconds", {}).items():
            sums[case_id.split(".", 1)[0]] += float(seconds)
        for module, total in sums.items():
            best[module] = max(best.get(module, 0.0), total)
    return {module: round(seconds, 2) for module, seconds in sorted(best.items())}


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    reports = [json.loads(Path(path).read_text(encoding="utf-8")) for path in argv]
    weights = module_weights(reports)
    document = {"measured_on": date.today().isoformat(), "reports": len(reports),
                "note": "Seconds per test module from tests/run_partitioned.py --timings; written by tools/module-timings.py.",
                "modules": weights}
    OUT.write_bytes((json.dumps(document, indent=2) + "\n").encode("utf-8"))
    print(f"{len(weights)} modules, {sum(weights.values()):.0f} s in all -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
