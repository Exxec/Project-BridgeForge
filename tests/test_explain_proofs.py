"""ROADMAP 60b/60c/65: more `audit-explain --auto` proofs, the copy ledger, the sibling-pack asset fixer, archive steps and the
master log."""
from __future__ import annotations

import json
import shutil
import unittest
import zipfile
from pathlib import Path

from bridgeforge.archive import ArchiveError, archive_mod
from bridgeforge.explain_proofs import prepare_for_audit, read_copies, record_copies, sha256
from bridgeforge.live_trust import audit_shipped, auto_explain_shipped
from bridgeforge.master_log import write_master_log
from bridgeforge.release import record_policy_decision
from bridgeforge.sibling_assets import fix_sibling_assets
from tests.support import resolved_temp_dir

REPO_POLICY = Path(__file__).resolve().parent.parent / "bridgeforge" / "release_policy.json"
DESCRIPTIONS = "data/strings/descriptions.csv"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")


def _workspace(root: Path, name: str = "Mod", mod_id: str = "m") -> Path:
    ws = root / name
    for base in (ws / "original" / "Mod v1", ws / "working"):
        _write(base / "mod_info.json", json.dumps({"id": mod_id, "name": name, "version": "1"}))
        _write(base / "data" / "config" / "settings.json", "{}")
    return ws


class DescriptionsAppliedTests(unittest.TestCase):
    def test_descriptions_written_by_apply_are_explained(self) -> None:
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            original = "id,type,text1,text2,text3,text4,text5,notes\nold,SHIP,Old text,,,,,\n"
            _write(ws / "original" / "Mod v1" / DESCRIPTIONS, original)
            _write(ws / "scratch" / "descriptions.csv.pre-bf-crafted", original)
            _write(ws / "working" / DESCRIPTIONS, original + "new,SHIP,Crafted text,,,,,\n")
            _write(ws / "working" / "BRIDGEFORGE_CREDITS.txt", "credits")
            groups = auto_explain_shipped(ws)
            status = audit_shipped(ws)["status"]
        self.assertTrue(any("descriptions apply" in reason for reason in groups), groups)
        self.assertEqual(status, "PASS")

    def test_edited_author_row_is_not_explained(self) -> None:
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            original = "id,type,text1\nold,SHIP,Old text\n"
            _write(ws / "original" / "Mod v1" / DESCRIPTIONS, original)
            _write(ws / "scratch" / "descriptions.csv.pre-bf-crafted", original)
            _write(ws / "working" / DESCRIPTIONS, "id,type,text1\nold,SHIP,Reworded\n")
            _write(ws / "working" / "BRIDGEFORGE_CREDITS.txt", "credits")
            groups = auto_explain_shipped(ws)
        self.assertFalse(any("descriptions apply" in reason for reason in groups))


class MovedAndBackupTests(unittest.TestCase):
    def test_files_kept_in_translator_workspace_and_removed_src_are_explained(self) -> None:
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            _write(ws / "original" / "Mod v1" / "tools" / "a.txt", "alpha")
            _write(ws / "original" / "Mod v1" / "extras" / "B.java", "class B {}")
            _write(ws / "scratch" / "translator-workspace" / "tools" / "a.txt", "alpha")
            _write(ws / "scratch" / "removed-src" / "extras" / "B.java", "class B {}")
            groups = auto_explain_shipped(ws)
            status = audit_shipped(ws)["status"]
        reasons = " ".join(groups)
        self.assertIn("scratch/translator-workspace/", reasons)
        self.assertIn("scratch/removed-src/", reasons)
        self.assertEqual(status, "PASS")

    def test_a_different_file_in_scratch_proves_nothing(self) -> None:
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            _write(ws / "original" / "Mod v1" / "tools" / "a.txt", "alpha")
            _write(ws / "scratch" / "removed-src" / "tools" / "a.txt", "changed")
            groups = auto_explain_shipped(ws)
        self.assertEqual(groups, {})

    def test_any_pre_bf_backup_and_a_patched_jar_are_explained(self) -> None:
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            _write(ws / "original" / "Mod v1" / "mod_extra.json", "{}")
            _write(ws / "working" / "mod_extra.json", '{"a": 1}')
            _write(ws / "working" / "mod_extra.json.pre-bf-declare-providers.bak", "{}")
            _write(ws / "original" / "Mod v1" / "jars" / "m.jar", "old")
            _write(ws / "working" / "jars" / "m.jar", "new")
            _write(ws / "scratch" / "jar-patch-2026-10-11" / "PATCH-m.json", json.dumps({"jar": "C:/elsewhere/jars/m.jar", "installed": True}))
            audit = audit_shipped(ws)
            auto_explain_shipped(ws)
            after = audit_shipped(ws)
        self.assertNotIn("mod_extra.json", audit["unexplained"])
        self.assertIn("jars/m.jar", audit["unexplained"])
        self.assertNotIn("jars/m.jar", after["unexplained"])


