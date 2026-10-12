"""ROADMAP 70 H1.3: generated launchers are checked by reading what they will really pass to java."""
from __future__ import annotations

import unittest
from pathlib import Path

from bridgeforge import java_matrix
from bridgeforge.env_check import env_check, main_class_index, verify_rig_launchers
from tests.support import resolved_temp_dir

FR_VMPARAMS = "-Xmx4g\n\n# General config\n-javaagent:fr.agent.jar\n-Xss4m\n-classpath\nfr.jar;a.jar\ncom.fs.starfarer.StarfarerLauncher\n"


def _rig_with_launchers(tmp: Path) -> Path:
    core, rig = tmp / "core", tmp / "rig"
    core.mkdir()
    rig.mkdir()
    (core / "fr.vmparams").write_text(FR_VMPARAMS, encoding="utf-8")
    for vid, prep in (("j28-fr", False), ("j28-fr-prep", True)):
        variant = {"id": vid, "major": 28, "launcher": "fr", "jdk_home": str(tmp / "nojdk"), "bat": f"run-{vid}.bat", "prepatcher": prep}
        java_matrix.write_launcher_files(rig, variant, core)
    return rig


class LauncherSelfTestTests(unittest.TestCase):
    def test_generated_launchers_pass(self) -> None:
        with resolved_temp_dir() as tmp:
            self.assertEqual(verify_rig_launchers(_rig_with_launchers(tmp)), [])

    def test_an_agent_after_the_main_class_is_found(self) -> None:
        """java-matrix --prepatcher appended the agent after the main class: a program argument, never an agent."""
        with resolved_temp_dir() as tmp:
            rig = _rig_with_launchers(tmp)
            argfile = rig / "fr.filtered-j28-fr-prep.vmparams"
            lines = [line for line in argfile.read_text(encoding="utf-8").splitlines() if "Prepatcher" not in line]
            argfile.write_text("\n".join([*lines, java_matrix.PREPATCHER_AGENT_FLAG]) + "\n", encoding="utf-8")
            problems = {(p["bat"], p["id"]) for p in verify_rig_launchers(rig)}
            self.assertIn(("run-j28-fr-prep.bat", "agent-after-main-class"), problems)
            self.assertIn(("run-j28-fr-prep.bat", "prep-launcher-without-agent"), problems)  # the agent is not in the JVM options either
            self.assertEqual([f["id"] for f in env_check(rig / "run-j28-fr-prep.bat")["findings"] if f["id"] == "agent-after-main-class"], ["agent-after-main-class"])

    def test_one_argument_file_shared_by_a_prep_and_a_plain_launcher_is_found(self) -> None:
        """One fr.filtered.vmparams for every variant: the last written won and every Fast Rendering launcher loaded the agent."""
        with resolved_temp_dir() as tmp:
            rig = _rig_with_launchers(tmp)
            shared = rig / "fr.filtered.vmparams"
            shared.write_text((rig / "fr.filtered-j28-fr-prep.vmparams").read_text(encoding="utf-8"), encoding="utf-8")
            for name in ("run-j28-fr.bat", "run-j28-fr-prep.bat"):
                bat = rig / name
                bat.write_text(bat.read_text(encoding="utf-8").replace(f"fr.filtered-{name[4:-4]}.vmparams", "fr.filtered.vmparams"), encoding="utf-8", newline="")
            ids = {p["id"] for p in verify_rig_launchers(rig)}
            self.assertIn("argfile-shared-between-variants", ids)
            self.assertIn("plain-launcher-with-agent", ids)

    def test_a_missing_argument_file_and_a_relative_rig_path_are_handled(self) -> None:
        with resolved_temp_dir() as tmp:
            rig = _rig_with_launchers(tmp)
            (rig / "fr.filtered-j28-fr.vmparams").unlink()
            self.assertIn("argfile-missing", {p["id"] for p in verify_rig_launchers(rig)})
            import os

            cwd = os.getcwd()
            try:
                os.chdir(tmp)
                (rig / "fr.filtered-j28-fr.vmparams").write_text(FR_VMPARAMS, encoding="utf-8")
                self.assertEqual(verify_rig_launchers(Path("rig")), [])  # %RT% resolves for a relative launcher path too
            finally:
                os.chdir(cwd)

    def test_the_main_class_is_the_first_token_that_is_not_an_option_or_a_value(self) -> None:
        self.assertEqual(main_class_index(["-Xmx4g", "-classpath", "a.jar", "Main", "-javaagent:x.jar"]), 3)
        self.assertEqual(main_class_index(["-Xmx4g", "@argfile", "-cp", "a.jar"]), None)

    def test_setup_refuses_a_launcher_set_that_fails_its_self_test(self) -> None:
        """setup_rig calls the self-test after writing; a bug in the generator is an error, not a silently wrong launcher."""
        from unittest import mock

        with resolved_temp_dir() as tmp:
            core = tmp / "real"
            core.mkdir()
            (core / "fr.vmparams").write_text(FR_VMPARAMS, encoding="utf-8")
            rig = tmp / "rig"
            rig.mkdir()
            from tests.support import link_dir

            link_dir(core, rig / "starsector-core")
            variants = [{"id": "j28-fr-prep", "major": 28, "launcher": "fr", "jdk_home": str(tmp / "nojdk"), "bat": "run-j28-fr-prep.bat", "prepatcher": True}]
            self.assertEqual(java_matrix.setup_rig(rig, variants), ["run-j28-fr-prep.bat"])
            # A generator that appends the agent at the end of the argument file (the 2026-10-12 bug) must fail setup.
            with mock.patch.object(java_matrix, "_insert_before_main_class", lambda lines, flag: [*lines, flag]):
                with self.assertRaises(ValueError) as caught:
                    java_matrix.setup_rig(rig, variants)
            self.assertIn("agent-after-main-class", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
