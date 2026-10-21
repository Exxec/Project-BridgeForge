"""Atlas census (ROADMAP-3 81.1/81.3/81.4): API usage, save risk, library calls. All STATIC reads of bytes and text."""
from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout

from bridgeforge import atlas
from bridgeforge.atlas_census_libs_report import libraries
from bridgeforge.atlas_census_report import api_how, api_usage, save_risk
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


MAP_PUT = ("java/util/Map", "put", "(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;")
ALOAD_0 = b"*"


def save_classes() -> dict[str, bytes]:
    unguarded = ClassBuilder("s/Unguarded", "com/fs/starfarer/api/BaseModPlugin")
    unguarded.method("onGameLoad", ALOAD_0 + unguarded.new("s/Tick") + unguarded.invoke(SECTOR, "addScript", "(Lcom/fs/starfarer/api/EveryFrameScript;)V", INVOKE_INTERFACE)
                     + unguarded.invoke("com/fs/starfarer/api/Global", "getPersistentData", "()Ljava/util/Map;", INVOKE_STATIC)
                     + unguarded.ldc("mymod_state") + unguarded.invoke(*MAP_PUT, INVOKE_INTERFACE) + RETURN, "(Z)V")
    guarded = ClassBuilder("s/Guarded", "com/fs/starfarer/api/BaseModPlugin")
    guarded.method("onGameLoad", ALOAD_0 + guarded.invoke(SECTOR, "hasScript", "(Ljava/lang/Class;)Z", INVOKE_INTERFACE)
                   + ALOAD_0 + guarded.new("s/Tick") + guarded.invoke(SECTOR, "addScript", "(Lcom/fs/starfarer/api/EveryFrameScript;)V", INVOKE_INTERFACE) + RETURN, "(Z)V")
    tick = ClassBuilder("s/Tick", "java/lang/Object", ("com/fs/starfarer/api/EveryFrameScript",))
    tick.field("cache", "Ljava/util/Map;", 0x0080).field("kept", "I", 0x0002).field("COUNT", "I", 0x0088)
    tick.method("readResolve", RETURN)
    return {"s/Unguarded.class": unguarded.build(), "s/Guarded.class": guarded.build(), "s/Tick.class": tick.build()}


LOOSE_SAVE = """package l;
public class Plug extends BaseModPlugin {
    public void onGameLoad(boolean newGame) {
        Global.getSector().addScript(new LTick());
        Global.getSector().getPersistentData().put("loose_key", 1);
        Global.getSector().getMemoryWithoutUpdate().set("$loose_flag", true);
    }
}
"""


LTICK_JAVA = """package l;
public class LTick implements EveryFrameScript { private transient int x; }
"""


class SaveRiskTests(unittest.TestCase):
    def test_save_risk_rows_from_jar_and_loose_script(self):
        with temp_root() as root:
            make_vanilla(root)
            jar_mod(root / "mods", "jarmod", save_classes())
            make_mod(root / "mods", "loosemod", {"data/scripts/Plug.java": LOOSE_SAVE,
                                                 "data/scripts/LTick.java": LTICK_JAVA})
            db, _ = build(root)
            conn = atlas.connect(db)
            rows = {(r["mod"], r["kind"], r["symbol"]) for r in conn.execute("SELECT * FROM census WHERE area = 'save'")}
            self.assertIn(("jarmod", "duplicate-script-risk", "s.Unguarded"), rows)
            self.assertNotIn(("jarmod", "duplicate-script-risk", "s.Guarded"), rows)
            self.assertIn(("jarmod", "persistent-key", "mymod_state"), rows)
            self.assertIn(("jarmod", "serialization-hook", "s.Tick.readResolve"), rows)
            self.assertIn(("jarmod", "transient-field", "s.Tick.cache"), rows)
            self.assertNotIn(("jarmod", "transient-field", "s.Tick.COUNT"), rows)
            self.assertIn(("loosemod", "duplicate-script-risk", "l.Plug"), rows)
            self.assertIn(("loosemod", "persistent-key", "loose_key"), rows)
            self.assertIn(("loosemod", "memory-key", "$loose_flag"), rows)
            self.assertIn(("loosemod", "transient-field", "l.LTick.x"), rows)
            leaders = save_risk(conn)["mods"]
            self.assertEqual({e["mod"] for e in leaders}, {"jarmod", "loosemod"})
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["atlas", "save-risk", "jarmod", "--db", str(db)]), 0)
            self.assertIn("duplicate-script-risk: s.Unguarded", out.getvalue())


def lib_class() -> bytes:
    b = ClassBuilder("m/UsesLibs")
    b.method("run", b.invoke("org/lazywizard/lazylib/MathUtils", "getDistance", "(II)F", INVOKE_STATIC)
             + b.invoke("org/magiclib/util/MagicRender", "battlespace", "(I)V", INVOKE_STATIC)
             + b.invoke("m/Own", "helper", "()V", INVOKE_STATIC) + RETURN)
    return b.build()


class LibraryCensusTests(unittest.TestCase):
    def test_library_calls_and_declared_versions(self):
        def info(mod_id: str, deps: list[dict]) -> str:
            return json.dumps({"id": mod_id, "name": mod_id, "version": "1", "jars": ["jars/x.jar"], "dependencies": deps})
        java = """package q;
import org.lazywizard.lazylib.MathUtils;
import exerelin.utilities.NexUtils;
public class Q { void go() { MathUtils.clamp(1, 2, 3); } }
"""
        with temp_root() as root:
            make_vanilla(root)
            jar_mod(root / "mods", "jarmod", {"m/UsesLibs.class": lib_class()},
                    {"mod_info.json": info("jarmod", [{"id": "lw_lazylib", "name": "LazyLib", "version": "2.8"}, {"id": "MagicLib", "version": "1.0.0"}])})
            make_mod(root / "mods", "loosemod", {"data/scripts/Q.java": java, "mod_info.json": json.dumps(
                {"id": "loosemod", "name": "loosemod", "version": "1", "dependencies": [{"id": "lw_lazylib", "version": {"major": "3", "minor": 0, "patch": "0"}}]})})
            db, _ = build(root)
            data = libraries(atlas.connect(db))
            by_name = {lib["library"]: lib for lib in data["libraries"]}
            self.assertEqual(set(by_name), {"LazyLib", "MagicLib", "Nexerelin", "pkg:m"})  # m/Own is not defined by the mod
            self.assertEqual(by_name["LazyLib"]["mods"], ["jarmod", "loosemod"])
            self.assertEqual(by_name["LazyLib"]["declared_versions"], {"2.8": ["jarmod"], "3.0.0": ["loosemod"]})
            symbols = {f["symbol"] for f in by_name["LazyLib"]["functions"]}
            self.assertIn("org.lazywizard.lazylib.MathUtils.getDistance", symbols)
            self.assertIn("org.lazywizard.lazylib.MathUtils.clamp", symbols)
            self.assertEqual(by_name["Nexerelin"]["undeclared_users"], [])
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["atlas", "libraries", "--db", str(db)]), 0)
            self.assertIn("LazyLib: 2 mod(s) call it", out.getvalue())


if __name__ == "__main__":
    unittest.main()
