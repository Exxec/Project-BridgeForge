"""`dropped-features` and `reports/REMOVALS.json` (ROADMAP items 77.16, 77.19)."""
from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from bridgeforge.cli import main
from bridgeforge.dropped_sweep import check_workspace, select_old_tree
from bridgeforge.removals import REMOVALS_FILE, RemovalsError, add_removals, load_removals, make_entry
from tests.support import resolved_temp_dir

RULES = "id,trigger,conditions,script\nr1,OpenCommLink,,\nr2,CrusadeNews,,\nr3,CrusadeEnd,,\n"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _mod(root: Path, mod_id: str, *, rules: str | None = RULES, java: tuple[str, ...] = ()) -> Path:
    _write(root / "mod_info.json", json.dumps({"id": mod_id, "name": mod_id, "version": "1"}))
    if rules is not None:
        _write(root / "data/campaign/rules.csv", rules)
    for name in java:
        _write(root / f"data/scripts/{name}.java", f"package data.scripts;\npublic class {name} {{}}\n")
    return root


def _entry(**kwargs) -> dict:
    return {"category": "rules.csv", "reason": "why", "source": "owner", "date": "2026-10-19", **kwargs}


class OldTreeSelectionTests(unittest.TestCase):
    def test_pack_root_original_chooses_the_sub_folder_with_the_same_id(self):
        with resolved_temp_dir() as root:
            ws = root / "Part"
            for part in ("alpha", "beta", "gamma"):
                _mod(ws / "original/extracted" / part, part, java=(f"{part.title()}Class",))
            _mod(ws / "working", "beta", rules=None)
            choice = select_old_tree(ws)
            self.assertEqual(choice["tree"], ws / "original/extracted/beta")
            row = check_workspace(ws)
            self.assertEqual(sorted(row["dropped"]), ["classes", "rules.csv"])
            self.assertNotIn("data.scripts.AlphaClass", row["dropped"]["classes"]["unexplained"])

    def test_multiple_roots_without_an_id_match_is_undetermined(self):
        with resolved_temp_dir() as root:
            ws = root / "Part"
            _mod(ws / "original/a", "a")
            _mod(ws / "original/b", "b")
            _mod(ws / "working", "c")
            row = check_workspace(ws)
            self.assertEqual((row["verdict"], row["old_tree"]), ("UNDETERMINED", None))
            self.assertIn("2 mod roots", row["reason"])

    def test_a_single_mod_root_is_used_without_an_id_match(self):
        with resolved_temp_dir() as root:
            ws = root / "Part"
            _mod(ws / "original/Folder/Inner", "old_id")
            _mod(ws / "working", "new_id", rules=None)
            self.assertEqual(select_old_tree(ws)["origin"], "original (only mod)")
            self.assertEqual(check_workspace(ws)["verdict"], "DROPS_UNEXPLAINED")

    def test_port_source_wins_over_original(self):
        with resolved_temp_dir() as root:
            ws = root / "Part"
            _mod(ws / "original/same", "same", rules="id,trigger\nx,FromOriginal\n")
            _mod(ws / "scratch/before", "same", rules="id,trigger\nx,FromPort\n")
            _mod(ws / "working", "same", rules="id,trigger\nx,Kept\n")
            _write(ws / "working/reports/PORT_SOURCE.json", json.dumps({"old_tree": "scratch/before"}))
            row = check_workspace(ws)
            self.assertEqual(row["origin"], "PORT_SOURCE.json")
            self.assertEqual(row["dropped"]["rules.csv"]["unexplained"], ["FromPort"])

    def test_no_original_is_undetermined_and_clean_when_nothing_dropped(self):
        with resolved_temp_dir() as root:
            ws = root / "Part"
            _mod(ws / "working", "x")
            self.assertEqual(check_workspace(ws)["verdict"], "UNDETERMINED")
            _mod(ws / "original/x", "x")
            self.assertEqual(check_workspace(ws)["verdict"], "CLEAN")


