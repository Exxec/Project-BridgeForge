"""ROADMAP-3 item 80.3: the dropped-feature sweep and content parity gate the archive, with `--allow-unexplained` and the probe offer."""
from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

from bridgeforge.archive import ArchiveError, archive_mod
from bridgeforge.archive_checks import archive_offer, check_reason, pre_archive_checks
from bridgeforge.release import record_policy_decision
from bridgeforge.removals import add_removals, make_entry
from bridgeforge.revise import ReviseError, _content_gates
from tests.support import resolved_temp_dir

REPO_POLICY = Path(__file__).resolve().parent.parent / "bridgeforge" / "release_policy.json"
RULES = "id,trigger,conditions,script\nr1,OpenCommLink,,\nr2,CrusadeNews,,\n"
REASON = "the rules file was split into two mods on purpose"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _workspace(root: Path) -> Path:
    """A synthetic revival: the author's original has data/campaign/rules.csv and the working copy is a copy of it."""
    ws = root / "In operation" / "Radar"
    original = ws / "original" / "Radar 3.0"
    _write(original / "mod_info.json", '{"id": "bf_fixture_radar", "name": "Radar", "author": "LazyWizard", "version": "3.0"}')
    _write(original / "data" / "campaign" / "rules.csv", RULES)
    shutil.copytree(original, ws / "working")
    _write(ws / "working" / "mod_info.json", '{"id": "bf_fixture_radar", "name": "Radar", "author": "LazyWizard", "version": "3.0", '
                                              '"gameVersion": "0.98a-RC8"}')
    _write(ws / "working" / "reports" / "REVIVAL_REPORT.md", "# Report\n\nREADY_FOR_LIVE_TEST\n")
    return ws


def _policy(root: Path) -> Path:
    policy = root / "policy.json"
    shutil.copy2(REPO_POLICY, policy)
    record_policy_decision("bf_fixture_radar", local_only=True, reason="author unreachable", policy_path=policy)
    return policy


def _drop_rules(ws: Path) -> None:
    (ws / "working" / "data" / "campaign" / "rules.csv").unlink()


def _explain_drop(ws: Path) -> None:
    """REMOVALS.json entries for the dropped rules.csv, as a file and as a rules.csv category."""
    add_removals(ws / "working", [make_entry("files", pattern="data/campaign/rules.csv", reason=REASON, source="owner"),
                                  make_entry("rules.csv", pattern="*", reason=REASON, source="owner")])


class ArchiveGateTests(unittest.TestCase):
    def test_a_clean_workspace_passes_both_checks_and_writes_no_override_section(self) -> None:
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            checks = pre_archive_checks(ws)
            result = archive_mod(ws, root / "Done", policy_path=_policy(root), today="2026-10-21")
            note = (root / "Done" / "Radar" / "ARCHIVE_NOTE.md").read_text(encoding="utf-8")
        self.assertEqual(checks, {"problems": [], "warnings": []})
        self.assertIsNone(result["allowed_unexplained"])
        self.assertNotIn("--allow-unexplained", note)

    def test_unexplained_dropped_features_refuse_before_anything_is_written(self) -> None:
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            _drop_rules(ws)
            policy = _policy(root)
            with self.assertRaises(ArchiveError) as caught:
                archive_mod(ws, root / "Done", policy_path=policy)
            done_entries = list((root / "Done").iterdir()) if (root / "Done").exists() else []
        message = str(caught.exception)
        self.assertIn("dropped features no REMOVALS.json entry explains", message)
        self.assertIn("dropped rules.csv", message)
        self.assertIn("missing from the archive: data/campaign/rules.csv", message)
        self.assertIn("--allow-unexplained REASON", message)
        self.assertEqual(done_entries, [])

    def test_recorded_removals_explain_the_drop_and_the_archive_goes_ahead(self) -> None:
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            _drop_rules(ws)
            _explain_drop(ws)
            result = archive_mod(ws, root / "Done", policy_path=_policy(root), today="2026-10-21")
            archived = Path(result["archive"]).is_dir()
        self.assertIsNone(result["allowed_unexplained"])
        self.assertTrue(archived)

    def test_allow_unexplained_archives_and_records_the_reason_and_the_refused_items(self) -> None:
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            _drop_rules(ws)
            result = archive_mod(ws, root / "Done", policy_path=_policy(root), today="2026-10-21", allow_unexplained=REASON)
            note = (root / "Done" / "Radar" / "ARCHIVE_NOTE.md").read_text(encoding="utf-8")
        self.assertEqual(result["allowed_unexplained"]["reason"], REASON)
        self.assertIn("## Archived past its checks (--allow-unexplained)", note)
        self.assertIn(f"Reason recorded by the owner: {REASON}", note)
        self.assertIn("missing from the archive: data/campaign/rules.csv", note)

    def test_allow_unexplained_needs_twenty_characters_and_refuses_otherwise(self) -> None:
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            _drop_rules(ws)
            with self.assertRaises(ArchiveError) as caught:
                archive_mod(ws, root / "Done", policy_path=_policy(root), allow_unexplained="  too short  ")
            self.assertFalse((root / "Done").exists())
        self.assertIn("at least 20 characters", str(caught.exception))

    def test_an_undetermined_check_is_a_warning_not_a_refusal(self) -> None:
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            shutil.rmtree(ws / "original")
            result = archive_mod(ws, root / "Done", policy_path=_policy(root), today="2026-10-21")
        self.assertTrue(any(w.startswith("dropped-feature sweep undetermined") for w in result["warnings"]))
        self.assertTrue(any(w.startswith("content parity undetermined") for w in result["warnings"]))

    def test_content_parity_refusal_is_listed_when_the_sweep_is_satisfied(self) -> None:
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            _drop_rules(ws)
            _explain_drop(ws)
            _write(ws / "original" / "Radar 3.0" / "data" / "campaign" / "gone.csv", "1")
            checks = pre_archive_checks(ws)
        parity = [p for p in checks["problems"] if p.startswith("content parity against original/")]
        self.assertEqual(len(parity), 1)
        self.assertIn("missing from the archive: data/campaign/gone.csv", parity[0])


