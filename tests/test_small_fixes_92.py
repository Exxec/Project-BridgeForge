"""Small fixes from ROADMAP-3 item 92 (2026-11-16): a missing dependency names itself (92.12); the credits file names the
revived mod's own game version (92.16)."""
from __future__ import annotations

import contextlib
import io
import json
import unittest
from unittest.mock import patch

from tests.support import resolved_temp_dir


class SmallFixesTests(unittest.TestCase):
    def test_a_missing_dependency_is_named_not_a_traceback(self) -> None:
        from bridgeforge import cli

        err = io.StringIO()
        with patch.object(cli, "build_parser", side_effect=ModuleNotFoundError("No module named 'psutil'", name="psutil")), \
                contextlib.redirect_stderr(err):
            code = cli.main(["--help"])
        self.assertEqual(code, 2)
        self.assertIn("missing dependency 'psutil'", err.getvalue())
        self.assertIn("pip install -e .", err.getvalue())

    def test_credits_name_the_revived_game_version(self) -> None:
        from bridgeforge.descriptions import _credits

        with resolved_temp_dir() as root:
            (root / "mod_info.json").write_text(json.dumps({"name": "Mod", "author": "a", "gameVersion": "0.98.5a-RC7"}), encoding="utf-8")
            _credits(root, [("emp_station", "SHIP_SYSTEM")])
            text = (root / "BRIDGEFORGE_CREDITS.txt").read_text(encoding="utf-8")
        self.assertIn("Revival for Starsector 0.98.5a-RC7", text)
        self.assertNotIn("0.98a-RC8", text)


class CliDefaultsTests(unittest.TestCase):
    def test_baseline_accept_finding_scans_with_the_vanilla_core(self) -> None:
        # 92.22: without the core, variant-op-over-budget (priced with vanilla weapons) matched in 1 of 5 mods.
        from bridgeforge import baseline_accept_finding
        from bridgeforge.cli import main

        with resolved_temp_dir() as root:
            (root / "ws" / "working").mkdir(parents=True)
            (root / "core").mkdir()
            with patch("bridgeforge.scan.scanner.scan_mod") as scan, \
                    patch.object(baseline_accept_finding, "accept_selected", return_value={"accepted": []}), \
                    contextlib.redirect_stdout(io.StringIO()):
                scan.return_value.findings = []
                main(["baseline-accept-finding", str(root / "ws"), "x", "--reason", "a reason long enough to pass",
                      "--vanilla-core", str(root / "core"), "--json"])
            self.assertEqual(scan.call_args.kwargs["vanilla_core"], root / "core")

    def test_revive_says_what_blocks_unattended_done(self) -> None:
        # 92.11: Scrapyard's only blocker was one cosmetic description and the output did not say so.
        from bridgeforge.revive import render

        result = {"workspace": "In operation/Mod", "status": "ESCALATED", "hardest_tier": "input", "findings_before": 1,
                  "findings_after": 1, "compile_checked": True, "apply": True, "applied": [], "next": "",
                  "packets": [{"id": "description-missing--mod", "kind": "owner", "tier": "input", "finding": "description-missing", "file": None}]}
        text = render(result)
        self.assertIn("## Blocking UNATTENDED_DONE (1)", text)
        self.assertIn("descriptions draft", text)
        done = render({**result, "status": "UNATTENDED_DONE", "packets": []})
        self.assertNotIn("Blocking", done)
        # 92.6: a ready fixer's diff is pointed to from REVIVE.md.
        ready = render({**result, "packets": [{"id": "variant-wings-exceed-bays--mod", "kind": "owner", "tier": "auto",
                                               "finding": "variant-wings-exceed-bays", "file": None, "fixer_files": 2}]})
        self.assertIn("fixer ready, 2 file(s) would change; diff in reports/escalations/variant-wings-exceed-bays--mod.md", ready)

    def test_a_jar_class_with_shipped_source_gets_one_packet(self) -> None:
        # 92.3: Bultach's hull mods were packeted twice, jars/ORKS.jar!... and src/...
        from pathlib import Path

        from bridgeforge.revive import build_packets

        def finding(file: str) -> dict:
            return {"id": "hullmod-instance-state", "file": file, "classification": "REVIEW", "evidence": [], "severity": "medium",
                    "category": "code", "confidence": "HEURISTIC", "explanation": ""}

        with resolved_temp_dir() as root:
            packets = build_packets(Path(root), [finding("jars/ORKS.jar!data/hullmods/bt_puncher.class"),
                                                 finding("src/data/hullmods/bt_puncher.java"),
                                                 finding("jars/ORKS.jar!data/hullmods/bt_only_compiled.class")],
                                    [{"finding": "hullmod-instance-state", "state": "FIXER_REFUSED", "reason": "x"}], vanilla_core=None)
        self.assertEqual(sorted(p["file"] for p in packets),
                         ["jars/ORKS.jar!data/hullmods/bt_only_compiled.class", "src/data/hullmods/bt_puncher.java"])

    def test_an_acceptance_survives_an_edit_that_moves_lines(self) -> None:
        # 92.29: Tania's accepted system-generation-unguarded came back after an agent fix shifted Carinasystem.java.
        from bridgeforge.baseline import finding_dict_baseline_key, load_baseline_keys

        with resolved_temp_dir() as root:
            stored = root / "baseline.json"
            stored.write_text(json.dumps({"findings": ["system-generation-unguarded||src/World/Carinasystem.java:31: Carina (called from onGameLoad)"]}),
                              encoding="utf-8")
            keys = load_baseline_keys(stored)
        moved = {"id": "system-generation-unguarded", "file": None, "evidence": ["src/World/Carinasystem.java:44: Carina (called from onGameLoad)"]}
        other = {"id": "system-generation-unguarded", "file": None, "evidence": ["src/World/Mustafar.java:44: Mustafar (called from onGameLoad)"]}
        self.assertIn(finding_dict_baseline_key(moved), keys)
        self.assertNotIn(finding_dict_baseline_key(other), keys)  # a different subject is still a new finding

    def test_escalation_run_has_a_default_agent(self) -> None:
        # 92.8: every run of the batch passed the same command; `claude` off PATH resolves to the bundled binary.
        from bridgeforge.cli import build_parser
        from bridgeforge.cmd_revive import DEFAULT_AGENT

        args = build_parser().parse_args(["escalation", "run", "ws", "--all"])
        self.assertEqual(args.agent, DEFAULT_AGENT)


if __name__ == "__main__":
    unittest.main()
