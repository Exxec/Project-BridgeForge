"""`bridgeforge escalation queue` (2026-09-27): group ESCALATED mods' packets by finding across a queue."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from bridgeforge.escalation_queue import CHECKPOINT_FILE, RESULT_MD, summarize_queue
from tests.support import resolved_temp_dir


def _revive(queue: Path, name: str, status: str, findings: list[str]) -> None:
    folder = queue / name / "reports" / "revive"
    folder.mkdir(parents=True)
    packets = [{"id": f"{f}--mod", "finding": f, "tier": "decision", "kind": "owner"} for f in findings]
    (folder / "REVIVE.json").write_text(json.dumps({"status": status, "packets": packets}), encoding="utf-8")


class EscalationQueueTests(unittest.TestCase):
    def test_counts_mods_blocked_and_only_blockers(self) -> None:
        with resolved_temp_dir() as queue:
            _revive(queue, "A", "ESCALATED", ["variant-op-over-budget"])
            _revive(queue, "B", "ESCALATED", ["variant-op-over-budget", "description-missing"])
            _revive(queue, "C", "UNATTENDED_DONE", [])
            result = summarize_queue(queue, quiet=True)
            markdown = (queue / RESULT_MD).read_text(encoding="utf-8")
            checkpoint_left = (queue / CHECKPOINT_FILE).exists()
        rows = {row["finding"]: row for row in result["findings"]}
        self.assertEqual(result["escalated"], 2)
        self.assertEqual(rows["variant-op-over-budget"]["mods"], ["A", "B"])
        self.assertEqual(rows["variant-op-over-budget"]["only_blocker"], ["A"])
        self.assertEqual(rows["description-missing"]["only_blocker"], [])
        self.assertIn("`variant-op-over-budget`: A", markdown)
        self.assertFalse(checkpoint_left)


if __name__ == "__main__":
    unittest.main()
