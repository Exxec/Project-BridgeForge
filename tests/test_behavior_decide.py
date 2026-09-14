"""Written decisions on D1 risks/unknowns (practical-release work on Flu-X, 2026-09-13)."""

import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.behavior_discovery import DiscoveryError, build_archaeology, evaluate_behavior_release, write_behavior_decisions


def _model(root: Path) -> Path:
    behaviors = [
        {"id": "BEH-1", "entry_point": "data/hullmods/hull_mods.csv:data.hullmods.livinghull", "lifecycle": "data-load", "subsystem": "data-loaded-class"},
        {"id": "BEH-2", "entry_point": "data.missions.flx_invasion.MissionDefinition#addPlugin:X", "lifecycle": "registered-runtime-object", "subsystem": "runtime-registration"},
    ]
    (root / "behavior.json").write_text(json.dumps({"schema_version": 1, "behaviors": behaviors}), encoding="utf-8")
    (root / "risks.json").write_text(json.dumps({"schema_version": 1, "risks": [
        {"id": "RISK-1", "behavior_id": "BEH-1", "level": "MEDIUM", "status": "OPEN"},
        {"id": "RISK-2", "behavior_id": "BEH-2", "level": "HIGH", "status": "OPEN"},
    ]}), encoding="utf-8")
    (root / "unknowns.json").write_text(json.dumps({"schema_version": 1, "unknowns": [
        {"id": "UNK-1", "behavior_id": "BEH-1", "status": "PRESERVE UNTIL EXPLAINED"},
        {"id": "UNK-2", "behavior_id": "BEH-2", "status": "PRESERVE UNTIL EXPLAINED"},
    ]}), encoding="utf-8")
    return root


def _decisions(root: Path, decisions: list) -> Path:
    path = root / "decisions.json"
    path.write_text(json.dumps({"schema_version": 1, "decisions": decisions}), encoding="utf-8")
    return path


GOOD = [
    {"select": {"lifecycle": "data-load"}, "status": "EXPLAINED", "why": "Data-loaded hullmod exercised in FLX-R1/R2 combat.", "by": "reviewer", "on": "2026-09-13", "applies_to": ["unknowns"]},
    {"select": {"lifecycle": "data-load"}, "status": "ACCEPTED", "why": "Same evidence.", "by": "reviewer", "on": "2026-09-13", "applies_to": ["risks"]},
    {"select": {"entry_point_prefix": "data.missions."}, "status": "EXPLAINED", "why": "Mission played in FLX-M2.", "evidence": ["logs/FLX-M2.triage.txt"], "by": "owner", "on": "2026-09-13", "applies_to": ["unknowns"]},
    {"select": {"ids": ["RISK-2"]}, "status": "MITIGATED", "why": "Plugin registration verified in FLX-M2.", "by": "owner", "on": "2026-09-13", "applies_to": ["risks"]},
]


class BehaviorDecideTests(unittest.TestCase):
    def test_decisions_clear_the_release_gate_without_touching_generated_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _model(Path(directory))
            generated = (root / "risks.json").read_text(encoding="utf-8")
            result = write_behavior_decisions(root, _decisions(root, GOOD))
            self.assertEqual(result["unknowns_open"], [])
            self.assertEqual(result["high_risks_open"], [])
            self.assertEqual((root / "risks.json").read_text(encoding="utf-8"), generated)
            decided = json.loads((root / "unknowns.decided.json").read_text(encoding="utf-8"))
            self.assertEqual(decided["unknowns"][1]["decision"]["evidence"], ["logs/FLX-M2.triage.txt"])
            (root / "diff.json").write_text(json.dumps({"schema_version": 1, "status": "PASS"}), encoding="utf-8")
            gate = evaluate_behavior_release(root / "diff.json", risks_path=root / "risks.decided.json", unknowns_path=root / "unknowns.decided.json")
        self.assertEqual(gate["status"], "PASS", gate)

    def test_stale_or_invalid_decisions_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _model(Path(directory))
            with self.assertRaises(DiscoveryError):  # selects nothing
                write_behavior_decisions(root, _decisions(root, [{"select": {"lifecycle": "onNewGame"}, "status": "EXPLAINED", "why": "x", "by": "y", "on": "2026-09-13"}]))
            with self.assertRaises(DiscoveryError):  # not a valid risk status
                write_behavior_decisions(root, _decisions(root, [{"select": {"ids": ["RISK-2"]}, "status": "EXPLAINED-ISH", "why": "x", "by": "y", "on": "2026-09-13", "applies_to": ["risks"]}]))
            with self.assertRaises(DiscoveryError):  # no reason given
                write_behavior_decisions(root, _decisions(root, [{"select": {"ids": ["UNK-1"]}, "status": "EXPLAINED", "why": "", "by": "y", "on": "2026-09-13"}]))


class ArchaeologyCommentTests(unittest.TestCase):
    def test_words_after_class_in_a_comment_are_not_a_class(self) -> None:
        # Flu-X NexCompat: "// Only class allowed to import exerelin.*" produced class "allowed".
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text(json.dumps({"id": "fx"}), encoding="utf-8")
            src = root / "jars" / "src" / "demo"
            src.mkdir(parents=True)
            (src / "Real.java").write_text("package demo;\n\n// Only class allowed to import things.\n/* an interface sketch */\npublic class Real {}\n", encoding="utf-8")
            text = json.dumps(build_archaeology(root))
        self.assertIn("class:demo.Real", text)
        self.assertNotIn("class:demo.allowed", text)
        self.assertNotIn("class:demo.sketch", text)


if __name__ == "__main__":
    unittest.main()
