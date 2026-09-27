import unittest
import ctypes
from ctypes import wintypes
import os
import subprocess
import sys
import types
from unittest.mock import patch

from bridgeforge.locks import _inside, _process_paths, _restart_manager, who_locks
from tests.support import resolved_temp_dir


class LockTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "requires Windows Restart Manager")
    def test_restart_manager_identifies_exclusive_file_owner(self):
        with resolved_temp_dir() as root:
            file = root / "locked.log"
            file.write_text("fixture", encoding="utf-8")
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
            kernel.CreateFileW.restype = wintypes.HANDLE
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            handle = kernel.CreateFileW(str(file), 0x80000000, 0, None, 3, 0x80, None)
            self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
            try:
                self.assertIn(os.getpid(), [p["pid"] for p in _restart_manager([file])])
            finally:
                kernel.CloseHandle(handle)

    def test_merges_sources_and_reports_limitations(self):
        with resolved_temp_dir() as root:
            with patch("bridgeforge.locks._process_paths", return_value=([
                {"pid": 42, "name": "tail", "sources": ["cwd"], "watcher_candidate": True}], [])), patch(
                "bridgeforge.locks._restart_manager", return_value=[
                    {"pid": 42, "name": "tail", "sources": ["restart_manager"]}]):
                result = who_locks(root)
            self.assertEqual(result["status"], "FOUND")
            self.assertEqual(result["processes"][0]["sources"], ["cwd", "restart_manager"])
            self.assertTrue(result["processes"][0]["watcher_candidate"])
            self.assertTrue(result["limitations"])

    def test_unavailable_checks_are_not_claimed_clear(self):
        with resolved_temp_dir() as root:
            with patch("bridgeforge.locks._process_paths", return_value=([], ["denied"])), patch(
                "bridgeforge.locks._restart_manager", side_effect=OSError("unsupported")):
                result = who_locks(root)
            self.assertEqual(result["status"], "NO_PROCESS_FOUND")
            self.assertIn("unsupported", result["limitations"])

    def test_containment_is_not_string_prefix(self):
        with resolved_temp_dir() as root:
            self.assertTrue(_inside(str(root / "child"), root))
            self.assertFalse(_inside(str(root.parent / (root.name + "-other")), root))


try:
    import psutil
except ImportError:  # pragma: no cover - psutil is a declared dependency
    psutil = None


@unittest.skipIf(psutil is None, "psutil not installed")
class LiveProcessPathTests(unittest.TestCase):
    """_process_paths against real processes: the cwd and open-file checks rig-doctor relies on."""

    def test_child_with_cwd_inside_target_is_found(self):
        with resolved_temp_dir() as root:
            inner = root / "logs"
            inner.mkdir()
            child = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.read()"],
                                     cwd=inner, stdin=subprocess.PIPE)
            try:
                found, _ = _process_paths(root)
            finally:
                child.communicate(b"")
            match = [item for item in found if item["pid"] == child.pid]
            self.assertEqual(len(match), 1, found)
            self.assertIn("cwd", match[0]["sources"])
            self.assertFalse(match[0]["watcher_candidate"])

    def test_own_open_file_inside_target_is_found(self):
        with resolved_temp_dir() as root:
            path = root / "starsector.log"
            with path.open("w", encoding="utf-8") as handle:
                handle.write("fixture")
                handle.flush()
                found, _ = _process_paths(root)
            mine = [item for item in found if item["pid"] == os.getpid()]
            self.assertEqual(len(mine), 1, found)
            self.assertEqual(mine[0]["sources"], ["open_file"])

    def test_sibling_folder_is_not_matched(self):
        with resolved_temp_dir() as base:
            target, sibling = base / "rig", base / "rig-other"
            target.mkdir()
            sibling.mkdir()
            with (sibling / "x.log").open("w", encoding="utf-8"):
                found, _ = _process_paths(target)
            self.assertNotIn(os.getpid(), [item["pid"] for item in found])


class _Denied(Exception):
    pass


class _Gone(Exception):
    pass


class _FakeProcess:
    def __init__(self, pid, cwd, files=(), name="python", cmdline=(), deny=()):
        self.pid, self._cwd, self._files = pid, cwd, list(files)
        self._name, self._cmdline, self._deny = name, list(cmdline), set(deny)

    def _check(self, what):
        if what in self._deny:
            raise _Denied()

    def cwd(self):
        self._check("cwd")
        return self._cwd

    def open_files(self):
        self._check("open_files")
        return [types.SimpleNamespace(path=path) for path in self._files]

    def name(self):
        self._check("name")
        return self._name

    def cmdline(self):
        return self._cmdline


def _fake_psutil(processes):
    return types.SimpleNamespace(process_iter=lambda: iter(processes), AccessDenied=_Denied, NoSuchProcess=_Gone)


class ProcessPathBranchTests(unittest.TestCase):
    def test_missing_psutil_is_a_limitation_not_a_clean_result(self):
        with resolved_temp_dir() as root, patch.dict(sys.modules, {"psutil": None}):
            found, limitations = _process_paths(root)
        self.assertEqual(found, [])
        self.assertIn("psutil unavailable", limitations[0])

    def test_denied_queries_are_counted_and_watchers_flagged(self):
        with resolved_temp_dir() as root:
            outside = str(root.parent)
            processes = [
                _FakeProcess(1, str(root), name="tail"),
                _FakeProcess(2, outside, cmdline=["powershell", "Get-Content", str(root / "a.log"), "-Wait"],
                             files=[str(root / "a.log")], name="powershell.exe"),
                _FakeProcess(3, outside, deny={"cwd", "open_files"}),
                _FakeProcess(4, str(root), deny={"name"}),
            ]
            with patch.dict(sys.modules, {"psutil": _fake_psutil(processes)}):
                found, limitations = _process_paths(root)
        by_pid = {item["pid"]: item for item in found}
        self.assertEqual(sorted(by_pid), [1, 2, 4])
        self.assertTrue(by_pid[1]["watcher_candidate"])
        self.assertEqual(by_pid[2]["sources"], ["open_file"])
        self.assertTrue(by_pid[2]["watcher_candidate"])
        self.assertEqual(by_pid[4]["name"], "unknown")
        self.assertEqual(limitations, ["2 process queries denied; absence of results is not proof of no locks"])

    def test_missing_target_is_refused(self):
        with resolved_temp_dir() as root:
            with self.assertRaises(ValueError):
                who_locks(root / "absent")