class CopyLedgerTests(unittest.TestCase):
    def test_recorded_copy_is_explained_only_while_the_bytes_match(self) -> None:
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            source = root / "Provider" / "graphics" / "x.png"
            _write(source, "PNGDATA")
            _write(ws / "working" / "graphics" / "x.png", "PNGDATA")
            _write(ws / "working" / "graphics" / "y.png", "OTHER")
            record_copies(ws, {"graphics/x.png": {"source": source, "sha256": sha256(source)},
                               "graphics/y.png": {"source": source, "sha256": sha256(source)}}, "vendor-copy", "2026-10-11")
            groups = auto_explain_shipped(ws)
            unexplained = audit_shipped(ws)["unexplained"]
        self.assertEqual(sum(len(files) for files in groups.values()), 1)
        self.assertEqual(unexplained, ["graphics/y.png"])  # recorded sha does not match the shipped file

    def test_vendor_copy_apply_into_a_workspace_working_folder_records_the_copy(self) -> None:
        from bridgeforge.strip_plan import _record_vendored

        with resolved_temp_dir() as root:
            ws = _workspace(root)
            (ws / "reports").mkdir()
            source = root / "Provider" / "data" / "f.txt"
            _write(source, "x")
            _record_vendored(ws / "working", [("data/f.txt", source)], "vendor-copy")
            _record_vendored(root / "not-a-workspace", [("data/f.txt", source)], "vendor-copy")
            ledger = read_copies(ws)
        self.assertEqual(list(ledger), ["data/f.txt"])
        self.assertEqual(ledger["data/f.txt"]["by"], "vendor-copy")


class PrepareForAuditTests(unittest.TestCase):
    def test_zip_original_is_extracted_and_translation_records_copied_without_overwriting(self) -> None:
        with resolved_temp_dir() as root:
            ws = root / "Zipped"
            (ws / "original").mkdir(parents=True)
            with zipfile.ZipFile(ws / "original" / "Zipped.zip", "w") as archive:
                archive.writestr("Zipped/mod_info.json", '{"id": "z"}')
                archive.writestr("../escape.txt", "no")
            _write(ws / "working" / "mod_info.json", '{"id": "z"}')
            _write(ws / "scratch" / "translation" / "a.json", "{}")
            _write(ws / "scratch" / "translation" / "b.json", "{}")
            _write(ws / "reports" / "translation" / "b.json", "kept")
            done = prepare_for_audit(ws)
            again = prepare_for_audit(ws)
            extracted = (ws / "scratch" / "original-extracted" / "Zipped" / "Zipped" / "mod_info.json").is_file()
            escaped = (ws / "scratch" / "escape.txt").exists() or (ws / "scratch" / "original-extracted" / "escape.txt").exists()
            kept = (ws / "reports" / "translation" / "b.json").read_text(encoding="utf-8")
            copied = (ws / "reports" / "translation" / "a.json").is_file()
            audit = audit_shipped(ws)
        self.assertTrue(extracted)
        self.assertFalse(escaped)
        self.assertEqual((kept, copied), ("kept", True))
        self.assertEqual(len(done), 2)
        self.assertEqual(again, [])
        self.assertEqual(audit["status"], "PASS")


