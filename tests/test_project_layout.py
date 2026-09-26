import contextlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import zipfile

from bridgeforge.archive_intake import inspect_zip_archive, _tree_sha256
from bridgeforge.cli import main
from bridgeforge.intake import intake_archive
from bridgeforge.project_board import layout_findings, project_board, render_board, write_board
from bridgeforge.rig_doctor import _check_layout
from tests.support import resolved_temp_dir


def _archive(root, *, members=None):
    path = root / "download.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("wrapper/mod_info.json", json.dumps({"id": "fixture", "name": "Fixture", "version": "1", "gameVersion": "0.98a"}))
        archive.writestr("wrapper/data/preserved.bin", b"\0\xff\xfeupstream")
        archive.writestr("wrapper/empty/", b"")
        archive.writestr("outside.txt", "keep only in original")
        for name, data in members or []:
            archive.writestr(name, data)
    return path


def _mod(root, area="In operation", folder="Fixture", release="working"):
    base = root / area / folder
    working = base / release
    working.mkdir(parents=True)
    (working / "mod_info.json").write_text(json.dumps({"id": "fixture", "name": "Fixture [BF r2]", "version": "1+bf.2"}), encoding="utf-8")
    (base / "reports").mkdir(exist_ok=True)
    return base, working


class IntakeTests(unittest.TestCase):
    def test_preserves_archive_and_selected_bytes_generates_relocated_evidence(self):
        with resolved_temp_dir() as root:
            archive = _archive(root)
            before = archive.read_bytes()
            result = intake_archive(archive, root, archaeology=True)
            destination = Path(result["destination"])
            self.assertEqual(archive.read_bytes(), before)
            self.assertEqual((destination / "original/archive/download.zip").read_bytes(), before)
            self.assertTrue((destination / "original/extracted/outside.txt").is_file())
            self.assertFalse((destination / "working/outside.txt").exists())
            self.assertTrue((destination / "working/empty").is_dir())
            self.assertEqual(_tree_sha256(destination / "original/extracted/wrapper"), _tree_sha256(destination / "working"))
            self.assertEqual(result["status"], "ASSESSMENT_REQUIRED")
            self.assertTrue((destination / "intake-complete.json").is_file())
            self.assertFalse((destination / "reports/REVIVAL_PLAN.md").exists())
            for path in (destination / "reports").rglob("*"):
                if path.is_file() and path.suffix in {".json", ".md"}:
                    self.assertNotIn("_intake-", path.read_text(encoding="utf-8"))
            scan = json.loads((destination / "reports/scan/bridgeforge.compat.json").read_text(encoding="utf-8"))
            self.assertIn(str(destination), json.dumps(scan).replace("\\\\", "\\"))
            self.assertEqual(project_board(root)["mods"][0]["stage"], "ASSESSMENT_REQUIRED")
            self.assertEqual(layout_findings(root), [])

    def test_existing_empty_casefold_folder_is_never_replaced(self):
        with resolved_temp_dir() as root:
            archive = _archive(root)
            existing = root / "In operation/FIXTURE"
            existing.mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, "already exists"):
                intake_archive(archive, root)
            self.assertEqual(list(existing.iterdir()), [])
            self.assertEqual(list(existing.parent.iterdir()), [existing])

    def test_analysis_failure_does_not_publish_or_change_input(self):
        with resolved_temp_dir() as root:
            archive = _archive(root)
            before = archive.read_bytes()
            with patch("bridgeforge.intake.build_dossier", side_effect=ValueError("forced analysis failure")):
                with self.assertRaisesRegex(ValueError, "forced"):
                    intake_archive(archive, root)
            self.assertEqual(list((root / "In operation").iterdir()), [])
            self.assertEqual(archive.read_bytes(), before)

    def test_ambiguous_root_needs_selection(self):
        with resolved_temp_dir() as root:
            archive = _archive(root, members=[("other/mod_info.json", '{"id":"other"}')])
            with self.assertRaisesRegex(ValueError, "one mod root"):
                intake_archive(archive, root)
            result = intake_archive(archive, root, selected_root="other", name="Other")
            self.assertEqual(result["mod_id"], "other")
            self.assertFalse((Path(result["working"]) / "data").exists())

    def test_invalid_name_and_metadata_are_not_published(self):
        with resolved_temp_dir() as root:
            archive = _archive(root)
            for name in ("../escape", "_rig", "CON", "trailing.", "space ", "C:stream"):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    intake_archive(archive, root, name=name)
            bad = root / "bad.zip"
            with zipfile.ZipFile(bad, "w") as zipped:
                zipped.writestr("mod_info.json", '{"name":"no id"}')
            with self.assertRaisesRegex(ValueError, "metadata"):
                intake_archive(bad, root)
            self.assertEqual(list((root / "In operation").iterdir()), [])

    def test_portable_hazards_and_file_ancestor_collisions_are_blocked(self):
        with resolved_temp_dir() as root:
            for member in ("../escape", "wrapper/CON.txt", "wrapper/a:stream", "wrapper/trailing.", "wrapper/file?.txt", "wrapper/Data/PRESERVED.bin"):
                with self.subTest(member=member):
                    archive = _archive(root, members=[(member, "hazard")])
                    self.assertFalse(inspect_zip_archive(archive)["safe_to_stage"])
                    with self.assertRaises(ValueError):
                        intake_archive(archive, root)
            archive = _archive(root, members=[("wrapper/block", "file"), ("wrapper/block/child", "collision")])
            report = inspect_zip_archive(archive)
            self.assertIn("archive-path-collision", [item["id"] for item in report["findings"]])
            self.assertFalse((root / "In operation").exists())

    def test_publish_failure_rolls_back_new_folder(self):
        with resolved_temp_dir() as root:
            archive = _archive(root)
            rename = Path.rename

            def fail_working(path, target):
                if path.name == "working" and Path(target).parent.name == "fixture":
                    raise OSError("forced publish failure")
                return rename(path, target)

            with patch.object(Path, "rename", fail_working):
                with self.assertRaisesRegex(OSError, "publish"):
                    intake_archive(archive, root)
            self.assertEqual(list((root / "In operation").iterdir()), [])

    def test_analysis_mutation_of_working_or_original_is_rejected(self):
        from bridgeforge.dossier import build_dossier
        with resolved_temp_dir() as root:
            archive = _archive(root)
            for target in ("working", "original"):
                def mutating_builder(working):
                    dossier = build_dossier(working)
                    path = working / "mod_info.json" if target == "working" else working.parent / "original/extracted/outside.txt"
                    path.write_text("unexpected mutation", encoding="utf-8")
                    return dossier
                with self.subTest(target=target), patch("bridgeforge.intake.build_dossier", side_effect=mutating_builder):
                    with self.assertRaisesRegex(ValueError, "changed preserved/working"):
                        intake_archive(archive, root)
                self.assertEqual(list((root / "In operation").iterdir()), [])

    def test_linked_operation_root_is_rejected(self):
        with resolved_temp_dir() as root:
            archive = _archive(root)
            with patch("bridgeforge.intake._is_link", return_value=True):
                with self.assertRaisesRegex(ValueError, "physical"):
                    intake_archive(archive, root)
            self.assertFalse((root / "In operation").exists())


