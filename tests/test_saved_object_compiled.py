"""saved-object-holds-market-ref for compiled classes (item 73 F2): a jar script or listener that keeps a MarketAPI/PlanetAPI field."""
from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

from bridgeforge.saved_object_scan import compiled_entity_fields, saved_interface
from bridgeforge.scanner import scan_mod
from tests.support import resolved_temp_dir
from tests.test_jar_linkage import _compile, _jar

API = {
    "com/fs/starfarer/api/EveryFrameScript.java": "package com.fs.starfarer.api; public interface EveryFrameScript { void advance(float a); }",
    "com/fs/starfarer/api/campaign/econ/MarketAPI.java": "package com.fs.starfarer.api.campaign.econ; public interface MarketAPI {}",
    "com/fs/starfarer/api/campaign/CampaignFleetAPI.java": "package com.fs.starfarer.api.campaign; public interface CampaignFleetAPI {}",
}
HEADER = ("package data; import com.fs.starfarer.api.EveryFrameScript; import com.fs.starfarer.api.campaign.econ.MarketAPI; "
          "import com.fs.starfarer.api.campaign.CampaignFleetAPI;\n")
SAVED = {"data/Holder.java": HEADER + "public class Holder implements EveryFrameScript { MarketAPI market; public void advance(float a) {} }"}
TRANSIENT = {"data/Holder.java": HEADER + "public class Holder implements EveryFrameScript { transient MarketAPI market; public void advance(float a) {} }"}
FLEET_ONLY = {"data/Holder.java": HEADER + "public class Holder implements EveryFrameScript { CampaignFleetAPI fleet; public void advance(float a) {} }"}
NOT_SAVED = {"data/Holder.java": HEADER + "public class Holder { MarketAPI market; }"}
GAME_COPY = {"com/fs/starfarer/api/impl/Copy.java": "package com.fs.starfarer.api.impl; import com.fs.starfarer.api.EveryFrameScript; "
             "import com.fs.starfarer.api.campaign.econ.MarketAPI; public class Copy implements EveryFrameScript { MarketAPI market; public void advance(float a) {} }"}


class SavedObjectCompiledTests(unittest.TestCase):
    def setUp(self) -> None:
        self.javac = shutil.which("javac")
        if self.javac is None:
            self.skipTest("no javac on PATH")

    def _hits(self, sources: dict[str, str]):
        with resolved_temp_dir() as base:
            root = Path(base)
            api = _compile(self.javac, root / "api", API)
            mod = root / "mod"
            _jar(_compile(self.javac, root / "build", sources, classpath=api), mod / "jars" / "m.jar")
            (mod / "mod_info.json").write_text(json.dumps({"id": "m", "name": "m", "version": "1", "gameVersion": "0.98a-RC8",
                                                           "jars": ["jars/m.jar"]}), encoding="utf-8")
            return [f for f in scan_mod(mod).findings if f.id == "saved-object-holds-market-ref"]

    def test_script_with_a_market_field_is_flagged_with_evidence(self) -> None:
        hits = self._hits(SAVED)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].classification, "REVIEW")
        self.assertIn("saved:implements EveryFrameScript", hits[0].evidence)
        self.assertIn("field:MarketAPI market", hits[0].evidence)

    def test_transient_fleet_only_unsaved_and_game_copies_are_quiet(self) -> None:
        for name, sources in (("transient", TRANSIENT), ("fleet only", FLEET_ONLY), ("not a script", NOT_SAVED), ("game copy", GAME_COPY)):
            with self.subTest(name):
                self.assertEqual(self._hits(sources), [])

    def test_pure_helpers(self) -> None:
        self.assertEqual(saved_interface(["java/lang/Runnable", "com/fs/starfarer/api/campaign/listeners/EconomyTickListener"]), "EconomyTickListener")
        self.assertIsNone(saved_interface(["java/lang/Runnable"]))
        fields = [("m", "Lcom/fs/starfarer/api/campaign/econ/MarketAPI;", False, False), ("s", "Lcom/fs/starfarer/api/campaign/econ/MarketAPI;", True, False)]
        self.assertEqual(compiled_entity_fields(fields, frozenset()), ["MarketAPI m"])
        self.assertEqual(compiled_entity_fields(fields, frozenset({"m"})), [])


if __name__ == "__main__":
    unittest.main()
