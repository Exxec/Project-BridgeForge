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


def _addon_with_missing_content(root: Path) -> tuple[Path, Path]:
    """An add-on whose variant uses a hull mod and weapon only an old sibling mod in the queue defines."""
    def w(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
        return path

    queue = root / "In operation"
    addon = queue / "Addon" / "working"
    w(addon / "mod_info.json", {"id": "addon", "name": "Addon", "version": "1", "gameVersion": "0.98a-RC8"})
    w(addon / "data/variants/lasher_addon.variant", {"variantId": "lasher_addon", "hullId": "lasher", "hullMods": ["old_armor"],
                                                    "weaponGroups": [{"weapons": {"WS1": "old_gun"}}]})
    prov = queue / "OldProvider" / "working"
    w(prov / "mod_info.json", {"id": "oldprov", "name": "Old Provider", "version": "2", "gameVersion": "0.9a"})
    w(prov / "data/hullmods/hull_mods.csv", "name,id,script\nOld Armor,old_armor,data.hullmods.OldArmor\n")
    w(prov / "data/hullmods/OldArmor.java", "package data.hullmods;\npublic class OldArmor {}\n")
    w(prov / "data/weapons/weapon_data.csv", "name,id\nOld Gun,old_gun\n")
    w(prov / "data/weapons/old_gun.wpn", {"id": "old_gun", "type": "ENERGY", "size": "SMALL"})
    core = root / "core"
    w(core / "data/hullmods/hull_mods.csv", "name,id\nArmor,heavyarmor\n")
    w(core / "data/hulls/ship_data.csv", "name,id\nLasher,lasher\n")
    w(core / "data/hulls/wing_data.csv", "id\ntalon_wing\n")
    w(core / "data/hulls/lasher.ship", {"hullId": "lasher", "hullSize": "FRIGATE", "weaponSlots": [{"id": "WS1", "type": "ENERGY", "size": "SMALL"}]})
    w(core / "data/weapons/weapon_data.csv", "name,id\nVanilla Beam,vbeam\n")
    w(core / "data/weapons/vbeam.wpn", {"id": "vbeam", "type": "ENERGY", "size": "SMALL"})
    return queue / "Addon", core


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

    def test_findings_the_mod_baseline_accepts_are_not_packeted(self):
        # scan --write-baseline's file (working/reports/baseline*.json), as corpus-recheck honours it.
        with resolved_temp_dir() as root:
            workspace = _workspace(root)
            first = revive(workspace)
            accepted = [f"{p['finding']}|{p['file']}|" for p in first["packets"] if p["id"] == AGENT_PACKET]
            (workspace / "working" / "reports").mkdir()
            (workspace / "working" / "reports" / "baseline.json").write_text(json.dumps({"findings": accepted}), encoding="utf-8")
            second = revive(workspace)
        self.assertEqual(accepted, ["json-empty-array-element|data/config/settings.json|"])
        self.assertIn(AGENT_PACKET, [p["id"] for p in first["packets"]])
        self.assertNotIn(AGENT_PACKET, [p["id"] for p in second["packets"]])

    def test_draft_report_only_when_nothing_is_left(self):
        with resolved_temp_dir() as root:
            core = root / "core"
            core.mkdir()
            escalated = revive(_workspace(root), vanilla_core=core, draft_report=True)
            clean = root / "In operation" / "Clean"
            (clean / "working").mkdir(parents=True)
            (clean / "working" / "mod_info.json").write_text(json.dumps({"id": "clean", "name": "Clean", "version": "1", "gameVersion": "0.98a-RC8"}), encoding="utf-8")
            dry = revive(clean, vanilla_core=core, draft_report=True)
            no_file = (clean / "working" / "reports" / "REVIVAL_REPORT.md").exists()
            applied = revive(clean, vanilla_core=core, draft_report=True, apply=True)
            report = (clean / "working" / "reports" / "REVIVAL_REPORT.md").read_text(encoding="utf-8")
            again = revive(clean, vanilla_core=core, draft_report=True, apply=True)
            summary = (clean / "reports" / "revive" / "REVIVE.md").read_text(encoding="utf-8")
        self.assertEqual(escalated["report_draft"]["status"], "NOT_DRAFTED")
        self.assertEqual((dry["status"], dry["report_draft"]["status"]), ("UNATTENDED_DONE", "OK"))
        self.assertFalse(no_file)  # a dry run writes no report
        self.assertEqual(applied["report_draft"]["status"], "WRITTEN")
        self.assertTrue(report.rstrip().endswith("READY_FOR_LIVE_TEST"))
        self.assertEqual(again["report_draft"]["status"], "REFUSED")  # never over an existing report
        self.assertIn("Report draft: REFUSED", summary)

    def test_missing_content_packets_carry_all_three_options(self):
        with resolved_temp_dir() as root:
            workspace, core = _addon_with_missing_content(root)
            result = revive(workspace, vanilla_core=core)
            packet = load_packet(workspace, "content-reference-unresolved--mod")
            text = render_packet(packet)
        self.assertEqual([p["id"] for p in result["packets"]], ["content-reference-unresolved--mod"])
        options = packet["options"]
        self.assertEqual(options["substitutes"]["strategy"], "STRIP_FROM_MOD")
        self.assertEqual(options["substitutes"]["providers"][0]["mod_id"], "oldprov")  # found in the workspace's own queue
        self.assertEqual([(v["provider"], v["files"], v["csv_rows"]) for v in options["vendor"]], [("oldprov", 2, 2)])
        self.assertEqual(options["strip"]["substitutes"], {"weapon:old_gun": ["vbeam"]})
        for expected in ("## Options (computed by BridgeForge)", "Recommended strategy: STRIP_FROM_MOD", "vendor-copy --plan vendor-plan.json",
                         "weapon:old_gun: vanilla fits vbeam"):
            self.assertIn(expected, text)

    def test_options_are_computed_only_for_missing_content(self):
        from unittest.mock import patch

        with resolved_temp_dir() as root, patch("bridgeforge.revive.content_options") as options:
            revive(_workspace(root))  # no missing-content finding here
            self.assertFalse(options.called)
            workspace, core = _addon_with_missing_content(root)
            options.return_value = {"notes": ["stubbed"]}
            result = revive(workspace, vanilla_core=core)
            self.assertEqual(options.call_count, 1)  # once per run, however many packets use it
            self.assertEqual(load_packet(workspace, "content-reference-unresolved--mod")["options"], {"notes": ["stubbed"]})
        self.assertEqual(len(result["packets"]), 1)

    def test_a_safe_finding_with_no_fixer_is_not_a_packet(self):
        # Fantastic Furniture (pilot 4, 2026-09-29): SAFE, null-guarded getEntityById lookups became an agent packet.
        with resolved_temp_dir() as root:
            ws = root / "In operation" / "Guarded"
            (ws / "working" / "data" / "scripts").mkdir(parents=True)
            (ws / "working" / "mod_info.json").write_text(json.dumps({"id": "guarded", "name": "Guarded", "version": "1", "gameVersion": "0.98a-RC8"}), encoding="utf-8")
            (ws / "working" / "data" / "scripts" / "Plugin.java").write_text(
                'class Plugin { void f(com.fs.starfarer.api.campaign.SectorAPI s) { if (s.getEntityById("gilead") != null) { s.getEntityById("gilead").getMarket(); } } }\n',
                encoding="utf-8")
            result = revive(ws)
        self.assertEqual([p["finding"] for p in result["packets"]], [])
        self.assertEqual(result["status"], "UNATTENDED_DONE")

    def test_refuses_a_non_workspace(self):
        with resolved_temp_dir() as root:
            with self.assertRaises(ReviveError):
                revive(root)


class JarOnlyPacketTests(unittest.TestCase):
    def test_jar_only_packets_are_recognised(self):
        # Fast Engine Rendering and Magellan Protectorate (2026-09-30): agents cannot open a jar in their sandbox.
        from bridgeforge.escalation import jar_only
        self.assertTrue(jar_only({"allowed_files": ["jars/x.jar!data/Cls.class"]}))
        self.assertFalse(jar_only({"allowed_files": ["jars/x.jar!data/Cls.class", "src/data/Cls.java"]}))
        self.assertFalse(jar_only({"allowed_files": []}))


class EscalationRunTests(unittest.TestCase):
    def test_a_timeout_kills_the_agent_and_its_helpers(self):
        # Hegemony Expeditionary (2026-10-02): a helper the agent started kept the output pipe open and the run
        # waited 13 hours. Output now goes to a file and the whole tree is killed.
        import time
        hang = ("import subprocess, sys, time\n"
                "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
                "time.sleep(120)\n")
        with resolved_temp_dir() as root:
            workspace = _workspace(root)
            revive(workspace)
            started = time.monotonic()
            result = run_packet(workspace, AGENT_PACKET, _agent(root, hang), retries=0, timeout=3)
            elapsed = time.monotonic() - started
            output = (workspace / "scratch" / "escalations" / AGENT_PACKET / "attempt-1" / "AGENT_OUTPUT.txt").read_text(encoding="utf-8")
        self.assertLess(elapsed, 60)
        self.assertEqual(result["outcome"], "FAILED")
        self.assertIn("timed out", output)

    def test_a_note_written_to_the_literal_variable_name_still_counts(self):
        # Pilot 2026-09-29: agents using file tools wrote "$BF_NOTE" as a file name in the sandbox, and every
        # attempt was REJECTED as a change outside the packet. The prompt now names the real path, and a stray
        # "$BF_NOTE" file is taken as the note.
        literal_fix = AGENT_FIX.replace("Path(os.environ['BF_NOTE'])", "Path('$BF_NOTE')")
        with resolved_temp_dir() as root:
            workspace = _workspace(root)
            revive(workspace)
            result = run_packet(workspace, AGENT_PACKET, _agent(root, literal_fix))
            attempt = workspace / "scratch" / "escalations" / AGENT_PACKET / "attempt-1"
            prompt = (attempt / "PROMPT.md").read_text(encoding="utf-8")
            note = (attempt / "NOTE.md").read_text(encoding="utf-8")
        self.assertEqual(result["outcome"], "VERIFIED")
        self.assertIn("Removed the empty array element", note)
        self.assertNotIn("$BF_NOTE", prompt)
        self.assertIn(str(attempt / "working" / "BF_NOTE.md"), prompt)  # inside the sandbox: agents are confined to it

    def test_a_claude_print_agent_is_pointed_at_the_prompt_file(self):
        # 2026-09-29: Fast Engine Rendering's agents got "no stdin data received in 3s" and exited. A `claude -p`
        # command now also gets a short argument naming BF_PROMPT.md, written into the sandbox (and removed after).
        body = ("import os, sys\nfrom pathlib import Path\n"
                "assert any('BF_PROMPT.md' in arg for arg in sys.argv[1:]), sys.argv\n"
                "assert 'settings.json' in Path('BF_PROMPT.md').read_text(encoding='utf-8')\n" + AGENT_FIX)
        with resolved_temp_dir() as root:
            workspace = _workspace(root)
            revive(workspace)
            script = root / "claude.py"
            script.write_text(body, encoding="utf-8")
            result = run_packet(workspace, AGENT_PACKET, f'"{sys.executable}" "{script}" -p')
            sandbox = workspace / "scratch" / "escalations" / AGENT_PACKET / "attempt-1" / "working"
            leftover = (sandbox / "BF_PROMPT.md").exists()
        self.assertEqual(result["outcome"], "VERIFIED")
        self.assertFalse(leftover)

    def test_a_note_left_as_NOTE_md_inside_the_sandbox_still_counts(self):
        # Pilot 2026-09-29 (Arthr's Faction Blender): a sandbox-confined agent wrote NOTE.md in its working folder.
        in_sandbox = AGENT_FIX.replace("Path(os.environ['BF_NOTE'])", "Path('NOTE.md')")
        with resolved_temp_dir() as root:
            workspace = _workspace(root)
            revive(workspace)
            result = run_packet(workspace, AGENT_PACKET, _agent(root, in_sandbox))
            note = (workspace / "scratch" / "escalations" / AGENT_PACKET / "attempt-1" / "NOTE.md").read_text(encoding="utf-8")
        self.assertEqual(result["outcome"], "VERIFIED")
        self.assertIn("Removed the empty array element", note)

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

    def test_apply_copies_the_reviewed_verified_attempt_without_rerunning(self):
        # P15 item 20.12: run --apply re-runs the agent; apply takes the attempt already verified.
        from bridgeforge.escalation import apply_verified

        with resolved_temp_dir() as root:
            workspace = _workspace(root)
            revive(workspace)
            with self.assertRaises(EscalationError):
                apply_verified(workspace, AGENT_PACKET)  # nothing verified yet
            run_packet(workspace, AGENT_PACKET, _agent(root, AGENT_FIX))
            result = apply_verified(workspace, AGENT_PACKET)
            settings = (workspace / "working" / SETTINGS).read_text(encoding="utf-8")
            ledger = [json.loads(line) for line in (workspace / "reports" / "escalations" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
            with self.assertRaises(EscalationError):
                apply_verified(workspace, AGENT_PACKET)  # working/ now differs from the packet: stale
        self.assertEqual(result["attempt"], 1)
        self.assertIn("[255,0]", settings)
        self.assertEqual([e["outcome"] for e in ledger][-1], "APPLIED")
        self.assertTrue(ledger[-1]["applied_without_rerun"])

    def test_apply_after_another_packet_changed_working(self):
        # ROADMAP P15 31.8 (Angry Periphery, 2026-09-28): an earlier packet's applied fix changed another file in
        # working/; the later attempt's sandbox still holds the old copy, which is not the attempt's own change.
        from bridgeforge.escalation import apply_verified

        with resolved_temp_dir() as root:
            workspace = _workspace(root)
            revive(workspace)
            run_packet(workspace, AGENT_PACKET, _agent(root, AGENT_FIX))
            (workspace / "working" / "mod_info.json").write_text('{"id": "oldmod", "name": "Old Mod", "version": "2"}', encoding="utf-8")
            result = apply_verified(workspace, AGENT_PACKET)
            settings = (workspace / "working" / SETTINGS).read_text(encoding="utf-8")
            mod_info = (workspace / "working" / "mod_info.json").read_text(encoding="utf-8")
        self.assertEqual(result["attempt"], 1)
        self.assertIn("[255,0]", settings)
        self.assertIn('"version": "2"', mod_info)  # the other change is kept, not overwritten by the sandbox copy

    def test_a_jar_source_edit_needs_rebuild_jar(self):
        # ROADMAP P15 31.7: a source fix in a compiled mod changes nothing until the jar is rebuilt.
        from bridgeforge.escalation import apply_verified

        with resolved_temp_dir() as root:
            workspace = _workspace(root)
            revive(workspace)
            run_packet(workspace, AGENT_PACKET, _agent(root, AGENT_FIX))
            packet_path = workspace / "reports" / "escalations" / f"{AGENT_PACKET}.json"
            packet = json.loads(packet_path.read_text(encoding="utf-8"))
            packet["allowed_files"].append("jars/src/data/Fix.java")
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            sandbox = workspace / "scratch" / "escalations" / packet["id"] / "attempt-1" / "working"
            (sandbox / "jars" / "src" / "data").mkdir(parents=True)
            (sandbox / "jars" / "src" / "data" / "Fix.java").write_text("class Fix {}", encoding="utf-8")
            with self.assertRaises(EscalationError) as caught:
                apply_verified(workspace, AGENT_PACKET)
        self.assertIn("--rebuild-jar", str(caught.exception))

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


class SameFilePacketMergeTests(unittest.TestCase):
    """Two agent findings on one file become one packet (Pegasus Belt Council, 2026-09-30)."""

    def test_agent_packets_on_one_file_merge(self) -> None:
        from bridgeforge.revive import _merge_same_file

        def packet(finding: str, file: str, kind: str = "agent") -> dict:
            return {"id": packet_id(finding, file), "finding": finding, "kind": kind, "file": file, "allowed_files": [file] if kind == "agent" else [],
                    "hint": f"hint {finding}", "excerpts": {}, "findings": [{"id": finding, "file": file, "evidence": ["line:3"]}]}

        with resolved_temp_dir() as root:
            (root / "Gen.java").write_text("a\nb\nc\n", encoding="utf-8")
            merged = _merge_same_file([packet("x-entity", "Gen.java"), packet("x-system", "Gen.java"), packet("x-entity", "Other.java"),
                                       packet("x-owner", "Gen.java", kind="owner")], root)
        self.assertEqual(len(merged), 3)
        head = merged[0]
        self.assertEqual(head["merged"], ["x-entity", "x-system"])
        self.assertEqual([f["id"] for f in head["findings"]], ["x-entity", "x-system"])
        self.assertIn("hint x-system", head["hint"])
        self.assertNotIn("merged", merged[1])


class RefusedAutoRoutingTests(unittest.TestCase):
    def test_a_refused_automatic_fix_becomes_an_agent_packet_per_file(self) -> None:
        from bridgeforge.revive import build_packets
        finding = {"id": "hard-coded-campaign-entity-reference", "file": "data/scripts/Gen.java", "classification": "REVIEW",
                   "severity": "medium", "confidence": "DETERMINISTIC", "explanation": "x", "evidence": ["nomios"]}
        with resolved_temp_dir() as root:
            (root / "working" / "data" / "scripts").mkdir(parents=True)
            (root / "working" / "data" / "scripts" / "Gen.java").write_text("class Gen {}", encoding="utf-8")
            packets = build_packets(root, [finding], [{"finding": finding["id"], "state": "FIXER_REFUSED", "reason": "inline argument"}], vanilla_core=None)
        self.assertEqual([(p["kind"], p["file"]) for p in packets], [("agent", "data/scripts/Gen.java")])
