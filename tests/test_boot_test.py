from __future__ import annotations

import json
import sys
from tests.support import resolved_temp_dir
import unittest
from pathlib import Path
from unittest import mock

from bridgeforge import boot_test


def _make_rig(directory: Path, link_core: bool = True) -> Path:
    runtime_dir = directory / "rig"
    (runtime_dir / "mods").mkdir(parents=True)
    (runtime_dir / "logs").mkdir(parents=True)
    (runtime_dir / "mods" / "enabled_mods.json").write_text(
        json.dumps({"enabledMods": ["existing_mod"]}), encoding="utf-8"
    )
    core_target = directory / "fake-core"
    core_target.mkdir(parents=True)
    core_path = runtime_dir / "starsector-core"
    if link_core:
        try:
            core_path.symlink_to(core_target, target_is_directory=True)
        except OSError:
            import subprocess

            subprocess.run(
                ["cmd.exe", "/c", "mklink", "/J", str(core_path), str(core_target)],
                capture_output=True,
                check=True,
            )
    else:
        core_path.mkdir(parents=True)
    return runtime_dir


def _write_fake_launcher(runtime_dir: Path, script_body: str) -> None:
    script_path = runtime_dir / "fake_launcher.py"
    script_path.write_text(script_body, encoding="utf-8")
    bat_path = runtime_dir / boot_test.BAT_NAME
    python_exe = sys.executable
    bat_path.write_text(f'@echo off\r\n"{python_exe}" -u "{script_path}" %*\r\n', encoding="utf-8")


class BootTestRefusalTests(unittest.TestCase):
    def test_refuses_when_core_is_not_a_link(self) -> None:
        with resolved_temp_dir() as directory:
            runtime_dir = _make_rig(Path(directory), link_core=False)
            _write_fake_launcher(runtime_dir, "print('unused')\n")
            result = boot_test.run_boot_test(runtime_dir, ["demo_mod"], timeout=3)
            self.assertEqual(result["status"], "REFUSED")
            self.assertIn("junction/symlink", result["reason"])

    def test_refuses_when_java_already_running_under_runtime_dir(self) -> None:
        with resolved_temp_dir() as directory:
            runtime_dir = _make_rig(Path(directory))
            _write_fake_launcher(runtime_dir, "print('unused')\n")
            fake_exe = str(runtime_dir / "jdk" / "bin" / "java.exe")
            with mock.patch.object(boot_test, "_running_java_under", return_value=[{"pid": 4321, "exe": fake_exe}]):
                result = boot_test.run_boot_test(runtime_dir, ["demo_mod"], timeout=3)
            self.assertEqual(result["status"], "REFUSED")
            self.assertIn("already running", result["reason"])
            # Refusal must not touch the mods file at all.
            data = json.loads((runtime_dir / "mods" / "enabled_mods.json").read_text(encoding="utf-8"))
            self.assertEqual(data["enabledMods"], ["existing_mod"])


@unittest.skipUnless(sys.platform == "win32", "boot-test launches the rig's Windows .bat")
class BootTestLaunchTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_poll = boot_test.POLL_INTERVAL_SECONDS
        boot_test.POLL_INTERVAL_SECONDS = 0.2

    def tearDown(self) -> None:
        boot_test.POLL_INTERVAL_SECONDS = self._orig_poll

    def test_pass_when_marker_appears(self) -> None:
        with resolved_temp_dir() as directory:
            runtime_dir = _make_rig(Path(directory))
            _write_fake_launcher(
                runtime_dir,
                "import time\n"
                "print('Playing music with id [miscallenous_main_menu.ogg]')\n"
                "time.sleep(30)\n",
            )
            with mock.patch.object(boot_test, "_running_java_under", return_value=[]):
                result = boot_test.run_boot_test(runtime_dir, ["demo_mod"], timeout=5, log_name="pass-case")
            self.assertEqual(result["status"], "PASS")
            self.assertTrue(result["restored"])
            self.assertTrue(Path(result["log"]).is_file())
            self.assertIsNotNone(result["triage"])
            data = json.loads((runtime_dir / "mods" / "enabled_mods.json").read_text(encoding="utf-8"))
            self.assertEqual(data["enabledMods"], ["existing_mod"])

    def test_suspect_fatal_dialog_when_alive_without_marker(self) -> None:
        with resolved_temp_dir() as directory:
            runtime_dir = _make_rig(Path(directory))
            _write_fake_launcher(runtime_dir, "import time\ntime.sleep(30)\n")
            with mock.patch.object(boot_test, "_running_java_under", return_value=[]):
                result = boot_test.run_boot_test(runtime_dir, ["demo_mod"], timeout=2, log_name="stuck-case")
            self.assertEqual(result["status"], "SUSPECT_FATAL_DIALOG")
            self.assertIn("Fatal", result["reason"])

    def test_fail_when_process_exits_early(self) -> None:
        with resolved_temp_dir() as directory:
            runtime_dir = _make_rig(Path(directory))
            _write_fake_launcher(runtime_dir, "print('booting')\n")
            with mock.patch.object(boot_test, "_running_java_under", return_value=[]):
                result = boot_test.run_boot_test(runtime_dir, ["demo_mod"], timeout=5, log_name="fail-case")
            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(result["restored"])

    def test_keep_mods_leaves_new_enabled_mods_in_place(self) -> None:
        with resolved_temp_dir() as directory:
            runtime_dir = _make_rig(Path(directory))
            _write_fake_launcher(runtime_dir, "print('booting')\n")
            with mock.patch.object(boot_test, "_running_java_under", return_value=[]):
                result = boot_test.run_boot_test(
                    runtime_dir, ["kept_mod"], timeout=5, log_name="keep-case", keep_mods=True
                )
            self.assertFalse(result["restored"])
            data = json.loads((runtime_dir / "mods" / "enabled_mods.json").read_text(encoding="utf-8"))
            self.assertEqual(data["enabledMods"], ["kept_mod"])


