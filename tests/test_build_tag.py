from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import json

from bridgeforge.build_tag import BuildTagError, apply_build_tag, record_current_manifest
from bridgeforge.cli import main
from bridgeforge.test_plan import _normalize_tag, plan_tests


class BuildTagTests(unittest.TestCase):
    def setUp(self) -> None:
        # apply_build_tag now also records a per-tag hash manifest outside the mod folder
        # (roadmap P5). Redirect its default location to a per-test temp dir so these tests never
        # write into the real repo's bridgeforge-state/ directory.
        self._manifests_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._manifests_tmp.cleanup)
        patcher = mock.patch("bridgeforge.build_tag.default_manifests_dir", return_value=Path(self._manifests_tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_fresh_add_appends_r1_and_bf_1(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text(
                '{"id":"fixture","name":"Fixture Mod","version":"1.0"}', encoding="utf-8"
            )
            result = apply_build_tag(root)
            self.assertEqual(result["old_name"], "Fixture Mod")
            self.assertEqual(result["new_name"], "Fixture Mod [BF r1]")
            self.assertEqual(result["old_version"], "1.0")
            self.assertEqual(result["new_version"], "1.0+bf.1")
            written = (root / "mod_info.json").read_text(encoding="utf-8")
            self.assertIn('"name":"Fixture Mod [BF r1]"', written)
            self.assertIn('"version":"1.0+bf.1"', written)
            self.assertIn('"id":"fixture"', written)  # id untouched, spacing preserved

    def test_increment_existing_tag(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text(
                '{"id":"fixture","name":"Fixture Mod [BF r3]","version":"1.0+bf.3"}', encoding="utf-8"
            )
            result = apply_build_tag(root)
            self.assertEqual(result["new_name"], "Fixture Mod [BF r4]")
            self.assertEqual(result["new_version"], "1.0+bf.4")
            self.assertEqual(result["build"], 4)

    def test_set_forces_build_number(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text(
                '{"id":"fixture","name":"Fixture Mod [BF r3]","version":"1.0+bf.3"}', encoding="utf-8"
            )
            result = apply_build_tag(root, set_value=9)
            self.assertEqual(result["new_name"], "Fixture Mod [BF r9]")
            self.assertEqual(result["new_version"], "1.0+bf.9")
            self.assertEqual(result["build"], 9)

    def test_custom_label(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text('{"id":"fixture","name":"Fixture Mod","version":"1.0"}', encoding="utf-8")
            result = apply_build_tag(root, label="TEST")
            self.assertEqual(result["new_name"], "Fixture Mod [TEST r1]")

    def test_single_quoted_legacy_json_with_comments_and_trailing_commas_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = (
                "{\n"
                "    'id':'fixture', # do not touch this comment\n"
                "    'name':'Fixture Mod',\n"
                "    'version':'1.0',\n"
                "}\n"
            )
            (root / "mod_info.json").write_text(original, encoding="utf-8")
            result = apply_build_tag(root)
            written = (root / "mod_info.json").read_text(encoding="utf-8")
            self.assertEqual(result["new_name"], "Fixture Mod [BF r1]")
            self.assertEqual(result["new_version"], "1.0+bf.1")
            self.assertIn("# do not touch this comment", written)
            self.assertIn("'id':'fixture'", written)
            self.assertIn("'name':'Fixture Mod [BF r1]'", written)
            self.assertIn("'version':'1.0+bf.1'", written)
            # Everything outside the two edited value spans is byte-for-byte unchanged.
            self.assertTrue(written.startswith("{\n    'id':'fixture', # do not touch this comment\n"))
            self.assertTrue(written.endswith(",\n}\n"))

    def test_object_form_version_is_left_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text(
                '{"id":"fixture","name":"Fixture Mod","version":{"major":1,"minor":0}}', encoding="utf-8"
            )
            result = apply_build_tag(root)
            self.assertTrue(result["version_is_object"])
            self.assertEqual(result["new_name"], "Fixture Mod [BF r1]")
            written = (root / "mod_info.json").read_text(encoding="utf-8")
            self.assertIn('"version":{"major":1,"minor":0}', written)

    def test_bom_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            content = '{"id":"fixture","name":"Fixture Mod","version":"1.0"}'
            (root / "mod_info.json").write_bytes(b"\xef\xbb\xbf" + content.encode("utf-8"))
            apply_build_tag(root)
            raw = (root / "mod_info.json").read_bytes()
            self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))

    def test_id_is_never_touched(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text(
                '{"id":"fixture_untouched","name":"Fixture Mod","version":"1.0"}', encoding="utf-8"
            )
            apply_build_tag(root)
            written = (root / "mod_info.json").read_text(encoding="utf-8")
            self.assertIn('"id":"fixture_untouched"', written)

    def test_dry_run_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = '{"id":"fixture","name":"Fixture Mod","version":"1.0"}'
            (root / "mod_info.json").write_text(original, encoding="utf-8")
            result = apply_build_tag(root, dry_run=True)
            self.assertEqual(result["new_name"], "Fixture Mod [BF r1]")
            self.assertEqual((root / "mod_info.json").read_text(encoding="utf-8"), original)

    def test_nested_mod_root_is_found_at_depth_two(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()  # CI temp dirs are 8.3 short paths; the code resolves them
            nested = root / "Extracted" / "MyMod 1.0"
            nested.mkdir(parents=True)
            (nested / "mod_info.json").write_text('{"id":"fixture","name":"Fixture Mod","version":"1.0"}', encoding="utf-8")
            result = apply_build_tag(root)
            self.assertEqual(Path(result["mod_info"]), nested / "mod_info.json")

    def test_missing_mod_info_raises(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(BuildTagError):
                apply_build_tag(root)

    def test_cli_dry_run_exit_code_and_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text('{"id":"fixture","name":"Fixture Mod","version":"1.0"}', encoding="utf-8")
            exit_code = main(["build-tag", str(root), "--dry-run", "--json"])
            self.assertEqual(exit_code, 0)
            self.assertEqual((root / "mod_info.json").read_text(encoding="utf-8"), '{"id":"fixture","name":"Fixture Mod","version":"1.0"}')

    def test_cli_missing_mod_info_returns_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(main(["build-tag", str(root)]), 2)

    def test_record_current_manifest_untagged_mod_writes_r0_and_does_not_touch_mod_info(self) -> None:
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as manifests_dir:
            root = Path(directory)
            mod_info = root / "mod_info.json"
            original_text = '{"id":"fixture","name":"Fixture Mod","version":"1.0"}'
            mod_info.write_text(original_text, encoding="utf-8")
            result = record_current_manifest(root, manifests_dir=Path(manifests_dir))
            self.assertEqual(result["build"], 0)
            self.assertEqual(mod_info.read_text(encoding="utf-8"), original_text)  # never bumped/written
            manifest_path = Path(result["path"])
            self.assertEqual(manifest_path.name, "r0.json")
            self.assertTrue(manifest_path.is_file())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["build"], 0)
            self.assertEqual(manifest["mod_id"], "fixture")

    def test_record_current_manifest_reads_existing_tag_without_bumping(self) -> None:
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as manifests_dir:
            root = Path(directory)
            mod_info = root / "mod_info.json"
            mod_info.write_text('{"id":"fixture","name":"Fixture Mod [BF r3]","version":"1.0+bf.3"}', encoding="utf-8")
            result = record_current_manifest(root, manifests_dir=Path(manifests_dir))
            self.assertEqual(result["build"], 3)
            self.assertEqual(Path(result["path"]).name, "r3.json")
            self.assertIn('"name":"Fixture Mod [BF r3]"', mod_info.read_text(encoding="utf-8"))  # untouched

    def test_r0_tag_is_accepted_by_test_plan_normalize_and_plan_tests(self) -> None:
        # _normalize_tag must accept the "r0" that record_current_manifest writes for an untagged mod.
        self.assertEqual(_normalize_tag("r0"), "r0")
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as manifests_dir:
            root = Path(directory)
            (root / "mod_info.json").write_text('{"id":"fixture","name":"Fixture Mod","version":"1.0"}', encoding="utf-8")
            (root / "data").mkdir()
            (root / "data" / "hulls").mkdir()
            (root / "data" / "hulls" / "ship_data.csv").write_text("id\nfoo\n", encoding="utf-8")
            record_current_manifest(root, manifests_dir=Path(manifests_dir))
            # Change a file after the r0 manifest was recorded, so plan_tests has something to diff.
            (root / "data" / "hulls" / "ship_data.csv").write_text("id\nfoo\nbar\n", encoding="utf-8")
            plan = plan_tests(root, "r0", manifests_dir=Path(manifests_dir))
            self.assertEqual(plan["since_tag"], "r0")
            self.assertIn("data/hulls/ship_data.csv", plan["changed_files"]["modified"])


if __name__ == "__main__":
    unittest.main()
