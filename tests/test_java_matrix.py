from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from bridgeforge import boot_test, java_matrix
from bridgeforge.cli import main
from tests.support import link_dir, resolved_temp_dir


def _fake_jdk(root: Path, name: str, version: str) -> Path:
    home = root / name
    (home / "bin").mkdir(parents=True)
    (home / "bin" / "java.exe").write_text("", encoding="utf-8")
    (home / "release").write_text(f'JAVA_VERSION="{version}"\n', encoding="utf-8")
    return home


def _rig(root: Path) -> Path:
    rig = root / "rig"
    rig.mkdir()
    target = root / "core"
    target.mkdir()
    link_dir(target, rig / "starsector-core")
    return rig


class DiscoverTests(unittest.TestCase):
    def test_finds_one_jdk_per_major_and_reads_versions_from_folder_or_release(self):
        with resolved_temp_dir() as root:
            _fake_jdk(root, "jdk-28+13", "28-beta")
            _fake_jdk(root, "jdk-25.0.4.1+1", "25.0.4.1")
            _fake_jdk(root, "jre1.8.0_503", "1.8.0_503")
            found = java_matrix.discover_jdks(None, [root])
            self.assertEqual([j["major"] for j in found], [8, 25, 28])

    def test_major_parses_old_and_new_schemes(self):
        self.assertEqual([java_matrix._major(t) for t in ("1.8.0_271", "17.0.9", "28-beta", "jdk-27+22")], [8, 17, 28, 27])

    def test_plan_skips_java_below_17_unless_asked(self):
        jdks = [{"major": 8, "home": "h8", "version": "1.8"}, {"major": 25, "home": "h25", "version": "25"}]
        self.assertEqual([v["id"] for v in java_matrix.plan_variants(jdks)], ["j25-direct", "j25-fr"])
        self.assertEqual([v["id"] for v in java_matrix.plan_variants(jdks, ["fr"], [8])], ["j8-fr"])


class LauncherTests(unittest.TestCase):
    def test_direct_launcher_uses_the_jdk_and_keeps_the_rig_paths(self):
        text = java_matrix.build_launcher(r"C:\jdk-28", "direct", 28)
        self.assertIn(r'"C:\jdk-28\bin\java.exe"', text)
        self.assertIn("-noverify", text)
        self.assertIn(r"-Dcom.fs.starfarer.settings.paths.logs=..\logs", text)
        self.assertIn("com.fs.starfarer.StarfarerLauncher", text)

    def test_fr_launcher_uses_fr_vmparams_and_redirects_the_log_into_the_rig(self):
        text = java_matrix.build_launcher(r"C:\jdk-28", "fr", 28)
        self.assertIn("@fr.vmparams", text)
        self.assertIn("-javaagent:PatchLibAgent.jar", text)
        self.assertIn(r"paths.logs=..\logs", text)

    def test_unknown_launcher_is_rejected(self):
        with self.assertRaises(ValueError):
            java_matrix.build_launcher("x", "bogus", 25)

    def test_setup_refuses_a_rig_without_a_core_link_and_writes_bats_otherwise(self):
        with resolved_temp_dir() as root:
            plain = root / "plain"
            (plain / "starsector-core").mkdir(parents=True)
            variants = java_matrix.plan_variants([{"major": 25, "home": str(root), "version": "25"}], ["direct"])
            with self.assertRaises(ValueError):
                java_matrix.setup_rig(plain, variants)
            rig = _rig(root)
            self.assertEqual(java_matrix.setup_rig(rig, variants), ["run-j25-direct.bat"])
            self.assertTrue((rig / "run-j25-direct.bat").is_file())
            self.assertFalse((rig / "run-java25.bat").exists())


class RunTests(unittest.TestCase):
    def _variants(self):
        return [{"id": "j25-direct", "major": 25, "launcher": "direct", "jdk_home": "x", "java_version": "25", "bat": "run-j25-direct.bat"},
                {"id": "j28-fr", "major": 28, "launcher": "fr", "jdk_home": "y", "java_version": "28", "bat": "run-j28-fr.bat"}]

    def test_reports_a_pass_rate_per_variant_and_flags_a_flaky_one(self):
        outcomes = iter(["PASS", "PASS", "PASS", "FAIL"])
        seen = []

        def fake(rig, mods, timeout, log_name, bat_name):
            seen.append(bat_name)
            return {"status": next(outcomes), "reason": None, "log": log_name, "elapsed_seconds": 1.0, "triage": None}

        with resolved_temp_dir() as root, mock.patch.object(boot_test, "run_boot_test", fake), redirect_stderr(io.StringIO()) as err:
            result = java_matrix.run_java_matrix(_rig(root), ["m"], self._variants(), repeats=2, checkpoint=root / "c.partial.jsonl")
            self.assertFalse((root / "c.partial.jsonl").exists())
        self.assertEqual(seen, ["run-j25-direct.bat"] * 2 + ["run-j28-fr.bat"] * 2)
        self.assertEqual([m["pass_rate"] for m in result["matrix"]], [1.0, 0.5])
        self.assertEqual(result["verdict"], "FLAKY")
        self.assertIn("[4/4] j28-fr#2: FAIL", err.getvalue())

    def test_an_interrupted_run_resumes_from_its_checkpoint(self):
        calls = []

        def fake(rig, mods, timeout, log_name, bat_name):
            calls.append(log_name)
            if len(calls) == 2:
                raise KeyboardInterrupt
            return {"status": "PASS", "reason": None, "log": None, "elapsed_seconds": 1.0, "triage": None}

        with resolved_temp_dir() as root:
            rig, ckpt = _rig(root), root / "c.partial.jsonl"
            with mock.patch.object(boot_test, "run_boot_test", fake), redirect_stderr(io.StringIO()):
                with self.assertRaises(KeyboardInterrupt):
                    java_matrix.run_java_matrix(rig, ["m"], self._variants(), repeats=1, checkpoint=ckpt)
                calls.clear()
                result = java_matrix.run_java_matrix(rig, ["m"], self._variants(), repeats=1, checkpoint=ckpt)
        self.assertEqual(len(calls), 1)  # only the unfinished boot reran
        self.assertEqual(result["verdict"], "PASS_ALL")

    def test_missing_launcher_is_refused_not_skipped(self):
        with resolved_temp_dir() as root:
            result = java_matrix.run_java_matrix(_rig(root), ["m"], self._variants()[:1], repeats=1)
        self.assertEqual(result["verdict"], "REFUSED")


