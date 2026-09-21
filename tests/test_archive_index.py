from __future__ import annotations

import contextlib
import io
import json
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from bridgeforge.archive_index import build_index, search_index
from bridgeforge.cli import main
from tests.support import resolved_temp_dir


def _write_zip(path: Path, members: dict[str, bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)


class ArchiveIndexTests(unittest.TestCase):
    """ROADMAP P14 item 18: a one-time content index of a mod-archive folder, found necessary
    2026-09-20 when an unindexed `timeout 60 grep -rl` returned a false negative on a real file.
    """

    def test_filename_and_content_are_both_indexed(self) -> None:
        with resolved_temp_dir() as root:
            _write_zip(root / "ModA.zip", {
                "ModA/mod_info.json": b'{"id":"moda"}',
                "ModA/data/hullmods/hull_mods.csv": b"id,name\nshieldbypass,Shield Bypass\n",
                "ModA/graphics/icon.png": b"\x89PNG\r\n\x1a\nfake-binary-data",
            })
            index_path = root / "index.db"
            result = build_index(root, index_path)
            self.assertEqual(result["archive_count"], 1)
            self.assertEqual(result["counts"]["INDEXED"], 1)

            by_filename = search_index(index_path, "hull_mods", mode="filename")
            self.assertEqual(by_filename["match_count"], 1)
            self.assertEqual(by_filename["matches"][0]["archive"], "ModA.zip")

            by_content = search_index(index_path, "shieldbypass", mode="content")
            self.assertEqual(by_content["match_count"], 1)
            self.assertEqual(by_content["matches"][0]["member"], "ModA/data/hullmods/hull_mods.csv")

            # The binary asset's filename is indexed, but never its bytes as content.
            binary_by_name = search_index(index_path, "icon.png", mode="filename")
            self.assertEqual(binary_by_name["match_count"], 1)
            no_binary_content = search_index(index_path, "PNG", mode="content")
            self.assertEqual(no_binary_content["match_count"], 0)

    def test_unchanged_archive_is_skipped_on_a_second_run(self) -> None:
        with resolved_temp_dir() as root:
            zip_path = root / "ModA.zip"
            _write_zip(zip_path, {"ModA/mod_info.json": b'{"id":"moda"}'})
            index_path = root / "index.db"
            first = build_index(root, index_path)
            self.assertEqual(first["counts"]["INDEXED"], 1)
            second = build_index(root, index_path)
            self.assertEqual(second["counts"]["UNCHANGED"], 1)
            self.assertEqual(second["counts"]["INDEXED"], 0)

    def test_a_changed_archive_is_reindexed_and_old_content_is_replaced(self) -> None:
        with resolved_temp_dir() as root:
            zip_path = root / "ModA.zip"
            _write_zip(zip_path, {"ModA/data/x.csv": b"old_marker_text\n"})
            index_path = root / "index.db"
            build_index(root, index_path)
            self.assertEqual(search_index(index_path, "old_marker_text")["match_count"], 1)

            time.sleep(0.01)
            _write_zip(zip_path, {"ModA/data/x.csv": b"new_marker_text\n"})
            import os
            os.utime(zip_path, None)  # ensure mtime actually advances on fast filesystems
            build_index(root, index_path)
            self.assertEqual(search_index(index_path, "old_marker_text")["match_count"], 0)
            self.assertEqual(search_index(index_path, "new_marker_text")["match_count"], 1)

    def test_a_corrupt_archive_is_reported_as_an_error_not_a_crash(self) -> None:
        with resolved_temp_dir() as root:
            (root / "Good.zip").parent.mkdir(parents=True, exist_ok=True)
            _write_zip(root / "Good.zip", {"Good/mod_info.json": b'{"id":"good"}'})
            (root / "Corrupt.zip").write_bytes(b"not a real zip file")
            index_path = root / "index.db"
            result = build_index(root, index_path)
            self.assertEqual(result["archive_count"], 2)
            self.assertEqual(result["counts"]["INDEXED"], 1)
            self.assertEqual(result["counts"]["ERROR"], 1)
            self.assertEqual(result["errors"][0]["archive"], "Corrupt.zip")

    def test_a_large_content_file_is_indexed_by_filename_only(self) -> None:
        with resolved_temp_dir() as root:
            _write_zip(root / "Big.zip", {"Big/data/huge.csv": b"x" * 100})
            index_path = root / "index.db"
            build_index(root, index_path, max_content_bytes=50)
            self.assertEqual(search_index(index_path, "huge.csv", mode="filename")["match_count"], 1)
            self.assertEqual(search_index(index_path, "xxxx")["match_count"], 0)

    def test_a_password_protected_member_is_skipped_not_a_crash(self) -> None:
        """Real case, 2026-09-21: a password-protected member in the actual Downloads archive
        made zipfile.ZipFile.open raise a plain RuntimeError (stdlib zipfile gives this no
        dedicated exception type), which crashed the very first real run of this command.
        """
        with resolved_temp_dir() as root:
            _write_zip(root / "ModA.zip", {
                "ModA/data/ok.csv": b"readable_marker\n",
                "ModA/data/locked.java": b"would be password-protected in a real archive",
            })
            index_path = root / "index.db"
            real_open = zipfile.ZipFile.open

            def fake_open(self, name, *args, **kwargs):
                if isinstance(name, zipfile.ZipInfo) and name.filename.endswith("locked.java"):
                    raise RuntimeError(f"File {name.filename!r} is encrypted, password required for extraction")
                return real_open(self, name, *args, **kwargs)

            with patch.object(zipfile.ZipFile, "open", fake_open):
                result = build_index(root, index_path)
            self.assertEqual(result["counts"]["INDEXED"], 1)
            self.assertEqual(result["counts"]["ERROR"], 0)
            # The readable member is still indexed; the encrypted one's filename is indexed too
            # (that only needs infolist(), not open()), just never its content.
            self.assertEqual(search_index(index_path, "readable_marker")["match_count"], 1)
            self.assertEqual(search_index(index_path, "locked.java", mode="filename")["match_count"], 1)

    def test_search_before_build_raises(self) -> None:
        with resolved_temp_dir() as root:
            with self.assertRaises(ValueError):
                search_index(root / "does-not-exist.db", "anything")

    def test_cli_builds_and_searches(self) -> None:
        with resolved_temp_dir() as root:
            _write_zip(root / "ModA.zip", {"ModA/data/x.csv": b"cli_marker_text\n"})
            index_path = root / "index.db"
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                exit_code = main(["archive-index", str(root), "--output", str(index_path), "--json"])
            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(out.getvalue())["counts"]["INDEXED"], 1)

            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                exit_code = main(["archive-search", str(index_path), "cli_marker_text", "--json"])
            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(out.getvalue())["match_count"], 1)


if __name__ == "__main__":
    unittest.main()
