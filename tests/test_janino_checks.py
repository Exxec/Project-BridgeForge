"""Live bug PRB-MISSION-02: a loose script the game's Janino compiler can't handle is a Fatal dialog."""

import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.log_triage import triage_log
from bridgeforge.models import TargetProfile
from bridgeforge.scanner import scan_mod

REPO_ROOT = Path(__file__).resolve().parent.parent


def _mod_with_loose_script(root: Path, body: str) -> Path:
    (root / "mod_info.json").write_text(json.dumps({"id": "fixture", "gameVersion": "0.98a-RC8"}), encoding="utf-8")
    script = root / "data" / "missions" / "fx" / "MissionDefinition.java"
    script.parent.mkdir(parents=True)
    script.write_text(body, encoding="utf-8")
    return root


def _janino_findings(root: Path) -> list:
    return [f for f in scan_mod(root, TargetProfile()).findings if f.id == "loose-script-janino-risk"]


class LooseScriptJaninoRiskTests(unittest.TestCase):
    def test_typed_for_each_over_generic_entries_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            body = "class M {\n  void f(java.util.Map m) {\n    for (Map.Entry<String, String> e : m.entrySet()) { }\n  }\n}\n"
            findings = _janino_findings(_mod_with_loose_script(Path(directory), body))
            self.assertEqual(len(findings), 1)
            self.assertIn("line:3:typed-for-each", findings[0].evidence)
            self.assertEqual(findings[0].classification, "REVIEW")

    def test_diamond_and_lambda_are_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            body = "class M {\n  Object a = new java.util.ArrayList<>();\n  Runnable r = () -> {};\n}\n"
            evidence = _janino_findings(_mod_with_loose_script(Path(directory), body))[0].evidence
            self.assertIn("line:2:diamond", evidence)
            self.assertIn("line:3:lambda", evidence)

    def test_vanilla_style_iterator_and_comments_are_clean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            body = (
                "class M {\n"
                "  // for (ShipAPI s : engine.getShips()) { }   <- commented out, like vanilla\n"
                "  void f(java.util.List ships) {\n"
                "    java.util.Iterator it = ships.iterator();\n"
                "    while (it.hasNext()) { String id = (String) it.next(); }\n"
                "    for (Object o : ships) { }\n"
                "  }\n"
                "}\n"
            )
            self.assertEqual(_janino_findings(_mod_with_loose_script(Path(directory), body)), [])

    def test_probe_mission_is_janino_safe(self) -> None:
        self.assertEqual(_janino_findings(REPO_ROOT / "probe-mod"), [])


class JaninoTriageTests(unittest.TestCase):
    def test_script_compile_failure_is_fatal(self) -> None:
        # The real PRB-1 log lines (the Fatal dialog itself never reaches the log).
        log = (
            "30394 [Thread-2] ERROR com.fs.starfarer.combat.CombatMain  - java.lang.RuntimeException: Error loading [data.missions.bfprobe_combat.MissionDefinition]\n"
            "java.lang.RuntimeException: Error loading [data.missions.bfprobe_combat.MissionDefinition]\n"
            "Caused by: java.lang.ClassNotFoundException: File 'data/missions/bfprobe_combat/MissionDefinition.java', Line 56, Column 26: Assignment conversion not possible from type \"java.lang.Object\" to type \"java.lang.String\"\n"
            "Caused by: org.codehaus.commons.compiler.CompileException: File 'data/missions/bfprobe_combat/MissionDefinition.java', Line 56, Column 26: Assignment conversion not possible\n"
            "\tat org.codehaus.janino.UnitCompiler.compileError(UnitCompiler.java:10174)\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.log"
            path.write_text(log, encoding="utf-8")
            result = triage_log(path)
        self.assertGreaterEqual(result["counts"]["FATAL"], 1)
        self.assertIn(result["fatal"][0]["matched_rule"], {"Janino script compile error", "Script class load error"})


if __name__ == "__main__":
    unittest.main()
