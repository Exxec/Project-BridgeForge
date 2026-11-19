"""Side-by-side checks between two builds (ROADMAP-3 item 91, 2026-11-15): which CLEAN mods touch changed API (live-test
order), content ids new vanilla now also defines, links the new core restores, helpers vanilla now provides, and how
vanilla's own source migrated each changed call (`vanilla-migration`)."""
from __future__ import annotations

import time
import unittest
import zipfile
from pathlib import Path

from bridgeforge.target_bump import catalogue, render_catalogue
from bridgeforge.target_delta import changed_api, id_collisions, now_provides, touches
from bridgeforge.target_impact import target_impact
from bridgeforge.vanilla_migration import call_sites, changed_members, vanilla_migration
from tests.support import javac_path, resolved_temp_dir
from tests.test_jar_linkage import _compile, _jar
from tests.test_target_impact import NEW_CORE, OLD_CORE, _mod

_UTIL = "com/fs/starfarer/api/util/"
OLD = {**OLD_CORE, _UTIL + "Misc.java": "package com.fs.starfarer.api.util; public class Misc { public static int gone() { return 0; } }"}
NEW = {**NEW_CORE, _UTIL + "Misc.java": "package com.fs.starfarer.api.util; public class Misc { public static int gone() { return 0; }"
                                       " public static float fluxFraction(Object ship) { return 0f; } }"}
USER = {"mod/Uses.java": "package mod; import com.fs.starfarer.api.combat.*;\n"
                         "public class Uses { boolean t(ShipAPI s) { return h(s); } boolean h(ShipAPI s) { return s == null; } }"}
GONE = {"mod/Gone.java": "package mod; public class Gone { int g() { return com.fs.starfarer.api.util.Misc.gone(); } }"}


def _ship_csv(root: Path, *ids: str) -> None:
    (root / "data" / "hullmods").mkdir(parents=True, exist_ok=True)
    (root / "data" / "hullmods" / "hull_mods.csv").write_text("name,id\n" + "".join(f"{i},{i}\n" for i in ids), encoding="utf-8")


class SideBySideTests(unittest.TestCase):
    def setUp(self) -> None:
        self.javac = javac_path()
        if self.javac is None:
            self.skipTest("no JDK found")

    def _cores(self, root: Path) -> tuple[Path, Path, Path]:
        old_classes = _compile(self.javac, root / "oldbuild", OLD)
        _jar(old_classes, root / "old" / "starfarer.api.jar")
        _jar(_compile(self.javac, root / "newbuild", NEW), root / "new" / "starfarer.api.jar")
        return root / "old", root / "new", old_classes

    def test_changed_api_lists_changed_classes_and_brand_new_names(self) -> None:
        with resolved_temp_dir() as root:
            old, new, _ = self._cores(root)
            delta = changed_api(str(old), str(new))
            self.assertIn("isBeingIgnored", delta["classes"]["com/fs/starfarer/api/combat/ShipAPI"])
            self.assertEqual(delta["new_names"][("fluxFraction", 1)], _UTIL + "Misc")
            self.assertNotIn(("isBeingIgnored", 1), delta["new_names"])  # an overload of an old name is not new

    def test_clean_mod_touching_changed_classes_is_ranked_and_gone_links_are_reported(self) -> None:
        with resolved_temp_dir() as root:
            old, new, old_classes = self._cores(root)
            queue = root / "queue"
            _mod(queue, "uses", {"id": "uses"}, _compile(self.javac, root / "usesbuild", USER, classpath=old_classes))
            _mod(queue, "plain", {"id": "plain"}, None)
            src = _mod(queue, "src", {"id": "src"}, None)
            (src / "S.java").write_text("import com.fs.starfarer.api.combat.ShipAPI;\nclass S { boolean b(ShipAPI s) { return s.isBeingIgnored(); } }",
                                        encoding="utf-8")
            result = target_impact([queue], old, new)
            by = {r["id"]: r for r in result["records"]}
            self.assertEqual(by["uses"]["verdict"], "CLEAN")
            self.assertEqual(by["uses"]["touches"]["classes"], ["com.fs.starfarer.api.combat.ShipAPI"])
            self.assertEqual(by["plain"]["touches"], {"classes": [], "members": []})
            self.assertIn("com.fs.starfarer.api.combat.ShipAPI.isBeingIgnored", by["src"]["touches"]["members"])
            text = render_catalogue("new", "old", catalogue(result), False)
            self.assertIn("## Live-test order for CLEAN mods", text)
            self.assertRegex(text, r"\| [^|\n]*uses \| 0: ")

    def test_links_restored_by_the_new_core_are_listed(self) -> None:
        with resolved_temp_dir() as root:
            old_classes = _compile(self.javac, root / "oldbuild", OLD_CORE)  # old has no Misc
            _jar(old_classes, root / "old" / "starfarer.api.jar")
            new_classes = _compile(self.javac, root / "newbuild", NEW)
            _jar(new_classes, root / "new" / "starfarer.api.jar")
            queue = root / "queue"
            _mod(queue, "gone", {"id": "gone"}, _compile(self.javac, root / "gonebuild", GONE, classpath=new_classes))
            record = target_impact([queue], root / "old", root / "new")["records"][0]
            self.assertEqual(record["verdict"], "CLEAN")
            self.assertTrue(any("Misc" in m for m in record["resolved_on_new"]))

    def test_new_vanilla_id_collision_is_review_and_now_provides_is_information(self) -> None:
        with resolved_temp_dir() as root:
            old, new, _ = self._cores(root)
            _ship_csv(old, "onslaught")
            _ship_csv(new, "onslaught", "mirage")
            mod = _mod(root / "queue", "m", {"id": "m"}, None)
            _ship_csv(mod, "mirage", "onslaught", "mine")
            (mod / "H.java").write_text("class H { public static float fluxFraction(Object s) { return 1f; } }", encoding="utf-8")
            self.assertEqual(id_collisions(mod, old, new), [{"kind": "new-vanilla-id-collision", "detail": "hullmod:mirage"}])
            self.assertEqual([h["kind"] for h in now_provides(mod, old, new)], ["vanilla-now-provides"])
            record = target_impact([root / "queue"], old, new)["records"][0]
            self.assertEqual(record["verdict"], "REVIEW")
            self.assertEqual(len(record["next"]), 1)  # the collision; the lead is information only

    def test_static_scan_does_not_backtrack_on_long_lines(self) -> None:
        with resolved_temp_dir() as root:
            old, new, _ = self._cores(root)
            mod = _mod(root / "queue", "long", {"id": "long"}, None)
            line = "static " + "a, " * 20000 + "fluxFraction"
            (mod / "L.java").write_text(f"class L {{ {line} }}", encoding="utf-8")
            started = time.process_time()  # CPU seconds, not a busy runner's wall clock (96.5 C7)
            now_provides(mod, old, new)
            touches(mod, [], old, new)
            self.assertLess(time.process_time() - started, 5.0)


