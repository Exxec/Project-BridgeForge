import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.scanner import scan_mod
from bridgeforge.report import write_artifacts
from bridgeforge.migrate import build_plan
from bridgeforge.models import TargetProfile
from bridgeforge.workspace import create_workspace, workspace_paths
from bridgeforge.interface import export_patch, inspect_workspace



class WorkspaceTests(unittest.TestCase):
    def test_refuses_artifacts_inside_original_mod(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = scan_mod(root)
            with self.assertRaises(ValueError):
                write_artifacts(result, root / "artifacts")


    def test_inspect_and_patch_export_exclude_original_mod(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "mod_info.json").write_text(json.dumps({"id": "legacy", "gameVersion": "0.95"}), encoding="utf-8")
            workspace = create_workspace(source, root / "workspace")
            build_plan(workspace, TargetProfile("0.98", 17))
            self.assertEqual(len(inspect_workspace(workspace)["planned_migrations"]), 1)
            output = export_patch(workspace, root / "patch")
            self.assertTrue((output / "migration-plan.json").is_file())
            self.assertFalse((output / "original-reference").exists())


    def test_workspace_rejects_manifest_path_escape_and_repeated_plan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "mod_info.json").write_text(json.dumps({"gameVersion": "0.95"}), encoding="utf-8")
            workspace = create_workspace(source, root / "workspace")
            build_plan(workspace, TargetProfile("0.98", 17))
            build_plan(workspace, TargetProfile("0.98", 17))
            self.assertTrue((workspace / "checkpoints" / "01-scanned-2").is_dir())
            manifest = json.loads((workspace / "workspace-manifest.json").read_text(encoding="utf-8"))
            manifest["working_copy"] = "../source"
            (workspace / "workspace-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(ValueError):
                workspace_paths(workspace)


    def test_workspace_rejects_manifest_symlink_escape_when_supported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "mod_info.json").write_text("{}", encoding="utf-8")
            workspace = create_workspace(source, root / "workspace")
            outside = root / "outside"
            outside.mkdir()
            link = workspace / "linked-working-copy"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest("symlink creation is unavailable in this environment")
            manifest = json.loads((workspace / "workspace-manifest.json").read_text(encoding="utf-8"))
            manifest["working_copy"] = link.name
            (workspace / "workspace-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(ValueError):
                workspace_paths(workspace)


