"""hs_err JVM crash logs in log-triage (ROADMAP 35.10, ported from SPW's crash_log)."""
from __future__ import annotations

import json
import os
import time
import unittest
import zipfile
from pathlib import Path

from bridgeforge.crash_log import attribute_frames, frame_class, parse_crash_log
from bridgeforge.log_triage import triage_log
from tests.support import resolved_temp_dir

SEGV = """#
# A fatal error has been detected by the Java Runtime Environment:
#
#  EXCEPTION_ACCESS_VIOLATION (0xc0000005) at pc=0x00007ff, pid=4242, tid=17
#
# JRE version: OpenJDK Runtime Environment (17.0.9+9) (build 17.0.9+9)
# Java VM: OpenJDK 64-Bit Server VM (17.0.9+9, mixed mode, tiered, compressed oops, g1 gc, windows-amd64)
# Problematic frame:
# C  [lwjgl64.dll+0x1234]
#

---------------  S U M M A R Y ------------

Command Line: -Xmx4g com.fs.starfarer.StarfarerLauncher
Host: Windows 11
Time: Sat Oct  4 12:00:00 2026 elapsed time: 812.5 seconds (0d 0h 13m 32s)

Java frames: (J=compiled Java code, j=interpreted, Vv=VM code)
j  org.lwjgl.opengl.GL11.nglDrawArrays(IIIJ)V+0
J 1234 c2 data.scripts.fx.FxRenderer.render(F)V (88 bytes) @ 0x0000 [0x0000+0x0000]
j  com.fs.starfarer.combat.CombatEngine.advance(F)V+40
v  ~StubRoutines::call_stub

"""

OOM = """#
# There is insufficient memory for the Java Runtime Environment to continue.
# Native memory allocation (mmap) failed to map 528482304 bytes. Error detail: G1 virtual space
# Possible reasons:
#   The system is out of physical RAM or swap space
"""


class CrashLogTests(unittest.TestCase):
    def test_parses_summary_frames_and_header_lines(self) -> None:
        with resolved_temp_dir() as directory:
            path = directory / "hs_err_pid4242.log"
            path.write_text(SEGV, encoding="utf-8")
            crash = parse_crash_log(path)
        self.assertEqual((crash["pid"], crash["tid"]), (4242, 17))
        self.assertIn("EXCEPTION_ACCESS_VIOLATION (0xc0000005) at pc=0x00007ff, pid=4242, tid=17", crash["problem_summary"])
        self.assertEqual(crash["elapsed_seconds"], 812.5)
        self.assertEqual(len(crash["java_frames"]), 4)
        self.assertEqual(frame_class(crash["java_frames"][1]), "data.scripts.fx.FxRenderer")
        self.assertIsNone(frame_class(crash["java_frames"][3]))

    def test_out_of_memory_log_without_a_fatal_header_keeps_its_summary(self) -> None:
        with resolved_temp_dir() as directory:
            path = directory / "hs_err_pid1.log"
            path.write_text(OOM, encoding="utf-8")
            crash = parse_crash_log(path)
        self.assertEqual(crash["problem_summary"][0], "There is insufficient memory for the Java Runtime Environment to continue.")
        self.assertEqual(len(crash["problem_summary"]), 2)

    def test_attributes_frames_to_the_owning_mod(self) -> None:
        crash = {"java_frames": SEGV.split("Java frames: (J=compiled Java code, j=interpreted, Vv=VM code)\n")[1].strip().splitlines()}
        result = attribute_frames(crash, {"data.scripts.fx.FxRenderer": "fx_mod"})
        self.assertEqual(result["top_mod"], "fx_mod")
        self.assertEqual([f["class"] for f in result["mod_frames"]], ["data.scripts.fx.FxRenderer"])

    def test_log_triage_counts_a_crash_written_during_the_log(self) -> None:
        with resolved_temp_dir() as directory:
            core = directory / "starsector-core"
            core.mkdir()
            log = core / "starsector.log"
            log.write_text("0 [main] INFO  com.fs.starfarer.StarfarerLauncher  - Starting Starsector 0.98a-RC8 launcher\n", encoding="utf-8")
            old = core / "hs_err_pid1.log"
            old.write_text(OOM, encoding="utf-8")
            past = time.time() - 7 * 86400
            os.utime(old, (past, past))
            (core / "hs_err_pid4242.log").write_text(SEGV, encoding="utf-8")
            mods = directory / "mods" / "Fx"
            (mods / "jars").mkdir(parents=True)
            (mods / "mod_info.json").write_text('{"id": "fx_mod", "jars": ["jars/fx.jar"]}', encoding="utf-8")
            with zipfile.ZipFile(mods / "jars" / "fx.jar", "w") as jar:
                jar.writestr("data/scripts/fx/FxRenderer.class", b"\xca\xfe\xba\xbe")
            (directory / "mods" / "enabled_mods.json").write_text('{"enabledMods": ["fx_mod"]}', encoding="utf-8")
            result = triage_log(log, mods_dir=directory / "mods", all_mods=True)
        # ROADMAP 36.10: the result names what it ran on.
        self.assertEqual(result["rig_fingerprint"]["enabled_mods"], {"fx_mod": ""})
        crashes = {c["file"]: c for c in result["jvm_crash_logs"]}
        self.assertEqual(set(crashes), {"hs_err_pid1.log", "hs_err_pid4242.log"})
        self.assertFalse(crashes["hs_err_pid1.log"]["during_this_log"])
        self.assertEqual(crashes["hs_err_pid4242.log"]["top_mod"], "fx_mod")
        fatal_files = [f.get("file") for f in result["fatal"] if f.get("kind") == "jvm-crash"]
        self.assertEqual(fatal_files, ["hs_err_pid4242.log"])


