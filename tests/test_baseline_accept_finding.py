"""ROADMAP 77.14: accept named findings into a workspace baseline, outside escalation packets."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from bridgeforge.baseline import load_baseline_keys
from bridgeforge.baseline_accept_finding import accept_selected, select_findings
from bridgeforge.models import Finding
from tests.support import resolved_temp_dir

REASON = "authored that way; the preset override is intentional content"
TODAY = "2026-10-20"


def _finding(finding_id: str, file: str, evidence: str) -> Finding:
    return Finding(id=finding_id, category="c", severity="low", classification="REVIEW", confidence="high",
                   explanation="e", file=file, evidence=[evidence])


FINDINGS = [
    _finding("preset-override", "data/presets/alpha.json", "override: hullId=alpha"),
    _finding("preset-override", "data/presets/beta.json", "override: hullId=beta"),
    _finding("preset-override", "data/presets/beta.json", "override: hullId=beta-2"),
    _finding("hardcoded-id", "data/presets/alpha.json", "string literal alpha"),
]


def _workspace(root: Path, baseline: dict | None = None) -> Path:
    working = root / "ws" / "working"
    (working / "reports").mkdir(parents=True)
    (working / "mod_info.json").write_text(json.dumps({"id": "ws", "version": "1.0"}), encoding="utf-8")
    if baseline is not None:
        (working / "reports" / "baseline.json").write_text(json.dumps(baseline), encoding="utf-8")
    return root / "ws"


class SelectFindingsTests(unittest.TestCase):
    def test_file_and_evidence_parts_narrow_the_match(self) -> None:
        matches = select_findings(FINDINGS, ["preset-override", "preset-override:beta", "preset-override:beta:beta-2"])
        self.assertEqual(len(matches["preset-override"]), 3)
        self.assertEqual(len(matches["preset-override:beta"]), 2)
        self.assertEqual(len(matches["preset-override:beta:beta-2"]), 1)
        self.assertIn("beta-2", matches["preset-override:beta:beta-2"][0])


class AcceptSelectedTests(unittest.TestCase):
    def test_accepts_exactly_the_selected_keys_and_keeps_the_stamp(self) -> None:
        stamp = {"version": "1.0", "date": "2026-10-01"}
        with resolved_temp_dir() as root:
            ws = _workspace(root, {"findings": ["old|x|y"], "stamp": stamp})
            result = accept_selected(ws, ["preset-override:alpha"], REASON, FINDINGS, today=TODAY)
            path = ws / "working" / "reports" / "baseline.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(result["added"], ["preset-override|data/presets/alpha.json|override: hullId=alpha"])
        self.assertEqual(payload["findings"], sorted(["old|x|y", result["added"][0]]))
        self.assertEqual(payload["stamp"], stamp)
        self.assertEqual(payload["reasons"][result["added"][0]], REASON)

    def test_no_match_is_refused_and_nothing_is_written(self) -> None:
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            with self.assertRaisesRegex(ValueError, "no finding matches: preset-override:gamma"):
                accept_selected(ws, ["preset-override:alpha", "preset-override:gamma"], REASON, FINDINGS, today=TODAY)
            self.assertFalse((ws / "working" / "reports" / "baseline.json").exists())
            self.assertFalse((ws / "reports" / "ESCALATION_REVIEW.md").exists())

    def test_short_reason_is_refused(self) -> None:
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            with self.assertRaisesRegex(ValueError, "at least 20 characters"):
                accept_selected(ws, ["hardcoded-id"], "too short reason", FINDINGS, today=TODAY)
            with self.assertRaises(ValueError):
                accept_selected(ws, ["hardcoded-id"], "   ", FINDINGS, today=TODAY)

    def test_rerun_is_idempotent_and_says_nothing_is_new(self) -> None:
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            first = accept_selected(ws, ["preset-override:beta"], REASON, FINDINGS, today=TODAY)
            review = (ws / "reports" / "ESCALATION_REVIEW.md").read_text(encoding="utf-8")
            path = ws / "working" / "reports" / "baseline.json"
            before = path.read_text(encoding="utf-8")
            second = accept_selected(ws, ["preset-override:beta"], REASON, FINDINGS, today="2026-10-21")
            after = path.read_text(encoding="utf-8")
            review_after = (ws / "reports" / "ESCALATION_REVIEW.md").read_text(encoding="utf-8")
        self.assertEqual(len(first["added"]), 2)
        self.assertEqual(second["added"], [])
        self.assertEqual(sorted(second["already_accepted"]), sorted(first["added"]))
        self.assertEqual(before, after)
        self.assertEqual(review, review_after)

    def test_review_file_is_appended_with_reason_and_keys(self) -> None:
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            review_path = ws / "reports" / "ESCALATION_REVIEW.md"
            review_path.parent.mkdir(parents=True)
            review_path.write_text("# Escalation review\n\n## earlier entry\n", encoding="utf-8")
            result = accept_selected(ws, ["hardcoded-id"], REASON, FINDINGS, today=TODAY)
            text = review_path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# Escalation review\n\n## earlier entry"))
        self.assertIn(f"## {TODAY}: hardcoded-id accepted by selector", text)
        self.assertIn(REASON, text)
        self.assertIn(f"- `{result['added'][0]}`", text)

    def test_new_baseline_is_created_when_none_exists(self) -> None:
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            accept_selected(ws, ["hardcoded-id"], REASON, FINDINGS, today=TODAY)
            keys = load_baseline_keys(ws / "working" / "reports" / "baseline.json")
        self.assertEqual(keys, {"hardcoded-id|data/presets/alpha.json|string literal alpha"})


if __name__ == "__main__":
    unittest.main()
