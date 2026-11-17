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

    def test_escalation_run_has_a_default_agent(self) -> None:
        # 92.8: every run of the batch passed the same command; `claude` off PATH resolves to the bundled binary.
        from bridgeforge.cli import build_parser
        from bridgeforge.cmd_revive import DEFAULT_AGENT

        args = build_parser().parse_args(["escalation", "run", "ws", "--all"])
        self.assertEqual(args.agent, DEFAULT_AGENT)


if __name__ == "__main__":
    unittest.main()
