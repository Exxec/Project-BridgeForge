"""94.G2 P4: a Nexerelin custom start as a gene, and the nested classes of a gene's jar classes. Synthetic fixtures only."""
from __future__ import annotations

import json
import subprocess
import unittest
import zipfile

from bridgeforge.genome.gene import (CUSTOM_STARTS_FILE, GeneError, _nested_classes, custom_start_entry, describe, validate)
from bridgeforge.genome.gene_set import unresolved_in_carrier
from bridgeforge.genome.proof import prove
from tests.support import javac_path, resolved_temp_dir, write_text as _write

START = """package data.scripts;
public class demo_Start {
    void execute() {
        String ship = "demo_flagship_Var1";
    }
}
"""
# Trailing commas, as Bultach Coalition's file has: Nexerelin reads it leniently (getMergedJSONForMod).
STARTS = """{
    "starts":[
        {"id":"demoStart", "name":"Demo", "desc":"A start.", "className":"data.scripts.demo_Start", "factionId":"player",},
    ],
}"""


def _mod(root, starts: str = STARTS):
    mod = root / "mod"
    _write(mod / "mod_info.json", json.dumps({"id": "demomod", "name": "Demo", "version": "1.0", "gameVersion": "0.98.5a-RC7",
                                              "dependencies": [{"id": "lw_lazylib"}]}))
    _write(mod / CUSTOM_STARTS_FILE, starts)
    _write(mod / "data" / "scripts" / "demo_Start.java", START)
    _write(mod / "data" / "variants" / "demo_flagship_Var1.variant",
           json.dumps({"variantId": "demo_flagship_Var1", "hullId": "demo_flagship"}))
    _write(mod / "data" / "hulls" / "ship_data.csv", "name,id\nFlagship,demo_flagship\n")
    return mod


def _core(root):
    core = root / "core"
    _write(core / "data" / "hulls" / "ship_data.csv", "name,id\n")
    _write(core / "data" / "hullmods" / "hull_mods.csv", "name,id\n")
    return core


class CustomStartTests(unittest.TestCase):
    def test_a_start_gene_is_its_whole_file_its_class_and_the_ship_it_names_and_needs_nexerelin(self) -> None:
        with resolved_temp_dir() as root:
            gene = describe(_mod(root), "custom-start:demoStart", vanilla_core=_core(root))
        self.assertEqual(validate(gene), [])
        paths = {(m["what"], m["path"]) for m in gene["members"]}
        self.assertIn(("file", CUSTOM_STARTS_FILE), paths)
        self.assertIn(("file", "data/scripts/demo_Start.java"), paths)
        self.assertIn(("file", "data/variants/demo_flagship_Var1.variant"), paths)  # P2's rule: the code names it
        self.assertIn("custom-start:demoStart", gene["provides"])
        self.assertIn("nexerelin", gene["needs"]["mods"])
        self.assertIn({"kind": "mod-enabled", "subject": "nexerelin"},
                      [{k: c[k] for k in ("kind", "subject")} for c in gene["conditions"]])
        self.assertEqual(gene["registrations"], [{"locus": CUSTOM_STARTS_FILE, "statement": "data.scripts.demo_Start"}])

    def test_a_file_the_gene_cannot_take_whole_is_refused(self) -> None:
        two = STARTS.replace("},", "}, {\"id\":\"other\", \"name\":\"O\", \"desc\":\"d\", \"className\":\"x.Y\"},", 1)
        cases = {
            "two starts": (two, "holds 2 start"),
            "another key": ('{"starts":[{"id":"demoStart","className":"data.scripts.demo_Start"}], "config":{}}', "other keys"),
            "another id": ('{"starts":[{"id":"elsewhere","className":"data.scripts.demo_Start"}]}', "registers 'elsewhere'"),
            "no class": ('{"starts":[{"id":"demoStart"}]}', "names no className"),
        }
        for name, (text, message) in cases.items():
            with self.subTest(name), resolved_temp_dir() as root, self.assertRaisesRegex(GeneError, message):
                describe(_mod(root, text), "custom-start:demoStart", vanilla_core=_core(root))

    def test_a_mod_without_the_file_is_refused(self) -> None:
        with resolved_temp_dir() as root:
            mod = _mod(root)
            (mod / CUSTOM_STARTS_FILE).unlink()
            with self.assertRaisesRegex(GeneError, "does not exist"):
                custom_start_entry(mod, "demoStart")

    def test_proofs_take_the_file_from_the_donor_and_give_the_carrier_nexerelin(self) -> None:
        with resolved_temp_dir() as root:
            out = root / "proofs"
            result = prove(_mod(root), "custom-start:demoStart", out, vanilla_core=_core(root))
            subtracted = (out / "work" / "subtraction" / CUSTOM_STARTS_FILE).exists()
            carried = (out / "work" / "carrier" / CUSTOM_STARTS_FILE).is_file()
            info = json.loads((out / "work" / "carrier" / "mod_info.json").read_text(encoding="utf-8"))
            isolation = json.loads((out / "isolation-proof.json").read_text(encoding="utf-8"))
        self.assertFalse(subtracted)
        self.assertTrue(carried)
        self.assertIn({"id": "nexerelin"}, info["dependencies"])
        self.assertEqual(isolation["unresolved_in_carrier"], [])
        self.assertEqual(result["verdicts"]["isolation-proof"], "PASS")


