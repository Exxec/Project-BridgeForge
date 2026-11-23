"""94.G2 slice 21: images the game derives from a phase hull's sprite (RC8_BEHAVIOUR RC8-51). Synthetic fixtures only."""
from __future__ import annotations

import json
import unittest

from bridgeforge.genome.carrier_load import load_gaps
from bridgeforge.genome.gene import describe
from bridgeforge.genome.proof import prove
from bridgeforge.phase_sprites import hull_facts, is_phase, light_index, phase_sprite_paths, phase_systems
from bridgeforge.vendor_plan import vendor_plan
from tests.support import resolved_temp_dir, write_text as _write

HULLS = "name,id,system id,defense id,shield type,hints\n"
PHASECLOAK = {"id": "phasecloak", "type": "PHASE_CLOAK", "phaseHighlight": "_glow1", "phaseDiffuse": "_glow2"}


def _core(root, *, glows: bool = True):
    core = root / "core"
    _write(core / "data" / "config" / "hull_styles.json", json.dumps({"LOW_TECH": {}}))
    _write(core / "data" / "hulls" / "ship_data.csv", HULLS + "Afflictor,afflictor,emp,phasecloak,PHASE,\n")
    _write(core / "data" / "hulls" / "afflictor.ship", json.dumps({"hullId": "afflictor", "style": "LOW_TECH",
                                                                  "spriteName": "graphics/ships/phase/afflictor.png"}))
    for name in ("afflictor.png", *(("afflictor_glow1.png", "afflictor_glow2.png") if glows else ())):
        _write(core / "graphics" / "ships" / "phase" / name, "png")
    _write(core / "data" / "shipsystems" / "phasecloak.system", json.dumps(PHASECLOAK))
    _write(core / "data" / "shipsystems" / "emp.system", json.dumps({"id": "emp", "type": "EMP"}))
    _write(core / "data" / "hullmods" / "hull_mods.csv", "name,id\n")
    return core


def _mod(root, rows: str, ships: dict, *, files: tuple = (), systems: dict | None = None):
    mod = root / "mod"
    _write(mod / "mod_info.json", json.dumps({"id": "demomod", "name": "Demo", "version": "1.0", "gameVersion": "0.98.5a-RC7"}))
    _write(mod / "data" / "hulls" / "ship_data.csv", HULLS + rows)
    for name, spec in ships.items():
        _write(mod / "data" / "hulls" / name, json.dumps(spec))
    for name, spec in (systems or {}).items():
        _write(mod / "data" / "shipsystems" / f"{name}.system", json.dumps(spec))
    for path in files:
        _write(mod / path, "png")
    return mod


def _ship(ident: str, sprite: str) -> dict:
    return {"hullId": ident, "style": "LOW_TECH", "spriteName": sprite}


