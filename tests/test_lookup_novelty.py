"""lookup (query surface + inspection priority) and novelty (corpus comparison), 2026-09-14."""

import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.behavior_discovery import write_archaeology
from bridgeforge.lookup import lookup
from bridgeforge.novelty import api_class, compare, fingerprint, novelty

PLUGIN = """package data.scripts;
import com.fs.starfarer.api.BaseModPlugin;
import exerelin.campaign.SectorManager;
public class DemoModPlugin extends BaseModPlugin {
    private static boolean seeded;
    public void onNewGame() { seeded = SectorManager.getCorvusMode(); }
}
"""
HELPER = """package data.scripts;
public class DemoHelper { public static int twice(int x) { return 2 * x; } }
"""


def _mod(root: Path) -> Path:
    mod = root / "Demo" / "working"
    (mod / "src" / "data" / "scripts").mkdir(parents=True)
    (mod / "mod_info.json").write_text(json.dumps({"id": "demo", "name": "Demo", "version": "1", "gameVersion": "0.98a-RC8", "modPlugin": "data.scripts.DemoModPlugin"}), encoding="utf-8")
    (mod / "src" / "data" / "scripts" / "DemoModPlugin.java").write_text(PLUGIN, encoding="utf-8")
    (mod / "src" / "data" / "scripts" / "DemoHelper.java").write_text(HELPER, encoding="utf-8")
    return mod


class LookupTests(unittest.TestCase):
    def test_lookup_joins_definition_lifecycle_persistence_and_external_references(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory).resolve())
            result = lookup(mod, "DemoModPlugin")
        self.assertIn("built in memory", result["graph"])
        item = result["items"][0]
        self.assertEqual(item["name"], "data.scripts.DemoModPlugin")
        self.assertIn("source:src/data/scripts/DemoModPlugin.java", item["definitions"])
        self.assertTrue(any(hook.startswith("onNewGame") for hook in item["lifecycle_hooks"]))
        self.assertTrue(any(entry.startswith("seeded") for entry in item["persistent_state"]))
        self.assertEqual(item["external_mods"], ["Nexerelin"])
        reasons = " ".join(item["priority_reasons"])
        for expected in ("lifecycle hook", "persistence", "Nexerelin"):
            self.assertIn(expected, reasons)
        self.assertGreater(item["priority"], 0)

    def test_saved_graph_is_used_until_the_mod_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory).resolve())
            discovery = mod.parent / "reports" / "discovery" / "working"
            write_archaeology(mod, discovery)
            self.assertEqual(lookup(mod, "DemoHelper")["graph"], str(discovery / "archaeology" / "architecture.json"))
            (mod / "src" / "data" / "scripts" / "DemoHelper.java").write_text(HELPER.replace("2 * x", "3 * x"), encoding="utf-8")
            self.assertIn("stale", lookup(mod, "DemoHelper")["graph"])

    def test_treasure_map_ranks_the_plugin_above_the_plain_helper(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory).resolve())
            ranked = lookup(mod, top=5)["treasure_map"]
        self.assertEqual(ranked[0]["name"], "data.scripts.DemoModPlugin")
        # Nothing calls the helper: that alone is worth a look ("no known caller"), but ranks below the plugin.
        helper = next(entry for entry in ranked if entry["name"] == "data.scripts.DemoHelper")
        self.assertEqual([reason.split(" ", 1)[1] for reason in helper["reasons"]], ["no known reference (every checked domain)"])
        self.assertLess(helper["priority"], ranked[0]["priority"])


