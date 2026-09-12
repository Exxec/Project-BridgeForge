from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bridgeforge.scanner import scan_mod


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _findings(result, finding_id: str):
    return [item for item in result.findings if item.id == finding_id]


class DataClassReferenceMissingTests(unittest.TestCase):
    def test_modplugin_missing_class_is_manual_critical(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(
                root / "mod_info.json",
                '{"id":"demo","name":"Demo","version":"1.0","gameVersion":"0.98a-RC8",'
                '"modPlugin":"data.scripts.DemoModPlugin"}',
            )
            result = scan_mod(root)
            hits = _findings(result, "data-class-reference-missing")
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0].classification, "MANUAL")
            self.assertEqual(hits[0].severity, "critical")
            self.assertIn("class:data.scripts.DemoModPlugin", hits[0].evidence)

    def test_modplugin_resolves_against_mod_jar(self) -> None:
        import zipfile

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(
                root / "mod_info.json",
                '{"id":"demo","name":"Demo","version":"1.0","gameVersion":"0.98a-RC8",'
                '"jars":["jars/demo.jar"],"modPlugin":"data.scripts.DemoModPlugin"}',
            )
            jar_path = root / "jars" / "demo.jar"
            jar_path.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(jar_path, "w") as archive:
                archive.writestr("data/scripts/DemoModPlugin.class", b"\xca\xfe\xba\xbe\x00\x00\x00\x41")
            result = scan_mod(root)
            self.assertEqual(_findings(result, "data-class-reference-missing"), [])

    def test_commented_csv_row_does_not_fire(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(
                root / "data" / "config" / "radar" / "combat_radar_plugins.csv",
                "renderer id,render order,script,settings file (optional)\n"
                "#exigency_RepulsorRenderer,45,data.scripts.radar.exigency_RepulsorRenderer,foo.json\n",
            )
            # combat_radar_plugins.csv is not part of the checked source list itself, but the
            # equivalent commented-row skip is exercised via hull_mods.csv below.
            _write(
                root / "data" / "hullmods" / "hull_mods.csv",
                "name,id,unlocked,hidden,cost_frigate,cost_dest,cost_cruiser,cost_capital,script,desc,sprite\n"
                "#Disabled,disabled_hm,TRUE,,0,0,0,0,data.scripts.hullmods.MissingScript,,\n",
            )
            result = scan_mod(root)
            self.assertEqual(_findings(result, "data-class-reference-missing"), [])

    def test_external_library_package_is_unknown_not_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(
                root / "data" / "hullmods" / "hull_mods.csv",
                "name,id,unlocked,hidden,cost_frigate,cost_dest,cost_cruiser,cost_capital,script,desc,sprite\n"
                "Magic,magic_hm,TRUE,,0,0,0,0,org.lazywizard.lazylib.MagicStub,,\n",
            )
            result = scan_mod(root)
            hits = _findings(result, "data-class-reference-missing")
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0].classification, "UNKNOWN")
            self.assertIn("external dependency, unverified", hits[0].evidence)

    def test_vanilla_namespace_reference_without_vanilla_core_is_unknown_not_manual(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(
                root / "data" / "config" / "settings.json",
                '{"plugins":{"newGameDialogPlugin":"com.fs.starfarer.api.impl.campaign.NewGameDialogPluginImpl"}}',
            )
            result = scan_mod(root)
            hits = _findings(result, "data-class-reference-missing")
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0].classification, "UNKNOWN")
            self.assertIn("vanilla class, unverified (no vanilla core supplied)", hits[0].evidence)

    def test_rule_command_resolves_via_vanilla_rulecmd_subpackage(self) -> None:
        # Regression: vanilla keeps rule commands in sub-packages (rulecmd.salvage.AddBarEvent); a bare
        # rules.csv command was expanded only to rulecmd.<Name> and falsely flagged (Legacy of Arkgneisis).
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as vanilla_dir:
            root = Path(mod_dir)
            vanilla = Path(vanilla_dir)
            _write(
                vanilla / "data" / "campaign" / "rulecmd" / "AddBarEvent.java",
                "package com.fs.starfarer.api.impl.campaign.rulecmd.salvage;\npublic class AddBarEvent {}\n",
            )
            _write(
                root / "data" / "campaign" / "rules.csv",
                "id,trigger,conditions,script,text,options,notes\n"
                "fixtureBar,OpenInteractionDialog,,AddBarEvent,,,\n"
                "fixtureMissing,OpenInteractionDialog,,TotallyMissingCmd,,,\n",
            )
            result = scan_mod(root, vanilla_core=vanilla)
            flagged = [hit for hit in _findings(result, "data-class-reference-missing") if hit.file.endswith("rules.csv")]
            classes = [item for hit in flagged for item in hit.evidence if item.startswith("class:")]
            self.assertFalse(any(item.endswith(".AddBarEvent") for item in classes))
            self.assertTrue(any(item.endswith(".TotallyMissingCmd") for item in classes))

    def test_vanilla_namespace_reference_resolves_with_vanilla_core(self) -> None:
        import zipfile

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vanilla_root = Path(directory) / "vanilla-core"
            _write(
                root / "data" / "config" / "settings.json",
                '{"plugins":{"newGameDialogPlugin":"com.fs.starfarer.api.impl.campaign.NewGameDialogPluginImpl"}}',
            )
            jar_path = vanilla_root / "starfarer_obf.jar"
            jar_path.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(jar_path, "w") as archive:
                archive.writestr(
                    "com/fs/starfarer/api/impl/campaign/NewGameDialogPluginImpl.class",
                    b"\xca\xfe\xba\xbe\x00\x00\x00\x41",
                )
            result = scan_mod(root, vanilla_core=vanilla_root)
            self.assertEqual(_findings(result, "data-class-reference-missing"), [])

    def test_ship_system_stats_script_resolves_against_vanilla_loose_script(self) -> None:
        """A .system statsScript pointing at a vanilla LOOSE script outside data/scripts must resolve.

        Regression for SEEKER's SKR_drone_sensor.system, which names
        data.shipsystems.scripts.SensorDroneStats; vanilla ships that class as a loose .java under
        starsector-core/data/shipsystems/scripts/, not under data/scripts/.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vanilla_root = Path(directory) / "vanilla-core"
            _write(
                root / "data" / "shipsystems" / "demo.system",
                '{"statsScript":"data.shipsystems.scripts.SensorDroneStats"}',
            )
            _write(
                vanilla_root / "data" / "shipsystems" / "scripts" / "SensorDroneStats.java",
                "package data.shipsystems.scripts;\n\npublic class SensorDroneStats {}\n",
            )
            result = scan_mod(root, vanilla_core=vanilla_root)
            self.assertEqual(_findings(result, "data-class-reference-missing"), [])

    def test_settings_json_plugin_missing_class(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(
                root / "data" / "config" / "settings.json",
                '{"plugins":{"demo_plugin":"data.scripts.plugins.MissingPlugin"}}',
            )
            result = scan_mod(root)
            hits = _findings(result, "data-class-reference-missing")
            self.assertEqual(len(hits), 1)
            self.assertIn("field:plugins.demo_plugin", hits[0].evidence)


class HardcodedHyperspaceCoordinatesTests(unittest.TestCase):
    def _many_waypoints(self) -> str:
        lines = ["class Waypoints {", "  void go(SectorEntityToken e) {", "    e.getLocationInHyperspace();"]
        for index in range(29):
            lines.append(f"    Vector2f p{index} = new Vector2f({1000 + index}f, {-2000 - index}f);")
        lines.append("  }")
        lines.append("}")
        return "\n".join(lines)

    def test_many_literal_pairs_in_hyperspace_class_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "data" / "scripts" / "world" / "Waypoints.java", self._many_waypoints())
            result = scan_mod(root)
            hits = _findings(result, "hardcoded-hyperspace-coordinates")
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0].classification, "REVIEW")
            self.assertTrue(any("total_coordinate_pairs:29" in item for item in hits[0].evidence))

    def test_non_hyperspace_class_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            text = "class NotHyperspace {\n" + "\n".join(
                f"  Vector2f p{i} = new Vector2f({i}f, {i}f);" for i in range(10)
            ) + "\n}\n"
            _write(root / "data" / "scripts" / "world" / "NotHyperspace.java", text)
            result = scan_mod(root)
            self.assertEqual(_findings(result, "hardcoded-hyperspace-coordinates"), [])

    def test_commented_out_coordinates_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lines = ["class Waypoints {", "  void go() { getHyperspace(); }", "  /*"]
            for index in range(29):
                lines.append(f"  Vector2f p{index} = new Vector2f({index}f, {index}f);")
            lines.append("  */")
            lines.append("}")
            _write(root / "data" / "scripts" / "world" / "Waypoints.java", "\n".join(lines))
            result = scan_mod(root)
            self.assertEqual(_findings(result, "hardcoded-hyperspace-coordinates"), [])


class HardcodedTerrainGridSizeTests(unittest.TestCase):
    def test_literal_mask_division_near_get_tiles_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            text = (
                "class Tasserus {\n"
                "  void removePNGFromNebula(TerrainMask mask) {\n"
                "    int[][] tiles = mask.getTiles();\n"
                "    int index = someValue % 260;\n"
                "  }\n"
                "}\n"
            )
            _write(root / "data" / "scripts" / "world" / "Tasserus.java", text)
            result = scan_mod(root)
            hits = _findings(result, "hardcoded-terrain-grid-size")
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0].classification, "REVIEW")
            self.assertIn("literal:260", hits[0].evidence)

    def test_fixed_via_get_tile_center_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            text = (
                "class Tasserus {\n"
                "  void removePNGFromNebula(TerrainMask mask) {\n"
                "    int[][] tiles = mask.getTiles();\n"
                "    Vector2f center = mask.getTileCenter(someValue);\n"
                "  }\n"
                "}\n"
            )
            _write(root / "data" / "scripts" / "world" / "Tasserus.java", text)
            result = scan_mod(root)
            self.assertEqual(_findings(result, "hardcoded-terrain-grid-size"), [])


if __name__ == "__main__":
    unittest.main()
