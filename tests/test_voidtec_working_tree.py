import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.build_inputs import build_input_manifest
from bridgeforge.evaluation import evaluate_releases
from bridgeforge.integration_scenarios import suggest_integration_scenarios
from bridgeforge.models import TargetProfile
from bridgeforge.working_tree import analyze_working_tree, write_source_authority_selection


class VoidTecWorkingTreeTests(unittest.TestCase):
    def test_layout_and_source_authority_keep_backup_and_build_evidence_visible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "mod"
            (root / "src").mkdir(parents=True)
            (root / "backup_src_orig").mkdir()
            (root / "build").mkdir()
            (root / "mod_info.json").write_text("{}", encoding="utf-8")
            (root / "src" / "Main.java").write_text("class Main {}", encoding="utf-8")
            (root / "backup_src_orig" / "Main.java").write_text("class Main {}", encoding="utf-8")
            (root / "build" / "Main.class").write_bytes(b"\xca\xfe\xba\xbe")
            layout = analyze_working_tree(root)
            self.assertEqual(layout["file_counts"]["GENERATED_CANDIDATE"], 1)
            self.assertEqual(layout["file_counts"]["BACKUP_CANDIDATE"], 1)
            self.assertTrue(layout["selection_required"])
            output = Path(directory) / "authority.json"
            write_source_authority_selection(root, "src", output)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["selected_root"], "src")

    def test_build_input_manifest_requires_authority_for_multiple_roots_and_detects_lombok(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "mod"
            (root / "src").mkdir(parents=True)
            (root / "backup_src_orig").mkdir()
            (root / "mod_info.json").write_text("{}", encoding="utf-8")
            (root / "src" / "Main.java").write_text("import lombok.Getter; class Main {}", encoding="utf-8")
            (root / "backup_src_orig" / "Old.java").write_text("class Old {}", encoding="utf-8")
            unresolved = build_input_manifest(root)
            self.assertTrue(unresolved["source_authority"]["selection_required"])
            selected = build_input_manifest(root, "src")
            self.assertEqual(selected["annotation_processing"]["status"], "REQUIRED")

    def test_integration_suggestions_and_generated_release_delta_are_review_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before, after = root / "before", root / "after"
            for mod in (before, after):
                (mod / "src").mkdir(parents=True)
                (mod / "mod_info.json").write_text('{"id":"fixture","gameVersion":"0.98a"}', encoding="utf-8")
            (before / "src" / "Main.java").write_text("import org.lazywizard.console.Console; class Main {}", encoding="utf-8")
            (after / "src" / "Main.java").write_text("import org.lazywizard.console.Console; class Main {}", encoding="utf-8")
            (after / "build").mkdir()
            (after / "build" / "Main.class").write_bytes(b"\xca\xfe\xba\xbe")
            (after / "backup_src_orig").mkdir()
            (after / "backup_src_orig" / "Main.java").write_text("class Main {}", encoding="utf-8")
            suggestions = suggest_integration_scenarios(after, TargetProfile())
            self.assertTrue(any(item.get("dependency") == "Console Commands" for item in suggestions["suggestions"]))
            report = evaluate_releases(before, after, TargetProfile())
            self.assertEqual(report["content"]["after_only_generated_candidate_count"], 1)
            self.assertEqual(report["content"]["after_only_backup_candidate_count"], 1)
