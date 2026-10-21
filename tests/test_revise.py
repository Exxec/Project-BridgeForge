"""ROADMAP item 75 R5: prepare, test, finalize a revision without changing the tested bytes."""
from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from unittest import mock

from bridgeforge import revise
from bridgeforge.archive import archive_mod
from bridgeforge.live_accept import accept_run
from bridgeforge.live_trust import shipped_hash, write_run_record
from bridgeforge.release import record_policy_decision
from bridgeforge.removals import add_removals, make_entry
from bridgeforge.revise import ReviseError, StepFailed, finalize, prepare
from tests.bound_runs import BASIC_LOG, bound_run
from tests.support import resolved_temp_dir

REPO_POLICY = Path(__file__).resolve().parent.parent / "bridgeforge" / "release_policy.json"
MOD_ID = "bf_fixture_radar"
REASON = "Fixed the radar ring spawn.\nSecond line is not for the changelog."


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _mod(base: Path, version: str, hulls: tuple[str, ...] = ("radar_hull",)) -> None:
    _write(base / "mod_info.json", json.dumps({"id": MOD_ID, "name": "Radar", "version": version, "gameVersion": "0.98a-RC8"}, indent=2))
    for hull in hulls:
        _write(base / "data" / "hulls" / f"{hull}.ship", json.dumps({"hullId": hull}))
    _write(base / "jars" / "radar.jar", "PK-fixture")


class Fixture:
    def __init__(self, root: Path, version: str = "3.0", archived: bool = False) -> None:
        self.root = root
        self.ws = root / "In operation" / "Radar"
        _mod(self.ws / "working", version)
        _mod(self.ws / "original" / "Radar", version)
        _write(self.ws / "working" / "reports" / "REVIVAL_REPORT.md", "# Report\n\nREADY_FOR_LIVE_TEST\n")
        self.done = root / "Done"
        self.policy = root / "policy.json"
        shutil.copy2(REPO_POLICY, self.policy)
        record_policy_decision(MOD_ID, local_only=True, reason="fixture", policy_path=self.policy)
        self.changelog = root / "CL.md"
        if archived:
            archive_mod(self.ws, self.done, policy_path=self.policy, today="2026-10-01")

    def prepare(self, **kwargs):
        return prepare(self.ws, REASON, done_dir=self.done, today="2026-10-18", **kwargs)

    def test_and_accept(self, test_id: str = "T-R1", record: bool = True) -> None:
        rig, log = bound_run(self.root, {MOD_ID: self.ws}, test_id, BASIC_LOG) if not (self.root / "rig").exists() else \
            bound_run(self.root, {MOD_ID: self.ws}, test_id, BASIC_LOG, rig=self.root / "rig")
        if record:
            accept_run(self.ws, log, test_id=test_id, note="played", rig=rig, today="2026-10-18")

    def finalize(self, revision: str, test_id: str = "T-R1"):
        return finalize(self.ws, revision, test_id, done_dir=self.done, policy_path=self.policy, changelog=self.changelog)

    def version(self) -> str:
        return json.loads((self.ws / "working" / "mod_info.json").read_text(encoding="utf-8"))["version"]