class RemovalsTests(unittest.TestCase):
    def _workspace(self, root: Path) -> Path:
        ws = root / "Mod"
        _mod(ws / "original/Mod", "mod", java=("Old",))
        _mod(ws / "working", "mod", rules="id,trigger\nr1,OpenCommLink\n")
        return ws

    def test_items_and_patterns_explain_drops(self):
        with resolved_temp_dir() as root:
            ws = self._workspace(root)
            self.assertEqual(check_workspace(ws)["unexplained"], 3)
            add_removals(ws / "working", [make_entry("rules.csv", item="CrusadeNews", reason="gone upstream", source="upstream"),
                                          make_entry("rules.csv", pattern="CrusadeE*", reason="gone", source="owner")])
            row = check_workspace(ws)
            self.assertEqual((row["explained"], row["unexplained"]), (2, 1))
            self.assertEqual(row["dropped"]["classes"]["unexplained"], ["data.scripts.Old"])
            add_removals(ws / "working", [make_entry("classes", pattern="data.scripts.*", reason="stripped", source="strip-plan")])
            self.assertEqual(check_workspace(ws)["verdict"], "EXPLAINED")

    def test_add_removals_skips_duplicates(self):
        with resolved_temp_dir() as root:
            working = root / "working"
            entry = make_entry("classes", item="a.B", reason="r", source="renamed")
            add_removals(working, [entry])
            add_removals(working, [dict(entry)])
            self.assertEqual(len(load_removals(working)), 1)

    def test_invalid_files_are_refused(self):
        bad = [
            {"schema": 1, "removals": [_entry(category="nope", item="x")]},
            {"schema": 1, "removals": [_entry(item="x", reason="")]},
            {"schema": 1, "removals": [{k: v for k, v in _entry(item="x").items() if k != "reason"}]},
            {"schema": 1, "removals": [_entry(item="x", pattern="y")]},
            {"schema": 1, "removals": [_entry()]},
            {"schema": 1, "removals": [_entry(item="x", source="whim")]},
            {"schema": 1, "removals": [_entry(item="x", date="yesterday")]},
            {"schema": 2, "removals": []},
        ]
        for data in bad:
            with self.subTest(data=data), resolved_temp_dir() as root:
                _write(root / "working" / REMOVALS_FILE, json.dumps(data))
                with self.assertRaises(RemovalsError):
                    load_removals(root / "working")
        with resolved_temp_dir() as root:
            _write(root / "working" / REMOVALS_FILE, "{not json")
            with self.assertRaises(RemovalsError):
                load_removals(root / "working")

    def test_an_invalid_file_explains_nothing_and_is_reported(self):
        with resolved_temp_dir() as root:
            ws = self._workspace(root)
            _write(ws / "working" / REMOVALS_FILE, json.dumps({"schema": 1, "removals": [_entry(item="CrusadeNews", reason=" ")]}))
            row = check_workspace(ws)
            self.assertEqual((row["verdict"], row["explained"]), ("DROPS_UNEXPLAINED", 0))
            self.assertIn("reason", row["removals_error"])


class QueueCommandTests(unittest.TestCase):
    def _queue(self, root: Path) -> Path:
        queue = root / "queue"
        _mod(queue / "ATDD/original/ATDD", "atdd")
        _mod(queue / "ATDD/working", "atdd", rules=None)  # whole rules.csv lost
        _mod(queue / "Clean/original/Clean", "clean")
        _mod(queue / "Clean/working", "clean")
        _mod(queue / "Pack/original/a", "a")
        _mod(queue / "Pack/original/b", "b")
        _mod(queue / "Pack/working", "zzz")
        _mod(queue / "Explained/original/E", "e")
        _mod(queue / "Explained/working", "e", rules=None)
        add_removals(queue / "Explained/working", [make_entry("rules.csv", pattern="*", reason="rules dropped", source="owner")])
        return queue

    def test_rules_csv_missing_is_unexplained_and_output_is_worst_first(self):
        with resolved_temp_dir() as root:
            queue, out = self._queue(root), root / "out"
            before = sorted(p.relative_to(queue).as_posix() for p in queue.rglob("*"))
            err = io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(err):
                self.assertEqual(main(["dropped-features", "--queue", str(queue), "--write", str(out)]), 0)
            self.assertEqual(sorted(p.relative_to(queue).as_posix() for p in queue.rglob("*")), before)
            data = json.loads((out / "dropped_features.json").read_text(encoding="utf-8"))
            self.assertEqual([r["workspace"] for r in data["rows"]], ["ATDD", "Pack", "Explained", "Clean"])
            self.assertEqual(data["rows"][0]["verdict"], "DROPS_UNEXPLAINED")
            self.assertEqual(data["rows"][0]["unexplained"], 3)
            self.assertEqual(data["verdicts"], {"DROPS_UNEXPLAINED": 1, "UNDETERMINED": 1, "EXPLAINED": 1, "CLEAN": 1})
            self.assertIn("[4/4]", err.getvalue())
            self.assertFalse((out / "DROPPED_FEATURES.partial.jsonl").exists())
            text = (out / "DROPPED_FEATURES.md").read_text(encoding="utf-8")
            self.assertLess(text.index("  ATDD:"), text.index("  Explained:"))

    def test_single_workspace_json_and_usage_errors(self):
        with resolved_temp_dir() as root:
            queue = self._queue(root)
            out = io.StringIO()
            with redirect_stdout(out), redirect_stderr(io.StringIO()):
                self.assertEqual(main(["dropped-features", str(queue / "ATDD"), "--json"]), 0)
                self.assertEqual(main(["dropped-features"]), 2)
                self.assertEqual(main(["dropped-features", str(queue / "nope")]), 2)
            self.assertEqual(json.loads(out.getvalue())["rows"][0]["verdict"], "DROPS_UNEXPLAINED")


if __name__ == "__main__":
    unittest.main()
