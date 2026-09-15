from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.fixers import FixerError, apply_fix, compute_fix, unified_diff_for_change
from bridgeforge.scanner import scan_mod


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _findings(result, finding_id: str):
    return [item for item in result.findings if item.id == finding_id]


class WingDataMissingRoleDescTests(unittest.TestCase):
    """VAC-R002: RC8 cannot load wing_data.csv without 'role desc'; a blank value is accepted."""

    def _mod(self, root: Path, wing_data: str) -> Path:
        _write(root / "mod_info.json", '{"id":"fixture","name":"Fixture","gameVersion":"0.98a"}')
        _write(root / "data" / "hulls" / "wing_data.csv", wing_data)
        return root / "data" / "hulls" / "wing_data.csv"

    def test_apply_appends_a_blank_column_padding_short_rows_then_rescan_clean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self._mod(root, "id,variant,tags,op cost\nwing_a,a_Wing,,4\n#note,x\nwing_b,b_Wing\n")
            self.assertEqual(len(_findings(scan_mod(root), "wing-data-missing-role-desc-column")), 1)
            applied = apply_fix(compute_fix(root, "wing-data-missing-role-desc-column"))
            self.assertTrue(Path(applied[0]["backup"]).is_file())
            self.assertEqual(path.read_text(encoding="utf-8"), "id,variant,tags,op cost,role desc\nwing_a,a_Wing,,4,\n#note,x,,,\nwing_b,b_Wing,,,\n")
            self.assertEqual(_findings(scan_mod(root), "wing-data-missing-role-desc-column"), [])

    def test_comma_only_padding_rows_are_not_mistaken_for_multiline_fields(self) -> None:
        # Cobalt Arms pads wing_data.csv with rows of bare commas; the fixer wrongly refused it.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self._mod(root, "id,variant,role,,number\nwing_a,a,ASSAULT,,\n,,,,\n,,,,26\n")
            apply_fix(compute_fix(root, "wing-data-missing-role-desc-column"))
            self.assertEqual(path.read_text(encoding="utf-8"), "id,variant,role,,number,role desc\nwing_a,a,ASSAULT,,,\n,,,,,\n,,,,26,\n")

    def test_refuses_when_present_or_rows_span_lines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._mod(root, "id,role desc\nwing_a,x\n")
            with self.assertRaises(FixerError):
                compute_fix(root, "wing-data-missing-role-desc-column")
            self._mod(root, 'id,variant\nwing_a,"two\nlines"\n')
            with self.assertRaises(FixerError):
                compute_fix(root, "wing-data-missing-role-desc-column")


class AssaultRoleIsValidTests(unittest.TestCase):
    """RC8's WingRole enum still has ASSAULT (javap, 2026-09-14); the old rewrite to FIGHTER is retired."""

    def test_assault_wings_raise_nothing_and_have_no_rewrite_fixer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "mod_info.json", '{"id":"fixture","name":"Fixture","gameVersion":"0.98a"}')
            _write(root / "data" / "hulls" / "wing_data.csv", "id,role,role desc,op cost\nwing_a,ASSAULT,desc,4\n")
            result = scan_mod(root)
            self.assertEqual(_findings(result, "wing-role-assault-removed"), [])
            self.assertEqual(_findings(result, "fighter-wing-role-invalid"), [])
            with self.assertRaises(FixerError):
                compute_fix(root, "wing-role-assault-removed")


