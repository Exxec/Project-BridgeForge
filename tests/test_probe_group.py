"""ROADMAP P15 item 24: probe several finished mods in one live session."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from bridgeforge.probe_group import group_report, install_group, merge_configs, plan_groups
from bridgeforge.probe_config import build_probe_config
from tests.support import link_dir, resolved_temp_dir


def _workspace(queue: Path, name: str, mod_id: str, hull: str, *, deps: list[str] | None = None,
               status: str = "READY_FOR_LIVE_TEST", tc: bool = False, game_version: str = "0.98a-RC8") -> Path:
    working = queue / name / "working"
    (working / "data" / "hulls").mkdir(parents=True)
    (working / "data" / "variants").mkdir(parents=True)
    (working / "reports").mkdir()
    info = {"id": mod_id, "gameVersion": game_version, "dependencies": [{"id": d} for d in deps or []]}
    if tc:
        info["totalConversion"] = "true"
    (working / "mod_info.json").write_text(json.dumps(info), encoding="utf-8")
    (working / "data" / "hulls" / "ship_data.csv").write_text(f"id,hints\n{hull},\n", encoding="utf-8")
    (working / "data" / "variants" / f"{hull}_Std.variant").write_text(json.dumps({"hullId": hull, "variantId": f"{hull}_Std"}), encoding="utf-8")
    (working / "reports" / "REVIVAL_REPORT.md").write_text(f"# Report\n\nsome text\n\n{status}\n", encoding="utf-8")
    return working


def _rig(root: Path, *mod_ids: str) -> Path:
    rig = root / "rig"
    for mod_id in mod_ids:
        (rig / "mods" / mod_id).mkdir(parents=True)
        (rig / "mods" / mod_id / "mod_info.json").write_text(json.dumps({"id": mod_id}), encoding="utf-8")
    (rig / "mods").mkdir(parents=True, exist_ok=True)
    return rig


class PlanTests(unittest.TestCase):
    def test_groups_avoid_shared_ids_missing_dependencies_and_share_nothing_with_a_total_conversion(self) -> None:
        with resolved_temp_dir() as root:
            queue = root / "q"
            _workspace(queue, "A", "mod_a", "hull_a", deps=["lw_lazylib"])
            _workspace(queue, "B", "mod_b", "hull_a")                       # same hull id as A: another group
            _workspace(queue, "C", "mod_c", "hull_c")
            _workspace(queue, "D", "mod_d", "hull_d", deps=["missing_lib"])  # dependency not in the rig
            _workspace(queue, "E", "mod_e", "hull_e", status="ESCALATED")   # not finished: not a candidate
            _workspace(queue, "T", "mod_t", "hull_t", tc=True)               # total conversion: alone
            _workspace(queue, "V", "mod_v", "hull_v", game_version="0.95.1a-RC6")  # launcher would refuse it
            stale = _workspace(queue, "S", "mod_s", "hull_s").parent            # report says ready, revive disagrees
            (stale / "reports" / "revive").mkdir(parents=True)
            (stale / "reports" / "revive" / "REVIVE.json").write_text('{"status": "ESCALATED"}', encoding="utf-8")
            plan = plan_groups(queue, _rig(root, "lw_lazylib"), size=8)
        groups = [[m["workspace"] for m in g["members"]] for g in plan["groups"]]
        self.assertEqual(groups, [["A", "C"], ["B"], ["T"]])
        self.assertEqual(plan["unplaced"][0], {"workspace": "D", "reason": "dependencies not in the rig: missing_lib"})
        self.assertEqual(plan["unplaced"][1]["workspace"], "V")
        self.assertIn("gameVersion 0.95.1a-RC6", plan["unplaced"][1]["reason"])

    def test_group_size_is_respected(self) -> None:
        with resolved_temp_dir() as root:
            queue = root / "q"
            for index in range(5):
                _workspace(queue, f"M{index}", f"mod_{index}", f"hull_{index}")
            plan = plan_groups(queue, _rig(root), size=2)
        self.assertEqual([len(g["members"]) for g in plan["groups"]], [2, 2, 1])


class MergeAndReportTests(unittest.TestCase):
    def test_merged_config_keeps_every_members_content_and_the_report_blames_the_right_mod(self) -> None:
        with resolved_temp_dir() as root:
            queue = root / "q"
            a = build_probe_config(_workspace(queue, "A", "mod_a", "hull_a"))
            b = build_probe_config(_workspace(queue, "B", "mod_b", "hull_b"))
            merged = merge_configs([a, b])
            log = root / "run.stdout.log"
            log.write_text(
                "5 [main] INFO  com.fs.starfarer.StarfarerLauncher  - Starting\n"
                "9 [Thread-2] INFO  com.bridgeforge.probe.ProbeLog  - BF-PROBE|0.2.5|content-ids|FAIL|variant:hull_b_Std|hull mod [x] has no spec\n"
                "9 [Thread-2] INFO  com.bridgeforge.probe.ProbeLog  - BF-PROBE|0.2.5|content-ids|FAIL|all-content|checked=2 failed=1 ship-variants built=2\n",
                encoding="utf-8")
            report = group_report(log, merged)
        self.assertEqual(merged["target_mod_id"], "group:mod_a,mod_b")
        self.assertEqual(merged["content_variants"]["ship"], ["hull_a_Std", "hull_b_Std"])
        self.assertEqual(sorted(merged["group_members"]), ["mod_a", "mod_b"])
        self.assertEqual(report["members"]["mod_a"]["verdict"], "PASS")
        self.assertEqual(report["members"]["mod_b"]["verdict"], "FAIL")
        self.assertIn("hull mod [x] has no spec", report["members"]["mod_b"]["failures"][0])

    def test_a_faction_fleet_generation_failure_blames_the_factions_mod(self) -> None:
        # Probe 0.2.8 faction-fleet-gen (ROADMAP 29.2): a FAIL names the faction, and the report blames its mod.
        with resolved_temp_dir() as root:
            queue = root / "q"
            a = build_probe_config(_workspace(queue, "A", "mod_a", "hull_a"))
            working_b = _workspace(queue, "B", "mod_b", "hull_b")
            (working_b / "data" / "world" / "factions").mkdir(parents=True)
            (working_b / "data" / "world" / "factions" / "b_navy.faction").write_text('{"id": "b_navy"}', encoding="utf-8")
            merged = merge_configs([a, build_probe_config(working_b)])
            log = root / "run.stdout.log"
            log.write_text(
                "5 [main] INFO  com.fs.starfarer.StarfarerLauncher  - Starting\n"
                "9 [Thread-2] INFO  com.bridgeforge.probe.ProbeLog  - BF-PROBE|0.2.8|content-ids|OK|all-content|checked=2 failed=0 ship-variants built=2\n"
                "9 [Thread-2] INFO  com.bridgeforge.probe.ProbeLog  - BF-PROBE|0.2.8|faction-fleet-gen|FAIL|b_navy|FleetFactoryV3 built an empty patrolMedium\n",
                encoding="utf-8")
            report = group_report(log, merged)
        self.assertEqual(report["members"]["mod_a"]["verdict"], "PASS")
        self.assertEqual(report["members"]["mod_b"]["verdict"], "FAIL")

    def test_a_patched_vanilla_faction_is_built_and_blamed_on_the_patching_mod(self) -> None:
        # Probe 0.2.9 (GRP-8, 2026-09-28): Amogus-Shipyards' hegemony.faction has no id; it patches the Hegemony.
        with resolved_temp_dir() as root:
            queue = root / "q"
            a = build_probe_config(_workspace(queue, "A", "mod_a", "hull_a"))
            working_b = _workspace(queue, "B", "mod_b", "hull_b")
            (working_b / "data" / "world" / "factions").mkdir(parents=True)
            (working_b / "data" / "world" / "factions" / "hegemony.faction").write_text('{"knownShips": {"hulls": ["hull_b"]}}', encoding="utf-8")
            merged = merge_configs([a, build_probe_config(working_b)])
            log = root / "run.stdout.log"
            log.write_text("5 [main] INFO  com.fs.starfarer.StarfarerLauncher  - Starting" + chr(10) + ""
                           "9 [Thread-2] INFO  com.bridgeforge.probe.ProbeLog  - BF-PROBE|0.2.9|content-ids|OK|all-content|checked=2 failed=0 ship-variants built=2" + chr(10) + ""
                           "9 [Thread-2] INFO  com.bridgeforge.probe.ProbeLog  - BF-PROBE|0.2.9|faction-fleet-gen|FAIL|hegemony|FleetFactoryV3 built an empty patrolMedium" + chr(10) + "", encoding="utf-8")
            report = group_report(log, merged)
        self.assertEqual(merged["patched_factions"], ["hegemony"])
        self.assertEqual(report["members"]["mod_a"]["verdict"], "PASS")
        self.assertEqual(report["members"]["mod_b"]["verdict"], "FAIL")

    def test_no_content_check_means_incomplete(self) -> None:
        with resolved_temp_dir() as root:
            a = build_probe_config(_workspace(root / "q", "A", "mod_a", "hull_a"))
            log = root / "run.stdout.log"
            log.write_text("5 [main] INFO  com.fs.starfarer.StarfarerLauncher  - Starting\n", encoding="utf-8")
            report = group_report(log, merge_configs([a]))
        self.assertEqual(report["members"]["mod_a"]["verdict"], "INCOMPLETE")


class InstallTests(unittest.TestCase):
    def test_install_copies_members_writes_config_and_enables_dependencies(self) -> None:
        with resolved_temp_dir() as root:
            queue = root / "q"
            _workspace(queue, "A", "mod_a", "hull_a", deps=["lw_lazylib"])
            _workspace(queue, "C", "mod_c", "hull_c")
            rig = _rig(root, "lw_lazylib")
            core = root / "core_real"
            core.mkdir()
            link_dir(core, rig / "starsector-core")
            plan = plan_groups(queue, rig)
            result = install_group(plan, 1, queue, rig, install_probe=False)
            config = json.loads((rig / "saves" / "common" / "bf_probe_config.data").read_text(encoding="utf-8"))
            enabled = json.loads((rig / "mods" / "enabled_mods.json").read_text(encoding="utf-8"))["enabledMods"]
            copied = (rig / "mods" / "A" / "mod_info.json").is_file()
        self.assertEqual(result["members"], ["A", "C"])
        self.assertTrue(copied)
        self.assertEqual(enabled, ["lw_lazylib", "mod_a", "mod_c", "bridgeforge_probe"])
        self.assertEqual(sorted(config["group_members"]), ["mod_a", "mod_c"])

    def test_dependencies_of_dependencies_are_enabled_and_a_missing_one_blocks_the_plan(self) -> None:
        # GRP-SPARKLE (2026-09-27): SPARKLE -> Secrets of the Frontier -> LazyLib, GraphicsLib, LunaLib, MagicLib.
        with resolved_temp_dir() as root:
            queue = root / "q"
            _workspace(queue, "Addon", "addon", "hull_addon", deps=["base"])
            rig = _rig(root, "lib_a", "lib_b")
            (rig / "mods" / "base").mkdir()
            (rig / "mods" / "base" / "mod_info.json").write_text(
                json.dumps({"id": "base", "dependencies": [{"id": "lib_a"}, {"id": "lib_b"}]}), encoding="utf-8")
            core = root / "core_real"
            core.mkdir()
            link_dir(core, rig / "starsector-core")
            install_group(plan_groups(queue, rig), 1, queue, rig, install_probe=False)
            enabled = json.loads((rig / "mods" / "enabled_mods.json").read_text(encoding="utf-8"))["enabledMods"]
            (rig / "mods" / "lib_b" / "mod_info.json").unlink()
            blocked = plan_groups(queue, rig)
        self.assertEqual(enabled, ["lib_a", "lib_b", "base", "addon", "bridgeforge_probe"])
        self.assertEqual(blocked["groups"], [])
        self.assertIn("lib_b", blocked["unplaced"][0]["reason"])

    def test_a_bold_status_line_counts(self) -> None:
        # Older hand-written reports end with **READY_FOR_LIVE_TEST** (RogueSynth, 2026-09-28).
        with resolved_temp_dir() as root:
            queue = root / "q"
            working = _workspace(queue, "A", "mod_a", "hull_a")
            report = working / "reports" / "REVIVAL_REPORT.md"
            report.write_text("# Report" + chr(10) + chr(10) + "## Status" + chr(10) + chr(10) + "**READY_FOR_LIVE_TEST**" + chr(10), encoding="utf-8")
            plan = plan_groups(queue, _rig(root))
        self.assertEqual([m["workspace"] for g in plan["groups"] for m in g["members"]], ["A"])

    def test_install_refuses_a_non_isolated_rig(self) -> None:
        from bridgeforge.probe_config import ProbeConfigError

        with resolved_temp_dir() as root:
            queue = root / "q"
            _workspace(queue, "A", "mod_a", "hull_a")
            rig = _rig(root)
            (rig / "starsector-core").mkdir()
            with self.assertRaises(ProbeConfigError):
                install_group(plan_groups(queue, rig), 1, queue, rig, install_probe=False)


if __name__ == "__main__":
    unittest.main()
