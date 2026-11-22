"""94.G2 slice 16: CSV rows as the game's loader keeps them (RC8_BEHAVIOUR RC8-47)."""
from __future__ import annotations

import unittest
from pathlib import Path

from bridgeforge.game_csv import game_rows, records
from bridgeforge.scan.scan_json import _read_csv_rows_lenient
from tests.support import resolved_temp_dir
from tests.support import write_text as _write


def _ids(root: Path, text: str) -> list[str]:
    path = root / "table.csv"
    _write(path, text)
    return [row["id"] for row in game_rows(path) or []]


class GameCsvTests(unittest.TestCase):
    def test_a_row_whose_line_starts_with_a_hash_is_dropped_whatever_its_id(self) -> None:
        with resolved_temp_dir() as root:
            ids = _ids(root, "name,id\n#Atropos,atropos\nRail,rail\n")  # Eridani's commented vanilla weapons
        self.assertEqual(ids, ["rail"])

    def test_a_quoted_or_indented_hash_is_kept_as_the_game_keeps_it(self) -> None:
        # The loader tests the row's first character before reading quotes: vanilla's "#Light Mortar ...",lightmortar_fighter
        # is a row the game keeps.
        with resolved_temp_dir() as root:
            ids = _ids(root, 'name,id\n"#Light Mortar",lightmortar_fighter\n #Spaced,spaced\n')
        self.assertEqual(ids, ["lightmortar_fighter", "spaced"])

    def test_a_hash_row_after_a_blank_line_is_dropped_and_a_hash_line_inside_a_quoted_cell_is_not_a_row(self) -> None:
        with resolved_temp_dir() as root:
            path = root / "table.csv"
            _write(path, 'name,id,desc\nA,a,x\n\n#B,b,x\nC,c,"first\n#second"\nD,d,y\n')
            rows = game_rows(path)
        self.assertEqual([row["id"] for row in rows], ["a", "c", "d"])
        self.assertEqual(rows[1]["desc"], "first\n#second")

    def test_cells_are_exactly_those_the_lenient_reader_gives(self) -> None:
        # Row hashes and gene identities depend on the cells: CRLF endings, a CRLF inside a quoted cell, an extra cell and a
        # short row must come out as csv.DictReader gives them.
        text = 'name,id,desc\r\nA,a,"two\r\nlines"\r\nB,b,x,extra\r\nC,c\r\n'
        with resolved_temp_dir() as root:
            path = root / "table.csv"
            path.write_bytes(text.encode("utf-8"))
            self.assertEqual(game_rows(path), _read_csv_rows_lenient(path))
            self.assertEqual(game_rows(path)[0]["desc"], "two\r\nlines")

    def test_a_leading_blank_line_is_the_header_as_dictreader_takes_it(self) -> None:
        # Review 2026-11-22: DictReader takes the first record as the header even when it is blank, and the pairing must too.
        for text in (b"\nid,name\na,b\n", b"\r\nid,name\r\na,b\r\n", b"\xef\xbb\xbf\nid,x\na,b\n", b"\nid,name\n#c,d\na,b\n"):
            with self.subTest(text=text), resolved_temp_dir() as root:
                path = root / "table.csv"
                path.write_bytes(text)
                expected = [row for row in _read_csv_rows_lenient(path) if row.get(None, [""])[0] != "#c"]
                self.assertEqual(game_rows(path), expected)

    def test_records_give_each_rows_lines_and_comment_flag(self) -> None:
        text = "name,id\n#X,x\nY,\"y\ny\"\n"
        self.assertEqual(list(records(text)), [
            (["name", "id"], 0, 1, False),
            (["#X", "x"], 1, 2, True),
            (["Y", "y\ny"], 2, 4, False),
        ])

    def test_an_unreadable_file_is_none(self) -> None:
        with resolved_temp_dir() as root:
            self.assertIsNone(game_rows(root / "missing.csv"))


if __name__ == "__main__":
    unittest.main()
