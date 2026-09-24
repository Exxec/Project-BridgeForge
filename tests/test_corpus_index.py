from __future__ import annotations

import io
import os
import sqlite3
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from bridgeforge.cli import main
from bridgeforge.corpus_index import CorpusIndexError, build_index, search_index
from tests.support import resolved_temp_dir


def _trigram_available() -> bool:
    try:
        sqlite3.connect(":memory:").execute("CREATE VIRTUAL TABLE t USING fts5(x, tokenize='trigram')")
    except sqlite3.OperationalError:
        return False
    return True


def _write(path: Path, data: bytes | str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    (path.write_bytes if isinstance(data, bytes) else lambda d: path.write_text(d, encoding="utf-8"))(data)
    return path


def _archive(root: Path) -> Path:
    downloads = root / "Downloads"
    # The 2026-09-20 false negative: the id sat in Ship and Weapon Pack's hull_mods.csv.
    _write(downloads / "Ship and Weapon Pack" / "data" / "hullmods" / "hull_mods.csv",
           "name,id,tags\nShield Bypass,shieldbypass,special\n")
    with zipfile.ZipFile(_write(downloads / "Rebal.zip", b""), "w") as archive:
        archive.writestr("Rebal/data/weapons/lightmg.wpn", '{"id":"lightmg","type":"BALLISTIC"}')
        archive.writestr("Rebal/graphics/lightmg.png", b"\x89PNG\x00\x00")
        archive.writestr("Rebal/nested.zip", b"PK")
    _write(downloads / "Old.7z", b"7z\xbc\xaf")
    _write(downloads / "big.csv", "id\n" + "x" * 200 + "\n")
    _write(downloads / "blob.json", b"\x00\x01binary")
    _write(downloads / "cp1252.csv", "id,name\nq,caf\xe9\n".encode("cp1252"))
    return downloads


@unittest.skipUnless(_trigram_available(), "this Python's SQLite has no FTS5 trigram tokenizer")
class CorpusIndexTests(unittest.TestCase):
    def test_finds_content_inside_folders_and_zips_case_insensitively(self):
        with resolved_temp_dir() as root:
            downloads, db = _archive(root), root / "state" / "index.sqlite"
            build_index(downloads, db, max_bytes=100)
            bypass = search_index(db, "SHIELDBYPASS")
            weapon = search_index(db, "BALLISTIC")
            accent = search_index(db, "café")
        self.assertEqual([h["location"] for h in bypass["content_hits"]], ["Ship and Weapon Pack/data/hullmods/hull_mods.csv"])
        self.assertEqual(bypass["content_hits"][0]["lines"], ["2: Shield Bypass,shieldbypass,special"])
        self.assertEqual([h["location"] for h in weapon["content_hits"]], ["Rebal.zip!Rebal/data/weapons/lightmg.wpn"])
        self.assertEqual([h["location"] for h in accent["content_hits"]], ["cp1252.csv"])

    def test_every_unsearched_file_is_reported(self):
        with resolved_temp_dir() as root:
            downloads, db = _archive(root), root / "index.sqlite"
            result = build_index(downloads, db, max_bytes=100)
            names = search_index(db, "lightmg.png", names_only=True)
        self.assertEqual(result["not_searched"], {
            ".7z archives are not read": 1, "archive inside an archive": 1, "binary content": 1, "larger than 100 bytes": 1})
        self.assertEqual(names["name_hits"], ["Rebal.zip!Rebal/graphics/lightmg.png"])

    def test_rebuild_reads_only_changes_and_forgets_deleted_files(self):
        with resolved_temp_dir() as root:
            downloads, db = _archive(root), root / "index.sqlite"
            first = build_index(downloads, db)
            again = build_index(downloads, db)
            csv = downloads / "Ship and Weapon Pack" / "data" / "hullmods" / "hull_mods.csv"
            csv.write_text("name,id\nPhase Lance,phaselance\n", encoding="utf-8")
            os.utime(csv, ns=(1, 1))
            (downloads / "blob.json").unlink()
            third = build_index(downloads, db)
            gone = search_index(db, "shieldbypass")
            new = search_index(db, "phaselance")
        self.assertEqual((first["reindexed"], again["reindexed"], again["unchanged"]), (6, 0, 6))
        self.assertEqual((third["reindexed"], third["forgotten"]), (1, 1))
        self.assertEqual(gone["content_hits"], [])
        self.assertEqual(len(new["content_hits"]), 1)
        self.assertNotIn("binary content", new["not_searched"])

    def test_guards(self):
        with resolved_temp_dir() as root:
            downloads = _archive(root)
            with self.assertRaises(CorpusIndexError):
                build_index(downloads, downloads / "index.sqlite")  # inside the archive
            build_index(downloads, root / "index.sqlite")
            other = root / "Other"
            other.mkdir()
            with self.assertRaises(CorpusIndexError):
                build_index(other, root / "index.sqlite")  # one index per root
            with self.assertRaises(CorpusIndexError):
                search_index(root / "index.sqlite", "ab")
            with self.assertRaises(CorpusIndexError):
                search_index(root / "missing.sqlite", "abc")

    def test_cli_prints_hits_and_coverage(self):
        with resolved_temp_dir() as root:
            downloads, db = _archive(root), root / "index.sqlite"
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["corpus-index", "build", str(downloads), "--db", str(db), "--max-bytes", "100"]), 0)
                self.assertEqual(main(["corpus-index", "search", "shieldbypass", "--db", str(db)]), 0)
                self.assertEqual(main(["corpus-index", "search", "nowhere_to_be_found", "--db", str(db)]), 1)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(main(["corpus-index", "search", "ab", "--db", str(db)]), 2)
        text = out.getvalue()
        self.assertIn("Ship and Weapon Pack/data/hullmods/hull_mods.csv (1 matching line(s))", text)
        self.assertIn("No hits for 'nowhere_to_be_found'.", text)
        self.assertIn("NOT searched: 1 .7z archives are not read", text)


if __name__ == "__main__":
    unittest.main()
