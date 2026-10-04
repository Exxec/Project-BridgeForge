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

    def test_rule_accepts_in_baselines_or_approves_the_fixer(self) -> None:
        # ROADMAP P15 31.12: one owner ruling per finding id, recorded, instead of rulings typed into chat.
        from bridgeforge.escalation_queue import rule

        with resolved_temp_dir() as queue:
            _revive(queue, "A", "ESCALATED", ["variant-op-over-budget"])
            (queue / "A" / "working").mkdir()
            (queue / "A" / "reports" / "escalations").mkdir(parents=True)
            (queue / "A" / "reports" / "escalations" / "variant-op-over-budget--1.json").write_text(json.dumps(
                {"findings": [{"id": "variant-op-over-budget", "file": "data/variants/x.variant", "evidence": ["variant:x"]}]}), encoding="utf-8")
            accepted = rule(queue, "variant-op-over-budget", accept=True, reason="authored that way", today="2026-09-28")
            baseline = json.loads((queue / "A" / "working" / "reports" / "baseline.json").read_text(encoding="utf-8"))
            approved = rule(queue, "variant-op-over-budget", approve_fixer=True, reason="trim to fit", today="2026-09-28")
            policy = json.loads((queue / "AUTOMATION_POLICY.json").read_text(encoding="utf-8"))
            log = (queue / "ESCALATION_RULINGS.jsonl").read_text(encoding="utf-8").splitlines()
            with self.assertRaises(ValueError):
                rule(queue, "variant-op-over-budget", accept=True, reason=" ")
        self.assertEqual(accepted["mods"], ["A"])
        self.assertEqual(baseline["findings"], ["variant-op-over-budget|data/variants/x.variant|variant:x"])
        self.assertEqual(policy["approved_fixers"]["variant-op-over-budget"]["reason"], "trim to fit")
        self.assertEqual(len(log), 2)
        self.assertEqual(approved["ruling"], "approve-fixer")

    def test_accept_in_mod_by_finding_and_file_part(self) -> None:
        # ROADMAP 34.12: one mod's findings accepted as authored, with the evidence in ESCALATION_REVIEW.md.
        from bridgeforge.escalation_queue import accept_in_mod

        with resolved_temp_dir() as ws:
            (ws / "working").mkdir()
            (ws / "reports" / "escalations").mkdir(parents=True)
            (ws / "reports" / "escalations" / "hard-coded-campaign-entity-reference--1.json").write_text(json.dumps({"findings": [
                {"id": "hard-coded-campaign-entity-reference", "file": "data/scripts/world/A_Gen.java", "evidence": ["a_star"]},
                {"id": "hard-coded-campaign-entity-reference", "file": "data/scripts/B.java", "evidence": ["corvus"]}]}), encoding="utf-8")
            entry = accept_in_mod(ws, ["hard-coded-campaign-entity-reference:A_Gen"], "A_Gen creates a_star (initStar, line 4)", today="2026-10-04")
            baseline = json.loads((ws / "working" / "reports" / "baseline.json").read_text(encoding="utf-8"))
            review = (ws / "reports" / "ESCALATION_REVIEW.md").read_text(encoding="utf-8")
            with self.assertRaises(ValueError):
                accept_in_mod(ws, ["hard-coded-campaign-entity-reference:Typo"], "x")
            with self.assertRaises(ValueError):
                accept_in_mod(ws, ["hard-coded-campaign-entity-reference"], " ")
        self.assertEqual(entry["keys"], ["hard-coded-campaign-entity-reference|data/scripts/world/A_Gen.java|a_star"])
        self.assertEqual(baseline["findings"], entry["keys"])
        self.assertIn("## 2026-10-04: hard-coded-campaign-entity-reference accepted as authored", review)
        self.assertIn("initStar, line 4", review)

if __name__ == "__main__":
    unittest.main()
