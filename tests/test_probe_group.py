"""ROADMAP P15 item 24: probe several finished mods in one live session."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

from bridgeforge.probe.probe_group import ProbeGroupError, bisect_group, dependency_version_conflicts, install_group, merge_configs, plan_groups
from bridgeforge.probe.probe_record import combat_rounds, combat_undeployed, group_report
from bridgeforge.probe.probe_config import build_probe_config
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

    def test_retest_and_solo_take_a_workspace_path_or_a_bare_name(self) -> None:
        from bridgeforge.cli import main
        with resolved_temp_dir() as root:
            queue = root / "q"
            _workspace(queue, "A", "mod_a", "hull_a")
            _workspace(queue, "B", "mod_b", "hull_b", status="LIVE_VALIDATED")
            _workspace(queue, "C", "mod_c", "hull_c")  # would share A's group unless A runs solo
            plan_file = root / "plan.json"
            with mock.patch("bridgeforge.probe.probe_group.DEFAULT_PROVIDER_SOURCES", ()), mock.patch("sys.stdout"):
                code = main(["probe-group", "plan", "--queue", str(queue), "--rig", str(_rig(root)), "--write", str(plan_file),
                             "--retest", "q/B", "--solo", str(queue / "A")])
            plan = json.loads(plan_file.read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        self.assertEqual(sorted([m["workspace"] for m in g["members"]] for g in plan["groups"]), [["A"], ["B"], ["C"]])

    def test_group_size_is_respected(self) -> None:
        with resolved_temp_dir() as root:
            queue = root / "q"
            for index in range(5):
                _workspace(queue, f"M{index}", f"mod_{index}", f"hull_{index}")
            plan = plan_groups(queue, _rig(root), size=2)
        self.assertEqual([len(g["members"]) for g in plan["groups"]], [2, 2, 1])


class MergeAndReportTests(unittest.TestCase):
    def test_a_member_the_game_could_not_load_fails_and_another_mods_failure_is_the_groups(self) -> None:
        # P1B-CAR-20261120: the gene carrier's mod_info lacked `description`, RC7 skipped the mod, and the run read PASS.
        with resolved_temp_dir() as root:
            queue = root / "q"
            a = build_probe_config(_workspace(queue, "A", "mod_a", "hull_a"))
            b = build_probe_config(_workspace(queue, "B", "mod_b", "hull_b"))
            merged = merge_configs([a, b])
            mods = root / "mods"
            (mods / "A-folder").mkdir(parents=True)
            (mods / "A-folder" / "mod_info.json").write_text(json.dumps({"id": "mod_a"}), encoding="utf-8")
            (mods / "SomeLib").mkdir()
            (mods / "SomeLib" / "mod_info.json").write_text(json.dumps({"id": "some_lib"}), encoding="utf-8")
            log = root / "run.stdout.log"
            log.write_text(
                "607  [main] INFO  com.fs.starfarer.launcher.ModManager  - Error loading mod from [..\\mods\\A-folder]\n"
                '607  [main] INFO  com.fs.starfarer.launcher.ModManager  - JSONObject["description"] not found.\n'
                "9 [Thread-2] INFO  com.bridgeforge.probe.ProbeLog  - BF-PROBE|0.2.5|content-ids|PASS|all-content|checked=2 failed=0\n",
                encoding="utf-8")
            report = group_report(log, merged, mods_dir=mods)
            self.assertEqual(report["members"]["mod_a"]["verdict"], "FAIL")
            self.assertEqual(report["members"]["mod_a"]["failures"],
                             ['mod-load|A-folder|JSONObject["description"] not found.'])
            self.assertEqual(report["members"]["mod_b"]["verdict"], "PASS")
            log.write_text(log.read_text(encoding="utf-8").replace("A-folder", "SomeLib"), encoding="utf-8")
            report = group_report(log, merged, mods_dir=mods)
            self.assertIn('mod-load|SomeLib|JSONObject["description"] not found.', report["unattributed"])
            self.assertEqual(report["members"]["mod_a"]["verdict"], "UNCLEAR")  # a library that did not load: rerun to clear
            # A folder name holding `]` is read whole, and the same failure logged twice is one entry.
            from bridgeforge.probe.probe_record import mod_load_failures

            (mods / "Odd]Name").mkdir()
            (mods / "Odd]Name" / "mod_info.json").write_text(json.dumps({"id": "mod_b"}), encoding="utf-8")
            twice = ("1 [main] INFO  com.fs.starfarer.launcher.ModManager  - Error loading mod from [..\\mods\\Odd]Name]\n"
                     "1 [main] INFO  com.fs.starfarer.launcher.ModManager  - bad\n") * 2
            self.assertEqual(mod_load_failures(twice, mods), [{"folder": "Odd]Name", "mod_id": "mod_b", "reason": "bad"}])
            # A broken folder the game was not asked to enable (LOBSTER-SUB-20261120: the old carrier left in mods/) is no one's.
            (mods / "enabled_mods.json").write_text(json.dumps({"enabledMods": ["mod_a", "mod_b"]}), encoding="utf-8")
            report = group_report(log, merged, mods_dir=mods)
            self.assertEqual(report["unattributed"], [])
            self.assertEqual(report["members"]["mod_a"]["verdict"], "PASS")

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

    def test_a_bounty_line_belongs_to_the_mod_it_names_and_its_acceptance_applies(self) -> None:
        # MagicLib bounty lines name "<mod id>/<bounty id>"; YunruCore's eight went to the group and read UNCLEAR, and its own
        # probe_accepted.json could not apply (P962YC-LIVE-0985a-20261119).
        with resolved_temp_dir() as root:
            queue = root / "q"
            merged = merge_configs([build_probe_config(_workspace(queue, "A", "mod_a", "hull_a")),
                                    build_probe_config(_workspace(queue, "B", "mod_b", "hull_b"))])
            log = root / "run.stdout.log"
            log.write_text(
                "5 [main] INFO  com.fs.starfarer.StarfarerLauncher  - Starting\n"
                "9 [Thread-2] INFO  com.bridgeforge.probe.ProbeLog  - BF-PROBE|0.3.3|content-ids|OK|all-content|checked=2 failed=0 ship-variants built=2\n"
                "9 [Thread-2] INFO  com.bridgeforge.probe.ProbeLog  - BF-PROBE|0.3.3|bounty|FAIL|mod_b/b_hunt|MagicLib has no bounty data for this id (not loaded)\n",
                encoding="utf-8")
            plain = group_report(log, merged)
            accepted = group_report(log, merged, accepted={"mod_b": [{"check": "bounty", "subject": "mod_b/b_hunt", "reason": "needs a sibling mod"}]})
        self.assertEqual(plain["unattributed"], [])
        self.assertEqual((plain["members"]["mod_a"]["verdict"], plain["members"]["mod_b"]["verdict"]), ("PASS", "FAIL"))
        self.assertEqual(accepted["members"]["mod_b"]["verdict"], "PASS")
        self.assertEqual(len(accepted["members"]["mod_b"]["accepted"]), 1)

    def test_an_accepted_probe_finding_is_listed_and_no_longer_fails_the_mod(self) -> None:
        # Magellan's hidden magellan_startigers builds no patrol and nothing spawns its fleets (GRP5C-20261006); the owner-side
        # decision lives in the workspace's working/reports/probe_accepted.json with a reason
        from bridgeforge.probe.probe_record import accepted_probe_findings

        with resolved_temp_dir() as root:
            queue = root / "q"
            a = build_probe_config(_workspace(queue, "A", "mod_a", "hull_a"))
            working_b = _workspace(queue, "B", "mod_b", "hull_b")
            (working_b / "data" / "world" / "factions").mkdir(parents=True)
            (working_b / "data" / "world" / "factions" / "b_navy.faction").write_text('{"id": "b_navy"}', encoding="utf-8")
            (working_b / "data" / "world" / "factions" / "b_other.faction").write_text('{"id": "b_other"}', encoding="utf-8")
            (working_b / "reports").mkdir(exist_ok=True)
            (working_b / "reports" / "probe_accepted.json").write_text(json.dumps({"accepted": [
                {"check": "faction-fleet-gen", "subject": "b_navy", "reason": "hidden, nothing spawns its fleets"},
                {"check": "faction-fleet-gen", "subject": "b_nothing_reason"}]}), encoding="utf-8")
            merged = merge_configs([a, build_probe_config(working_b)])
            log = root / "run.stdout.log"
            log.write_text(
                "5 [main] INFO  com.fs.starfarer.StarfarerLauncher  - Starting\n"
                "9 [Thread-2] INFO  com.bridgeforge.probe.ProbeLog  - BF-PROBE|0.2.8|content-ids|OK|all-content|checked=2 failed=0 ship-variants built=2\n"
                "9 [Thread-2] INFO  com.bridgeforge.probe.ProbeLog  - BF-PROBE|0.2.8|faction-fleet-gen|FAIL|b_navy|FleetFactoryV3 built an empty patrolMedium\n",
                encoding="utf-8")
            accepted = accepted_probe_findings(queue, None)
            with_accepted = group_report(log, merged, accepted=accepted)
            without = group_report(log, merged)
            other_log = root / "other.stdout.log"
            other_log.write_text(log.read_text(encoding="utf-8").replace("|b_navy|", "|b_other|"), encoding="utf-8")
            other_faction = group_report(other_log, merged, accepted=accepted)
        self.assertEqual(list(accepted), ["mod_b"])
        self.assertEqual(len(accepted["mod_b"]), 1, "an entry without a reason is ignored")
        self.assertEqual(with_accepted["members"]["mod_b"]["verdict"], "PASS")
        self.assertIn("faction-fleet-gen|b_navy", with_accepted["members"]["mod_b"]["accepted"][0])
        self.assertEqual(without["members"]["mod_b"]["verdict"], "FAIL")
        self.assertEqual(other_faction["members"]["mod_b"]["verdict"], "FAIL", "only the named faction is accepted")

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

    def _rig_with_saves(self, root: Path) -> tuple[Path, Path]:
        queue = root / "q"
        _workspace(queue, "A", "mod_a", "hull_a")
        rig = _rig(root)
        core = root / "core_real"
        core.mkdir()
        link_dir(core, rig / "starsector-core")
        for name in ("save_Old_1", "save_Old_2"):
            (rig / "saves" / name).mkdir(parents=True)
            (rig / "saves" / name / "campaign.xml").write_text("<x/>", encoding="utf-8")
        (rig / "saves" / "common").mkdir(parents=True, exist_ok=True)
        (rig / "saves" / "common" / "keep.data").write_text("k", encoding="utf-8")
        return queue, rig

    def test_install_moves_earlier_saves_aside_and_keeps_common(self) -> None:
        # SR7-LIVE-0985a-20261117's New Game read a save SR6 had left in the rig (93.50).
        with resolved_temp_dir() as root:
            queue, rig = self._rig_with_saves(root)
            result = install_group(plan_groups(queue, rig), 1, queue, rig, install_probe=False)
            left = sorted(p.name for p in (rig / "saves").iterdir())
            moved_to = Path(result["saves_aside"]["to"])
            moved = sorted(p.name for p in moved_to.iterdir())
            kept = (rig / "saves" / "common" / "keep.data").is_file()
            content = (moved_to / "save_Old_1" / "campaign.xml").read_text(encoding="utf-8")
        self.assertEqual(left, ["common"])
        self.assertTrue(kept)
        self.assertEqual(moved, ["save_Old_1", "save_Old_2"])
        self.assertEqual(result["saves_aside"]["moved"], ["save_Old_1", "save_Old_2"])
        self.assertEqual(moved_to.parent.name, "_saves-moved")
        self.assertEqual(content, "<x/>")  # moved, never deleted

    def test_install_keeps_saves_when_asked(self) -> None:
        with resolved_temp_dir() as root:
            queue, rig = self._rig_with_saves(root)
            result = install_group(plan_groups(queue, rig), 1, queue, rig, install_probe=False, keep_saves=True)
            left = sorted(p.name for p in (rig / "saves").iterdir())
        self.assertEqual(left, ["common", "save_Old_1", "save_Old_2"])
        self.assertEqual(result["saves_aside"]["moved"], [])
        self.assertFalse((rig / "_saves-moved").exists())

    def test_a_linked_saves_folder_is_left_alone(self) -> None:
        from bridgeforge.probe.probe_group import move_aside_saves

        with resolved_temp_dir() as root:
            owners = root / "owners_saves"
            (owners / "save_Mine_1").mkdir(parents=True)
            rig = root / "rig"
            rig.mkdir()
            link_dir(owners, rig / "saves")
            result = move_aside_saves(rig)
            still = (owners / "save_Mine_1").is_dir()
        self.assertEqual(result["moved"], [])
        self.assertIn("junction or link", result["left"])
        self.assertTrue(still)

    def test_only_real_save_folders_move(self) -> None:
        # Review of #213: a `save_*` file, or a `save_*` entry that is a link, is not a game save of the rig's.
        from bridgeforge.probe.probe_group import move_aside_saves

        with resolved_temp_dir() as root:
            rig = root / "rig"
            (rig / "saves" / "save_Real_1").mkdir(parents=True)
            (rig / "saves" / "save_note.txt").write_text("x", encoding="utf-8")
            elsewhere = root / "elsewhere_save"
            elsewhere.mkdir()
            link_dir(elsewhere, rig / "saves" / "save_Linked_1")
            result = move_aside_saves(rig)
            left = sorted(p.name for p in (rig / "saves").iterdir())
        self.assertEqual(result["moved"], ["save_Real_1"])
        self.assertEqual(left, ["save_Linked_1", "save_note.txt"])

    def test_two_batches_in_one_second_do_not_mix(self) -> None:
        from bridgeforge.probe.probe_group import move_aside_saves

        with resolved_temp_dir() as root:
            rig = root / "rig"
            (rig / "saves" / "save_A_1").mkdir(parents=True)
            first = move_aside_saves(rig, stamp="T")
            (rig / "saves" / "save_B_1").mkdir(parents=True)
            second = move_aside_saves(rig, stamp="T")
        self.assertNotEqual(first["to"], second["to"])
        self.assertEqual((first["moved"], second["moved"]), (["save_A_1"], ["save_B_1"]))

    def test_install_enables_speedup_when_the_rig_has_it(self) -> None:
        with resolved_temp_dir() as root:
            queue = root / "q"
            _workspace(queue, "A", "mod_a", "hull_a")
            rig = _rig(root, "speedUp")
            core = root / "core_real"
            core.mkdir()
            link_dir(core, rig / "starsector-core")
            plan = plan_groups(queue, rig)
            install_group(plan, 1, queue, rig, install_probe=False)
            enabled = json.loads((rig / "mods" / "enabled_mods.json").read_text(encoding="utf-8"))["enabledMods"]
        self.assertEqual(enabled, ["mod_a", "bridgeforge_probe", "speedUp"])

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

        from bridgeforge.probe.probe_record import record_group
        with resolved_temp_dir() as root:
            queue = root / "In operation"
            a = _workspace(queue, "A", "mod_a", "hull_a")
            b = _workspace(queue, "B", "mod_b", "hull_b")
            merged = merge_configs([build_probe_config(a), build_probe_config(b)])
            # R1: the run is bound to its staged inputs by a pre-launch manifest; without one the record would be UNBOUND, not archivable.
            from tests.bound_runs import bound_run
            rig, _ = bound_run(root, {"mod_a": queue / "A", "mod_b": queue / "B"}, "GRP-T", [
                "5 [main] INFO  com.fs.starfarer.StarfarerLauncher  - Starting",
                "9 [Thread-2] INFO  com.bridgeforge.probe.ProbeLog  - BF-PROBE|0.2.9|content-ids|FAIL|variant:hull_b_Std|broken",
                "9 [Thread-2] INFO  com.bridgeforge.probe.ProbeLog  - BF-PROBE|0.2.9|content-ids|FAIL|all-content|checked=2 failed=1"],
                expected=("content_ids",))
            policy = root / "policy.json"
            shutil.copy2(Path(__file__).resolve().parent.parent / "bridgeforge" / "release_policy.json", policy)
            # The archive gate (ROADMAP 36.11) needs original/ to audit against.
            shutil.copytree(a, queue / "A" / "original" / "A")
            result = record_group(rig / "logs" / "GRP-T.stdout.log", merged, queue, rig, test_id="GRP-T", archive=True,
                                  done_dir=root / "Done", policy_path=policy, today="2026-09-28")
            from bridgeforge.live.live_trust import live_status
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

    def test_record_describes_the_save_its_own_log_wrote(self) -> None:
        """ROADMAP-3 93.38: G3-LIVE-0985a-20261117 (KoC), recorded after group 4's run, listed Tania's mods as its save's: the
        record read the rig's newest save. The run's log names the folder it saved to."""
        import os
        import time

        from bridgeforge.live.live_trust import save_made_with
        from bridgeforge.probe.probe_record import record_group, run_save_made_with
        from tests.bound_runs import LOAD, MENU, bound_run
        from tests.test_live_trust import DESCRIPTOR

        saving = "100705 [main] INFO  com.fs.starfarer.campaign.save.CampaignGameManager  - Saving to ..\\saves/save_Own_1..."
        with resolved_temp_dir() as root:
            queue = root / "In operation"
            a = _workspace(queue, "A", "mod_a", "hull_a")
            rig, log = bound_run(root, {"mod_a": queue / "A"}, "GRP-S", [MENU, LOAD, saving])
            for name, game in (("save_Own_1", "0.98a-RC8"), ("save_Later_2", "0.98.5a-RC7")):
                (rig / "saves" / name).mkdir(parents=True)
                (rig / "saves" / name / "descriptor.xml").write_text(DESCRIPTOR.replace("0.98a-RC8", game), encoding="utf-8")
            later = time.time() + 60
            os.utime(rig / "saves" / "save_Later_2", (later, later))  # another run's save is the newest
            record_group(log, build_probe_config(a), queue, rig, test_id="GRP-S", today="2026-11-17")
            run = json.loads((queue / "_live" / "GRP-S.json").read_text(encoding="utf-8"))
            unsaved = run_save_made_with(rig, "\n".join([MENU, LOAD]), save_made_with)
            # A path outside the rig is never read, even when a save is there: only its last part is looked up in saves/.
            outside = root / "elsewhere" / "save_Outside_3"
            outside.mkdir(parents=True)
            (outside / "descriptor.xml").write_text(DESCRIPTOR, encoding="utf-8")
            elsewhere = run_save_made_with(rig, saving.replace("..\\saves/save_Own_1", str(outside)), save_made_with)
        self.assertEqual(run["save_made_with"]["game_version"], "0.98a-RC8")
        self.assertIsNone(unsaved)  # a run that saved nothing has no save of its own, whatever else the rig holds
        self.assertIsNone(elsewhere)

    def test_record_refresh_replaces_an_earlier_archive_only_when_asked(self) -> None:
        # Six archives made as READY_FOR_LIVE_TEST stayed that way after their runs passed (2026-10-11): `record --archive` met
        # the existing folder and stopped; `--refresh` is the owner's word to replace it.
        import shutil

        from bridgeforge.probe.probe_record import record_group
        with resolved_temp_dir() as root:
            queue = root / "In operation"
            a = _workspace(queue, "A", "mod_a", "hull_a")
            merged = merge_configs([build_probe_config(a)])
            from tests.bound_runs import bound_run
            rig, log = bound_run(root, {"mod_a": queue / "A"}, "GRP-R", [
                "5 [main] INFO  com.fs.starfarer.StarfarerLauncher  - Starting",
                "9 [Thread-2] INFO  com.bridgeforge.probe.ProbeLog  - BF-PROBE|0.2.9|content-ids|OK|all-content|checked=1 failed=0"],
                expected=("content_ids",))
            policy = root / "policy.json"
            shutil.copy2(Path(__file__).resolve().parent.parent / "bridgeforge" / "release_policy.json", policy)
            shutil.copytree(a, queue / "A" / "original" / "A")
            done = root / "Done"
            first = record_group(log, merged, queue, rig, test_id="GRP-R", archive=True, done_dir=done, policy_path=policy, today="2026-09-28")
            (done / "A" / "marker.txt").write_text("from the first archive", encoding="utf-8")
            again = record_group(log, merged, queue, rig, test_id="GRP-R", archive=True, done_dir=done, policy_path=policy, today="2026-10-11")
            kept = (done / "_replaced-2026-10-11" / "A" / "marker.txt").is_file()  # moved aside, never deleted (60b)
            refreshed = record_group(log, merged, queue, rig, test_id="GRP-R", archive=True, done_dir=done, policy_path=policy,
                                     today="2026-10-11", refresh=True)
            replaced = not (done / "A" / "marker.txt").exists()
            moved_not_deleted = (done / "_replaced-2026-10-11" / "A-2" / "ARCHIVE_NOTE.md").is_file() and (done / "_replaced-2026-10-11" / "A" / "marker.txt").is_file()
            note = (done / "A" / "ARCHIVE_NOTE.md").read_text(encoding="utf-8")
        self.assertEqual(first["archived"], ["A"])
        self.assertEqual(again["archived"], ["A"])
        self.assertTrue(kept)
        self.assertEqual(refreshed["archived"], ["A"])
        self.assertTrue(replaced)
        self.assertTrue(moved_not_deleted)  # DOC-001: refresh moves the previous archive aside, never deletes it
        self.assertIn("archived 2026-10-11", note)

    def test_record_picks_the_workspace_installed_in_the_rig(self) -> None:
        # SEEKER-SOLO2-20260928: workspaces SEEKER (0.3.0) and SEEKER-0.6 share mod id SEEKER; the first by name was
        # recorded and archived, not the SEEKER-0.6 the rig ran. With neither in the rig, the id is ambiguous.
        import shutil

        from bridgeforge.probe.probe_record import _workspaces_by_mod_id
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
            real_member = __import__("bridgeforge.probe.probe_group", fromlist=["_member"])._member

            def member(workspace):
                found = real_member(workspace)
                if workspace.name == "C":
                    found["content"] = [f"id{i}" for i in range(60)]
                    found["config"]["mod_systems"] = ["C Prime"]
                return found

            with mock.patch("bridgeforge.probe.probe_group._member", side_effect=member):
                plan = plan_groups(queue, rig, exclude={"D"}, solo={"B"})
                grouped = plan_groups(queue, rig, exclude={"D"}, auto_solo=False)
        names = [[m["workspace"] for m in g["members"]] for g in plan["groups"]]
        self.assertEqual(names, [["A"], ["B"], ["C"]])
        self.assertEqual([[m["workspace"] for m in g["members"]] for g in grouped["groups"]], [["A", "B", "C"]])

    def test_install_says_close_the_game_when_the_probe_jar_is_in_use(self) -> None:
        # ROADMAP P15 31.9: WinError 32 midway through an install, 2026-09-28.
        from unittest import mock

        from bridgeforge.probe.probe_group import ProbeGroupError, _refuse_running_game
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
        from bridgeforge.probe.probe_config import ProbeConfigError

        with resolved_temp_dir() as root:
            queue = root / "q"
            _workspace(queue, "A", "mod_a", "hull_a")
            rig = _rig(root)
            (rig / "starsector-core").mkdir()
            with self.assertRaises(ProbeConfigError):
                install_group(plan_groups(queue, rig), 1, queue, rig, install_probe=False)


if __name__ == "__main__":
    unittest.main()


class SyncStaleFilesTests(unittest.TestCase):
    """96.12: Broken Star's bf.4 moved two .wpn files out of data/weapons/decorative/, the rig kept the old ones, and record
    refused the passing P962BS5 as "staged files differ from the candidate working copy"."""

    def _copies(self, root: Path) -> tuple[Path, Path]:
        from tests.support import write_text as _write

        working = root / "q" / "BS" / "working"
        _write(working / "mod_info.json", json.dumps({"id": "bs", "version": "1.0+bf.4"}))
        _write(working / "data" / "weapons" / "gun.wpn", "{}")
        target = root / "rig" / "mods" / "BS"
        _write(target / "mod_info.json", json.dumps({"id": "bs", "version": "1.0+bf.4"}))
        _write(target / "data" / "weapons" / "gun.wpn", "{}")
        _write(target / "data" / "weapons" / "decorative" / "gun.wpn", '{"old": true}')
        return working, target

    def test_a_rig_file_the_working_copy_no_longer_has_is_moved_aside_not_deleted(self) -> None:
        from bridgeforge.probe.probe_group import sync_working_copy

        with resolved_temp_dir() as root:
            working, target = self._copies(root)
            said = sync_working_copy(working, target)
            gone = not (target / "data" / "weapons" / "decorative" / "gun.wpn").exists()
            held = list((root / "rig" / "_stale-staged").rglob("gun.wpn"))
            content = held[0].read_text(encoding="utf-8") if held else None
            again = sync_working_copy(working, target)
        self.assertTrue(gone)
        self.assertEqual(len(held), 1)
        self.assertEqual(held[0].parts[-5:], ("BS", "data", "weapons", "decorative", "gun.wpn"))
        self.assertEqual(content, '{"old": true}')
        self.assertIn("moved 1 the working copy no longer has", said)
        self.assertIsNone(again)  # the rig copy now matches: the next sync has nothing to do

    def test_a_path_that_differs_only_in_case_is_not_moved_aside(self) -> None:
        # Review of #214: `Data/x.csv` in the rig and `data/x.csv` in the working copy are one file on Windows; moving the
        # "extra" took away the file just copied, and every other sync lost it again.
        from bridgeforge.probe.probe_group import sync_working_copy
        from tests.support import write_text as _write

        with resolved_temp_dir() as root:
            working, target = self._copies(root)
            (target / "data" / "weapons" / "decorative" / "gun.wpn").unlink()
            weapons = target / "data" / "weapons"
            (weapons / "gun.wpn").rename(weapons / "Gun.wpn")  # the same file name, another case
            _write(weapons / "Gun.wpn", '{"old": 1}')
            for _ in range(3):
                sync_working_copy(working, target)
            present = [p for p in weapons.iterdir() if p.name.lower() == "gun.wpn"]
            held = (root / "rig" / "_stale-staged").exists()
        self.assertTrue(present)  # the rig always has the file
        self.assertFalse(held)    # and nothing was moved aside for it

    def test_a_new_rig_folder_is_copied_whole(self) -> None:
        from bridgeforge.probe.probe_group import sync_working_copy

        with resolved_temp_dir() as root:
            working, _ = self._copies(root)
            target = root / "rig" / "mods" / "Fresh"
            said = sync_working_copy(working, target)
            copied = (target / "data" / "weapons" / "gun.wpn").is_file()
        self.assertEqual(said, "copied")
        self.assertTrue(copied)

    def test_two_stale_batches_are_kept_apart(self) -> None:
        from bridgeforge.probe.probe_group import sync_working_copy
        from tests.support import write_text as _write

        with resolved_temp_dir() as root:
            working, target = self._copies(root)
            sync_working_copy(working, target)
            _write(target / "data" / "weapons" / "decorative" / "gun.wpn", '{"second": true}')
            sync_working_copy(working, target)
            held = sorted(p.read_text(encoding="utf-8") for p in (root / "rig" / "_stale-staged").rglob("gun.wpn"))
        self.assertEqual(held, ['{"old": true}', '{"second": true}'])


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


class InstallHygieneTests(unittest.TestCase):
    def _install(self, root: Path, deps: list[str], rig_ids: tuple[str, ...]):
        queue = root / "q"
        _workspace(queue, "A", "mod_a", "hull_a", deps=deps)
        rig = _rig(root, *rig_ids)
        core = root / "core_real"
        core.mkdir()
        link_dir(core, rig / "starsector-core")
        return queue, rig, plan_groups(queue, rig)

    def test_second_folder_with_a_members_id_is_moved_aside_and_round_counter_reset(self) -> None:
        # SEEKER-0.6 beside SEEKER, Legacy-of-Arkgneisis-0.98a beside Arkgneisis (2026-10-05)
        with resolved_temp_dir() as root:
            queue, rig, plan = self._install(root, [], ())
            (rig / "mods" / "A-old").mkdir()
            (rig / "mods" / "A-old" / "mod_info.json").write_text(json.dumps({"id": "mod_a"}), encoding="utf-8")
            (rig / "saves" / "common").mkdir(parents=True)
            (rig / "saves" / "common" / "bf_probe_combat_round.data").write_text("3", encoding="utf-8")
            result = install_group(plan, 1, queue, rig, install_probe=False)
            gone = not (rig / "mods" / "A-old").exists()
            aside = (rig / "mods-disabled-providers" / "A-old").is_dir()
            counter = (rig / "saves" / "common" / "bf_probe_combat_round.data").exists()
        self.assertEqual(result["moved_aside"], [{"mod_id": "mod_a", "folder": "A-old", "kept": "A"}])
        self.assertTrue(gone and aside)
        self.assertFalse(counter)

    def test_dependency_added_to_mod_info_after_planning_is_enabled(self) -> None:
        # Hiigaran Descendants declared shaderLib after the group was planned (GRP7B-20261005)
        with resolved_temp_dir() as root:
            queue, rig, plan = self._install(root, [], ("shaderLib",))
            info = queue / "A" / "working" / "mod_info.json"
            info.write_text(json.dumps({"id": "mod_a", "gameVersion": "0.98a-RC8", "dependencies": [{"id": "shaderLib"}]}), encoding="utf-8")
            install_group(plan, 1, queue, rig, install_probe=False)
            enabled = json.loads((rig / "mods" / "enabled_mods.json").read_text(encoding="utf-8"))["enabledMods"]
        self.assertEqual(enabled, ["shaderLib", "mod_a", "bridgeforge_probe"])

    def test_provider_copy_missing_a_folder_the_real_install_has_is_reported(self) -> None:
        # Industrial Evolution without its IndEvo/ sounds folder: Fatal on the first Group 2 launch (2026-10-05)
        with resolved_temp_dir() as root:
            queue, rig, plan = self._install(root, ["lib"], ("lib",))
            (rig / "mods" / "lib" / "data").mkdir()
            (root / "mods" / "lib" / "IndEvo").mkdir(parents=True)
            (root / "mods" / "lib" / "data").mkdir()
            (root / "mods" / "lib" / "src").mkdir()
            result = install_group(plan, 1, queue, rig, install_probe=False)
        self.assertEqual(result["incomplete_providers"], [{"mod_id": "lib", "folder": "lib", "missing": ["IndEvo"]}])


class ProbeMissionInReplacingMemberTests(unittest.TestCase):
    def test_probe_row_is_appended_to_a_member_that_replaces_the_mission_list(self) -> None:
        # Ironclads replaces data/missions/mission_list.csv, so the probe mission never showed (GRP10N-20261005)
        from bridgeforge.probe.probe_group import _add_probe_mission_to_replacing_members

        crlf = b"\r\n"
        with resolved_temp_dir() as root:
            rig = root / "rig"
            (rig / "mods" / "bridgeforge-probe" / "data" / "missions").mkdir(parents=True)
            (rig / "mods" / "bridgeforge-probe" / "data" / "missions" / "mission_list.csv").write_text("mission,\nbfprobe_combat,\n", encoding="utf-8")
            conv = rig / "mods" / "Conv"
            (conv / "data" / "missions").mkdir(parents=True)
            (conv / "mod_info.json").write_text(json.dumps({"id": "conv", "replace": ["data/missions/mission_list.csv"]}), encoding="utf-8")
            (conv / "data" / "missions" / "mission_list.csv").write_bytes(b"mission" + crlf + b"conv_one" + crlf)
            plain = rig / "mods" / "Plain"
            (plain / "data" / "missions").mkdir(parents=True)
            (plain / "mod_info.json").write_text(json.dumps({"id": "plain"}), encoding="utf-8")
            (plain / "data" / "missions" / "mission_list.csv").write_bytes(b"mission" + crlf)
            first = _add_probe_mission_to_replacing_members(rig, {"conv": conv, "plain": plain})
            second = _add_probe_mission_to_replacing_members(rig, {"conv": conv, "plain": plain})
            conv_text = (conv / "data" / "missions" / "mission_list.csv").read_bytes()
            plain_text = (plain / "data" / "missions" / "mission_list.csv").read_bytes()
        self.assertEqual(first, ["Conv"])
        self.assertEqual(second, [])
        self.assertEqual(conv_text, b"mission" + crlf + b"conv_one" + crlf + b"bfprobe_combat," + crlf)
        self.assertEqual(plain_text, b"mission" + crlf)


class SmokeGroupTests(unittest.TestCase):
    """probe-group smoke (ROADMAP 60a): boot the installed group unattended and triage the startup log."""

    def _rig(self, base: Path, enabled: list[str]) -> Path:
        rig, core = base / "rig", base / "core"
        core.mkdir()
        (rig / "mods").mkdir(parents=True)
        link_dir(core, rig / "starsector-core")
        (rig / "mods" / "enabled_mods.json").write_text(json.dumps({"enabledMods": enabled}), encoding="utf-8")
        return rig

    def _smoke(self, boot: dict, enabled: list[str] | None = None):
        from unittest import mock

        from bridgeforge.probe.probe_record import smoke_group
        with resolved_temp_dir() as base:
            rig = self._rig(base, ["alpha", "bfprobe"] if enabled is None else enabled)
            with mock.patch("bridgeforge.boot_test.run_boot_test", return_value=boot) as run:
                result = smoke_group(rig, timeout=5)
        return result, run

    def test_clean_boot_is_smoke_pass_and_uses_the_installed_mods(self) -> None:
        boot = {"status": "PASS", "reason": None, "triage": {"counts": {"FATAL": 0, "MOD-ERROR": 0}}}
        result, run = self._smoke(boot)
        self.assertEqual(result["verdict"], "SMOKE_PASS")
        self.assertEqual(run.call_args.args[1], ["alpha", "bfprobe"])
        self.assertEqual(run.call_args.kwargs["bat_name"], "run-j25-direct.bat")

    def test_mod_error_in_the_startup_log_is_smoke_errors(self) -> None:
        boot = {"status": "PASS", "reason": None, "triage": {"counts": {"FATAL": 0, "MOD-ERROR": 2}}}
        self.assertEqual(self._smoke(boot)[0]["verdict"], "SMOKE_ERRORS")

    def test_process_that_never_reaches_the_menu_is_smoke_fail(self) -> None:
        boot = {"status": "SUSPECT_FATAL_DIALOG", "reason": "stuck", "triage": None}
        self.assertEqual(self._smoke(boot)[0]["verdict"], "SMOKE_FAIL")

    def test_nothing_installed_is_refused(self) -> None:
        with self.assertRaises(ProbeGroupError):
            self._smoke({"status": "PASS", "triage": None}, enabled=[])


class SmokeLoadErrorTests(unittest.TestCase):
    """Real lines from saved rig logs: Metelson's rules.csv (GRP1-20261005) and a duplicate name row (GRP10B-20261005)."""

    def _errors(self, text: str):
        from bridgeforge.probe.probe_record import smoke_load_errors
        with resolved_temp_dir() as base:
            log = base / "x.stdout.log"
            log.write_text(text, encoding="utf-8")
            return smoke_load_errors(log)

    def test_mismatched_quotes_and_duplicate_key_are_found(self) -> None:
        text = ("8613 [Thread-2] ERROR com.fs.starfarer.combat.CombatMain  - org.json.JSONException: Mismatched quotes in the string; last quote: [,,\n"
                "13764 [Thread-2] ERROR com.fs.starfarer.combat.CombatMain  - java.lang.RuntimeException: Duplicate key [Mao |  | f | xle | ] while loading [x]\n"
                "1 [main] INFO  fine line\n")
        found = self._errors(text)
        self.assertEqual(len(found), 2)
        self.assertIn("Mismatched quotes", found[0])

    def test_clean_log_and_missing_log_give_nothing(self) -> None:
        from bridgeforge.probe.probe_record import smoke_load_errors
        self.assertEqual(self._errors("1 [main] INFO  Running with the following mods\n"), [])
        self.assertEqual(smoke_load_errors(Path("does-not-exist.log")), [])

    def test_smoke_group_fails_a_clean_menu_boot_whose_log_has_a_load_error(self) -> None:
        from unittest import mock

        from bridgeforge.probe.probe_record import smoke_group
        with resolved_temp_dir() as base:
            rig = SmokeGroupTests()._rig(base, ["alpha"])
            log = base / "boot.stdout.log"
            log.write_text("5 [Thread-2] ERROR x - java.lang.NoClassDefFoundError: lunalib/Foo\n", encoding="utf-8")
            boot = {"status": "PASS", "reason": None, "log": str(log), "triage": {"counts": {"FATAL": 0, "MOD-ERROR": 0}}}
            with mock.patch("bridgeforge.boot_test.run_boot_test", return_value=boot):
                result = smoke_group(rig)
        self.assertEqual(result["verdict"], "SMOKE_ERRORS")
        self.assertEqual(len(result["load_errors"]), 1)