class TargetInterfaceMethodMissingTests(unittest.TestCase):
    SYSTEM = "package data.shipsystems.scripts;\nimport com.fs.starfarer.api.plugins.ShipSystemStatsScript;\npublic class Old implements ShipSystemStatsScript {\n    public void apply() {}\n    public float getActiveOverride(com.fs.starfarer.api.combat.ShipAPI s) { return 2f; }\n}\n"
    HIT = "package data.scripts;\npublic class Hit implements OnHitEffectPlugin {\n    public void onHit(DamagingProjectileAPI projectile, CombatEntityAPI target, Vector2f point, boolean shieldHit, CombatEngineAPI engine) { engine.getTotalElapsedTime(false); }\n}\n"
    MOD = "package data.hullmods;\npublic class Tow implements HullModEffect {\n    public void init() {}\n}\n"

    def test_loose_scripts_gain_rc8_members_without_touching_bodies_then_rescan_clean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "mod_info.json", '{"id":"fixture","name":"Fixture","gameVersion":"0.98a"}')
            _write(root / "data" / "shipsystems" / "scripts" / "Old.java", self.SYSTEM)
            _write(root / "data" / "scripts" / "Hit.java", self.HIT)
            _write(root / "data" / "hullmods" / "Tow.java", self.MOD)
            self.assertEqual(len(_findings(scan_mod(root), "target-interface-method-missing")), 7)
            apply_fix(compute_fix(root, "target-interface-method-missing"))
            system = (root / "data" / "shipsystems" / "scripts" / "Old.java").read_text(encoding="utf-8")
            self.assertIn("return 2f;", system)  # an existing override is kept
            self.assertEqual(system.count("getActiveOverride"), 1)
            self.assertIn("public int getUsesOverride(com.fs.starfarer.api.combat.ShipAPI ship) { return -1; }", system)
            self.assertIn("com.fs.starfarer.api.combat.listeners.ApplyDamageResultAPI damageResult, CombatEngineAPI engine)", (root / "data" / "scripts" / "Hit.java").read_text(encoding="utf-8"))
            self.assertIn("showInRefitScreenModPickerFor", (root / "data" / "hullmods" / "Tow.java").read_text(encoding="utf-8"))
            self.assertEqual(_findings(scan_mod(root), "target-interface-method-missing"), [])

    def test_jar_sources_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "mod_info.json", '{"id":"fixture","name":"Fixture","gameVersion":"0.98a"}')
            _write(root / "jars" / "src" / "data" / "scripts" / "Hit.java", self.HIT)
            with self.assertRaises(FixerError) as caught:
                compute_fix(root, "target-interface-method-missing")
            self.assertIn("jar sources need a rebuild", str(caught.exception))