class CarrierResolutionTests(unittest.TestCase):
    def test_a_carrier_defines_a_start_only_with_its_registration_and_its_class(self) -> None:
        gene = {"provides": ["custom-start:demoStart"], "needs": {"genes": []}}
        with resolved_temp_dir() as root:
            carrier = _mod(root)
            self.assertEqual(unresolved_in_carrier(carrier, {"custom-start:demoStart": gene}), [])
            (carrier / "data" / "scripts" / "demo_Start.java").unlink()
            missing = unresolved_in_carrier(carrier, {"custom-start:demoStart": gene})
            self.assertEqual(len(missing), 1)
            self.assertIn("holds no class data.scripts.demo_Start", missing[0]["why"])
            (carrier / CUSTOM_STARTS_FILE).unlink()
            self.assertIn("does not exist", unresolved_in_carrier(carrier, {"custom-start:demoStart": gene})[0]["why"])


class NestedClassTests(unittest.TestCase):
    @unittest.skipUnless(javac_path(), "needs javac")
    def test_a_start_in_a_jar_carries_its_anonymous_class(self) -> None:
        # Bultach Coalition's bt_murtach_start adds an anonymous Script ($1) in execute(); it was not a member (P4, 2026-11-22).
        source = START.replace('String ship = "demo_flagship_Var1";',
                               'String ship = "demo_flagship_Var1"; Runnable later = new Runnable() { public void run() {} };')
        with resolved_temp_dir() as root:
            mod = _mod(root)
            (mod / "data" / "scripts" / "demo_Start.java").unlink()
            src, out = root / "src", root / "classes"
            _write(src / "data" / "scripts" / "demo_Start.java", source)
            subprocess.run([javac_path(), "-encoding", "UTF-8", "-proc:none", "-d", str(out), str(src / "data" / "scripts" / "demo_Start.java")],
                           check=True, capture_output=True)
            info = json.loads((mod / "mod_info.json").read_text(encoding="utf-8"))
            _write(mod / "mod_info.json", json.dumps({**info, "jars": ["jars/demo.jar"]}))
            (mod / "jars").mkdir()
            with zipfile.ZipFile(mod / "jars" / "demo.jar", "w") as jar:
                for path in sorted((out / "data" / "scripts").glob("*.class")):
                    jar.write(path, f"data/scripts/{path.name}")
            gene = describe(mod, "custom-start:demoStart", vanilla_core=_core(root))
        paths = {m["path"] for m in gene["members"] if m["what"] == "jar-class"}
        self.assertEqual(paths, {"jars/demo.jar!data/scripts/demo_Start.class", "jars/demo.jar!data/scripts/demo_Start$1.class"})

    def test_a_jar_class_brings_its_nested_and_anonymous_classes_and_nothing_else(self) -> None:
        with resolved_temp_dir() as root:
            (root / "jars").mkdir()
            with zipfile.ZipFile(root / "jars" / "j.jar", "w") as jar:
                for name in ("a/Gene.class", "a/Gene$1.class", "a/Gene$Inner.class", "a/Gene$Inner$2.class",
                             "a/GeneOther$1.class", "a/Other.class", "a/Gene$readme.txt"):
                    jar.writestr(name, name.encode("utf-8"))
            members = [{"what": "jar-class", "path": "jars/j.jar!a/Gene.class", "sha256": "0" * 64},
                       {"what": "jar-class", "path": "jars/j.jar!a/Gene$Inner.class", "sha256": "0" * 64}]
            found = _nested_classes(root, members)
        self.assertEqual([m["path"] for m in found], ["jars/j.jar!a/Gene$1.class", "jars/j.jar!a/Gene$Inner$2.class"])
        self.assertEqual(found[0]["reason"], "a nested class of a.Gene")
        self.assertEqual(len(found[0]["sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