class LunaLibAdviceTests(unittest.TestCase):
    """RC8-25: GraphicsLib 1.12.1 enabled without LunaLib."""

    def test_advice_only_when_graphicslib_is_on_and_lunalib_is_installed_but_off(self) -> None:
        from bridgeforge.probe.probe_group import lunalib_advice
        installed = {"lunalib": "LunaLib-2.0.5", "shaderLib": "GraphicsLib"}
        self.assertIn("--with-lunalib", lunalib_advice(["shaderLib", "demo"], installed))
        self.assertIsNone(lunalib_advice(["shaderLib", "lunalib"], installed))
        self.assertIsNone(lunalib_advice(["demo"], installed))
        self.assertIsNone(lunalib_advice(["shaderLib"], {"shaderLib": "GraphicsLib"}))


class CampaignLayoutAttributionTests(unittest.TestCase):
    """GRP1B2-20261011: Neutrino's campaign-layout FAIL lines name a system, not a content id, so they were group-level and made the
    verdict UNCLEAR. With one member they are that member's, and an accepted entry then applies."""

    def _report(self, accepted):
        with resolved_temp_dir() as root:
            queue = root / "q"
            a = build_probe_config(_workspace(queue, "A", "mod_a", "hull_a"))
            log = root / "run.stdout.log"
            log.write_text(
                "9 [Thread-2] INFO  com.bridgeforge.probe.ProbeLog  - BF-PROBE|0.2.23|content-ids|OK|all-content|checked=1 failed=0\n"
                "9 [Thread-2] INFO  com.bridgeforge.probe.ProbeLog  - BF-PROBE|0.2.23|campaign-layout|FAIL|mod-systems|systems expected=2 missing=1\n",
                encoding="utf-8")
            return group_report(log, merge_configs([a]), accepted=accepted)

    def test_single_member_owns_the_layout_failure(self) -> None:
        report = self._report(None)
        self.assertEqual(report["members"]["mod_a"]["verdict"], "FAIL")
        self.assertEqual(report["unattributed"], [])

    def test_an_accepted_layout_entry_clears_it(self) -> None:
        report = self._report({"mod_a": [{"check": "campaign-layout", "subject": "mod-systems", "reason": "author disabled Exelion"}]})
        self.assertEqual(report["members"]["mod_a"]["verdict"], "PASS")


