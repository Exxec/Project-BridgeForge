"""94.G2 slice 20, owner 2026-11-23 ("Separate, needed"): a part a gene shares with other donor content is a need, not a member.

A hull style (RC8_BEHAVIOUR RC8-49) travels as `needs.donor`: a carrier gets a copy, the subtraction copy keeps it. A custom
start's starting ship is a gene the start needs. Synthetic fixtures only.
"""
from __future__ import annotations

import json
import unittest

from bridgeforge.genome.carrier_load import HULL_STYLES
from bridgeforge.genome.gene import CUSTOM_STARTS_FILE, describe, validate
from bridgeforge.genome.gene_set import prove_set
from bridgeforge.genome.proof import prove
from tests.support import resolved_temp_dir, write_text as _write

STYLE = {"slotCoverSmallTurret": "graphics/covers/fx_small.png", "damageDecalSheet": "graphics/damage/decals.png",
         "shieldRingColor": [1, 2, 3, 255]}


def _core(root):
    core = root / "core"
    _write(core / HULL_STYLES, json.dumps({"LOW_TECH": {"damageDecalSheet": "graphics/damage/decals.png"}}))
    _write(core / "graphics" / "damage" / "decals.png", "png")
    _write(core / "data" / "hulls" / "ship_data.csv", "name,id\n")
    _write(core / "data" / "hullmods" / "hull_mods.csv", "name,id\n")
    return core


def _mod(root, *, shared: bool = True, style: str = "FX_STYLE"):
    """fx_ship uses `style`; with `shared`, fx_other (outside fx_ship's gene) uses it too."""
    mod = root / "mod"
    _write(mod / "mod_info.json", json.dumps({"id": "demomod", "name": "Demo", "version": "1.0", "gameVersion": "0.98.5a-RC7"}))
    _write(mod / "data" / "hulls" / "ship_data.csv", "name,id\nShip,fx_ship\nOther,fx_other\n")
    _write(mod / "data" / "hulls" / "fx_ship.ship", json.dumps({"hullId": "fx_ship", "style": style}))
    _write(mod / "data" / "hulls" / "fx_other.ship", json.dumps({"hullId": "fx_other", "style": "FX_STYLE" if shared else "LOW_TECH"}))
    _write(mod / HULL_STYLES, json.dumps({"FX_STYLE": STYLE}))
    _write(mod / "graphics" / "covers" / "fx_small.png", "png")
    return mod


