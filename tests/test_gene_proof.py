"""94.G2: the static halves of a gene's subtraction and isolation proofs (genome/proof.py)."""
from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from types import SimpleNamespace

from bridgeforge.cli import main
from bridgeforge.genome.evidence import check
from bridgeforge.genome.proof import ProofError, classify_isolation, classify_subtraction, cut_csv_row, cut_json_key, prove
from bridgeforge.models import Finding
from tests.support import resolved_temp_dir, write_text as _write

GENE = {"provides": ["hullmod:tank_mod"], "needs": {"vanilla": ["commodity:food"], "mods": []},
        "members": [{"what": "csv-row", "path": "data/hullmods/hull_mods.csv [tank_mod]"},
                    {"what": "file", "path": "data/hullmods/tank_script.java"},
                    {"what": "json-entry", "path": "data/config/settings.json#/tank_mod_rate"}]}


def _scan(*findings):
    return SimpleNamespace(findings=[Finding(id=i, category="c", severity="medium", classification="REVIEW", confidence="high",
                                             explanation=f"about {i}", file=f, evidence=list(e)) for i, f, e in findings])


class CutTests(unittest.TestCase):
    def test_a_csv_row_is_cut_by_the_id_column_and_the_rest_stays_byte_for_byte(self) -> None:
        text = 'name,id,desc\r\nA,keep_me,"two\r\nlines"\r\nB,tank_mod,x\r\nC,also_keep,y\r\n'
        rest, row = cut_csv_row(text, "tank_mod")
        self.assertEqual(row, "B,tank_mod,x\r\n")
        self.assertEqual(rest, 'name,id,desc\r\nA,keep_me,"two\r\nlines"\r\nC,also_keep,y\r\n')
        id_second = "id,name\ntank_mod,A\nother,B\n"  # the id column is found from the header, not assumed
        self.assertEqual(cut_csv_row(id_second, "tank_mod")[0], "id,name\nother,B\n")
        with self.assertRaises(ProofError):
            cut_csv_row("name,desc\nA,b\n", "tank_mod")

    def test_a_settings_key_line_is_cut_and_a_multi_line_value_is_refused(self) -> None:
        text = '{\n  # comment\n  "tank_mod_rate": 5,\n  "other": [1,\n    2],\n  "last": true,\n}\n'
        self.assertEqual(cut_json_key(text, "tank_mod_rate"), '{\n  # comment\n  "other": [1,\n    2],\n  "last": true,\n}\n')
        self.assertIsNone(cut_json_key(text, "other"))
        self.assertIsNone(cut_json_key(text, "absent"))


class SubtractionTests(unittest.TestCase):
    def test_a_dependent_passes_a_leak_and_an_unexplained_reference_fail(self) -> None:
        before = _scan()
        used_by = [{"path": "data/hulls/tank.ship", "mentions": ["tank_mod"]}]
        dependent = classify_subtraction(before, _scan(("content-reference-unresolved", "", ["hullmod:tank_mod (1 file(s))"])), GENE, used_by)
        self.assertEqual((dependent["verdict"], dependent["dependents"]),
                         ("PASS", [{"from": "data/hulls/tank.ship", "to": "hullmod:tank_mod"}]))
        leak = classify_subtraction(before, _scan(("class-missing", "data/x.java", ["data.hullmods.tank_script not found"])), GENE, used_by)
        self.assertEqual((leak["verdict"], len(leak["leaks"])), ("FAIL", 1))
        stray = classify_subtraction(before, _scan(("odd", "data/y.csv", ["something else"])), GENE, used_by)
        self.assertEqual((stray["verdict"], len(stray["unexplained"])), ("FAIL", 1))

    def test_a_new_reference_inside_a_finding_the_donor_already_had_is_still_seen(self) -> None:
        # content-reference-unresolved gathers all of a mod's unresolved references: a key-level diff would miss this one.
        before = _scan(("content-reference-unresolved", "", ["weapon:unrelated_gun (2 file(s))"]))
        after = _scan(("content-reference-unresolved", "", ["weapon:unrelated_gun (2 file(s))", "data.hullmods.tank_script"]))
        result = classify_subtraction(before, after, GENE, [])
        self.assertEqual(result["verdict"], "FAIL")
        self.assertEqual([leak["reference"] for leak in result["leaks"]], ["data.hullmods.tank_script"])