class CombatPerfTests(unittest.TestCase):
    """Probe 0.2.24 logs combat-perf FAIL when the field runs away (RC8-27: 2,388 wreck hulks after one Bone-Breaker kill)."""

    LINE = "9 [Thread-2] INFO  com.bridgeforge.probe.ProbeLog  - BF-PROBE|0.2.24|combat-perf|FAIL|runaway|hulks=412 ships=430 worstFrameMs=2400 at t=150s\n"
    CONTENT = "9 [Thread-2] INFO  com.bridgeforge.probe.ProbeLog  - BF-PROBE|0.2.24|content-ids|OK|all-content|checked=1 failed=0\n"

    def _report(self, members: int):
        with resolved_temp_dir() as root:
            queue = root / "q"
            configs = [build_probe_config(_workspace(queue, n, f"mod_{n.lower()}", f"hull_{n.lower()}")) for n in ("A", "B")[:members]]
            log = root / "run.stdout.log"
            log.write_text(self.CONTENT + self.LINE, encoding="utf-8")
            return group_report(log, merge_configs(configs))

    def test_a_runaway_fails_the_only_member(self) -> None:
        self.assertEqual(self._report(1)["members"]["mod_a"]["verdict"], "FAIL")

    def test_a_runaway_in_a_bigger_group_makes_every_member_unclear(self) -> None:
        report = self._report(2)
        self.assertEqual({v["verdict"] for v in report["members"].values()}, {"UNCLEAR"})


