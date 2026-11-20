"""94.G2 schema 4: every G2 kind named, combat plugins closed, ids named by code followed, nested pointers in proofs."""
from __future__ import annotations

import json
import unittest

from bridgeforge.genome.evidence import check
from bridgeforge.genome.gene import CLOSABLE_KINDS, GENE_KINDS, PHENOTYPE, GeneError, describe, validate
from bridgeforge.genome.proof import pointer_tokens, prove
from tests.support import resolved_temp_dir, write_text as _write

SPAWNER = """package data.scripts;
public class demo_Spawner {
    void spawn(Object engine) {
        String hullmod = "demo_spawner_mark";
        String variant = "demo_beast_Var1";
        String vanilla = "tempest_Attack";
        String plain = "not an id at all";
    }
}
"""


def _mod(root, *, plugin_key="demo_Spawner"):
    mod = root / "mod"
    _write(mod / "mod_info.json", json.dumps({"id": "demomod", "name": "Demo", "version": "1.0", "gameVersion": "0.98.5a-RC7"}))
    _write(mod / "data" / "config" / "settings.json",
           json.dumps({"plugins": {plugin_key: "data.scripts.demo_Spawner", "other": "data.scripts.Other"}, "unrelated": 1}, indent=2))
    _write(mod / "data" / "scripts" / "demo_Spawner.java", SPAWNER)
    _write(mod / "data" / "hullmods" / "hull_mods.csv", "name,id,script\nMark,demo_spawner_mark,\nOther,other_mod,\n")
    _write(mod / "data" / "variants" / "demo_beast_Var1.variant", json.dumps({"variantId": "demo_beast_Var1", "hullId": "demo_beast"}))
    _write(mod / "data" / "hulls" / "ship_data.csv", "name,id\nBeast,demo_beast\n")
    return mod


def _core(root):
    core = root / "core"
    _write(core / "data" / "variants" / "tempest_Attack.variant", json.dumps({"variantId": "tempest_Attack", "hullId": "tempest"}))
    _write(core / "data" / "hulls" / "ship_data.csv", "name,id\nTempest,tempest\n")
    _write(core / "data" / "hullmods" / "hull_mods.csv", "name,id\n")
    return core


class KindTests(unittest.TestCase):
    def test_every_g2_kind_is_named_with_a_phenotype_and_unclosable_ones_are_refused(self) -> None:
        for kind in ("faction", "star-system", "market", "industry", "condition", "ability", "rule", "combat-plugin",
                     "campaign-plugin", "custom-start"):
            with self.subTest(kind):
                self.assertIn(kind, GENE_KINDS)
                self.assertTrue(PHENOTYPE[kind])
        self.assertIn("combat-plugin", CLOSABLE_KINDS)
        with resolved_temp_dir() as root, self.assertRaisesRegex(GeneError, "cannot be closed yet"):
            describe(_mod(root), "faction:demo")


class CombatPluginTests(unittest.TestCase):
    def test_a_plugin_gene_holds_its_registration_class_and_the_ids_its_code_names(self) -> None:
        with resolved_temp_dir() as root:
            gene = describe(_mod(root), "combat-plugin:demo_Spawner", vanilla_core=_core(root))
        self.assertEqual(validate(gene), [])
        paths = {(m["what"], m["path"]) for m in gene["members"]}
        self.assertIn(("json-entry", "data/config/settings.json#/plugins/demo_Spawner"), paths)
        self.assertIn(("file", "data/scripts/demo_Spawner.java"), paths)
        self.assertIn(("csv-row", "data/hullmods/hull_mods.csv [demo_spawner_mark]"), paths)
        self.assertIn(("file", "data/variants/demo_beast_Var1.variant"), paths)
        self.assertNotIn(("csv-row", "data/hullmods/hull_mods.csv [other_mod]"), paths)
        self.assertIn("combat-plugin:demo_Spawner", gene["provides"])
        self.assertIn("variant:tempest_Attack", gene["needs"]["vanilla"])
        self.assertEqual(gene["registrations"], [{"locus": "data/config/settings.json#/plugins/demo_Spawner",
                                                  "statement": "data.scripts.demo_Spawner"}])

    def test_an_unregistered_plugin_key_is_refused(self) -> None:
        with resolved_temp_dir() as root, self.assertRaisesRegex(GeneError, "registers no plugin"):
            describe(_mod(root), "combat-plugin:nope")


