"""ROADMAP-3 96.5 A1: records name the build a mod was revived for and the build a rig's core reports, not a fixed "RC8"."""
from __future__ import annotations

import json
import unittest

from bridgeforge.game_version import revival_build, rig_label
from bridgeforge.master_log import GENERIC, _revived_for
from bridgeforge.mod_changelog import archived_text, seed_from_archives
from tests.bound_runs import write_core_build
from tests.support import resolved_temp_dir


def _working(root, game_version: str | None, revive_target: str | None = None):
    working = root / "Mod" / "working"
    working.mkdir(parents=True)
    info = {"id": "m", "name": "Mod"} | ({"gameVersion": game_version} if game_version is not None else {})
    (working / "mod_info.json").write_text(json.dumps(info), encoding="utf-8")
    if revive_target:
        revive = root / "Mod" / "reports" / "revive"
        revive.mkdir(parents=True)
        (revive / "REVIVE.json").write_text(json.dumps({"mode": "REVIVE", "target": revive_target}), encoding="utf-8")
    return working


class RevivalBuildTests(unittest.TestCase):
    def test_the_gameversion_revive_and_retarget_wrote_is_the_build(self) -> None:
        with resolved_temp_dir() as root:
            self.assertEqual(revival_build(_working(root, "0.98.5a-RC7", revive_target="0.98a-RC8")), "0.98.5a-RC7")

    def test_an_authors_short_version_falls_back_to_the_target_revive_recorded(self) -> None:
        # Templars Maelstrom Expanded declares "0.98": revived for RC8 on 2026-10-13, archived on 2026-11-17.
        with resolved_temp_dir() as root:
            self.assertEqual(revival_build(_working(root, "0.98", revive_target="0.98a-RC8")), "0.98a-RC8")

    def test_no_build_anywhere_claims_none(self) -> None:
        with resolved_temp_dir() as root:
            self.assertIsNone(revival_build(_working(root, None)))


class RigLabelTests(unittest.TestCase):
    def test_a_rig_is_named_by_the_build_its_core_reports(self) -> None:
        with resolved_temp_dir() as root:
            (root / "rig" / "starsector-core").mkdir(parents=True)
            write_core_build(root / "rig" / "starsector-core", "0.98.5a-RC7")
            self.assertEqual(rig_label(root / "rig"), "0.98.5a-RC7 rig")

    def test_an_unreadable_core_or_no_rig_claims_no_build(self) -> None:
        with resolved_temp_dir() as root:
            (root / "rig" / "starsector-core").mkdir(parents=True)
            self.assertEqual(rig_label(root / "rig"), "rig (build not read)")
        self.assertEqual(rig_label(None), "rig (build not read)")


class ChangelogTextTests(unittest.TestCase):
    def test_the_line_names_the_build_and_keeps_the_legacy_rc8_words(self) -> None:
        self.assertEqual(archived_text("0.98.5a-RC7", "LIVE_VALIDATED"), "revived for 0.98.5a-RC7 and archived (live validated)")
        # Lines written while RC8 was the only target said "RC8"; the same words keep a re-seed from duplicating them.
        self.assertEqual(archived_text("0.98a-RC8", "LIVE_VALIDATED"), "revived for RC8 and archived (live validated)")
        self.assertEqual(archived_text(None, None), "revived and archived (no status)")

    def test_seeding_reads_the_build_from_each_archive_note(self) -> None:
        with resolved_temp_dir() as root:
            done = root / "Done"
            for folder, build in (("New", "0.98.5a-RC7"), ("Old", "0.98a-RC8")):
                (done / folder).mkdir(parents=True)
                (done / folder / "ARCHIVE_NOTE.md").write_text(
                    f"# {folder} 1.0: archive note\n\n**Original author: a.** Revival for Starsector {build}: BridgeForge by Exxec.\n\n"
                    "Revival report status: **LIVE_VALIDATED** (archived 2026-11-17)\n", encoding="utf-8")
            changelog = root / "MOD_CHANGELOG.md"
            seed_from_archives(done, changelog)
            text = changelog.read_text(encoding="utf-8")
        self.assertIn("- **New 1.0**: revived for 0.98.5a-RC7 and archived (live validated)", text)
        self.assertIn("- **Old 1.0**: revived for RC8 and archived (live validated)", text)

    def test_the_master_log_treats_every_build_line_as_generic_and_names_the_notes_build(self) -> None:
        for line in ("revived for RC8 and archived (live validated)", "revived for 0.98.5a-RC7 and archived (live validated)",
                     "revived and archived (no status)"):
            with self.subTest(line=line):
                self.assertTrue(GENERIC.search(line))
        self.assertEqual(_revived_for("x Revival for Starsector 0.98.5a-RC7: BridgeForge by Exxec."), "Revived for 0.98.5a-RC7")
        self.assertEqual(_revived_for("x Revival for Starsector 0.98a-RC8: BridgeForge by Exxec."), "Revived for RC8")
        self.assertEqual(_revived_for("a note without a credit line"), "Revived")


if __name__ == "__main__":
    unittest.main()