class CrashLogCliTests(unittest.TestCase):
    def test_text_output_prints_the_jvm_crash(self) -> None:
        import io
        from unittest import mock

        from bridgeforge.cli import main

        with resolved_temp_dir() as directory:
            log = directory / "starsector.log"
            log.write_text("0 [main] INFO  x  - Starting Starsector\n", encoding="utf-8")
            (directory / "hs_err_pid4242.log").write_text(SEGV, encoding="utf-8")
            with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
                code = main(["log-triage", str(log)])
        self.assertEqual(code, 1)  # a FATAL was found
        self.assertIn("FATAL hs_err_pid4242.log [JVM crash (hs_err)]: EXCEPTION_ACCESS_VIOLATION", out.getvalue())


if __name__ == "__main__":
    unittest.main()


class RigCoreIntegrityTests(unittest.TestCase):
    # ROADMAP 35.11 (2026-10-04, from SPW core_integrity): the rig's core hashes match the recorded baseline.
    def test_records_then_detects_a_changed_core_jar(self) -> None:
        from bridgeforge.rig_doctor import _check_core_integrity

        with resolved_temp_dir() as directory:
            core = directory / "rig" / "starsector-core"
            (core / "data" / "config").mkdir(parents=True)
            (core / "starfarer.api.jar").write_bytes(b"api")
            (core / "data" / "config" / "settings.json").write_text("{}", encoding="utf-8")
            baseline = directory / "state" / "core.json"
            written = _check_core_integrity(directory / "rig", directory, baseline, True)
            same = _check_core_integrity(directory / "rig", directory, baseline, False)
            (core / "starfarer.api.jar").write_bytes(b"patched")
            changed = _check_core_integrity(directory / "rig", directory, baseline, False)
            missing = _check_core_integrity(directory / "rig", directory, directory / "none.json", False)
        self.assertEqual((written["status"], same["status"], changed["status"], missing["status"]), ("PASS", "PASS", "FAIL", "SKIPPED"))
        self.assertIn("starfarer.api.jar", changed["detail"])


class RigCoreBuildTests(unittest.TestCase):
    def test_a_new_build_is_named_not_reported_as_drift(self) -> None:
        from bridgeforge.rig_doctor import _check_core_integrity

        def launcher(core: Path, build: bytes) -> None:
            with zipfile.ZipFile(core / "starfarer_obf.jar", "w") as jar:
                jar.writestr("com/fs/starfarer/StarfarerLauncher.class", b"\xca\xfe" + build + b"\x00")

        with resolved_temp_dir() as directory:
            core = directory / "rig" / "starsector-core"
            core.mkdir(parents=True)
            launcher(core, b"0.98a-RC8")
            baseline = directory / "core.json"
            _check_core_integrity(directory / "rig", directory, baseline, True)
            recorded = json.loads(baseline.read_text(encoding="utf-8"))["build"]
            launcher(core, b"0.99a-RC1")
            result = _check_core_integrity(directory / "rig", directory, baseline, False)
        self.assertEqual(recorded, "0.98a-RC8")
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("runs 0.99a-RC1 but the baseline records 0.98a-RC8", result["detail"])
