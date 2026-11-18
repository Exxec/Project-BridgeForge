"""ROADMAP 70 H2.4: untrusted archives and class files must not exhaust memory or hang a command."""
from __future__ import annotations

import hashlib
import io
import json
import struct
import subprocess
import unittest
import zipfile
from unittest import mock

from bridgeforge.atlas import atlas
from bridgeforge.bytecode.java_toolchain import find_jdk
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


# Entry names a hostile jar can carry. javap's launcher reads an argument starting with -J as a JVM option wherever it stands:
# a jar entry named "-J-version.class" made the JVM print its version instead of running javap (JDK 25, 2026-11-17).
_HOSTILE_ENTRIES = ["-J-version.class", "@javap-args.class", "x/class.class", "a b.class", "a:b.class", "a//b.class"]


def _jar_with_class_names(path, marker: bytes) -> None:
    with zipfile.ZipFile(path, "w") as out:
        for name in [*_HOSTILE_ENTRIES, "a/B.class"]:
            out.writestr(name, b"\xca\xfe\xba\xbe " + marker)


def _javap_class_arguments(module, call) -> list[str]:
    """Every argument the jar walk passed to javap after the jar path, with subprocess.run replaced by a recorder."""
    seen: list[str] = []

    def record(args, **_kwargs):
        seen.extend(args[args.index("-cp") + 2:])
        return mock.Mock(stdout="", stderr="", returncode=0)

    with mock.patch.object(module.subprocess, "run", side_effect=record):
        call()
    return seen


class JavapClassNameTests(unittest.TestCase):
    """ROADMAP-3 93.45: a jar entry's name reaches javap only as a plain binary class name, never as an option, an argument
    file, a path or a URL."""

    def test_only_a_plain_binary_name_is_a_javap_class_name(self) -> None:
        from bridgeforge.zipsafe import javap_class_name

        for entry, expected in [("a/B.class", "a.B"), ("a/B$1.class", "a.B$1"), ("Top.class", "Top"), ("_a/$b/c9.class", "_a.$b.c9")]:
            self.assertEqual(javap_class_name(entry), expected, entry)
        # Non-ASCII too: on Windows javap gets its arguments in the ANSI code page (U+FF0D arrived as "?" on cp1252).
        for entry in [*_HOSTILE_ENTRIES, "a/-J-x.class", "/a.class", "a/.class", ".class", "a\\B.class", "a/B.txt", "a/B.class\n",
                      "－J－version.class", "ü/Kläss.class"]:
            self.assertIsNone(javap_class_name(entry), entry)

    def test_settings_reads_never_pass_a_hostile_entry_name_to_javap(self) -> None:
        from bridgeforge import settings_keys
        from bridgeforge.bytecode import javap_batch

        with resolved_temp_dir() as root:
            jar = root / "mod.jar"
            _jar_with_class_names(jar, b"com/fs/starfarer/api/SettingsAPI")
            passed = _javap_class_arguments(javap_batch, lambda: settings_keys.jar_reads(jar, root / "javap.exe"))
        self.assertEqual(set(passed), {"a.B"})  # however many calls: only a.B ever reaches javap

    def test_procgen_suspects_never_pass_a_hostile_entry_name_to_javap(self) -> None:
        from bridgeforge import procgen_args
        from bridgeforge.bytecode import javap_batch

        with resolved_temp_dir() as root:
            jar = root / "mod.jar"
            _jar_with_class_names(jar, b"initStar")
            passed = _javap_class_arguments(javap_batch, lambda: procgen_args.jar_suspects(jar, root / "javap.exe"))
        self.assertEqual(set(passed), {"a.B"})  # however many calls: only a.B ever reaches javap


# A mod_info.json "jars" entry whose line-break component the ".." cancels: Windows' is_file() said yes, and the line breaks
# reached javac's argument file, where a line break ends a token even inside quotes (ROADMAP-3 93.46, 2026-11-17).
_LINE_BREAK_JAR = "x\n-proc:full\n-Afoo=/../jars/lib.jar"


def _processor_mod(root, marker) -> tuple:
    """(mod folder, JDK): a mod whose own jar ships an annotation processor that writes `marker`, declared through
    _LINE_BREAK_JAR."""
    jdk = find_jdk()
    (root / "proc" / "evil").mkdir(parents=True)
    (root / "proc" / "evil" / "P.java").write_text(
        "package evil;\nimport javax.annotation.processing.*; import javax.lang.model.element.TypeElement; import java.util.Set;\n"
        '@SupportedAnnotationTypes("*") public class P extends AbstractProcessor {\n'
        '  static { try { java.nio.file.Files.write(java.nio.file.Paths.get("' + marker.as_posix() + '"), new byte[] {1}); }'
        " catch (Exception e) { throw new RuntimeException(e); } }\n"
        "  public boolean process(Set<? extends TypeElement> a, RoundEnvironment r) { return false; }\n"
        "  public javax.lang.model.SourceVersion getSupportedSourceVersion() { return javax.lang.model.SourceVersion.latestSupported(); } }\n",
        encoding="utf-8")
    subprocess.run([str(jdk.javac), "-d", str(root / "proc_classes"), str(root / "proc" / "evil" / "P.java")], check=True,
                   capture_output=True)
    mod = root / "mod"
    (mod / "jars").mkdir(parents=True)
    (mod / "data" / "scripts").mkdir(parents=True)
    with zipfile.ZipFile(mod / "jars" / "lib.jar", "w") as out:
        out.write(root / "proc_classes" / "evil" / "P.class", "evil/P.class")
        out.writestr("META-INF/services/javax.annotation.processing.Processor", "evil.P\n")
    (mod / "data" / "scripts" / "A.java").write_text("public class A {}\n", encoding="utf-8")
    (mod / "mod_info.json").write_text(json.dumps({"id": "m", "jars": ["jars/lib.jar", _LINE_BREAK_JAR]}), encoding="utf-8")
    return mod, jdk


