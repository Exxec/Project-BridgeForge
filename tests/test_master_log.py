"""Done/MASTER_LOG.md must show each mod's own name and release version (found 2026-10-12: 17 archives were listed as "LazyLib")."""
from __future__ import annotations

import unittest
from pathlib import Path

from bridgeforge.master_log import archive_row
from tests.support import resolved_temp_dir


def _archive(done: Path, folder: str, mod_info: str) -> Path:
    root = done / folder
    (root / "Inner").mkdir(parents=True)
    (root / "ARCHIVE_NOTE.md").write_text(f"# {folder}: archive note\n\nStatus LIVE_VALIDATED on 2026-10-12.\n", encoding="utf-8")
    (root / "Inner" / "mod_info.json").write_text(mod_info, encoding="utf-8")
    return root


class ModInfoFieldsTests(unittest.TestCase):
    def test_a_mod_info_that_lists_dependencies_first_shows_the_mods_own_name_and_version(self) -> None:
        info = ('{"dependencies":[{"id":"lw_lazylib","name":"LazyLib","version":"3.0.0"}],\n'
                '\t"id":"Sylphon_RnD", # internal id\n\t"name":"Sylphon RnD", # shown\n\t"version":"1.0+bf.1",\n}')
        with resolved_temp_dir() as base:
            row = archive_row(_archive(base / "Done", "Sylphon-RnD", info), [], base / "In operation")
        self.assertEqual((row["mod"], row["release_version"]), ("Sylphon RnD", "1.0+bf.1"))

    def test_an_object_version_is_joined_and_a_missing_name_falls_back_to_the_note_title(self) -> None:
        info = '{"id":"x", "version":{"major":"0","minor":"9","patch":"1a"}}'
        with resolved_temp_dir() as base:
            row = archive_row(_archive(base / "Done", "Titled", info), [], base / "In operation")
        self.assertEqual((row["mod"], row["release_version"]), ("Titled", "0.9.1a"))


if __name__ == "__main__":
    unittest.main()