class ParallelTests(unittest.TestCase):
    def _variants(self, n=4):
        return [{"id": f"j{25 + i}-direct", "major": 25 + i, "launcher": "direct", "jdk_home": "x", "java_version": str(25 + i), "bat": f"run-j{25 + i}-direct.bat"} for i in range(n)]

    def _ok(self, rig, mods, timeout, log_name, bat_name):
        return {"status": "PASS", "reason": None, "log": log_name, "elapsed_seconds": 0.1, "triage": None}

    def test_parallel_is_capped_at_three(self):
        with resolved_temp_dir() as root:
            rig = _rig(root)
            for bad in (0, 4):
                with self.assertRaises(ValueError):
                    java_matrix.run_java_matrix(rig, ["m"], self._variants(1), parallel=bad)

    def test_each_parallel_variant_gets_its_own_rig_with_linked_mods_and_core(self):
        with resolved_temp_dir() as root:
            rig = _rig(root)
            (rig / "mods" / "ModA").mkdir(parents=True)
            (rig / "mods" / "ModA" / "mod_info.json").write_text("{}", encoding="utf-8")
            seen = []

            def fake(inst, mods, timeout, log_name, bat_name):
                seen.append(Path(inst))
                return self._ok(inst, mods, timeout, log_name, bat_name)

            with mock.patch.object(boot_test, "run_boot_test", fake), redirect_stderr(io.StringIO()):
                result = java_matrix.run_java_matrix(rig, ["ModA"], self._variants(3), repeats=1, parallel=3)
            self.assertEqual(result["verdict"], "PASS_ALL")
            self.assertEqual(sorted(p.name for p in seen), ["j25-direct", "j26-direct", "j27-direct"])
            inst = rig / "instances" / "j25-direct"
            self.assertTrue(boot_test._is_link(inst / "starsector-core"))
            self.assertTrue((inst / "mods" / "ModA" / "mod_info.json").is_file())
            self.assertTrue((inst / "run-j25-direct.bat").is_file())
            self.assertEqual(json.loads((inst / "instance.json").read_text(encoding="utf-8"))["state"], "done")
            self.assertEqual(len(java_matrix.list_instances(rig)), 3)
            # rebuilding removes the junctions without touching the real mod behind them
            java_matrix.make_instance_rig(rig, self._variants(1)[0], ["ModA"])
            self.assertTrue((rig / "mods" / "ModA" / "mod_info.json").is_file())

    def test_skip_known_reuses_an_all_pass_for_the_same_mod_set_only(self):
        calls = []

        def fake(rig, mods, timeout, log_name, bat_name):
            calls.append(bat_name)
            return self._ok(rig, mods, timeout, log_name, bat_name)

        with resolved_temp_dir() as root, mock.patch.object(boot_test, "run_boot_test", fake), redirect_stderr(io.StringIO()):
            rig, ledger, variants = _rig(root), root / "ledger.json", self._variants(2)
            java_matrix.run_java_matrix(rig, ["m"], variants, repeats=1, ledger=ledger)
            calls.clear()
            again = java_matrix.run_java_matrix(rig, ["m"], variants, repeats=1, ledger=ledger, skip_known=True)
            self.assertEqual(calls, [])
            self.assertEqual(again["matrix"][0]["statuses"], ["KNOWN_PASS"])
            self.assertEqual(again["verdict"], "PASS_ALL")
            java_matrix.run_java_matrix(rig, ["m", "new_mod"], variants, repeats=1, ledger=ledger, skip_known=True)
            self.assertEqual(len(calls), 2)  # a new mod set boots on every variant

    def test_cli_exposes_parallel_skip_known_and_instances(self):
        out = io.StringIO()
        with redirect_stdout(out), self.assertRaises(SystemExit):
            main(["java-matrix", "run", "--help"])
        for flag in ("--parallel", "--skip-known", "--preset"):
            self.assertIn(flag, out.getvalue())
        with resolved_temp_dir() as root, redirect_stdout(io.StringIO()) as listing:
            self.assertEqual(main(["java-matrix", "instances", str(_rig(root))]), 0)
        self.assertIn("no instances", listing.getvalue())


class DescribeLogTests(unittest.TestCase):
    def test_reads_java_version_and_fast_rendering_from_a_tester_log(self):
        with resolved_temp_dir() as root:
            log = root / "starsector.log"
            log.write_text("673 [main] INFO  com.fs.starfarer.StarfarerLauncher  - Java version: 28-beta (64-bit)\n"
                           "9 [Thread-3] INFO  com.genir.renderer.bridge.context.TextureManager  - Loading image\n", encoding="utf-8")
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["java-matrix", "describe-log", str(log), "--json"]), 0)
            self.assertEqual(json.loads(out.getvalue()), {"java_version": "28-beta (64-bit)", "fast_rendering": True, "launcher_hint": "fr"})


if __name__ == "__main__":
    unittest.main()