def _write_fixture_compat_sets(directory: Path) -> Path:
    data = {
        "schema_version": 1,
        "sets": {
            "libs": {
                "mods": {
                    "lib_a": {"name": "Lib A", "role": "lib", "gameVersion": "0.98a-RC8", "required_by": []},
                    "lib_b": {"name": "Lib B", "role": "lib", "gameVersion": "0.98a-RC8", "required_by": []},
                }
            },
            "standard": {
                "extends": ["libs"],
                "mods": {
                    "content_x": {"name": "Content X", "role": "content", "gameVersion": "0.98a-RC8", "required_by": []},
                },
            },
        },
    }
    path = directory / "fixture-compat-sets.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _write_target_mod_info(runtime_dir: Path, mod_id: str, dependency_ids: list[str]) -> None:
    mod_dir = runtime_dir / "mods" / mod_id
    mod_dir.mkdir(parents=True, exist_ok=True)
    (mod_dir / "mod_info.json").write_text(
        json.dumps({"id": mod_id, "dependencies": [{"id": dep} for dep in dependency_ids]}),
        encoding="utf-8",
    )


@unittest.skipUnless(sys.platform == "win32", "boot-test launches the rig's Windows .bat")
class BootMatrixTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_poll = boot_test.POLL_INTERVAL_SECONDS
        boot_test.POLL_INTERVAL_SECONDS = 0.2

    def tearDown(self) -> None:
        boot_test.POLL_INTERVAL_SECONDS = self._orig_poll

    def test_fails_only_with_pack_when_pack_only_id_triggers_failure(self) -> None:
        with resolved_temp_dir() as directory:
            root = Path(directory)
            runtime_dir = _make_rig(root)
            compat_sets_path = _write_fixture_compat_sets(root)
            # target_mod only declares lib_a as a dependency, so run (a) never enables content_x or lib_b.
            _write_target_mod_info(runtime_dir, "target_mod", ["lib_a"])
            _write_fake_launcher(
                runtime_dir,
                "import json, pathlib, time\n"
                "data = json.loads(pathlib.Path('mods/enabled_mods.json').read_text(encoding='utf-8'))\n"
                "if 'content_x' in data['enabledMods']:\n"
                "    print('boom')\n"
                "else:\n"
                "    print('Playing music with id [miscallenous_main_menu.ogg]')\n"
                "    time.sleep(30)\n",
            )
            with mock.patch.object(boot_test, "_running_java_under", return_value=[]):
                result = boot_test.run_boot_matrix(
                    runtime_dir, ["target_mod"], "standard", timeout=5, log_name="matrix-fail-with-pack", compat_sets_path=compat_sets_path
                )

            self.assertEqual(result["verdict"], "FAIL_WITH_PACK_ONLY")
            alone, with_pack = result["matrix"]
            self.assertEqual(alone["config"], "alone")
            self.assertEqual(alone["status"], "PASS")
            self.assertNotIn("content_x", alone["mods"])
            self.assertIn("lib_a", alone["mods"])
            self.assertEqual(with_pack["config"], "with_pack")
            self.assertEqual(with_pack["status"], "FAIL")
            self.assertIn("content_x", with_pack["mods"])

            # enabled_mods.json must be restored to its pre-matrix content.
            data = json.loads((runtime_dir / "mods" / "enabled_mods.json").read_text(encoding="utf-8"))
            self.assertEqual(data["enabledMods"], ["existing_mod"])

    def test_pass_pass_verdict_is_pass(self) -> None:
        with resolved_temp_dir() as directory:
            root = Path(directory)
            runtime_dir = _make_rig(root)
            compat_sets_path = _write_fixture_compat_sets(root)
            _write_target_mod_info(runtime_dir, "target_mod", ["lib_a"])
            _write_fake_launcher(
                runtime_dir,
                "import time\n"
                "print('Playing music with id [miscallenous_main_menu.ogg]')\n"
                "time.sleep(30)\n",
            )
            with mock.patch.object(boot_test, "_running_java_under", return_value=[]):
                result = boot_test.run_boot_matrix(
                    runtime_dir, ["target_mod"], "standard", timeout=5, log_name="matrix-pass-pass", compat_sets_path=compat_sets_path
                )
            self.assertEqual(result["verdict"], "PASS")
            self.assertEqual(result["matrix"][0]["status"], "PASS")
            self.assertEqual(result["matrix"][1]["status"], "PASS")

            data = json.loads((runtime_dir / "mods" / "enabled_mods.json").read_text(encoding="utf-8"))
            self.assertEqual(data["enabledMods"], ["existing_mod"])

    def test_fail_alone_short_circuits_verdict(self) -> None:
        with resolved_temp_dir() as directory:
            root = Path(directory)
            runtime_dir = _make_rig(root)
            compat_sets_path = _write_fixture_compat_sets(root)
            _write_target_mod_info(runtime_dir, "target_mod", ["lib_a"])
            _write_fake_launcher(runtime_dir, "print('booting')\n")
            with mock.patch.object(boot_test, "_running_java_under", return_value=[]):
                result = boot_test.run_boot_matrix(
                    runtime_dir, ["target_mod"], "standard", timeout=5, log_name="matrix-fail-alone", compat_sets_path=compat_sets_path
                )
            self.assertEqual(result["verdict"], "FAIL_ALONE")


if __name__ == "__main__":
    unittest.main()
