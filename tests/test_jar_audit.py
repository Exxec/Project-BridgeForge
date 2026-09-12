import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from bridgeforge.jar_audit import ClassFileError, audit_jar, parse_constant_pool, referenced_class_names
from bridgeforge.cli import main


def _u2(value: int) -> bytes:
    return value.to_bytes(2, "big")


def build_minimal_class(this_name: str, referenced_names: tuple[str, ...] = ()) -> bytes:
    """Emit a minimal valid .class file whose constant pool references the given class names."""
    constants: list[bytes] = []

    def add_utf8(text: str) -> int:
        raw = text.encode("utf-8")
        constants.append(bytes([1]) + _u2(len(raw)) + raw)
        return len(constants)

    def add_class(name_index: int) -> int:
        constants.append(bytes([7]) + _u2(name_index))
        return len(constants)

    this_index = add_class(add_utf8(this_name))
    super_index = add_class(add_utf8("java/lang/Object"))
    for name in referenced_names:
        add_class(add_utf8(name))

    body = b"\xca\xfe\xba\xbe" + _u2(0) + _u2(61) + _u2(len(constants) + 1)
    for entry in constants:
        body += entry
    body += _u2(0x0021)  # access_flags
    body += _u2(this_index)
    body += _u2(super_index)
    body += _u2(0) + _u2(0) + _u2(0) + _u2(0)  # interfaces/fields/methods/attributes counts
    return body


def _write_jar(path: Path, classes: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in classes.items():
            archive.writestr(name, data)


class ConstantPoolTests(unittest.TestCase):
    def test_parses_referenced_class_names(self) -> None:
        data = build_minimal_class("Sample", ("java/lang/reflect/Field", "java/util/List"))
        entries = parse_constant_pool(data)
        names = referenced_class_names(entries)
        self.assertIn("Sample", names)
        self.assertIn("java/lang/reflect/Field", names)
        self.assertIn("java/util/List", names)

    def test_rejects_bad_magic(self) -> None:
        with self.assertRaises(ClassFileError):
            parse_constant_pool(b"not-a-class-file")


class JarAuditTests(unittest.TestCase):
    def test_reports_bundled_library_and_removed_and_changed_classes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original_jar = root / "Original.jar"
            _write_jar(
                original_jar,
                {
                    "data/scripts/Plugin.class": build_minimal_class("data/scripts/Plugin"),
                    "data/scripts/Removed.class": build_minimal_class("data/scripts/Removed"),
                },
            )
            rebuilt_jar = root / "Rebuilt.jar"
            _write_jar(
                rebuilt_jar,
                {
                    "data/scripts/Plugin.class": build_minimal_class("data/scripts/Plugin", ("java/util/List",)),
                    "org/dark/shaders/Shader.class": build_minimal_class("org/dark/shaders/Shader"),
                },
            )
            result = audit_jar(rebuilt_jar, original_jar)
            self.assertEqual(result["rebuilt_class_count"], 2)
            self.assertEqual(result["original_class_count"], 2)
            self.assertEqual([entry["class"] for entry in result["removed_classes"]], ["data/scripts/Removed.class"])
            self.assertEqual(result["changed_classes"], ["data/scripts/Plugin.class"])
            self.assertEqual(result["unchanged_class_count"], 0)
            self.assertEqual([entry["package"] for entry in result["bundled_library_packages"]], ["org/dark/shaders"])
            self.assertEqual(result["status"], "MANUAL")

    def test_flags_reflection_and_file_and_nio_references(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original_jar = root / "Original.jar"
            _write_jar(original_jar, {"data/scripts/Teleport.class": build_minimal_class("data/scripts/Teleport")})
            rebuilt_jar = root / "Rebuilt.jar"
            _write_jar(
                rebuilt_jar,
                {"data/scripts/Teleport.class": build_minimal_class("data/scripts/Teleport", ("java/lang/reflect/Field", "java/io/FileInputStream", "java/nio/file/Files"))},
            )
            result = audit_jar(rebuilt_jar, original_jar)
            self.assertEqual(len(result["reflection_findings"]), 1)
            flagged = set(result["reflection_findings"][0]["referenced_symbols"])
            self.assertEqual(flagged, {"java/lang/reflect/Field", "java/io/FileInputStream", "java/nio/file/Files"})
            self.assertEqual(result["status"], "MANUAL")

    def test_does_not_flag_reflective_operation_or_io_exception(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original_jar = root / "Original.jar"
            _write_jar(original_jar, {"data/scripts/Safe.class": build_minimal_class("data/scripts/Safe")})
            rebuilt_jar = root / "Rebuilt.jar"
            _write_jar(
                rebuilt_jar,
                {"data/scripts/Safe.class": build_minimal_class("data/scripts/Safe", ("java/lang/ReflectiveOperationException", "java/io/IOException"))},
            )
            result = audit_jar(rebuilt_jar, original_jar)
            self.assertEqual(result["reflection_findings"], [])
            self.assertEqual(result["status"], "PASS")

    def test_accepts_original_as_zip_archive_containing_the_jar(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inner_jar_bytes = io.BytesIO()
            with zipfile.ZipFile(inner_jar_bytes, "w") as inner:
                inner.writestr("data/scripts/Plugin.class", build_minimal_class("data/scripts/Plugin"))
            archive = root / "Mod 1.0.zip"
            with zipfile.ZipFile(archive, "w") as outer:
                outer.writestr("Mod 1.0/jars/MOD.jar", inner_jar_bytes.getvalue())
            rebuilt_jar = root / "MOD.jar"
            _write_jar(rebuilt_jar, {"data/scripts/Plugin.class": build_minimal_class("data/scripts/Plugin")})
            result = audit_jar(rebuilt_jar, archive)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["unchanged_class_count"], 1)

    def test_accepts_original_jar_renamed_as_backup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original_backup = root / "al_arkleg.jar.pre-ring-guard.bak"
            _write_jar(original_backup, {"data/scripts/Plugin.class": build_minimal_class("data/scripts/Plugin")})
            rebuilt_jar = root / "al_arkleg.jar"
            _write_jar(rebuilt_jar, {"data/scripts/Plugin.class": build_minimal_class("data/scripts/Plugin")})
            result = audit_jar(rebuilt_jar, original_backup)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["unchanged_class_count"], 1)

    def test_rejects_non_zip_original(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original_backup = root / "al_arkleg.jar.pre-ring-guard.bak"
            original_backup.write_bytes(b"not a zip at all")
            rebuilt_jar = root / "al_arkleg.jar"
            _write_jar(rebuilt_jar, {"data/scripts/Plugin.class": build_minimal_class("data/scripts/Plugin")})
            with self.assertRaises(ValueError) as ctx:
                audit_jar(rebuilt_jar, original_backup)
            self.assertIn("--original must be an existing .jar file or a .zip archive containing one", str(ctx.exception))

    def test_cli_exit_code_reflects_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original_jar = root / "Original.jar"
            _write_jar(original_jar, {"data/scripts/Plugin.class": build_minimal_class("data/scripts/Plugin")})
            rebuilt_jar = root / "Rebuilt.jar"
            _write_jar(rebuilt_jar, {"data/scripts/Plugin.class": build_minimal_class("data/scripts/Plugin")})
            self.assertEqual(main(["jar-audit", str(rebuilt_jar), "--original", str(original_jar)]), 0)
            _write_jar(rebuilt_jar, {"org/dark/shaders/Shader.class": build_minimal_class("org/dark/shaders/Shader")})
            self.assertEqual(main(["jar-audit", str(rebuilt_jar), "--original", str(original_jar), "--json"]), 1)