class PrepareTests(unittest.TestCase):
    def test_version_bump_rules_and_one_bump_only(self) -> None:
        with resolved_temp_dir() as root:
            plain = Fixture(root / "a", "1.0")
            suffixed = Fixture(root / "b", "1.0+bf.3")
            first = plain.prepare()
            again = plain.prepare()
            second = suffixed.prepare()
            versions = (plain.version(), suffixed.version())
        self.assertEqual((first["new_version"], second["new_version"]), ("1.0+bf.1", "1.0+bf.4"))
        self.assertEqual(versions, ("1.0+bf.1", "1.0+bf.4"))
        self.assertTrue(again["reused"])
        self.assertEqual(first["revision_id"], again["revision_id"])
        self.assertEqual(first["state"], "PREPARED")
        self.assertEqual(first["publication"][:14], "not authorized")

    def test_the_previous_archive_is_recorded_and_the_same_version_is_refused(self) -> None:
        with resolved_temp_dir() as root:
            fx = Fixture(root, "3.0", archived=True)
            journal = fx.prepare()
            kept = Fixture(root / "k", "3.0", archived=True)
            with self.assertRaisesRegex(ReviseError, "already archived"):
                kept.prepare(keep_version=True)
        self.assertEqual(journal["previous"]["version"], "3.0")
        self.assertEqual(len(journal["previous"]["shipped_sha256"]), 64)

    def test_a_changed_candidate_needs_an_explicit_refresh_which_keeps_the_version(self) -> None:
        with resolved_temp_dir() as root:
            fx = Fixture(root)
            first = fx.prepare()
            _write(fx.ws / "working" / "data" / "hulls" / "extra.ship", json.dumps({"hullId": "extra"}))
            with self.assertRaisesRegex(ReviseError, "refresh-candidate"):
                fx.prepare()
            refreshed = fx.prepare(refresh_candidate=True)
            version = fx.version()
        self.assertEqual(refreshed["new_version"], first["new_version"])
        self.assertEqual(version, first["new_version"])
        self.assertNotEqual(refreshed["candidate"]["shipped_sha256"], first["candidate"]["shipped_sha256"])
        self.assertEqual(len(refreshed["superseded"]), 1)

    def test_concurrent_prepare_is_refused_by_the_workspace_lock(self) -> None:
        with resolved_temp_dir() as root:
            fx = Fixture(root)
            _write(revise.revisions_dir(fx.ws) / revise.LOCK_NAME, "pid 1")
            with self.assertRaisesRegex(ReviseError, "another revise operation"):
                fx.prepare()
            self.assertEqual(fx.version(), "3.0")


