"""ROADMAP 77.24: every backing-up writer re-reads what it wrote and refuses a short or missing write, keeping its backup.

Each test drops the last byte of one named file's write (or skips the copy entirely) and expects WriteVerificationError or the
writer's own FixerError, with the pre-write backup still on disk.
"""
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

from bridgeforge.fixers import FileChange, FixerError, FixPlan, apply_fix
from bridgeforge.bytecode.jar_batch import _copy_back_sources
from bridgeforge.archive_intake import stage_zip_archive
from bridgeforge.safeio import WriteVerificationError, verify_removed, verify_written
from bridgeforge.translation import _apply_java
import zipfile


def _drop_last_byte_for(name: str):
    """Patch Path.write_bytes so a write to a file called `name` loses its final byte."""
    real = Path.write_bytes

    def write(self: Path, data: bytes) -> int:
        return real(self, data[:-1] if self.name == name else data)

    return mock.patch.object(Path, "write_bytes", write)


class SafeioVerificationTests(unittest.TestCase):
    def test_matching_bytes_pass_and_short_or_missing_bytes_raise(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "a.txt"
            target.write_bytes(b"abc")
            verify_written(target, b"abc")
            with self.assertRaises(WriteVerificationError):
                verify_written(target, b"abcd")
            with self.assertRaises(WriteVerificationError):
                verify_written(Path(directory) / "missing.txt", b"abc")

    def test_removal_must_leave_nothing_behind(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "a.txt"
            with self.assertRaises(WriteVerificationError):
                target.write_bytes(b"x")
                verify_removed(target)
            target.unlink()
            verify_removed(target)


class WriterVerificationTests(unittest.TestCase):
    def test_apply_fix_raises_when_a_written_file_is_short_and_keeps_its_backup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rules = root / "rules.csv"
            rules.write_bytes(b"old\n")
            plan = FixPlan("test-fix", root, [FileChange(path=rules, before=b"old\n", after=b"new\n")])
            with _drop_last_byte_for("rules.csv"), self.assertRaises(FixerError) as raised:
                apply_fix(plan)
            backups = list(root.glob("rules.csv.pre-bf-fix-test-fix.bak*"))
            kept = [b.read_bytes() for b in backups]
        self.assertIn("did not leave the planned files", str(raised.exception))
        self.assertEqual(kept, [b"old\n"])

    def test_apply_fix_passes_when_the_write_is_complete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rules = root / "rules.csv"
            rules.write_bytes(b"old\n")
            apply_fix(FixPlan("test-fix", root, [FileChange(path=rules, before=b"old\n", after=b"new\n")]))
            self.assertEqual(rules.read_bytes(), b"new\n")

    def test_copy_back_of_a_port_raises_when_the_source_is_short(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            working = Path(directory) / "working"
            source = working / "src" / "Foo.java"
            edited = Path(directory) / "scratch" / "Foo.java"
            source.parent.mkdir(parents=True)
            edited.parent.mkdir(parents=True)
            source.write_bytes(b"old\n")
            edited.write_bytes(b"new\n")

            def copy_dropping_last_byte(src, dst):
                data = Path(src).read_bytes()
                Path(dst).write_bytes(data[:-1] if Path(dst).name == "Foo.java" else data)

            with mock.patch("bridgeforge.bytecode.jar_batch.shutil.copy2", copy_dropping_last_byte), \
                    self.assertRaises(WriteVerificationError):
                _copy_back_sources({edited: source}, [edited], working, "port-interfaces")
            backup = source.with_name("Foo.java.pre-bf-port-interfaces.bak")
            self.assertEqual(backup.read_bytes(), b"old\n")

    def test_translation_java_write_raises_when_short(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "Foo.java"
            source.write_text('class Foo { String s = "中文"; }', encoding="utf-8")
            entries = {"java:Foo.java@0": {"id": "T1", "kind": "java", "source": "中文", "translation": "hello"}}
            with _drop_last_byte_for("Foo.java"), self.assertRaises(WriteVerificationError):
                _apply_java(source, "Foo.java", entries, Counter(), [])

    def test_translation_java_write_passes_when_complete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "Foo.java"
            source.write_text('class Foo { String s = "中文"; }', encoding="utf-8")
            entries = {"java:Foo.java@0": {"id": "T1", "kind": "java", "source": "中文", "translation": "hello"}}
            applied: Counter = Counter()
            _apply_java(source, "Foo.java", entries, applied, [])
            self.assertEqual(applied["java"], 1)
            self.assertIn('"hello"', source.read_text(encoding="utf-8"))

    def test_archive_staging_raises_when_an_extracted_file_is_not_the_archived_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "one.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("One/mod_info.json", '{"id": "One"}')
            # The copy writes nothing, so the staged file is empty while the archive holds the bytes.
            with mock.patch("bridgeforge.archive_intake.shutil.copyfileobj", lambda source, output: None), \
                    self.assertRaises(WriteVerificationError):
                stage_zip_archive(archive, root / "staged", "One")


if __name__ == "__main__":
    unittest.main()