class CombatRoundsTests(unittest.TestCase):
    """Which slices of the combat plan started a battle. Probe 0.3.2 advanced its round on every definition of the mission and the
    game defines it again after each battle, so G1-LIVE3-0985a-20261117 fought round 1 twice and round 2 never."""

    @staticmethod
    def _log(*events: str) -> str:
        prefix = "9 [main] INFO  com.bridgeforge.probe.ProbeLog  - BF-PROBE|0.3.2|"
        lines = []
        for event in events:
            if event in ("START", "END"):
                lines.append(f"{prefix}probe|INFO|combat|{event}")
            else:
                number, total, hulls = event.split("/")
                lines.append(f"{prefix}combat-round|INFO|round {number} of {total}|hulls {hulls} of 113; restart the mission for the next round")
        return "\n".join(lines) + "\n"

    def test_probe_0_3_2_fought_round_one_twice_and_never_round_two(self) -> None:
        # G1-LIVE3: round 1 started and ended, the game defined round 2 after the battle, the restart defined round 1 again.
        rounds = combat_rounds(self._log("1/2/1-60", "START", "END", "2/2/61-113", "1/2/1-60", "START", "END"))
        self.assertEqual(rounds, {"planned": 2, "started": [1, 1], "missing": [2], "missing_hulls": ["61-113"], "ended": []})

    def test_probe_0_3_4_says_why_each_battle_ended(self) -> None:
        # 96.13: P962SA2-LIVE-0985a-20261119's frigate won early and the probe wrote no END; 0.3.4 says why it ended.
        prefix = "9 [main] INFO  com.bridgeforge.probe.ProbeLog  - BF-PROBE|0.3.4|"
        log = self._log("1/2/1-60", "START") + (
            f"{prefix}combat-end|INFO|side-wiped|t=12s player=sa_frigate enemy=none\n"
            + self._log("END", "2/2/61-105", "START")
            + f"{prefix}combat-end|INFO|time|t=60s player=a,b enemy=c\n" + self._log("END"))
        rounds = combat_rounds(log)
        self.assertEqual(rounds["ended"], [{"reason": "side-wiped", "detail": "t=12s player=sa_frigate enemy=none"},
                                           {"reason": "time", "detail": "t=60s player=a,b enemy=c"}])
        self.assertEqual(rounds["missing"], [])

    def test_a_restart_that_started_nothing_leaves_its_round_out(self) -> None:
        # SR3-LIVE-0985a-20261117: round 2 was defined after the battle and no battle followed.
        self.assertEqual(combat_rounds(self._log("1/2/1-60", "START", "END", "2/2/61-105"))["missing"], [2])

    def test_a_run_stopped_before_a_round_was_defined_names_no_hulls_for_it(self) -> None:
        # Review 2026-11-17: a run stuck or crashed in round 1 never defines round 2, so its hull range is unknown (was a KeyError).
        rounds = combat_rounds(self._log("1/2/1-60", "START"))
        self.assertEqual((rounds["missing"], rounds["missing_hulls"]), ([2], ["?"]))
        rounds = combat_rounds(self._log("1/3/1-60", "START", "END", "2/3/61-120"))
        self.assertEqual((rounds["missing"], rounds["missing_hulls"]), ([2, 3], ["61-120", "?"]))

    def test_probe_0_3_3_fights_each_round_once(self) -> None:
        rounds = combat_rounds(self._log("1/2/1-60", "START", "END", "2/2/61-105", "2/2/61-105", "START", "END", "1/2/1-60"))
        self.assertEqual((rounds["started"], rounds["missing"]), ([1, 2], []))

    def test_a_log_without_combat_plans_nothing(self) -> None:
        self.assertEqual(combat_rounds("nothing\n"), {"planned": 0, "started": [], "missing": [], "missing_hulls": [], "ended": []})

    def test_the_group_report_carries_the_rounds(self) -> None:
        with resolved_temp_dir() as root:
            config = merge_configs([build_probe_config(_workspace(root / "q", "A", "mod_a", "hull_a"))])
            log = root / "run.stdout.log"
            log.write_text(CombatPerfTests.CONTENT + self._log("1/2/1-60", "START", "END", "2/2/61-113", "1/2/1-60", "START", "END"),
                           encoding="utf-8")
            report = group_report(log, config)
        self.assertEqual(report["combat_rounds"]["missing"], [2])
        self.assertEqual(report["members"]["mod_a"]["verdict"], "PASS")  # coverage is reported, not a verdict


