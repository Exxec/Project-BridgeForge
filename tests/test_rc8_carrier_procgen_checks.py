from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bridgeforge.models import TargetProfile
from bridgeforge.scanner import scan_mod


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _findings(result, finding_id: str):
    return [item for item in result.findings if item.id == finding_id]


class ProcgenRowChecksTests(unittest.TestCase):
    def test_used_custom_type_missing_row_is_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(
                root / "data" / "config" / "planets.json",
                '{"custom_star":{"isStar":true,"name":"Custom Star"},'
                '"custom_planet":{"isStar":false,"name":"Custom Planet"}}',
            )
            _write(
                root / "src" / "CustomSystem.java",
                'class CustomSystem { void go() { api.addPlanet("x", "custom_planet"); '
                'api.addStar("custom_star"); } }',
            )
            result = scan_mod(root)
            stars = _findings(result, "procgen-star-row-missing")
            planets = _findings(result, "procgen-planet-row-missing")
            self.assertEqual(len(stars), 1)
            self.assertEqual(len(planets), 1)
            self.assertEqual(stars[0].classification, "REVIEW")
            self.assertIn("type:custom_star", stars[0].evidence)
            self.assertIn("vanilla-core:unavailable; vanilla-row exemption could not be checked", stars[0].evidence)

    def test_vanilla_row_exemption_suppresses_finding(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as vanilla_dir:
            root = Path(mod_dir)
            vanilla = Path(vanilla_dir)
            _write(
                root / "data" / "config" / "planets.json",
                '{"star_yellow":{"isStar":true,"name":"Yellow Star"}}',
            )
            _write(root / "src" / "S.java", 'class S { void g() { api.addStar("star_yellow"); } }')
            _write(
                vanilla / "data" / "campaign" / "procgen" / "star_gen_data.csv",
                "id,age\nstar_yellow,ANY\n",
            )
            result = scan_mod(root, vanilla_core=vanilla)
            self.assertEqual(_findings(result, "procgen-star-row-missing"), [])

    def test_mission_only_reference_is_exempt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(
                root / "data" / "config" / "planets.json",
                '{"combat_only_star":{"isStar":true,"name":"Combat Only"}}',
            )
            _write(
                root / "data" / "missions" / "combat1" / "MissionDefinition.java",
                'class MissionDefinition { void createMission() { api.addStar("combat_only_star"); } }',
            )
            result = scan_mod(root)
            self.assertEqual(_findings(result, "procgen-star-row-missing"), [])

    def test_unused_type_is_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(
                root / "data" / "config" / "planets.json",
                '{"unused_star":{"isStar":true,"name":"Unused"}}',
            )
            result = scan_mod(root)
            self.assertEqual(_findings(result, "procgen-star-row-missing"), [])


class FactionKnownListsTests(unittest.TestCase):
    def test_new_faction_missing_known_lists_is_review(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as vanilla_dir:
            root = Path(mod_dir)
            vanilla = Path(vanilla_dir)
            _write(
                root / "data" / "world" / "factions" / "exipirated.faction",
                '{"id":"exipirated","displayName":"Exipirated"}',
            )
            _write(vanilla / "data" / "world" / "factions" / "pirates.faction", '{"id":"pirates"}')
            result = scan_mod(root, vanilla_core=vanilla)
            findings = _findings(result, "faction-known-lists-missing")
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].classification, "REVIEW")
            self.assertIn("missing:knownShips,knownWeapons,knownFighters", findings[0].evidence)

    def test_faction_with_known_lists_present_is_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as vanilla_dir:
            root = Path(mod_dir)
            vanilla = Path(vanilla_dir)
            _write(
                root / "data" / "world" / "factions" / "newfac.faction",
                '{"id":"newfac","knownShips":{"a":1},"knownWeapons":{"b":1},"knownFighters":{"c":1}}',
            )
            _write(vanilla / "data" / "world" / "factions" / "pirates.faction", '{"id":"pirates"}')
            result = scan_mod(root, vanilla_core=vanilla)
            self.assertEqual(_findings(result, "faction-known-lists-missing"), [])

    def test_vanilla_id_merge_fragment_is_exempt(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as vanilla_dir:
            root = Path(mod_dir)
            vanilla = Path(vanilla_dir)
            _write(root / "data" / "world" / "factions" / "pirates_patch.faction", '{"id":"pirates"}')
            _write(vanilla / "data" / "world" / "factions" / "pirates.faction", '{"id":"pirates"}')
            result = scan_mod(root, vanilla_core=vanilla)
            self.assertEqual(_findings(result, "faction-known-lists-missing"), [])


class ShipRolesTests(unittest.TestCase):
    def test_wing_id_key_in_shiproles_is_manual(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(
                root / "data" / "world" / "factions" / "newfac.faction",
                '{"id":"newfac","shipRoles":{"combatSmall":{"includeDefault":true,"talon_wing":5}}}',
            )
            result = scan_mod(root)
            findings = _findings(result, "shiproles-wing-id")
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].classification, "MANUAL")
            self.assertIn("key:talon_wing", findings[0].evidence)

    def test_special_keys_are_not_flagged_as_wing_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(
                root / "data" / "world" / "factions" / "newfac.faction",
                '{"id":"newfac","shipRoles":{"combatSmall":'
                '{"doctrine":1,"includeDefault":true,"fallback":1,"fallback2":1,"gremlin_Strike":5}}}',
            )
            result = scan_mod(root)
            self.assertEqual(_findings(result, "shiproles-wing-id"), [])

    def test_obsolete_fighter_role_block_is_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(
                root / "data" / "world" / "factions" / "newfac.faction",
                '{"id":"newfac","shipRoles":{"fighter":{"includeDefault":true}}}',
            )
            result = scan_mod(root)
            findings = _findings(result, "shiproles-obsolete-fighter-role")
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].evidence, ["role:fighter"])

    def test_current_role_block_name_is_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(
                root / "data" / "world" / "factions" / "newfac.faction",
                '{"id":"newfac","shipRoles":{"combatSmall":{"includeDefault":true}}}',
            )
            result = scan_mod(root)
            self.assertEqual(_findings(result, "shiproles-obsolete-fighter-role"), [])


