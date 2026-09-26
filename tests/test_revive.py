from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from bridgeforge.cli import main
from bridgeforge.escalation import EscalationError, list_packets, load_packet, run_packet, verify
from bridgeforge.revive import ReviveError, packet_id, render_packet, revive
from tests.support import resolved_temp_dir

CSV = "data/hulls/ship_data.csv"
SETTINGS = "data/config/settings.json"
# json-empty-array-element is tier 'mechanical' (no fixer yet), so it becomes an agent packet.
AGENT_PACKET = packet_id("json-empty-array-element", SETTINGS)


def _workspace(root: Path) -> Path:
    workspace = root / "In operation" / "OldMod"
    working = workspace / "working"
    (working / "data" / "hulls").mkdir(parents=True)
    (working / "mod_info.json").write_text('{"id": "oldmod", "name": "Old Mod", "version": "1", "gameVersion": "0.9.1a"}', encoding="utf-8")
    (working / CSV).write_text("name,id,hitpoints\nA,old_a,１５００\n", encoding="utf-8")
    (working / "data" / "config").mkdir(parents=True)
    (working / SETTINGS).write_text('{\n  "colors": [255,,0],\n  "x": 1\n}\n', encoding="utf-8")
    return workspace


def _agent(root: Path, body: str) -> list[str]:
    """A stand-in for an AI agent: a script run in the sandbox with the packet on stdin."""
    script = root / "agent.py"
    script.write_text("import os, sys\nfrom pathlib import Path\nprompt = sys.stdin.read()\n" + body, encoding="utf-8")
    return [sys.executable, str(script)]


AGENT_FIX = (  # the stand-in agent's fix: drop the empty element, and write the note
    "settings = Path('data/config/settings.json')\n"
    "settings.write_text(settings.read_text(encoding='utf-8').replace('255,,0', '255,0'), encoding='utf-8')\n"
    "Path(os.environ['BF_NOTE']).write_text('Removed the empty array element; the loader skipped it, so the value is unchanged.', encoding='utf-8')\n"
)


