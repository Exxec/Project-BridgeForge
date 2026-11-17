"""ROADMAP 70 H2.4: untrusted archives and class files must not exhaust memory or hang a command."""
from __future__ import annotations

import hashlib
import io
import struct
import unittest
import zipfile
from unittest import mock

from bridgeforge.atlas import atlas
from bridgeforge.atlas.atlas_classfile import ClassFormatError, parse_class
from bridgeforge.scan import scan_classfile
from bridgeforge.zipsafe import ZipEntryTooLarge, entry_sha256, read_limited
from tests.support import resolved_temp_dir
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

    def test_an_entry_hash_is_streamed_and_matches_the_whole_entry(self) -> None:
        data = bytes(range(256)) * 9000  # over two read chunks
        archive = _zip({"music.ogg": data})
        self.assertEqual(entry_sha256(archive, "music.ogg"), hashlib.sha256(data).hexdigest())
        self.assertEqual(entry_sha256(archive, archive.getinfo("music.ogg")), hashlib.sha256(data).hexdigest())


def _class_with_string(text: str) -> bytes:
    """A class file holding one Utf8 constant: enough for the constant-pool readers."""
    raw = text.encode("utf-8")
    return b"\xca\xfe\xba\xbe\x00\x00\x00\x3d" + struct.pack(">H", 2) + b"\x01" + struct.pack(">H", len(raw)) + raw + b"\x00" * 8


def _jar_with_big_class_first(path, small: bytes) -> None:
    with zipfile.ZipFile(path, "w") as out:
        out.writestr("a/Big.class", b"\xca\xfe\xba\xbe" + b"\x00" * 200)
        out.writestr("a/Small.class", small)


class JarClassLimitTests(unittest.TestCase):
    """ROADMAP-3 93.33: jar walks read class entries with a bound, skip an oversize one and go on with the rest of the jar."""

    def test_a_class_over_the_limit_is_skipped_and_named_apart_from_unreadable_jars(self) -> None:
        with resolved_temp_dir() as root:
            jar = root / "mod.jar"
            _jar_with_big_class_first(jar, b"\xca\xfe\xba\xbe" + b"\x00" * 8)
            unreadable: list[str] = []
            skipped: list[str] = []
            with mock.patch.object(scan_classfile, "MAX_CLASS_BYTES", 64):
                members = [member for _jar, member, _data in
                           scan_classfile.iter_class_files_in_jars([jar], unreadable=unreadable, skipped_entries=skipped)]
        self.assertEqual(members, ["a/Small.class"])
        self.assertEqual(unreadable, [])  # whole jars only: verify-shadow counts the jars it checked from this list
        self.assertEqual(len(skipped), 1)
        self.assertIn("a/Big.class", skipped[0])
        self.assertIn("64 byte limit", skipped[0])

    def test_verify_shadow_counts_a_jar_with_a_skipped_class_as_checked(self) -> None:
        """Review 2026-11-17: per-entry records in `unreadable` made `jars_checked` wrong, even negative."""
        from bridgeforge.verify_shadow import verify_shadow

        with resolved_temp_dir() as root:
            jar = root / "mod.jar"
            _jar_with_big_class_first(jar, _class_with_string("unrelated"))
            script = root / "data" / "scripts" / "X.java"
            script.parent.mkdir(parents=True)
            script.write_text("package data.scripts;\npublic class X {}\n", encoding="utf-8")
            with mock.patch.object(scan_classfile, "MAX_CLASS_BYTES", 64):
                result = verify_shadow([script], [jar])
        self.assertEqual((result["jars_checked"], result["unreadable_jars"]), (1, []))
        self.assertEqual(len(result["skipped_classes"]), 1)

    def test_a_walk_that_catches_per_jar_reads_past_an_oversize_class(self) -> None:
        """Review 2026-11-17: campaign_layout and six other walks catch errors per jar, so before read_class one huge entry
        hid every class after it."""
        from bridgeforge import zipsafe
        from bridgeforge.campaign_layout import mod_placed_types

        with resolved_temp_dir() as root:
            (root / "jars").mkdir()
            (root / "mod_info.json").write_text('{"id": "m", "name": "m", "version": "1", "jars": ["jars/m.jar"]}', encoding="utf-8")
            _jar_with_big_class_first(root / "jars" / "m.jar", _class_with_string("m_planet_type"))
            with mock.patch.object(zipsafe, "MAX_CLASS_BYTES", 64):
                placed = mod_placed_types(root, {"m_planet_type"})
                big = zipsafe.read_class(zipfile.ZipFile(root / "jars" / "m.jar"), "a/Big.class")
        self.assertEqual(placed, {"m_planet_type"})
        self.assertIsNone(big)


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