class RevisedGateTests(unittest.TestCase):
    def test_revise_finalize_refuses_before_its_first_write_unless_overridden(self) -> None:
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            _drop_rules(ws)
            journal = {"revision_id": "bf_fixture_radar-3.0+bf.1", "candidate": {}, "state": "PREPARED"}
            with self.assertRaises(ReviseError) as caught:
                _content_gates(ws, None, journal)
            self.assertIn("--allow-unexplained REASON", str(caught.exception))
            self.assertNotIn("allowed_unexplained", journal)
            _content_gates(ws, REASON, journal)
        self.assertEqual(journal["allowed_unexplained"]["reason"], REASON)
        self.assertTrue(any("rules.csv" in p for p in journal["allowed_unexplained"]["problems"]))

    def test_the_reason_is_checked_before_finalize_reads_anything(self) -> None:
        with self.assertRaises(ValueError):
            check_reason("short")
        self.assertEqual(check_reason("  " + REASON + "  "), REASON)
        self.assertIsNone(check_reason(None))


class ProbeOfferTests(unittest.TestCase):
    def test_a_passing_candidate_on_probe_0_3_0_is_offered_the_refresh_command_and_nothing_runs(self) -> None:
        with resolved_temp_dir() as root:
            queue = root / "In operation"
            ws = queue / "Radar"
            ws.mkdir(parents=True)
            lines = archive_offer({"probe_version": "0.3.0", "test_id": "T-1", "recorded": ["Radar"], "archived": []}, queue)
            self.assertEqual(lines, [f'  To archive Radar (offered, not run): bridgeforge archive "{ws}" --refresh'])
            self.assertFalse((root / "Done").exists())

    def test_a_pending_revision_is_offered_its_finalize_command(self) -> None:
        with resolved_temp_dir() as root:
            queue = root / "In operation"
            revisions = queue / "Radar" / "reports" / "revisions"
            _write(revisions / "rev-1.json", json.dumps({"revision_id": "rev-1", "state": "PREPARED"}))
            lines = archive_offer({"probe_version": "0.4.1", "test_id": "T-2", "recorded": ["Radar"], "archived": []}, queue)
        self.assertEqual(len(lines), 1)
        self.assertIn("bridgeforge revise finalize", lines[0])
        self.assertIn("--revision rev-1 --test-id T-2", lines[0])

    def test_no_offer_below_probe_0_3_0_or_for_an_archived_or_unknown_version(self) -> None:
        queue = Path("unused")
        self.assertEqual(archive_offer({"probe_version": "0.2.26", "test_id": "T", "recorded": ["Radar"]}, queue), [])
        self.assertEqual(archive_offer({"probe_version": "?", "test_id": "T", "recorded": ["Radar"]}, queue), [])
        self.assertEqual(archive_offer({"probe_version": "0.3.0", "test_id": "T", "recorded": ["Radar"], "archived": ["Radar"]}, queue), [])


if __name__ == "__main__":
    unittest.main()