class RemovedApiCallTests(unittest.TestCase):
    """removed-api-call: 0.6's getSector().createFleet(...) has no RC8 SectorAPI equivalent (javap,
    2026-09-14); the fixer ports call sites to the BF Legacy Fleets library instead."""

    SPAWN_SRC = (
        "package data.scripts.world;\n"
        "public class Spawn extends BaseSpawnPoint {\n"
        "    protected CampaignFleetAPI spawnFleet() {\n"
        "        // getSector().createFleet(\"x\", \"y\") -- commented out, must stay untouched\n"
        "        CampaignFleetAPI fleet = getSector().createFleet(\"gekelonian\", type);\n"
        "        return fleet;\n"
        "    }\n"
        "}\n"
    )
    CONVOY_SRC = (
        "package data.scripts.world;\n"
        "public class Convoy extends BaseSpawnPoint {\n"
        "    protected CampaignFleetAPI spawnFleet() {\n"
        "        return Global.getSector().createFleet(\"gekelonian\", \"heavy\");\n"
        "    }\n"
        "}\n"
    )

    def _mod(self, root: Path, mod_info: str = '{"id":"fixture","name":"Fixture","gameVersion":"0.98a"}') -> None:
        _write(root / "mod_info.json", mod_info)
        _write(root / "data" / "scripts" / "world" / "Spawn.java", self.SPAWN_SRC)
        _write(root / "data" / "scripts" / "world" / "Convoy.java", self.CONVOY_SRC)

    def test_rewrites_both_receiver_forms_leaves_comments_alone_adds_dependency_once_then_rescan_clean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._mod(root)
            before_scan = scan_mod(root)
            self.assertEqual(len(_findings(before_scan, "removed-api-call")), 1)

            plan = compute_fix(root, "removed-api-call")
            changed = {change.path.relative_to(root).as_posix() for change in plan.changes}
            self.assertEqual(
                changed,
                {"data/scripts/world/Spawn.java", "data/scripts/world/Convoy.java", "mod_info.json"},
            )
            applied = apply_fix(plan)
            self.assertTrue(all(Path(item["backup"]).is_file() for item in applied))

            spawn_lines = (root / "data" / "scripts" / "world" / "Spawn.java").read_text(encoding="utf-8").split("\n")
            # The commented-out call keeps its original (unqualified) receiver text untouched...
            self.assertIn('// getSector().createFleet("x", "y") -- commented out', spawn_lines[3])
            # ...while the real, active call is rewritten.
            self.assertNotIn("getSector().createFleet(", spawn_lines[4])
            self.assertIn('bf.legacyfleets.LegacyFleets.createFleet("gekelonian", type);', spawn_lines[4])

            convoy_text = (root / "data" / "scripts" / "world" / "Convoy.java").read_text(encoding="utf-8")
            self.assertIn('bf.legacyfleets.LegacyFleets.createFleet("gekelonian", "heavy");', convoy_text)
            self.assertNotIn("Global.getSector()", convoy_text)

            mod_info = json.loads((root / "mod_info.json").read_text(encoding="utf-8"))
            self.assertEqual(mod_info["dependencies"], [{"id": "bf_legacy_fleets", "name": "BF Legacy Fleets"}])

            after_scan = scan_mod(root)
            self.assertEqual(_findings(after_scan, "removed-api-call"), [])

    def test_existing_dependencies_array_gets_the_entry_prepended_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._mod(
                root,
                '{\n\t"id":"fixture",\n\t"dependencies": [\n\t\t{"id": "lw_lazylib", "name": "LazyLib"}\n\t]\n}\n',
            )
            apply_fix(compute_fix(root, "removed-api-call"))
            mod_info = json.loads((root / "mod_info.json").read_text(encoding="utf-8"))
            self.assertEqual(
                mod_info["dependencies"],
                [{"id": "bf_legacy_fleets", "name": "BF Legacy Fleets"}, {"id": "lw_lazylib", "name": "LazyLib"}],
            )

    def test_dependency_already_present_is_not_duplicated_and_only_source_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._mod(root, '{"id":"fixture","dependencies":[{"id":"bf_legacy_fleets","name":"BF Legacy Fleets"}]}')
            plan = compute_fix(root, "removed-api-call")
            changed = {change.path.relative_to(root).as_posix() for change in plan.changes}
            self.assertEqual(changed, {"data/scripts/world/Spawn.java", "data/scripts/world/Convoy.java"})
            apply_fix(plan)
            mod_info = json.loads((root / "mod_info.json").read_text(encoding="utf-8"))
            self.assertEqual(mod_info["dependencies"], [{"id": "bf_legacy_fleets", "name": "BF Legacy Fleets"}])

    def test_disabled_files_are_never_touched_or_counted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "mod_info.json", '{"id":"fixture"}')
            _write(root / "data" / "scripts" / "world" / "disabled_files" / "Old.java", self.SPAWN_SRC)
            with self.assertRaises(FixerError):
                compute_fix(root, "removed-api-call")

    def test_jar_sources_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "mod_info.json", '{"id":"fixture"}')
            _write(root / "jars" / "src" / "data" / "scripts" / "world" / "Spawn.java", self.SPAWN_SRC)
            with self.assertRaises(FixerError) as caught:
                compute_fix(root, "removed-api-call")
            self.assertIn("jar sources need a rebuild", str(caught.exception))

    def test_refuses_when_no_removed_call_is_present(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "mod_info.json", '{"id":"fixture"}')
            with self.assertRaises(FixerError):
                compute_fix(root, "removed-api-call")

    def test_refuses_when_dependencies_is_not_an_array(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._mod(root, '{"id":"fixture","dependencies":"oops"}')
            with self.assertRaises(FixerError):
                compute_fix(root, "removed-api-call")

    def test_global_getsectorapi_create_fleet_receiver_is_also_rewritten(self) -> None:
        # E6, 2026-09-14: javap confirms Global.getSectorAPI() returns SectorAPI too.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "mod_info.json", '{"id":"fixture"}')
            _write(
                root / "data" / "scripts" / "world" / "Spawn.java",
                'package data.scripts.world;\npublic class Spawn extends BaseSpawnPoint {\n'
                '    CampaignFleetAPI f() { return Global.getSectorAPI().createFleet("CAPSCO", type); }\n}\n',
            )
            apply_fix(compute_fix(root, "removed-api-call"))
            text = (root / "data" / "scripts" / "world" / "Spawn.java").read_text(encoding="utf-8")
            self.assertIn('bf.legacyfleets.LegacyFleets.createFleet("CAPSCO", type);', text)
            self.assertNotIn("getSectorAPI()", text)
            mod_info = json.loads((root / "mod_info.json").read_text(encoding="utf-8"))
            self.assertEqual(mod_info["dependencies"], [{"id": "bf_legacy_fleets", "name": "BF Legacy Fleets"}])


class AddMessageRewriteTests(unittest.TestCase):
    """removed-api-call, E6 (2026-09-14): RC8's SectorAPI has no addMessage; the fixer inserts
    .getCampaignUI() before .addMessage(, keeping the original receiver, since CampaignUIAPI has it."""

    CONVOY_SRC = (
        "package data.scripts.world;\n"
        "public class Convoy extends BaseSpawnPoint {\n"
        "    protected CampaignFleetAPI spawnFleet() {\n"
        "        // Global.getSectorAPI().addMessage(\"x\") -- commented out, must stay untouched\n"
        "        Global.getSectorAPI().addMessage(\"A CAPSCO supply convoy is in-system\");\n"
        "        return null;\n"
        "    }\n"
        "    private Script createArrivedScript() {\n"
        "        return new Script() {\n"
        "            public void run() {\n"
        "                Global.getSectorAPI().addMessage(\"delivered\");\n"
        "            }\n"
        "        };\n"
        "    }\n"
        "    private void bare() {\n"
        "        getSector().addMessage(\"bare receiver\");\n"
        "    }\n"
        "}\n"
    )

    def _mod(self, root: Path) -> Path:
        _write(root / "mod_info.json", '{"id":"fixture","name":"Fixture","gameVersion":"0.98a"}')
        path = root / "data" / "scripts" / "world" / "Convoy.java"
        _write(path, self.CONVOY_SRC)
        return path

    def test_inserts_getcampaignui_before_addmessage_keeping_receiver_and_does_not_add_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self._mod(root)
            before_scan = scan_mod(root)
            self.assertEqual(len(_findings(before_scan, "removed-api-call")), 1)

            plan = compute_fix(root, "removed-api-call")
            changed = {change.path.relative_to(root).as_posix() for change in plan.changes}
            # mod_info.json is untouched: no createFleet rewrite happened in this run, so no dependency is added.
            self.assertEqual(changed, {"data/scripts/world/Convoy.java"})
            apply_fix(plan)

            lines = path.read_text(encoding="utf-8").split("\n")
            # The commented-out call keeps its original text untouched...
            self.assertIn('// Global.getSectorAPI().addMessage("x") -- commented out', lines[3])
            # ...while the real calls are rewritten, receiver kept, .getCampaignUI() inserted before .addMessage(.
            self.assertIn('Global.getSectorAPI().getCampaignUI().addMessage("A CAPSCO supply convoy is in-system");', lines[4])
            text = path.read_text(encoding="utf-8")
            self.assertIn('Global.getSectorAPI().getCampaignUI().addMessage("delivered");', text)
            self.assertIn('getSector().getCampaignUI().addMessage("bare receiver");', text)

            mod_info = json.loads((root / "mod_info.json").read_text(encoding="utf-8"))
            self.assertNotIn("dependencies", mod_info)

            after_scan = scan_mod(root)
            self.assertEqual(_findings(after_scan, "removed-api-call"), [])

    def test_create_fleet_and_add_message_together_rewrite_both_and_add_dependency_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "mod_info.json", '{"id":"fixture"}')
            _write(
                root / "data" / "scripts" / "world" / "Convoy.java",
                "package data.scripts.world;\npublic class Convoy extends BaseSpawnPoint {\n"
                "    CampaignFleetAPI spawnFleet() {\n"
                '        CampaignFleetAPI fleet = getSector().createFleet("CAPSCO", "supplyConvoy");\n'
                '        Global.getSectorAPI().addMessage("under way");\n'
                "        return fleet;\n"
                "    }\n}\n",
            )
            plan = compute_fix(root, "removed-api-call")
            apply_fix(plan)
            text = (root / "data" / "scripts" / "world" / "Convoy.java").read_text(encoding="utf-8")
            self.assertIn('bf.legacyfleets.LegacyFleets.createFleet("CAPSCO", "supplyConvoy");', text)
            self.assertIn('Global.getSectorAPI().getCampaignUI().addMessage("under way");', text)
            mod_info = json.loads((root / "mod_info.json").read_text(encoding="utf-8"))
            self.assertEqual(mod_info["dependencies"], [{"id": "bf_legacy_fleets", "name": "BF Legacy Fleets"}])
            self.assertEqual(_findings(scan_mod(root), "removed-api-call"), [])


