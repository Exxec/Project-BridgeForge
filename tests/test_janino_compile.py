"""ROADMAP P15 item 22.1: loose scripts compiled with RC8's own Janino, offline."""
from __future__ import annotations

import unittest
from pathlib import Path

from bridgeforge.models import ScanResult, TargetProfile
from bridgeforge.scanner import _apply_janino_outcome
from tests.support import resolved_temp_dir

RC8_CORE = Path("C:/Program Files (x86)/Fractal Softworks/Starsector/starsector-core")


def _result_with_risk(*files: str) -> ScanResult:
    result = ScanResult(input_path=Path("x"), target=TargetProfile())
    for file in files:
        result.add(id="loose-script-janino-risk", category="scripts", severity="high", classification="REVIEW",
                   confidence="HEURISTIC", explanation="guess", file=file, evidence=["line:1:typed-for-each"])
    return result


class ApplyJaninoOutcomeTests(unittest.TestCase):
    def test_a_janino_pass_removes_the_guess_and_a_failure_is_manual(self) -> None:
        result = _result_with_risk("data/scripts/Ok.java", "data/scripts/Bad.java")
        _apply_janino_outcome(Path("."), result, {"status": "FAIL", "checked": 2,
                                                  "failures": {"data/scripts/Bad.java": "Unexpected token"}})
        ids = sorted((f.id, f.file) for f in result.findings)
        self.assertEqual(ids, [("loose-script-janino-compile-error", "data/scripts/Bad.java"),
                               ("loose-script-janino-risk", "data/scripts/Bad.java")])
        error = next(f for f in result.findings if f.id == "loose-script-janino-compile-error")
        self.assertEqual((error.classification, error.confidence), ("MANUAL", "DETERMINISTIC"))

    def test_unavailable_janino_leaves_the_guess(self) -> None:
        result = _result_with_risk("data/scripts/Ok.java")
        _apply_janino_outcome(Path("."), result, {"status": "UNAVAILABLE", "failures": {}, "checked": 0})
        self.assertEqual([f.id for f in result.findings], ["loose-script-janino-risk"])


@unittest.skipUnless((RC8_CORE / "janino.jar").is_file(), "needs the RC8 install's janino.jar")
class RealJaninoTests(unittest.TestCase):
    def test_rc8_janino_accepts_typed_for_each_but_rejects_lambdas_and_erased_generic_calls(self) -> None:
        from bridgeforge.compile_check import compile_loose_scripts

        with resolved_temp_dir() as root:
            scripts = root / "m" / "data" / "scripts"
            scripts.mkdir(parents=True)
            (root / "m" / "mod_info.json").write_text('{"id": "jt"}', encoding="utf-8")
            (scripts / "A.java").write_text("package data.scripts;\nimport java.util.*;\npublic class A { public int f(List<String> xs) { int n = 0; for (String s : xs) { n += s.length(); } return n; } }\n", encoding="utf-8")
            (scripts / "B.java").write_text("package data.scripts;\npublic class B { public void f() { Runnable r = () -> {}; } }\n", encoding="utf-8")
            (scripts / "C.java").write_text("package data.scripts;\nimport java.util.*;\npublic class C { public int f(Map<String, List<String>> m) { int n = 0; for (Map.Entry<String, List<String>> e : m.entrySet()) { n += e.getValue().size(); } return n; } }\n", encoding="utf-8")
            outcome = compile_loose_scripts(root / "m", vanilla_core=RC8_CORE)
        if outcome["status"] == "UNAVAILABLE":
            self.skipTest("no JDK")
        janino = outcome["janino"]
        self.assertEqual(janino["checked"], 3)
        self.assertEqual(sorted(janino["failures"]), ["data/scripts/B.java", "data/scripts/C.java"])
        self.assertEqual(outcome["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
