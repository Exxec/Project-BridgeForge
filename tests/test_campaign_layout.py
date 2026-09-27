"""P15 item 25: a mod's own star systems and body types (Zorg18's leaking artificial star, 2026-09-27)."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

from bridgeforge.campaign_layout import mod_body_types, mod_created_systems, mod_placed_types
from bridgeforge.fixers import apply_fix, compute_fix
from bridgeforge.probe_config import build_probe_config
from bridgeforge.scanner import scan_mod


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _mod(root: Path, star_weights: str = "40,35,30", planet_weight: str = "10") -> Path:
    mod = root / "zorg"
    _write(mod / "mod_info.json", '{"id": "zorg"}')
    _write(mod / "data" / "config" / "planets.json", json.dumps({
        "star_zorg": {"isStar": True, "texture": "t.jpg"}, "zorg_planet": {"isStar": False, "texture": "t.jpg"},
        "zorg_unused": {"isStar": False}}))
    _write(mod / "data" / "campaign" / "procgen" / "star_gen_data.csv",
           f"id,age,tags,freqYOUNG,freqAVERAGE,freqOLD,minRadius\nstar_zorg,ANY,,{star_weights},800\n")
    _write(mod / "data" / "campaign" / "procgen" / "planet_gen_data.csv",
           f"id,type,category,frequency,habOffsetMin\nzorg_planet,PLANET,cat_hab1,{planet_weight},1\n")
    _write(mod / "data" / "scripts" / "world" / "ZorgGen.java",
           'class ZorgGen { void g(SectorAPI s) { StarSystemAPI z = s.createStarSystem("Zorg Zeta");\n'
           '  z.initStar("zorg_star_000", "star_zorg", 800f, 500f); z.addPlanet("p", null, "Zeta I", "zorg_planet", 0f, 90f, 1000f, 30f); } }')
    return mod


class CampaignLayoutFactsTests(unittest.TestCase):
    def test_systems_types_weights_and_placement_from_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory))
            types = mod_body_types(mod)
            self.assertEqual(mod_created_systems(mod), ["Zorg Zeta"])
            self.assertEqual(types["star_zorg"], {"star": True, "procgen_weight": 105.0})
            self.assertEqual(types["zorg_unused"]["procgen_weight"], 0.0)
            self.assertEqual(mod_placed_types(mod, set(types)), {"star_zorg", "zorg_planet"})

    def test_system_name_from_jar_bytecode(self) -> None:
        # Zorg ships only a jar: `ldc "Zorg Zeta"` right before `invokeinterface createStarSystem`.
        javac = shutil.which("javac") or next(iter(Path("In operation/_rig").glob("jdk-*/bin/javac.exe")), None)
        if javac is None:
            self.skipTest("no javac")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "src" / "api" / "SectorAPI.java", "package api; public interface SectorAPI { Object createStarSystem(String name); }")
            _write(root / "src" / "gen" / "Gen.java", 'package gen; public class Gen { void g(api.SectorAPI s) { s.createStarSystem("Zorg Zeta"); String other = "Zeta I"; } }')
            out = root / "classes"
            subprocess.run([str(javac), "-d", str(out), *map(str, (root / "src").rglob("*.java"))], check=True, capture_output=True)
            mod = root / "mod"
            _write(mod / "mod_info.json", '{"id": "m", "jars": ["jars/m.jar"]}')
            (mod / "jars").mkdir()
            with zipfile.ZipFile(mod / "jars" / "m.jar", "w") as jar:
                jar.write(out / "gen" / "Gen.class", "gen/Gen.class")
            self.assertEqual(mod_created_systems(mod), ["Zorg Zeta"])


class ProcgenLeakTests(unittest.TestCase):
    def test_placed_and_weighted_types_are_flagged_and_the_fixer_zeroes_them(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory))
            hits = sorted(f.evidence[0] for f in scan_mod(mod).findings if f.id == "procgen-mod-body-leak")
            apply_fix(compute_fix(mod, "procgen-mod-body-leak"))
            star_row = (mod / "data" / "campaign" / "procgen" / "star_gen_data.csv").read_text(encoding="utf-8").splitlines()[1]
            planet_row = (mod / "data" / "campaign" / "procgen" / "planet_gen_data.csv").read_text(encoding="utf-8").splitlines()[1]
            after = [f for f in scan_mod(mod).findings if f.id == "procgen-mod-body-leak"]
        self.assertEqual(hits, ["type:star_zorg", "type:zorg_planet"])
        self.assertEqual(star_row, "star_zorg,ANY,,0,0,0,800")
        self.assertEqual(planet_row, "zorg_planet,PLANET,cat_hab1,0,1")
        self.assertEqual(after, [])

    def test_unweighted_types_are_quiet(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory), star_weights="0,0,0", planet_weight="0")
            self.assertEqual([f for f in scan_mod(mod).findings if f.id == "procgen-mod-body-leak"], [])

    def test_probe_config_carries_systems_and_body_weights(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = build_probe_config(_mod(Path(directory)))
        self.assertEqual(config["mod_systems"], ["Zorg Zeta"])
        self.assertEqual(config["mod_body_types"], {"star_zorg": 105.0, "zorg_planet": 10.0, "zorg_unused": 0.0})


if __name__ == "__main__":
    unittest.main()