class CarrierReworkColumnTests(unittest.TestCase):
    def test_ship_data_missing_fighter_bays_column_is_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "data" / "hulls" / "ship_data.csv", "name,id,hints\nDrone,drone_pd,\n")
            result = scan_mod(root)
            findings = _findings(result, "ship-data-missing-fighter-bays-column")
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].classification, "REVIEW")

    def test_ship_data_with_fighter_bays_column_is_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "data" / "hulls" / "ship_data.csv", "name,id,fighter bays,hints\nDrone,drone_pd,,\n")
            result = scan_mod(root)
            self.assertEqual(_findings(result, "ship-data-missing-fighter-bays-column"), [])

    def test_wing_data_missing_role_desc_column_is_manual(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "data" / "hulls" / "wing_data.csv", "id,variant,role,op cost\nfixture_wing,v,FIGHTER,5\n")
            result = scan_mod(root)
            findings = _findings(result, "wing-data-missing-role-desc-column")
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].classification, "MANUAL")

    def test_wing_data_with_role_desc_column_is_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(
                root / "data" / "hulls" / "wing_data.csv",
                "id,variant,role,role desc,op cost\nfixture_wing,v,FIGHTER,Heavy Fighter,5\n",
            )
            result = scan_mod(root)
            self.assertEqual(_findings(result, "wing-data-missing-role-desc-column"), [])

    def test_assault_role_is_valid_in_rc8(self) -> None:
        # RC8's WingRole enum still has ASSAULT (javap, 2026-09-14); it is neither removed nor invalid.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(
                root / "data" / "hulls" / "wing_data.csv",
                "id,variant,role,role desc,op cost\nfixture_wing,v,ASSAULT,Old Role,5\n",
            )
            result = scan_mod(root)
            self.assertEqual(_findings(result, "wing-role-assault-removed"), [])
            self.assertEqual(_findings(result, "fighter-wing-role-invalid"), [])

    def test_fighter_role_is_not_flagged_as_assault(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(
                root / "data" / "hulls" / "wing_data.csv",
                "id,variant,role,role desc,op cost\nfixture_wing,v,FIGHTER,Heavy Fighter,5\n",
            )
            result = scan_mod(root)
            self.assertEqual(_findings(result, "wing-role-assault-removed"), [])

    def test_blank_op_cost_is_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(
                root / "data" / "hulls" / "wing_data.csv",
                "id,variant,role,role desc,op cost\nfixture_wing,v,FIGHTER,Heavy Fighter,\n",
            )
            result = scan_mod(root)
            findings = _findings(result, "wing-op-cost-blank")
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].classification, "REVIEW")

    def test_filled_op_cost_is_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(
                root / "data" / "hulls" / "wing_data.csv",
                "id,variant,role,role desc,op cost\nfixture_wing,v,FIGHTER,Heavy Fighter,8\n",
            )
            result = scan_mod(root)
            self.assertEqual(_findings(result, "wing-op-cost-blank"), [])

    def test_carrier_without_bays_or_wings_is_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "data" / "hulls" / "ship_data.csv", "name,id,fighter bays,hints\nFixture,fixture_hull,,CARRIER\n")
            result = scan_mod(root)
            findings = _findings(result, "carrier-without-bays-or-wings")
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].classification, "REVIEW")
            self.assertIn("hull:fixture_hull", findings[0].evidence)

    def test_carrier_with_variant_wings_is_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "data" / "hulls" / "ship_data.csv", "name,id,fighter bays,hints\nFixture,fixture_hull,,CARRIER\n")
            _write(
                root / "data" / "variants" / "fixture_hull_Pirate.variant",
                '{"hullId":"fixture_hull","wings":["talon_wing","talon_wing"]}',
            )
            result = scan_mod(root)
            self.assertEqual(_findings(result, "carrier-without-bays-or-wings"), [])


