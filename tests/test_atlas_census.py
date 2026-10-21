"""Atlas census (ROADMAP-3 81.1/81.3/81.4): API usage, save risk, library calls. All STATIC reads of bytes and text."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout

from bridgeforge import atlas
from bridgeforge.atlas_census_report import api_how, api_usage
from bridgeforge.cli import main
from tests.test_atlas import build, make_mod, make_vanilla, temp_root
from tests.test_atlas_calls import INVOKE_INTERFACE, INVOKE_STATIC, RETURN, STRING_CALL, ClassBuilder, jar_mod

SECTOR = "com/fs/starfarer/api/campaign/SectorAPI"
CAMPAIGN_UI = "com/fs/starfarer/api/campaign/CampaignUIAPI"
GLOBAL = "com/fs/starfarer/api/Global"


def sector_user(name: str, owner: str, method: str) -> bytes:
    b = ClassBuilder(name)
    b.method("run", b.invoke(GLOBAL, "getSector", "()L" + SECTOR + ";", INVOKE_STATIC) + b.ldc("hi")
             + b.invoke(owner, method, STRING_CALL, INVOKE_INTERFACE) + RETURN)
    return b.build()


class ApiCensusTests(unittest.TestCase):
    def census(self, root):
        db, _ = build(root)
        return atlas.connect(db)

    def test_jar_and_loose_api_references_are_counted_per_mod(self):
        java = ("package r;\nimport com.fs.starfarer.api.Global;\nimport com.fs.starfarer.api.util.Misc;\n"
                "public class R { void go() { Global.getSector(); Misc.getPlayerShip(); int c = Misc.MAX; } }\n")
        with temp_root() as root:
            make_vanilla(root)
            jar_mod(root / "mods", "old", {"a/One.class": sector_user("a/One", SECTOR, "addMessage"),
                                           "a/Two.class": sector_user("a/Two", SECTOR, "addMessage")})
            jar_mod(root / "mods", "new", {"b/One.class": sector_user("b/One", CAMPAIGN_UI, "addMessage")})
            make_mod(root / "mods", "scripty", {"data/scripts/R.java": java})
            conn = self.census(root)
            data = api_usage(conn, "com.fs.starfarer.api.campaign.SectorAPI.addMessage")
            (entry,) = data["shown"]
            self.assertEqual((entry["kind"], entry["mod_count"], entry["total"]), ("method", 1, 2))
            self.assertEqual(entry["mods"][0], {"mod": "old", "count": 2, "example": "jars/x.jar!a/One.class"})
            sector = api_usage(conn, "com.fs.starfarer.api.Global.getSector")["shown"][0]
            self.assertEqual({m["mod"] for m in sector["mods"]}, {"old", "new", "scripty"})
            loose = {r["symbol"] for r in conn.execute("SELECT symbol FROM census WHERE mod = 'scripty'")}
            self.assertEqual(loose, {"com.fs.starfarer.api.Global", "com.fs.starfarer.api.Global.getSector",
                                     "com.fs.starfarer.api.util.Misc", "com.fs.starfarer.api.util.Misc.getPlayerShip",
                                     "com.fs.starfarer.api.util.Misc.MAX"})

    def test_api_how_lists_candidates_and_the_mods_that_use_them(self):
        catalogue = {"note": "n", "removed_classes": [], "changed_classes": {
            "com.fs.starfarer.api.campaign.SectorAPI": {"methods_removed": [{
                "name": "addMessage", "descriptor": "(Ljava/lang/String;)V", "signature": "void addMessage(String)",
                "same_name_in_class": [], "same_signature_elsewhere": ["com.fs.starfarer.api.campaign.CampaignUIAPI.addMessage(String)"]}],
                "fields_removed": [], "methods_added": []}}}
        with temp_root() as root:
            make_vanilla(root)
            jar_mod(root / "mods", "old", {"a/One.class": sector_user("a/One", SECTOR, "addMessage")})
            jar_mod(root / "mods", "new", {"b/One.class": sector_user("b/One", CAMPAIGN_UI, "addMessage")})
            data = api_how(self.census(root), catalogue, "SectorAPI.addMessage")
            (removed,) = data["removed"]
            self.assertEqual(removed["still_referenced_by"], ["old"])
            (candidate,) = removed["candidates"]
            self.assertEqual((candidate["candidate"], candidate["mod_count"]), ("com.fs.starfarer.api.campaign.CampaignUIAPI.addMessage", 1))
            self.assertEqual(candidate["mods"][0]["mod"], "new")

    def test_cli_api_usage_and_missing_atlas(self):
        with temp_root() as root:
            make_vanilla(root)
            jar_mod(root / "mods", "old", {"a/One.class": sector_user("a/One", SECTOR, "addMessage")})
            db, _ = build(root)
            out = io.StringIO()
            with redirect_stdout(out):
                code = main(["atlas", "api-usage", "com.fs.starfarer.api.campaign.SectorAPI", "--db", str(db)])
            self.assertEqual(code, 0)
            self.assertIn("SectorAPI.addMessage [method]: 1 mod(s)", out.getvalue())
            err = io.StringIO()
            with redirect_stderr(err):
                self.assertEqual(main(["atlas", "api-usage", "x", "--db", str(root / "none.sqlite")]), 2)


if __name__ == "__main__":
    unittest.main()
