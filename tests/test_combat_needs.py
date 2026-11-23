"""94.G2 slice 22: what a gene's ships need once they are built for combat: engine styles and sounds (RC8_BEHAVIOUR RC8-52,
RC8-53). Synthetic fixtures only."""
from __future__ import annotations

import json
import subprocess
import unittest
import zipfile

from bridgeforge.genome.carrier_load import HULL_STYLES, load_gaps
from bridgeforge.genome.combat_needs import ENGINE_STYLES, SOUNDS, combat_gaps, donor_needs, engine_style_ids
from bridgeforge.genome.gene import describe, validate
from bridgeforge.genome.proof import prove
from tests.support import javac_path, resolved_temp_dir, write_text as _write

ENGINES = {"Vectored FX": {"glowSprite": "graphics/fx/fx_glow.png", "type": "SMOKE", "engineSound": "fx_engine"},
           "FX_ENGINE": {"type": "GLOW"}}
MOD_SOUNDS = {name: {"sounds": [{"file": f"sounds/{name}.ogg"}]} for name in ("fx_raise", "fx_fire", "fx_cue", "fx_engine", "fx_unused")}
SLOTS = [{"style": "CUSTOM", "styleId": "Vectored FX"}, {"style": "FX_ENGINE"}, {"style": "LOW_TECH"},
         {"style": "CUSTOM", "styleSpec": {"type": "GLOW"}}]


def _core(root):
    core = root / "core"
    _write(core / HULL_STYLES, json.dumps({"LOW_TECH": {"engineLoopSet": "engine_loop", "fluxLoopSet": "flux_loop"}}))
    _write(core / SOUNDS, json.dumps({"engine_loop": {"sounds": []}, "flux_loop": {"sounds": []}}))
    _write(core / ENGINE_STYLES, json.dumps({"LOW_TECH": {"type": "GLOW"}}))
    _write(core / "data" / "hulls" / "ship_data.csv", "name,id\n")
    _write(core / "data" / "hullmods" / "hull_mods.csv", "name,id\n")
    return core


def _mod(root, *, script: str = "", slots: list | None = None):
    mod = root / "mod"
    _write(mod / "mod_info.json", json.dumps({"id": "demomod", "name": "Demo", "version": "1.0", "gameVersion": "0.98.5a-RC7"}))
    _write(mod / "data" / "hulls" / "ship_data.csv", "name,id\nShip,fx_ship\nOther,fx_other\n")
    _write(mod / "data" / "hulls" / "fx_ship.ship", json.dumps({"hullId": "fx_ship", "style": "FX_STYLE",
                                                               "engineSlots": SLOTS if slots is None else slots,
                                                               "builtInWeapons": {"WS1": "fx_gun"}}))
    _write(mod / "data" / "hulls" / "fx_other.ship", json.dumps({"hullId": "fx_other", "style": "FX_STYLE"}))
    _write(mod / HULL_STYLES, json.dumps({"FX_STYLE": {"shieldRaiseSet": "fx_raise", "engineLoopSet": "engine_loop"}}))
    _write(mod / ENGINE_STYLES, json.dumps(ENGINES))
    _write(mod / SOUNDS, json.dumps(MOD_SOUNDS))
    _write(mod / "data" / "weapons" / "weapon_data.csv", "name,id\nGun,fx_gun\n")
    _write(mod / "data" / "weapons" / "fx_gun.wpn", json.dumps({"id": "fx_gun", "type": "BALLISTIC", "fireSoundOne": "fx_fire"}))
    for name in (*MOD_SOUNDS, ):
        _write(mod / "sounds" / f"{name}.ogg", "ogg")
    _write(mod / "graphics" / "fx" / "fx_glow.png", "png")
    if script:
        _write(mod / "data" / "scripts" / "fx_Effect.java", script)
    return mod


PLAYER = 'package data.scripts;\npublic class fx_Effect {\n  void go(Object p) { play("fx_cue"); }\n  void play(String s) {}\n}\n'


class EngineSlotTests(unittest.TestCase):
    def test_which_slots_name_an_engine_style(self) -> None:
        # RC7 ShipHullSpecLoader (javap 2026-11-23): a non-enum style is a CUSTOM styleId; CUSTOM names one by styleId or
        # carries an inline styleSpec; an enum name needs nothing.
        self.assertEqual(engine_style_ids({"engineSlots": SLOTS}), ["FX_ENGINE", "Vectored FX"])
        self.assertEqual(engine_style_ids({"engineSlotChanges": {"E1": {"style": "CUSTOM", "styleId": "SKIN_ENGINE"}}}), ["SKIN_ENGINE"])
        self.assertEqual(engine_style_ids({"engineSlots": "oops"}), [])