class BlackHoleFlagTests(unittest.TestCase):
    def test_black_hole_like_star_without_flag_is_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(
                root / "data" / "config" / "planets.json",
                '{"custom_black_hole":{"isStar":true,"name":"Custom Black Hole"}}',
            )
            result = scan_mod(root)
            findings = _findings(result, "black-hole-type-missing-flag")
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].classification, "REVIEW")

    def test_black_hole_with_flag_set_is_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(
                root / "data" / "config" / "planets.json",
                '{"custom_black_hole":{"isStar":true,"isBlackHole":true,"name":"Custom Black Hole"}}',
            )
            result = scan_mod(root)
            self.assertEqual(_findings(result, "black-hole-type-missing-flag"), [])


class ModInfoAndShadowingTests(unittest.TestCase):
    def test_inexact_game_version_against_rc_target_is_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # A different BASE version is what the launcher rejects (an older RC of 0.98a is accepted).
            _write(root / "mod_info.json", '{"id":"fixture","gameVersion":"0.97a"}')
            result = scan_mod(root, target=TargetProfile("0.98a-RC8"))
            findings = _findings(result, "mod-info-game-version-inexact")
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].classification, "REVIEW")

    def test_exact_game_version_is_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "mod_info.json", '{"id":"fixture","gameVersion":"0.98a-RC8"}')
            result = scan_mod(root, target=TargetProfile("0.98a-RC8"))
            self.assertEqual(_findings(result, "mod-info-game-version-inexact"), [])

    def test_older_rc_of_same_base_version_is_not_flagged(self) -> None:
        # Regression: LazyLib/LunaLib/Console Commands (0.98a-RC5) and MagicLib (0.98a-RC7) all loaded
        # and ran in the RC8 rig, so the launcher matches on the base version, not the RC.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "mod_info.json", '{"id":"fixture","gameVersion":"0.98a-RC5"}')
            result = scan_mod(root, target=TargetProfile("0.98a-RC8"))
            self.assertEqual(_findings(result, "mod-info-game-version-inexact"), [])

    def test_non_rc_target_does_not_trigger_check(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "mod_info.json", '{"id":"fixture","gameVersion":"0.98a-RC7"}')
            result = scan_mod(root)
            self.assertEqual(_findings(result, "mod-info-game-version-inexact"), [])

    def test_shadowed_vanilla_file_with_different_bytes_is_manual(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as vanilla_dir:
            root = Path(mod_dir)
            vanilla = Path(vanilla_dir)
            _write(root / "data" / "hulls" / "shepherd.ship", '{"hullName":"modified"}')
            _write(vanilla / "data" / "hulls" / "shepherd.ship", '{"hullName":"original"}')
            result = scan_mod(root, vanilla_core=vanilla)
            findings = _findings(result, "vanilla-path-shadowing")
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].classification, "MANUAL")

    def test_byte_identical_shadow_is_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as vanilla_dir:
            root = Path(mod_dir)
            vanilla = Path(vanilla_dir)
            _write(root / "data" / "hulls" / "shepherd.ship", '{"hullName":"original"}')
            _write(vanilla / "data" / "hulls" / "shepherd.ship", '{"hullName":"original"}')
            result = scan_mod(root, vanilla_core=vanilla)
            self.assertEqual(_findings(result, "vanilla-path-shadowing"), [])

    def test_total_conversion_shadow_is_downgraded_to_review(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as vanilla_dir:
            root = Path(mod_dir)
            vanilla = Path(vanilla_dir)
            _write(root / "mod_info.json", '{"id":"fixture_tc","totalConversion":true,}')
            _write(root / "data" / "hulls" / "shepherd.ship", '{"hullName":"modified"}')
            _write(vanilla / "data" / "hulls" / "shepherd.ship", '{"hullName":"original"}')
            result = scan_mod(root, vanilla_core=vanilla)
            findings = _findings(result, "vanilla-path-shadowing")
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].classification, "REVIEW")
            self.assertIn("mod_info:totalConversion=true", findings[0].evidence)


class FactionParsingTests(unittest.TestCase):
    def test_trailing_comma_after_root_object_is_parsed_and_checked(self) -> None:
        # Exigency's shipped faction files end with "},": Starsector accepts it, so must BridgeForge.
        with tempfile.TemporaryDirectory() as mod_dir:
            root = Path(mod_dir)
            _write(
                root / "data" / "world" / "factions" / "exipirated.faction",
                '{\n\t"id":"exipirated", # legacy comment\n\t"doctrine":{"warships":3,},\n},\n',
            )
            result = scan_mod(root)
            self.assertEqual(_findings(result, "faction-file-unparsed"), [])
            self.assertEqual(len(_findings(result, "faction-known-lists-missing")), 1)

    def test_unparseable_faction_is_reported_not_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir:
            root = Path(mod_dir)
            _write(root / "data" / "world" / "factions" / "broken.faction", '{"id": "broken", "shipRoles": {')
            result = scan_mod(root)
            findings = _findings(result, "faction-file-unparsed")
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].classification, "UNKNOWN")
            self.assertEqual(findings[0].file, "data/world/factions/broken.faction")


if __name__ == "__main__":
    unittest.main()