class RuleTests(unittest.TestCase):
    def test_a_phase_shield_with_phasecloak_takes_every_both_key_system_s_suffixes(self) -> None:
        with resolved_temp_dir() as root:
            core = _core(root)
            indexes = [light_index(core)]
            paths = phase_sprite_paths("afflictor", indexes, phase_systems(indexes))
        self.assertEqual([p for p, _ in paths], ["graphics/ships/phase/afflictor_glow1.png", "graphics/ships/phase/afflictor_glow2.png"])

    def test_who_is_a_phase_hull(self) -> None:
        base = {"sprite": "x.png", "system": "", "defense": "", "shield": "", "hints": set()}
        self.assertTrue(is_phase({**base, "hints": {"PHASE"}}))
        self.assertTrue(is_phase({**base, "shield": "PHASE", "defense": "phasecloak"}))
        self.assertFalse(is_phase({**base, "shield": "PHASE", "defense": "other_cloak"}))  # no PHASE hint either
        self.assertFalse(is_phase({**base, "defense": "phasecloak", "shield": "FRONT"}))

    def test_a_system_needs_both_keys_and_an_empty_suffix_names_no_file(self) -> None:
        systems = {"only_high": {"id": "only_high", "phaseHighlight": "_a"},
                   "empty_diffuse": {"id": "empty_diffuse", "phaseHighlight": "_b", "phaseDiffuse": ""}}
        with resolved_temp_dir() as root:
            mod = _mod(root, "One,fx_one,only_high,,FRONT,PHASE\nTwo,fx_two,empty_diffuse,,FRONT,\"CARRIER, PHASE\"\n",
                       {"fx_one.ship": _ship("fx_one", "graphics/ships/fx_one.png"),
                        "fx_two.ship": _ship("fx_two", "graphics/ships/fx_two.png")}, systems=systems)
            indexes = [light_index(mod)]
            found = phase_systems(indexes)
            one = phase_sprite_paths("fx_one", indexes, found)
            two = phase_sprite_paths("fx_two", indexes, found)
        self.assertEqual(found, {"empty_diffuse": ("_b", "")})
        self.assertEqual(one, [])
        self.assertEqual([p for p, _ in two], ["graphics/ships/fx_two_b.png"])

    def test_a_hull_whose_system_matches_needs_no_phase_shield_and_a_non_phase_hull_needs_nothing(self) -> None:
        systems = {"fx_dive": {"id": "fx_dive", "phaseHighlight": "_glow1", "phaseDiffuse": "_glow2"}}
        with resolved_temp_dir() as root:
            mod = _mod(root, "Diver,fx_diver,fx_dive,,NONE,PHASE\nPlain,fx_plain,fx_dive,,FRONT,\n",
                       {"fx_diver.ship": _ship("fx_diver", "graphics/ships/fx_diver.png"),
                        "fx_plain.ship": _ship("fx_plain", "graphics/ships/fx_plain.png")}, systems=systems)
            indexes = [light_index(mod), light_index(_core(root))]
            found = phase_systems(indexes)
            diver = [p for p, _ in phase_sprite_paths("fx_diver", indexes, found)]
            plain = phase_sprite_paths("fx_plain", indexes, found)
        # fx_dive matches by system id; phasecloak does not, since the shield is not PHASE.
        self.assertEqual(diver, ["graphics/ships/fx_diver_glow1.png", "graphics/ships/fx_diver_glow2.png"])
        self.assertEqual(plain, [])

    def test_a_skin_derives_from_its_own_sprite_and_takes_its_hint_and_system_changes(self) -> None:
        skins = {"fx_base.ship": _ship("fx_base", "graphics/ships/fx_base.png"),
                 "fx_skin.skin": {"baseHullId": "fx_base", "skinHullId": "fx_skin", "spriteName": "graphics/ships/fx_skin.png",
                                  "addHints": ["PHASE"], "systemId": "fx_dive"},
                 "fx_plain_skin.skin": {"baseHullId": "fx_base", "skinHullId": "fx_plain_skin"},
                 "fx_unphased.skin": {"baseHullId": "afflictor", "skinHullId": "fx_unphased", "removeHints": ["PHASE"],
                                      "spriteName": "graphics/ships/fx_unphased.png"}}
        systems = {"fx_dive": {"id": "fx_dive", "phaseHighlight": "_hi", "phaseDiffuse": "_di"}}
        with resolved_temp_dir() as root:
            mod = _mod(root, "Base,fx_base,emp,,FRONT,\n", skins, systems=systems)
            indexes = [light_index(mod), light_index(_core(root))]
            found = phase_systems(indexes)
            skin = [p for p, _ in phase_sprite_paths("fx_skin", indexes, found)]
            plain = phase_sprite_paths("fx_plain_skin", indexes, found)
            unphased = [p for p, _ in phase_sprite_paths("fx_unphased", indexes, found)]
            facts = hull_facts("fx_skin", indexes)
        self.assertEqual(skin, ["graphics/ships/fx_skin_di.png", "graphics/ships/fx_skin_hi.png"])
        self.assertEqual(facts["system"], "fx_dive")
        self.assertEqual(plain, [])
        # A vanilla base hull: the skin keeps its PHASE shield and phasecloak defense, so it stays a phase hull. A PHASE shield
        # takes every both-key system's suffixes (SpecStore), so fx_dive's too.
        self.assertEqual(unphased, ["graphics/ships/fx_unphased_di.png", "graphics/ships/fx_unphased_glow1.png",
                                    "graphics/ships/fx_unphased_glow2.png", "graphics/ships/fx_unphased_hi.png"])


    def test_a_skin_that_removes_the_phase_hint_is_no_phase_hull(self) -> None:
        skins = {"fx_base.ship": _ship("fx_base", "graphics/ships/fx_base.png"),
                 "fx_solid.skin": {"baseHullId": "fx_base", "skinHullId": "fx_solid", "removeHints": ["PHASE"],
                                   "spriteName": "graphics/ships/fx_solid.png"}}
        systems = {"fx_dive": {"id": "fx_dive", "phaseHighlight": "_glow1", "phaseDiffuse": "_glow2"}}
        with resolved_temp_dir() as root:
            mod = _mod(root, "Base,fx_base,fx_dive,,FRONT,PHASE\n", skins, systems=systems)
            indexes = [light_index(mod), light_index(_core(root))]
            found = phase_systems(indexes)
            base = [p for p, _ in phase_sprite_paths("fx_base", indexes, found)]
            solid = phase_sprite_paths("fx_solid", indexes, found)
        self.assertEqual(base, ["graphics/ships/fx_base_glow1.png", "graphics/ships/fx_base_glow2.png"])
        self.assertEqual(solid, [])  # without the hint and with a FRONT shield it is no phase hull

    def test_a_mod_s_system_replaces_the_core_s_of_the_same_id(self) -> None:
        with resolved_temp_dir() as root:
            mod = _mod(root, "Ghost,fx_ghost,emp,phasecloak,PHASE,\n", {"fx_ghost.ship": _ship("fx_ghost", "graphics/ships/fx_ghost.png")},
                       systems={"phasecloak": {**PHASECLOAK, "phaseHighlight": "_m1", "phaseDiffuse": "_m2"}})
            indexes = [light_index(mod), light_index(_core(root))]
            found = phase_systems(indexes)
            paths = [p for p, _ in phase_sprite_paths("fx_ghost", indexes, found)]
        self.assertEqual(found, {"phasecloak": ("_m1", "_m2")})
        self.assertEqual(paths, ["graphics/ships/fx_ghost_m1.png", "graphics/ships/fx_ghost_m2.png"])


    def test_a_skin_listing_phase_in_both_hint_lists_keeps_it(self) -> None:
        # The game's skin loader removes hints first, then adds them (review of slice 21).
        skins = {"fx_base.ship": _ship("fx_base", "graphics/ships/fx_base.png"),
                 "fx_both.skin": {"baseHullId": "fx_base", "skinHullId": "fx_both", "removeHints": ["PHASE"], "addHints": ["PHASE"],
                                  "spriteName": "graphics/ships/fx_both.png"}}
        systems = {"fx_dive": {"id": "fx_dive", "phaseHighlight": "_glow1", "phaseDiffuse": "_glow2"}}
        with resolved_temp_dir() as root:
            mod = _mod(root, "Base,fx_base,fx_dive,,FRONT,\n", skins, systems=systems)
            indexes = [light_index(mod), light_index(_core(root))]
            both = [p for p, _ in phase_sprite_paths("fx_both", indexes, phase_systems(indexes))]
        self.assertEqual(both, ["graphics/ships/fx_both_glow1.png", "graphics/ships/fx_both_glow2.png"])