class CrewXPLevelNotRewrittenTests(unittest.TestCase):
    """removed-api-call, E6 (2026-09-14): RC8's CargoAPI no longer nests CrewXPLevel, and its plain
    addCrew(int) is not a behaviour-equivalent replacement, so this fixer never rewrites it."""

    def test_crewxplevel_only_file_refuses_rather_than_guess(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "mod_info.json", '{"id":"fixture"}')
            _write(
                root / "data" / "scripts" / "world" / "Convoy.java",
                "package data.scripts.world;\n"
                "import com.fs.starfarer.api.campaign.CargoAPI.CrewXPLevel;\n"
                "public class Convoy extends BaseSpawnPoint {\n"
                "    void crew(CargoAPI cargo) { cargo.addCrew(CrewXPLevel.VETERAN, 5); }\n}\n",
            )
            with self.assertRaises(FixerError) as caught:
                compute_fix(root, "removed-api-call")
            self.assertIn("no safe mechanical rewrite", str(caught.exception))
            self.assertIn("CargoAPI.CrewXPLevel", str(caught.exception))

    def test_addmessage_is_rewritten_but_crewxplevel_in_the_same_file_is_left_for_the_owner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "mod_info.json", '{"id":"fixture"}')
            path = root / "data" / "scripts" / "world" / "Convoy.java"
            _write(
                path,
                "package data.scripts.world;\n"
                "import com.fs.starfarer.api.campaign.CargoAPI.CrewXPLevel;\n"
                "public class Convoy extends BaseSpawnPoint {\n"
                "    void spawn(CargoAPI cargo) {\n"
                "        cargo.addCrew(CrewXPLevel.VETERAN, 5);\n"
                '        Global.getSectorAPI().addMessage("heavy convoy returned");\n'
                "    }\n}\n",
            )
            before_scan = scan_mod(root)
            self.assertEqual(len(_findings(before_scan, "removed-api-call")), 2)  # addMessage + CrewXPLevel

            apply_fix(compute_fix(root, "removed-api-call"))
            text = path.read_text(encoding="utf-8")
            self.assertIn('Global.getSectorAPI().getCampaignUI().addMessage("heavy convoy returned");', text)
            # CrewXPLevel is untouched: no rewrite exists for it.
            self.assertIn("import com.fs.starfarer.api.campaign.CargoAPI.CrewXPLevel;", text)
            self.assertIn("cargo.addCrew(CrewXPLevel.VETERAN, 5);", text)

            after_scan = scan_mod(root)
            remaining = _findings(after_scan, "removed-api-call")
            self.assertEqual(len(remaining), 1)
            self.assertEqual(remaining[0].evidence[0], "CargoAPI.CrewXPLevel: 1 call(s)")


