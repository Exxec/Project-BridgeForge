"""94.G2 slice 5: the three causes of P2's first static FAIL, each fixed (2026-11-19)."""
from __future__ import annotations

import json
import unittest
import zipfile
from types import SimpleNamespace

from bridgeforge.genome.closure import mods_needed
from bridgeforge.genome.proof import classify_subtraction, subtract
from bridgeforge.models import Finding
from tests.support import resolved_temp_dir, write_text as _write


def _scan(*findings):
    return SimpleNamespace(findings=[Finding(id=i, category="c", severity="medium", classification="REVIEW", confidence="high",
                                             explanation=i, file=f, evidence=list(e)) for i, f, e in findings])


class BuildSourceTests(unittest.TestCase):
    def test_a_removed_class_takes_its_build_source_and_keeps_the_rest_and_reports(self) -> None:
        with resolved_temp_dir() as root:
            mod = root / "mod"
            _write(mod / "mod_info.json", json.dumps({"id": "j", "jars": ["jars/j.jar"]}))
            _write(mod / "src" / "a" / "Gene.java", "package a;\npublic class Gene { }\n")
            _write(mod / "src" / "a" / "Other.java", "package a;\npublic class Other { }\n")
            _write(mod / "reports" / "src-to-jar.json", "{}\n")
            (mod / "jars").mkdir()
            with zipfile.ZipFile(mod / "jars" / "j.jar", "w") as jar:
                jar.writestr("a/Gene.class", b"gene")
                jar.writestr("a/Gene$1.class", b"inner")
                jar.writestr("a/Other.class", b"other")
            gene = {"members": [{"what": "jar-class", "path": "jars/j.jar!a/Gene.class"},
                                {"what": "jar-class", "path": "jars/j.jar!a/Gene$1.class"}]}
            notes = subtract(mod, gene, root / "copy")
            self.assertFalse((root / "copy" / "src" / "a" / "Gene.java").exists())
            self.assertTrue((root / "copy" / "src" / "a" / "Other.java").exists())
            self.assertTrue((root / "copy" / "reports" / "src-to-jar.json").exists())  # the scanner reads it
            self.assertTrue((mod / "src" / "a" / "Gene.java").exists())  # the donor is untouched
        self.assertIn("src/a/Gene.java removed with its class (build source)", notes)


class SummaryLineTests(unittest.TestCase):
    GENE = {"provides": ["hullmod:x_mark"], "members": [{"what": "file", "path": "data/hullmods/x_script.java"}]}

    def test_scanner_totals_are_summaries_and_a_real_reference_is_still_judged(self) -> None:
        after = _scan(("bundled-source-stale", "", ["differ:0", "source-only:9"]),
                      ("content-reference-unresolved", "", ["common prefix: other_ (3 ids)", "weapon:stray_gun"]))
        result = classify_subtraction(_scan(), after, self.GENE, [])
        self.assertEqual(sorted(s["line"] for s in result["summaries"]), ["common prefix: other_ (3 ids)", "differ:0", "source-only:9"])
        self.assertEqual([u["reference"] for u in result["unexplained"]], ["weapon:stray_gun"])
        self.assertEqual(result["verdict"], "FAIL")

    def test_a_summary_line_naming_the_gene_is_not_set_aside(self) -> None:
        result = classify_subtraction(_scan(), _scan(("odd", "", ["x_mark: 2"])), self.GENE, [])
        self.assertEqual(result["summaries"], [])
        self.assertEqual(len(result["dependents"]), 1)


class ModsNeededTests(unittest.TestCase):
    def test_a_known_library_stays_only_when_the_code_references_it_and_an_unknown_one_stays(self) -> None:
        with resolved_temp_dir() as root:
            _write(root / "data" / "scripts" / "A.java",
                   "package data.scripts;\nimport org.lazywizard.lazylib.MathUtils;\npublic class A { }\n")
            members = [{"what": "file", "path": "data/scripts/A.java"}]
            needed = mods_needed(root, members, ["lw_lazylib", "MagicLib", "someones_private_lib"])
        self.assertEqual(needed, ["lw_lazylib", "someones_private_lib"])


if __name__ == "__main__":
    unittest.main()