class CombatUndeployedTests(unittest.TestCase):
    """93.67: P034-BULTACH-20261122 deployed 67 of its 108 planned hulls; the rest waited in reserve until time ran out."""

    PREFIX = "9 [main] INFO  com.bridgeforge.probe.ProbeLog  - BF-PROBE|0.3.5|"

    def _deployed(self, *hulls: str) -> str:
        return "".join(f"{self.PREFIX}combat-deployment|INFO|{hull}|hull={hull} owner=0\n" for hull in hulls)

    def test_planned_hulls_without_a_deployment_line_are_listed(self) -> None:
        log = (f"{self.PREFIX}combat-round|INFO|round 1 of 1|hulls 1-3 of 3\n"
               + self._deployed("ork_a", "ork_a_module_left", "ork_c"))  # a module is deployed but was never planned
        undeployed = combat_undeployed(log, {"hulls": ["ork_a", "ork_b_Hull_skin", "ork_c"]})
        self.assertEqual(undeployed, {"planned": 3, "deployed": 2, "missing": ["ork_b_Hull_skin"]})

    def test_a_log_without_a_combat_round_plans_nothing(self) -> None:
        self.assertIsNone(combat_undeployed(self._deployed("ork_a"), {"hulls": ["ork_a", "ork_b"]}))

    def test_a_hull_listed_twice_or_not_a_string_is_counted_once_as_planned(self) -> None:
        log = f"{self.PREFIX}combat-round|INFO|round 1 of 1|hulls 1-2 of 2\n" + self._deployed("ork_a")
        undeployed = combat_undeployed(log, {"hulls": ["ork_a", 7, None, "ork_b", "ork_a"]})
        self.assertEqual(undeployed, {"planned": 2, "deployed": 1, "missing": ["ork_b"]})

    def test_the_warn_line_names_ten_hulls_and_counts_the_rest(self) -> None:
        from bridgeforge.probe.cmd_probe_group import undeployed_line

        self.assertIsNone(undeployed_line(None))
        self.assertIsNone(undeployed_line({"planned": 3, "deployed": 3, "missing": []}))
        missing = [f"h{n:02d}" for n in range(12)]
        line = undeployed_line({"planned": 108, "deployed": 96, "missing": missing})
        self.assertIn("12 of 108 planned hulls never deployed", line)
        self.assertIn("h09 and 2 more", line)
        self.assertNotIn("h10", line)

    def test_the_group_report_carries_and_prints_them(self) -> None:
        with resolved_temp_dir() as root:
            config = merge_configs([build_probe_config(_workspace(root / "q", "A", "mod_a", "hull_a"))])
            log = root / "run.stdout.log"
            log.write_text(CombatPerfTests.CONTENT + f"{self.PREFIX}combat-round|INFO|round 1 of 1|hulls 1-1 of 1\n",
                           encoding="utf-8")
            report = group_report(log, config)
        self.assertEqual(report["combat_undeployed"], {"planned": 1, "deployed": 0, "missing": ["hull_a"]})
        self.assertEqual(report["members"]["mod_a"]["verdict"], "PASS")  # coverage is reported, not a verdict


