"""94.G1 WP2 (GR-1): the committed gene contract equals what gene.py defines, and its fixtures mean what they say."""
from __future__ import annotations

import json
import unittest

from bridgeforge.genome import contract
from bridgeforge.genome.gene import REQUIRED_KEYS, identity, validate
from bridgeforge.paths import checkout_root
from tests.support import resolved_temp_dir


class GeneContractTests(unittest.TestCase):
    def test_committed_contract_is_current(self) -> None:
        # A change to gene.py's rules must come with `bridgeforge gene contract --write` and a new pin in the sister repos.
        problems = contract.check_contract(checkout_root() / contract.CONTRACT_RELATIVE)
        self.assertEqual(problems, [], "run `python -m bridgeforge gene contract --write` and review the diff")

    def test_fixture_verdicts_follow_validate(self) -> None:
        for name, gene in contract.fixtures().items():
            with self.subTest(name):
                self.assertEqual(not validate(gene), name.startswith("valid-"))

    def test_each_invalid_fixture_breaks_exactly_one_rule(self) -> None:
        # Otherwise a consumer that misses one rule still rejects the fixture for another reason, and passes.
        for name, gene in contract.fixtures().items():
            if name.startswith("invalid-"):
                with self.subTest(name):
                    self.assertEqual(len(validate(gene)), 1, validate(gene))

    def test_same_gene_in_another_mod_has_the_same_identity(self) -> None:
        recorded = json.loads(contract.contract_files()["CONTRACT.json"])["fixtures"]
        self.assertEqual(recorded["valid-hullmod.json"]["identity"], recorded["valid-same-gene-other-mod.json"]["identity"])
        gene = contract.fixtures()["valid-hullmod.json"]
        self.assertEqual(gene["identity"], identity(gene["kind"], gene["members"]))

    def test_schema_requires_every_key_validate_requires(self) -> None:
        schema = contract.json_schema()
        self.assertEqual(schema["required"], list(REQUIRED_KEYS))
        self.assertEqual(set(schema["properties"]), set(REQUIRED_KEYS))

    def test_contract_lists_every_file_by_hash(self) -> None:
        files = contract.contract_files()
        listed = json.loads(files["CONTRACT.json"])["files"]
        self.assertEqual(set(listed), set(files) - {"CONTRACT.json"})

    def test_check_reports_a_changed_missing_or_extra_file(self) -> None:
        with resolved_temp_dir() as tmp:
            pin = contract.write_contract(tmp)
            self.assertEqual(pin, contract.contract_sha256())
            self.assertEqual(contract.check_contract(tmp), [])
            (tmp / "fixtures" / "valid-hullmod.json").write_bytes(b"{}\n")
            (tmp / "gene.schema.json").unlink()
            (tmp / "notes.txt").write_bytes(b"x")
            problems = contract.check_contract(tmp)
        self.assertIn("fixtures/valid-hullmod.json differs from the contract gene.py defines", problems)
        self.assertIn("gene.schema.json is missing", problems)
        self.assertIn("notes.txt is not part of the contract", problems)


if __name__ == "__main__":
    unittest.main()
