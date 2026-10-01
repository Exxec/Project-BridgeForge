"""bump-version, restore-from-done, revive-review, decompile repair and Object-owner noise (ROADMAP P15 item 33)."""
from __future__ import annotations

import json
import os
import unittest

from bridgeforge.jar_batch import repair_decompile
from bridgeforge.jar_patch import _only_return_type_relinks
from bridgeforge.workspace_tools import bump_version, next_version, restore_from_done, review_applied
from tests.support import resolved_temp_dir


class WorkspaceToolTests(unittest.TestCase):
    def test_next_version(self) -> None:
        self.assertEqual(next_version("1.0.0"), "1.0.0+bf.1")
        self.assertEqual(next_version("v2.0a DEV+bf.2"), "v2.0a DEV+bf.3")

    def test_bump_version_writes_mod_info_report_and_changelog(self) -> None:
        with resolved_temp_dir() as root:
            working = root / "Mod" / "working"
            working.mkdir(parents=True)
            (working / "mod_info.json").write_text('{"id":"m","name":"Some Mod","version":"1.2"}', encoding="utf-8")
            result = bump_version(root / "Mod", "Relinked a tooltip call.\nEvidence: javap.", day="2026-10-01", changelog=root / "MOD_CHANGELOG.md")
            info = json.loads((working / "mod_info.json").read_text(encoding="utf-8"))
            report = (working / "reports" / "REVIVAL_REPORT.md").read_text(encoding="utf-8")
            log = (root / "MOD_CHANGELOG.md").read_text(encoding="utf-8")
        self.assertEqual((result["new"], info["version"]), ("1.2+bf.1", "1.2+bf.1"))
        self.assertTrue(report.rstrip().endswith("READY_FOR_LIVE_TEST"))
        self.assertIn("- **Some Mod** 1.2+bf.1: Relinked a tooltip call.", log)

    def test_restore_from_done_brings_back_reports_and_baseline(self) -> None:
        with resolved_temp_dir() as root:
            done = root / "Done" / "Mod"
            (done / "Mod").mkdir(parents=True)
            (done / "Mod" / "mod_info.json").write_text("{}", encoding="utf-8")
            (done / "workspace").mkdir()
            (done / "workspace" / "REVIVAL_REPORT.md").write_text("LIVE_VALIDATED\n", encoding="utf-8")
            (done / "workspace" / "baseline.json").write_text("{}", encoding="utf-8")
            result = restore_from_done(done, root / "In operation")
            restored = (root / "In operation" / "Mod" / "working" / "reports" / "baseline.json").is_file()
        self.assertTrue(result["baseline"] and restored)
        self.assertIsNone(result["note"])

    def test_review_flags_a_misplaced_guard_and_a_jar_source_edit(self) -> None:
        with resolved_temp_dir() as root:
            ws = root / "Mod"
            source = ws / "working" / "src" / "data" / "Gen.java"
            source.parent.mkdir(parents=True)
            (ws / "reports" / "revive").mkdir(parents=True)
            (ws / "reports" / "revive" / "REVIVE.json").write_text(json.dumps({"applied": [
                {"finding": "hard-coded-campaign-system-reference", "files": ["src/data/Gen.java"]}]}), encoding="utf-8")
            backup = source.with_name("Gen.java.pre-bf-fix-hard-coded-campaign-system-reference.bak")
            backup.write_text("/**\n */\nclass Gen { void g() { StarSystemAPI s = x.getStarSystem(\"A\"); } }\n", encoding="utf-8")
            source.write_text("/**\nif (s == null) { // BridgeForge: guard a missing star system\n */\nclass Gen {}\n", encoding="utf-8")
            os.utime(backup, (1790000000, 1790000000))  # 2026-09-21
            result = review_applied(root, "2026-09-01")
        flags = result["flagged"][0]["flags"]
        self.assertIn("guard-misplaced", flags)
        self.assertTrue(any(f.startswith("jar-source-edit") for f in flags))


class RelinkHelperTests(unittest.TestCase):
    def test_object_method_owner_swaps_are_noise(self) -> None:
        calls = {"java/lang/Object.equals:(Ljava/lang/Object;)Z": -1, "a/Fleet.equals:(Ljava/lang/Object;)Z": 1,
                 "a/Tip.add:(F)V": -1, "a/Tip.add:(F)La/Panel;": 1}
        self.assertEqual(_only_return_type_relinks(calls), ["a/Tip.add:(F)V -> La/Panel;"])

    def test_repair_decompile_comments_out_a_redeclaration(self) -> None:
        with resolved_temp_dir() as root:
            source = root / "H.java"
            source.write_text("switch (k) {\ncase 1:\n  String disc;\n  disc = \"a\";\ncase 2:\n  String disc;\n  disc = \"b\";\n}\n", encoding="utf-8")
            changed = repair_decompile(source, [{"file": str(source), "message": "variable disc is already defined in method f()"}])
            text = source.read_text(encoding="utf-8")
        self.assertTrue(changed)
        self.assertEqual(text.count("String disc;"), 1)


if __name__ == "__main__":
    unittest.main()


class OverloadGateTests(unittest.TestCase):
    def test_balanced_overload_calls_drop_and_unbalanced_stay(self) -> None:
        from bridgeforge.jar_batch import _drop_overloads
        site = "com/fs/starfarer/api/ui/TooltipMakerAPI.addCustom"
        calls = {site + ":(Lcom/fs/starfarer/api/ui/CustomPanelAPI;F)Lx;": -1, site + ":(Lcom/fs/starfarer/api/ui/UIComponentAPI;F)Lx;": 1}
        self.assertEqual(_drop_overloads(calls, {site}), {})  # Void-Tec: same call site, new overload
        self.assertEqual(_drop_overloads({**calls, site + ":(F)Lx;": 1}, {site}), {**calls, site + ":(F)Lx;": 1})
        self.assertEqual(_drop_overloads(calls, set()), calls)

    def test_renames_are_listed_with_the_rc8_name(self) -> None:
        from bridgeforge.jar_batch import RENAMED_METHODS
        self.assertEqual(RENAMED_METHODS["com/fs/starfarer/api/impl/campaign/events/OfficerManagerEvent.pickPortrait"], "pickPortraitPreferNonDuplicate")


class CopyBackTests(unittest.TestCase):
    def test_an_edited_copy_goes_back_over_the_mod_source_with_a_backup(self) -> None:
        from bridgeforge.jar_batch import _copy_back_sources
        with resolved_temp_dir() as root:
            working = root / "working"
            source = working / "jars" / "src" / "data" / "Gate.java"
            source.parent.mkdir(parents=True)
            source.write_text("new CampaignEntityPickerListener() {}", encoding="utf-8")
            edited = root / "scratch" / "data" / "Gate.java"
            edited.parent.mkdir(parents=True)
            edited.write_text("new com.fs.starfarer.api.campaign.BaseCampaignEntityPickerListener() {}", encoding="utf-8")
            updated = _copy_back_sources({edited: source}, [edited], working, "port-interfaces")
            backup = source.with_name("Gate.java.pre-bf-port-interfaces.bak").read_text(encoding="utf-8")
            now = source.read_text(encoding="utf-8")
        self.assertEqual(len(updated), 1)
        self.assertIn("BaseCampaignEntityPickerListener", now)
        self.assertIn("new CampaignEntityPickerListener()", backup)
