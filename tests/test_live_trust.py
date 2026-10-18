"""Live-test trust (ROADMAP item 36): shipped-copy audit, run records, stale results, noise budget, archive gate."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from bridgeforge.live_trust import (archive_gate, audit_shipped, auto_explain_shipped, explain_shipped, live_status, original_root,
                                    write_run_record)
from tests.support import resolved_temp_dir


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _workspace(root: Path, name: str = "Mod") -> Path:
    ws = root / name
    for base in (ws / "original" / "Mod v1", ws / "working"):
        _write(base / "mod_info.json", '{"id": "m", "version": "1"}')
        _write(base / "data" / "hulls" / "ship_data.csv", "id\nm_hull\n")
        _write(base / "data" / "config" / "settings.json", "{}")
    return ws


def _evidence(ws: Path) -> dict:
    """What run_manifest.evaluate_run returns for a clean run of the fixture's mod `m` (the evaluator itself is tested in test_run_manifest)."""
    from bridgeforge.live_trust import shipped_hash

    digest = shipped_hash(ws / "working")
    return {"status": "ACCEPTABLE", "run_id": "T", "manifest_id": "abc", "problems": [],
            "members": {"m": {"ok": True, "verdict": "PASS", "candidate_sha256": digest, "workspace_sha256_now": digest, "problems": []}}}


class ShippedAuditTests(unittest.TestCase):
    def test_identical_and_declared_changes_pass(self) -> None:
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            _write(ws / "working" / "mod_info.json", '{"id": "m", "version": "1+bf.1"}')  # declared generated
            result = audit_shipped(ws)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual([r["file"] for r in result["differences"]], ["mod_info.json"])

    def test_unexplained_edit_and_removal_fail_until_explained(self) -> None:
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            _write(ws / "working" / "data" / "hulls" / "ship_data.csv", "id\nm_hull\nstray\n")
            (ws / "working" / "data" / "config" / "settings.json").unlink()
            before = audit_shipped(ws)
            # "\r" as left by a list read from a CRLF file (SEEKER 2026-10-05)
            explain_shipped(ws, ["data/hulls/ship_data.csv\r", "data/config/settings.json"], "hand fix 2026-10-04")
            after = audit_shipped(ws)
        self.assertEqual(before["status"], "FAIL")
        self.assertEqual(sorted(before["unexplained"]), ["data/config/settings.json", "data/hulls/ship_data.csv"])
        self.assertEqual(after["status"], "PASS")

    def test_fixer_backup_jar_patch_and_revive_records_explain(self) -> None:
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            _write(ws / "working" / "data" / "hulls" / "ship_data.csv", "id\nm_hull2\n")
            _write(ws / "working" / "data" / "hulls" / "ship_data.csv.pre-bf-fix-csv-row-extra-columns.bak", "id\nm_hull\n")
            _write(ws / "working" / "jars" / "m.jar", "patched")
            _write(ws / "original" / "Mod v1" / "jars" / "m.jar", "old")
            _write(ws / "scratch" / "jar-patch-2026-10-04" / "PATCH-m.json", json.dumps({"jar": "jars/m.jar"}))
            _write(ws / "working" / "data" / "new.csv", "id\n")
            _write(ws / "reports" / "revive" / "REVIVE.json", json.dumps({"applied": [{"finding": "x", "files": ["data/new.csv"]}]}))
            result = audit_shipped(ws)
        self.assertEqual(result["status"], "PASS", result["unexplained"])
        why = {r["file"]: r["explained_by"] for r in result["differences"]}
        self.assertTrue(why["data/hulls/ship_data.csv"].startswith("fixer csv-row-extra-columns"))
        self.assertTrue(why["jars/m.jar"].startswith("patch-jar-class"))

    def test_no_original_is_unknown_never_pass(self) -> None:
        with resolved_temp_dir() as root:
            ws = root / "Mod"
            _write(ws / "working" / "mod_info.json", "{}")
            self.assertEqual(audit_shipped(ws)["status"], "UNKNOWN")


