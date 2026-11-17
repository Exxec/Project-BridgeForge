"""False positives found reviving six mods on 0.98.5a (ROADMAP-3 items 92.1 and 92.28, 2026-11-16). Each case keeps
the true positive next to it, so the narrowing cannot hide a real finding."""
from __future__ import annotations

import unittest
from pathlib import Path

from bridgeforge.scan.scanner import scan_mod
from tests.support import resolved_temp_dir

INFO = '{"id":"demo","name":"Demo","version":"1.0","gameVersion":"0.98a-RC8"}'


def _write(path: Path, data: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))


def _ids(mod: Path, core: Path | None = None) -> list[str]:
    return [f.id for f in scan_mod(mod, vanilla_core=core).findings]


def _evidence(mod: Path, core: Path, finding: str) -> list[str]:
    return [e for f in scan_mod(mod, vanilla_core=core).findings if f.id == finding for e in f.evidence]


class FalsePositiveTests(unittest.TestCase):
    def test_a_commented_row_overrides_no_vanilla_row(self) -> None:
        # Musashi Manufactorum: "#Paragon,paragon,..." x17 in ship_data.csv; the loader skips '#'-first rows.
        with resolved_temp_dir() as root:
            mod, core = root / "mod", root / "core"
            _write(core / "data" / "hulls" / "ship_data.csv", "name,id,hitpoints\nParagon,paragon,18000\nAtlas,atlas,3000\n")
            _write(mod / "mod_info.json", INFO)
            _write(mod / "data" / "hulls" / "ship_data.csv", "name,id,hitpoints\n#Paragon,paragon,1\nAtlas,atlas,2900\nMine,mm_mine,900\n")
            evidence = _evidence(mod, core, "csv-vanilla-row-override")
        joined = " ".join(evidence)
        self.assertIn("atlas", joined)  # a live override is still reported
        self.assertNotIn("paragon", joined)

    def test_a_faction_id_starting_with_star_is_not_a_star_type(self) -> None:
        # Navarchy of Tania: setRelationship("star_federation", RepLevel.NEUTRAL) in TaniaGen.
        with resolved_temp_dir() as root:
            mod, core = root / "mod", root / "core"
            _write(core / "data" / "config" / "planets.json", '{"star_yellow": {}}')
            _write(mod / "mod_info.json", INFO)
            _write(mod / "data" / "scripts" / "Gen.java",
                   'class Gen { void g(Object f, Object s) {\n'
                   '  f.setRelationship("star_federation", null);\n'
                   '  s.initStar("x", "star_yellow", 500f, 100f);\n'
                   '  s.initStar("y", "star_purple_ghost", 500f, 100f);\n'
                   '} }\n')
            evidence = _evidence(mod, core, "star-type-undefined")
        joined = " ".join(evidence)
        self.assertIn("star_purple_ghost", joined)  # an undefined star type is still caught
        self.assertNotIn("star_federation", joined)

    def test_a_cp1252_byte_does_not_hide_every_description(self) -> None:
        # Scrapyard Armories: one 0x92 apostrophe (line 57) and ~34 described hulls read as undescribed.
        with resolved_temp_dir() as root:
            mod, core = root / "mod", root / "core"
            core.mkdir()
            _write(mod / "mod_info.json", INFO)
            _write(mod / "data" / "hulls" / "ship_data.csv", "name,id,hitpoints\nKyresh,sa_kyresh,900\nBox,sa_box,800\n")
            _write(mod / "data" / "hulls" / "sa_kyresh.ship", '{"hullId":"sa_kyresh","hullSize":"FRIGATE"}')
            _write(mod / "data" / "hulls" / "sa_box.ship", '{"hullId":"sa_box","hullSize":"FRIGATE"}')
            _write(mod / "data" / "strings" / "descriptions.csv",
                   b"id,type,text1,text2,text3,notes\nsa_kyresh,SHIP,The pilot\x92s choice.,,,\n")
            evidence = _evidence(mod, core, "description-missing")
            ids = _ids(mod, core)
        self.assertIn("hull:sa_box", evidence)  # the genuinely undescribed hull is still reported
        self.assertNotIn("hull:sa_kyresh", evidence)
        self.assertIn("data-file-not-utf8", ids)  # the bad byte is that check's finding


class CallerGuardTests(unittest.TestCase):
    def _mod(self, root: Path, plugin_body: str) -> Path:
        mod = root / "mod"
        _write(mod / "mod_info.json", INFO)
        _write(mod / "data" / "scripts" / "world" / "Gen.java",
               'class Gen { void generate(Object sector) { sector.createStarSystem("Carina"); sector.initStar("carina_system", "star_yellow", 1f, 1f); } }\n')
        _write(mod / "data" / "scripts" / "Plugin.java",
               "class Plugin extends BaseModPlugin {\n  public void onGameLoad(boolean newGame) {\n" + plugin_body + "\n  }\n}\n")
        return mod

    def test_generation_inside_an_existence_check_is_guarded(self) -> None:
        # Navarchy of Tania: ModPlugin_tania.onGameLoad -> if (getEntityById("carina_system") == null) new TaniaGen().generate(...)
        with resolved_temp_dir() as root:
            guarded = self._mod(root / "a", '    if (Global.getSector().getEntityById("carina_system") == null) {\n      new Gen().generate(Global.getSector());\n    }')
            bare = self._mod(root / "b", "    new Gen().generate(Global.getSector());")
            guarded_ids = _ids(guarded)
            bare_evidence = [e for f in scan_mod(bare).findings if f.id == "system-generation-unguarded" for e in f.evidence]
        self.assertNotIn("system-generation-unguarded", guarded_ids)
        self.assertTrue(any("called from onGameLoad" in e for e in bare_evidence))  # the unguarded plugin is still reported


class RootReadmeTests(unittest.TestCase):
    def test_an_unreferenced_root_file_is_a_note_and_a_referenced_one_is_not(self) -> None:
        # Scrapyard Armories: prose "Changelog.json" / "Special Thanks.json" in the mod root (ROADMAP-3 item 92.10).
        with resolved_temp_dir() as root:
            mod = root / "mod"
            _write(mod / "mod_info.json", INFO)
            _write(mod / "Changelog.json", "0.0.19 Added a ship\n")
            _write(mod / "Settings.json", "not json either\n")
            _write(mod / "data" / "scripts" / "Plugin.java", 'class P { Object o = loadJSON("Settings.json"); }\n')
            _write(mod / "Special Thanks.json", "Thanks to\nGJdude for the sprite\n")
            found: dict[str, set[str]] = {}
            readme: dict[str, bool] = {}
            for f in scan_mod(mod).findings:
                if f.file in ("Changelog.json", "Special Thanks.json", "Settings.json"):
                    found.setdefault(f.file, set()).add(f.classification)
                    readme[f.file] = readme.get(f.file, False) or "root-file-unreferenced" in (f.evidence or [])
        self.assertEqual(found["Changelog.json"], {"SAFE"})
        self.assertEqual(found["Special Thanks.json"], {"SAFE"})  # json-content-after-root (REVIEW) demoted too
        self.assertTrue(readme["Special Thanks.json"])
        self.assertFalse(readme["Settings.json"])  # the mod's own code reads it, so it keeps its own classification


if __name__ == "__main__":
    unittest.main()