class FinalizeTests(unittest.TestCase):
    def test_finalize_archives_exactly_the_tested_bytes_keeps_the_old_archive_and_is_idempotent(self) -> None:
        with resolved_temp_dir() as root:
            fx = Fixture(root, "3.0", archived=True)
            journal = fx.prepare()
            tested = journal["candidate"]["shipped_sha256"]
            fx.test_and_accept()
            result = fx.finalize(journal["revision_id"])
            again = fx.finalize(journal["revision_id"])
            archived = shipped_hash(fx.done / "Radar" / "Radar")
            replaced = sorted(p.name for p in (fx.done / "_replaced-2026-10-18").iterdir()) if (fx.done / "_replaced-2026-10-18").is_dir() else []
            old_note_kept = list(fx.done.glob("_replaced-*/Radar/ARCHIVE_NOTE.md"))
            changelog_lines = (fx.changelog.read_text(encoding="utf-8")).count("Fixed the radar ring spawn.")
            version_after = fx.version()
            top_zip = sorted(p.name for p in fx.done.glob("*.zip"))
        self.assertEqual(result["state"], "COMPLETE")
        self.assertTrue(again["already_complete"])
        self.assertEqual(archived, tested)
        self.assertEqual(version_after, "3.0+bf.1")
        self.assertEqual(changelog_lines, 1)
        self.assertTrue(replaced and old_note_kept)
        self.assertTrue(any("3.0+bf.1" in name for name in top_zip), top_zip)
        self.assertIn("not configured", result["steps"]["snapshot"])

    def test_the_journal_label_is_not_trusted_without_a_bound_run(self) -> None:
        with resolved_temp_dir() as root:
            fx = Fixture(root)
            journal = fx.prepare()
            path = revise._journal_path(fx.ws, journal["revision_id"])
            edited = json.loads(path.read_text(encoding="utf-8"))
            edited["state"] = "LIVE_ACCEPTED"
            edited["live"] = {"test_id": "T-FAKE"}
            path.write_text(json.dumps(edited), encoding="utf-8")
            with self.assertRaisesRegex(ReviseError, "no run T-FAKE|no readable run log"):
                fx.finalize(journal["revision_id"], "T-FAKE")
            self.assertFalse((fx.done / "Radar").exists())

    def test_runs_that_do_not_qualify_are_refused(self) -> None:
        with resolved_temp_dir() as root:
            fx = Fixture(root)
            journal = fx.prepare()
            rev = journal["revision_id"]
            # a legacy-style record: PASS recorded without a manifest -> provenance UNKNOWN
            write_run_record(fx.ws.parent, "T-LEGACY", [fx.ws], triage={"counts": {}}, verdicts={MOD_ID: "PASS"}, today="2026-10-18")
            with self.assertRaisesRegex(ReviseError, "not bound to staged inputs"):
                fx.finalize(rev, "T-LEGACY")
            with self.assertRaisesRegex(ReviseError, "no run T-NONE"):
                fx.finalize(rev, "T-NONE")
            fx.test_and_accept("T-R2")
            _write(fx.ws / "working" / "data" / "hulls" / "late.ship", json.dumps({"hullId": "late"}))  # edit after testing
            with self.assertRaisesRegex(ReviseError, "changed after the candidate was prepared"):
                fx.finalize(rev, "T-R2")
            self.assertFalse((fx.done / "Radar").exists())

    def test_a_run_of_another_version_is_refused(self) -> None:
        with resolved_temp_dir() as root:
            fx = Fixture(root)
            rig, log = bound_run(root, {MOD_ID: fx.ws}, "T-OLD", BASIC_LOG)  # tested before prepare: version 3.0
            accept_run(fx.ws, log, test_id="T-OLD", note="played", rig=rig, today="2026-10-17")
            journal = fx.prepare()
            with self.assertRaisesRegex(ReviseError, "tested version 3.0|other bytes"):
                fx.finalize(journal["revision_id"], "T-OLD")

    def test_dropped_ids_need_migration_evidence_before_anything_is_archived(self) -> None:
        with resolved_temp_dir() as root:
            fx = Fixture(root, "3.0", archived=True)
            (fx.ws / "working" / "data" / "hulls" / "radar_hull.ship").unlink()
            _write(fx.ws / "working" / "data" / "hulls" / "radar_new.ship", json.dumps({"hullId": "radar_new"}))
            journal = fx.prepare()
            self.assertTrue(journal["migration"]["required"])
            fx.test_and_accept()
            with self.assertRaisesRegex(ReviseError, "migration pack or a written reason"):
                fx.finalize(journal["revision_id"])
            from bridgeforge.live_trust import explain_shipped
            from bridgeforge.revision_renames import migration_requirement, write_evidence

            explain_shipped(fx.ws, ["data/hulls/radar_hull.ship", "data/hulls/radar_new.ship"], "the hull was renamed by the revision")
            add_removals(fx.ws / "working", [make_entry("files", pattern="data/hulls/radar_hull.ship", reason="the hull was renamed by the revision", source="owner")])
            previous = Path(journal["previous"]["root"])
            write_evidence(fx.ws, migration_requirement(fx.ws, previous, fx.ws / "working"),
                           reason="radar_hull was renamed radar_new; no campaign script spawns it, so saves never hold it")
            result = fx.finalize(journal["revision_id"])
        self.assertEqual(result["state"], "COMPLETE")
        self.assertEqual(result["migration"]["how"], "reason")

    def test_a_missing_local_archive_authorization_is_refused(self) -> None:
        with resolved_temp_dir() as root:
            fx = Fixture(root)
            journal = fx.prepare()
            fx.test_and_accept()
            path = revise._journal_path(fx.ws, journal["revision_id"])
            edited = json.loads(path.read_text(encoding="utf-8"))
            edited["scope"] = []
            path.write_text(json.dumps(edited), encoding="utf-8")
            with self.assertRaisesRegex(ReviseError, "scope"):
                fx.finalize(journal["revision_id"])