class MixedArchiveDifferencesTests(unittest.TestCase):
    def test_every_provable_category_together_leaves_under_a_tenth_for_a_person(self) -> None:
        """ROADMAP item 73 H1 / 60b done-means, on a synthetic Ironclads-shaped workspace: zip original, moved files, translation,
        backups, a patched jar, a copied file, and one real edit that must stay unexplained."""
        with resolved_temp_dir() as root:
            ws = root / "Mixed"
            (ws / "original").mkdir(parents=True)
            with zipfile.ZipFile(ws / "original" / "Mixed.zip", "w") as archive:
                archive.writestr("Mixed/mod_info.json", '{"id": "mx", "version": "1"}')
                archive.writestr("Mixed/data/config/settings.json", "{}")
                archive.writestr("Mixed/jars/mx.jar", "old")
                archive.writestr("Mixed/data/strings/zh.csv", "id,text\na,\u4e2d\u6587\u4e2d\u6587\n")
                for index in range(8):
                    archive.writestr(f"Mixed/tools/t{index}.txt", f"tool {index}")
                    archive.writestr(f"Mixed/src/C{index}.java", f"class C{index} {{}}")
                archive.writestr("Mixed/data/config/real_edit.json", '{"v": 1}')
            _write(ws / "working" / "mod_info.json", '{"id": "mx", "version": "1"}')
            _write(ws / "working" / "data" / "config" / "settings.json", "{}")
            _write(ws / "working" / "jars" / "mx.jar", "new")
            _write(ws / "working" / "data" / "strings" / "zh.csv", "id,text\na,Chinese\n")
            _write(ws / "working" / "data" / "config" / "real_edit.json", '{"v": 2}')
            _write(ws / "working" / "BRIDGEFORGE_CREDITS.txt", "credits")
            _write(ws / "scratch" / "jar-patch-2026-10-11" / "PATCH-mx.json", json.dumps({"jar": "C:/x/jars/mx.jar", "installed": True}))
            _write(ws / "scratch" / "translation" / "zh.json", "{}")
            for index in range(8):
                _write(ws / "scratch" / "translator-workspace" / "tools" / f"t{index}.txt", f"tool {index}")
                _write(ws / "scratch" / "removed-src" / "src" / f"C{index}.java", f"class C{index} {{}}")
            before = len(prepare_and_audit(ws)["unexplained"])
            auto_explain_shipped(ws)
            after = audit_shipped(ws)
        self.assertGreater(before, 10)
        self.assertEqual(after["unexplained"], ["data/config/real_edit.json"])
        self.assertLess(len(after["unexplained"]) / before, 0.1)


def prepare_and_audit(ws: Path) -> dict:
    prepare_for_audit(ws)
    return audit_shipped(ws)


