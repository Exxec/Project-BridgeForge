import base64
import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.translation import apply_translation, export_translation


class TranslationExtensionConformanceTests(unittest.TestCase):
    def test_extended_schema_v1_matches_shared_units_hashes_and_output_bytes(self):
        self.check_fixture("schema-v1-extensions.json")

    def test_imported_roles_preserve_identifiers_and_translate_the_complete_group(self):
        self.check_fixture("schema-v1-roles.json")

    def check_fixture(self, name):
        fixture = json.loads((Path(__file__).resolve().parents[1] / "fixtures/translation-conformance" / name).read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input"
            for name, encoded in fixture["input_files"].items():
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(base64.b64decode(encoded))
            before = {p: p.read_bytes() for p in source.rglob("*") if p.is_file()}
            actual = export_translation(source)
            for field, expected in fixture["expected_export"].items():
                self.assertEqual(actual[field], expected, field)
            output = Path(directory) / "output"
            report = apply_translation(source, fixture["translated"], output)
            self.assertEqual(len(report["problems"]), fixture.get("expected_problem_count", 0))
            actual_files = {p.relative_to(output).as_posix(): base64.b64encode(p.read_bytes()).decode("ascii") for p in output.rglob("*") if p.is_file()}
            self.assertEqual(actual_files, fixture["expected_output_files"])
            self.assertEqual(before, {p: p.read_bytes() for p in before})
