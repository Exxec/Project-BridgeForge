"""94.G2 slice 19: what a carrier must hold for the game to load it (RC8-49). Synthetic fixtures only.

P2's and P3's carriers passed static isolation and were Fatal at load on undefined hull styles (P2B-CAR-20261122,
P3B-CAR-20261122); with the styles added, P3's went on to a missing cover image (DIAG-P3-STYLES-20261123).
"""
from __future__ import annotations

import json
import unittest

from bridgeforge.genome.carrier_load import HULL_STYLES, files_named, load_gaps
from bridgeforge.genome.proof import prove
from tests.support import resolved_temp_dir, write_text as _write

STYLE = {"slotCoverSmallTurret": "graphics/covers/small.png", "slotCoverLargeTurret": "graphics/covers/large.png",
         "damageDecalSheet": "graphics/damage/decals.png", "shieldRingColor": [1, 2, 3, 255], "hyperspaceJitterColor": "#ff00ff"}


def _core(root):
    core = root / "core"
    _write(core / HULL_STYLES, json.dumps({"LOW_TECH": {"damageDecalSheet": "graphics/damage/decals.png"}}))
    _write(core / "graphics" / "damage" / "decals.png", "png")
    _write(core / "data" / "hulls" / "ship_data.csv", "name,id\n")
    _write(core / "data" / "hullmods" / "hull_mods.csv", "name,id\n")
    return core


class LoadGapTests(unittest.TestCase):
    def test_a_hull_whose_style_nothing_defines_is_a_gap_and_a_defined_one_is_not(self) -> None:
        with resolved_temp_dir() as root:
            carrier = root / "carrier"
            _write(carrier / "data" / "hulls" / "a.ship", json.dumps({"hullId": "a", "style": "FX_STYLE"}))
            _write(carrier / "data" / "hulls" / "b.ship", json.dumps({"hullId": "b", "style": "LOW_TECH"}))  # the core's
            _write(carrier / "data" / "hulls" / "skins" / "c.skin", json.dumps({"skinHullId": "c", "style": "SKIN_STYLE"}))
            gaps = load_gaps(carrier, _core(root))
        self.assertEqual([(g["finding"], g["file"], g["style"]) for g in gaps],
                         [("hull-style-undefined", "data/hulls/a.ship", "FX_STYLE"),
                          ("hull-style-undefined", "data/hulls/skins/c.skin", "SKIN_STYLE")])

    def test_every_file_a_carried_style_names_must_exist_and_all_missing_ones_are_listed(self) -> None:
        with resolved_temp_dir() as root:
            carrier = root / "carrier"
            _write(carrier / "data" / "hulls" / "a.ship", json.dumps({"hullId": "a", "style": "FX_STYLE"}))
            _write(carrier / HULL_STYLES, json.dumps({"FX_STYLE": STYLE}))
            _write(carrier / "graphics" / "covers" / "small.png", "png")  # in the carrier; decals.png is the core's
            gaps = load_gaps(carrier, _core(root))
        self.assertEqual(gaps, [{"finding": "hull-style-file-missing", "file": HULL_STYLES, "style": "FX_STYLE",
                                 "path": "graphics/covers/large.png"}])

    def test_a_declared_dependency_s_styles_and_files_count_and_unreadable_files_are_their_own_gaps(self) -> None:
        # Review of slice 19: a library the carrier depends on merges its styles too; a broken file is not an undefined style.
        with resolved_temp_dir() as root:
            carrier, library = root / "carrier", root / "library"
            _write(library / HULL_STYLES, json.dumps({"LIB_STYLE": {"slotCoverSmallTurret": "graphics/lib/c.png"}}))
            _write(library / "graphics" / "lib" / "c.png", "png")
            _write(carrier / "data" / "hulls" / "a.ship", json.dumps({"hullId": "a", "style": "LIB_STYLE"}))
            _write(carrier / "data" / "hulls" / "plain.ship", json.dumps({"hullId": "plain"}))  # no style: nothing to check
            _write(carrier / "data" / "hulls" / "broken.ship", "{not json")
            _write(carrier / HULL_STYLES, json.dumps({"OWN": {"slotCoverLargeTurret": "/graphics/lib/c.png",
                                                              "slotCoverSmallTurret": "graphics\\LIB\\D.PNG",
                                                              "damageDecalSheet": "../outside.png"}}))
            core = _core(root)
            with_library = load_gaps(carrier, core, [library])
            without = load_gaps(carrier, core)
            (carrier / HULL_STYLES).write_text("[1, 2]", encoding="utf-8")
            unreadable = load_gaps(carrier, core, [library])
        self.assertEqual(sorted((g["finding"], g.get("style"), g.get("path")) for g in with_library),
                         [("hull-file-unreadable", None, None),
                          ("hull-style-file-missing", "OWN", "../outside.png"),    # never looked up outside the folders
                          ("hull-style-file-missing", "OWN", "graphics/LIB/D.PNG")])  # a backslash and an upper-case suffix
        self.assertIn(("hull-style-undefined", "LIB_STYLE"), [(g["finding"], g.get("style")) for g in without])
        self.assertIn("hull-styles-unreadable", [g["finding"] for g in unreadable])

    def test_a_style_names_only_its_image_and_sound_files(self) -> None:
        nested = {"a": {"b": ["graphics/x/one.png", "sounds/two.ogg"]}, "c": "LOW_TECH", "d": "#ffffff", "e": "notes/readme.txt"}
        self.assertEqual(files_named(nested), ["graphics/x/one.png", "sounds/two.ogg"])
        self.assertEqual(files_named({**STYLE}), ["graphics/covers/large.png", "graphics/covers/small.png",
                                                  "graphics/damage/decals.png"])


