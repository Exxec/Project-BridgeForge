"""Board: empty workspace skeletons (ROADMAP-3 item 92.24) and revived work with no backup (92.37), 2026-11-16."""
from __future__ import annotations

import json
import unittest

from bridgeforge.project_board import project_board, render_board
from tests.support import resolved_temp_dir


class BoardTests(unittest.TestCase):
    def test_a_folder_tree_with_no_files_is_an_empty_skeleton(self) -> None:
        with resolved_temp_dir() as root:
            (root / "In operation" / "Hollow" / "original" / "SCY").mkdir(parents=True)
            (root / "In operation" / "Partial" / "original").mkdir(parents=True)
            (root / "In operation" / "Partial" / "original" / "note.txt").write_text("x", encoding="utf-8")
            stages = {row["folder"]: row["stage"] for row in project_board(root)["mods"]}
        self.assertEqual(stages["Hollow"], "EMPTY_SKELETON")
        self.assertEqual(stages["Partial"], "LAYOUT_INCOMPLETE")  # has a file: incomplete, not hollow

    def test_revived_workspaces_without_a_snapshot_destination_are_listed(self) -> None:
        with resolved_temp_dir() as root:
            ws = root / "In operation" / "Mod"
            (ws / "working").mkdir(parents=True)
            (ws / "working" / "mod_info.json").write_text('{"id":"m","name":"M","version":"1"}', encoding="utf-8")
            (ws / "reports" / "revive").mkdir(parents=True)
            (ws / "reports" / "revive" / "REVIVE.json").write_text(json.dumps({"status": "UNATTENDED_DONE"}), encoding="utf-8")
            unbacked = project_board(root)
            (root / "bridgeforge-state").mkdir()
            (root / "bridgeforge-state" / "snapshot.json").write_text('{"to": "D:/backup"}', encoding="utf-8")
            backed = project_board(root)
        self.assertEqual(unbacked["backup"]["revived_unbacked"], ["Mod"])
        self.assertIn("exist only here", render_board(unbacked))
        self.assertEqual(backed["backup"]["revived_unbacked"], [])
        self.assertNotIn("## Backup", render_board(backed))


if __name__ == "__main__":
    unittest.main()
