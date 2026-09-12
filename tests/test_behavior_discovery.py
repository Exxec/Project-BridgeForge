from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from bridgeforge.behavior_discovery import (
    DiscoveryError,
    behavior_diff,
    build_archaeology,
    build_behavior_model,
    build_coverage,
    build_probe_baseline,
    build_save_baseline,
    check_expected_changes,
    evaluate_behavior_release,
    synthesize_tests,
    add_expected_change,
    update_expected_change_status,
    write_archaeology,
    write_behavior_model,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _fixture_mod(root: Path) -> None:
    _write(root / "mod_info.json", '{"id":"fixture","name":"Fixture","jars":["jars/fixture.jar"]}')
    _write(
        root / "src" / "data" / "FixturePlugin.java",
        """package data;
import com.fs.starfarer.api.BaseModPlugin;
public class FixturePlugin extends BaseModPlugin {
  private int persistedCount;
  public void onNewGame() {
    Global.getSector().addScript(new MovingScript());
    Global.getSector().addScript(new MovingScript());
  }
}
class MovingScript { private String destination; }
class UnwiredHelper { private int value; }
""",
    )
    _write(
        root / "data" / "campaign" / "rules.csv",
        "id,script\nfixtureRule,data.rulecmd.FixtureCommand,legacy-extra\n",
    )
    _write(root / "data" / "world" / "factions" / "fixture.faction", '{"id":"fixture","plugin":"data.FixturePlugin"}')
    jar = root / "jars" / "fixture.jar"
    jar.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(jar, "w") as archive:
        archive.writestr("data/FixturePlugin.class", b"not executed")
        archive.writestr("data/PackagedOnly.class", b"not executed")


def _write_observations(path: Path, behavior_id: str, value: int) -> None:
    _write(path, json.dumps({"observations": [{"behavior_id": behavior_id, "observation": "script.count", "subject": "data.MovingScript", "fields": {"count": value}}]}))


class ArchaeologyTests(unittest.TestCase):
    def test_archaeology_is_deterministic_and_never_calls_unreferenced_code_dead(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir:
            root = Path(mod_dir)
            _fixture_mod(root)
            first = build_archaeology(root)
            second = build_archaeology(root)
            self.assertEqual(first, second)
            self.assertEqual(len(first["input_manifest_sha256"]), 64)
            self.assertFalse(first["scope"]["dead_code_claims"])
            unwired = next(item for item in first["no_known_reference"] if item["class"].endswith("UnwiredHelper"))
            self.assertEqual(unwired["finding"], "NO_KNOWN_REFERENCE")
            self.assertIn("runtime-registration", unwired["not_verified"])
            self.assertIn("dead-code", unwired["note"])
            self.assertEqual(len(first["lifecycle"]["possible_duplicates"]), 1)
            authority = first["source_package_authority"]
            self.assertIn("data.FixturePlugin", authority["class_name_overlap"])
            self.assertIn("data.PackagedOnly", authority["package_only_classes"])

    def test_write_archaeology_emits_required_d0_files_outside_mod(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as out_dir:
            root = Path(mod_dir)
            _fixture_mod(root)
            result = write_archaeology(root, Path(out_dir))
            self.assertTrue(Path(result["architecture"]).is_file())
            self.assertTrue(Path(result["cross_reference"]).is_file())
            markdown = Path(result["markdown"]).read_text(encoding="utf-8")
            self.assertIn("NO KNOWN REFERENCE", markdown)
            self.assertIn("not a dead-code verdict", markdown)

    def test_write_archaeology_rejects_output_inside_selected_mod(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir:
            root = Path(mod_dir)
            _fixture_mod(root)
            with self.assertRaises(DiscoveryError):
                write_archaeology(root, root / "reports")


class BehaviorModelTests(unittest.TestCase):
    def test_d1_outputs_stable_linked_ids_and_preserve_unknowns(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as out_dir:
            root, out = Path(mod_dir), Path(out_dir)
            _fixture_mod(root)
            paths = write_archaeology(root, out / "d0")
            first = build_behavior_model(Path(paths["architecture"]))
            second = build_behavior_model(Path(paths["architecture"]))
            self.assertEqual(first, second)
            self.assertTrue(first["behaviors"])
            behavior_ids = {item["id"] for item in first["behaviors"]}
            self.assertTrue(all(item["behavior_id"] in behavior_ids for item in first["risks"] + first["hypotheses"] + first["unknowns"]))
            self.assertTrue(all(item["status"] == "PRESERVE UNTIL EXPLAINED" for item in first["unknowns"]))
            written = write_behavior_model(Path(paths["architecture"]), out / "d1")
            for name in ("behavior", "risks", "hypotheses", "unknowns", "coverage_seed", "behavior_markdown", "risk_markdown", "unknown_markdown"):
                self.assertTrue(Path(written[name]).is_file())

    def test_d3_tests_are_adversarial_and_traceable(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as out_dir:
            root, out = Path(mod_dir), Path(out_dir)
            _fixture_mod(root)
            d0 = write_archaeology(root, out / "d0")
            d1 = write_behavior_model(Path(d0["architecture"]), out / "d1")
            result = synthesize_tests(Path(d1["hypotheses"]))
            self.assertTrue(result["tests"])
            self.assertTrue(all(item["hypothesis_id"].startswith("HYP-") for item in result["tests"]))
            self.assertTrue(all("save and reload between trigger and observation" in item["adversarial_variants"] for item in result["tests"]))


class BaselineDiffCoverageTests(unittest.TestCase):
    def test_static_map_diff_participates_in_expected_change_classification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = root / "capture.json"
            _write_observations(capture, "BEH-ONE", 1)
            baseline = build_probe_baseline(capture, build="r1", scenario="new-game")
            before_baseline, after_baseline = root / "before.json", root / "after.json"
            _write(before_baseline, json.dumps(baseline))
            _write(after_baseline, json.dumps(baseline))
            before_map, after_map = root / "before-map.json", root / "after-map.json"
            _write(before_map, json.dumps({"schema_version": 1, "nodes": [{"id": "class:a.A", "kind": "class", "name": "a.A"}], "lifecycle": {}, "persistent_state": []}))
            _write(after_map, json.dumps({"schema_version": 1, "nodes": [{"id": "class:a.A", "kind": "class", "name": "a.A"}, {"id": "class:a.B", "kind": "class", "name": "a.B"}], "lifecycle": {}, "persistent_state": []}))
            expected = root / "expected.json"
            _write(expected, json.dumps({"schema_version": 1, "mod_id": "fixture", "changes": [{"id": "EXP-FIX-003", "build": "r1", "layer": "static", "summary": "class added", "why": "fixture", "links": {"test": ["TEST-STATIC"]}, "match": {"observation": "static.class", "subject": "a.B", "field": "present", "change": "added"}, "status": "APPROVED", "approved_by": "owner", "approved_on": "2026-09-11"}]}))
            result = behavior_diff(before_baseline, after_baseline, expected_path=expected, before_map_path=before_map, after_map_path=after_map)
            self.assertEqual(result["status"], "PASS")
            static = next(item for item in result["deltas"] if item["subject"] == "a.B")
            self.assertEqual(static["category"], "EXPECTED_CHANGE")
            self.assertEqual(static["layer"], "static")

    def test_expected_change_lifecycle_is_proposed_then_approved_then_retired_with_backup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "expected-changes.json"
            added = add_expected_change(
                path, mod_id="fixture", change_id="EXP-FIX-001", build="r1", layer="runtime",
                summary="count changes", why="fixture", links={"risk": ["RISK-ONE"]},
                match={"observation": "script.count", "subject": "data.Script", "field": "count", "change": "from_to", "from": 1, "to": 2},
            )
            self.assertEqual(added["status"], "UPDATED")
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["changes"][0]["status"], "PROPOSED")
            update_expected_change_status(path, "EXP-FIX-001", status="APPROVED", actor="owner", on="2026-09-11")
            self.assertTrue(path.with_suffix(".json.before-last-edit").is_file())
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["changes"][0]["status"], "APPROVED")
            update_expected_change_status(path, "EXP-FIX-001", status="RETIRED", actor="owner", why="superseded")
            entry = json.loads(path.read_text(encoding="utf-8"))["changes"][0]
            self.assertEqual(entry["status"], "RETIRED")
            self.assertEqual(entry["retired_why"], "superseded")

    def test_baseline_has_no_verdict_and_hashes_its_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "captured.json"
            _write_observations(source, "BEH-ONE", 1)
            result = build_probe_baseline(source, build="r1", scenario="new-game")
            self.assertEqual(result["mode"], "NO_VERDICT_BASELINE")
            self.assertIsNone(result["verdict"])
            self.assertEqual(len(result["input"]["sha256"]), 64)

    def test_expected_change_buckets_and_absent_expectation_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before_input, after_input = root / "before-input.json", root / "after-input.json"
            _write_observations(before_input, "BEH-ONE", 1)
            _write_observations(after_input, "BEH-ONE", 2)
            before = build_probe_baseline(before_input, build="old", scenario="new-game")
            after = build_probe_baseline(after_input, build="r1", scenario="new-game")
            before_path, after_path = root / "before.json", root / "after.json"
            _write(before_path, json.dumps(before))
            _write(after_path, json.dumps(after))
            expected_path = root / "expected.json"
            _write(expected_path, json.dumps({"schema_version": 1, "mod_id": "fixture", "changes": [{"id": "EXP-FIX-001", "build": "r1", "layer": "runtime", "summary": "count changes", "why": "fixture", "links": {"test": ["TEST-ONE"]}, "match": {"observation": "script.count", "subject": "data.MovingScript", "field": "count", "change": "from_to", "from": 1, "to": 2}, "status": "APPROVED", "approved_by": "owner", "approved_on": "2026-09-11"}, {"id": "EXP-FIX-002", "build": "r1", "layer": "runtime", "summary": "missing fix", "why": "fixture", "links": {"risk": ["RISK-TWO"]}, "match": {"observation": "market.stock", "subject": "fixture", "field": "ships", "change": "from_to", "from": 0, "to": ">0"}, "status": "APPROVED", "approved_by": "owner", "approved_on": "2026-09-11"}]}))
            checked = check_expected_changes(expected_path, known_builds=["r1"])
            self.assertEqual(checked["status"], "PASS")
            diff = behavior_diff(before_path, after_path, expected_path=expected_path)
            self.assertEqual(diff["counts"]["EXPECTED_CHANGE"], 1)
            self.assertEqual(diff["counts"]["EXPECTED_BUT_ABSENT"], 1)
            self.assertEqual(diff["status"], "REVIEW_REQUIRED")
            diff_path = root / "diff.json"
            _write(diff_path, json.dumps(diff))
            gate = evaluate_behavior_release(diff_path)
            self.assertEqual(gate["status"], "FAIL")

    def test_coverage_uses_counts_not_percentages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            behavior = root / "behavior.json"
            _write(behavior, json.dumps({"schema_version": 1, "behaviors": [{"id": "BEH-ONE", "persistent_state": []}, {"id": "BEH-TWO", "persistent_state": []}]}))
            captured = root / "captured.json"
            _write_observations(captured, "BEH-ONE", 1)
            baseline = root / "baseline.json"
            _write(baseline, json.dumps(build_probe_baseline(captured, build="r1", scenario="new-game")))
            result = build_coverage(behavior, baselines=[baseline])
            self.assertIsNone(result["percentage"])
            self.assertEqual(result["counts"]["known_behaviors"], 2)
            self.assertEqual(result["counts"]["covered"], 0)
            self.assertEqual(result["counts"]["open"], 2)
            self.assertTrue(any("D5 differential" in reason for reason in result["residual_human_tests"][0]["reasons"]))
            diff = root / "diff.json"
            _write(diff, json.dumps({"schema_version": 1, "status": "PASS", "deltas": [{"behavior_id": "BEH-ONE", "category": "UNCHANGED"}]}))
            validated = build_coverage(behavior, baselines=[baseline], diff_path=diff)
            self.assertEqual(validated["counts"]["covered"], 1)


class SaveBaselineTests(unittest.TestCase):
    def test_historical_save_becomes_hash_bound_no_verdict_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            save = Path(directory) / "save"
            _write(
                save / "campaign.xml",
                '<?xml version="1.0" ?>\n<CampaignEngine><knownFactions><st>a</st><st>b</st></knownFactions>'
                '<Movement><progress>0.5</progress><waypoint>2</waypoint></Movement></CampaignEngine>\n',
            )
            result = build_save_baseline(
                save,
                build="exigency-original-0.7.2a",
                scenario="new-game",
                track_classes=["Movement"],
            )
            self.assertEqual(result["mode"], "NO_VERDICT_BASELINE")
            self.assertEqual(result["reference"]["kind"], "old-game-rig")
            self.assertEqual(result["input"]["kind"], "starsector-save")
            self.assertIsNone(result["verdict"])
            self.assertTrue(any(item["observation"] == "save.object" for item in result["observations"]))
            self.assertTrue(any(item["observation"] == "save.known-list" for item in result["observations"]))


if __name__ == "__main__":
    unittest.main()
