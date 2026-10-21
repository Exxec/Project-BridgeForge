"""ROADMAP-3 item 80.1: changelog fragments."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from bridgeforge.cli import main
from bridgeforge.release_notes import ReleaseNotesError, assemble, pending_fragments
from tests.support import resolved_temp_dir

CHANGELOG = "# Changelog\n\n## 0.5.0 (unreleased)\n\n- old one\n\n## 0.4.0 (unreleased)\n\n- older\n"


def make_repo(root: Path, fragments: dict[str, str], changelog: str = CHANGELOG) -> None:
    (root / "changelog.d").mkdir()
    (root / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    for name, text in fragments.items():
        (root / "changelog.d" / name).write_text(text, encoding="utf-8")


class ReleaseNotesTests(unittest.TestCase):
    def test_assemble_inserts_in_name_order_under_top_heading_and_deletes(self) -> None:
        with resolved_temp_dir() as tmp:
            make_repo(tmp, {"b-two.md": "- two\n", "a-one.md": "one\n", "README.md": "ignored"})
            moved = assemble(tmp)
            text = (tmp / "CHANGELOG.md").read_text(encoding="utf-8")
            self.assertEqual(moved, ["a-one.md", "b-two.md"])
            self.assertIn("## 0.5.0 (unreleased)\n\n- one\n- two\n\n- old one\n", text)
            self.assertEqual(pending_fragments(tmp), [])
            self.assertTrue((tmp / "changelog.d" / "README.md").exists())

    def test_version_selects_another_heading(self) -> None:
        with resolved_temp_dir() as tmp:
            make_repo(tmp, {"x.md": "- x"})
            assemble(tmp, "0.4.0")
            self.assertIn("## 0.4.0 (unreleased)\n\n- x\n\n- older", (tmp / "CHANGELOG.md").read_text(encoding="utf-8"))

    def test_missing_heading_or_empty_fragment_changes_nothing(self) -> None:
        with resolved_temp_dir() as tmp:
            make_repo(tmp, {"x.md": "- x"})
            with self.assertRaises(ReleaseNotesError):
                assemble(tmp, "9.9.9")
            self.assertEqual(len(pending_fragments(tmp)), 1)
            (tmp / "changelog.d" / "y.md").write_text("  \n", encoding="utf-8")
            with self.assertRaises(ReleaseNotesError):
                assemble(tmp)
            self.assertEqual((tmp / "CHANGELOG.md").read_text(encoding="utf-8"), CHANGELOG)

    def test_dry_run_and_check_cli(self) -> None:
        with resolved_temp_dir() as tmp:
            make_repo(tmp, {"x.md": "- x"})
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["release-notes", "--check", "--root", str(tmp)]), 1)
                self.assertEqual(main(["release-notes", "assemble", "--dry-run", "--root", str(tmp)]), 0)
            self.assertIn("x.md", out.getvalue())
            self.assertEqual(len(pending_fragments(tmp)), 1)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["release-notes", "assemble", "--root", str(tmp)]), 0)
                self.assertEqual(main(["release-notes", "--check", "--root", str(tmp)]), 0)

    def test_repository_fragment_folder_has_a_readme(self) -> None:
        self.assertTrue((Path(__file__).resolve().parent.parent / "changelog.d" / "README.md").exists())


if __name__ == "__main__":
    unittest.main()
