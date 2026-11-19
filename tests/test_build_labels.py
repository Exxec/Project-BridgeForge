"""ROADMAP-3 96.5 A1: records name the build a mod was revived for and the build a rig's core reports, not a fixed "RC8"."""
from __future__ import annotations

import json
import unittest

from bridgeforge.game_version import revival_build, rig_label
from bridgeforge.master_log import GENERIC, _revived_for
from bridgeforge.mod_changelog import archived_text, note_build, seed_from_archives
from tests.bound_runs import write_core_build
from tests.support import resolved_temp_dir
from bridgeforge.mod_changelog import merged_text


def _working(root, game_version: str | None, revive_target: str | None = None, *, applied: bool = True):
    working = root / "Mod" / "working"
    working.mkdir(parents=True)
    info = {"id": "m", "name": "Mod"} | ({"gameVersion": game_version} if game_version is not None else {})
    (working / "mod_info.json").write_text(json.dumps(info), encoding="utf-8")
    if revive_target:
        revive = root / "Mod" / "reports" / "revive"
        revive.mkdir(parents=True)
        (revive / "REVIVE.json").write_text(json.dumps({"mode": "REVIVE", "apply": applied, "target": revive_target}), encoding="utf-8")
    return working


class RevivalBuildTests(unittest.TestCase):
    def test_a_retargeted_gameversion_is_newer_than_the_revive_it_came_from(self) -> None:
        # `retarget` moves gameVersion to the new build and leaves REVIVE.json at the build the mod was first revived for.
        with resolved_temp_dir() as root:
            self.assertEqual(revival_build(_working(root, "0.98.5a-RC7", revive_target="0.98a-RC8")), "0.98.5a-RC7")

    def test_a_revive_against_a_newer_build_of_the_same_release_wins_over_its_gameversion(self) -> None:
        # Review 2026-11-17: revive's fixer leaves "0.98.5a-RC3" alone under an RC7 target (same release), so gameVersion lags.
        with resolved_temp_dir() as root:
            self.assertEqual(revival_build(_working(root, "0.98.5a-RC3", revive_target="0.98.5a-RC7")), "0.98.5a-RC7")

    def test_an_authors_short_version_falls_back_to_the_target_revive_applied(self) -> None:
        # Templars Maelstrom Expanded declares "0.98": revived for RC8 on 2026-10-13, archived on 2026-11-17.
        with resolved_temp_dir() as root:
            self.assertEqual(revival_build(_working(root, "0.98", revive_target="0.98a-RC8")), "0.98a-RC8")

    def test_a_dry_run_or_a_release_name_alone_names_no_build(self) -> None:
        with resolved_temp_dir() as root:
            self.assertIsNone(revival_build(_working(root, "0.98", revive_target="0.98.5a-RC7", applied=False)))
        with resolved_temp_dir() as root:
            self.assertIsNone(revival_build(_working(root, "0.98a")))
        with resolved_temp_dir() as root:
            self.assertIsNone(revival_build(_working(root, None)))


class RigLabelTests(unittest.TestCase):
    def test_a_rig_is_named_by_the_build_its_core_reports(self) -> None:
        with resolved_temp_dir() as root:
            (root / "rig" / "starsector-core").mkdir(parents=True)
            write_core_build(root / "rig" / "starsector-core", "0.98.5a-RC7")
            self.assertEqual(rig_label(root / "rig"), "0.98.5a-RC7 rig")

    def test_the_core_the_manifest_recorded_wins_over_where_the_junction_points_now(self) -> None:
        with resolved_temp_dir() as root:
            (root / "rig" / "starsector-core").mkdir(parents=True)
            write_core_build(root / "rig" / "starsector-core", "0.98.5a-RC8")
            (root / "launched-core").mkdir()
            write_core_build(root / "launched-core", "0.98.5a-RC7")
            self.assertEqual(rig_label(root / "rig", core=root / "launched-core"), "0.98.5a-RC7 rig")

    def test_an_unreadable_core_or_no_rig_claims_no_build(self) -> None:
        with resolved_temp_dir() as root:
            (root / "rig" / "starsector-core").mkdir(parents=True)
            self.assertEqual(rig_label(root / "rig"), "rig (build not read)")
        self.assertEqual(rig_label(None), "rig (build not read)")


def _note(folder: str, credit: str | None) -> str:
    line = f"**Original author: a.** {credit}\n\n" if credit else ""
    return f"# {folder} 1.0: archive note\n\n{line}Revival report status: **LIVE_VALIDATED** (archived 2026-11-17)\n"


