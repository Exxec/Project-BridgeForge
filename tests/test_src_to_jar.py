"""`src-to-jar` and the `jar-source-not-rebuilt` check (ROADMAP-3 item 92.25, 2026-11-16): agent fixes to a jar mod's
src/ never reached the jar the game loads (Navarchy of Tania: 8 fixes; Eridani Combine: 1)."""
from __future__ import annotations

import hashlib
import subprocess
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from bridgeforge.bytecode.src_to_jar import changed_sources, read_ledger, src_to_jar, unbuilt_sources
from bridgeforge.scan.scanner import scan_mod
from tests.support import javac_path, resolved_temp_dir

ORIGINAL = "package data.scripts;\npublic class Spawner {\n    public int count() { return 1; }\n}\n"
FIXED = ORIGINAL.replace("return 1;", "return 2;")
OTHER = ORIGINAL.replace("return 1;", "return 7;")  # what a jar built from different source holds
CLASS = "data/scripts/Spawner.class"


class SrcToJarTests(unittest.TestCase):
    """Real javac; skipped cleanly when no JDK is on PATH."""

    def setUp(self) -> None:
        javac = javac_path()
        if javac is None:
            self.skipTest("no javac on PATH")
        self.javac = javac

    def _compile(self, root: Path, text: str, release: str) -> bytes:
        src = root / f"build-{release}-{hashlib.md5(text.encode()).hexdigest()[:6]}"
        (src / "data" / "scripts").mkdir(parents=True)
        (src / "data" / "scripts" / "Spawner.java").write_text(text, encoding="utf-8")
        done = subprocess.run([self.javac, "--release", release, "-nowarn", "-encoding", "UTF-8", "-d", str(src / "out"), str(src / "data" / "scripts" / "Spawner.java")],
                              capture_output=True, text=True, check=False)
        self.assertEqual(done.returncode, 0, done.stderr)
        return (src / "out" / CLASS).read_bytes()

    def _workspace(self, root: Path, *, shipped_from: str | None = None, release: str = "17", original: str = ORIGINAL) -> Path:
        ws = root / "In operation" / "Mod"
        info = '{"id":"mod","name":"Mod","version":"1","gameVersion":"0.98a-RC8","jars":["jars/mod.jar"]}'
        for base in (ws / "original" / "extracted" / "Mod", ws / "working"):
            (base / "src" / "data" / "scripts").mkdir(parents=True)
            (base / "jars").mkdir()
            (base / "mod_info.json").write_text(info, encoding="utf-8")
            (base / "src" / "data" / "scripts" / "Spawner.java").write_text(original, encoding="utf-8")
        with zipfile.ZipFile(ws / "working" / "jars" / "mod.jar", "w") as archive:
            archive.writestr(CLASS, self._compile(root, shipped_from or original, release))
            archive.writestr("README.txt", "kept")
        (root / "core").mkdir(exist_ok=True)
        return ws

    def _agent_edit(self, ws: Path, original: str = ORIGINAL, fixed: str = FIXED) -> None:
        source = ws / "working" / "src" / "data" / "scripts" / "Spawner.java"
        source.with_name("Spawner.java.pre-bf-escalation-x--1.bak").write_text(original, encoding="utf-8")
        source.write_text(fixed, encoding="utf-8")

    def _jar_class(self, ws: Path) -> bytes:
        with zipfile.ZipFile(ws / "working" / "jars" / "mod.jar") as archive:
            return archive.read(CLASS)

    def test_a_jar_entry_cannot_write_outside_the_proofs_folder(self) -> None:
        """ROADMAP-3 93.48: `prove_authoritative` wrote each shipped inner class to `<scratch>/shipped/<entry name>` and checked
        only that `<scratch>/ref/<entry name>` existed. Both climb out by the same number of `..`.
        - With `/` separators javac refuses the jar ("cannot access data.scripts"), so the proof stopped first.
        - Stored with backslashes, the entry is a plain file name to javac, which compiled, while Python's zipfile on Windows
          reads it as `data/scripts/Spawner$/../../../../../../victim.class`: it overwrote a file outside the scratch folder
          (2026-11-17)."""
        from bridgeforge.bytecode import src_to_jar as module

        class FixedScratch:
            def __init__(self, path: Path) -> None:
                self.path = path

            def __enter__(self) -> str:
                self.path.mkdir(parents=True)
                return str(self.path)

            def __exit__(self, *_exc) -> bool:
                return False

        with resolved_temp_dir() as root:
            ws = self._workspace(root)
            victim = root / "victim.class"
            victim.write_bytes(b"untouched")
            # <root>/scratch/proof/shipped/data/scripts/Spawner$ is six folders below <root>. ZipInfo turns "\" into "/" when
            # it is created, so the raw name is set afterwards.
            hostile = zipfile.ZipInfo("placeholder")
            hostile.filename = "data/scripts/Spawner$" + "\\.." * 6 + "\\victim.class"
            with zipfile.ZipFile(ws / "working" / "jars" / "mod.jar", "a") as archive:
                archive.writestr(hostile, b"hostile bytes")
            with mock.patch.object(module.tempfile, "TemporaryDirectory", return_value=FixedScratch(root / "scratch" / "proof")):
                module.prove_authoritative(ws, "jars/mod.jar", ["data/scripts/Spawner.java"], reference_core=root / "core",
                                           jdk=Path(self.javac).resolve().parent.parent)
            self.assertEqual(victim.read_bytes(), b"untouched")

    def test_the_proof_writes_nothing_outside_its_folder_even_past_the_name_filter(self) -> None:
        """The second guard of 93.48, on its own: a name the filter let through still may not leave the scratch folder."""
        from bridgeforge.bytecode import src_to_jar as module

        with resolved_temp_dir() as root:
            ws = self._workspace(root)
            victim = root / "victim.class"
            victim.write_bytes(b"untouched")
            real = module._class_entries(ws / "working" / "jars" / "mod.jar", "data/scripts/Spawner")
            hostile = "data/scripts/Spawner$/" + "../" * 12 + victim.relative_to(victim.anchor).as_posix()
            with mock.patch.object(module, "_class_entries", return_value={**real, hostile: b"hostile bytes"}), \
                    mock.patch.object(module, "_javap_text", return_value="same"), \
                    mock.patch.object(Path, "is_file", lambda path: True):
                problems = module.prove_authoritative(ws, "jars/mod.jar", ["data/scripts/Spawner.java"],
                                                      reference_core=root / "core", jdk=Path(self.javac).resolve().parent.parent)
            self.assertEqual(victim.read_bytes(), b"untouched")
        self.assertTrue(any("points outside the proof's folder" in problem for problem in problems), problems)

    def test_only_plain_class_entries_are_read_for_the_proof(self) -> None:
        from bridgeforge.bytecode.src_to_jar import _class_entries

        with resolved_temp_dir() as root:
            jar = root / "mod.jar"
            with zipfile.ZipFile(jar, "w") as archive:
                for name in ["data/scripts/Spawner.class", "data/scripts/Spawner$1.class",
                             "data/scripts/Spawner$/../../x.class", "data/scripts/Spawner$-J-x.class"]:
                    archive.writestr(name, b"\xca\xfe\xba\xbe")
            self.assertEqual(sorted(_class_entries(jar, "data/scripts/Spawner")),
                             ["data/scripts/Spawner$1.class", "data/scripts/Spawner.class"])

    def test_an_agent_edit_is_flagged_then_built_into_the_jar(self) -> None:
        with resolved_temp_dir() as root:
            ws = self._workspace(root)
            self._agent_edit(ws)
            flagged = [f.id for f in scan_mod(ws / "working").findings]
            self.assertEqual(changed_sources(ws), ["data/scripts/Spawner.java"])
            result = src_to_jar(ws, "jars/mod.jar", vanilla_core=root / "core", reference_core=root / "core", apply=True)
            after = [f.id for f in scan_mod(ws / "working").findings]
            fixed_class = self._compile(root, FIXED, "17")
            jar_class = self._jar_class(ws)
            ledger = read_ledger(ws / "working")
            readme = zipfile.ZipFile(ws / "working" / "jars" / "mod.jar").read("README.txt")
            backup = Path(result["backup_jar"]).is_file()
        self.assertIn("jar-source-not-rebuilt", flagged)
        self.assertEqual(result["status"], "PASS", result)
        self.assertTrue(result["installed"] and backup)
        self.assertEqual(jar_class, fixed_class)  # the jar now runs the fixed source
        self.assertEqual(readme, b"kept")
        self.assertIn("src/data/scripts/Spawner.java", ledger)
        self.assertNotIn("jar-source-not-rebuilt", after)
        self.assertEqual(unbuilt_sources(ws / "working"), [])

    def test_a_jar_not_built_from_src_is_refused_and_left_alone(self) -> None:
        with resolved_temp_dir() as root:
            ws = self._workspace(root, shipped_from=OTHER)
            self._agent_edit(ws)
            before = self._jar_class(ws)
            result = src_to_jar(ws, "jars/mod.jar", vanilla_core=root / "core", reference_core=root / "core", apply=True)
            after = self._jar_class(ws)
        self.assertEqual(result["status"], "REFUSED")
        self.assertIn("does not reproduce the jar class", " ".join(result["refusals"]))
        self.assertEqual(before, after)

    def test_a_java_8_jar_stays_java_8(self) -> None:
        # Eridani Combine's jar is class version 52 (2026-11-16): the proof and the patch compile for Java 8.
        with resolved_temp_dir() as root:
            ws = self._workspace(root, release="8")
            self._agent_edit(ws)
            result = src_to_jar(ws, "jars/mod.jar", vanilla_core=root / "core", reference_core=root / "core", apply=True)
            major = int.from_bytes(self._jar_class(ws)[6:8], "big")
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(major, 52)

    def test_no_reference_core_means_no_proof_and_no_patch(self) -> None:
        with resolved_temp_dir() as root:
            ws = self._workspace(root)
            self._agent_edit(ws)
            result = src_to_jar(ws, "jars/mod.jar", vanilla_core=root / "core", reference_core=None, apply=True)
        self.assertEqual(result["status"], "REFUSED")

    def test_non_ascii_string_constants_do_not_break_the_proof(self) -> None:
        # Bultach Coalition: javap prints constants in the platform encoding; a text-mode read crashed on 'è' (2026-11-16).
        original = ORIGINAL.replace("return 1;", 'String s = "Caf\u00e8"; return s.length() > 0 ? 1 : 0;')
        fixed = original.replace("? 1 : 0", "? 2 : 0")
        with resolved_temp_dir() as root:
            ws = self._workspace(root, original=original)
            self._agent_edit(ws, original, fixed)
            result = src_to_jar(ws, "jars/mod.jar", vanilla_core=root / "core", reference_core=root / "core", apply=True)
        self.assertEqual(result["status"], "PASS", result)

    def test_nothing_changed_is_nothing_to_build(self) -> None:
        with resolved_temp_dir() as root:
            ws = self._workspace(root)
            result = src_to_jar(ws, "jars/mod.jar", vanilla_core=root / "core", reference_core=root / "core")
            flagged = [f.id for f in scan_mod(ws / "working").findings]
        self.assertEqual(result["status"], "NOTHING_TO_BUILD")
        self.assertNotIn("jar-source-not-rebuilt", flagged)


if __name__ == "__main__":
    unittest.main()