class RunRecordTests(unittest.TestCase):
    def test_record_marks_current_then_stale_after_a_change(self) -> None:
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            untested = live_status(ws)["status"]
            write_run_record(root, "T1", [ws], triage={"counts": {"FATAL": 0, "KNOWN-NOISE": 10}}, verdicts={"m": "PASS"}, today="2026-10-04",
                             evidence=_evidence(ws))
            current = live_status(ws)
            _write(ws / "working" / "data" / "hulls" / "ship_data.csv", "id\nm_hull\nfix\n")
            stale = live_status(ws)
        self.assertEqual((untested, current["status"], stale["status"], stale["test_id"]), ("NOT_TESTED", "CURRENT", "STALE", "T1"))
        self.assertEqual(current["provenance"], "BOUND")

    def test_a_record_without_bound_evidence_is_never_current(self) -> None:
        # R1: a new record with no manifest evidence says provenance UNKNOWN; refused evidence does not bind either.
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            write_run_record(root, "T1", [ws], triage={"counts": {}}, verdicts={"m": "PASS"}, today="2026-10-04")
            unbound = live_status(ws)
            refused = _evidence(ws)
            refused["status"] = "REFUSED"
            write_run_record(root, "T2", [ws], triage={"counts": {}}, verdicts={"m": "PASS"}, today="2026-10-05", evidence=refused)
            still = live_status(ws)
            wrong_bytes = _evidence(ws)
            wrong_bytes["members"]["m"]["candidate_sha256"] = "0" * 64
            write_run_record(root, "T3", [ws], triage={"counts": {}}, verdicts={"m": "PASS"}, today="2026-10-06", evidence=wrong_bytes)
            different = live_status(ws)
            gate = archive_gate(ws)
        self.assertEqual((unbound["status"], unbound["provenance"]), ("UNBOUND", "UNKNOWN"))
        self.assertEqual(still["status"], "UNBOUND")
        self.assertEqual(different["status"], "UNBOUND")
        self.assertIn("live result UNBOUND", " ".join(gate["problems"]))

    def test_a_legacy_run_line_stays_readable_with_provenance_unknown(self) -> None:
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            from bridgeforge.live_trust import shipped_hash

            _write(ws / "reports" / "live_runs.jsonl", json.dumps({"test_id": "OLD", "date": "2026-10-04", "verdict": "PASS",
                                                                   "shipped_sha256": shipped_hash(ws / "working"), "version": "1"}) + "\n")
            status = live_status(ws)
        self.assertEqual((status["status"], status["provenance"]), ("CURRENT", "UNKNOWN"))

    def test_validated_before_run_records_is_unknown_build(self) -> None:
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            _write(ws / "working" / "reports" / "REVIVAL_REPORT.md", "# R\n\nLIVE_VALIDATED\n")
            self.assertEqual(live_status(ws)["status"], "UNKNOWN_BUILD")

    def test_known_noise_jump_between_runs_of_the_same_members_is_review(self) -> None:
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            first = write_run_record(root, "T1", [ws], triage={"counts": {"KNOWN-NOISE": 10}}, verdicts={})
            calm = write_run_record(root, "T2", [ws], triage={"counts": {"KNOWN-NOISE": 14}}, verdicts={})
            jump = write_run_record(root, "T3", [ws], triage={"counts": {"KNOWN-NOISE": 60}}, verdicts={})
        self.assertEqual(first["known_noise"]["status"], "NO_PREVIOUS")
        self.assertEqual(calm["known_noise"]["status"], "OK")
        self.assertEqual((jump["known_noise"]["status"], jump["known_noise"]["previous_run"]), ("REVIEW", "T2"))


class ArchiveGateTests(unittest.TestCase):
    def test_gate_needs_audit_and_current_live_result_or_a_recorded_waiver(self) -> None:
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            untested = archive_gate(ws)
            explain_shipped(ws, [], "validated live 2026-09-28 before run records existed", live=True)
            waived = archive_gate(ws)
            with self.assertRaises(ValueError):
                explain_shipped(ws, [], "x")
        self.assertFalse(untested["allowed"])
        self.assertIn("live result NOT_TESTED", untested["problems"][0])
        self.assertTrue(waived["allowed"])


if __name__ == "__main__":
    unittest.main()


