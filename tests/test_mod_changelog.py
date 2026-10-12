"""MOD_CHANGELOG.md: bigger updates to revived mods by date (2026-09-30)."""
from __future__ import annotations

import unittest

from bridgeforge.mod_changelog import add_entry, seed_from_archives
from tests.support import resolved_temp_dir


class ModChangelogTests(unittest.TestCase):
    def test_entries_group_by_date_newest_first_without_duplicates(self) -> None:
        with resolved_temp_dir() as root:
            path = root / "MOD_CHANGELOG.md"
            add_entry("Old Mod", "archived", version="1.0", day="2026-09-27", path=path)
            add_entry("New Mod", "relinked a tooltip call", version="2.0+bf.1", day="2026-09-30", path=path)
            add_entry("New Mod", "relinked a tooltip call", version="2.0+bf.1", day="2026-09-30", path=path)
            text = path.read_text(encoding="utf-8")
        self.assertLess(text.index("## 2026-09-30"), text.index("## 2026-09-27"))
        self.assertEqual(text.count("**New Mod** 2.0+bf.1: relinked a tooltip call"), 1)

    def test_seed_reads_archive_notes(self) -> None:
        with resolved_temp_dir() as root:
            note = root / "Done" / "Mod" / "ARCHIVE_NOTE.md"
            note.parent.mkdir(parents=True)
            note.write_text("# Some Mod 1.2: archive note\n\nRevival report status: **LIVE_VALIDATED** (archived 2026-09-28).\n", encoding="utf-8")
            self.assertEqual(seed_from_archives(root / "Done", root / "MOD_CHANGELOG.md"), 1)
            text = (root / "MOD_CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("## 2026-09-28\n\n- **Some Mod 1.2**: revived for RC8 and archived (live validated)", text)


if __name__ == "__main__":
    unittest.main()