class DonorNeedTests(unittest.TestCase):
    def test_a_gene_needs_its_engine_styles_and_the_mod_sounds_its_specs_styles_and_code_name(self) -> None:
        with resolved_temp_dir() as root:
            mod = _mod(root, script=PLAYER)
            members = [{"what": "file", "path": p} for p in ("data/hulls/fx_ship.ship", "data/weapons/fx_gun.wpn",
                                                              "data/scripts/fx_Effect.java")]
            needs = donor_needs(mod, members, _core(root))
        self.assertEqual(needs["donor"], [
            "data/config/engine_styles.json#/FX_ENGINE", "data/config/engine_styles.json#/Vectored FX",
            "data/config/sounds.json#/fx_cue", "data/config/sounds.json#/fx_engine", "data/config/sounds.json#/fx_fire",
            "data/config/sounds.json#/fx_raise", "graphics/fx/fx_glow.png", "sounds/fx_cue.ogg", "sounds/fx_engine.ogg",
            "sounds/fx_fire.ogg", "sounds/fx_raise.ogg"])  # not fx_unused; engine_loop is the core's
        self.assertEqual(needs["missing"], [])

    def test_the_core_s_own_engine_styles_and_sounds_are_not_carried(self) -> None:
        # Vanilla's engine_styles.json defines ids outside the enum too (`midlineFlare`); a mod that re-defines a core sound
        # id keeps the core's (recorded as a fidelity limit, as with hull styles).
        with resolved_temp_dir() as root:
            mod = _mod(root, slots=[{"style": "CUSTOM", "styleId": "coreFlare"}])
            _write(mod / SOUNDS, json.dumps({**MOD_SOUNDS, "engine_loop": {"sounds": [{"file": "sounds/fx_raise.ogg"}]}}))
            core = _core(root)
            _write(core / ENGINE_STYLES, json.dumps({"LOW_TECH": {}, "coreFlare": {"type": "GLOW"}}))
            needs = donor_needs(mod, [{"what": "file", "path": "data/hulls/fx_ship.ship"}], core)
        self.assertEqual(needs["missing"], [])
        self.assertEqual(needs["donor"], ["data/config/sounds.json#/fx_raise", "sounds/fx_raise.ogg"])  # no coreFlare, no engine_loop

    def test_an_engine_style_or_a_style_sound_nothing_defines_is_missing(self) -> None:
        with resolved_temp_dir() as root:
            mod = _mod(root, slots=[{"style": "CUSTOM", "styleId": "NOWHERE"}])
            _write(mod / HULL_STYLES, json.dumps({"FX_STYLE": {"shieldRaiseSet": "no_such_sound"}}))
            needs = donor_needs(mod, [{"what": "file", "path": "data/hulls/fx_ship.ship"}], _core(root))
            without_core = donor_needs(mod, [{"what": "file", "path": "data/hulls/fx_ship.ship"}], None)
        self.assertEqual(needs["missing"], ["engine style NOWHERE: no engine_styles.json defines it (RC8-52)",
                                            "sound no_such_sound (hull style FX_STYLE): no sounds.json defines it (RC8-53)"])
        self.assertEqual(without_core["missing"], [])  # without the core nothing can be called undefined

    def test_the_proof_carries_them_the_subtraction_keeps_them_and_a_spaced_id_survives(self) -> None:
        with resolved_temp_dir() as root:
            mod, core = _mod(root), _core(root)
            gene = describe(mod, "hull:fx_ship", vanilla_core=core)
            result = prove(mod, "hull:fx_ship", root / "proofs", vanilla_core=core)
            work = root / "proofs" / "work"
            carried = (json.loads((work / "carrier" / ENGINE_STYLES).read_text(encoding="utf-8")),
                       json.loads((work / "carrier" / SOUNDS).read_text(encoding="utf-8")))
            files = sorted(p.name for p in (work / "carrier" / "sounds").iterdir())
            kept = json.loads((work / "subtraction" / ENGINE_STYLES).read_text(encoding="utf-8"))
            isolation = json.loads((root / "proofs" / "isolation-proof.json").read_text(encoding="utf-8"))
        self.assertEqual(validate(gene), [])
        self.assertEqual(carried[0], ENGINES)
        self.assertEqual(sorted(carried[1]), ["fx_engine", "fx_fire", "fx_raise"])
        self.assertEqual(files, ["fx_engine.ogg", "fx_fire.ogg", "fx_raise.ogg"])
        self.assertIn("Vectored FX", kept)
        self.assertEqual((isolation["load_gaps"], result["verdicts"]), ([], {"subtraction-proof": "PASS", "isolation-proof": "PASS"}))
        self.assertTrue({("need", ENGINE_STYLES), ("need", SOUNDS)} <= {(i["role"], i["path"]) for i in isolation["inputs"]})


