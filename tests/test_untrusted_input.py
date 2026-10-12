"""ROADMAP 70 H2.4: untrusted archives and class files must not exhaust memory or hang a command."""
from __future__ import annotations

import io
import unittest
import zipfile

from bridgeforge import atlas
from bridgeforge.atlas_classfile import ClassFormatError, parse_class
from bridgeforge.zipsafe import ZipEntryTooLarge, read_limited
from tests.test_atlas import build, make_mod, make_vanilla, temp_root


def _zip(entries: dict[str, bytes]) -> zipfile.ZipFile:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as out:
        for name, data in entries.items():
            out.writestr(name, data)
    return zipfile.ZipFile(io.BytesIO(buffer.getvalue()))


class ZipSafeTests(unittest.TestCase):
    def test_an_entry_within_the_limit_is_read_and_one_over_it_is_refused(self) -> None:
        archive = _zip({"small.txt": b"x" * 10, "big.bin": b"y" * 1000})
        self.assertEqual(read_limited(archive, "small.txt", max_bytes=100), b"x" * 10)
        with self.assertRaises(ZipEntryTooLarge) as caught:
            read_limited(archive, "big.bin", max_bytes=100)
        self.assertIsInstance(caught.exception, OSError)  # the per-entry readers already catch OSError
        self.assertIn("big.bin", str(caught.exception))

    def test_a_header_that_understates_the_size_is_caught_while_reading(self) -> None:
        """A zip bomb says one thing and holds another: the declared size must not be the only check."""
        archive = _zip({"bomb.bin": b"z" * 5000})
        info = archive.getinfo("bomb.bin")
        info.file_size = 10  # the lie
        # zipfile itself stops reading at the declared size, so the lie ends as a CRC error; either way nothing beyond the limit is returned.
        with self.assertRaises((ZipEntryTooLarge, zipfile.BadZipFile)):
            read_limited(archive, info, max_bytes=100)

    def test_a_bad_crc_is_still_an_error(self) -> None:
        archive = _zip({"a.txt": b"hello world"})
        info = archive.getinfo("a.txt")
        info.CRC = 0xDEADBEEF
        with self.assertRaises(zipfile.BadZipFile):
            read_limited(archive, info)


class ClassFileLimitTests(unittest.TestCase):
    def test_truncated_and_garbage_class_files_raise_the_parser_error_not_something_else(self) -> None:
        for data in (b"", b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbe" + b"\x00" * 8, b"not a class at all" * 100,
                     b"\xca\xfe\xba\xbe\x00\x00\x00\x34\xff\xff"):  # a constant pool count of 65535 with no entries
            with self.subTest(size=len(data)), self.assertRaises(ClassFormatError):
                parse_class(data, frozenset())


class AtlasHostileJarTests(unittest.TestCase):
    def test_a_truncated_jar_and_a_class_full_of_garbage_do_not_stop_the_build(self) -> None:
        with temp_root() as root:
            make_vanilla(root)
            good = make_mod(root / "mods", "good", {"mod_info.json": '{"id": "good", "name": "good", "version": "1", "jars": ["jars/g.jar"]}'})
            (good / "jars").mkdir()
            (good / "jars" / "g.jar").write_bytes(b"PK\x03\x04" + b"\x00" * 6)  # truncated: not a readable zip
            hostile = make_mod(root / "mods", "hostile", {"mod_info.json": '{"id": "hostile", "name": "hostile", "version": "1", "jars": ["jars/h.jar"]}'})
            (hostile / "jars").mkdir()
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w") as jar:
                jar.writestr("a/Garbage.class", b"\xca\xfe\xba\xbe" + b"\xff" * 64)
                jar.writestr("a/Empty.class", b"")
            (hostile / "jars" / "h.jar").write_bytes(buffer.getvalue())
            db, stats = build(root)
            conn = atlas.connect(db)
            indexed = {r[0] for r in conn.execute("SELECT id FROM mods")}
        self.assertTrue({"good", "hostile"} <= indexed)
        self.assertEqual(stats["skipped"], 0)


if __name__ == "__main__":
    unittest.main()