def _api_zip(path: Path, files: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text)


class VanillaMigrationTests(unittest.TestCase):
    def test_call_sites_skip_declarations_and_comments(self) -> None:
        text = ("class A {\n public static String pick(Object f, Object g) { return null; }\n"
                " void u() { pick(a, b); // pick(c)\n  return pick(x, y); }\n}")
        sites = call_sites({"A.java": __import__("bridgeforge.vanilla_migration", fromlist=["_sources"])._COMMENTS.sub(
            lambda m: " " * len(m.group(0)), text)}, "A", "pick")
        self.assertEqual([s["args"] for s in sites["A.java"]], [["a", "b"], ["x", "y"]])

    def test_rule_backed_by_vanilla_and_rule_that_differs(self) -> None:
        with resolved_temp_dir() as root:
            old_src = {"com/fs/starfarer/api/impl/campaign/events/P.java":
                       "class P { void a() { OfficerManagerEvent.pickPortraitPreferNonDuplicate(f, g); new ShipAIConfig(); } }"}
            new_src = {"com/fs/starfarer/api/impl/campaign/events/P.java":
                       "class P { void a() { OfficerManagerEvent.pickPortraitPreferNonDuplicate(f, g, null); new ShipAIConfig(ship); } }"}
            for core, files in (("old", old_src), ("new", new_src)):
                _api_zip(root / core / "starfarer.api.zip", files)
                (root / core / "starfarer.api.jar").write_bytes(b"")
            api = {"changed_classes": {
                "com.fs.starfarer.api.impl.campaign.events.OfficerManagerEvent": {"methods_removed": [
                    {"name": "pickPortraitPreferNonDuplicate", "signature": "String pickPortraitPreferNonDuplicate(FactionAPI, Gender)",
                     "same_name_in_class": ["String pickPortraitPreferNonDuplicate(FactionAPI, Gender, Random)"]}]},
                "com.fs.starfarer.api.combat.ShipAIConfig": {"methods_removed": [
                    {"name": "<init>", "signature": "ShipAIConfig()", "same_name_in_class": ["ShipAIConfig(ShipAPI)"]}]}}}
            self.assertEqual(len(changed_members(api)), 2)
            result = vanilla_migration(root / "old", root / "new", api)
            verdicts = {m["name"]: m["rules"][0]["verdict"] for m in result["members"]}
            self.assertEqual(verdicts, {"pickPortraitPreferNonDuplicate": "BACKED", "<init>": "DIFFERS"})


if __name__ == "__main__":
    unittest.main()