class BoardTests(unittest.TestCase):
    def test_missing_evidence_is_unknown_and_write_preserves_manual_status(self):
        with resolved_temp_dir() as root:
            base, working = _mod(root)
            manual = root / "In operation/STATUS.md"
            manual.write_text("manual authority", encoding="utf-8")
            before = _tree_sha256(base)
            board = project_board(root)
            self.assertEqual(board, project_board(root))
            row = board["mods"][0]
            self.assertIsNone(row["open_risks"])
            self.assertIsNone(row["last_test"])
            self.assertEqual(row["build_tag"], "r2")
            self.assertEqual(row["stage"], "WORKING_COPY_PRESENT")
            write_board(board, root)
            self.assertEqual(manual.read_text(encoding="utf-8"), "manual authority")
            self.assertEqual(_tree_sha256(base), before)
            self.assertEqual(layout_findings(root), [])

    def test_declared_report_risks_and_last_test_are_traceable_not_verified(self):
        with resolved_temp_dir() as root:
            base, _ = _mod(root)
            reports = base / "reports"
            (reports / "REVIVAL_REPORT.md").write_text("# Report\n\nLIVE TEST NOT PERFORMED\n\nREADY_FOR_LIVE_TEST\n", encoding="utf-8")
            (reports / "risks.json").write_text(json.dumps({"risks": [{"status": "OPEN"}, {"status": "CLOSED"}]}), encoding="utf-8")
            (reports / "last-test.json").write_text(json.dumps({"test_id": "BOOT-1", "status": "PASS", "build": "r1"}), encoding="utf-8")
            row = project_board(root)["mods"][0]
            self.assertEqual(row["stage"], "REPORT_DECLARED_READY_FOR_LIVE_TEST")
            self.assertEqual(row["open_risks"], 1)
            self.assertIn("last test does not match current build tag", row["warnings"])
            self.assertEqual(row["evidence"]["risks"], str(reports / "risks.json"))

    def test_legacy_named_evidence_is_used_even_when_external_reports_folder_exists(self):
        with resolved_temp_dir() as root:
            _, working = _mod(root)
            reports = working / "reports"
            reports.mkdir()
            (reports / "REVIVAL_REPORT.md").write_text("READY_FOR_LIVE_TEST\n", encoding="utf-8")
            row = project_board(root)["mods"][0]
            self.assertEqual(row["declared_completion_status"], "READY_FOR_LIVE_TEST")
            self.assertEqual(row["evidence"]["report"], str(reports / "REVIVAL_REPORT.md"))

    def test_intake_marker_and_later_plan_are_not_silently_ignored(self):
        with resolved_temp_dir() as root:
            result = intake_archive(_archive(root), root)
            folder = Path(result["destination"])
            (folder / "reports/REVIVAL_PLAN.md").write_text("# Plan present, not verified approval\n", encoding="utf-8")
            self.assertEqual(project_board(root)["mods"][0]["stage"], "PLAN_PRESENT_NOT_APPROVAL_VERIFIED")
            (folder / "intake-complete.json").unlink()
            self.assertEqual(project_board(root)["mods"][0]["stage"], "INTAKE_INCOMPLETE")

    def test_malformed_or_conflicting_evidence_does_not_imply_ready(self):
        with resolved_temp_dir() as root:
            base, working = _mod(root)
            (base / "reports/REVIVAL_REPORT.md").write_text("READY\nREADY_FOR_LIVE_TEST\n", encoding="utf-8")
            (base / "reports/risks.json").write_text('{"risks":[{}]}', encoding="utf-8")
            (base / "reports/last-test.json").write_text('{"status":"PASS"}', encoding="utf-8")
            info = working / "mod_info.json"
            info.write_text('{"name":"Fixture [BF r2]","version":"1+bf.3"}', encoding="utf-8")
            row = project_board(root)["mods"][0]
            self.assertIsNone(row["declared_completion_status"])
            self.assertIsNone(row["open_risks"])
            self.assertIsNone(row["last_test"])
            self.assertIsNone(row["build_tag"])
            self.assertGreaterEqual(len(row["warnings"]), 4)

    def test_unreadable_report_and_missing_working_copy_never_imply_readiness(self):
        with resolved_temp_dir() as root:
            base, _ = _mod(root)
            report = base / "reports/REVIVAL_REPORT.md"
            report.write_bytes(b"\xff\xfeinvalid UTF-8")
            row = project_board(root)["mods"][0]
            self.assertIsNone(row["declared_completion_status"])
            self.assertTrue(any("unreadable" in item for item in row["warnings"]))
            legacy = root / "In operation/Legacy"
            (legacy / "reports").mkdir(parents=True)
            (legacy / "reports/REVIVAL_REPORT.md").write_text("READY\n", encoding="utf-8")
            row = next(item for item in project_board(root)["mods"] if item["folder"] == "Legacy")
            self.assertEqual(row["stage"], "LAYOUT_INCOMPLETE")

    def test_done_is_not_automatically_a_validated_release_and_original_is_not_active(self):
        with resolved_temp_dir() as root:
            base, working = _mod(root, "Done", release="Release-1")
            original = base / "original"
            original.mkdir()
            (original / "mod_info.json").write_text('{"id":"upstream"}', encoding="utf-8")
            row = project_board(root)["mods"][0]
            self.assertEqual(row["mod_id"], "fixture")
            self.assertEqual(row["stage"], "RELEASE_PRESENT_NOT_VERIFIED")
            self.assertEqual(row["release_folder"], "Release-1")

    def test_layout_warns_for_strays_and_nonconforming_paths_without_moving(self):
        with resolved_temp_dir() as root:
            base, working = _mod(root)
            stray = root / "In operation/old.zip"
            stray.write_bytes(b"keep")
            legacy = root / "In operation/Legacy"
            legacy.mkdir()
            (legacy / "mod_info.json").write_text('{"id":"legacy"}', encoding="utf-8")
            before = _tree_sha256(root)
            mapping = {"fixture": working, "legacy": legacy}
            findings = layout_findings(root, mapping)
            self.assertEqual({item["code"] for item in findings}, {"root-stray", "missing-working-copy", "nonconforming-working-copy"})
            self.assertEqual(_check_layout(root, mapping)["status"], "WARN")
            self.assertEqual(_tree_sha256(root), before)

    def test_finding_stats_and_automation_policy_are_known_queue_files(self):
        with resolved_temp_dir() as root:
            _base, working = _mod(root)
            for name in ("FINDING_STATS.json", "FINDING_STATS.md", "AUTOMATION_POLICY.json"):
                (root / "In operation" / name).write_text("{}", encoding="utf-8")
            findings = layout_findings(root, {"fixture": working})
        self.assertNotIn("root-stray", {item["code"] for item in findings})

    def test_markdown_rows_remain_contiguous_and_cells_escape_pipes(self):
        with resolved_temp_dir() as root:
            for folder in ("One", "Two"):
                base, _ = _mod(root, folder=folder)
                (base / "reports/risks.json").write_text("bad|json", encoding="utf-8")
            rendered = render_board(project_board(root))
            table = rendered.split("## Evidence warnings")[0]
            self.assertEqual(sum(line.startswith("| In operation") for line in table.splitlines()), 2)

    def test_cli_intake_board_and_errors(self):
        with resolved_temp_dir() as root:
            archive = _archive(root)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(["intake", str(archive), "--repo-root", str(root), "--json"]), 0)
            self.assertEqual(json.loads(output.getvalue())["status"], "ASSESSMENT_REQUIRED")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(["board", "--repo-root", str(root), "--write", "--json"]), 0)
            self.assertEqual(len(json.loads(output.getvalue())["mods"]), 1)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["intake", str(archive), "--repo-root", str(root)]), 2)

    def test_generated_output_link_is_not_overwritten(self):
        with resolved_temp_dir() as root:
            _mod(root)
            board = project_board(root)
            with patch("bridgeforge.project_board._is_link", side_effect=lambda path: path.name == "STATUS.generated.md"):
                with self.assertRaisesRegex(ValueError, "board output"):
                    write_board(board, root)
            self.assertFalse((root / "In operation/STATUS.generated.json").exists())


if __name__ == "__main__":
    unittest.main()