class RecoveryTests(unittest.TestCase):
    def _ready(self, root: Path):
        fx = Fixture(root, "3.0", archived=True)
        journal = fx.prepare()
        fx.test_and_accept()
        return fx, journal["revision_id"]

    def test_a_failed_changelog_step_resumes_without_a_second_archive_or_line(self) -> None:
        import bridgeforge.mod_changelog as changelog

        with resolved_temp_dir() as root:
            fx, rev = self._ready(root)
            real = changelog.add_entry
            calls = {"n": 0}

            def flaky(mod, text, **kwargs):
                if Path(kwargs.get("path") or "") == fx.changelog and calls["n"] == 0:
                    calls["n"] += 1
                    raise OSError("disk full")
                return real(mod, text, **kwargs)

            with mock.patch.object(changelog, "add_entry", flaky):
                with self.assertRaises(StepFailed):
                    fx.finalize(rev)
                failed = revise.read_journal(fx.ws, rev)
                result = fx.finalize(rev)
            lines = fx.changelog.read_text(encoding="utf-8").count("Fixed the radar ring spawn.")
        self.assertEqual((failed["state"], failed["failed_step"]["step"]), ("LIVE_ACCEPTED", "changelog"))
        self.assertEqual((result["state"], result["failed_step"]), ("COMPLETE", None))
        self.assertEqual(lines, 1)

    def test_a_failed_archive_leaves_the_old_archive_and_a_retry_completes(self) -> None:
        import bridgeforge.archive as archive

        with resolved_temp_dir() as root:
            fx, rev = self._ready(root)
            old_zip_exists = list((fx.done / "Radar").glob("*.zip"))
            with mock.patch.object(archive, "archive_mod", side_effect=OSError("zip failed")):
                with self.assertRaises(StepFailed):
                    fx.finalize(rev)
            failed = revise.read_journal(fx.ws, rev)
            still_there = (fx.done / "Radar" / "ARCHIVE_NOTE.md").is_file()
            result = fx.finalize(rev)
        self.assertTrue(old_zip_exists and still_there)
        self.assertEqual((failed["state"], failed["failed_step"]["step"]), ("LIVE_ACCEPTED", "archive"))
        self.assertEqual(result["state"], "COMPLETE")

    def test_a_failed_snapshot_after_archiving_reports_that_exact_state_and_resumes_only_the_snapshot(self) -> None:
        import bridgeforge.archive as archive
        import bridgeforge.state_snapshot as snapshot

        with resolved_temp_dir() as root:
            fx, rev = self._ready(root)
            real_archive = archive.archive_mod
            archived_calls = []

            def counting(*args, **kwargs):
                archived_calls.append(1)
                return real_archive(*args, **kwargs)

            with mock.patch.object(archive, "archive_mod", counting), \
                    mock.patch.object(snapshot, "snapshot_after_archive", return_value="snapshot after archive FAILED: disk offline"):
                with self.assertRaises(StepFailed) as ctx:
                    fx.finalize(rev)
                partial = revise.read_journal(fx.ws, rev)
            with mock.patch.object(archive, "archive_mod", counting), \
                    mock.patch.object(snapshot, "snapshot_after_archive", return_value="snapshot X: 3 copied"):
                result = fx.finalize(rev)
        self.assertIn("after ARCHIVED", str(ctx.exception))
        self.assertEqual((partial["state"], partial["failed_step"]["step"]), ("ARCHIVED", "snapshot"))
        self.assertEqual(result["state"], "COMPLETE")
        self.assertEqual(result["steps"]["snapshot"], "snapshot X: 3 copied")
        self.assertEqual(len(archived_calls), 1)

    def test_an_archive_written_before_the_journal_was_updated_is_adopted_not_redone(self) -> None:
        import bridgeforge.archive as archive

        with resolved_temp_dir() as root:
            fx, rev = self._ready(root)
            fx.finalize(rev)
            path = revise._journal_path(fx.ws, rev)
            crashed = json.loads(path.read_text(encoding="utf-8"))
            crashed.update(state="LIVE_ACCEPTED", steps={"changelog": crashed["steps"]["changelog"]})
            path.write_text(json.dumps(crashed), encoding="utf-8")
            with mock.patch.object(archive, "archive_mod", side_effect=AssertionError("archived twice")):
                result = fx.finalize(rev)
        self.assertEqual(result["state"], "COMPLETE")
        self.assertTrue(result["steps"]["archive"]["reconciled"])


if __name__ == "__main__":
    unittest.main()
