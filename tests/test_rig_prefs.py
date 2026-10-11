"""rig_prefs: the rig pins the shared launcher resolution and gives the owner's setting back (2026-10-11)."""
from __future__ import annotations

import unittest
from unittest import mock

from bridgeforge import rig_prefs


class PinnedPrefsTests(unittest.TestCase):
    def test_values_are_pinned_inside_and_the_owners_come_back_after_an_error(self) -> None:
        store = {"resolution": "2048x1152", "fullscreen": "true"}
        writes = []

        def read(names):
            return {n: store.get(n) for n in names}

        def write(values):
            writes.append(dict(values))
            for k, v in values.items():
                if v is None:
                    store.pop(k, None)
                else:
                    store[k] = v

        with mock.patch.object(rig_prefs, "read_prefs", side_effect=read), mock.patch.object(rig_prefs, "write_prefs", side_effect=write):
            with self.assertRaises(RuntimeError):
                with rig_prefs.pinned_launcher_prefs():
                    self.assertEqual(store, {"resolution": "1920x1440", "fullscreen": "false"})
                    raise RuntimeError("the game crashed")
        self.assertEqual(store, {"resolution": "2048x1152", "fullscreen": "true"})
        self.assertEqual(len(writes), 2)

    def test_an_absent_value_is_removed_again(self) -> None:
        store: dict[str, str] = {}

        def write(values):
            for k, v in values.items():
                if v is None:
                    store.pop(k, None)
                else:
                    store[k] = v

        with mock.patch.object(rig_prefs, "read_prefs", side_effect=lambda names: {n: store.get(n) for n in names}), \
                mock.patch.object(rig_prefs, "write_prefs", side_effect=write):
            with rig_prefs.pinned_launcher_prefs():
                self.assertIn("resolution", store)
        self.assertEqual(store, {})


if __name__ == "__main__":
    unittest.main()
