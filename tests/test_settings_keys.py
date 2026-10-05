"""settings-key-missing (owner crash log 2026-10-04): Exigency 0.8 read settings RC8 does not have."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bridgeforge.scanner import scan_mod
from bridgeforge.settings_keys import javap_reads, source_reads

LISTING = """  public void updateCargoPrePlayerInteraction();
    Code:
     120: invokestatic  #40                 // Method com/fs/starfarer/api/Global.getSettings:()Lcom/fs/starfarer/api/SettingsAPI;
     123: ldc           #44                 // String blackMarketMinSupplies
     125: invokeinterface #46,  2           // InterfaceMethod com/fs/starfarer/api/SettingsAPI.getFloat:(Ljava/lang/String;)F
     130: ldc           #50                 // String unrelated
     132: aload_1
     133: invokeinterface #46,  2           // InterfaceMethod com/fs/starfarer/api/SettingsAPI.getFloat:(Ljava/lang/String;)F
"""


class SettingsKeysTests(unittest.TestCase):
    def test_source_and_javap_reads(self) -> None:
        self.assertEqual(source_reads('float a = Global.getSettings().getFloat("blackMarketMinFuel");\nint b = Global.getSettings().getInt("x");'),
                         [(1, "getFloat", "blackMarketMinFuel"), (2, "getInt", "x")])
        # The second getFloat takes a variable (aload_1 came between): not a literal read.
        self.assertEqual(javap_reads(LISTING), [("getFloat", "blackMarketMinSupplies")])

    def test_scan_flags_only_keys_no_settings_json_defines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            core = root / "core" / "data" / "config"
            core.mkdir(parents=True)
            (core / "settings.json").write_text('{"sensorRangeMult": 1, "shipMaxBurn": 20}', encoding="utf-8")
            mod = root / "mod"
            (mod / "data" / "config").mkdir(parents=True)
            (mod / "mod_info.json").write_text('{"id": "fx"}', encoding="utf-8")
            (mod / "data" / "config" / "settings.json").write_text('{"fxOwnKey": 3}', encoding="utf-8")
            (mod / "data" / "scripts").mkdir(parents=True)
            (mod / "data" / "scripts" / "P.java").write_text(
                'class P { void a() { Global.getSettings().getFloat("blackMarketMinSupplies"); '
                'Global.getSettings().getFloat("shipMaxBurn"); Global.getSettings().getInt("fxOwnKey"); } }', encoding="utf-8")
            found = [f for f in scan_mod(mod, vanilla_core=root / "core").findings if f.id == "settings-key-missing"]
        self.assertEqual([f.evidence[0] for f in found], ["key:blackMarketMinSupplies"])


if __name__ == "__main__":
    unittest.main()


class FactionKnownTagTests(unittest.TestCase):
    # Owner report 2026-10-04: Exigency's ships could not be bought; knownShips' tag exigency_bp was on no hull.
    def test_a_known_tag_no_hull_carries_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            core = root / "core"
            (core / "data" / "hulls").mkdir(parents=True)
            (core / "data" / "hulls" / "ship_data.csv").write_text("name,id,tags\nWolf,wolf,base_bp\n", encoding="utf-8")
            mod = root / "mod"
            (mod / "data" / "hulls").mkdir(parents=True)
            (mod / "data" / "world" / "factions").mkdir(parents=True)
            (mod / "mod_info.json").write_text('{"id": "fx"}', encoding="utf-8")
            (mod / "data" / "hulls" / "ship_data.csv").write_text("name,id,tags\nA,fx_a,\nB,fx_b,fx_other\n", encoding="utf-8")
            # Exigency's shape: its own tag dead, base_bp matching only vanilla hulls -> knows none of its own ships.
            (mod / "data" / "world" / "factions" / "fx.faction").write_text(
                '{"id": "fx", "knownShips": {"tags": ["fx_bp", "base_bp"], "hulls": []}}', encoding="utf-8")
            # A dead tag beside one that covers the mod's ships is harmless (2026-10-05 refinement).
            (mod / "data" / "world" / "factions" / "fy.faction").write_text(
                '{"id": "fy", "knownShips": {"tags": ["fy_bp", "fx_other"], "hulls": []}}', encoding="utf-8")
            found = [f for f in scan_mod(mod, vanilla_core=core).findings if f.id == "faction-known-tag-unmatched"]
        self.assertEqual([(f.file.split("/")[-1], f.evidence) for f in found], [("fx.faction", ["list:knownShips", "tag:fx_bp"])])

    def test_skin_tags_and_tags_vanilla_factions_use_are_not_flagged(self) -> None:
        # done-audit 2026-10-04: Amogus' hegemony.faction (XIV_bp on vanilla skins; knownWeapons tag "hegemony").
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            core = root / "core"
            (core / "data" / "hulls" / "skins").mkdir(parents=True)
            (core / "data" / "world" / "factions").mkdir(parents=True)
            (core / "data" / "hulls" / "ship_data.csv").write_text("name,id,tags\nWolf,wolf,base_bp\n", encoding="utf-8")
            (core / "data" / "hulls" / "skins" / "wolf_xiv.skin").write_text('{"skinHullId": "wolf_xiv", "tags": ["XIV_bp"]}', encoding="utf-8")
            (core / "data" / "world" / "factions" / "hegemony.faction").write_text(
                '{"id": "hegemony", "knownWeapons": {"tags": ["hegemony"]}}', encoding="utf-8")
            mod = root / "mod"
            (mod / "data" / "world" / "factions").mkdir(parents=True)
            (mod / "mod_info.json").write_text('{"id": "fx"}', encoding="utf-8")
            (mod / "data" / "world" / "factions" / "hegemony.faction").write_text(
                '{"id": "hegemony", "knownShips": {"tags": ["XIV_bp"]}, "knownWeapons": {"tags": ["hegemony"]}}', encoding="utf-8")
            found = [f for f in scan_mod(mod, vanilla_core=core).findings if f.id == "faction-known-tag-unmatched"]
        self.assertEqual(found, [])


class GuardedSettingsReadTests(unittest.TestCase):
    def test_a_read_behind_an_isModEnabled_guard_is_another_mods_setting(self) -> None:
        # Kadur Remnant (2026-10-05): isModEnabled("IndEvo") && getBoolean("PirateHaven"), IndEvo's own key.
        text = ('if (Global.getSettings().getModManager().isModEnabled("IndEvo") && Global.getSettings().getBoolean("PirateHaven")) {}\n'
                'boolean b = Global.getSettings().getBoolean("ownKey");\n')
        self.assertEqual(source_reads(text), [(2, "getBoolean", "ownKey")])
