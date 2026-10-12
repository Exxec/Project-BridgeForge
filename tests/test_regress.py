"""ROADMAP 60g(1): the unattended regression pass over every live-validated workspace."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from bridgeforge.regress import perf_lines, run_regression, validated_workspaces
from tests.support import link_dir, resolved_temp_dir


def _workspace(queue: Path, name: str, mod_id: str, status: str) -> None:
    working = queue / name / "working"
    (working / "data" / "hulls").mkdir(parents=True)
    (working / "reports").mkdir()
    (working / "mod_info.json").write_text(json.dumps({"id": mod_id, "gameVersion": "0.98a-RC8"}), encoding="utf-8")
    (working / "data" / "hulls" / "ship_data.csv").write_text(f"id,hints\nhull_{mod_id},\n", encoding="utf-8")
    (working / "reports" / "REVIVAL_REPORT.md").write_text(f"# Report\n\n{status}\n", encoding="utf-8")


PERF_OK = "BF-PROBE|0.2.25|combat-perf|INFO|round-1|frames=900 avgFrameMs=16 worstFrameMs=40 peakHulks=3\n"
PERF_RUNAWAY = "BF-PROBE|0.2.25|combat-perf|FAIL|runaway|hulks=412 worstFrameMs=2400\n"
SUPPLY_FAIL = "BF-PROBE|0.2.25|market-supply|FAIL|c_b|demand with no supply anywhere\n"


class RegressionTests(unittest.TestCase):
    def _run(self, logs: dict[str, str], *, fail_install: bool = False):
        with resolved_temp_dir() as root:
            queue = root / "q"
            _workspace(queue, "A", "mod_a", "LIVE_VALIDATED")
            _workspace(queue, "B", "mod_b", "LIVE_VALIDATED")
            _workspace(queue, "C", "mod_c", "READY_FOR_LIVE_TEST")
            rig = root / "rig"
            (rig / "mods").mkdir(parents=True)
            core = root / "core_real"
            core.mkdir()
            link_dir(core, rig / "starsector-core")
            (rig / "saves" / "common").mkdir(parents=True)
            (rig / "saves" / "common" / "bf_probe_config.data").write_text("{}", encoding="utf-8")
            installed: list[int] = []

            def install(plan, number):
                if fail_install:
                    raise RuntimeError("rig busy")
                installed.append(number)

            def play(rig_path, test_id, **_):
                log = rig_path / "logs" / f"{test_id}.stdout.log"
                log.parent.mkdir(exist_ok=True)
                log.write_text(logs.get(test_id[-2:], ""), encoding="utf-8")
                return SimpleNamespace(verdict="LIVE_DONE", stage="done", detail="", rounds=1, log=str(log))

            def judge(log, config):
                text = Path(log).read_text(encoding="utf-8")
                verdict_b = "FAIL" if "market-supply|FAIL" in text else "PASS"
                return {"members": {"mod_a": {"verdict": "PASS", "failures": [], "crashes": []},
                                    "mod_b": {"verdict": verdict_b, "failures": ["market-supply|c_b"] if verdict_b == "FAIL" else [], "crashes": []}},
                        "unattributed": []}

            out = root / "out" / "regress.json"
            names = [w.name for w in validated_workspaces(queue)]
            result = run_regression(queue, rig, out, quiet=True, test_prefix="REG-T", install=install, play=play, judge=judge)
            written = json.loads(out.read_text(encoding="utf-8"))
            leftover = out.with_name("regress.partial.jsonl").exists()
        return names, result, written, installed, leftover

    def test_only_live_validated_mods_are_run_and_problems_are_listed(self) -> None:
        names, result, written, installed, leftover = self._run({"G1": PERF_OK + SUPPLY_FAIL})
        self.assertEqual(names, ["A", "B"])
        self.assertEqual(installed, [1])
        self.assertFalse(leftover)
        row = written["groups"][0]
        self.assertEqual(row["members"], {"mod_a": "PASS", "mod_b": "FAIL"})
        self.assertEqual(row["supply_failures"], ["c_b"])
        self.assertEqual(row["combat_perf"][0]["subject"], "round-1")
        self.assertEqual([(a["mod"], a["why"]) for a in result["attention"]], [("mod_b", "FAIL")])

    def test_a_runaway_is_in_the_summary_and_a_broken_group_does_not_stop_the_pass(self) -> None:
        _, result, _, _, _ = self._run({"G1": PERF_RUNAWAY})
        self.assertIn("RUNAWAY", result["groups"][0]["summary"])
        _, broken, _, _, _ = self._run({}, fail_install=True)
        self.assertIn("rig busy", broken["groups"][0]["error"])
        self.assertTrue(broken["attention"])

    def test_perf_lines_reads_only_combat_perf(self) -> None:
        with resolved_temp_dir() as root:
            log = root / "x.log"
            log.write_text("noise\n" + PERF_RUNAWAY + SUPPLY_FAIL, encoding="utf-8")
            self.assertEqual([p["status"] for p in perf_lines(log)], ["FAIL"])
            self.assertEqual(perf_lines(root / "missing.log"), [])


class RejudgeTests(unittest.TestCase):
    def test_a_finished_pass_is_judged_again_from_its_saved_logs_with_no_game(self) -> None:
        """REG-20261012-G1: mission-variant lines had no owner, so the whole group read UNCLEAR; re-judging attributes them."""
        from bridgeforge.regress import rejudge

        with resolved_temp_dir() as root:
            queue = root / "q"
            _workspace(queue, "A", "mod_a", "LIVE_VALIDATED")
            _workspace(queue, "B", "mod_b", "LIVE_VALIDATED")
            rig = root / "rig"
            (rig / "mods").mkdir(parents=True)
            log = root / "G1.stdout.log"
            log.write_text("9 INFO x - BF-PROBE|0.2.27|content-ids|OK|all-content|checked=1 failed=0\n"
                           "BF-PROBE|0.2.27|content-ids|FAIL|mission-variant:gone_a|doesVariantExist=false\n"
                           "BF-PROBE|0.2.27|mission-fleets|FAIL|all-missions|checked=1 failed=1\n", encoding="utf-8")
            wa = queue / "A" / "working"
            (wa / "data" / "missions" / "m").mkdir(parents=True)
            (wa / "data" / "missions" / "m" / "descriptor.json").write_text("{}", encoding="utf-8")
            (wa / "data" / "missions" / "m" / "mission_init.json").write_text("{}", encoding="utf-8")
            (wa / "data" / "missions" / "m" / "MissionDefinition.java").write_text(
                'public class MissionDefinition { void d(MissionDefinitionAPI api) { api.addToFleet(FleetSide.ENEMY, "gone_a", FleetMemberType.SHIP, false); } }', encoding="utf-8")
            source = root / "pass.partial.jsonl"
            row = {"group": 1, "members": {"mod_a": "UNCLEAR", "mod_b": "UNCLEAR"}, "log": str(log), "live": {"verdict": "LIVE_DONE"}, "summary": "2 UNCLEAR"}
            source.write_text(json.dumps({"header": 1}) + "\n" + json.dumps({"key": "A+B", "value": row}) + "\n", encoding="utf-8")
            result = rejudge(queue, rig, source, root / "out" / "rejudged.json")
            written = json.loads((root / "out" / "rejudged.json").read_text(encoding="utf-8"))
        members = result["groups"][0]["members"]
        self.assertEqual(members["mod_b"], "PASS")
        self.assertEqual(result["groups"][0]["unattributed"], [])
        self.assertEqual(written["mode"], "PROBE_GROUP_REGRESS_REJUDGED")
        self.assertIn(members["mod_a"], ("FAIL", "PASS"))  # attributed to mod_a either way, never UNCLEAR
        self.assertNotIn("UNCLEAR", members.values())

if __name__ == "__main__":
    unittest.main()