class ReviveTests(unittest.TestCase):
    def test_dry_run_changes_nothing_but_writes_packets(self):
        with resolved_temp_dir() as root:
            workspace = _workspace(root)
            before = (workspace / "working" / CSV).read_bytes()
            result = revive(workspace)
            after = (workspace / "working" / CSV).read_bytes()
            packets = {p["id"]: p for p in list_packets(workspace)}
            report = (workspace / "reports" / "revive" / "REVIVE.md").read_text(encoding="utf-8")
        self.assertEqual(before, after)
        self.assertEqual(result["applied"], [])
        self.assertEqual(packets["csv-fullwidth-number--mod"]["fixer"]["state"], "READY_NOT_APPLIED")  # SAFE: would apply with --apply
        self.assertEqual(packets["mod-info-game-version-inexact--mod"]["fixer"]["state"], "AWAITING_APPROVAL")  # REVIEW: needs a yes
        self.assertEqual(packets[AGENT_PACKET]["kind"], "agent")
        self.assertEqual(packets[AGENT_PACKET]["allowed_files"], [SETTINGS])
        self.assertEqual(packets[packet_id("ship-data-missing-fighter-bays-column", "")]["fixer"]["state"], "AWAITING_APPROVAL")
        self.assertIn("Status: **ESCALATED**", report)

    def test_apply_runs_safe_fixers_only_until_approved(self):
        with resolved_temp_dir() as root:
            workspace = _workspace(root)
            first = revive(workspace, apply=True)
            mod_info = (workspace / "working" / "mod_info.json").read_text(encoding="utf-8")
            (workspace.parent / "AUTOMATION_POLICY.json").write_text(json.dumps(
                {"approved_fixers": {"mod-info-game-version-inexact": {"reason": "owner 2026-09-26: every revival targets RC8"}}}), encoding="utf-8")
            second = revive(workspace, apply=True)
            approved_info = (workspace / "working" / "mod_info.json").read_text(encoding="utf-8")
            ledger = (workspace / "reports" / "escalations" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
            scans = sorted(p.name for p in (workspace / "reports").glob("scan-*-revive"))
        self.assertEqual([a["finding"] for a in first["applied"]], ["csv-fullwidth-number"])
        self.assertIn("0.9.1a", mod_info)  # REVIEW finding: not applied without approval
        self.assertEqual([(a["finding"], a["why"]) for a in second["applied"]], [("mod-info-game-version-inexact", "approved")])
        self.assertIn("0.98a-RC8", approved_info)
        self.assertEqual([json.loads(line)["runner"] for line in ledger], ["fixer", "fixer"])
        self.assertTrue(scans)
        self.assertEqual(second["status"], "ESCALATED")

    def test_manual_is_never_applied_without_approval(self):
        with resolved_temp_dir() as root:
            workspace = _workspace(root)
            (workspace / "working" / "data" / "scripts").mkdir(parents=True)
            (workspace / "working" / "data" / "scripts" / "Spawner.java").write_text(
                "package data.scripts;\nimport com.fs.starfarer.api.Global;\npublic class Spawner {\n"
                "  void f() { Global.getSector().createFleet(\"pirates\", \"raiders\"); }\n}\n", encoding="utf-8")
            result = revive(workspace, apply=True)
            source = (workspace / "working" / "data" / "scripts" / "Spawner.java").read_text(encoding="utf-8")
        removed = [p for p in result["packets"] if p["finding"] == "removed-api-call"]
        self.assertEqual([p["kind"] for p in removed], ["owner"])  # found, fix ready, held for a yes
        self.assertNotIn("removed-api-call", [a["finding"] for a in result["applied"]])
        self.assertIn("getSector().createFleet", source)

    def test_packets_are_self_contained_prompts(self):
        with resolved_temp_dir() as root:
            workspace = _workspace(root)
            revive(workspace)
            text = render_packet(load_packet(workspace, AGENT_PACKET))
        for expected in ("## Files you may change", f"- `{SETTINGS}`", '    2    "colors": [255,,0],', "## Rules", "$BF_NOTE", "escalation verify", "## Done means"):
            self.assertIn(expected, text)

    def test_refuses_a_non_workspace(self):
        with resolved_temp_dir() as root:
            with self.assertRaises(ReviveError):
                revive(root)


class EscalationRunTests(unittest.TestCase):
    def test_verified_agent_fix_is_applied_with_backup_and_ledger(self):
        with resolved_temp_dir() as root:
            workspace = _workspace(root)
            revive(workspace)
            dry = run_packet(workspace, AGENT_PACKET, _agent(root, AGENT_FIX))
            untouched = (workspace / "working" / SETTINGS).read_text(encoding="utf-8")
            result = run_packet(workspace, AGENT_PACKET, _agent(root, AGENT_FIX), apply=True)
            settings = (workspace / "working" / SETTINGS).read_text(encoding="utf-8")
            backups = list((workspace / "working" / "data" / "config").glob("*.pre-bf-escalation-*.bak"))
            check = verify(load_packet(workspace, AGENT_PACKET), workspace / "working")
            ledger = [json.loads(line) for line in (workspace / "reports" / "escalations" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
            prompt = (workspace / "scratch" / "escalations" / AGENT_PACKET / "attempt-1" / "PROMPT.md").read_text(encoding="utf-8")
        self.assertEqual(dry["outcome"], "VERIFIED")
        self.assertIn("255,,0", untouched)
        self.assertEqual(result["outcome"], "APPLIED")
        self.assertIn("[255,0]", settings)
        self.assertEqual(len(backups), 1)
        self.assertEqual(check["status"], "PASS")
        self.assertEqual([(e["outcome"], e["classification"]) for e in ledger], [("VERIFIED", "REVIEW"), ("APPLIED", "REVIEW")])
        self.assertIn("--working", prompt)  # the agent verifies its own sandbox, not the real copy

    def test_edits_outside_the_packet_are_rejected(self):
        body = AGENT_FIX + "Path('mod_info.json').write_text('{}', encoding='utf-8')\n"
        with resolved_temp_dir() as root:
            workspace = _workspace(root)
            revive(workspace)
            result = run_packet(workspace, AGENT_PACKET, _agent(root, body), apply=True)
            mod_info = (workspace / "working" / "mod_info.json").read_text(encoding="utf-8")
        self.assertEqual(result["outcome"], "REJECTED")
        self.assertEqual(len(result["attempts"]), 1)  # a scope breach is not retried
        self.assertIn("oldmod", mod_info)

    def test_failures_are_retried_with_feedback(self):
        with resolved_temp_dir() as root:
            workspace = _workspace(root)
            revive(workspace)
            idle = run_packet(workspace, AGENT_PACKET, _agent(root, "pass\n"), retries=1)
            second_prompt = (workspace / "scratch" / "escalations" / AGENT_PACKET / "attempt-2" / "PROMPT.md").read_text(encoding="utf-8")
            no_note = run_packet(workspace, AGENT_PACKET, _agent(root, AGENT_FIX.replace("Path(os.environ['BF_NOTE'])", "Path('/dev/null' if False else os.devnull)")), retries=0)
            wrong = run_packet(workspace, AGENT_PACKET, _agent(root, "Path('data/config/settings.json').write_text('{\"colors\": [1,,,2]}', encoding='utf-8')\nPath(os.environ['BF_NOTE']).write_text('x')\n"), retries=0)
        self.assertEqual([a["outcome"] for a in idle["attempts"]], ["FAILED", "FAILED"])
        self.assertIn("## Previous attempt failed", second_prompt)
        self.assertIn("the agent changed nothing", second_prompt)
        self.assertEqual(no_note["outcome"], "FAILED")
        self.assertTrue(any("no note" in r for r in no_note["attempts"][0]["reasons"]))
        self.assertEqual(wrong["outcome"], "FAILED")
        self.assertTrue(any("remain" in r for r in wrong["attempts"][0]["reasons"]))

    def test_owner_packets_and_bad_input(self):
        with resolved_temp_dir() as root:
            workspace = _workspace(root)
            revive(workspace)
            with self.assertRaises(EscalationError):
                run_packet(workspace, "mod-info-game-version-inexact--mod", _agent(root, AGENT_FIX))
            with self.assertRaises(EscalationError):
                load_packet(workspace, "nope")
            with self.assertRaises(EscalationError):
                run_packet(workspace, AGENT_PACKET, [])

    def test_cli(self):
        with resolved_temp_dir() as root:
            workspace = _workspace(root)
            agent = " ".join(f'"{part}"' for part in _agent(root, AGENT_FIX))
            out = io.StringIO()
            with redirect_stdout(out), redirect_stderr(io.StringIO()):
                self.assertEqual(main(["revive", str(workspace), "--apply"]), 0)
                self.assertEqual(main(["escalation", "list", str(workspace)]), 0)
                self.assertEqual(main(["escalation", "show", str(workspace), AGENT_PACKET]), 0)
                self.assertEqual(main(["escalation", "verify", str(workspace), AGENT_PACKET]), 1)
                self.assertEqual(main(["escalation", "run", str(workspace), "--all", "--agent", agent, "--apply"]), 0)
                self.assertEqual(main(["escalation", "verify", str(workspace), AGENT_PACKET]), 0)
                self.assertEqual(main(["escalation", "run", str(workspace), "--agent", agent]), 2)
                self.assertEqual(main(["revive", str(root / "nowhere")]), 2)
        text = out.getvalue()
        self.assertIn("# Revive: OldMod", text)
        self.assertIn(f"{AGENT_PACKET}  agent  mechanical", text)
        self.assertIn(f"APPLIED: {AGENT_PACKET} after 1 attempt(s)", text)
        self.assertIn(f"PASS: {AGENT_PACKET}", text)


if __name__ == "__main__":
    unittest.main()
