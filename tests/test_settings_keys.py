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
