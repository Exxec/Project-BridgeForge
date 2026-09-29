"""legacy-market-condition: pre-0.9 market conditions that RC8 removed (FlowerGod, FG-SOLO-20260928)."""
from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from bridgeforge.scanner import scan_mod
from tests.test_personality_ids import _class_with_strings


def _mod(root: Path) -> Path:
    mod = root / "mod"
    mod.mkdir()
    (mod / "mod_info.json").write_text(json.dumps({"id": "m", "name": "M", "version": "1", "gameVersion": "0.98a-RC8"}), encoding="utf-8")
    return mod


def _hits(mod: Path) -> list:
    return [f for f in scan_mod(mod).findings if f.id == "legacy-market-condition"]


class LegacyMarketConditionTests(unittest.TestCase):
    def test_jar_class_adding_a_removed_condition_is_manual(self) -> None:
        # FlowerGod's Shek_KongEvening adds antimatter_fuel_production and eight more; RC8 Fatal at New Game.
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory))
            (mod / "jars").mkdir()
            with zipfile.ZipFile(mod / "jars" / "m.jar", "w") as archive:
                archive.writestr("demo/Gen.class", _class_with_strings("demo/Gen", ["antimatter_fuel_production", "arid"], ["addCondition"]))
            hits = _hits(mod)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].classification, "MANUAL")
        self.assertIn("antimatter_fuel_production -> fuelprod", hits[0].explanation)

    def test_loose_source_hit_and_ported_code_is_quiet(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory))
            source = mod / "data" / "scripts" / "Gen.java"
            source.parent.mkdir(parents=True)
            source.write_text('class Gen { void g(M m) { m.addCondition("ore_complex"); } }\n', encoding="utf-8")
            unported = _hits(mod)
            # Ported code maps the old ids and calls addIndustry, which 0.8.1a's MarketAPI lacked.
            source.write_text('class Gen { void g(M m) { if ("ore_complex".equals(x)) m.addIndustry("mining"); else m.addCondition(x); } }\n', encoding="utf-8")
            ported = _hits(mod)
        self.assertEqual(len(unported), 1)
        self.assertEqual(ported, [])

    def test_an_id_that_is_also_an_rc8_industry_alone_is_quiet(self) -> None:
        # The 2026-09-28 sweep: seven classes (Omega-Trauma's, live-validated) hold "spaceport" for industry lookups.
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory))
            (mod / "jars").mkdir()
            with zipfile.ZipFile(mod / "jars" / "m.jar", "w") as archive:
                archive.writestr("demo/Post.class", _class_with_strings("demo/Post", ["spaceport"], ["addCondition"]))
            hits = _hits(mod)
        self.assertEqual(hits, [])

    def test_a_condition_the_mod_defines_itself_is_quiet(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory))
            source = mod / "data" / "scripts" / "Gen.java"
            source.parent.mkdir(parents=True)
            source.write_text('class Gen { void g(M m) { m.addCondition("spaceport"); } }\n', encoding="utf-8")
            (mod / "data" / "campaign").mkdir(parents=True)
            (mod / "data" / "campaign" / "market_conditions.csv").write_text("name,id\nPort,spaceport\n", encoding="utf-8")
            hits = _hits(mod)
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