class JarSubtractionTests(unittest.TestCase):
    def test_a_jar_that_loses_classes_is_written_fresh_without_them(self) -> None:
        import zipfile

        from bridgeforge.genome.proof import subtract
        with resolved_temp_dir() as root:
            mod = root / "mod"
            _write(mod / "mod_info.json", json.dumps({"id": "j", "jars": ["jars/j.jar"]}))
            (mod / "jars").mkdir()
            with zipfile.ZipFile(mod / "jars" / "j.jar", "w") as jar:
                jar.writestr("a/Gene.class", b"gene")
                jar.writestr("a/Gene$1.class", b"inner")
                jar.writestr("a/Other.class", b"other")
            gene = {"members": [{"what": "jar-class", "path": "jars/j.jar!a/Gene.class"},
                                {"what": "jar-class", "path": "jars/j.jar!a/Gene$1.class"}]}
            import shutil
            from unittest import mock

            skipped, real_copytree = set(), shutil.copytree

            def recording_copytree(src, dst, symlinks=False, ignore=None, *a, **k):  # copytree recurses with ignore positional
                def watched(folder, names):
                    result = ignore(folder, names) if ignore else set()
                    skipped.update(result)
                    return result
                return real_copytree(src, dst, symlinks, watched if ignore else None, *a, **k)

            with mock.patch("bridgeforge.genome.proof.shutil.copytree", recording_copytree):
                notes = subtract(mod, gene, root / "copy")
            self.assertIn("j.jar", skipped)  # never copied then rewritten: a just-copied jar can be locked on Windows
            with zipfile.ZipFile(root / "copy" / "jars" / "j.jar") as jar:
                names = sorted(jar.namelist())
            with zipfile.ZipFile(mod / "jars" / "j.jar") as jar:
                original = sorted(jar.namelist())
        self.assertEqual(names, ["a/Other.class"])
        self.assertEqual(original, ["a/Gene$1.class", "a/Gene.class", "a/Other.class"])  # the donor is untouched
        self.assertEqual(notes, ["jars/j.jar written without 2 class(es) of the gene by zipfile (static scan only)"])


class NestedPointerTests(unittest.TestCase):
    def test_tokens_unescape(self) -> None:
        self.assertEqual(pointer_tokens("/plugins/a~1b~0c"), ["plugins", "a/b~c"])

    def test_proofs_remove_and_carry_a_nested_registration(self) -> None:
        with resolved_temp_dir() as root:
            mod, out = _mod(root), root / "proofs"
            result = prove(mod, "combat-plugin:demo_Spawner", out, vanilla_core=_core(root))
            subtracted = json.loads((out / "work" / "subtraction" / "data" / "config" / "settings.json").read_text(encoding="utf-8"))
            carried = json.loads((out / "work" / "carrier" / "data" / "config" / "settings.json").read_text(encoding="utf-8"))
            proof = json.loads((out / "subtraction-proof.json").read_text(encoding="utf-8"))
            gene = json.loads((out / "gene.json").read_text(encoding="utf-8"))
            self.assertEqual(check(proof, gene, mod), [])
        self.assertEqual(subtracted["plugins"], {"other": "data.scripts.Other"})
        self.assertEqual(subtracted["unrelated"], 1)
        self.assertEqual(carried, {"plugins": {"demo_Spawner": "data.scripts.demo_Spawner"}})
        self.assertTrue(any("a nested key" in note for note in proof["rewritten"]))
        self.assertIn(result["verdicts"]["isolation-proof"], ("PASS", "FAIL"))


if __name__ == "__main__":
    unittest.main()