class ClosureAndLoadTests(unittest.TestCase):
    def test_without_a_core_the_vanilla_cloak_s_suffixes_still_apply(self) -> None:
        # Review of slice 21: with no core the closure never learned phasecloak's suffixes and dropped the glows.
        with resolved_temp_dir() as root:
            mod = _mod(root, "Ghost,fx_ghost,emp,phasecloak,PHASE,\n", {"fx_ghost.ship": _ship("fx_ghost", "graphics/ships/fx_ghost.png")},
                       files=("graphics/ships/fx_ghost.png", "graphics/ships/fx_ghost_glow1.png", "graphics/ships/fx_ghost_glow2.png"))
            plan = vendor_plan(mod, ["hull:fx_ghost"])
        files = {e["path"] for e in plan["include"] if e["what"] == "file"}
        self.assertTrue({"graphics/ships/fx_ghost_glow1.png", "graphics/ships/fx_ghost_glow2.png"} <= files)

    def test_a_hull_the_check_cannot_judge_fails_closed(self) -> None:
        ships = {"fx_diver.ship": _ship("fx_diver", "graphics/ships/fx_diver.png"),
                 "fx_plain.ship": _ship("fx_plain", "graphics/ships/fx_plain.png"),
                 "fx_orphan.skin": {"baseHullId": "nowhere_hull", "skinHullId": "fx_orphan"}}
        with resolved_temp_dir() as root:
            carrier = _mod(root, "Diver,fx_diver,lib_dive,,NONE,PHASE\nPlain,fx_plain,lib_other,,FRONT,\n", ships,
                           files=("graphics/ships/fx_diver.png", "graphics/ships/fx_plain.png"))
            gaps = load_gaps(carrier, _core(root))
        self.assertEqual(sorted((g["finding"], g["hull"]) for g in gaps),
                         [("hull-phase-unresolved", "fx_diver"), ("hull-phase-unresolved", "fx_orphan")])  # fx_plain is no phase hull

    def test_the_closure_takes_the_mod_s_phase_sprites_and_reports_one_nobody_has(self) -> None:
        with resolved_temp_dir() as root:
            mod = _mod(root, "Ghost,fx_ghost,emp,phasecloak,PHASE,\n", {"fx_ghost.ship": _ship("fx_ghost", "graphics/ships/fx_ghost.png")},
                       files=("graphics/ships/fx_ghost.png", "graphics/ships/fx_ghost_glow1.png"))
            plan = vendor_plan(mod, ["hull:fx_ghost"], vanilla_core=_core(root))
        files = {e["path"] for e in plan["include"] if e["what"] == "file"}
        self.assertIn("graphics/ships/fx_ghost_glow1.png", files)
        self.assertTrue([m for m in plan["missing"] if "fx_ghost_glow2.png" in m and "RC8-51" in m])

    def test_a_carrier_missing_a_phase_sprite_has_a_load_gap_and_the_core_s_copy_counts(self) -> None:
        with resolved_temp_dir() as root:
            carrier = _mod(root, "Ghost,fx_ghost,emp,phasecloak,PHASE\nSkin,afflictor_skin,emp,phasecloak,PHASE,\n",
                           {"fx_ghost.ship": _ship("fx_ghost", "graphics/ships/fx_ghost.png"),
                            "afflictor_d.skin": {"baseHullId": "afflictor", "skinHullId": "afflictor_d"}},
                           files=("graphics/ships/fx_ghost.png", "graphics/ships/fx_ghost_glow1.png"))
            gaps = load_gaps(carrier, _core(root))
        self.assertEqual([(g["finding"], g["hull"], g["path"]) for g in gaps],
                         [("hull-phase-sprite-missing", "fx_ghost", "graphics/ships/fx_ghost_glow2.png")])
        self.assertEqual(gaps[0]["file"], "data/hulls/fx_ghost.ship")

    def test_a_hull_gene_s_proof_carries_its_phase_sprites(self) -> None:
        with resolved_temp_dir() as root:
            mod = _mod(root, "Ghost,fx_ghost,emp,phasecloak,PHASE,\n", {"fx_ghost.ship": _ship("fx_ghost", "graphics/ships/fx_ghost.png")},
                       files=("graphics/ships/fx_ghost.png", "graphics/ships/fx_ghost_glow1.png", "graphics/ships/fx_ghost_glow2.png"))
            core = _core(root)
            gene = describe(mod, "hull:fx_ghost", vanilla_core=core)
            result = prove(mod, "hull:fx_ghost", root / "proofs", vanilla_core=core)
            carried = sorted(p.name for p in (root / "proofs" / "work" / "carrier" / "graphics" / "ships").iterdir())
        self.assertIn("graphics/ships/fx_ghost_glow2.png", [m["path"] for m in gene["members"]])
        self.assertEqual(carried, ["fx_ghost.png", "fx_ghost_glow1.png", "fx_ghost_glow2.png"])
        self.assertEqual(result["verdicts"], {"subtraction-proof": "PASS", "isolation-proof": "PASS"})

    def test_a_removed_glow_another_donor_weapon_shows_fails_the_subtraction(self) -> None:
        # The advisor's case (2026-11-23): the donor's decorative weapon uses the hull's glow as its sprite. Until shared files
        # are needs, the subtraction removes it and the scan reports the weapon's missing asset as a leak.
        with resolved_temp_dir() as root:
            mod = _mod(root, "Ghost,fx_ghost,emp,phasecloak,PHASE,\n", {"fx_ghost.ship": _ship("fx_ghost", "graphics/ships/fx_ghost.png")},
                       files=("graphics/ships/fx_ghost.png", "graphics/ships/fx_ghost_glow1.png", "graphics/ships/fx_ghost_glow2.png"))
            _write(mod / "data" / "weapons" / "weapon_data.csv", "name,id\nDeco,fx_deco\n")
            _write(mod / "data" / "weapons" / "fx_deco.wpn", json.dumps({"id": "fx_deco", "type": "DECORATIVE",
                                                                         "turretSprite": "graphics/ships/fx_ghost_glow2.png"}))
            result = prove(mod, "hull:fx_ghost", root / "proofs", vanilla_core=_core(root))
            subtraction = json.loads((root / "proofs" / "subtraction-proof.json").read_text(encoding="utf-8"))
        self.assertEqual(result["verdicts"]["subtraction-proof"], "FAIL")
        self.assertIn({"finding": "asset-reference-missing", "file": "data/weapons/fx_deco.wpn",
                       "reference": "path:graphics/ships/fx_ghost_glow2.png"}, subtraction["leaks"])


if __name__ == "__main__":
    unittest.main()