class MarketSupplyTests(unittest.TestCase):
    """Probe 0.2.25's market-supply check: DNEEP's food vanished with Ashes of the Domain's farms and nothing noticed (2026-10-11)."""

    CONTENT = "9 [Thread-2] INFO  com.bridgeforge.probe.ProbeLog  - BF-PROBE|0.2.25|content-ids|OK|all-content|checked=1 failed=0\n"

    @staticmethod
    def _member(queue: Path, name: str, mod_id: str, commodities: list[str]) -> Path:
        working = _workspace(queue, name, mod_id, f"hull_{mod_id}")
        (working / "data" / "campaign").mkdir(parents=True)
        (working / "data" / "campaign" / "commodities.csv").write_text("name,id\n" + "".join(f"X,{c}\n" for c in commodities), encoding="utf-8")
        return working

    def test_the_config_lists_the_mods_commodities_and_a_group_keeps_sweeps(self) -> None:
        with resolved_temp_dir() as root:
            a = build_probe_config(self._member(root / "q", "A", "mod_a", ["dneep_grain", "#comment"]))
            b = build_probe_config(self._member(root / "q", "B", "mod_b", ["zz_ore"]))
        a["class_sweep"], a["mission_fleets"] = ["data.A"], {"ship": ["v_a"], "wing": []}
        merged = merge_configs([a, b])
        self.assertEqual(a["mod_commodities"], ["dneep_grain"])
        self.assertEqual(merged["mod_commodities"], ["dneep_grain", "zz_ore"])
        self.assertEqual(merged["class_sweep"], ["data.A"])
        self.assertEqual(merged["mission_fleets"]["ship"], ["v_a"])
        self.assertEqual(merged["group_members"]["mod_b"]["commodities"], ["zz_ore"])

    def _report(self, lines: str):
        with resolved_temp_dir() as root:
            configs = [build_probe_config(self._member(root / "q", n, f"mod_{n.lower()}", [f"c_{n.lower()}"])) for n in ("A", "B")]
            log = root / "run.stdout.log"
            log.write_text(self.CONTENT + lines, encoding="utf-8")
            return group_report(log, merge_configs(configs))

    def test_demand_without_supply_fails_the_commodity_owner_only(self) -> None:
        report = self._report("BF-PROBE|0.2.25|market-supply|FAIL|c_a|supplied in 0 market(s); demanded in 4: demand with no supply anywhere\n"
                              "BF-PROBE|0.2.25|market-supply|FAIL|commodities|checked=2 expectations=0 failed=1\n")
        self.assertEqual(report["members"]["mod_a"]["verdict"], "FAIL")
        self.assertEqual(report["members"]["mod_b"]["verdict"], "PASS")
        self.assertEqual(report["unattributed"], [])

    def test_an_unmet_expectation_is_blamed_on_the_commodity_owner(self) -> None:
        report = self._report("BF-PROBE|0.2.25|market-supply|FAIL|c_b@aotd_subsidised_farming|no market runs aotd_subsidised_farming\n")
        self.assertEqual(report["members"]["mod_b"]["verdict"], "FAIL")
        self.assertEqual(report["members"]["mod_a"]["verdict"], "PASS")

    def test_install_writes_setups_and_expectations_and_rejects_bad_ones(self) -> None:
        with resolved_temp_dir() as root:
            queue = root / "q"
            self._member(queue, "A", "mod_a", ["dneep_grain"])
            rig = _rig(root)
            core = root / "core_real"
            core.mkdir()
            link_dir(core, rig / "starsector-core")
            plan = plan_groups(queue, rig)
            install_group(plan, 1, queue, rig, install_probe=False, setups=["swap-industry:farming:aotd_subsidised_farming:3:DNEEP_grain"],
                          expect_supply=["dneep_grain@aotd_subsidised_farming"])
            config = json.loads((rig / "saves" / "common" / "bf_probe_config.data").read_text(encoding="utf-8"))
            with self.assertRaises(ValueError):
                install_group(plan, 1, queue, rig, install_probe=False, expect_supply=["dneep_grain"])
            with self.assertRaises(ValueError):
                install_group(plan, 1, queue, rig, install_probe=False, setups=["swap-industry:farming:x"])
        self.assertEqual(config["setups"], ["swap-industry:farming:aotd_subsidised_farming:3:DNEEP_grain"])
        self.assertEqual(config["expect_supply"], ["dneep_grain@aotd_subsidised_farming"])


