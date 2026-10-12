"""Versioned, repository-owned inputs shared with Project Go's P7 tests."""

import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.translation import apply_translation, export_translation


class SharedTranslationConformanceTests(unittest.TestCase):
    def test_export_and_apply_match_versioned_shared_bytes(self):
        fixture = Path(__file__).resolve().parents[1] / "fixtures/translation-conformance"
        expected = json.loads((fixture / "expected-export.json").read_text(encoding="utf-8"))
        actual = export_translation(fixture / "input")
        for field in ("entries", "file_hashes", "unreadable", "entry_count", "unique_source_count"):
            self.assertEqual(actual[field], expected[field], field)
        document = json.loads((fixture / "translated.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            result = apply_translation(fixture / "input", document, out_dir=output)
            self.assertEqual(result["problems"], [])
            for path in (fixture / "expected-output").rglob("*"):
                if path.is_file():
                    relative = path.relative_to(fixture / "expected-output")
                    self.assertEqual((output / relative).read_bytes(), path.read_bytes(), str(relative))
