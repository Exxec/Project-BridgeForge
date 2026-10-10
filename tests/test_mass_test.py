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


class BundleTests(unittest.TestCase):
    def _targets(self, root, n, tc=()):
        for i in range(n):
            _archive(root, f"M{i}", f"m{i}")
            if i in tc:
                info = json.loads((root / f"M{i}" / f"M{i}" / "mod_info.json").read_text(encoding="utf-8"))
                info["totalConversion"] = "true"
                (root / f"M{i}" / f"M{i}" / "mod_info.json").write_text(json.dumps(info), encoding="utf-8")
        return mass_test.collect_targets(root)

    def test_total_conversions_and_core_replacers_never_share_a_boot(self):
        with resolved_temp_dir() as root:
            targets = self._targets(root, 6, tc=(2,))
            groups = mass_test.plan_bundles(targets, 4)
            self.assertEqual([[t["name"] for t in g] for g in groups], [["M2"], ["M0", "M1", "M3", "M4"], ["M5"]])
            self.assertEqual([[t["name"] for t in g] for g in mass_test.plan_bundles(targets, 1)], [[f"M{i}"] for i in range(6)])

    def _run(self, root, fails, n=4, **kw):
        calls = []

        def fake(rig, mods, variants, **kwargs):
            calls.append((sorted(mods), [v["id"] for v in variants], kwargs.get("mod_sources") is not None, variants[0].get("heap_gb")))
            bad = any(m in fails for m in mods) or (len(mods) > 1 and kw.get("conflict") and set(mods) >= set(kw["conflict"]))
            return {"matrix": [_row(v["id"], 0.0 if bad else 1.0) for v in variants]}

        targets = self._targets(root, n)
        providers = {t["id"]: Path(t["folder"]) for t in targets}
        with mock.patch.object(java_matrix, "run_java_matrix", fake), redirect_stderr(io.StringIO()):
            result = mass_test.run_mass(root, targets, VARIANTS, providers, root / "out", bundle=4)
        return result, calls

    def test_a_passing_bundle_is_one_boot_set_with_a_bigger_heap_and_every_member_passes(self):
        with resolved_temp_dir() as root:
            result, calls = self._run(root, fails=())
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][0], ["m0", "m1", "m2", "m3"])
            self.assertEqual(calls[0][3], mass_test.DEFAULT_BUNDLE_HEAP_GB)
            self.assertEqual({m["verdict"] for m in result["mods"]}, {"SCREEN_PASS"})
            self.assertEqual(result["mods"][0]["stage"], "bundle(4)")

    def test_a_failing_bundle_is_split_until_the_bad_mod_is_placed(self):
        with resolved_temp_dir() as root:
            result, calls = self._run(root, fails=("m2",))
            by = {m["id"]: m["verdict"] for m in result["mods"]}
            self.assertEqual(by["m0"], "SCREEN_PASS")
            self.assertEqual(by["m1"], "SCREEN_PASS")
            self.assertEqual(by["m3"], "SCREEN_PASS")
            self.assertEqual(by["m2"], "ENVIRONMENT_SENSITIVE")  # its validated baseline is assumed to pass; the new variants fail
            self.assertFalse(any(m.get("bundle_conflict") for m in result["mods"]))

    def test_mods_that_pass_alone_but_fail_together_are_a_bundle_conflict(self):
        with resolved_temp_dir() as root:
            result, _calls = self._run(root, fails=(), conflict=("m0", "m3"))
            self.assertTrue(all(m.get("bundle_conflict") for m in result["mods"]))
            self.assertEqual({m["verdict"] for m in result["mods"]}, {"SCREEN_PASS"})


class MikoLauncherTests(unittest.TestCase):
    ARGS = "\n".join([
        "-XX:+UseG1GC", "-Xss4m", "-Xms10240m", "-Xmx10240m",
        "-javaagent:fr.agent.jar",
        '"-javaagent:../mods/StarsectorPrepatcher/agent/StarsectorPrepatcherAgent.jar"',
        "-classpath fr.jar;x.jar",
        "-Dcom.fs.starfarer.settings.paths.saves=..\\\\saves",
        "-Dcom.fs.starfarer.settings.paths.logs=.",
        "com.fs.starfarer.StarfarerLauncher", ""])

    def _install(self, root):
        install = root / "Starsector"
        (install / "starsector-core").mkdir(parents=True)
        (install / "mikohime").mkdir()
        (install / "mods" / "StarsectorPrepatcher").mkdir(parents=True)
        (install / "Miko_Simple.txt").write_text(self.ARGS, encoding="utf-8", newline="")
        return install

    def test_miko_copy_sets_the_heap_and_log_path_and_keeps_the_owners_agents_in_order(self):
        java_matrix._PROBES.clear()
        with resolved_temp_dir() as root:
            install = self._install(root)
            rig = root / "rig"
            (rig / "mods").mkdir(parents=True)
            variant = {"id": "j28-miko", "jdk_home": "C:\\jdk", "launcher": "miko", "major": 28, "bat": "run-j28-miko.bat", "heap_gb": 5}
            with mock.patch.object(java_matrix, "_java_rejects", lambda exe, flags: False):
                java_matrix.write_launcher_files(rig, variant, install / "starsector-core")
            args = (rig / "miko-j28-miko.args").read_text(encoding="utf-8").splitlines()
            self.assertIn("-Xms5g", args)
            self.assertIn("-Xmx5g", args)
            self.assertIn("-Dcom.fs.starfarer.settings.paths.logs=..\\\\logs", args)
            self.assertLess(args.index("-javaagent:fr.agent.jar"), [i for i, a in enumerate(args) if "Prepatcher" in a][0])
            self.assertTrue((rig / "mods" / "StarsectorPrepatcher").exists())
            self.assertTrue((rig / "mikohime").exists())
            self.assertEqual((install / "Miko_Simple.txt").read_text(encoding="utf-8"), self.ARGS)  # install untouched
            java_matrix._remove_tree(rig)

    def test_noprep_variant_drops_only_the_prepatcher_agent(self):
        java_matrix._PROBES.clear()
        with resolved_temp_dir() as root:
            install = self._install(root)
            rig = root / "rig"
            (rig / "mods").mkdir(parents=True)
            variant = {"id": "j28-miko-noprep", "jdk_home": "C:\\jdk", "launcher": "miko-noprep", "major": 28, "bat": "run-j28-miko-noprep.bat"}
            with mock.patch.object(java_matrix, "_java_rejects", lambda exe, flags: False):
                java_matrix.write_launcher_files(rig, variant, install / "starsector-core")
            text = (rig / "miko-j28-miko-noprep.args").read_text(encoding="utf-8")
            self.assertNotIn("Prepatcher", text)
            self.assertIn("-javaagent:fr.agent.jar", text)
            self.assertFalse((rig / "mods" / "StarsectorPrepatcher").exists())
            java_matrix._remove_tree(rig)

    def test_direct_launcher_uses_the_variant_heap(self):
        text = java_matrix.build_launcher("C:\\jdk", "direct", 28, [], 6, "x")
        self.assertIn("-Xms6g -Xmx6g", text)


if __name__ == "__main__":
    unittest.main()
