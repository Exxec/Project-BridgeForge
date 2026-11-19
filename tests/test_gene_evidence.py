"""94.G1 WP5: the header every evidence file about a gene carries, and `gene evidence check`."""
from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout

from bridgeforge.cli import main
from bridgeforge.genome import contract
from bridgeforge.genome.evidence import REQUIRED_KEYS, check, header, path_problem, validate
from tests.support import resolved_temp_dir, write_text as _write

GENE = contract.fixtures()["valid-hullmod.json"]


class HeaderTests(unittest.TestCase):
    def test_a_written_header_validates_and_checks_against_its_gene_and_inputs(self) -> None:
        with resolved_temp_dir() as root:
            _write(root / "data" / "hullmods" / "hull_mods.csv", "name,id\nx,example_mod\n")
            made = header("subtraction-proof", GENE, root=root, inputs=[("donor", "data/hullmods/hull_mods.csv")], verdict="PASS")
            self.assertEqual(validate(made), [])
            self.assertEqual(check(made, GENE, root), [])
            self.assertEqual((made["gene"], made["build"]["game_version"]), (
                {"identity": GENE["identity"], "schema_version": GENE["schema_version"]}, "0.98.5a-RC7"))
            _write(root / "data" / "hullmods" / "hull_mods.csv", "name,id\nx,example_mod\ny,other\n")
            self.assertEqual(check(made, GENE, root), ["input data/hullmods/hull_mods.csv changed since the evidence was made"])
            (root / "data" / "hullmods" / "hull_mods.csv").unlink()
            self.assertEqual(check(made, GENE, root), ["input data/hullmods/hull_mods.csv is gone"])

    def test_another_gene_or_another_gene_schema_is_refused(self) -> None:
        made = contract.evidence_fixtures()["valid-subtraction-proof.json"]
        self.assertEqual(check(made, {**GENE, "identity": "e" * 64}), ["the evidence is about another gene (identity differs)"])
        self.assertIn("the evidence names gene schema 2, the manifest is 3", check(made, {**GENE, "schema_version": 3}))
        # Withdrawn schema 1 is refused by the header itself, whatever manifest it is checked against.
        withdrawn = {**made, "gene": {**made["gene"], "schema_version": 1}}
        self.assertEqual(validate(withdrawn), ["gene schema 1 is withdrawn"])

    def test_a_header_never_names_a_machine_path(self) -> None:
        for bad in ("/home/x/a.csv", "C:/mods/a.csv", "data\\a.csv", "../a.csv", "data/./a.csv", "data//a.csv", " a.csv", ""):
            with self.subTest(bad):
                self.assertIsNotNone(path_problem(bad))
        self.assertIsNone(path_problem("data/hullmods/hull_mods.csv"))
        with resolved_temp_dir() as root, self.assertRaises(ValueError):
            header("x", GENE, root=root, inputs=[("donor", "/etc/passwd")], verdict="PASS")

    def test_malformed_shapes_give_problems_not_exceptions(self) -> None:
        made = contract.evidence_fixtures()["valid-subtraction-proof.json"]
        self.assertEqual(validate([]), ["an evidence file is a JSON object"])
        for key in REQUIRED_KEYS:
            with self.subTest(key):
                self.assertNotEqual(validate({**made, key: None}), [])
        self.assertIn("missing inputs", validate({k: v for k, v in made.items() if k != "inputs"}))


class ContractTests(unittest.TestCase):
    def test_evidence_fixtures_break_one_rule_each_and_the_contract_records_them(self) -> None:
        for name, made in contract.evidence_fixtures().items():
            with self.subTest(name):
                problems = check(made, GENE)
                self.assertEqual(len(problems), 0 if name.startswith("valid-") else 1, problems)
        recorded = json.loads(contract.contract_files()["CONTRACT.json"])
        self.assertEqual(recorded["evidence_header"]["schema_version"], 1)
        self.assertEqual(set(recorded["evidence_header"]["fixtures"]), set(contract.evidence_fixtures()))
        self.assertIn("evidence-header.schema.json", recorded["files"])

    def test_the_schema_requires_what_validate_requires(self) -> None:
        self.assertEqual(sorted(contract.evidence_schema()["required"]), sorted(REQUIRED_KEYS))


class CliTests(unittest.TestCase):
    def test_check_ok_stale_and_unreadable(self) -> None:
        with resolved_temp_dir() as root:
            _write(root / "mod" / "data" / "hullmods" / "hull_mods.csv", "name,id\nx,example_mod\n")
            made = header("isolation-proof", GENE, root=root / "mod", inputs=[("donor", "data/hullmods/hull_mods.csv")], verdict="FAIL")
            _write(root / "proof.json", json.dumps(made))
            _write(root / "gene.json", json.dumps(GENE))
            argv = ["gene", "evidence", "check", str(root / "proof.json"), "--gene", str(root / "gene.json"), "--root", str(root / "mod")]
            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(main(argv), 0)
            self.assertIn("OK isolation-proof FAIL", out.getvalue())
            _write(root / "mod" / "data" / "hullmods" / "hull_mods.csv", "changed\n")
            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(main(argv), 1)
            self.assertIn("changed since", out.getvalue())
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(["gene", "evidence", "check", str(root / "nope.json"), "--gene", str(root / "gene.json")]), 2)


if __name__ == "__main__":
    unittest.main()
