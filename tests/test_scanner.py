import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from bridgeforge.scanner import scan_mod
from bridgeforge.report import write_artifacts
from bridgeforge.migrate import apply_plan, build_plan
from bridgeforge.models import TargetProfile
from bridgeforge.workspace import create_workspace, rollback, workspace_paths


class ScannerTests(unittest.TestCase):
    def test_scans_metadata_bytecode_and_assets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text(json.dumps({"id": "legacy", "gameVersion": "0.95.1a", "dependencies": ["MagicLib"]}), encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "Example.java").write_text("import sun.misc.Unsafe;", encoding="utf-8")
            (root / "data").mkdir()
            (root / "data" / "broken.json").write_text("{", encoding="utf-8")
            with zipfile.ZipFile(root / "LazyLib.jar", "w") as archive:
                archive.writestr("Example.class", b"\xca\xfe\xba\xbe\x00\x00\x00\x34")
            result = scan_mod(root)
            self.assertEqual(result.estimated_starsector, "0.95.1a")
            self.assertEqual(result.estimated_java, "8")
            self.assertTrue(any(f.id == "bundled-lazylib" for f in result.findings))
            self.assertTrue(any(f.id == "internal-jvm-api" for f in result.findings))
            self.assertTrue(any(f.id == "invalid-json" for f in result.findings))

    def test_refuses_artifacts_inside_original_mod(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = scan_mod(root)
            with self.assertRaises(ValueError):
                write_artifacts(result, root / "artifacts")

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
