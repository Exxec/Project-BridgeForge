import unittest
import ctypes
from ctypes import wintypes
import os
from unittest.mock import patch

from bridgeforge.locks import _inside, _restart_manager, who_locks
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