class SiblingAssetsTests(unittest.TestCase):
    def _pack(self, root: Path) -> tuple[Path, Path, Path]:
        ws = _workspace(root, "Core", "core")
        a = _workspace(root, "Alpha", "alpha")
        b = _workspace(root, "Beta", "beta")
        _write(ws / "working" / "data" / "hulls" / "core_ship.ship", json.dumps({"hullId": "core_ship", "spriteName": "graphics/ships/core_ship.png"}))
        return ws, a, b

    def test_identical_sibling_copies_are_copied_and_recorded(self) -> None:
        with resolved_temp_dir() as root:
            ws, a, b = self._pack(root)
            _write(a / "working" / "graphics" / "ships" / "core_ship.png", "ART")
            _write(b / "original" / "Mod v1" / "graphics" / "ships" / "core_ship.png", "ART")
            vanilla = root / "vanilla-core"
            vanilla.mkdir()
            dry = fix_sibling_assets(ws, vanilla)
            wrote_dry = (ws / "working" / "graphics" / "ships" / "core_ship.png").exists()
            applied = fix_sibling_assets(ws, vanilla, apply=True, today="2026-10-11")
            copied = (ws / "working" / "graphics" / "ships" / "core_ship.png").read_text(encoding="utf-8")
            ledger = read_copies(ws)
            explained = auto_explain_shipped(ws)
        self.assertEqual([c["path"] for c in dry["files"]], ["graphics/ships/core_ship.png"])
        self.assertFalse(wrote_dry)
        self.assertEqual(len(applied["files"]), 1)
        self.assertEqual(copied, "ART")
        self.assertIn("graphics/ships/core_ship.png", ledger)
        self.assertTrue(any("another mod" in reason for reason in explained), explained)

    def test_differing_sibling_copies_are_refused(self) -> None:
        with resolved_temp_dir() as root:
            ws, a, b = self._pack(root)
            _write(a / "working" / "graphics" / "ships" / "core_ship.png", "ART-A")
            _write(b / "working" / "graphics" / "ships" / "core_ship.png", "ART-B")
            vanilla = root / "vanilla-core"
            vanilla.mkdir()
            result = fix_sibling_assets(ws, vanilla, apply=True)
            exists = (ws / "working" / "graphics" / "ships" / "core_ship.png").exists()
        self.assertEqual(result["files"], [])
        self.assertEqual([r["path"] for r in result["files_refused"]], ["graphics/ships/core_ship.png"])
        self.assertFalse(exists)

    def test_nothing_is_invented_when_no_sibling_holds_the_file(self) -> None:
        with resolved_temp_dir() as root:
            ws, _a, _b = self._pack(root)
            vanilla = root / "vanilla-core"
            vanilla.mkdir()
            result = fix_sibling_assets(ws, vanilla, apply=True)
        self.assertEqual(result["files"], [])
        self.assertEqual([r["path"] for r in result["files_unresolved"]], ["graphics/ships/core_ship.png"])

    def test_description_rows_are_copied_when_siblings_agree_and_explained(self) -> None:
        header = "id,type,text1,text2,text3,text4,text5,notes\n"
        with resolved_temp_dir() as root:
            ws, a, b = self._pack(root)
            _write(ws / "working" / "data" / "hulls" / "ship_data.csv", "name,id\nCore,core_ship\n")
            _write(ws / "original" / "Mod v1" / "data" / "hulls" / "ship_data.csv", "name,id\nCore,core_ship\n")
            _write(ws / "working" / DESCRIPTIONS, header + "keep,SHIP,Kept,,,,,\n")
            _write(ws / "original" / "Mod v1" / DESCRIPTIONS, header + "keep,SHIP,Kept,,,,,\n")
            _write(a / "working" / DESCRIPTIONS, header + "core_ship,SHIP,Shared text,,,,,\n")
            _write(b / "working" / DESCRIPTIONS, header + "core_ship,SHIP,Shared text,,,,,\n")
            (root / "vanilla-core").mkdir()
            result = fix_sibling_assets(ws, root / "vanilla-core", apply=True)
            text = (ws / "working" / DESCRIPTIONS).read_text(encoding="utf-8")
            explained = auto_explain_shipped(ws)
        self.assertEqual([r["id"] for r in result["rows"]], ["core_ship"])
        self.assertIn("core_ship,SHIP,Shared text", text)
        self.assertTrue(any("copied from sibling" in reason for reason in explained), explained)

    def test_disagreeing_description_rows_are_refused(self) -> None:
        header = "id,type,text1\n"
        with resolved_temp_dir() as root:
            ws, a, b = self._pack(root)
            _write(ws / "working" / "data" / "hulls" / "ship_data.csv", "name,id\nCore,core_ship\n")
            _write(ws / "working" / DESCRIPTIONS, header)
            _write(a / "working" / DESCRIPTIONS, header + "core_ship,SHIP,One\n")
            _write(b / "working" / DESCRIPTIONS, header + "core_ship,SHIP,Two\n")
            (root / "vanilla-core").mkdir()
            result = fix_sibling_assets(ws, root / "vanilla-core", apply=True)
        self.assertEqual(result["rows"], [])
        self.assertEqual([r["id"] for r in result["rows_refused"]], ["core_ship"])


