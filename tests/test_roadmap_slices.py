import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from bridgeforge.archive_intake import stage_zip_archive
from bridgeforge.cli import main
from bridgeforge.corpus_audit import audit_directories
from bridgeforge.library_api import inventory_library_api, validate_library_api_inventory
from bridgeforge.models import TargetProfile


class RoadmapSlicesTests(unittest.TestCase):
    def test_stage_requires_explicit_selection_and_writes_path_minimal_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "multi.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("One/mod_info.json", "{}")
                bundle.writestr("Two/mod_info.json", "{}")
            with self.assertRaises(ValueError):
                stage_zip_archive(archive, root / "staged")
            staged = stage_zip_archive(archive, root / "staged", "One")
            manifest = root / "staged.bridgeforge-stage.json"
            data = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(staged, (root / "staged").resolve())
            self.assertEqual(data["selected_mod_root"], "One")
            self.assertTrue(data["input_preserved"])
            self.assertNotIn(str(root), json.dumps(data))

    def test_corpus_budget_summary_accounts_for_skipped_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod = Path(directory) / "mod"
            mod.mkdir()
            (mod / "mod_info.json").write_text("{}", encoding="utf-8")
            result = audit_directories([mod], TargetProfile(), max_files_per_mod=0)
            self.assertEqual(result["budget_summary"]["observed_file_count"], 1)
            self.assertEqual(result["skipped_budget_mod_count"], 1)

    def test_inventory_validation_rejects_tampered_class_count(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            jar = Path(directory) / "api.jar"
            with zipfile.ZipFile(jar, "w") as archive:
                archive.writestr("example/Api.class", b"\xca\xfe\xba\xbe")
            inventory = inventory_library_api(jar, "example", "1")
            inventory["class_count"] = 99
            with self.assertRaises(ValueError):
                validate_library_api_inventory(inventory)

    def test_archive_stage_cli_records_selected_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "one.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("Wrapper/mod_info.json", "{}")
            self.assertEqual(main(["archive-stage", str(archive), "--output", str(root / "staged")]), 0)
            self.assertTrue((root / "staged.bridgeforge-stage.json").is_file())
