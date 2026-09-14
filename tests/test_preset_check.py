"""bf-test.ps1 presets vs the rig's installed mods (Flu-X r3 / Zorg18 r2 kept enabling dropped libraries)."""

import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.preset_check import check_presets, parse_presets

SCRIPT = '''$Presets = @{
    "flux"      = @{ Folder = "Flu-X"; Mods = @("lw_lazylib", "MagicLib", "infected"); Setups = @(); Track = @() }
    "flux-nex"  = @{ Folder = "Flu-X"; Mods = @("lw_lazylib", "MagicLib", "nexerelin", "infected"); Setups = @(); Track = @() }
    "zorg"      = @{ Folder = "Zorg18"; Mods = @("zorg"); Setups = @("credits:500000"); Track = @() }
    "exigency"  = @{ Folder = "Exigency"; Mods = @("exigency"); Setups = @(); Track = @() }
    "ghost"     = @{ Folder = "Missing"; Mods = @("ghost"); Setups = @(); Track = @() }
    "zorg-luna" = @{ Folder = "Zorg18"; Mods = @("lunalib", "zorg"); Setups = @(); Track = @() }
    "luna-user" = @{ Folder = "LunaUser"; Mods = @("lunalib", "lunauser"); Setups = @(); Track = @() }
}
'''


def _rig(root: Path) -> Path:
    mods = root / "_rig" / "mods"
    for folder, info in {
        "Flu-X": {"id": "infected"},
        "Zorg18": {"id": "zorg"},
        "Exigency": {"id": "exigency", "dependencies": [{"id": "lw_lazylib", "name": "LazyLib"}]},
        "Nexerelin": {"id": "nexerelin", "dependencies": [{"id": "lw_lazylib"}, {"id": "MagicLib"}]},
        "LazyLib": {"id": "lw_lazylib"},
        "MagicLib": {"id": "MagicLib", "dependencies": [{"id": "lw_lazylib"}]},
        "LunaLib": {"id": "lunalib"},
        "LunaUser": {"id": "lunauser"},
    }.items():
        (mods / folder).mkdir(parents=True)
        (mods / folder / "mod_info.json").write_text(json.dumps(info), encoding="utf-8")
    # Uses LunaLib for settings without declaring it: enabling LunaLib is right.
    (mods / "LunaUser" / "Settings.java").write_text("import lunalib.lunaSettings.LunaSettings;\nclass Settings {}\n", encoding="utf-8")
    script = root / "bf-test.ps1"
    script.write_text(SCRIPT, encoding="utf-8")
    return script


class PresetCheckTests(unittest.TestCase):
    def test_parse_presets(self) -> None:
        presets = parse_presets(SCRIPT)
        self.assertEqual(presets["flux-nex"], {"folder": "Flu-X", "mods": ["lw_lazylib", "MagicLib", "nexerelin", "infected"]})

    def test_leftover_libraries_missing_dependencies_and_folders(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = check_presets(_rig(Path(directory)))
        by_name = {preset["preset"]: preset for preset in result["presets"]}
        self.assertEqual(result["status"], "FAIL")
        # Flu-X dropped its libraries: both are leftovers, although MagicLib declares LazyLib.
        self.assertEqual(by_name["flux"]["status"], "REVIEW")
        self.assertEqual(len(by_name["flux"]["warnings"]), 2)
        self.assertEqual(by_name["zorg-luna"]["status"], "REVIEW")  # nothing uses LunaLib
        self.assertEqual(by_name["luna-user"]["status"], "PASS")  # referenced in code, so needed
        # With Nexerelin enabled, the same libraries are its declared dependencies: fine.
        self.assertEqual(by_name["flux-nex"]["status"], "PASS")
        self.assertEqual(by_name["zorg"]["status"], "PASS")
        self.assertEqual(by_name["exigency"]["errors"], ["'exigency' declares dependency 'lw_lazylib', which is not enabled"])
        self.assertIn("no readable mod_info.json", by_name["ghost"]["errors"][0])
        self.assertIn("'ghost' is enabled but no rig mod has that id", by_name["ghost"]["errors"])


if __name__ == "__main__":
    unittest.main()
