"""A real Project Go coverage manifest is accepted by BridgeForge's consumer (ROADMAP-3 80.9, Project Go H3).

Runs only when PROJECT_GO_FIXTURES names a Project Go checkout; CI sets it in the `shared-fixtures` job. The manifest is the
file Project Go's own build proves it still exports for `fixtures/coverage-manifest/mod`, so a producer change the consumer cannot
accept fails here. Acceptance is identity MATCH only: it never claims complete coverage, approval, rights or runtime proof.
"""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from bridgeforge.localization_coverage import observe

ENV_VAR = "PROJECT_GO_FIXTURES"


@unittest.skipUnless(os.environ.get(ENV_VAR), f"set {ENV_VAR} to a Project Go checkout to import its coverage manifest")
class GoCoverageManifestContractTest(unittest.TestCase):
    def setUp(self):
        self.go_fixture = Path(os.environ[ENV_VAR]).expanduser() / "fixtures" / "coverage-manifest"
        self.manifest = self.go_fixture / "localization-coverage.json"
        self.mod = self.go_fixture / "mod"
        self.assertTrue(self.manifest.is_file(), f"Project Go has no {self.manifest}")
        self.assertTrue(self.mod.is_dir(), f"Project Go has no {self.mod}")
        self.work = Path(tempfile.mkdtemp(prefix="bf-manifest-contract-"))
        self.addCleanup(shutil.rmtree, self.work, ignore_errors=True)

    def _mutated_manifest(self, mutate) -> Path:
        report = json.loads(self.manifest.read_text(encoding="utf-8"))
        mutate(report)
        path = self.work / "mutated.json"
        path.write_text(json.dumps(report), encoding="utf-8")
        return path

    def test_actual_export_is_accepted_without_claiming_more_than_identity(self):
        result = observe(self.manifest, self.mod)
        self.assertEqual(result["candidateIdentity"], "MATCH")
        self.assertEqual(result["coverageStatus"], "OBSERVED_STANDARD_EXTRACTION")
        self.assertIs(result["completeCoverageEstablished"], False)
        self.assertEqual(result["scope"], "SELECTED_STRINGS_ONLY")
        self.assertEqual(result["runtime"], "NOT_TESTED")
        self.assertEqual(result["approval"], "NOT_ASSESSED")
        self.assertEqual(result["rights"], "NOT_ASSESSED")
        self.assertEqual(result["archiveIdentity"], "NOT_VERIFIED")

    def test_changed_field_name_breaks_the_check(self):
        broken = self._mutated_manifest(lambda report: report.update(coverageState=report.pop("coverageStatus")))
        with self.assertRaises(ValueError):
            observe(broken, self.mod)

    def test_changed_count_breaks_the_check(self):
        broken = self._mutated_manifest(lambda report: report.update(extractedStringCount=report["extractedStringCount"] + 1))
        with self.assertRaises(ValueError):
            observe(broken, self.mod)

    def test_changed_candidate_bytes_are_a_mismatch_not_a_match(self):
        copy = self.work / "mod"
        shutil.copytree(self.mod, copy)
        target = copy / "data" / "strings" / "strings.json"
        target.write_bytes(target.read_bytes().replace(b"Hello", b"Howdy"))
        self.assertEqual(observe(self.manifest, copy)["candidateIdentity"], "MISMATCH")


if __name__ == "__main__":
    unittest.main()