class ModInfoGameVersionInexactTests(unittest.TestCase):
    def _mod(self, root: Path) -> None:
        _write(root / "mod_info.json", '{"id":"fixture","name":"Fixture","gameVersion":"0.97a"}')

    def test_requires_target_game_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._mod(root)
            with self.assertRaises(FixerError):
                compute_fix(root, "mod-info-game-version-inexact")

    def test_dry_run_byte_identical_then_apply_and_rescan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._mod(root)
            path = root / "mod_info.json"
            before = path.read_bytes()
            plan = compute_fix(root, "mod-info-game-version-inexact", {"target_game_version": "0.98a"})
            self.assertEqual(path.read_bytes(), before)
            before_scan = scan_mod(root, vanilla_core=None)
            applied = apply_fix(plan)
            self.assertTrue(Path(applied[0]["backup"]).is_file())
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["gameVersion"], "0.98a")
            self.assertEqual(data["id"], "fixture")


class CsvRowExtraColumnsTests(unittest.TestCase):
    def test_drops_trailing_empty_extras_and_rescans_clean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "mod_info.json", '{"id":"fixture","name":"Fixture"}')
            _write(
                root / "data" / "strings" / "descriptions.csv",
                "id,text\nrow1,hello,,\nrow2,world\n",
            )
            path = root / "data" / "strings" / "descriptions.csv"
            before = path.read_bytes()
            plan = compute_fix(root, "csv-row-extra-columns")
            self.assertEqual(path.read_bytes(), before)
            before_scan = scan_mod(root)
            self.assertEqual(len(_findings(before_scan, "csv-row-extra-columns")), 1)
            apply_fix(plan)
            self.assertEqual(path.read_text(encoding="utf-8"), "id,text\nrow1,hello\nrow2,world\n")
            after_scan = scan_mod(root)
            self.assertEqual(_findings(after_scan, "csv-row-extra-columns"), [])

    def test_refuses_when_extra_field_non_empty(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(
                root / "data" / "strings" / "descriptions.csv",
                "id,text\nrow1,hello,unexpected\n",
            )
            with self.assertRaises(FixerError):
                compute_fix(root, "csv-row-extra-columns")


class CsvMissingDesignTypeColumnTests(unittest.TestCase):
    def _mod(self, root: Path) -> None:
        _write(
            root / "data" / "hulls" / "ship_data.csv",
            "id,name,hints\nff_cruiser,Cruiser,\nvanilla_hull,Vanilla,\n",
        )

    def test_requires_all_options(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._mod(root)
            with self.assertRaises(FixerError):
                compute_fix(root, "csv-missing-design-type-column")

    def test_apply_adds_column_and_settings_color_then_rescan_clean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._mod(root)
            options = {"design_type": "FF", "id_prefixes": ["ff_"], "design_color": "10,20,30"}
            plan = compute_fix(root, "csv-missing-design-type-column", options)
            before_scan = scan_mod(root)
            self.assertEqual(len(_findings(before_scan, "csv-missing-design-type-column")), 1)
            apply_fix(plan)
            ship_data = (root / "data" / "hulls" / "ship_data.csv").read_text(encoding="utf-8")
            lines = ship_data.splitlines()
            self.assertEqual(lines[0], "id,name,hints,tech/manufacturer")
            self.assertEqual(lines[1], "ff_cruiser,Cruiser,,FF")
            self.assertEqual(lines[2], "vanilla_hull,Vanilla,,")
            settings = json.loads((root / "data" / "config" / "settings.json").read_text(encoding="utf-8"))
            self.assertEqual(settings["designTypeColors"]["FF"], [10, 20, 30, 255])
            after_scan = scan_mod(root)
            self.assertEqual(_findings(after_scan, "csv-missing-design-type-column"), [])

    def test_existing_settings_designtypecolors_key_left_alone(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._mod(root)
            _write(root / "data" / "config" / "settings.json", '{"designTypeColors":{"Other":[1,2,3,255]}}')
            options = {"design_type": "FF", "id_prefixes": ["ff_"], "design_color": "10,20,30"}
            plan = compute_fix(root, "csv-missing-design-type-column", options)
            # Only the CSV file should be part of the plan; settings.json already has the key.
            self.assertEqual(len(plan.changes), 1)
            self.assertTrue(str(plan.changes[0].path).endswith("ship_data.csv"))


class ProcgenRowMissingTests(unittest.TestCase):
    def _vanilla(self, vanilla: Path) -> None:
        _write(
            vanilla / "data" / "campaign" / "procgen" / "planet_gen_data.csv",
            "id,age,frequency\nbarren,ANY,10\n",
        )
        _write(
            vanilla / "data" / "campaign" / "procgen" / "star_gen_data.csv",
            "id,freqYOUNG,freqAVERAGE,freqOLD\nstar_yellow,5,5,5\n",
        )

    def test_requires_options(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(FixerError):
                compute_fix(root, "procgen-planet-row-missing")

    def test_apply_clones_and_zeroes_planet_frequency_then_rescan_clean(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as vanilla_dir:
            root = Path(mod_dir)
            vanilla = Path(vanilla_dir)
            self._vanilla(vanilla)
            _write(root / "data" / "config" / "planets.json", '{"custom_planet":{"isStar":false,"name":"Custom"}}')
            _write(root / "src" / "S.java", 'class S { void g() { api.addPlanet("x", "custom_planet"); } }')
            before_scan = scan_mod(root, vanilla_core=vanilla)
            self.assertEqual(len(_findings(before_scan, "procgen-planet-row-missing")), 1)
            options = {"vanilla_core": vanilla, "type_id": "custom_planet", "from_vanilla_id": "barren"}
            plan = compute_fix(root, "procgen-planet-row-missing", options)
            apply_fix(plan)
            written = (root / "data" / "campaign" / "procgen" / "planet_gen_data.csv").read_text(encoding="utf-8")
            self.assertEqual(written, "id,age,frequency\ncustom_planet,ANY,0\n")
            after_scan = scan_mod(root, vanilla_core=vanilla)
            self.assertEqual(_findings(after_scan, "procgen-planet-row-missing"), [])

    def test_apply_clones_and_zeroes_star_frequencies(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as vanilla_dir:
            root = Path(mod_dir)
            vanilla = Path(vanilla_dir)
            self._vanilla(vanilla)
            _write(root / "data" / "config" / "planets.json", '{"custom_star":{"isStar":true,"name":"Custom Star"}}')
            _write(root / "src" / "S.java", 'class S { void g() { api.addStar("custom_star"); } }')
            options = {"vanilla_core": vanilla, "type_id": "custom_star", "from_vanilla_id": "star_yellow"}
            plan = compute_fix(root, "procgen-star-row-missing", options)
            apply_fix(plan)
            written = (root / "data" / "campaign" / "procgen" / "star_gen_data.csv").read_text(encoding="utf-8")
            self.assertEqual(written, "id,freqYOUNG,freqAVERAGE,freqOLD\ncustom_star,0,0,0\n")


class FactionKnownListsMissingTests(unittest.TestCase):
    def test_requires_options(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(FixerError):
                compute_fix(root, "faction-known-lists-missing")

    def test_apply_derives_known_lists_from_variants_and_rescan_clean(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as vanilla_dir:
            root = Path(mod_dir)
            vanilla = Path(vanilla_dir)
            faction_path = root / "data" / "world" / "factions" / "newfac.faction"
            _write(
                faction_path,
                '{"id":"newfac","displayName":"New Faction",'
                '"shipRoles":{"role1":{"variant1":1}}}',
            )
            _write(vanilla / "data" / "world" / "factions" / "pirates.faction", '{"id":"pirates"}')
            _write(root / "data" / "variants" / "variant1.variant", '{"hullId":"hull1","weaponGroups":[{"weapons":{"WP0":"weapon1"}}],"wings":["wing1_wing"]}')
            _write(root / "data" / "hulls" / "ship_data.csv", "id,name\nhull1,Hull One\n")
            _write(root / "data" / "weapons" / "weapon_data.csv", "id,name\nweapon1,Weapon One\n")
            _write(root / "data" / "hulls" / "wing_data.csv", "id,role,role desc,op cost\nwing1_wing,FIGHTER,desc,4\n")

            before_scan = scan_mod(root, vanilla_core=vanilla)
            self.assertEqual(len(_findings(before_scan, "faction-known-lists-missing")), 1)

            options = {"faction_file": faction_path, "vanilla_core": vanilla}
            plan = compute_fix(root, "faction-known-lists-missing", options)
            apply_fix(plan)
            data = json.loads(faction_path.read_text(encoding="utf-8"))
            self.assertEqual(data["knownShips"]["hulls"], ["hull1"])
            self.assertEqual(data["knownWeapons"]["weapons"], ["weapon1"])
            self.assertEqual(data["knownFighters"]["fighters"], ["wing1_wing"])
            self.assertNotIn("knownHullMods", data)
            after_scan = scan_mod(root, vanilla_core=vanilla)
            self.assertEqual(_findings(after_scan, "faction-known-lists-missing"), [])

    def test_refuses_on_unresolved_id(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as vanilla_dir:
            root = Path(mod_dir)
            vanilla = Path(vanilla_dir)
            faction_path = root / "data" / "world" / "factions" / "newfac.faction"
            _write(faction_path, '{"id":"newfac","shipRoles":{"role1":{"variant_missing":1}}}')
            options = {"faction_file": faction_path, "vanilla_core": vanilla}
            with self.assertRaises(FixerError):
                compute_fix(root, "faction-known-lists-missing", options)


class ModInfoTriageBannerTests(unittest.TestCase):
    def test_apply_removes_leading_banner_and_rescan_clean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "mod_info.json", '{"id":"fixture","name":"(BROEKN MAYBE) Fixture Mod"}')
            path = root / "mod_info.json"
            before = path.read_bytes()
            plan = compute_fix(root, "mod-info-triage-banner")
            self.assertEqual(path.read_bytes(), before)
            before_scan = scan_mod(root)
            self.assertEqual(len(_findings(before_scan, "mod-info-triage-banner")), 1)
            apply_fix(plan)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["name"], "Fixture Mod")
            after_scan = scan_mod(root)
            self.assertEqual(_findings(after_scan, "mod-info-triage-banner"), [])

    def test_refuses_when_no_leading_banner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "mod_info.json", '{"id":"fixture","name":"Clean Mod Name"}')
            with self.assertRaises(FixerError):
                compute_fix(root, "mod-info-triage-banner")


class UnsupportedFindingTests(unittest.TestCase):
    def test_unsupported_finding_lists_supported_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(FixerError) as ctx:
                compute_fix(root, "not-a-real-finding")
            self.assertIn("wing-data-missing-role-desc-column", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
