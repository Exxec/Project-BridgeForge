from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.cli import main
from bridgeforge.diff_data import diff_data


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class DiffDataTests(unittest.TestCase):
    """ROADMAP P14 item 19: value-diff, not a line diff. Found building E11's Rebal rebuild plan:
    a real historical vanilla reference and current RC8 use different key order and formatting
    (pretty-printed vs. commented blocks), so a plain text diff is swamped by noise.
    """

    def test_formatting_and_key_order_differences_produce_no_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "a.json", '{\n  # a comment\n  "b": 2,\n  "a": 1,\n}\n')
            _write(root / "b.json", '{"a": 1, "b": 2}')
            result = diff_data(root / "a.json", root / "b.json")
        self.assertEqual(result["status"], "IDENTICAL")
        self.assertEqual(result["changes"], [])

    def test_a_changed_scalar_field_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "a.json", '{"hitpoints": 100, "id": "x"}')
            _write(root / "b.json", '{"hitpoints": 150, "id": "x"}')
            result = diff_data(root / "a.json", root / "b.json")
        self.assertEqual(result["status"], "DIFFERENT")
        self.assertEqual(result["changes"], [{"path": "hitpoints", "kind": "changed", "a": 100, "b": 150}])

    def test_added_and_removed_fields_are_distinguished(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "a.json", '{"old_field": 1, "shared": true}')
            _write(root / "b.json", '{"new_field": 2, "shared": true}')
            result = diff_data(root / "a.json", root / "b.json")
        kinds = {c["path"]: c["kind"] for c in result["changes"]}
        self.assertEqual(kinds, {"old_field": "removed", "new_field": "added"})

    def test_nested_dict_field_is_diffed_at_its_own_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "a.json", '{"weaponSlots": {"WS001": {"angle": 0, "arc": 90}}}')
            _write(root / "b.json", '{"weaponSlots": {"WS001": {"angle": 0, "arc": 120}}}')
            result = diff_data(root / "a.json", root / "b.json")
        self.assertEqual(result["changes"], [{"path": "weaponSlots.WS001.arc", "kind": "changed", "a": 90, "b": 120}])

    def test_same_length_list_diffed_by_index(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "a.json", '{"tags": ["a", "b", "c"]}')
            _write(root / "b.json", '{"tags": ["a", "x", "c"]}')
            result = diff_data(root / "a.json", root / "b.json")
        self.assertEqual(result["changes"], [{"path": "tags[1]", "kind": "changed", "a": "b", "b": "x"}])

    def test_different_length_list_is_one_whole_value_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "a.json", '{"tags": ["a", "b"]}')
            _write(root / "b.json", '{"tags": ["a", "b", "c"]}')
            result = diff_data(root / "a.json", root / "b.json")
        self.assertEqual(result["changes"], [{"path": "tags", "kind": "changed", "a": ["a", "b"], "b": ["a", "b", "c"]}])

    def test_cli_reports_identical_and_different(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "a.json", '{"x": 1}')
            _write(root / "b.json", '{"x": 1}')
            _write(root / "c.json", '{"x": 2}')
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                exit_code = main(["diff-data-local", str(root / "a.json"), str(root / "b.json"), "--json"])
            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(out.getvalue())["status"], "IDENTICAL")

            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                exit_code = main(["diff-data-local", str(root / "a.json"), str(root / "c.json"), "--json"])
            self.assertEqual(exit_code, 0)
            payload = json.loads(out.getvalue())
            self.assertEqual(payload["status"], "DIFFERENT")
            self.assertEqual(payload["changes"], [{"path": "x", "kind": "changed", "a": 1, "b": 2}])


if __name__ == "__main__":
    unittest.main()
