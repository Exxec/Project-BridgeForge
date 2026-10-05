"""ROADMAP P15 item 24: probe several finished mods in one live session."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from bridgeforge.probe_group import (ProbeGroupError, bisect_group, dependency_version_conflicts, group_report, install_group,
                                     merge_configs, plan_groups)
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
        self.assertEqual(plan["unplaced"][0]["reason"], "dependencies not in the rig: missing_lib")
        self.assertEqual(plan["unplaced"][0]["providers"], ["missing_lib: no ready provider (no workspace declares it)"])
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

    def test_report_counts_combat_filler_sides(self) -> None:
        # ROADMAP P15 31.13: say when vanilla ships stood in for a side with no mod ships.
        with resolved_temp_dir() as root:
            merged = merge_configs([build_probe_config(_workspace(root / "q", "A", "mod_a", "hull_a"))])
            log = root / "run.stdout.log"
            log.write_text("5 [main] INFO  com.fs.starfarer.StarfarerLauncher  - Starting" + chr(10) + ""
                           "9 [Thread-2] INFO  com.bridgeforge.probe.ProbeLog  - BF-PROBE|0.2.9|content-ids|OK|all-content|checked=1 failed=0" + chr(10) + ""
                           "9 [Thread-2] INFO  com.bridgeforge.probe.ProbeLog  - BF-PROBE|0.2.9|combat-filler|INFO|ENEMY|2 vanilla ship(s) added" + chr(10) + "", encoding="utf-8")
            report = group_report(log, merged)
        self.assertEqual(report["combat_filler_sides"], ["ENEMY"])
        self.assertEqual(report["members"]["mod_a"]["verdict"], "PASS")

    def test_no_content_check_means_incomplete(self) -> None:
        with resolved_temp_dir() as root:
            a = build_probe_config(_workspace(root / "q", "A", "mod_a", "hull_a"))
            log = root / "run.stdout.log"
            log.write_text("5 [main] INFO  com.fs.starfarer.StarfarerLauncher  - Starting\n", encoding="utf-8")
            report = group_report(log, merge_configs([a]))
        self.assertEqual(report["members"]["mod_a"]["verdict"], "INCOMPLETE")


def _done(workspace: Path) -> None:
    (workspace / "reports" / "revive").mkdir(parents=True, exist_ok=True)
    (workspace / "reports" / "revive" / "REVIVE.json").write_text('{"status": "UNATTENDED_DONE"}', encoding="utf-8")


class ProviderStagingTests(unittest.TestCase):
    # ROADMAP 36.1 (2026-10-04): SCY Nation Utility waited on SCY, which was revived in the same queue.
    def test_a_ready_provider_is_planned_staged_and_verified(self) -> None:
        with resolved_temp_dir() as root:
            queue = root / "q"
            _workspace(queue, "Addon", "addon", "hull_addon", deps=["base"])
            base = _workspace(queue, "Base", "base", "hull_base", status="ESCALATED").parent  # not itself ready to test
            _done(base)
            rig = _rig(root)
            core = root / "core_real"
            core.mkdir()
            link_dir(core, rig / "starsector-core")
            plan = plan_groups(queue, rig)
            addon_group = next(g for g in plan["groups"] if g["members"][0]["workspace"] == "Addon")
            with self.assertRaises(ProbeGroupError):
                install_group(plan, addon_group["group"], queue, rig, install_probe=False)
            result = install_group(plan, addon_group["group"], queue, rig, install_probe=False, stage=True)
            enabled = json.loads((rig / "mods" / "enabled_mods.json").read_text(encoding="utf-8"))["enabledMods"]
            staged_info = (rig / "mods" / "Base" / "mod_info.json").is_file()
        self.assertEqual(addon_group["members"][0]["stage_providers"], [{"mod_id": "base", "workspace": "Base", "version": ""}])
        self.assertEqual(result["staged_providers"][0]["action"], "copied")
        self.assertTrue(staged_info)
        self.assertEqual(enabled, ["base", "addon", "bridgeforge_probe"])

    def test_an_escalated_provider_is_not_staged(self) -> None:
        with resolved_temp_dir() as root:
            queue = root / "q"
            _workspace(queue, "Addon", "addon", "hull_addon", deps=["base"])
            base = _workspace(queue, "Base", "base", "hull_base").parent
            (base / "reports" / "revive").mkdir(parents=True)
            (base / "reports" / "revive" / "REVIVE.json").write_text('{"status": "ESCALATED"}', encoding="utf-8")
            plan = plan_groups(queue, _rig(root))
        addon = next(u for u in plan["unplaced"] if u["workspace"] == "Addon")
        self.assertIn("base: no ready provider (Base=ESCALATED)", addon["providers"])


class OutsideProviderTests(unittest.TestCase):
    # 2026-10-04: 16 blocked addons were provided by mods in the real install, not the queue.
    def test_a_provider_outside_the_queue_is_staged_from_its_source(self) -> None:
        with resolved_temp_dir() as root:
            queue = root / "q"
            _workspace(queue, "Addon", "addon", "hull_addon", deps=["base"])
            source = root / "install_mods"
            (source / "Base 1.0").mkdir(parents=True)
            (source / "Base 1.0" / "mod_info.json").write_text('{"id": "base", "version": "1.0", "gameVersion": "0.98a-RC8"}', encoding="utf-8")
            (source / "Base 1.0" / "data").mkdir()
            (source / "Base 1.0" / "data" / "x.csv").write_text("id\n", encoding="utf-8")
            rig = _rig(root)
            core = root / "core_real"
            core.mkdir()
            link_dir(core, rig / "starsector-core")
            plan = plan_groups(queue, rig, extra_sources=[source])
            without = plan_groups(queue, rig)
            group = next(g for g in plan["groups"] if g["members"][0]["workspace"] == "Addon")
            result = install_group(plan, group["group"], queue, rig, install_probe=False, stage=True)
            copied = (rig / "mods" / "Base 1.0" / "data" / "x.csv").is_file()
            source_untouched = sorted(p.name for p in (source / "Base 1.0").rglob("*"))
        self.assertEqual(group["members"][0]["stage_providers"][0]["origin"], str(source))
        self.assertIn("Addon", [u["workspace"] for u in without["unplaced"]])
        self.assertEqual(result["staged_providers"][0]["action"], "copied")
        self.assertTrue(copied)
        self.assertEqual(source_untouched, ["data", "mod_info.json", "x.csv"])


class BisectTests(unittest.TestCase):
    def test_a_group_splits_into_two_new_groups(self) -> None:
        plan = {"groups": [{"group": 1, "members": [{"workspace": w} for w in "ABCDE"]}, {"group": 2, "members": [{"workspace": "F"}]}]}
        result = bisect_group(plan, 1)
        with self.assertRaises(ProbeGroupError):
            bisect_group(result, 2)
        self.assertEqual([[m["workspace"] for m in g["members"]] for g in result["groups"][2:]], [["A", "B", "C"], ["D", "E"]])
        self.assertEqual(result["groups"][0]["bisected_into"], [3, 4])


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

    def test_record_marks_passes_and_archives_them(self) -> None:
        # ROADMAP P15 31.1: one command replaces the per-group record script and archive loop.
        import shutil

        from bridgeforge.probe_group import record_group
        with resolved_temp_dir() as root:
            queue = root / "In operation"
            a = _workspace(queue, "A", "mod_a", "hull_a")
            b = _workspace(queue, "B", "mod_b", "hull_b")
            merged = merge_configs([build_probe_config(a), build_probe_config(b)])
            rig = _rig(root)
            (rig / "logs").mkdir(parents=True)
            (rig / "logs" / "GRP-T.stdout.log").write_text("5 [main] INFO  com.fs.starfarer.StarfarerLauncher  - Starting" + chr(10) + ""
                "9 [Thread-2] INFO  com.bridgeforge.probe.ProbeLog  - BF-PROBE|0.2.9|content-ids|FAIL|variant:hull_b_Std|broken" + chr(10) + ""
                "9 [Thread-2] INFO  com.bridgeforge.probe.ProbeLog  - BF-PROBE|0.2.9|content-ids|FAIL|all-content|checked=2 failed=1" + chr(10) + "", encoding="utf-8")
            policy = root / "policy.json"
            shutil.copy2(Path(__file__).resolve().parent.parent / "bridgeforge" / "release_policy.json", policy)
            # The archive gate (ROADMAP 36.11) needs original/ to audit against.
            shutil.copytree(a, queue / "A" / "original" / "A")
            result = record_group(rig / "logs" / "GRP-T.stdout.log", merged, queue, rig, test_id="GRP-T", archive=True,
                                  done_dir=root / "Done", policy_path=policy, today="2026-09-28")
            from bridgeforge.live_trust import live_status
            run = json.loads((queue / "_live" / "GRP-T.json").read_text(encoding="utf-8"))
            live_a = live_status(queue / "A")["status"]
            report_a = (a / "reports" / "REVIVAL_REPORT.md").read_text(encoding="utf-8")
            report_b = (b / "reports" / "REVIVAL_REPORT.md").read_text(encoding="utf-8")
            top_zip = sorted(p.name for p in (root / "Done").glob("*.zip"))
        self.assertEqual((result["recorded"], result["archived"], result["probe_version"]), (["A"], ["A"], "0.2.9"))
        self.assertEqual({m["workspace"]: m["verdict"] for m in run["members"]}, {"A": "PASS", "B": "FAIL"})
        self.assertEqual(run["known_noise"]["status"], "NO_PREVIOUS")
        self.assertEqual(live_a, "CURRENT")
        self.assertTrue(report_a.rstrip().endswith("LIVE_VALIDATED"))
        self.assertNotIn("LIVE_VALIDATED", report_b)
        self.assertEqual(len(top_zip), 1)

    def test_record_picks_the_workspace_installed_in_the_rig(self) -> None:
        # SEEKER-SOLO2-20260928: workspaces SEEKER (0.3.0) and SEEKER-0.6 share mod id SEEKER; the first by name was
        # recorded and archived, not the SEEKER-0.6 the rig ran. With neither in the rig, the id is ambiguous.
        import shutil

        from bridgeforge.probe_group import _workspaces_by_mod_id
        with resolved_temp_dir() as root:
            queue = root / "In operation"
            _workspace(queue, "SEEKER", "SEEKER", "hull_a")
            newer = _workspace(queue, "SEEKER-0.6", "SEEKER", "hull_a").parent
            rig = _rig(root)
            ambiguous = _workspaces_by_mod_id(queue, rig / "mods")
            shutil.copytree(newer / "working", rig / "mods" / "SEEKER-0.6")
            tested = _workspaces_by_mod_id(queue, rig / "mods")
        self.assertIsNone(ambiguous["SEEKER"])
        self.assertEqual(tested["SEEKER"].name, "SEEKER-0.6")

    def test_exclude_solo_and_large_campaign_mods_run_alone(self) -> None:
        # ROADMAP P15 31.3: large campaign mods (systems + 60 content ids) and --solo get their own group.
        from unittest import mock

        with resolved_temp_dir() as root:
            queue = root / "q"
            for name in ("A", "B", "C", "D"):
                _workspace(queue, name, f"mod_{name.lower()}", f"hull_{name.lower()}")
            rig = _rig(root)
            real_member = __import__("bridgeforge.probe_group", fromlist=["_member"])._member

            def member(workspace):
                found = real_member(workspace)
                if workspace.name == "C":
                    found["content"] = [f"id{i}" for i in range(60)]
                    found["config"]["mod_systems"] = ["C Prime"]
                return found

            with mock.patch("bridgeforge.probe_group._member", side_effect=member):
                plan = plan_groups(queue, rig, exclude={"D"}, solo={"B"})
                grouped = plan_groups(queue, rig, exclude={"D"}, auto_solo=False)
        names = [[m["workspace"] for m in g["members"]] for g in plan["groups"]]
        self.assertEqual(names, [["A"], ["B"], ["C"]])
        self.assertEqual([[m["workspace"] for m in g["members"]] for g in grouped["groups"]], [["A", "B", "C"]])

    def test_install_says_close_the_game_when_the_probe_jar_is_in_use(self) -> None:
        # ROADMAP P15 31.9: WinError 32 midway through an install, 2026-09-28.
        from unittest import mock

        from bridgeforge.probe_group import ProbeGroupError, _refuse_running_game
        with resolved_temp_dir() as root:
            jar = root / "mods" / "bridgeforge-probe" / "jars" / "bridgeforge-probe.jar"
            jar.parent.mkdir(parents=True)
            jar.write_bytes(b"jar")
            _refuse_running_game(root)  # free: passes and leaves the jar in place
            self.assertTrue(jar.is_file())
            with mock.patch("pathlib.Path.replace", side_effect=PermissionError(32, "in use")):
                with self.assertRaises(ProbeGroupError) as caught:
                    _refuse_running_game(root)
        self.assertIn("close Starsector", str(caught.exception))

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


class DependencyVersionTests(unittest.TestCase):
    def test_major_mismatch_is_reported_minor_is_not(self) -> None:
        # RC8-23: zzz Bingus Sustem declared IndEvo 3.0.c against 4.1.b and was silently disabled (GRP2C-20261005)
        with resolved_temp_dir() as root:
            mods = root / "mods"
            for folder, info in {
                "IndEvo": {"id": "IndEvo", "version": "4.1.b"},
                "US": {"id": "US", "version": {"major": "3", "minor": "0", "patch": "3"}},
                "Lazy": {"id": "lw_lazylib", "version": "3.0.0"},
                "Bingus": {"id": "bingus", "version": "1", "dependencies": [
                    {"id": "IndEvo", "version": "3.0.c"}, {"id": "US", "version": "3.0.1"}, {"id": "lw_lazylib"}]},
            }.items():
                (mods / folder).mkdir(parents=True)
                (mods / folder / "mod_info.json").write_text(json.dumps(info), encoding="utf-8")
            conflicts = dependency_version_conflicts(mods, ["bingus", "IndEvo"])
        self.assertEqual(conflicts, [{"mod_id": "bingus", "dependency": "IndEvo", "wanted": "3.0.c", "installed": "4.1.b"}])
