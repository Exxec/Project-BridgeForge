import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from bridgeforge.migrate import apply_plan, build_plan
from bridgeforge.models import TargetProfile
from bridgeforge.workspace import create_workspace, rollback, workspace_paths



class MigrationsTests(unittest.TestCase):
    def test_workspace_plan_apply_and_rollback_preserve_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "mod_info.json").write_text(json.dumps({"id": "legacy", "gameVersion": "0.95.1a"}), encoding="utf-8")
            workspace = create_workspace(source, root / "workspace")
            plan = build_plan(workspace, TargetProfile("0.98a-RC8", 17))
            self.assertEqual(len(plan["migrations"]), 1)
            manifest = apply_plan(workspace, {"metadata-target-starsector-version"})
            self.assertEqual(len(manifest["applied"]), 1)
            _, working, _ = workspace_paths(workspace)
            self.assertEqual(json.loads((working / "mod_info.json").read_text(encoding="utf-8"))["gameVersion"], "0.98a-RC8")
            self.assertEqual(json.loads((source / "mod_info.json").read_text(encoding="utf-8"))["gameVersion"], "0.95.1a")
            rollback(workspace, "00-original")
            self.assertEqual(json.loads((working / "mod_info.json").read_text(encoding="utf-8"))["gameVersion"], "0.95.1a")


    def test_safe_rule_packs_apply_only_with_safe_flag(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "mod_info.json").write_text(json.dumps({"id": "legacy", "gameVersion": "0.95.1a"}), encoding="utf-8")
            pack = root / "safe-pack.json"
            pack.write_text(json.dumps({"pack": {"id": "fixture", "schema_version": 1}, "rules": [{"id": "fixture-safe", "classification": "SAFE", "confidence": "DETERMINISTIC", "description": "fixture", "file": "mod_info.json", "json_key": "gameVersion", "value_from_target": "starsector"}]}), encoding="utf-8")
            workspace = create_workspace(source, root / "workspace")
            plan = build_plan(workspace, TargetProfile("0.98a-RC8", 17), [pack])
            self.assertEqual(plan["rule_packs"], ["fixture"])
            self.assertEqual(len(apply_plan(workspace, set())["applied"]), 0)
            self.assertEqual(len(apply_plan(workspace, set(), apply_safe=True)["applied"]), 1)


    def test_import_migration_uses_ast_confirmed_import_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "Example.java").write_text("import old.api.Helper;\nclass Example { String note = \"import old.api.Helper;\"; }\n", encoding="utf-8")
            pack = root / "imports.json"
            pack.write_text(json.dumps({"pack": {"id": "fixture-imports", "schema_version": 1}, "rules": [{"id": "migrate-helper-import", "classification": "REVIEW", "confidence": "DETERMINISTIC", "description": "fixture", "action": "replace-import", "from_import": "old.api.Helper", "to_import": "new.api.Helper"}]}), encoding="utf-8")
            workspace = create_workspace(source, root / "workspace")
            plan = build_plan(workspace, TargetProfile(), [pack])
            self.assertEqual(len(plan["migrations"]), 1)
            apply_plan(workspace, {"migrate-helper-import"})
            _, working, _ = workspace_paths(workspace)
            content = (working / "Example.java").read_text(encoding="utf-8")
            self.assertIn("import new.api.Helper;", content)
            self.assertIn('"import old.api.Helper;"', content)


    def test_apply_preflights_all_changes_and_blocks_manual_rules(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "mod_info.json").write_text(json.dumps({"gameVersion": "0.95"}), encoding="utf-8")
            workspace = create_workspace(source, root / "workspace")
            plan = build_plan(workspace, TargetProfile("0.98", 17))
            plan["migrations"][0]["classification"] = "MANUAL"
            (workspace / "migration-plan.json").write_text(json.dumps(plan), encoding="utf-8")
            self.assertEqual(len(apply_plan(workspace, {"metadata-target-starsector-version"})["applied"]), 0)


    def test_apply_recovers_every_file_after_a_later_write_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "one.json").write_text(json.dumps({"one": "old"}), encoding="utf-8")
            (source / "two.json").write_text(json.dumps({"two": "old"}), encoding="utf-8")
            rules = root / "rules.json"
            rules.write_text(json.dumps({"pack": {"schema_version": 1, "id": "fault-test"}, "rules": [
                {"id": "one", "classification": "SAFE", "confidence": "HIGH", "description": "one", "file": "one.json", "json_key": "one", "value_from_target": "starsector"},
                {"id": "two", "classification": "SAFE", "confidence": "HIGH", "description": "two", "file": "two.json", "json_key": "two", "value_from_target": "starsector"}
            ]}), encoding="utf-8")
            workspace = create_workspace(source, root / "workspace")
            build_plan(workspace, TargetProfile("0.98", 17), [rules])
            import os
            real_replace = os.replace

            def fail_second_temp_replace(source_path: str | Path, destination_path: str | Path) -> None:
                if str(source_path).endswith("two.json.bridgeforge-tmp"):
                    raise OSError("simulated disk failure")
                real_replace(source_path, destination_path)

            with patch("bridgeforge.migrate.os.replace", side_effect=fail_second_temp_replace):
                with self.assertRaises(OSError):
                    apply_plan(workspace, {"one", "two"})
            self.assertEqual(json.loads((workspace / "working-copy" / "one.json").read_text(encoding="utf-8"))["one"], "old")
            self.assertEqual(json.loads((workspace / "working-copy" / "two.json").read_text(encoding="utf-8"))["two"], "old")


