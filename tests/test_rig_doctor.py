from __future__ import annotations

import json
from contextlib import contextmanager
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bridgeforge.probe_mod_build import RELEASE_RELATIVE
from tests.support import link_dir
from bridgeforge.rig_doctor import (
    _check_path_locks,
    default_working_copies,
    rig_doctor,
)


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _make_mod(mods_dir: Path, folder_name: str, mod_id: str, **extra) -> Path:
    mod = mods_dir / folder_name
    mod.mkdir(parents=True, exist_ok=True)
    info = {"id": mod_id, "name": folder_name, "gameVersion": "0.98a-RC8"}
    info.update(extra)
    _write_json(mod / "mod_info.json", info)
    (mod / "data").mkdir(exist_ok=True)
    (mod / "data" / "file.txt").write_text("content", encoding="utf-8")
    return mod


def _junction(target: Path, link: Path) -> bool:
    """Link like a rig's starsector-core; True on success, False if this environment can't."""
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link_dir(target, link)
    except OSError:
        return False
    return True


def _make_isolated_rig(root: Path) -> Path | None:
    core_real = root / "core_real"
    core_real.mkdir(exist_ok=True)
    rig = root / "rig"
    (rig / "mods").mkdir(parents=True, exist_ok=True)
    if not _junction(core_real, rig / "starsector-core"):
        return None
    return rig


@contextmanager
def _patch_repo_root(repo_root: Path):
    # Machine process state is not part of these filesystem fixtures.
    with mock.patch("bridgeforge.rig_doctor._repo_root", return_value=repo_root), mock.patch(
        "bridgeforge.rig_doctor.who_locks", return_value={"processes": [], "limitations": []}
    ):
        yield


class IsolationCheckTests(unittest.TestCase):
    def test_lock_candidate_warns_without_stopping_process(self):
        with mock.patch("bridgeforge.rig_doctor.who_locks", return_value={
            "processes": [{"pid": 42, "name": "tail", "sources": ["cwd"]}], "limitations": []
        }):
            result = _check_path_locks(Path("fixture"))
        self.assertEqual(result["status"], "WARN")
        self.assertIn("pid 42", result["detail"])

    def test_fail_when_core_is_a_plain_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rig = root / "rig"
            (rig / "starsector-core").mkdir(parents=True)
            (rig / "mods").mkdir()
            with _patch_repo_root(root):
                result = rig_doctor(rig)
            check = next(c for c in result["checks"] if c["name"] == "isolation")
            self.assertEqual(check["status"], "FAIL")
            self.assertEqual(result["status"], "FAIL")

    def test_pass_when_core_is_a_junction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rig = _make_isolated_rig(root)
            if rig is None:
                self.skipTest("Could not create an NTFS junction in this environment.")
            with _patch_repo_root(root):
                result = rig_doctor(rig)
            check = next(c for c in result["checks"] if c["name"] == "isolation")
            self.assertEqual(check["status"], "PASS")


