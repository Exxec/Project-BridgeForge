"""96.5 A4: one public module finds a mod's folder and reads its mod_info.json; the modules that had copies use it."""
from __future__ import annotations

import inspect
import unittest
from pathlib import Path

from bridgeforge import mod_files
from bridgeforge.mod_files import ModRootError, find_mod_root, nearest_mod_root, read_mod_info, workspace_or_mod_root
from tests.support import resolved_temp_dir


def _mod(folder: Path, text: str = '{"id": "m", "name": "M"}') -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "mod_info.json").write_bytes(text.encode("utf-8"))
    return folder


class ReadModInfoTests(unittest.TestCase):
    def test_lenient_json_missing_and_non_objects(self) -> None:
        with resolved_temp_dir() as root:
            self.assertEqual(read_mod_info(_mod(root / "a", '{"id": "a", # a comment\n "name": "A",}'))["id"], "a")
            self.assertIsNone(read_mod_info(root / "missing"))
            self.assertIsNone(read_mod_info(_mod(root / "list", "[1, 2]")))
            self.assertIsNone(read_mod_info(_mod(root / "broken", "{not json")))


class ModRootTests(unittest.TestCase):
    def test_the_folder_itself_or_its_only_child(self) -> None:
        with resolved_temp_dir() as root:
            self.assertEqual(find_mod_root(_mod(root / "direct")), (root / "direct").resolve())
            _mod(root / "wrapped" / "Inner")
            self.assertEqual(find_mod_root(root / "wrapped"), (root / "wrapped" / "Inner").resolve())
            self.assertEqual(nearest_mod_root(root / "wrapped"), root / "wrapped" / "Inner")

    def test_none_or_several_is_an_error_or_none(self) -> None:
        with resolved_temp_dir() as root:
            (root / "empty").mkdir()
            _mod(root / "two" / "A")
            _mod(root / "two" / "B")
            for folder, message in ((root / "empty", "No mod_info.json"), (root / "two", "ambiguous"), (root / "nowhere", "not an existing")):
                with self.subTest(folder=folder.name):
                    with self.assertRaisesRegex(ModRootError, message):
                        find_mod_root(folder)
                    self.assertIsNone(nearest_mod_root(folder))
            self.assertTrue(issubclass(ModRootError, ValueError))  # callers that caught ValueError still do

    def test_a_workspace_working_copy_comes_first(self) -> None:
        with resolved_temp_dir() as root:
            _mod(root / "ws")
            _mod(root / "ws" / "working")
            self.assertEqual(workspace_or_mod_root(root / "ws"), (root / "ws" / "working").resolve())
            self.assertEqual(workspace_or_mod_root(_mod(root / "plain")), (root / "plain").resolve())
            with self.assertRaisesRegex(ModRootError, "not a mod folder"):
                workspace_or_mod_root(root / "missing")


class CallersUseItTests(unittest.TestCase):
    def test_the_old_entry_points_keep_their_own_errors(self) -> None:
        from bridgeforge.prepare_test import PrepareTestError, _mod_root_for_sync
        from bridgeforge.value_proposals import ValueProposalError, mod_root
        from bridgeforge.vendor_plan import VendorPlanError, _mod_root

        with resolved_temp_dir() as root:
            for call, error in ((_mod_root_for_sync, PrepareTestError), (mod_root, ValueProposalError), (_mod_root, VendorPlanError)):
                with self.subTest(call=call.__name__), self.assertRaises(error):
                    call(root / "missing")

    def test_the_copies_are_gone(self) -> None:
        from bridgeforge import copy_drift, intake, mass_test, target_impact
        from bridgeforge.live import live_trust
        from bridgeforge.probe import probe_group

        from bridgeforge import prepare_test, value_proposals, vendor_plan

        self.assertIs(copy_drift._find_mod_root, mod_files.find_mod_root)
        delegates = {live_trust._mod_info: "read_mod_info", mass_test._mod_info: "read_mod_info",
                     probe_group._mod_info: "read_mod_info", target_impact._mod_info: "read_mod_info",
                     prepare_test._mod_root_for_sync: "find_mod_root", intake._mod_root_of: "nearest_mod_root",
                     value_proposals.mod_root: "workspace_or_mod_root", vendor_plan._mod_root: "workspace_or_mod_root"}
        for function, shared in delegates.items():
            with self.subTest(function=f"{function.__module__}.{function.__name__}"):
                source = inspect.getsource(function)
                self.assertIn(shared, source)
                self.assertNotIn('"mod_info.json"', source)  # no path of its own any more


if __name__ == "__main__":
    unittest.main()
