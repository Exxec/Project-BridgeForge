from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from bridgeforge import java_matrix, mass_test
from tests.support import resolved_temp_dir

VARIANTS = [
    {"id": "j25-direct", "major": 25, "launcher": "direct", "java_version": "25", "jdk_home": "a", "bat": "a.bat"},
    {"id": "j25-fr", "major": 25, "launcher": "fr", "java_version": "25", "jdk_home": "a", "bat": "b.bat"},
    {"id": "j28-direct", "major": 28, "launcher": "direct", "java_version": "28", "jdk_home": "c", "bat": "c.bat"},
    {"id": "j28-fr", "major": 28, "launcher": "fr", "java_version": "28", "jdk_home": "c", "bat": "d.bat"},
]


def _archive(done: Path, name: str, mod_id: str, deps: list[str] | None = None, status: str = "LIVE_VALIDATED") -> None:
    mod = done / name / name
    mod.mkdir(parents=True)
    info = {"id": mod_id, "version": {"major": "1", "minor": "2", "patch": "3"}, "dependencies": [{"id": d} for d in deps or []]}
    (mod / "mod_info.json").write_text(json.dumps(info), encoding="utf-8")
    (done / name / "original" / name).mkdir(parents=True)
    (done / name / "original" / name / "mod_info.json").write_text("{}", encoding="utf-8")
    (done / name / "ARCHIVE_NOTE.md").write_text(f"Revival report status: **{status}** (archived)\n", encoding="utf-8")


def _row(vid: str, rate: float) -> dict:
    return {"id": vid, "major": 25, "launcher": "direct", "java_version": "25", "runs": 1, "passed": int(rate), "pass_rate": rate, "statuses": ["PASS" if rate else "FAIL"], "results": []}


class CollectTests(unittest.TestCase):
    def test_collects_shipped_folder_version_status_and_dependencies_not_original_copies(self):
        with resolved_temp_dir() as root:
            _archive(root, "Alpha", "alpha", ["lw_lazylib"])
            (root / "stray.zip").write_text("", encoding="utf-8")
            targets = mass_test.collect_targets(root)
            self.assertEqual(len(targets), 1)
            self.assertEqual((targets[0]["id"], targets[0]["version"], targets[0]["status"], targets[0]["dependencies"]), ("alpha", "1.2.3", "LIVE_VALIDATED", ["lw_lazylib"]))
            self.assertTrue(targets[0]["folder"].endswith("Alpha"))
            self.assertEqual(mass_test.collect_targets(root, ["Nope"]), [])

    def test_resolve_needs_follows_transitive_dependencies_and_reports_missing(self):
        with resolved_temp_dir() as root:
            for n in ("lib", "lib2"):
                (root / n).mkdir()
            (root / "lib" / "mod_info.json").write_text(json.dumps({"id": "lib", "dependencies": [{"id": "lib2"}]}), encoding="utf-8")
            (root / "lib2" / "mod_info.json").write_text(json.dumps({"id": "lib2"}), encoding="utf-8")
            providers = mass_test.index_providers([root])
            target = {"id": "m", "folder": str(root / "m"), "dependencies": ["lib", "ghost"]}
            needs = mass_test.resolve_needs(target, providers)
            self.assertEqual(needs["ids"], ["lib", "lib2", "m"])
            self.assertEqual(needs["missing"], ["ghost"])


class ClassifyTests(unittest.TestCase):
    def test_screen_variants_are_direct_on_lowest_java_and_fr_on_highest(self):
        baseline, stress = mass_test.pick_screen_variants(VARIANTS)
        self.assertEqual((baseline["id"], stress["id"]), ("j25-direct", "j28-fr"))

    def test_classify(self):
        self.assertEqual(mass_test.classify([_row("a", 1.0), _row("b", 1.0)]), "ALL_PASS")
        self.assertEqual(mass_test.classify([_row("a", 0.0), _row("b", 0.0)]), "ALL_FAIL")
        self.assertEqual(mass_test.classify([_row("a", 1.0), _row("b", 0.0)]), "ENVIRONMENT_SENSITIVE")
        self.assertEqual(mass_test.classify([_row("a", 1.0), _row("b", 0.5)]), "FLAKY")