class JavacArgumentFileTests(unittest.TestCase):
    """ROADMAP-3 93.46: nothing from a mod reaches a javac argument file with a line break in it."""

    def test_a_line_break_never_reaches_a_javac_argument_file(self) -> None:
        from bridgeforge.bytecode.java_toolchain import javac_argument_line

        self.assertEqual(javac_argument_line('C:\\a "b"'), '"C:\\\\a \\"b\\""\n')
        for argument in ["x\n-proc:full", "x\r-proc:full", "x\r\n"]:
            with self.assertRaises(ValueError):
                javac_argument_line(argument)

    def test_compile_check_refuses_a_line_break_before_starting_javac(self) -> None:
        from bridgeforge.bytecode import java_toolchain

        with resolved_temp_dir() as root, mock.patch.object(java_toolchain.subprocess, "run") as run:
            with self.assertRaises(ValueError):
                java_toolchain.run_javac(root / "javac.exe", "a.jar\n-proc:full", [root / "A.java"], root / "out")
        run.assert_not_called()

    def test_build_refuses_a_line_break_before_starting_javac(self) -> None:
        from bridgeforge import build
        from bridgeforge.models import TargetProfile
        from bridgeforge.workspace import create_workspace

        with resolved_temp_dir() as root:
            (root / "source" / "src").mkdir(parents=True)
            (root / "source" / "src" / "Example.java").write_text("class Example {}", encoding="utf-8")
            workspace = create_workspace(root / "source", root / "workspace")
            build.create_build_profile(workspace, TargetProfile("0.98a-RC8", 17), None, [], [])
            profile_file = workspace / "build-profile.json"
            profile = json.loads(profile_file.read_text(encoding="utf-8"))
            (root / "javac.exe").write_bytes(b"")
            profile["jdk"] = {"javac": str(root / "javac.exe")}
            profile["command_preview"][-1:-1] = ["-classpath", "a.jar\n-proc:full"]  # a Linux file name may hold a line break
            profile_file.write_text(json.dumps(profile), encoding="utf-8")
            with mock.patch.object(build.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")) as run, \
                    self.assertRaises(ValueError):
                build.run_compile(workspace)
        run.assert_not_called()

    def test_build_turns_annotation_processing_off(self) -> None:
        """A JDK 17 or 21 javac runs any processor a classpath jar declares unless told not to."""
        from bridgeforge import build
        from bridgeforge.models import TargetProfile
        from bridgeforge.workspace import create_workspace

        with resolved_temp_dir() as root:
            (root / "source" / "src").mkdir(parents=True)
            (root / "source" / "src" / "Example.java").write_text("class Example {}", encoding="utf-8")
            workspace = create_workspace(root / "source", root / "workspace")
            profile = build.create_build_profile(workspace, TargetProfile("0.98a-RC8", 17), None, [], [])
            self.assertIn("-proc:none", profile.command_preview)
            # A profile written before 93.46 has no -proc option; run_compile adds it.
            profile_file = workspace / "build-profile.json"
            saved = json.loads(profile_file.read_text(encoding="utf-8"))
            saved["command_preview"].remove("-proc:none")
            (root / "javac.exe").write_bytes(b"")
            saved["jdk"] = {"javac": str(root / "javac.exe")}
            profile_file.write_text(json.dumps(saved), encoding="utf-8")
            with mock.patch.object(build.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")):
                result = build.run_compile(workspace)
        self.assertIn("-proc:none", result["command"])

    def test_the_probe_build_turns_annotation_processing_off(self) -> None:
        """Its classpath holds other mods' jars: MagicLib for the probe, Nexerelin for the raid check."""
        from bridgeforge.probe import probe_mod_build

        with resolved_temp_dir() as root, mock.patch.object(
                probe_mod_build.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")) as run:
            probe_mod_build._run_javac(root / "javac.exe", "core.jar;MagicLib.jar", [root / "A.java"], root / "out")
        self.assertIn("-proc:none", run.call_args.args[0])

    def test_a_declared_jar_with_a_control_character_is_left_off_the_classpath(self) -> None:
        from bridgeforge.bytecode.java_toolchain import _mod_jars

        with resolved_temp_dir() as root:
            mod = root / "mod"
            (mod / "jars").mkdir(parents=True)
            (mod / "jars" / "lib.jar").write_bytes(b"PK\x05\x06" + b"\x00" * 18)
            (mod / "mod_info.json").write_text(json.dumps({"id": "m", "jars": ["jars/lib.jar", _LINE_BREAK_JAR]}), encoding="utf-8")
            self.assertEqual(_mod_jars(mod), [mod / "jars" / "lib.jar"])

    @unittest.skipIf(find_jdk() is None, "needs a JDK (javac)")
    def test_compile_check_runs_no_processor_from_a_mods_jar(self) -> None:
        """The reviewer's case end to end: before the fix the processor ran and compile-check said PASS."""
        from bridgeforge.compile_check import compile_loose_scripts

        with resolved_temp_dir() as root:
            marker = root / "PROCESSOR_RAN"
            mod, jdk = _processor_mod(root, marker)
            result = compile_loose_scripts(mod, vanilla_core=None, jdk=jdk.home)
            self.assertFalse(marker.exists())
        self.assertFalse(any("\n" in jar for jar in result.get("classpath", {}).get("mod_jars", [])))


if __name__ == "__main__":
    unittest.main()