class MissionAndClassAttributionTests(unittest.TestCase):
    """Found by REG-20261012-G1: with mission-fleets and class-sweep now merged into group configs (2026-10-11), their FAIL lines named
    ids no member owned, so every member of the group read UNCLEAR."""

    CONTENT = "9 INFO x - BF-PROBE|0.2.27|content-ids|OK|all-content|checked=1 failed=0\n"

    def _report(self, lines: str):
        with resolved_temp_dir() as root:
            queue = root / "q"
            a, b = _workspace(queue, "A", "mod_a", "hull_a"), _workspace(queue, "B", "mod_b", "hull_b")
            (a / "data" / "missions" / "m1").mkdir(parents=True)
            (a / "data" / "missions" / "m1" / "mission.json").write_text("{}", encoding="utf-8")
            configs = [build_probe_config(a), build_probe_config(b)]
            configs[0]["mission_fleets"] = {"ship": ["aiv_gone_standard"], "wing": []}
            configs[1]["class_sweep"] = ["data.scripts.Broken"]
            log = root / "run.stdout.log"
            log.write_text(self.CONTENT + lines, encoding="utf-8")
            return group_report(log, merge_configs(configs))

    def test_a_mission_variant_and_a_class_sweep_failure_blame_their_own_mods_only(self) -> None:
        report = self._report("BF-PROBE|0.2.27|content-ids|FAIL|mission-variant:aiv_gone_standard|doesVariantExist=false\n"
                              "BF-PROBE|0.2.27|mission-fleets|FAIL|all-missions|checked=1 failed=1\n"
                              "BF-PROBE|0.2.27|class-sweep|FAIL|data.scripts.Broken|java.lang.NoClassDefFoundError: x\n"
                              "BF-PROBE|0.2.27|class-sweep|FAIL|all-classes|loaded=0 failed=1\n")
        self.assertEqual({m: v["verdict"] for m, v in report["members"].items()}, {"mod_a": "FAIL", "mod_b": "FAIL"})
        self.assertEqual(report["unattributed"], [])
        self.assertIn("mission-variant:aiv_gone_standard", report["members"]["mod_a"]["failures"][0])
        self.assertIn("data.scripts.Broken", report["members"]["mod_b"]["failures"][0])

    def test_a_clean_group_with_mission_and_class_data_still_passes(self) -> None:
        report = self._report("BF-PROBE|0.2.27|mission-fleets|OK|all-missions|checked=1 failed=0\n")
        self.assertEqual({v["verdict"] for v in report["members"].values()}, {"PASS"})


