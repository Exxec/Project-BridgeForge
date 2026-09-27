from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from bridgeforge.automation import TIER_ORDER, bucket, tier_for, tiered_ids
from bridgeforge.checks_index import gather
from bridgeforge.cli import main
from bridgeforge.finding_stats import FindingStatsError, finding_stats, render
from bridgeforge.fixers import SUPPORTED_FINDINGS
from tests.support import resolved_temp_dir


def _workspace(queue: Path, name: str, finding_ids: list[str], *, scan_name: str = "scan-1") -> Path:
    workspace = queue / name
    (workspace / "working").mkdir(parents=True)
    (workspace / "working" / "mod_info.json").write_text('{"id": "%s"}' % name.lower(), encoding="utf-8")
    scan = workspace / "reports" / scan_name
    scan.mkdir(parents=True)
    findings = [{"id": finding_id, "classification": "REVIEW", "file": "data/x"} for finding_id in finding_ids]
    (scan / "bridgeforge.compat.json").write_text(json.dumps({"findings": findings}), encoding="utf-8")
    return workspace


def _ledger(workspace: Path, *entries: dict) -> None:
    ledger = workspace / "reports" / "escalations" / "ledger.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text("".join(json.dumps(entry) + "\n" for entry in entries) + "not json\n", encoding="utf-8")


class TierTableTests(unittest.TestCase):
    def test_every_scan_finding_id_has_a_tier(self):
        # A new check must be placed in automation_tiers.json, or finding-stats would call it unclassified.
        missing = sorted(set(gather().checks) - tiered_ids())
        self.assertEqual(missing, [], "add these ids to bridgeforge/automation_tiers.json")

    def test_tiers_and_patterns(self):
        self.assertEqual(tier_for("json-hash-comment"), "none")
        self.assertEqual(tier_for("bundled-lazylib"), "decision")          # bundled-{...}
        self.assertEqual(tier_for("lazylib-drawable-string-draw"), "code")  # lazylib-drawable-string-{...}
        self.assertEqual(tier_for("never-heard-of-it"), "unclassified")
        self.assertEqual(bucket(["auto", "code", "none"]), "code")
        self.assertEqual(bucket([]), "none")

    def test_auto_tier_names_real_fixers(self):
        table = json.loads(Path("bridgeforge/automation_tiers.json").read_text(encoding="utf-8"))["findings"]
        for finding_id, tier in table.items():
            if tier == "auto":
                self.assertIn(finding_id, SUPPORTED_FINDINGS, f"{finding_id} is '{tier}' but has no fixer")


class FindingStatsTests(unittest.TestCase):
    def _queue(self, root: Path) -> Path:
        queue = root / "In operation"
        _workspace(queue, "DataOnly", ["json-hash-comment", "mod-info-game-version-inexact"])        # auto
        _workspace(queue, "Almost", ["removed-api-call", "black-hole-type-missing-flag"])            # mechanical
        _workspace(queue, "OneDecision", ["content-reference-unresolved", "json-hash-comment"])      # decision
        java = _workspace(queue, "Java", ["loose-script-compile-error", "legacy-vanilla-class-import"])  # code
        _workspace(queue, "Odd", ["brand-new-check"])
        (queue / "Unscanned" / "working").mkdir(parents=True)
        (queue / "Unscanned" / "working" / "mod_info.json").write_text("{}", encoding="utf-8")
        (queue / "notes").mkdir()
        _ledger(java, *[{"finding": "loose-script-compile-error", "outcome": "APPLIED", "runner": "agent"}] * 2,
                {"finding": "loose-script-compile-error", "outcome": "FAILED", "runner": "agent"})
        _ledger(queue / "Almost", {"finding": "loose-script-compile-error", "outcome": "VERIFIED", "runner": "agent"},
                {"finding": "removed-api-call", "outcome": "APPLIED", "runner": "fixer"})
        return queue

    def test_buckets_unlocks_and_promotion(self):
        with resolved_temp_dir() as root:
            stats = finding_stats([self._queue(root)])
        buckets = {mod["workspace"]: (mod["bucket"], mod["projected_bucket"]) for mod in stats["mods"]}
        self.assertEqual(buckets, {"DataOnly": ("auto", "auto"), "Almost": ("mechanical", "auto"), "OneDecision": ("decision", "decision"),
                                   "Java": ("code", "code"), "Odd": ("unclassified", "unclassified")})
        self.assertEqual((stats["unattended_now"], stats["unattended_with_mechanical_fixers"]), (1, 2))
        self.assertEqual(stats["unscanned"][0]["workspace"], "Unscanned")
        self.assertEqual(stats["unclassified_ids"], ["brand-new-check"])
        unlocks = {row["id"]: row["unlocks"] for row in stats["by_finding"]}
        self.assertEqual(unlocks["black-hole-type-missing-flag"], 1)   # the only thing between Almost and unattended
        self.assertEqual(unlocks["content-reference-unresolved"], 1)
        self.assertEqual(unlocks["loose-script-compile-error"], 0)     # Java has two blockers
        self.assertNotIn("json-hash-comment", unlocks)                  # tier none is not listed
        self.assertEqual(stats["promote_to_fixer"], [{"id": "loose-script-compile-error", "verified_fixes": 3, "mods": ["Almost", "Java"], "tier": "code"}])
        text = render(stats)
        self.assertIn("Unattended now (fixers only): 1 (20%)", text)
        self.assertIn("Unattended if every `mechanical` finding had a fixer: 2 (40%)", text)
        self.assertIn("`loose-script-compile-error` (code): 3 verified fixes in Almost, Java", text)
        self.assertIn("- Unscanned: no stored scan", text)

    def test_latest_scan_wins_and_fresh_scan(self):
        import os

        with resolved_temp_dir() as root:
            queue = root / "q"
            workspace = _workspace(queue, "Mod", ["loose-script-compile-error"], scan_name="scan-old")
            newer = _workspace(root / "tmp", "Mod", ["json-hash-comment"], scan_name="scan-new")
            (newer / "reports" / "scan-new").rename(workspace / "reports" / "scan-new")
            os.utime(workspace / "reports" / "scan-old" / "bridgeforge.compat.json", (1, 1))
            stored = finding_stats([workspace])  # a single workspace as the root
            fresh = finding_stats([queue], scan=True)
        self.assertEqual(stored["mods"][0]["bucket"], "none")
        self.assertTrue(fresh["mods"][0]["source"].startswith("scanned "))

    def test_cli(self):
        with resolved_temp_dir() as root:
            queue = self._queue(root)
            out = io.StringIO()
            with redirect_stdout(out), redirect_stderr(io.StringIO()):
                self.assertEqual(main(["finding-stats", str(queue), "--write", str(root / "out")]), 0)
                self.assertEqual(main(["finding-stats", str(queue), "--json"]), 0)
                self.assertEqual(main(["finding-stats", str(root / "missing")]), 2)
            written = (root / "out" / "FINDING_STATS.md").read_text(encoding="utf-8")
        self.assertIn("# Finding stats (5 of 6 workspaces, latest stored scan)", out.getvalue())
        self.assertIn("## What to automate next", written)
        with self.assertRaises(FindingStatsError):
            finding_stats([Path("definitely/not/here")])
        self.assertEqual(TIER_ORDER[0], "none")


if __name__ == "__main__":
    unittest.main()