class GameNotRunningCheckTests(unittest.TestCase):
    def test_pass_when_nothing_running(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rig = _make_isolated_rig(root)
            if rig is None:
                self.skipTest("Could not create an NTFS junction in this environment.")
            with _patch_repo_root(root), mock.patch("bridgeforge.rig_doctor._running_java_under", return_value=[]):
                result = rig_doctor(rig)
            check = next(c for c in result["checks"] if c["name"] == "game_not_running")
            self.assertEqual(check["status"], "PASS")

    def test_warn_when_java_running_under_rig(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rig = _make_isolated_rig(root)
            if rig is None:
                self.skipTest("Could not create an NTFS junction in this environment.")
            with _patch_repo_root(root), mock.patch(
                "bridgeforge.rig_doctor._running_java_under",
                return_value=[{"pid": 4321, "exe": str(rig / "jre" / "java.exe")}],
            ):
                result = rig_doctor(rig)
            check = next(c for c in result["checks"] if c["name"] == "game_not_running")
            self.assertEqual(check["status"], "WARN")
            self.assertIn("4321", check["detail"])


class ProbeInstalledCheckTests(unittest.TestCase):
    def _repo_with_release(self, root: Path, content: str = "probe-content") -> Path:
        release_dir = root / RELEASE_RELATIVE
        release_dir.mkdir(parents=True)
        _write_json(release_dir / "mod_info.json", {"id": "bridgeforge-probe", "gameVersion": "0.98a-RC8"})
        (release_dir / "data").mkdir()
        (release_dir / "data" / "probe.txt").write_text(content, encoding="utf-8")
        return release_dir

    def test_fail_when_repo_release_copy_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rig = _make_isolated_rig(root)
            if rig is None:
                self.skipTest("Could not create an NTFS junction in this environment.")
            with _patch_repo_root(root), mock.patch("bridgeforge.rig_doctor._running_java_under", return_value=[]):
                result = rig_doctor(rig)
            check = next(c for c in result["checks"] if c["name"] == "probe_installed")
            self.assertEqual(check["status"], "FAIL")
            self.assertEqual(result["status"], "FAIL")

    def test_warn_when_probe_not_installed_in_rig(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rig = _make_isolated_rig(root)
            if rig is None:
                self.skipTest("Could not create an NTFS junction in this environment.")
            self._repo_with_release(root)
            with _patch_repo_root(root), mock.patch("bridgeforge.rig_doctor._running_java_under", return_value=[]):
                result = rig_doctor(rig)
            check = next(c for c in result["checks"] if c["name"] == "probe_installed")
            self.assertEqual(check["status"], "WARN")
            self.assertIn("probe-config", check["detail"])
            self.assertIn("--install", check["detail"])

    def test_warn_when_probe_drifted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rig = _make_isolated_rig(root)
            if rig is None:
                self.skipTest("Could not create an NTFS junction in this environment.")
            self._repo_with_release(root, content="new-content")
            rig_probe = rig / "mods" / "bridgeforge-probe"
            rig_probe.mkdir(parents=True)
            _write_json(rig_probe / "mod_info.json", {"id": "bridgeforge-probe", "gameVersion": "0.98a-RC8"})
            (rig_probe / "data").mkdir()
            (rig_probe / "data" / "probe.txt").write_text("old-content", encoding="utf-8")
            with _patch_repo_root(root), mock.patch("bridgeforge.rig_doctor._running_java_under", return_value=[]):
                result = rig_doctor(rig)
            check = next(c for c in result["checks"] if c["name"] == "probe_installed")
            self.assertEqual(check["status"], "WARN")
            self.assertIn("drift", check["detail"])

    def test_pass_when_probe_matches(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rig = _make_isolated_rig(root)
            if rig is None:
                self.skipTest("Could not create an NTFS junction in this environment.")
            self._repo_with_release(root, content="same-content")
            rig_probe = rig / "mods" / "bridgeforge-probe"
            rig_probe.mkdir(parents=True)
            _write_json(rig_probe / "mod_info.json", {"id": "bridgeforge-probe", "gameVersion": "0.98a-RC8"})
            (rig_probe / "data").mkdir()
            (rig_probe / "data" / "probe.txt").write_text("same-content", encoding="utf-8")
            with _patch_repo_root(root), mock.patch("bridgeforge.rig_doctor._running_java_under", return_value=[]):
                result = rig_doctor(rig)
            check = next(c for c in result["checks"] if c["name"] == "probe_installed")
            self.assertEqual(check["status"], "PASS")


class EnabledModsResolveCheckTests(unittest.TestCase):
    def test_fail_when_enabled_id_has_no_folder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rig = _make_isolated_rig(root)
            if rig is None:
                self.skipTest("Could not create an NTFS junction in this environment.")
            mods_dir = rig / "mods"
            _make_mod(mods_dir, "Known", "known_id")
            _write_json(mods_dir / "enabled_mods.json", {"enabledMods": ["known_id", "ghost_id"]})
            with _patch_repo_root(root), mock.patch("bridgeforge.rig_doctor._running_java_under", return_value=[]):
                result = rig_doctor(rig)
            check = next(c for c in result["checks"] if c["name"] == "enabled_mods_resolve")
            self.assertEqual(check["status"], "FAIL")
            self.assertIn("ghost_id", check["detail"])
            self.assertEqual(result["status"], "FAIL")

    def test_warn_on_missing_dependency_and_game_version_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rig = _make_isolated_rig(root)
            if rig is None:
                self.skipTest("Could not create an NTFS junction in this environment.")
            mods_dir = rig / "mods"
            _make_mod(mods_dir, "Needs", "needs_id", dependencies=[{"id": "missing_lib"}])
            _make_mod(mods_dir, "OldVer", "old_ver_id", gameVersion="0.97a")
            _write_json(mods_dir / "enabled_mods.json", {"enabledMods": ["needs_id", "old_ver_id"]})
            with _patch_repo_root(root), mock.patch("bridgeforge.rig_doctor._running_java_under", return_value=[]):
                result = rig_doctor(rig)
            check = next(c for c in result["checks"] if c["name"] == "enabled_mods_resolve")
            self.assertEqual(check["status"], "WARN")
            self.assertIn("missing_lib", check["detail"])
            self.assertIn("old_ver_id", check["detail"])

    def test_pass_when_everything_resolves(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rig = _make_isolated_rig(root)
            if rig is None:
                self.skipTest("Could not create an NTFS junction in this environment.")
            mods_dir = rig / "mods"
            _make_mod(mods_dir, "Lib", "lib_id")
            _make_mod(mods_dir, "Content", "content_id", dependencies=[{"id": "lib_id"}])
            _write_json(mods_dir / "enabled_mods.json", {"enabledMods": ["lib_id", "content_id"]})
            with _patch_repo_root(root), mock.patch("bridgeforge.rig_doctor._running_java_under", return_value=[]):
                result = rig_doctor(rig)
            check = next(c for c in result["checks"] if c["name"] == "enabled_mods_resolve")
            self.assertEqual(check["status"], "PASS")

    def test_pass_when_missing_file_but_no_mod_workspaces_exist(self) -> None:
        """A freshly registered P10 reference rig has no mods enabled yet, so enabled_mods.json
        legitimately does not exist - that is not a configuration problem (ROADMAP P14 item 22,
        found 2026-09-20/21 registering a real 0.9a reference rig)."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rig = _make_isolated_rig(root)
            if rig is None:
                self.skipTest("Could not create an NTFS junction in this environment.")
            (rig / "mods").mkdir(exist_ok=True)
            with _patch_repo_root(root), mock.patch("bridgeforge.rig_doctor._running_java_under", return_value=[]):
                result = rig_doctor(rig)
            check = next(c for c in result["checks"] if c["name"] == "enabled_mods_resolve")
            self.assertEqual(check["status"], "PASS")
            self.assertIn("no mod workspaces", check["detail"])

    def test_fail_when_missing_file_and_mod_workspaces_exist(self) -> None:
        """The missing-file leniency above must not swallow the real problem: a mods folder that
        does hold workspaces but nothing declares any of them enabled."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rig = _make_isolated_rig(root)
            if rig is None:
                self.skipTest("Could not create an NTFS junction in this environment.")
            mods_dir = rig / "mods"
            _make_mod(mods_dir, "Known", "known_id")
            with _patch_repo_root(root), mock.patch("bridgeforge.rig_doctor._running_java_under", return_value=[]):
                result = rig_doctor(rig)
            check = next(c for c in result["checks"] if c["name"] == "enabled_mods_resolve")
            self.assertEqual(check["status"], "FAIL")
            self.assertIn("not found", check["detail"])

    def test_lenient_mod_info_with_hash_comments_and_unquoted_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rig = _make_isolated_rig(root)
            if rig is None:
                self.skipTest("Could not create an NTFS junction in this environment.")
            mods_dir = rig / "mods"
            mod = mods_dir / "Lenient"
            mod.mkdir(parents=True)
            (mod / "mod_info.json").write_text(
                "{\n"
                "  # a comment\n"
                "  id: \"lenient_id\",\n"
                "  gameVersion: '0.98a-RC8',\n"
                "}\n",
                encoding="utf-8",
            )
            (mod / "data").mkdir()
            (mod / "data" / "file.txt").write_text("x", encoding="utf-8")
            _write_json(mods_dir / "enabled_mods.json", {"enabledMods": ["lenient_id"]})
            with _patch_repo_root(root), mock.patch("bridgeforge.rig_doctor._running_java_under", return_value=[]):
                result = rig_doctor(rig)
            check = next(c for c in result["checks"] if c["name"] == "enabled_mods_resolve")
            self.assertEqual(check["status"], "PASS")


class WorkingCopyDriftCheckTests(unittest.TestCase):
    def test_skipped_when_no_working_copies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rig = _make_isolated_rig(root)
            if rig is None:
                self.skipTest("Could not create an NTFS junction in this environment.")
            with _patch_repo_root(root), mock.patch("bridgeforge.rig_doctor._running_java_under", return_value=[]):
                result = rig_doctor(rig)
            check = next(c for c in result["checks"] if c["name"] == "working_copy_drift")
            self.assertEqual(check["status"], "SKIPPED")

    def test_pass_when_identical(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rig = _make_isolated_rig(root)
            if rig is None:
                self.skipTest("Could not create an NTFS junction in this environment.")
            _make_mod(rig / "mods", "Content", "content_id")
            working = root / "working" / "Content"
            working.mkdir(parents=True)
            _write_json(working / "mod_info.json", {"id": "content_id", "name": "Content", "gameVersion": "0.98a-RC8"})
            (working / "data").mkdir()
            (working / "data" / "file.txt").write_text("content", encoding="utf-8")
            with _patch_repo_root(root), mock.patch("bridgeforge.rig_doctor._running_java_under", return_value=[]):
                result = rig_doctor(rig, working_copies={"content_id": working})
            check = next(c for c in result["checks"] if c["name"] == "working_copy_drift")
            self.assertEqual(check["status"], "PASS", check["detail"])

    def test_warn_on_drift_with_fix_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()  # CI temp dirs are 8.3 short paths; the detail uses resolved ones
            rig = _make_isolated_rig(root)
            if rig is None:
                self.skipTest("Could not create an NTFS junction in this environment.")
            rig_mod = _make_mod(rig / "mods", "Content", "content_id")
            working = root / "working" / "Content"
            working.mkdir(parents=True)
            _write_json(working / "mod_info.json", {"id": "content_id", "gameVersion": "0.98a-RC8"})
            (working / "data").mkdir()
            (working / "data" / "file.txt").write_text("different-content", encoding="utf-8")
            with _patch_repo_root(root), mock.patch("bridgeforge.rig_doctor._running_java_under", return_value=[]):
                result = rig_doctor(rig, working_copies={"content_id": working})
            check = next(c for c in result["checks"] if c["name"] == "working_copy_drift")
            self.assertEqual(check["status"], "WARN")
            self.assertIn("prepare-test", check["detail"])
            self.assertIn(str(working), check["detail"])
            self.assertIn(str(rig_mod), check["detail"])

    def test_fail_when_id_not_present_in_rig(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rig = _make_isolated_rig(root)
            if rig is None:
                self.skipTest("Could not create an NTFS junction in this environment.")
            working = root / "working" / "Ghost"
            working.mkdir(parents=True)
            _write_json(working / "mod_info.json", {"id": "ghost_id", "gameVersion": "0.98a-RC8"})
            (working / "data").mkdir()
            (working / "data" / "file.txt").write_text("content", encoding="utf-8")
            with _patch_repo_root(root), mock.patch("bridgeforge.rig_doctor._running_java_under", return_value=[]):
                result = rig_doctor(rig, working_copies={"ghost_id": working})
            check = next(c for c in result["checks"] if c["name"] == "working_copy_drift")
            self.assertEqual(check["status"], "FAIL")

    def test_pass_when_rig_folder_is_a_link_to_working_copy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rig = _make_isolated_rig(root)
            if rig is None:
                self.skipTest("Could not create an NTFS junction in this environment.")
            working = _make_mod(root / "working_root", "Content", "content_id")
            linked_rig_mod = rig / "mods" / "Content"
            if not _junction(working, linked_rig_mod):
                self.skipTest("Could not create an NTFS junction in this environment.")
            with _patch_repo_root(root), mock.patch("bridgeforge.rig_doctor._running_java_under", return_value=[]):
                result = rig_doctor(rig, working_copies={"content_id": working})
            check = next(c for c in result["checks"] if c["name"] == "working_copy_drift")
            self.assertEqual(check["status"], "PASS")
            self.assertIn("same folder", check["detail"])


class RealInstallSavesCheckTests(unittest.TestCase):
    def test_skipped_when_no_real_install(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rig = _make_isolated_rig(root)
            if rig is None:
                self.skipTest("Could not create an NTFS junction in this environment.")
            with _patch_repo_root(root), mock.patch("bridgeforge.rig_doctor._running_java_under", return_value=[]):
                result = rig_doctor(rig)
            check = next(c for c in result["checks"] if c["name"] == "real_install_saves_untouched")
            self.assertEqual(check["status"], "SKIPPED")

    def test_skipped_when_no_baseline_yet(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rig = _make_isolated_rig(root)
            if rig is None:
                self.skipTest("Could not create an NTFS junction in this environment.")
            real_install = root / "real_install"
            (real_install / "saves" / "MySave").mkdir(parents=True)
            (real_install / "saves" / "MySave" / "campaign.xml").write_text("<x/>", encoding="utf-8")
            with _patch_repo_root(root), mock.patch("bridgeforge.rig_doctor._running_java_under", return_value=[]):
                result = rig_doctor(rig, real_install=real_install)
            check = next(c for c in result["checks"] if c["name"] == "real_install_saves_untouched")
            self.assertEqual(check["status"], "SKIPPED")
            self.assertIn("baseline", check["detail"])
            self.assertEqual(result["status"], "FAIL")  # isolation/probe checks still fail in this minimal rig

    def test_write_then_compare_unchanged_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rig = _make_isolated_rig(root)
            if rig is None:
                self.skipTest("Could not create an NTFS junction in this environment.")
            real_install = root / "real_install"
            (real_install / "saves" / "MySave").mkdir(parents=True)
            (real_install / "saves" / "MySave" / "campaign.xml").write_text("<x/>", encoding="utf-8")
            baseline_path = root / "state" / "baseline.json"

            with _patch_repo_root(root), mock.patch("bridgeforge.rig_doctor._running_java_under", return_value=[]):
                write_result = rig_doctor(
                    rig, real_install=real_install, saves_baseline=baseline_path, write_saves_baseline=True
                )
            write_check = next(c for c in write_result["checks"] if c["name"] == "real_install_saves_untouched")
            self.assertEqual(write_check["status"], "PASS")
            self.assertTrue(baseline_path.is_file())

            with _patch_repo_root(root), mock.patch("bridgeforge.rig_doctor._running_java_under", return_value=[]):
                compare_result = rig_doctor(rig, real_install=real_install, saves_baseline=baseline_path)
            compare_check = next(c for c in compare_result["checks"] if c["name"] == "real_install_saves_untouched")
            self.assertEqual(compare_check["status"], "PASS")

    def test_tamper_after_baseline_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rig = _make_isolated_rig(root)
            if rig is None:
                self.skipTest("Could not create an NTFS junction in this environment.")
            real_install = root / "real_install"
            (real_install / "saves" / "MySave").mkdir(parents=True)
            (real_install / "saves" / "MySave" / "campaign.xml").write_text("<x/>", encoding="utf-8")
            baseline_path = root / "state" / "baseline.json"

            with _patch_repo_root(root), mock.patch("bridgeforge.rig_doctor._running_java_under", return_value=[]):
                rig_doctor(rig, real_install=real_install, saves_baseline=baseline_path, write_saves_baseline=True)

            # Simulate a rig accidentally writing into the real install's saves.
            (real_install / "saves" / "MySave" / "campaign.xml").write_text("<tampered/>", encoding="utf-8")

            with _patch_repo_root(root), mock.patch("bridgeforge.rig_doctor._running_java_under", return_value=[]):
                result = rig_doctor(rig, real_install=real_install, saves_baseline=baseline_path)
            check = next(c for c in result["checks"] if c["name"] == "real_install_saves_untouched")
            self.assertEqual(check["status"], "FAIL")
            self.assertIn("changed", check["detail"])
            self.assertEqual(result["status"], "FAIL")

    def test_tamper_added_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rig = _make_isolated_rig(root)
            if rig is None:
                self.skipTest("Could not create an NTFS junction in this environment.")
            real_install = root / "real_install"
            (real_install / "saves" / "MySave").mkdir(parents=True)
            (real_install / "saves" / "MySave" / "campaign.xml").write_text("<x/>", encoding="utf-8")
            baseline_path = root / "state" / "baseline.json"

            with _patch_repo_root(root), mock.patch("bridgeforge.rig_doctor._running_java_under", return_value=[]):
                rig_doctor(rig, real_install=real_install, saves_baseline=baseline_path, write_saves_baseline=True)

            (real_install / "saves" / "NewSave").mkdir(parents=True)
            (real_install / "saves" / "NewSave" / "campaign.xml").write_text("<new/>", encoding="utf-8")

            with _patch_repo_root(root), mock.patch("bridgeforge.rig_doctor._running_java_under", return_value=[]):
                result = rig_doctor(rig, real_install=real_install, saves_baseline=baseline_path)
            check = next(c for c in result["checks"] if c["name"] == "real_install_saves_untouched")
            self.assertEqual(check["status"], "FAIL")
            self.assertIn("added", check["detail"])


class OverallStatusTests(unittest.TestCase):
    def test_pass_when_every_check_passes_or_skips(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rig = _make_isolated_rig(root)
            if rig is None:
                self.skipTest("Could not create an NTFS junction in this environment.")
            release_dir = root / RELEASE_RELATIVE
            release_dir.mkdir(parents=True)
            _write_json(release_dir / "mod_info.json", {"id": "bridgeforge-probe", "gameVersion": "0.98a-RC8"})
            (release_dir / "data").mkdir()
            (release_dir / "data" / "probe.txt").write_text("content", encoding="utf-8")
            rig_probe = rig / "mods" / "bridgeforge-probe"
            rig_probe.mkdir(parents=True)
            _write_json(rig_probe / "mod_info.json", {"id": "bridgeforge-probe", "gameVersion": "0.98a-RC8"})
            (rig_probe / "data").mkdir()
            (rig_probe / "data" / "probe.txt").write_text("content", encoding="utf-8")
            _write_json(rig / "mods" / "enabled_mods.json", {"enabledMods": []})

            with _patch_repo_root(root), mock.patch("bridgeforge.rig_doctor._running_java_under", return_value=[]):
                result = rig_doctor(rig)
            self.assertEqual(result["status"], "PASS")
            for check in result["checks"]:
                self.assertIn(check["status"], ("PASS", "SKIPPED"))


class DefaultWorkingCopiesTests(unittest.TestCase):
    def test_discovers_working_copies_by_layout_convention(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_json(root / "In operation" / "Flu-X" / "working" / "mod_info.json", {"id": "infected"})
            _write_json(root / "In operation" / "Flu-X" / "scratch" / "old" / "mod_info.json", {"id": "infected_old"})
            _write_json(root / "In operation" / "_rig" / "mods" / "X" / "mod_info.json", {"id": "rig_only"})
            _write_json(root / "Done" / "SEEKER" / "SEEKER-0.98a" / "mod_info.json", {"id": "SEEKER"})
            _write_json(root / "Done" / "SEEKER" / "original" / "Old SEEKER" / "mod_info.json", {"id": "SEEKER"})
            _write_json(root / "Done" / "SEEKER" / "workspace" / "mod_info.json", {"id": "seeker_ws"})
            # A finished mod still under re-test: the In operation working copy wins over Done's release.
            _write_json(root / "Done" / "Flu-X" / "Flu-X-0.98a" / "mod_info.json", {"id": "infected"})

            found = default_working_copies(root)
            self.assertEqual(set(found), {"infected", "SEEKER"})
            self.assertEqual(found["infected"], root / "In operation" / "Flu-X" / "working")
            self.assertEqual(found["SEEKER"], root / "Done" / "SEEKER" / "SEEKER-0.98a")

    def test_empty_when_nothing_exists(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            found = default_working_copies(Path(directory))
            self.assertEqual(found, {})


if __name__ == "__main__":
    unittest.main()
