"""ROADMAP 70 H1.1/H1.2 ratchet: bare `.write_text(` and `shutil.rmtree(` call sites per module may only shrink.

Before bridgeforge/safeio.py existed there were 182 in-place writes and 15 unguarded tree deletes. New code uses
`atomic_write_text` / `safe_rmtree`; old call sites are converted as they are touched, and `tests/safeio_baseline.json` records what is
left. Regenerate it with `python -m tests.test_safeio_ratchet --write` only after converting sites, never to admit new ones.
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "bridgeforge"
BASELINE = Path(__file__).resolve().parent / "safeio_baseline.json"
PATTERNS = {"write_text": re.compile(r"\.write_text\("), "rmtree": re.compile(r"shutil\.rmtree\(")}
EXEMPT = {"safeio.py"}  # the module that implements the safe versions


def counts() -> dict[str, dict[str, int]]:
    found: dict[str, dict[str, int]] = {}
    for path in sorted(PACKAGE.glob("*.py")):
        if path.name in EXEMPT:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        row = {name: len(pattern.findall(text)) for name, pattern in PATTERNS.items()}
        if any(row.values()):
            found[path.name] = {k: v for k, v in row.items() if v}
    return found


class SafeIoRatchetTests(unittest.TestCase):
    def test_bare_writes_and_tree_deletes_only_shrink(self) -> None:
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))["modules"]
        problems = []
        for module, row in counts().items():
            allowed = baseline.get(module, {})
            for kind, number in row.items():
                if number > allowed.get(kind, 0):
                    problems.append(f"{module}: {number} bare {kind}() call site(s), baseline {allowed.get(kind, 0)}")
        self.assertEqual(problems, [], "use bridgeforge.safeio (atomic_write_text / safe_rmtree) for new code, or convert the site instead of raising the baseline")

    def test_the_baseline_is_not_stale_after_conversions(self) -> None:
        """A converted site must lower the baseline too, or the next bare write hides under the old number."""
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))["modules"]
        current = counts()
        stale = [f"{m}: {k} baseline {n}, now {current.get(m, {}).get(k, 0)}" for m, row in baseline.items() for k, n in row.items()
                 if current.get(m, {}).get(k, 0) < n]
        self.assertEqual(stale, [], "run `python -m tests.test_safeio_ratchet --write` to record the lower counts")


if __name__ == "__main__":
    if "--write" in sys.argv:
        BASELINE.write_text(json.dumps({"schema_version": 1, "modules": counts()}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        total = {k: sum(r.get(k, 0) for r in counts().values()) for k in PATTERNS}
        print("wrote", BASELINE, total)
    else:
        unittest.main()
