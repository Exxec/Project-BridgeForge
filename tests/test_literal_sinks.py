"""94.G2 slice 13: a literal that only names an id is a mention, not a need (owner 2026-11-20)."""
from __future__ import annotations

import json
import shutil
import struct
import subprocess
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from bridgeforge.genome import literal_sinks
from bridgeforge.genome.gene import describe
from bridgeforge.genome.literal_sinks import MENTION_SINKS, NOT_LOADED, class_literal_sinks, is_mention
from bridgeforge.scan.scan_classfile import _parse_class_file
from bridgeforge.vendor_plan import vendor_plan
from tests.support import resolved_temp_dir, write_text as _write

STUBS = {
    "com/fs/starfarer/api/combat/ShipVariantAPI.java":
        "package com.fs.starfarer.api.combat;\npublic interface ShipVariantAPI { boolean hasHullMod(String id); void addMod(String id);"
        " void removeMod(String id); }\n",
    "com/fs/starfarer/api/combat/MutableStat.java":
        "package com.fs.starfarer.api.combat;\npublic class MutableStat { public void modifyMult(String source, float value) {}"
        " public void modifyPercent(String source, float value) {} public void modifyFlat(String source, float value) {}"
        " public void unmodify(String source) {} }\n",
    "com/fs/starfarer/api/combat/StatBonus.java":
        "package com.fs.starfarer.api.combat;\npublic class StatBonus { public void modifyPercent(String source, float value) {} }\n",
    "com/fs/starfarer/api/combat/CombatEngineAPI.java":
        "package com.fs.starfarer.api.combat;\npublic interface CombatEngineAPI { void maintainStatusForPlayerShip(Object key, "
        "String sprite, String title, String data, boolean debuff); }\n",
    "com/fs/starfarer/api/loading/WeaponSpecAPI.java":
        "package com.fs.starfarer.api.loading;\npublic interface WeaponSpecAPI { boolean hasTag(String tag); }\n",
}
# One call per mention sink, in MENTION_SINKS order: each literal must reach exactly that sink (review 2026-11-20).
SINKS_PROBE = """package demo;
import com.fs.starfarer.api.combat.*;
import com.fs.starfarer.api.loading.WeaponSpecAPI;
public class Sinks {
    void all(java.util.Collection<String> c, java.util.LinkedHashSet<String> s, ShipVariantAPI v, MutableStat m, StatBonus b,
             CombatEngineAPI e, WeaponSpecAPI w) {
        c.contains("sink_0"); s.contains("sink_1"); "text".contains("sink_2"); v.hasHullMod("sink_3"); v.removeMod("sink_4");
        m.modifyMult("sink_5", 1f); m.modifyPercent("sink_6", 1f); m.modifyFlat("sink_7", 1f); m.unmodify("sink_8");
        b.modifyPercent("sink_9", 1f); e.maintainStatusForPlayerShip("sink_10", "s", "t", "d", false); w.hasTag("sink_11");
    }
}
"""
PROBE = """package demo;
import com.fs.starfarer.api.combat.MutableStat;
import com.fs.starfarer.api.combat.ShipVariantAPI;
public class Probe {
    public static final String UNUSED = "demo_unused_const";
    private final java.util.Map<String, Integer> table = new java.util.HashMap<>();
    void check(ShipVariantAPI v) { v.hasHullMod("demo_checked"); }
    void stat(MutableStat s) { s.modifyMult("demo_key", 2f); }
    void add(ShipVariantAPI v) { v.addMod("demo_added"); }
    void both(ShipVariantAPI v) { v.hasHullMod("demo_both"); v.addMod("demo_both"); }
    void stored(ShipVariantAPI v) { String s = "demo_stored"; v.addMod(s); }
    void put() { table.put("demo_table", 1); }
    void branch(boolean b, ShipVariantAPI v) { v.hasHullMod(b ? "demo_a" : "demo_b"); }
    void dup(ShipVariantAPI v) { String s; v.hasHullMod(s = "demo_dup"); v.addMod(s); }
}
"""


def _javac() -> str | None:
    return shutil.which("javac")


def _compile(root: Path, sources: dict[str, str]) -> Path:
    src, out = root / "src", root / "classes"
    for rel, text in {**STUBS, **sources}.items():
        _write(src / rel, text)
    subprocess.run([_javac(), "-encoding", "UTF-8", "-proc:none", "-d", str(out), *map(str, src.rglob("*.java"))],
                   check=True, capture_output=True)
    return out