class StyleNeedTests(unittest.TestCase):
    def test_a_shared_style_and_its_own_files_are_donor_needs_not_members(self) -> None:
        with resolved_temp_dir() as root:
            gene = describe(_mod(root), "hull:fx_ship", vanilla_core=_core(root))
        self.assertEqual(validate(gene), [])
        self.assertEqual(gene["needs"]["donor"], ["data/config/hull_styles.json#/FX_STYLE", "graphics/covers/fx_small.png"])
        self.assertNotIn(HULL_STYLES, [m["path"].split("#")[0] for m in gene["members"]])  # the core's decals.png is not a need
        self.assertFalse([s for s in gene["unknowns"]["suspects"] if s["path"].startswith(HULL_STYLES)])

    def test_a_style_only_this_gene_uses_is_kept_a_need_and_flagged(self) -> None:
        with resolved_temp_dir() as root:
            gene = describe(_mod(root, shared=False), "hull:fx_ship", vanilla_core=_core(root))
        self.assertIn("data/config/hull_styles.json#/FX_STYLE", gene["needs"]["donor"])
        self.assertTrue([s for s in gene["unknowns"]["suspects"] if s["path"] == "data/config/hull_styles.json#/FX_STYLE"])

    def test_a_vanilla_style_needs_nothing_and_an_undefined_one_is_missing(self) -> None:
        with resolved_temp_dir() as root:
            vanilla = describe(_mod(root, style="LOW_TECH"), "hull:fx_ship", vanilla_core=_core(root))
        with resolved_temp_dir() as root:
            nowhere = describe(_mod(root, style="NOWHERE"), "hull:fx_ship", vanilla_core=_core(root))
        self.assertNotIn("donor", vanilla["needs"])  # absent, so earlier manifests stay byte-identical
        self.assertFalse([m for m in vanilla["unknowns"]["missing"] if m.startswith("hull style")])  # the core defines it
        self.assertTrue([m for m in nowhere["unknowns"]["missing"] if m.startswith("hull style NOWHERE")])

    def test_a_malformed_donor_list_fails_validation(self) -> None:
        with resolved_temp_dir() as root:
            gene = describe(_mod(root), "hull:fx_ship", vanilla_core=_core(root))
        self.assertIn("needs.donor, when present, is a list of member paths (slice 20)",
                      validate({**gene, "needs": {**gene["needs"], "donor": [1, ""]}}))

    def test_the_carrier_gets_the_style_the_subtraction_keeps_it_and_the_proof_reads_it_as_an_input(self) -> None:
        with resolved_temp_dir() as root:
            out = root / "proofs"
            result = prove(_mod(root), "hull:fx_ship", out, vanilla_core=_core(root))
            carried = json.loads((out / "work" / "carrier" / HULL_STYLES).read_text(encoding="utf-8"))
            cover = (out / "work" / "carrier" / "graphics" / "covers" / "fx_small.png").is_file()
            kept = json.loads((out / "work" / "subtraction" / HULL_STYLES).read_text(encoding="utf-8"))
            isolation = json.loads((out / "isolation-proof.json").read_text(encoding="utf-8"))
        self.assertEqual(carried, {"FX_STYLE": STYLE})
        self.assertTrue(cover)
        self.assertIn("FX_STYLE", kept)  # still used by fx_other in the donor
        self.assertEqual((isolation["load_gaps"], result["verdicts"]["isolation-proof"]), ([], "PASS"))
        self.assertIn(("need", HULL_STYLES), [(i["role"], i["path"]) for i in isolation["inputs"]])

    def test_a_set_carrier_unites_its_genes_donor_needs(self) -> None:
        with resolved_temp_dir() as root:
            result = prove_set(_mod(root), "hull:fx_ship", root / "set", vanilla_core=_core(root), quiet=True)
            carried = json.loads((root / "set" / "work" / "carrier" / HULL_STYLES).read_text(encoding="utf-8"))
        self.assertEqual((result["verdict"], result["load_gaps"]), ("PASS", 0))
        self.assertIn("FX_STYLE", carried)


START = """package data.scripts;
public class demo_Start {
    void execute() {
        String ship = "demo_flagship_Var1";
    }
}
"""


class StartShipTests(unittest.TestCase):
    def test_a_start_s_ship_is_a_gene_it_needs_which_its_set_carries(self) -> None:
        with resolved_temp_dir() as root:
            mod = root / "mod"
            _write(mod / "mod_info.json", json.dumps({"id": "demomod", "name": "Demo", "version": "1.0", "gameVersion": "0.98.5a-RC7"}))
            _write(mod / CUSTOM_STARTS_FILE, '{"starts":[{"id":"demoStart","name":"D","desc":"d","className":"data.scripts.demo_Start"}]}')
            _write(mod / "data" / "scripts" / "demo_Start.java", START)
            _write(mod / "data" / "variants" / "demo_flagship_Var1.variant",
                   json.dumps({"variantId": "demo_flagship_Var1", "hullId": "demo_flagship"}))
            _write(mod / "data" / "hulls" / "ship_data.csv", "name,id\nFlagship,demo_flagship\n")
            core = _core(root)
            single = prove(mod, "custom-start:demoStart", root / "single", vanilla_core=core)
            subtracted_variant = (root / "single" / "work" / "subtraction" / "data" / "variants" / "demo_flagship_Var1.variant").is_file()
            result = prove_set(mod, "custom-start:demoStart", root / "set", vanilla_core=core, quiet=True)
            set_variant = (root / "set" / "work" / "carrier" / "data" / "variants" / "demo_flagship_Var1.variant").is_file()
        self.assertTrue(subtracted_variant)  # removing the start leaves the ship in the donor
        self.assertEqual(single["verdicts"]["subtraction-proof"], "PASS")
        self.assertTrue(set_variant)         # the set carrier carries the ship gene the start needs
        self.assertGreaterEqual(result["carried"], 2)


if __name__ == "__main__":
    unittest.main()
