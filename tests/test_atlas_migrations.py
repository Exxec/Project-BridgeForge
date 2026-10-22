"""Atlas migration mining and feature exemplars (ROADMAP-3 81.2/81.5): synthetic jars, STATIC reads only."""
from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout

from bridgeforge import atlas
from bridgeforge.atlas_exemplars import FEATURES, exemplars, parse_symbols
from bridgeforge.atlas_migrations import Pair, installed_pairs, mine, queue_pairs
from bridgeforge.cli import main
from tests.test_atlas import make_mod, make_vanilla, temp_root, build
from tests.test_atlas_calls import make_jar
from tests.test_atlas_census import CAMPAIGN_UI, SECTOR, sector_user

CATALOGUE = {"note": "n", "removed_classes": [], "changed_classes": {
    SECTOR.replace("/", "."): {"methods_removed": [{
        "name": "addMessage", "descriptor": "(Ljava/lang/String;)V", "signature": "void addMessage(String)",
        "same_name_in_class": [], "same_signature_elsewhere": [CAMPAIGN_UI.replace("/", ".") + ".addMessage(String)"]}],
        "fields_removed": [], "methods_added": []}}}


def versioned(folder, mod_id, owner, author="", extra=None, version="1"):
    info = {"id": mod_id, "name": mod_id, "version": version, "jars": ["jars/x.jar"], **({"author": author} if author else {})}
    mod = make_mod(folder, mod_id, {"mod_info.json": json.dumps(info), **(extra or {})})
    make_jar(mod / "jars" / "x.jar", {"a/One.class": sector_user("a/One", owner, "addMessage")})
    return mod


class MigrationTests(unittest.TestCase):
    def pairs(self, root, authors):
        out = []
        for index, author in enumerate(authors):
            old = versioned(root / "old", f"m{index}", SECTOR, author)
            new = versioned(root / "new", f"m{index}", CAMPAIGN_UI, author)
            out.append(Pair(f"m{index}", old, new))
        return out

    def test_independent_mods_decide_r4_eligibility(self):
        with temp_root() as root:
            data = mine(self.pairs(root, ["a", "b", "c"]), CATALOGUE)
            (rule,) = data["rules"]
            self.assertEqual((rule["old"], rule["new"]), (SECTOR.replace("/", ".") + ".addMessage", CAMPAIGN_UI.replace("/", ".") + ".addMessage"))
            self.assertEqual((rule["independent_mods"], rule["r4_eligible"], rule["kind"]), (3, True, "pure-rename"))
            self.assertEqual(data["r4_eligible"], 1)
            self.assertIn("a/One", rule["old_examples"][0])

    def test_same_author_family_counts_once(self):
        with temp_root() as root:
            data = mine(self.pairs(root, ["Same Author", "same  author", "c"]), CATALOGUE)
            (rule,) = data["rules"]
            self.assertEqual((len(rule["mods"]), rule["independent_mods"], rule["r4_eligible"]), (3, 2, False))

    def test_without_api_diff_kind_is_unknown_and_unremoved_symbols_are_kept(self):
        with temp_root() as root:
            (rule,) = mine(self.pairs(root, ["a"]))["rules"]
            self.assertTrue(rule["kind"].startswith("unknown"))

    def test_api_diff_drops_symbols_the_new_api_still_has(self):
        with temp_root() as root:
            data = mine(self.pairs(root, ["a"]), {"note": "", "removed_classes": [], "changed_classes": {}})
            self.assertEqual(data["rules"], [])

    def test_queue_pairs_and_cli_write(self):
        with temp_root() as root:
            queue = root / "In operation"
            versioned(queue / "X" / "original", "x", SECTOR)
            versioned(queue / "X", "x", CAMPAIGN_UI)
            (queue / "X" / "x").rename(queue / "X" / "working")
            (queue / "_rig").mkdir()
            pairs = queue_pairs(queue, root / "scratch")
            self.assertEqual([p.label for p in pairs], ["X (original vs working)"])
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = main(["atlas", "migrations", "--pairs-from", str(queue), "--write", str(root / "out"), "--json"])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out.getvalue())["rules"][0]["independent_mods"], 1)
            self.assertIn("proposals only", (root / "out" / "MIGRATIONS.md").read_text(encoding="utf-8").lower())
            self.assertTrue((root / "out" / "MIGRATIONS.json").is_file())

    def test_installed_pairs_need_a_different_version_and_record_both(self):
        with temp_root() as root:
            queue = root / "In operation"
            versioned(queue / "X" / "original", "x", SECTOR, "a", version="1")
            versioned(queue / "Y" / "original", "y", SECTOR, "b", version="2")
            versioned(root / "mods", "x", CAMPAIGN_UI, "a", version="1.5")
            versioned(root / "mods", "y", CAMPAIGN_UI, "b", version="2")  # same version: no pair
            (pair,) = installed_pairs(queue, root / "mods")
            self.assertEqual((pair.old_version, pair.new_version), ("1", "1.5"))
            data = mine([pair], CATALOGUE)
            self.assertEqual(data["pairs"][0]["new_version"], "1.5")
            self.assertEqual(len(data["rules"]), 1)
            out = io.StringIO()
            with redirect_stdout(out):
                code = main(["atlas", "migrations", "--pairs-installed", str(queue), "--installed", str(root / "mods"),
                             "--write", str(root / "o"), "--stem", "MIGRATIONS-UPSTREAM", "--json"])
            self.assertEqual(code, 0)
            self.assertTrue((root / "o" / "MIGRATIONS-UPSTREAM.md").is_file())


class ExemplarTests(unittest.TestCase):
    def test_ranking_by_coverage_and_matching_forms(self):
        java = lambda body: ("package r;\nimport com.fs.starfarer.api.impl.campaign.intel.BaseIntelPlugin;\n"  # noqa: E731
                             + body)
        with temp_root() as root:
            make_vanilla(root)
            make_mod(root / "mods", "intel_only", {"data/scripts/A.java": java("public class A extends BaseIntelPlugin {}\n")})
            make_mod(root / "mods", "both", {"data/scripts/B.java": java(
                "import com.fs.starfarer.api.campaign.rules.IntelInfoPlugin;\npublic class B extends BaseIntelPlugin implements IntelInfoPlugin {}\n")})
            db, _ = build(root)
            conn = atlas.connect(db)
            data = exemplars(conn, FEATURES["intel"], 5, "intel")
            self.assertEqual([(e["mod"], e["coverage"]) for e in data["shown"]], [("both", 2), ("intel_only", 1)])
            self.assertEqual(data["shown"][1]["missing"], ["IntelInfoPlugin"])
            self.assertIn("B.java", data["shown"][0]["matched"][0]["examples"][0])
            self.assertEqual(exemplars(conn, parse_symbols("Nope, BaseIntelPlugin,"), 5)["shown"][0]["coverage"], 1)
            out = io.StringIO()
            with redirect_stdout(out):
                code = main(["atlas", "exemplars", "intel", "--db", str(db), "--top", "1"])
            self.assertEqual(code, 0)
            self.assertIn("both", out.getvalue())
            conn.close()

    def test_unknown_feature_is_an_error(self):
        with temp_root() as root:
            make_vanilla(root)
            db, _ = build(root)
            err = io.StringIO()
            with redirect_stderr(err):
                self.assertEqual(main(["atlas", "exemplars", "bogus", "--db", str(db)]), 2)


if __name__ == "__main__":
    unittest.main()