class OptionalIntegrationTests(unittest.TestCase):
    """REG-20261012-G2: Bionic Alteration's console-command and LunaLib classes extend libraries nobody enabled; they are not defects."""

    CONTENT = "9 INFO x - BF-PROBE|0.2.27|content-ids|OK|all-content|checked=1 failed=0\n"
    FAILS = ("BF-PROBE|0.2.27|class-sweep|FAIL|x.commands.AddAll|java.lang.NoClassDefFoundError: org/lazywizard/console/BaseCommand\n"
             "BF-PROBE|0.2.27|class-sweep|FAIL|x.Real|java.lang.NoClassDefFoundError: x/own/Missing\n")

    def _report(self, enabled: list[str] | None):
        with resolved_temp_dir() as root:
            queue = root / "q"
            config = build_probe_config(_workspace(queue, "A", "mod_a", "hull_a"))
            config["class_sweep"] = ["x.commands.AddAll", "x.Real"]
            mods = root / "rig" / "mods"
            mods.mkdir(parents=True)
            if enabled is not None:
                (mods / "enabled_mods.json").write_text(json.dumps({"enabledMods": enabled}), encoding="utf-8")
            log = root / "run.stdout.log"
            log.write_text(self.CONTENT + self.FAILS, encoding="utf-8")
            return group_report(log, merge_configs([config]), mods_dir=mods)

    def test_a_class_of_a_disabled_optional_library_is_not_a_failure_but_an_own_missing_class_still_is(self) -> None:
        report = self._report(["mod_a", "lw_lazylib"])
        self.assertEqual(report["optional_integration_classes"], [{"class": "x.commands.AddAll", "library": "lw_console"}])
        self.assertEqual(len(report["members"]["mod_a"]["failures"]), 1)
        self.assertIn("x.Real", report["members"]["mod_a"]["failures"][0])

    def test_with_the_library_enabled_the_same_class_failure_counts(self) -> None:
        report = self._report(["mod_a", "lw_console"])
        self.assertEqual(report["optional_integration_classes"], [])
        self.assertEqual(len(report["members"]["mod_a"]["failures"]), 2)

    def test_without_a_readable_enabled_list_nothing_is_treated_as_optional(self) -> None:
        report = self._report(None)
        self.assertEqual(len(report["members"]["mod_a"]["failures"]), 2)


class RegressionNoiseTests(unittest.TestCase):
    """REG-20261012: probe-loader artefacts, Nexerelin/SiC integrations and a mod's ERROR-level debug prints must not fail or blur a group."""

    CONTENT = "9 INFO x - BF-PROBE|0.2.27|content-ids|OK|all-content|checked=1 failed=0\n"

    def _report(self, text: str, enabled: list[str]):
        with resolved_temp_dir() as root:
            queue = root / "q"
            config = build_probe_config(_workspace(queue, "A", "mod_a", "hull_a"))
            mods = root / "rig" / "mods"
            mods.mkdir(parents=True)
            (mods / "enabled_mods.json").write_text(json.dumps({"enabledMods": enabled}), encoding="utf-8")
            log = root / "run.stdout.log"
            log.write_text(self.CONTENT + text, encoding="utf-8")
            return group_report(log, merge_configs([config]), mods_dir=mods)

    def test_sandbox_refusals_and_module_info_are_sweep_artefacts_not_failures(self) -> None:
        report = self._report(
            "BF-PROBE|0.2.27|class-sweep|FAIL|org.joml.Matrix2d|java.lang.SecurityException: File access and reflection are not allowed to scripts.\n"
            "BF-PROBE|0.2.27|class-sweep|FAIL|module-info|java.lang.NoClassDefFoundError: module-info is not a class because access_flag ACC_MODULE is set\n", ["mod_a"])
        self.assertEqual(report["members"]["mod_a"]["failures"], [])
        self.assertEqual(report["sweep_artefact_classes"], ["org.joml.Matrix2d", "module-info"])

    def test_nexerelin_and_second_in_command_classes_are_optional_when_those_mods_are_off(self) -> None:
        text = ("BF-PROBE|0.2.27|class-sweep|FAIL|a.Start|java.lang.NoClassDefFoundError: exerelin/campaign/customstart/CustomStart\n"
                "BF-PROBE|0.2.27|class-sweep|FAIL|a.Apt|java.lang.NoClassDefFoundError: second_in_command/specs/SCBaseAptitudePlugin\n")
        text += "BF-PROBE|0.2.27|class-sweep|FAIL|a.Bar|java.lang.NoClassDefFoundError: data/scripts/campaign/bases/VayraRaiderBaseBarEvent\n"
        report = self._report(text, ["mod_a"])
        self.assertEqual({item["library"] for item in report["optional_integration_classes"]}, {"nexerelin", "second_in_command", "vayrasector"})
        self.assertEqual(report["members"]["mod_a"]["failures"], [])

    def test_a_mods_cloak_ai_debug_prints_do_not_make_the_group_unclear(self) -> None:
        events = [{"level": "ERROR", "message": "Cloak AI: Running", "suspect": None},
                  {"level": "ERROR", "message": "Cloak AI: No valid Target.", "suspect": None}]
        counts = {"FATAL": 0, "MOD-ERROR": 2}
        with mock.patch("bridgeforge.log_triage.triage_log", return_value={"fatal": [], "mod_errors": events, "counts": counts}):
            report = self._report("", ["mod_a"])
        self.assertEqual(report["unattributed"], [])
        self.assertEqual(report["members"]["mod_a"]["verdict"], "PASS")
        other = [{"level": "ERROR", "message": "NullPointerException in something", "suspect": None}]
        with mock.patch("bridgeforge.log_triage.triage_log", return_value={"fatal": [], "mod_errors": other, "counts": counts}):
            self.assertEqual(self._report("", ["mod_a"])["members"]["mod_a"]["verdict"], "UNCLEAR")


class ReloadNextStepTests(unittest.TestCase):
    """93.63: after a save-reload run the hint named `run-manifest evaluate`, which does not exist (SA-SR3-20261119)."""

    def test_the_hint_names_a_command_the_parser_accepts(self) -> None:
        import shlex

        from bridgeforge.cli import build_parser
        from bridgeforge.probe.cmd_probe_group import reload_next_step
        line = reload_next_step(Path("rig"), "SA-SR3", {"equal": True, "diff_sections": []})
        command = line.split("bridgeforge ", 1)[1].split(" (", 1)[0]
        args = build_parser().parse_args(shlex.split(command))
        self.assertEqual((args.run_manifest_command, args.run_id, args.json), ("check", "SA-SR3-reload", True))
        self.assertNotIn("RC8-41", line)

    def test_a_lone_systems_diff_points_at_rc8_41(self) -> None:
        from bridgeforge.probe.cmd_probe_group import reload_next_step
        self.assertIn("RC8-41", reload_next_step(Path("rig"), "T", {"equal": False, "diff_sections": ["systems"]}))
        self.assertNotIn("RC8-41", reload_next_step(Path("rig"), "T", {"equal": False, "diff_sections": ["systems", "markets"]}))
        self.assertNotIn("RC8-41", reload_next_step(Path("rig"), "T", None))
