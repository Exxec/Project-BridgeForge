from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from bridgeforge.cli import main
from bridgeforge.data_diff import DataDiffError, diff_data
from tests.support import resolved_temp_dir

# The same .wpn twice: a vanilla-style pretty-printed copy and a mod's reordered, commented,
# trailing-comma copy that changes exactly one value (the E11/Rebal situation, ROADMAP P14 item 19).
VANILLA_WPN = """{
    "id":"lightmg",
    "specClass":"projectile",
    "type":"BALLISTIC",
    "size":"SMALL",
    "turretOffsets":[10, -2.5, 10, 2.5],
    "renderHints":[RENDER_BARREL_BELOW],
    "damage":{"amount":25, "type":"KINETIC"},
    "tags":["pd", "kinetic"]
}"""
MOD_WPN = """# modded light machine gun
{"tags":["kinetic","pd",],   # same tags, other order
 "size":"SMALL", "type":"BALLISTIC",
 "damage":{"type":"KINETIC","amount":30.0},
 "turretOffsets":[10.0, -2.5, 10, 2.5],
 "renderHints":[RENDER_BARREL_BELOW],
 "specClass":"projectile", "id":"lightmg",}
"""


def _write(root: Path, name: str, text: str) -> Path:
    path = root / name
    path.write_text(text, encoding="utf-8")
    return path


class JsonDialectTests(unittest.TestCase):
    def test_formatting_order_and_comments_are_not_differences(self):
        with resolved_temp_dir() as root:
            a = _write(root, "a.wpn", VANILLA_WPN)
            b = _write(root, "b.wpn", MOD_WPN.replace('"amount":30.0', '"amount":25.0').replace('["kinetic","pd",]', '["pd","kinetic",]'))
            result = diff_data(a, b)
        self.assertTrue(result["identical"], result["changes"])

    def test_the_one_real_change_is_reported(self):
        with resolved_temp_dir() as root:
            result = diff_data(_write(root, "a.wpn", VANILLA_WPN), _write(root, "b.wpn", MOD_WPN))
        self.assertEqual(result["changes"], [
            {"path": "damage.amount", "change": "changed", "a": 25, "b": 30.0},
            {"path": "tags", "change": "reordered", "a": ["pd", "kinetic"], "b": ["kinetic", "pd"]},
        ])

    def test_keys_slots_by_id_and_scalar_lists_by_content(self):
        a = {"hullId": "x", "weaponSlots": [{"id": "WS 001", "type": "ENERGY"}, {"id": "WS 002", "type": "MISSILE"}],
             "builtInMods": ["a", "b"], "color": [255, 0, 0, 255], "gone": 1}
        b = {"hullId": "x", "weaponSlots": [{"id": "WS 003", "type": "BALLISTIC"}, {"id": "WS 001", "type": "BALLISTIC"}],
             "builtInMods": ["b", "c", "a"], "color": [255, 0, 10, 255], "new": True}
        with resolved_temp_dir() as root:
            result = diff_data(_write(root, "a.ship", json.dumps(a)), _write(root, "b.ship", json.dumps(b)))
        self.assertEqual(result["changes"], [
            {"path": "weaponSlots[id=WS 001].type", "change": "changed", "a": "ENERGY", "b": "BALLISTIC"},
            {"path": "weaponSlots[id=WS 002]", "change": "removed", "a": {"id": "WS 002", "type": "MISSILE"}},
            {"path": "weaponSlots[id=WS 003]", "change": "added", "b": {"id": "WS 003", "type": "BALLISTIC"}},
            {"path": "builtInMods[]", "change": "added", "b": "c"},
            {"path": "color[2]", "change": "changed", "a": 0, "b": 10},
            {"path": "gone", "change": "removed", "a": 1},
            {"path": "new", "change": "added", "b": True},
        ])

    def test_booleans_are_not_numbers_and_types_matter(self):
        with resolved_temp_dir() as root:
            result = diff_data(_write(root, "a.json", '{"x": true, "y": "1", "z": [1, 2]}'),
                               _write(root, "b.json", '{"x": 1, "y": 1, "z": [1, 2, 2]}'))
        self.assertEqual([c["path"] for c in result["changes"]], ["x", "y", "z[]"])
        self.assertEqual(result["changes"][2], {"path": "z[]", "change": "added", "b": 2})


class CsvTests(unittest.TestCase):
    def test_rows_by_id_columns_by_name_numbers_by_value(self):
        vanilla = "name,id,range,tags\nLight MG,lightmg,500,pd\n#comment,#x,1,\nVulcan,vulcan,300,pd\n,,,\n"
        mod = "id,name,range,tags,extra\nvulcan,Vulcan,300.0,pd,\nlightmg,Light MG,600,pd,\nnewgun,New,100,,x\n"
        with resolved_temp_dir() as root:
            result = diff_data(_write(root, "a.csv", vanilla), _write(root, "b.csv", mod))
        self.assertEqual(result["kind"], "csv")
        self.assertEqual(result["changes"], [
            {"path": "column extra", "change": "added", "b": "extra"},
            {"path": "[lightmg].range", "change": "changed", "a": "500", "b": "600"},
            {"path": "[newgun]", "change": "added", "b": {"id": "newgun", "name": "New", "range": "100", "tags": "", "extra": "x"}},
        ])

    def test_first_column_is_the_key_without_an_id_column_and_duplicates_stay_visible(self):
        with resolved_temp_dir() as root:
            result = diff_data(_write(root, "a.csv", "type,freq\nstar_red,1\nstar_red,2\n"),
                               _write(root, "b.csv", "type,freq\nstar_red,1\nstar_red,3\n"))
        self.assertEqual(result["changes"], [{"path": "[star_red#2].freq", "change": "changed", "a": "2", "b": "3"}])

    def test_header_only_file_still_reports_its_columns(self):
        with resolved_temp_dir() as root:
            result = diff_data(_write(root, "a.csv", "id,a\n"), _write(root, "b.csv", "id,b\n"))
        self.assertEqual([c["path"] for c in result["changes"]], ["column a", "column b"])


class ErrorAndCliTests(unittest.TestCase):
    def test_unreadable_or_mismatched_inputs_are_refused(self):
        with resolved_temp_dir() as root:
            good, bad, table = _write(root, "a.json", "{}"), _write(root, "b.json", "{oops"), _write(root, "c.csv", "id\n")
            for a, b in ((good, bad), (good, table), (good, root / "missing.json")):
                with self.assertRaises(DataDiffError):
                    diff_data(a, b)

    def test_cli_exit_codes_and_lines(self):
        with resolved_temp_dir() as root:
            a, b = _write(root, "a.wpn", VANILLA_WPN), _write(root, "b.wpn", MOD_WPN)
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["diff-data", str(a), str(b)]), 1)
                self.assertEqual(main(["diff-data", str(a), str(a)]), 0)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(main(["diff-data", str(a), str(root / "nope.wpn")]), 2)
        self.assertIn("~ damage.amount: 25 -> 30.0", out.getvalue())
        self.assertIn('^ tags: same values, other order: ["pd", "kinetic"] -> ["kinetic", "pd"]', out.getvalue())
        self.assertIn("IDENTICAL (json): no value differences", out.getvalue())


if __name__ == "__main__":
    unittest.main()
