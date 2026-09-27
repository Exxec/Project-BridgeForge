import tempfile
import unittest
from pathlib import Path

from bridgeforge.workspace import create_workspace, workspace_paths
from bridgeforge.save_risk import analyze_save_risk



class Save_riskTests(unittest.TestCase):
    def test_save_risk_flags_changed_persistent_identifier(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "config.json").write_text('{"factionId": "legacy"}', encoding="utf-8")
            workspace = create_workspace(source, root / "workspace")
            _, working, _ = workspace_paths(workspace)
            (working / "config.json").write_text('{"factionIdRenamed": "modern"}', encoding="utf-8")
            result = analyze_save_risk(workspace)
            self.assertEqual(result["risk"], "HIGH")


    def test_save_risk_flags_identifier_value_change_and_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "a.json").write_text('{"factionId": "old"}', encoding="utf-8")
            (source / "deleted.json").write_text('{"shipId": "removed"}', encoding="utf-8")
            workspace = create_workspace(source, root / "workspace")
            _, working, _ = workspace_paths(workspace)
            (working / "a.json").write_text('{"factionId": "new"}', encoding="utf-8")
            (working / "deleted.json").unlink()
            result = analyze_save_risk(workspace)
            self.assertEqual(len(result["findings"]), 2)