DESCRIPTOR = """<?xml version="1.0" ?>
<SaveGameData z="1">
<gameVersion>0.98a-RC8</gameVersion>
<allModsEverEnabled z="4">
<EnabledModData z="5"><spec z="6"><id>lib</id><versionInfo z="7"><major>1</major><minor>5</minor><patch>6</patch></versionInfo></spec></EnabledModData>
<EnabledModData z="8"><spec z="9"><id>gone</id><versionInfo z="10"><string>0.1</string></versionInfo></spec></EnabledModData>
</allModsEverEnabled>
<enabledMods z="11">
<EnabledModData z="12"><spec ref="6"/></EnabledModData>
<EnabledModData z="13"><spec z="14"><id>mod_a</id><versionInfo z="15"><string>2.0+bf.1</string></versionInfo></spec></EnabledModData>
</enabledMods>
</SaveGameData>
"""


class SaveMadeWithTests(unittest.TestCase):
    # ROADMAP 36.5 (2026-10-04): a save baseline names the mods it was made with.
    def test_reads_enabled_mods_through_refs_and_numeric_versions(self) -> None:
        from bridgeforge.live_trust import save_made_with

        with resolved_temp_dir() as root:
            _write(root / "save_x" / "descriptor.xml", DESCRIPTOR)
            made = save_made_with(root / "save_x")
            none = save_made_with(root / "missing")
        self.assertEqual(made, {"game_version": "0.98a-RC8", "mods": {"lib": "1.5.6", "mod_a": "2.0+bf.1"}})
        self.assertIsNone(none)

    def test_comparison_is_never_a_pass_by_default(self) -> None:
        from bridgeforge.live_trust import compare_made_with

        made = {"game_version": "0.98a-RC8", "mods": {"lib": "1.5.6", "mod_a": "2.0"}}
        self.assertEqual(compare_made_with(made, made)["status"], "COMPARABLE")
        self.assertEqual(compare_made_with(made, {**made, "mods": {"lib": "1.5.6", "mod_a": "2.1"}})["status"], "REVIEW")
        self.assertEqual(compare_made_with(made, {**made, "mods": {"lib": "1.5.6"}})["status"], "UNKNOWN")
        self.assertEqual(compare_made_with(None, made)["status"], "UNKNOWN")


class OriginalRootTests(unittest.TestCase):
    def test_original_extracted_folder_is_found(self) -> None:
        # yunruindustries keeps original/archive/<zip> and original/extracted/<Mod Name>/ (2026-10-05)
        with resolved_temp_dir() as root:
            mod = root / "ws" / "original" / "extracted" / "Yunru Industries"
            mod.mkdir(parents=True)
            (mod / "mod_info.json").write_text("{}", encoding="utf-8")
            (root / "ws" / "original" / "archive").mkdir()
            self.assertEqual(original_root(root / "ws"), mod)

    def test_a_pack_download_resolves_to_the_root_with_the_working_copys_id(self) -> None:
        # yunruhullmods and yunruworlds were extracted from the one Yunru Core pack (GRP1B-20261006)
        with resolved_temp_dir() as root:
            ws = root / "ws"
            for folder, mod_id in (("Pack - Core", "yunrucore"), ("Pack - Hullmods", "yunruhullmods"), ("Pack - Worlds", "yunruworlds")):
                (ws / "original" / "extracted" / folder).mkdir(parents=True)
                (ws / "original" / "extracted" / folder / "mod_info.json").write_text('{"id":"%s"}' % mod_id, encoding="utf-8")
            (ws / "working").mkdir()
            (ws / "working" / "mod_info.json").write_text('{"id":"yunruhullmods"}', encoding="utf-8")
            self.assertEqual(original_root(ws), ws / "original" / "extracted" / "Pack - Hullmods")
            (ws / "working" / "mod_info.json").write_text('{"id":"somethingelse"}', encoding="utf-8")
            self.assertIsNone(original_root(ws))