class RunMassTests(unittest.TestCase):
    def _run(self, root, outcomes, targets, **kwargs):
        calls = []

        def fake(rig, mods, variants, **kw):
            calls.append([v["id"] for v in variants])
            return {"matrix": [_row(v["id"], outcomes(v["id"])) for v in variants]}

        providers = {t["id"]: Path(t["folder"]) for t in targets}
        with mock.patch.object(java_matrix, "run_java_matrix", fake), redirect_stderr(io.StringIO()):
            result = mass_test.run_mass(root, targets, VARIANTS, providers, root / "out", **kwargs)
        return result, calls

    def test_screening_boots_only_the_stress_variant_for_a_validated_mod_that_passes(self):
        with resolved_temp_dir() as root:
            _archive(root, "Alpha", "alpha")
            result, calls = self._run(root, lambda v: 1.0, mass_test.collect_targets(root))
            self.assertEqual(calls, [["j28-fr"]])
            self.assertEqual(result["mods"][0]["verdict"], "SCREEN_PASS")
            self.assertIn("ASSUMED_PASS", result["mods"][0]["matrix"][0]["statuses"])
            self.assertTrue((root / "out" / "MASS_TEST.md").is_file())

    def test_a_stress_failure_expands_to_the_remaining_variants_and_is_environment_sensitive(self):
        with resolved_temp_dir() as root:
            _archive(root, "Alpha", "alpha")
            result, calls = self._run(root, lambda v: 0.0 if v == "j28-fr" else 1.0, mass_test.collect_targets(root))
            self.assertEqual(calls, [["j28-fr"], ["j25-fr", "j28-direct"]])
            self.assertEqual(result["mods"][0]["verdict"], "ENVIRONMENT_SENSITIVE")
            self.assertIn("Alpha", (root / "out" / "MASS_TEST.md").read_text(encoding="utf-8"))

    def test_unvalidated_mod_boots_the_baseline_too_and_missing_dependency_is_skipped(self):
        with resolved_temp_dir() as root:
            _archive(root, "Alpha", "alpha", status="UNKNOWN")
            _archive(root, "Beta", "beta", ["ghost"])
            result, calls = self._run(root, lambda v: 1.0, mass_test.collect_targets(root))
            self.assertEqual(calls, [["j25-direct", "j28-fr"]])
            self.assertEqual([m["verdict"] for m in result["mods"]], ["SCREEN_PASS", "SKIPPED_MISSING_DEPENDENCY"])

    def test_limit_zero_tests_nothing(self):
        with resolved_temp_dir() as root:
            _archive(root, "Alpha", "alpha")
            result, calls = self._run(root, lambda v: 1.0, mass_test.collect_targets(root), limit=0)
            self.assertEqual((calls, result["tested"]), ([], 0))


class FlagFilterTests(unittest.TestCase):
    def test_a_rejected_flag_is_dropped_and_recorded_while_other_flags_stay(self):
        java_matrix._PROBES.clear()
        with mock.patch.object(java_matrix, "_java_rejects", lambda exe, flags: "-noverify" in flags):
            dropped = java_matrix.unsupported_flags(Path("j28/bin/java.exe"), ["-noverify", "-XX:+UseX", "-Dfoo=1"])
        self.assertEqual(dropped, ["-noverify"])
        text = java_matrix.build_launcher("C:\\jdk", "direct", 28, dropped)
        self.assertNotIn("-noverify", text)
        self.assertIn("-XX:+UnlockDiagnosticVMOptions", text)

    def test_fr_variant_gets_a_filtered_copy_of_the_install_vmparams_and_the_install_is_untouched(self):
        java_matrix._PROBES.clear()
        with resolved_temp_dir() as root:
            core = root / "core"
            core.mkdir()
            original = "-XX:+UseVectorStubs\n-Xss4m\n-classpath\nfr.jar\n"
            (core / "fr.vmparams").write_text(original, encoding="utf-8", newline="")
            rig = root / "rig"
            rig.mkdir()
            variant = {"jdk_home": "C:\\jdk", "launcher": "fr", "major": 28, "bat": "run-j28-fr.bat"}
            with mock.patch.object(java_matrix, "_java_rejects", lambda exe, flags: "-XX:+UseVectorStubs" in flags):
                dropped = java_matrix.write_launcher_files(rig, variant, core)
            self.assertEqual(dropped, ["-XX:+UseVectorStubs"])
            self.assertEqual((rig / "fr.filtered.vmparams").read_text(encoding="utf-8").splitlines(), ["-Xss4m", "-classpath", "fr.jar"])
            self.assertEqual((core / "fr.vmparams").read_text(encoding="utf-8"), original)
            self.assertIn("fr.filtered.vmparams", (rig / "run-j28-fr.bat").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
