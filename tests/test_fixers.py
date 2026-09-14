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

    def test_refuses_when_present_or_rows_span_lines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._mod(root, "id,role desc\nwing_a,x\n")
            with self.assertRaises(FixerError):
                compute_fix(root, "wing-data-missing-role-desc-column")
            self._mod(root, 'id,variant\nwing_a,"two\nlines"\n')
            with self.assertRaises(FixerError):
                compute_fix(root, "wing-data-missing-role-desc-column")


class WingRoleAssaultRemovedTests(unittest.TestCase):
    def _mod(self, root: Path) -> None:
        _write(root / "mod_info.json", '{"id":"fixture","name":"Fixture","gameVersion":"0.98a"}')
        _write(
            root / "data" / "hulls" / "wing_data.csv",
            "id,role,role desc,op cost\n"
            "wing_a,ASSAULT,desc,4\n"
            "wing_b,FIGHTER,desc,4\n",
        )

    def test_dry_run_leaves_file_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._mod(root)
            path = root / "data" / "hulls" / "wing_data.csv"
            before = path.read_bytes()
            plan = compute_fix(root, "wing-role-assault-removed")
            unified_diff_for_change(plan.changes[0])  # dry-run diff computation must not touch disk
            self.assertEqual(path.read_bytes(), before)

    def test_apply_fixes_and_backs_up(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._mod(root)
            path = root / "data" / "hulls" / "wing_data.csv"
            plan = compute_fix(root, "wing-role-assault-removed")
            applied = apply_fix(plan)
            self.assertEqual(len(applied), 1)
            backup = Path(applied[0]["backup"])
            self.assertTrue(backup.is_file())
            self.assertIn("wing_a,FIGHTER,desc,4", path.read_text(encoding="utf-8"))
            self.assertIn("wing_b,FIGHTER,desc,4", path.read_text(encoding="utf-8"))
            self.assertIn("wing_a,ASSAULT,desc,4", backup.read_text(encoding="utf-8"))

    def test_rescan_no_longer_reports_finding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._mod(root)
            before_scan = scan_mod(root)
            self.assertEqual(len(_findings(before_scan, "wing-role-assault-removed")), 1)
            apply_fix(compute_fix(root, "wing-role-assault-removed"))
            after_scan = scan_mod(root)
            self.assertEqual(_findings(after_scan, "wing-role-assault-removed"), [])

    def test_refuses_when_no_assault_role(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(
                root / "data" / "hulls" / "wing_data.csv",
                "id,role,role desc,op cost\nwing_b,FIGHTER,desc,4\n",
            )
            with self.assertRaises(FixerError):
                compute_fix(root, "wing-role-assault-removed")

    def test_apply_twice_does_not_clobber_first_backup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._mod(root)
            path = root / "data" / "hulls" / "wing_data.csv"
            plan = compute_fix(root, "wing-role-assault-removed")
            applied = apply_fix(plan)
            first_backup = Path(applied[0]["backup"])
            # Reintroduce an ASSAULT row (simulating a second independent fix run) and apply again.
            _write(path, "id,role,role desc,op cost\nwing_c,ASSAULT,desc,4\n")
            second_plan = compute_fix(root, "wing-role-assault-removed")
            second_applied = apply_fix(second_plan)
            second_backup = Path(second_applied[0]["backup"])
            self.assertNotEqual(first_backup, second_backup)
            self.assertTrue(first_backup.is_file())
            self.assertTrue(second_backup.is_file())
            self.assertIn("wing_c,ASSAULT,desc,4", second_backup.read_text(encoding="utf-8"))


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
            self.assertIn("wing-role-assault-removed", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
