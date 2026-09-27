import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from bridgeforge.migrate import apply_plan, build_plan
from bridgeforge.models import TargetProfile
from bridgeforge.workspace import create_workspace
from bridgeforge.conflicts import detect_conflicts
from bridgeforge.provenance import write_provenance



class ConflictsTests(unittest.TestCase):
    def test_plan_reports_conflicts_and_apply_never_starts_when_a_target_changed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "one.json").write_text(json.dumps({"one": "old"}), encoding="utf-8")
            (source / "two.json").write_text(json.dumps({"two": "old"}), encoding="utf-8")
            rules = root / "rules.json"
            rules.write_text(json.dumps({"pack": {"schema_version": 1, "id": "test"}, "rules": [
                {"id": "one", "classification": "SAFE", "confidence": "HIGH", "description": "one", "file": "one.json", "json_key": "one", "value_from_target": "starsector"},
                {"id": "two", "classification": "SAFE", "confidence": "HIGH", "description": "two", "file": "two.json", "json_key": "two", "value_from_target": "starsector"},
                {"id": "two-conflict", "classification": "SAFE", "confidence": "HIGH", "description": "conflict", "file": "two.json", "json_key": "other", "value_from_target": "starsector"}
            ]}), encoding="utf-8")
            workspace = create_workspace(source, root / "workspace")
            plan = build_plan(workspace, TargetProfile("0.98", 17), [rules])
            self.assertEqual(plan["conflicts"][0]["rule_id"], "two-conflict")
            (workspace / "working-copy" / "two.json").write_text(json.dumps({"two": "changed"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                apply_plan(workspace, {"one", "two"})
            self.assertEqual(json.loads((workspace / "working-copy" / "one.json").read_text(encoding="utf-8"))["one"], "old")


    def test_conflict_and_provenance_artifacts_are_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "mod_info.json").write_text("{}", encoding="utf-8")
            for name in ("one.jar", "two.jar"):
                with zipfile.ZipFile(source / name, "w") as archive:
                    archive.writestr("same/Thing.class", b"\xca\xfe\xba\xbe\x00\x00\x00\x34")
            workspace = create_workspace(source, root / "workspace")
            conflicts = detect_conflicts(workspace)
            provenance = write_provenance(workspace)
            repeat_provenance = write_provenance(workspace)
            (workspace / "working-copy" / "new-file.txt").write_text("changed", encoding="utf-8")
            changed_provenance = write_provenance(workspace)
            self.assertEqual(conflicts["status"], "CONFLICTS_FOUND")
            self.assertTrue(any(item["kind"] == "duplicate-class" for item in conflicts["findings"]))
            self.assertEqual(provenance["schema_version"], 1)
            self.assertEqual(provenance["working_copy_tree_sha256"], repeat_provenance["working_copy_tree_sha256"])
            self.assertNotEqual(provenance["working_copy_tree_sha256"], changed_provenance["working_copy_tree_sha256"])
            self.assertTrue((workspace / "conflicts.json").is_file())
            self.assertTrue((workspace / "provenance.json").is_file())