class ArchiveStepsTests(unittest.TestCase):
    def _ready(self, root: Path) -> tuple[Path, Path]:
        ws = root / "In operation" / "Radar"
        _write(ws / "original" / "Radar" / "mod_info.json", json.dumps({"id": "bf_radar", "name": "Radar", "version": "1"}))
        shutil.copytree(ws / "original" / "Radar", ws / "working")
        _write(ws / "working" / "reports" / "REVIVAL_REPORT.md", "# Report\n\nLIVE_VALIDATED\n")
        policy = root / "policy.json"
        shutil.copy2(REPO_POLICY, policy)
        record_policy_decision("bf_radar", local_only=True, reason="test", policy_path=policy)
        return ws, policy

    def test_note_always_carries_live_date_and_test_id_and_master_log_is_regenerated(self) -> None:
        with resolved_temp_dir() as root:
            ws, policy = self._ready(root)
            from bridgeforge.live_trust import shipped_hash

            _write(ws / "reports" / "live_runs.jsonl", json.dumps({"verdict": "PASS", "test_id": "GRP1-20261011", "date": "2026-10-11",
                                                                  "shipped_sha256": shipped_hash(ws / "working")}) + "\n")
            result = archive_mod(ws, root / "Done", policy_path=policy, today="2026-10-11")
            note = (root / "Done" / "Radar" / "ARCHIVE_NOTE.md").read_text(encoding="utf-8")
            log = (root / "Done" / "MASTER_LOG.md").read_text(encoding="utf-8")
        self.assertIn("Live-validated 2026-10-11 (test GRP1-20261011)", note)
        self.assertEqual(result["master_log"]["mods"], 1)
        self.assertIn("2026-10-11 (GRP1-20261011)", log)

    def test_untested_mod_note_says_so(self) -> None:
        with resolved_temp_dir() as root:
            ws, policy = self._ready(root)
            (ws / "working" / "reports" / "REVIVAL_REPORT.md").write_text("# Report\n\nREADY_FOR_LIVE_TEST\n", encoding="utf-8")
            archive_mod(ws, root / "Done", policy_path=policy, today="2026-10-11")
            note = (root / "Done" / "Radar" / "ARCHIVE_NOTE.md").read_text(encoding="utf-8")
        self.assertIn("Not live-tested", note)

    def test_existing_archive_is_moved_aside_never_deleted(self) -> None:
        with resolved_temp_dir() as root:
            ws, policy = self._ready(root)
            archive_mod(ws, root / "Done", policy_path=policy, today="2026-10-10")
            with self.assertRaises(ArchiveError):
                archive_mod(ws, root / "Done", policy_path=policy, today="2026-10-11")
            result = archive_mod(ws, root / "Done", policy_path=policy, today="2026-10-11", move_aside=True)
            moved = root / "Done" / "_replaced-2026-10-11" / "Radar" / "ARCHIVE_NOTE.md"
            self.assertTrue(moved.is_file())
            self.assertTrue((root / "Done" / "Radar" / "ARCHIVE_NOTE.md").is_file())
            self.assertTrue(result["replaced"].endswith("Radar"))
            log = write_master_log(root / "Done")
        self.assertEqual(log["set_aside"], 1)


if __name__ == "__main__":
    unittest.main()
