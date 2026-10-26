"""mission-map-reference-missing (item 73 F5): a mission map's background image or planet type that nothing defines."""
from __future__ import annotations

import unittest
from pathlib import Path

from bridgeforge.scan.scan_mission_map import mission_map_references
from bridgeforge.scan.scanner import scan_mod
from tests.support import resolved_temp_dir

SOURCE = """package data.missions.demo;
public class MissionDefinition {
    public void defineMission(MissionDefinitionAPI api) {
        api.setBackgroundSpriteName("graphics/demo/bg.png");
        api.addPlanet(0, 0, 200f, "wormholeA", 0f, true);
        api.addPlanet(0, 0, 100f, "star_yellow", 300f, true);
        api.addNebula(0, 0, 500);
        // api.setBackgroundSpriteName("graphics/demo/commented.png");
    }
}
"""


def _fixture(base: Path, with_background: bool, with_type: bool):
    mod, core = base / "mod", base / "core"
    (mod / "data" / "missions" / "demo").mkdir(parents=True)
    (core / "data" / "config").mkdir(parents=True)
    (mod / "mod_info.json").write_text('{"id":"demo","name":"Demo","version":"1","gameVersion":"0.98a-RC8"}', encoding="utf-8")
    (mod / "data" / "missions" / "demo" / "MissionDefinition.java").write_text(SOURCE, encoding="utf-8")
    (core / "data" / "config" / "planets.json").write_text('{"star_yellow":{}}', encoding="utf-8")
    if with_background:
        (mod / "graphics" / "demo").mkdir(parents=True)
        (mod / "graphics" / "demo" / "bg.png").write_bytes(b"png")
    if with_type:
        (mod / "data" / "config").mkdir(parents=True)
        (mod / "data" / "config" / "planets.json").write_text('{"wormholeA":{}}', encoding="utf-8")
    return mod, core


def _hits(mod: Path, core: Path | None):
    return [f for f in scan_mod(mod, vanilla_core=core).findings if f.id == "mission-map-reference-missing"]


class MissionMapReferenceTests(unittest.TestCase):
    def test_references_are_read_without_nebulas_or_comments(self) -> None:
        from bridgeforge.scan.scanner import _blank_java_comments

        refs = mission_map_references(_blank_java_comments(SOURCE))
        self.assertEqual(refs, [("background", "graphics/demo/bg.png"), ("planet-type", "wormholeA"), ("planet-type", "star_yellow")])

    def test_missing_background_and_planet_type_are_flagged(self) -> None:
        with resolved_temp_dir() as base:
            mod, core = _fixture(Path(base), with_background=False, with_type=False)
            evidence = [e for f in _hits(mod, core) for e in f.evidence]
        self.assertIn("background:graphics/demo/bg.png", evidence)
        self.assertIn("planet-type:wormholeA", evidence)
        self.assertNotIn("planet-type:star_yellow", evidence)

    def test_defined_background_and_type_are_quiet(self) -> None:
        with resolved_temp_dir() as base:
            mod, core = _fixture(Path(base), with_background=True, with_type=True)
            self.assertEqual(_hits(mod, core), [])

    def test_without_vanilla_core_nothing_is_claimed(self) -> None:
        with resolved_temp_dir() as base:
            mod, _ = _fixture(Path(base), with_background=False, with_type=False)
            self.assertEqual(_hits(mod, None), [])


if __name__ == "__main__":
    unittest.main()