class AutoExplainTests(unittest.TestCase):
    def test_provable_categories_are_explained_and_a_real_edit_is_not(self) -> None:
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            original, working = ws / "original" / "Mod v1", ws / "working"
            # syntax-only JSON: a trailing comma
            _write(original / "data" / "config" / "a.json", '{"x": [1, 2]}')
            _write(working / "data" / "config" / "a.json", '{"x": [1, 2],}')
            # a real value change
            _write(original / "data" / "config" / "b.json", '{"x": 1}')
            _write(working / "data" / "config" / "b.json", '{"x": 2}')
            # credits file, manufacturer column, unloaded archive, translation
            _write(working / "BRIDGEFORGE_CREDITS.txt", "credits")
            _write(original / "data" / "weapons" / "weapon_data.csv", "id,name\nw1,Gun\nw2,\n")
            _write(working / "data" / "weapons" / "weapon_data.csv", "id,name,tech/manufacturer\nw1,Gun,Infected\nw2,,Infected\n")
            _write(original / "data" / "strings" / "d.csv", "id,text\nx,我是中文\n")
            _write(working / "data" / "strings" / "d.csv", "id,text\nx,I am English\n")
            _write(ws / "reports" / "translation" / "m-en.json", "{}")
            (original / "Extra Ships.rar").write_bytes(b"Rar!")
            _write(ws / "scratch" / "moved-work-files" / "Extra Ships.rar", "Rar!")
            groups = auto_explain_shipped(ws)
            after = audit_shipped(ws)
        explained = sorted(f for files in groups.values() for f in files)
        self.assertEqual(explained, ["BRIDGEFORGE_CREDITS.txt", "Extra Ships.rar", "data/config/a.json", "data/strings/d.csv", "data/weapons/weapon_data.csv"])
        self.assertEqual(after["unexplained"], ["data/config/b.json"])

    def test_a_csv_with_a_changed_value_is_not_called_a_column_addition(self) -> None:
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            _write(ws / "original" / "Mod v1" / "data" / "weapons" / "weapon_data.csv", "id,name\nw1,Gun\n")
            _write(ws / "working" / "data" / "weapons" / "weapon_data.csv", "id,name,tech/manufacturer\nw1,Cannon,Infected\n")
            groups = auto_explain_shipped(ws)
        self.assertEqual(groups, {})


class AutoExplainWorkFileAndRowsTests(unittest.TestCase):
    def test_moved_work_file_and_added_rows_are_explained_but_a_changed_copy_is_not(self) -> None:
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            original, working = ws / "original" / "Mod v1", ws / "working"
            _write(original / "data" / "hulls" / "a.ship.old", "backup")
            _write(ws / "scratch" / "work-files" / "data" / "hulls" / "a.ship.old", "backup")
            _write(original / "data" / "hulls" / "b.ship.old", "backup")
            _write(ws / "scratch" / "work-files" / "data" / "hulls" / "b.ship.old", "edited later")
            _write(original / "data" / "strings" / "descriptions.csv", "id,type,text1\nx,SHIP,One\n")
            _write(working / "data" / "strings" / "descriptions.csv", "id,type,text1\nx,SHIP,One\ny,SHIP_SYSTEM,Two\n")
            _write(original / "data" / "strings" / "changed.csv", "id,type,text1\nx,SHIP,One\n")
            _write(working / "data" / "strings" / "changed.csv", "id,type,text1\nx,SHIP,Edited\ny,SHIP_SYSTEM,Two\n")
            groups = auto_explain_shipped(ws)
            after = audit_shipped(ws)
        explained = sorted(f for files in groups.values() for f in files)
        self.assertEqual(explained, ["data/hulls/a.ship.old", "data/strings/descriptions.csv"])
        self.assertEqual(sorted(after["unexplained"]), ["data/hulls/b.ship.old", "data/strings/changed.csv"])


class ExplainNeedsAWorkspaceTests(unittest.TestCase):
    def test_a_name_that_is_not_a_workspace_is_refused_and_nothing_is_written(self) -> None:
        with resolved_temp_dir() as root:
            stray = root / "Silent-Armada"
            with self.assertRaises(ValueError) as caught:
                explain_shipped(stray, ["a.txt"], "a reason")
            self.assertFalse(stray.exists())
        self.assertIn("not a workspace", str(caught.exception))
