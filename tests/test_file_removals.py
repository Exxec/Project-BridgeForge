"""ROADMAP 77.19 `files` category and 77.27 `remove` + `removed-without-record`."""
from __future__ import annotations

import io
import json
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from bridgeforge.cli import main
from bridgeforge.dropped_sweep import check_workspace
from bridgeforge.file_drops import dropped_files, is_junk_file, split_dropped_files
from bridgeforge.hand_remove import RemoveError, remove_files, unrecorded_removed_files
from bridgeforge.removals import REMOVALS_FILE, RemovalsError, add_removals, load_removals, make_entry
from bridgeforge.scan.scanner import scan_mod
from tests.support import resolved_temp_dir

MOD_INFO = '{"id": "bf_files", "name": "Files", "author": "A", "version": "1.0", "gameVersion": "0.98a-RC8"}'


def _write(path: Path, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _workspace(root: Path) -> Path:
    for tree in ("original/mod", "working"):
        _write(root / tree / "mod_info.json", MOD_INFO)
    return root


class FileDropTests(unittest.TestCase):
    def test_dropped_file_is_unexplained_until_a_files_entry_covers_it(self) -> None:
        with resolved_temp_dir() as tmp:
            ws = _workspace(tmp)
            _write(ws / "original/mod/data/hulls/a.ship")
            _write(ws / "original/mod/data/hulls/b.ship")
            _write(ws / "working/data/hulls/b.ship")
            row = check_workspace(ws)
            self.assertEqual(row["verdict"], "DROPS_UNEXPLAINED")
            self.assertEqual(row["dropped"]["files"]["unexplained"], ["data/hulls/a.ship"])
            add_removals(ws / "working", [make_entry("files", item="data/hulls/a.ship", reason="r", source="owner")])
            self.assertEqual(check_workspace(ws)["verdict"], "EXPLAINED")

    def test_a_pattern_explains_files(self) -> None:
        with resolved_temp_dir() as tmp:
            ws = _workspace(tmp)
            _write(ws / "original/mod/data/hulls/a.ship")
            add_removals(ws / "working", [make_entry("files", pattern="data/hulls/*", reason="r", source="owner")])
            self.assertEqual(check_workspace(ws)["dropped"]["files"]["explained"], ["data/hulls/a.ship"])

    def test_vanilla_core_paths_are_not_drops_and_no_core_is_marked(self) -> None:
        with resolved_temp_dir() as tmp:
            ws, core = _workspace(tmp / "ws"), tmp / "core"
            _write(ws / "original/mod/data/config/x.json")
            _write(ws / "original/mod/data/hulls/new.ship")
            _write(core / "data/config/x.json")
            self.assertEqual(dropped_files(ws / "original/mod", ws / "working", core), ["data/hulls/new.ship"])
            self.assertEqual(dropped_files(ws / "original/mod", ws / "working"), ["data/config/x.json", "data/hulls/new.ship"])
            self.assertEqual(check_workspace(ws)["files_core"], "skipped")
            self.assertEqual(check_workspace(ws, core)["files_core"], "checked")

    def test_java_source_is_not_dropped_when_its_class_ships_in_a_jar(self) -> None:
        with resolved_temp_dir() as tmp:
            ws = _workspace(tmp)
            _write(ws / "original/mod/data/scripts/Shipped.java", "package data.scripts;\nclass Shipped {}\n")
            _write(ws / "original/mod/data/scripts/Lost.java", "package data.scripts;\nclass Lost {}\n")
            (ws / "working/jars").mkdir()
            with zipfile.ZipFile(ws / "working/jars/m.jar", "w") as jar:
                jar.writestr("data/scripts/Shipped.class", b"")
            self.assertEqual(dropped_files(ws / "original/mod", ws / "working"), ["data/scripts/Lost.java"])

    def test_junk_is_split_off_and_never_changes_the_verdict(self) -> None:
        for name in ("a.ship.old", "x.png~", "a.bak.2", "a.java.pre-bf-fix.bak", "d.log", "s.lnk", "z.rar", "z.zip", "z.7z", "desktop.ini",
                     "Thumbs.db", "rules - копия.csv", "rules 副本.csv", "a - Copy.csv", "Copy of a.csv", "a (copy).csv"):
            self.assertTrue(is_junk_file("data/x/" + name), name)
        self.assertFalse(is_junk_file("data/x/rules.csv"))
        with resolved_temp_dir() as tmp:
            ws = _workspace(tmp)
            _write(ws / "original/mod/data/hulls/a.ship.old")
            row = check_workspace(ws)
            self.assertEqual(row["verdict"], "CLEAN")
            self.assertEqual(row["junk_dropped"], ["data/hulls/a.ship.old"])

    def test_java_and_class_files_inherit_the_classes_category(self) -> None:
        with resolved_temp_dir() as tmp:
            ws = _workspace(tmp)
            _write(ws / "original/mod/data/scripts/Gone.java", "package data.scripts;\nclass Gone {}\n")
            _write(ws / "original/mod/data/missions/m/MissionDefinition.class")
            files, _junk = split_dropped_files(ws / "original/mod", ws / "working", None, {"data.scripts.Gone", "data.missions.m.MissionDefinition"})
            self.assertEqual(files, [])
            row = check_workspace(ws)
            self.assertEqual(row["dropped"]["classes"]["unexplained"], ["data.scripts.Gone"])
            self.assertEqual(row["dropped"]["files"]["unexplained"], ["data/missions/m/MissionDefinition.class"])

    def test_files_category_is_accepted_by_validation(self) -> None:
        with self.assertRaises(RemovalsError):
            make_entry("nothing", item="x", reason="r", source="owner")
        self.assertEqual(make_entry("files", item="data/a.csv", reason="r", source="owner")["category"], "files")


class RemoveCommandTests(unittest.TestCase):
    def _ws(self, tmp: Path) -> Path:
        ws = _workspace(tmp)
        _write(ws / "working/data/hulls/raa_dragline.ship", '{"hullId":"raa_dragline"}')
        _write(ws / "working/data/hulls/variants/raa_dragline_standard.variant", '{"hullId":"raa_dragline"}')
        _write(ws / "working/data/hulls/other.ship", '{"hullId":"other"}')
        return ws

    def test_moves_and_records_together(self) -> None:
        with resolved_temp_dir() as tmp:
            ws = self._ws(tmp)
            paths = ["data/hulls/raa_dragline.ship", "data\\hulls\\variants\\raa_dragline_standard.variant"]
            entries = remove_files(ws, paths, reason="owner ruling", when="2026-10-20")
            self.assertEqual(len(entries), 2)
            self.assertFalse((ws / "working/data/hulls/raa_dragline.ship").exists())
            self.assertTrue((ws / "scratch/removed/2026-10-20/data/hulls/raa_dragline.ship").is_file())
            self.assertEqual([e["item"] for e in load_removals(ws / "working")],
                             ["data/hulls/raa_dragline.ship", "data/hulls/variants/raa_dragline_standard.variant"])
            self.assertEqual(unrecorded_removed_files(ws, ws / "working"), [])

    def test_refuses_while_referenced_unless_forced_and_records_the_references(self) -> None:
        with resolved_temp_dir() as tmp:
            ws = self._ws(tmp)
            with self.assertRaises(RemoveError) as caught:
                remove_files(ws, ["data/hulls/raa_dragline.ship"], reason="r")
            self.assertIn("raa_dragline_standard.variant", str(caught.exception))
            self.assertTrue((ws / "working/data/hulls/raa_dragline.ship").is_file())
            self.assertFalse((ws / "scratch").exists())
            entries = remove_files(ws, ["data/hulls/raa_dragline.ship"], reason="r", force_dangling=True)
            self.assertIn("dangling references accepted", entries[0]["reason"])

    def test_refuses_bad_paths_and_links(self) -> None:
        with resolved_temp_dir() as tmp:
            ws = self._ws(tmp)
            for bad in ("../x", "/abs/x", "C:/x", "data/hulls", "data/missing.csv", REMOVALS_FILE):
                with self.assertRaises(RemoveError, msg=bad):
                    remove_files(ws, [bad], reason="r")
            with self.assertRaises(RemoveError):
                remove_files(ws, ["data/hulls/other.ship"], reason=" ")
            link = ws / "working/data/hulls/link.ship"
            try:
                link.symlink_to(ws / "working/data/hulls/other.ship")
            except (OSError, NotImplementedError):
                self.skipTest("cannot create symlinks here")
            with self.assertRaises(RemoveError):
                remove_files(ws, ["data/hulls/link.ship"], reason="r")

    def test_cli_and_scanner_finding(self) -> None:
        with resolved_temp_dir() as tmp:
            ws = self._ws(tmp)
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(main(["remove", str(ws), "data/hulls/other.ship", "--reason", "gone", "--source", "upstream"]), 0)
                self.assertEqual(main(["remove", str(ws), "data/hulls/nope.ship", "--reason", "gone"]), 2)
            self.assertIn("Recorded 1", out.getvalue())
            data = json.loads((ws / "working" / REMOVALS_FILE).read_text(encoding="utf-8"))
            self.assertEqual(data["removals"][0]["source"], "upstream")
            self.assertNotIn("removed-without-record", {f.id for f in scan_mod(ws / "working").findings})
            _write(ws / "scratch/removed/rules.csv")
            _write(ws / "scratch/removed/2026-10-20/data/hulls/unlisted.ship")
            self.assertEqual(unrecorded_removed_files(ws, ws / "working"), ["2026-10-20/data/hulls/unlisted.ship", "rules.csv"])
            found = [f for f in scan_mod(ws / "working").findings if f.id == "removed-without-record"]
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0].classification, "MANUAL")


if __name__ == "__main__":
    unittest.main()