class NoveltyTests(unittest.TestCase):
    GRAPH = {
        "mod_id": "new",
        "nodes": [{"id": "class:a.B", "kind": "class", "name": "a.B"}, {"id": "symbol:com.fs.starfarer.api.campaign.SectorAPI", "kind": "symbol"}, {"id": "data:x", "kind": "data", "path": "data/hullmods/hull_mods.csv"}],
        "edges": [{"source": "class:a.B", "target": "symbol:com.fs.starfarer.api.campaign.SectorAPI", "relation": "bytecode-reference"},
                  {"source": "data:x", "target": "class:a.B", "relation": "data-reference"}],
        "lifecycle": {"hooks": [{"hook": "onNewGame", "class": "a.B"}], "registrations": [{"call": "addPlugin", "owner": "a.B"}]},
        "scanner_findings": [{"id": "rules-condition-merged-lines", "evidence": []}, {"id": "hard-coded-campaign-system-reference", "evidence": ["askonia", "ownership: external-or-core-unresolved"]}],
        "no_known_reference": [],
    }

    def test_fingerprint_and_comparison_against_a_corpus(self) -> None:
        fp = fingerprint(self.GRAPH)
        self.assertEqual(fp["features"]["api"], ["com.fs.starfarer.api.campaign.SectorAPI"])
        self.assertIn("data-reference|data:data/hullmods/*.csv|class", fp["features"]["structure"])
        self.assertEqual(fp["features"]["lifecycle"], ["hook:onNewGame", "register:addPlugin"])
        self.assertEqual(len(fp["weak"]), 1)
        old = {"mod_id": "old", "features": {"api": [], "lifecycle": ["hook:onNewGame"], "structure": ["data-reference|data:data/hullmods/*.csv|class"], "finding": ["finding:rules-condition-merged-lines"]}}
        report = compare(fp, [old, fp])  # its own entry is ignored
        self.assertEqual(report["corpus_size"], 1)
        self.assertTrue(report["small_corpus"])
        self.assertEqual(report["new_api_usages"], 1)
        self.assertEqual(report["new_lifecycle_patterns"], 1)  # addPlugin
        self.assertEqual(report["patterns_seen"], 3)  # onNewGame, the hull_mods structure, the finding
        self.assertEqual(report["unusual_structures"], 2)  # both seen in fewer than 2 other mods
        self.assertEqual(report["weak_ownership"], 1)

    def test_api_features_are_classes_and_exclude_the_mods_own(self) -> None:
        self.assertEqual(api_class("com.fs.starfarer.api.Global.getSector"), "com.fs.starfarer.api.Global")
        self.assertEqual(api_class("com.fs.starfarer.api.combat.WeaponAPI.WeaponType.MISSILE"), "com.fs.starfarer.api.combat.WeaponAPI.WeaponType")
        graph = {
            "mod_id": "m",
            "nodes": [{"id": "class:com.fs.starfarer.api.impl.campaign.items.LTHS_CARD", "kind": "class", "name": "com.fs.starfarer.api.impl.campaign.items.LTHS_CARD"},
                      {"id": "source:d", "kind": "source", "path": "disabled_files/Old.java"}],
            "edges": [{"source": "class:com.fs.starfarer.api.impl.campaign.items.LTHS_CARD", "target": "symbol:com.fs.starfarer.api.impl.campaign.items.LTHS_CARD", "relation": "bytecode-reference"},
                      {"source": "class:com.fs.starfarer.api.impl.campaign.items.LTHS_CARD", "target": "symbol:com.fs.starfarer.api.Global.getSector", "relation": "bytecode-reference"},
                      {"source": "source:d", "target": "symbol:x", "relation": "imports"}],
            "no_known_reference": [{"class": "a.Old", "file": "disabled_files/Old.java", "finding": "NO_KNOWN_REFERENCE"}],
        }
        fp = fingerprint(graph)
        self.assertEqual(fp["features"]["api"], ["com.fs.starfarer.api.Global"])  # the mod's own class in api's package is not API
        self.assertFalse([s for s in fp["features"]["structure"] if "disabled_files" in s])  # never loaded
        self.assertEqual(fp["weak"], ["no-known-reference: a.Old (disabled_files/Old.java)"])

    def test_record_writes_only_to_the_given_corpus(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            mod = _mod(root)
            corpus = root / "corpus"
            first = novelty(mod, corpus_dir=corpus, record=True)
            self.assertEqual(first["corpus_size"], 0)
            self.assertTrue((corpus / "demo.json").is_file())
            again = novelty(mod, corpus_dir=corpus)
            self.assertEqual(again["corpus_size"], 0)  # a mod never counts as its own precedent


if __name__ == "__main__":
    unittest.main()
