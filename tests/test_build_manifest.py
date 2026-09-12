from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.build_tag import apply_build_tag, compute_working_copy_hashes, record_build_manifest


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class BuildManifestTests(unittest.TestCase):
    def test_apply_build_tag_records_manifest_outside_mod_folder(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as manifests_dir:
            root = Path(mod_dir)
            _write(root / "mod_info.json", '{"id":"fixture_mod","name":"Fixture","version":"1.0"}')
            _write(root / "data" / "hulls" / "ship_data.csv", "id\nfixture_hull\n")

            result = apply_build_tag(root, manifests_dir=Path(manifests_dir), record_manifest=True)

            manifest_path = Path(result["manifest_path"])
            self.assertTrue(manifest_path.is_file())
            self.assertTrue(str(manifest_path).startswith(str(Path(manifests_dir))))
            self.assertNotIn(str(root), str(manifest_path))  # never inside the mod folder

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["mod_id"], "fixture_mod")
            self.assertEqual(manifest["build"], 1)
            self.assertIn("data/hulls/ship_data.csv", manifest["files"])
            self.assertIn("mod_info.json", manifest["files"])

    def test_dry_run_never_writes_a_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as manifests_dir:
            root = Path(mod_dir)
            _write(root / "mod_info.json", '{"id":"fixture_mod","name":"Fixture","version":"1.0"}')
            apply_build_tag(root, dry_run=True, manifests_dir=Path(manifests_dir), record_manifest=True)
            self.assertEqual(list(Path(manifests_dir).rglob("*.json")), [])

    def test_record_manifest_defaults_to_off(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as manifests_dir:
            root = Path(mod_dir)
            _write(root / "mod_info.json", '{"id":"fixture_mod","name":"Fixture","version":"1.0"}')
            result = apply_build_tag(root, manifests_dir=Path(manifests_dir))
            self.assertNotIn("manifest_path", result)
            self.assertEqual(list(Path(manifests_dir).rglob("*.json")), [])

    def test_record_manifest_false_skips_recording_even_with_manifests_dir(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as manifests_dir:
            root = Path(mod_dir)
            _write(root / "mod_info.json", '{"id":"fixture_mod","name":"Fixture","version":"1.0"}')
            result = apply_build_tag(root, manifests_dir=Path(manifests_dir), record_manifest=False)
            self.assertNotIn("manifest_path", result)
            self.assertEqual(list(Path(manifests_dir).rglob("*.json")), [])

    def test_manifest_hashes_change_when_a_file_changes(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir:
            root = Path(mod_dir)
            _write(root / "mod_info.json", '{"id":"fixture_mod","name":"Fixture","version":"1.0"}')
            _write(root / "data" / "hulls" / "ship_data.csv", "id\nfixture_hull\n")
            before = compute_working_copy_hashes(root)
            _write(root / "data" / "hulls" / "ship_data.csv", "id\nfixture_hull\nsecond_hull\n")
            after = compute_working_copy_hashes(root)
            self.assertNotEqual(before["data/hulls/ship_data.csv"], after["data/hulls/ship_data.csv"])

    def test_record_build_manifest_uses_caller_dir_over_default(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as manifests_dir:
            root = Path(mod_dir)
            _write(root / "mod_info.json", '{"id":"fixture_mod","name":"Fixture","version":"1.0"}')
            info = record_build_manifest(root, 7, manifests_dir=Path(manifests_dir))
            self.assertEqual(info["build"], 7)
            self.assertTrue(Path(info["path"]).is_file())
            self.assertEqual(Path(info["path"]).name, "r7.json")


if __name__ == "__main__":
    unittest.main()
