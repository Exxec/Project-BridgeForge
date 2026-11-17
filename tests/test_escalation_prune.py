"""`escalation prune` (ROADMAP-3 item 92.36, 2026-11-16): Bultach Coalition's 33 attempt sandboxes were 1.7 GB of 2.1 GB."""
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from bridgeforge.escalation.prune import prune_sandboxes
from tests.support import resolved_temp_dir


def _attempt(ws: Path, packet: str, number: int, *, changed: dict[str, str], same: dict[str, str]) -> Path:
    attempt = ws / "scratch" / "escalations" / packet / f"attempt-{number}"
    working = attempt / "working"
    start = {}
    for rel, text in {**same, **changed}.items():
        path = working / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        original = text if rel in same else "before"
        start[rel] = hashlib.sha256(original.encode()).hexdigest()
        path.write_text(text, encoding="utf-8")
    (attempt / "START_TREE.json").write_text(json.dumps(start), encoding="utf-8")
    (attempt / "NOTE.md").write_text("what I changed", encoding="utf-8")
    return attempt


def _ledger(ws: Path, *entries: dict) -> None:
    path = ws / "reports" / "escalations" / "ledger.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")


class PruneTests(unittest.TestCase):
    def test_finished_attempts_lose_only_the_mod_copy(self) -> None:
        with resolved_temp_dir() as root:
            ws = root / "In operation" / "Mod"
            done = _attempt(ws, "p--1", 1, changed={"src/A.java": "after"}, same={"data/big.csv": "x" * 1000})
            running = _attempt(ws, "p--2", 1, changed={}, same={"data/big.csv": "y"})
            _ledger(ws, {"packet": "p--1", "attempt": 1, "outcome": "APPLIED", "changed": ["src/A.java"]})
            dry = prune_sandboxes(ws)
            still_there = (done / "working").is_dir()
            result = prune_sandboxes(ws, apply=True)
            kept_change = (done / "changed" / "src" / "A.java").read_text(encoding="utf-8")
            note = (done / "NOTE.md").is_file()
            pruned = json.loads((done / "PRUNED.json").read_text(encoding="utf-8"))
            gone = not (done / "working").exists()
            unfinished = (running / "working").is_dir()
        self.assertEqual(dry["attempts"][0]["state"], "WOULD_PRUNE")
        self.assertTrue(still_there)  # a dry run deletes nothing
        self.assertTrue(gone and note and unfinished)
        self.assertEqual(kept_change, "after")
        self.assertEqual(pruned["changed_kept"], ["src/A.java"])
        self.assertGreater(result["bytes_freed"], 1000)
        self.assertEqual([a["state"] for a in result["attempts"]], ["PRUNED", "KEPT"])


if __name__ == "__main__":
    unittest.main()