class ChangelogTextTests(unittest.TestCase):
    def test_the_line_names_the_build_and_keeps_the_legacy_rc8_words(self) -> None:
        self.assertEqual(archived_text("0.98.5a-RC7", "LIVE_VALIDATED"), "revived for 0.98.5a-RC7 and archived (live validated)")
        # Lines written while RC8 was the only target said "RC8"; the same words keep a re-seed from duplicating them.
        self.assertEqual(archived_text("0.98a-RC8", "LIVE_VALIDATED"), "revived for RC8 and archived (live validated)")
        self.assertEqual(archived_text(None, None), "revived and archived (no status)")

    def test_seeding_reads_the_build_from_each_archive_note(self) -> None:
        with resolved_temp_dir() as root:
            done = root / "Done"
            notes = {"New": "Revival for Starsector 0.98.5a-RC7: BridgeForge by Exxec.", "Old": "Revival for Starsector 0.98a-RC8: BridgeForge by Exxec.",
                     "Unknown": "Revival: BridgeForge by Exxec.", "Handmade": None}
            for folder, credit in notes.items():
                (done / folder).mkdir(parents=True)
                (done / folder / "ARCHIVE_NOTE.md").write_text(_note(folder, credit), encoding="utf-8")
            changelog = root / "MOD_CHANGELOG.md"
            seed_from_archives(done, changelog)
            again = seed_from_archives(done, changelog)
            text = merged_text(changelog)
        self.assertIn("- **New 1.0**: revived for 0.98.5a-RC7 and archived (live validated)", text)
        self.assertIn("- **Old 1.0**: revived for RC8 and archived (live validated)", text)
        # Review 2026-11-17: a credit line naming no build is not an RC8 claim; a note older than the credit line is.
        self.assertIn("- **Unknown 1.0**: revived and archived (live validated)", text)
        self.assertIn("- **Handmade 1.0**: revived for RC8 and archived (live validated)", text)
        self.assertEqual(again, 0)

    def test_the_master_log_reads_a_note_as_the_seed_does(self) -> None:
        for credit, expected in (("Revival for Starsector 0.98.5a-RC7: BridgeForge by Exxec.", "Revived for 0.98.5a-RC7"),
                                 ("Revival for Starsector 0.98a-RC8: BridgeForge by Exxec.", "Revived for RC8"),
                                 ("Revival: BridgeForge by Exxec.", "Revived"), (None, "Revived for RC8")):
            with self.subTest(credit=credit):
                self.assertEqual(_revived_for(_note("M", credit)), expected)
                self.assertEqual(note_build(_note("M", credit)) is None, expected == "Revived")

    def test_only_a_whole_generated_line_is_generic(self) -> None:
        for line in ("revived for RC8 and archived (live validated)", "revived for 0.98.5a-RC7 and archived (live validated)",
                     "revived and archived (no status)"):
            with self.subTest(line=line):
                self.assertTrue(GENERIC.search(line))
        # Review 2026-11-17: hand-written notes that mention archiving stay in the master log.
        for line in ("re-revived and archived after the save-crash fix", "revived for 0.98a-RC8 (2026-10-13) and archived (live validated)"):
            with self.subTest(line=line):
                self.assertIsNone(GENERIC.search(line))


class ReportDraftTests(unittest.TestCase):
    def test_the_draft_names_the_build_its_core_reports_or_none(self) -> None:
        from bridgeforge.revival_report_draft import draft_revival_report
        from tests.test_revival_report_draft import _clean_mod

        with resolved_temp_dir() as root:
            core = root / "core"
            core.mkdir()
            write_core_build(core, "0.98.5a-RC7")
            named = draft_revival_report(_clean_mod(root / "A"), vanilla_core=core)
            (root / "unread").mkdir()
            unread = draft_revival_report(_clean_mod(root / "B"), vanilla_core=root / "unread")
        self.assertIn("# Revival Report: Fixture (0.98.5a-RC7)\n", named["report_text"])
        self.assertIn("compiled against 0.98.5a-RC7)", named["report_text"])
        self.assertNotIn("0.98a-RC8", named["report_text"])
        self.assertIn("# Revival Report: Fixture\n", unread["report_text"])
        self.assertIn("compiled against the given core)", unread["report_text"])


if __name__ == "__main__":
    unittest.main()