class ReviewTests(unittest.TestCase):
    """The independent review of slice 22 (2026-11-23)."""

    def test_a_missile_s_engine_style_is_carried_but_never_a_gap(self) -> None:
        missile = {"id": "fx_missile", "engineSlots": [{"style": "CUSTOM", "styleId": "FX_ENGINE"}, {"style": "BARE_MISSILE"}]}
        with resolved_temp_dir() as root:
            mod = _mod(root)
            _write(mod / "data" / "weapons" / "fx_missile.proj", json.dumps(missile))
            needs = donor_needs(mod, [{"what": "file", "path": "data/weapons/fx_missile.proj"}], _core(root))
            carrier = root / "carrier"
            _write(carrier / "data" / "weapons" / "fx_missile.proj", json.dumps(missile))
            gaps = combat_gaps(carrier, [_core(root)])
        self.assertIn("data/config/engine_styles.json#/FX_ENGINE", needs["donor"])
        self.assertIn("engine style BARE_MISSILE: no engine_styles.json defines it (RC8-52)", needs["missing"])
        self.assertEqual(gaps, [])  # a missing missile style is not shown to be Fatal

    def test_csv_rows_and_json_entries_name_sounds_too(self) -> None:
        with resolved_temp_dir() as root:
            mod = _mod(root)
            _write(mod / "data" / "campaign" / "abilities.csv", "name,id,uiOn\nAbility,fx_ability,fx_cue\n")
            _write(mod / "data" / "config" / "settings.json", json.dumps({"fxSound": {"loop": "fx_engine"}}))
            needs = donor_needs(mod, [{"what": "csv-row", "path": "data/campaign/abilities.csv [fx_ability]"},
                                      {"what": "json-entry", "path": "data/config/settings.json#/fxSound"}], _core(root))
        self.assertEqual([d for d in needs["donor"] if d.startswith(SOUNDS)],
                         ["data/config/sounds.json#/fx_cue", "data/config/sounds.json#/fx_engine"])

    def test_a_style_sound_gap_the_donor_already_has_does_not_fail_the_subtraction(self) -> None:
        # The gap names the styles file, not the first hull using the style, so removing that hull does not move it.
        with resolved_temp_dir() as root:
            mod = _mod(root, slots=[])
            _write(mod / HULL_STYLES, json.dumps({"FX_STYLE": {"shieldRaiseSet": "lib_sound"}}))
            result = prove(mod, "hull:fx_other", root / "proofs", vanilla_core=_core(root))
            subtraction = json.loads((root / "proofs" / "subtraction-proof.json").read_text(encoding="utf-8"))
        self.assertEqual((subtraction["load_gaps"], result["verdicts"]["subtraction-proof"]), ([], "PASS"))

    def test_a_commented_out_play_call_is_not_played(self) -> None:
        with resolved_temp_dir() as root:
            carrier = root / "carrier"
            _write(carrier / "data" / "scripts" / "fx_Effect.java",
                   'class X {\n // sp.playUISound("ghost_ping", 1f, 1f);\n /* sp.playSound("ghost_fire", 1f, 1f, a, b); */ }\n')
            gaps = combat_gaps(carrier, [_core(root)])
        self.assertEqual(gaps, [])

    def test_a_set_proof_counts_a_declared_dependency_s_engine_style(self) -> None:
        from bridgeforge.genome.gene_set import prove_set

        with resolved_temp_dir() as root:
            mod = _mod(root, slots=[{"style": "CUSTOM", "styleId": "LIB_FLARE"}])
            info = json.loads((mod / "mod_info.json").read_text(encoding="utf-8"))
            _write(mod / "mod_info.json", json.dumps({**info, "dependencies": [{"id": "libmod"}]}))
            library = root / "mods" / "libmod"
            _write(library / "mod_info.json", json.dumps({"id": "libmod", "name": "Lib", "version": "1"}))
            _write(library / ENGINE_STYLES, json.dumps({"LIB_FLARE": {"type": "GLOW"}}))
            core = _core(root)
            alone = prove_set(mod, "hull:fx_ship", root / "alone", vanilla_core=core, quiet=True)
            with_library = prove_set(mod, "hull:fx_ship", root / "with", vanilla_core=core, quiet=True, provider_roots=[root / "mods"])
        self.assertEqual((alone["load_gaps"], with_library["load_gaps"]), (1, 0))


