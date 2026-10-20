import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.translation import TranslationError, apply_translation, export_translation


class TranslationRoleContractTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.mod = self.root / "mod"
        (self.mod / "data").mkdir(parents=True)
        (self.mod / "mod_info.json").write_text('{"id":"roles"}', encoding="utf-8")
        (self.mod / "data/a.csv").write_text("id,design type\nhull,设计\n", encoding="utf-8")
        (self.mod / "data/a.json").write_text('{"designTypeColors":{"设计":"red","Existing":"blue"}}', encoding="utf-8")
        self.document = export_translation(self.mod)
        for entry in self.document["entries"]:
            entry.update(role="LINKED", group="design")
        self.document["entries"][0]["translation"] = "New design"
        self.output = self.root / "output"

    def test_one_linked_translation_is_applied_to_every_reference(self):
        result = apply_translation(self.mod, self.document, self.output)
        self.assertEqual(result["problems"], [])
        self.assertIn("hull,New design", (self.output / "data/a.csv").read_text(encoding="utf-8"))
        self.assertIn("New design", json.loads((self.output / "data/a.json").read_text(encoding="utf-8"))["designTypeColors"])

    def test_existing_key_collision_refuses_without_output_or_source_changes(self):
        before = {p: p.read_bytes() for p in self.mod.rglob("*") if p.is_file()}
        self.document["entries"][0]["translation"] = "Existing"
        with self.assertRaisesRegex(TranslationError, "Linked translation rejected"):
            apply_translation(self.mod, self.document, self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_incomplete_group_cannot_move_one_reference(self):
        self.document["entries"] = self.document["entries"][:1]
        with self.assertRaisesRegex(TranslationError, "Invalid linked group"):
            apply_translation(self.mod, self.document, self.output)
        self.assertFalse(self.output.exists())

    def test_identifier_translation_and_glossary_are_protected(self):
        for entry in self.document["entries"]:
            entry.pop("group")
            entry["role"] = "IDENTIFIER"
        self.document["glossary"] = {"设计": "New design"}
        report = apply_translation(self.mod, self.document, self.output)
        self.assertEqual(len(report["problems"]), 2)
        self.assertIn("设计", (self.output / "data/a.csv").read_text(encoding="utf-8"))

    def test_linked_in_place_is_explicitly_refused(self):
        with self.assertRaisesRegex(TranslationError, "in-place linked application is not supported"):
            apply_translation(self.mod, self.document, in_place=True)

    def test_invalid_placeholders_refuse_whole_linked_publication(self):
        for path in (self.mod / "data/a.csv", self.mod / "data/a.json"):
            path.write_text(path.read_text(encoding="utf-8").replace("设计", "%s设计"), encoding="utf-8")
        document = export_translation(self.mod)
        for entry in document["entries"]:
            entry.update(role="LINKED", group="design", translation="No placeholder")
        with self.assertRaisesRegex(TranslationError, "Linked translation rejected"):
            apply_translation(self.mod, document, self.output)
        self.assertFalse(self.output.exists())

    def test_extra_hash_cannot_escape_source_root(self):
        self.document["file_hashes"]["../outside"] = "0" * 64
        with self.assertRaisesRegex(TranslationError, "Unsafe relative source path"):
            apply_translation(self.mod, self.document, self.output)
        self.assertFalse(self.output.exists())

    def test_schema_kind_identity_and_role_drift_refuse_before_output(self):
        for field, value in (("kind", "unknown"), ("source", "forged"), ("role", "UNSAFE")):
            document = json.loads(json.dumps(self.document))
            document["entries"][0][field] = value
            with self.subTest(field=field), self.assertRaises(TranslationError):
                apply_translation(self.mod, document, self.output)
            self.assertFalse(self.output.exists())
        self.document["schema_version"] = 2
        with self.assertRaisesRegex(TranslationError, "schema_version 1"):
            apply_translation(self.mod, self.document, self.output)