def _styled_hull_mod(root):
    mod = root / "mod"
    _write(mod / "mod_info.json", json.dumps({"id": "demomod", "name": "Demo", "version": "1.0", "gameVersion": "0.98.5a-RC7"}))
    _write(mod / "data" / "hulls" / "ship_data.csv", "name,id\nShip,fx_ship\n")
    _write(mod / "data" / "hulls" / "fx_ship.ship", json.dumps({"hullId": "fx_ship", "style": "FX_STYLE"}))
    _write(mod / HULL_STYLES, json.dumps({"FX_STYLE": {"shieldRingColor": [1, 2, 3, 255]}}))
    return mod


class ProofTests(unittest.TestCase):
    def test_a_gene_set_whose_carrier_lacks_a_style_fails(self) -> None:
        from bridgeforge.genome.gene_set import prove_set

        with resolved_temp_dir() as root:
            result = prove_set(_styled_hull_mod(root), "hull:fx_ship", root / "set", vanilla_core=_core(root), quiet=True)
            proof = json.loads((root / "set" / "set-isolation-proof.json").read_text(encoding="utf-8"))
        self.assertEqual((result["verdict"], result["load_gaps"]), ("FAIL", 1))
        self.assertEqual(proof["load_gaps"][0]["finding"], "hull-style-undefined")

    def test_a_hull_gene_whose_style_the_carrier_lacks_fails_isolation(self) -> None:
        with resolved_temp_dir() as root:
            mod = _styled_hull_mod(root)
            prove(mod, "hull:fx_ship", root / "proofs", vanilla_core=_core(root))
            isolation = json.loads((root / "proofs" / "isolation-proof.json").read_text(encoding="utf-8"))
        self.assertEqual(isolation["verdict"], "FAIL")
        self.assertEqual([(g["finding"], g["style"]) for g in isolation["load_gaps"]], [("hull-style-undefined", "FX_STYLE")])

    def test_without_a_core_the_check_does_not_run_and_a_vanilla_styled_hull_still_passes(self) -> None:
        # Review of slice 19: without the core every vanilla style would read as undefined.
        with resolved_temp_dir() as root:
            mod = root / "mod"
            _write(mod / "mod_info.json", json.dumps({"id": "demomod", "name": "Demo", "version": "1.0", "gameVersion": "0.98.5a-RC7"}))
            _write(mod / "data" / "hulls" / "ship_data.csv", "name,id\nShip,fx_ship\n")
            _write(mod / "data" / "hulls" / "fx_ship.ship", json.dumps({"hullId": "fx_ship", "style": "LOW_TECH"}))
            prove(mod, "hull:fx_ship", root / "no-core")
            prove(mod, "hull:fx_ship", root / "with-core", vanilla_core=_core(root))
            no_core = json.loads((root / "no-core" / "isolation-proof.json").read_text(encoding="utf-8"))
            with_core = json.loads((root / "with-core" / "isolation-proof.json").read_text(encoding="utf-8"))
        self.assertTrue(no_core["load_gaps"].startswith("NOT_RUN"))
        self.assertEqual((with_core["load_gaps"], with_core["verdict"]), ([], "PASS"))


if __name__ == "__main__":
    unittest.main()