class IsolationTests(unittest.TestCase):
    def test_inherited_and_carrier_findings_pass_anything_else_fails(self) -> None:
        donor = _scan(("loose-script-janino-risk", "data/hullmods/tank_script.java", ["risk"]))
        carrier = _scan(("loose-script-janino-risk", "data/hullmods/tank_script.java", ["risk"]),
                        ("mod-info-game-version-inexact", "mod_info.json", ["version"]),
                        ("content-reference-unresolved", "", ["commodity:food", "hullmod:tank_mod"]))
        passed = classify_isolation(donor, carrier, GENE)
        self.assertEqual(passed["verdict"], "PASS")
        self.assertEqual(len(passed["inherited"]) + len(passed["carrier_own"]), 2)
        unresolved = classify_isolation(donor, _scan(("content-reference-unresolved", "", ["weapon:not_needed"])), GENE)
        self.assertEqual((unresolved["verdict"], unresolved["failures"][0]["reference"]), ("FAIL", "weapon:not_needed"))
        new = classify_isolation(donor, _scan(("brand-new", "data/hullmods/tank_script.java", ["x"])), GENE)
        self.assertEqual(new["verdict"], "FAIL")


def _mod(root):
    mod = root / "mod"
    _write(mod / "mod_info.json", json.dumps({"id": "tankmod", "name": "Tank Mod", "version": "1.0", "gameVersion": "0.98.5a-RC7"}))
    _write(mod / "data" / "hullmods" / "hull_mods.csv", "name,id,script\nTanks,tank_mod,data.hullmods.tank_mod\nOther,other_mod,\n")
    _write(mod / "data" / "hullmods" / "tank_mod.java",
           "package data.hullmods;\nimport com.fs.starfarer.api.Global;\npublic class tank_mod {\n"
           "  float a = Global.getSettings().getFloat(\"tank_mod_rate\");\n}\n")
    _write(mod / "data" / "config" / "settings.json", '{\n  "tank_mod_rate": 5,\n  "other_key": 1\n}\n')
    return mod


class ProveTests(unittest.TestCase):
    def test_prove_writes_gene_and_two_checked_evidence_files_and_leaves_the_donor_alone(self) -> None:
        with resolved_temp_dir() as root:
            mod = _mod(root)
            before = {p.relative_to(mod).as_posix(): p.read_bytes() for p in mod.rglob("*") if p.is_file()}
            out = root / "proofs"
            result = prove(mod, "hullmod:tank_mod", out)
            self.assertEqual(result["verdicts"], {"subtraction-proof": "PASS", "isolation-proof": "PASS"})
            gene = json.loads((out / "gene.json").read_text(encoding="utf-8"))
            for kind in ("subtraction-proof", "isolation-proof"):
                made = json.loads((out / f"{kind}.json").read_text(encoding="utf-8"))
                self.assertEqual(check(made, gene, mod), [])
                self.assertEqual((made["half"], made["boot"][:7]), ("static", "NOT_RUN"))
            sub = out / "work" / "subtraction"
            self.assertNotIn("tank_mod", (sub / "data" / "hullmods" / "hull_mods.csv").read_text(encoding="utf-8"))
            self.assertEqual((sub / "data" / "config" / "settings.json").read_text(encoding="utf-8"), '{\n  "other_key": 1\n}\n')
            carrier = out / "work" / "carrier"
            self.assertEqual(json.loads((carrier / "data" / "config" / "settings.json").read_text(encoding="utf-8")), {"tank_mod_rate": 5})
            self.assertEqual({p.relative_to(mod).as_posix(): p.read_bytes() for p in mod.rglob("*") if p.is_file()}, before)
            with self.assertRaises(ProofError):
                prove(mod, "hullmod:tank_mod", out)  # never into a folder that holds something

    def test_the_cli_reports_the_verdicts(self) -> None:
        with resolved_temp_dir() as root:
            mod = _mod(root)
            with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()):
                code = main(["gene", "prove", str(mod), "hullmod:tank_mod", "--out", str(root / "p")])
        self.assertEqual(code, 0)
        self.assertIn("subtraction-proof: PASS (static half; boot half NOT_RUN)", out.getvalue())


if __name__ == "__main__":
    unittest.main()