@unittest.skipUnless(_javac(), "needs javac")
class LiteralSinkTests(unittest.TestCase):
    def test_each_literal_is_judged_by_the_call_that_takes_it(self) -> None:
        with resolved_temp_dir() as root:
            data = (_compile(root, {"demo/Probe.java": PROBE}) / "demo" / "Probe.class").read_bytes()
        sinks = class_literal_sinks(data, _parse_class_file(data).string_constants)
        self.assertEqual(sinks["demo_checked"], {"com/fs/starfarer/api/combat/ShipVariantAPI.hasHullMod#0"})
        self.assertEqual(sinks["demo_key"], {"com/fs/starfarer/api/combat/MutableStat.modifyMult#0"})
        self.assertEqual(sinks["demo_added"], {"com/fs/starfarer/api/combat/ShipVariantAPI.addMod#0"})
        self.assertEqual(sinks["demo_unused_const"], {NOT_LOADED})
        self.assertEqual(sinks["demo_stored"], {"unknown: stored"})
        self.assertEqual(sinks["demo_table"], {"java/util/Map.put#0"})
        self.assertEqual(sinks["demo_dup"], {"unknown: duplicated"})  # its copy goes on to addMod: not followed, kept
        mentions = {value for value, where in sinks.items() if is_mention(where)}
        self.assertEqual(mentions & {f"demo_{n}" for n in ("checked", "key", "unused_const", "added", "both", "stored", "table", "a",
                                                           "b")}, {"demo_checked", "demo_key", "demo_unused_const"})
        self.assertFalse(is_mention(sinks["demo_both"]))  # one use among mentions keeps it a need
        self.assertTrue(all(s.startswith("unknown") for s in sinks["demo_a"] | sinks["demo_b"]))  # a branch: not followed

    def test_every_mention_sink_is_reached_by_its_own_call(self) -> None:
        with resolved_temp_dir() as root:
            data = (_compile(root, {"demo/Sinks.java": SINKS_PROBE}) / "demo" / "Sinks.class").read_bytes()
        sinks = class_literal_sinks(data, _parse_class_file(data).string_constants)
        self.assertEqual({f"sink_{i}": sinks[f"sink_{i}"] for i in range(len(MENTION_SINKS))},
                         {f"sink_{i}": {key} for i, key in enumerate(MENTION_SINKS)})  # a typo in the table fails here

    def test_an_unreadable_method_keeps_every_literal_a_need(self) -> None:
        with resolved_temp_dir() as root:
            data = (_compile(root, {"demo/Probe.java": PROBE}) / "demo" / "Probe.class").read_bytes()
        with mock.patch.object(literal_sinks, "instructions", side_effect=struct.error("truncated")):
            sinks = class_literal_sinks(data, ["demo_checked"])
        self.assertEqual(sinks, {"demo_checked": {"unknown: the class could not be read"}})
        self.assertFalse(is_mention(sinks["demo_checked"]))

    def test_a_hull_mod_that_only_checks_another_does_not_bring_it(self) -> None:
        checker = ("package demo;\nimport com.fs.starfarer.api.combat.*;\npublic class Checker {\n"
                   "    public boolean applies(ShipVariantAPI v) { return !v.hasHullMod(\"demo_other\") && !v.hasHullMod(\"demo_port\"); }\n"
                   "    public void apply(MutableStat s) { s.modifyMult(\"demo_checker\", 2f); }\n}\n")  # its own id as a key
        with resolved_temp_dir() as root:
            classes = _compile(root, {"demo/Checker.java": checker, "demo/Other.java": "package demo;\npublic class Other {}\n"})
            mod = root / "mod"
            _write(mod / "mod_info.json", json.dumps({"id": "demo", "name": "Demo", "jars": ["jars/demo.jar"]}))
            _write(mod / "data/hullmods/hull_mods.csv", "name,id,script\nChecker,demo_checker,demo.Checker\nOther,demo_other,demo.Other\n")
            _write(mod / "data/campaign/industries.csv", "id,name\ndemo_port,Port\n")  # a campaign id, mentioned only
            (mod / "jars").mkdir()
            with zipfile.ZipFile(mod / "jars/demo.jar", "w") as jar:
                for name in ("Checker", "Other"):
                    jar.write(classes / "demo" / f"{name}.class", f"demo/{name}.class")
            gene = describe(mod, "hullmod:demo_checker")
        self.assertEqual(gene["provides"], ["hullmod:demo_checker"])
        self.assertFalse([m for m in gene["members"] if "demo_other" in m["path"] or "Other" in m["path"]])
        mention = [s for s in gene["unknowns"]["suspects"] if "a mention, not a need" in s["reason"]]
        self.assertEqual([(s["path"], s["mentions"]) for s in mention],
                         [("jars/demo.jar!demo/Checker.class", ["demo_other", "demo_port"])])  # not its own demo_checker


class SamePackageLiteralTests(unittest.TestCase):
    def test_a_string_equal_to_a_same_package_class_name_is_no_use_of_it(self) -> None:
        # Eridani: hasHullMod("ECE_FluxEMPHullMod") in data.hullmods, where a class of that name also lives (slice 13).
        with resolved_temp_dir() as root:
            mod = root / "mod"
            _write(mod / "mod_info.json", json.dumps({"id": "demo", "name": "Demo"}))
            _write(mod / "data/hullmods/hull_mods.csv", "name,id,script\nA,demo_a,data.hullmods.Alpha\nB,demo_b,data.hullmods.Beta\n")
            _write(mod / "data/hullmods/Alpha.java", 'package data.hullmods;\npublic class Alpha {\n    String other = "Beta";\n}\n')
            _write(mod / "data/hullmods/Beta.java", "package data.hullmods;\npublic class Beta {}\n")
            _write(mod / "data/hullmods/Gamma.java", "package data.hullmods;\npublic class Gamma {}\n")
            _write(mod / "data/hullmods/Delta.java", "package data.hullmods;\npublic class Delta { Gamma g; }\n")
            _write(mod / "data/hullmods/Epsilon.java", "package data.hullmods;\npublic class Epsilon {\n"
                   "    char q = '\"'; Gamma g; String s = \"x\";\n}\n")  # a char literal opens no string (review)
            alpha = {e["path"] for e in vendor_plan(mod, ["hullmod:demo_a"])["include"]}
            delta = {e["path"] for e in vendor_plan(mod, [], classes=["data.hullmods.Delta"])["include"]}
            epsilon = {e["path"] for e in vendor_plan(mod, [], classes=["data.hullmods.Epsilon"])["include"]}
        self.assertNotIn("data/hullmods/Beta.java", alpha)
        self.assertIn("data/hullmods/Gamma.java", delta)  # a real use by name still counts
        self.assertIn("data/hullmods/Gamma.java", epsilon)


if __name__ == "__main__":
    unittest.main()