class CarrierCheckTests(unittest.TestCase):
    def test_undefined_engine_styles_style_sounds_and_played_sounds_are_gaps(self) -> None:
        with resolved_temp_dir() as root:
            carrier = root / "carrier"
            _write(carrier / "data" / "hulls" / "a.ship", json.dumps({"hullId": "a", "style": "FX_STYLE", "engineSlots": SLOTS}))
            _write(carrier / HULL_STYLES, json.dumps({"FX_STYLE": {"shieldRaiseSet": "fx_raise", "engineLoopSet": "engine_loop"}}))
            _write(carrier / ENGINE_STYLES, json.dumps({"FX_ENGINE": {}}))
            _write(carrier / "data" / "scripts" / "fx_Effect.java", 'class X { void f(Object p) { sp.playSound("fx_cue", 1f, 1f, a, b);'
                                                                   ' sp.playLoop("flux_loop", this, 1f, 1f, a, b); } }')
            core = _core(root)
            gaps = load_gaps(carrier, core)
            without_code = combat_gaps(carrier, [core], code=False)
        self.assertEqual([(g["finding"], g.get("style"), g.get("sound")) for g in gaps],
                         [("engine-style-undefined", "Vectored FX", None), ("hull-style-sound-undefined", "FX_STYLE", "fx_raise"),
                          ("sound-play-undefined", None, "fx_cue")])
        self.assertEqual([g["finding"] for g in without_code], ["engine-style-undefined", "hull-style-sound-undefined"])

    @unittest.skipUnless(javac_path(), "needs javac")
    def test_a_jar_class_that_plays_an_undefined_sound_is_a_gap(self) -> None:
        # The crash of DIAG-P4-S22A: a weapon's every-frame script played a mod sound id the carrier lacked.
        api = "package com.fs.starfarer.api;\npublic interface SoundPlayerAPI { Object playSound(String id, float p, float v, Object a, Object b); }\n"
        user = ("package data.scripts;\nimport com.fs.starfarer.api.SoundPlayerAPI;\npublic class fx_Deco {\n"
                "  void advance(SoundPlayerAPI sp) { sp.playSound(\"fx_cue\", 1f, 1f, null, null); String other = \"fx_label\"; }\n}\n")
        with resolved_temp_dir() as root:
            src, out, carrier = root / "src", root / "classes", root / "carrier"
            _write(src / "com" / "fs" / "starfarer" / "api" / "SoundPlayerAPI.java", api)
            _write(src / "data" / "scripts" / "fx_Deco.java", user)
            subprocess.run([javac_path(), "-encoding", "UTF-8", "-proc:none", "-d", str(out),
                            str(src / "com" / "fs" / "starfarer" / "api" / "SoundPlayerAPI.java"), str(src / "data" / "scripts" / "fx_Deco.java")],
                           check=True, capture_output=True)
            _write(carrier / "mod_info.json", json.dumps({"id": "c", "name": "C", "version": "1", "jars": ["jars/c.jar"]}))
            (carrier / "jars").mkdir(parents=True)
            with zipfile.ZipFile(carrier / "jars" / "c.jar", "w") as jar:
                jar.write(out / "data" / "scripts" / "fx_Deco.class", "data/scripts/fx_Deco.class")
            gaps = combat_gaps(carrier, [_core(root)])
        self.assertEqual([(g["finding"], g["sound"], g["file"]) for g in gaps],
                         [("sound-play-undefined", "fx_cue", "jars/c.jar!data/scripts/fx_Deco.class")])  # fx_label is no sound


if __name__ == "__main__":
    unittest.main()
