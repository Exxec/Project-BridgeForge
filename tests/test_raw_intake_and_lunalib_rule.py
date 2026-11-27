"""ROADMAP 65 (raw folder intake, planner listing) and 60f(3) (LunaLib install rule)."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from bridgeforge.archive_intake import inspect_zip_archive
from bridgeforge.intake import RENAME_MAX_WAIT_SECONDS, _rename_with_retry, unprocessed_raw_folders, zip_raw_folder
from bridgeforge.probe.probe_group import ProbeGroupError, lunalib_rule
from tests.support import resolved_temp_dir
from tests.support import write_text as _write


class RawFolderIntakeTests(unittest.TestCase):
    def test_raw_folder_is_zipped_into_the_intake_path_and_is_a_safe_archive(self) -> None:
        with resolved_temp_dir() as root:
            raw = root / "In operation" / "Yellow Jackets"
            _write(raw / "mod_info.json", '{"id": "yj"}')
            _write(raw / "data" / "a.csv", "id\n")
            zipped = zip_raw_folder(raw, root)
            again = zip_raw_folder(raw, root)
            preflight = inspect_zip_archive(zipped)
            untouched = (raw / "mod_info.json").is_file()
        self.assertEqual(zipped, root / "In operation" / "_raw-zips" / "Yellow Jackets.zip")
        self.assertEqual(again, zipped)
        self.assertTrue(preflight["safe_to_stage"])
        self.assertEqual(preflight["candidate_mod_roots"], ["Yellow Jackets"])
        self.assertTrue(untouched)

    def test_a_modpack_folder_name_with_a_note_gets_a_portable_zip_name(self) -> None:
        with resolved_temp_dir() as root:
            raw = root / "packs" / "Templars Expanded V2.5.2 (DISABLE UI SCALING!)"
            _write(raw / "mod_info.json", "{}")
            zipped = zip_raw_folder(raw, root)
            roots = inspect_zip_archive(zipped)["candidate_mod_roots"]
        self.assertEqual(zipped.name, "Templars Expanded V2.5.2 -DISABLE UI SCALING.zip")
        self.assertEqual(roots, ["Templars Expanded V2.5.2 -DISABLE UI SCALING"])

    def test_a_folder_without_a_mod_is_refused_and_a_changed_zip_is_never_overwritten(self) -> None:
        with resolved_temp_dir() as root:
            empty = root / "In operation" / "Empty"
            _write(empty / "notes.txt", "x")
            with self.assertRaises(ValueError):
                zip_raw_folder(empty, root)
            raw = root / "In operation" / "Mod"
            _write(raw / "mod_info.json", "{}")
            zip_raw_folder(raw, root)
            _write(raw / "extra.txt", "changed since")
            with self.assertRaises(ValueError):
                zip_raw_folder(raw, root)

    def test_planner_lists_only_unprocessed_raw_folders(self) -> None:
        with resolved_temp_dir() as root:
            queue = root / "In operation"
            _write(queue / "Raw One" / "mod_info.json", "{}")
            _write(queue / "Raw Two" / "Inner" / "mod_info.json", "{}")
            _write(queue / "Done Mod" / "working" / "mod_info.json", "{}")
            _write(queue / "_raw-zips" / "x" / "mod_info.json", "{}")
            _write(queue / "Not a mod" / "readme.txt", "x")
            found = unprocessed_raw_folders(queue)
        self.assertEqual([f["folder"] for f in found], ["Raw One", "Raw Two"])
        self.assertEqual(found[1]["mod_root"], "Inner")


class RenameRetryTests(unittest.TestCase):
    """2026-10-26: Exotica RC4 and New Galactic Order failed the publish rename after the old ~14 s of retries."""

    class _Locked:
        def __init__(self, denials: int) -> None:
            self.denials, self.calls = denials, 0

        def rename(self, target) -> None:
            self.calls += 1
            if self.calls <= self.denials:
                raise PermissionError("Access is denied")

    def test_a_long_first_scan_lock_is_waited_out_with_capped_backoff(self) -> None:
        waits: list[float] = []
        source = self._Locked(denials=10)
        _rename_with_retry(source, Path("target"), sleep=waits.append)
        self.assertEqual(source.calls, 11)
        self.assertEqual(max(waits), RENAME_MAX_WAIT_SECONDS)
        self.assertGreaterEqual(sum(waits), 30)

    def test_the_last_denial_is_raised(self) -> None:
        with self.assertRaises(PermissionError):
            _rename_with_retry(self._Locked(denials=99), Path("target"), sleep=lambda seconds: None)


class LunaLibRuleTests(unittest.TestCase):
    def _mods(self, root: Path, graphicslib_version: str, references_lunalib: bool = True) -> tuple[Path, dict[str, str]]:
        import zipfile

        mods = root / "mods"
        _write(mods / "GraphicsLib" / "mod_info.json",
               json.dumps({"id": "shaderLib", "version": graphicslib_version, "jars": ["jars/Graphics.jar"]}))
        (mods / "GraphicsLib" / "jars").mkdir(parents=True)
        # GraphicsLib 1.12.1 and 1.12.3 both ship GraphicsLibSettingsListener, which names lunalib/lunaSettings/ (98.15).
        body = b"\xca\xfe\xba\xbe lunalib/lunaSettings/LunaSettingsListener" if references_lunalib else b"\xca\xfe\xba\xbe org/dark/x"
        with zipfile.ZipFile(mods / "GraphicsLib" / "jars" / "Graphics.jar", "w") as jar:
            jar.writestr("org/dark/shaders/util/GraphicsLibSettingsListener.class", body)
            jar.writestr("org/dark/shaders/util/ShaderLib.class", b"\xca\xfe\xba\xbe")
        # A jar mod_info.json does not list is never loaded: a reference there does not count.
        with zipfile.ZipFile(mods / "GraphicsLib" / "jars" / "old.jar", "w") as jar:
            jar.writestr("a/B.class", b"\xca\xfe\xba\xbe lunalib/lunaSettings/LunaSettingsListener")
        _write(mods / "LunaLib" / "mod_info.json", json.dumps({"id": "lunalib", "version": "2.0.5"}))
        return mods, {"shaderLib": "GraphicsLib", "lunalib": "LunaLib"}

    def test_graphicslib_1_12_1_gets_lunalib_automatically(self) -> None:
        with resolved_temp_dir() as root:
            mods, installed = self._mods(root, "1.12.1")
            enable, why, advice = lunalib_rule(["shaderLib", "demo"], installed, mods)
        self.assertTrue(enable)
        self.assertIn("RC8-25", why)
        self.assertIsNone(advice)

    def test_any_graphicslib_whose_jar_references_lunalib_gets_it(self) -> None:
        # 98.15, RC9NC-LIVE5: GraphicsLib 1.12.3 also needs LunaLib; the rule named 1.12.1 only, and the game died at start-up.
        with resolved_temp_dir() as root:
            mods, installed = self._mods(root, "1.12.3")
            enable, why, _advice = lunalib_rule(["shaderLib"], installed, mods)
        self.assertTrue(enable)
        self.assertIn("1.12.3", why)

    def test_no_lunalib_opts_out_and_keeps_the_advice(self) -> None:
        with resolved_temp_dir() as root:
            mods, installed = self._mods(root, "1.12.1")
            enable, why, advice = lunalib_rule(["shaderLib"], installed, mods, no_lunalib=True)
        self.assertFalse(enable)
        self.assertIn("--no-lunalib", why)
        self.assertIn("--with-lunalib", advice)

    def test_a_graphicslib_without_the_reference_stays_advice_only_until_with_lunalib_is_given(self) -> None:
        with resolved_temp_dir() as root:
            mods, installed = self._mods(root, "1.12.1", references_lunalib=False)
            plain = lunalib_rule(["shaderLib"], installed, mods)
            forced = lunalib_rule(["shaderLib"], installed, mods, with_lunalib=True)
        self.assertEqual(plain[0], False)
        self.assertIsNotNone(plain[2])
        self.assertTrue(forced[0])
        self.assertIn("forced", forced[1])

    def test_nothing_happens_without_graphicslib_or_when_lunalib_is_already_enabled(self) -> None:
        with resolved_temp_dir() as root:
            mods, installed = self._mods(root, "1.12.1")
            self.assertEqual(lunalib_rule(["demo"], installed, mods), (False, None, None))
            self.assertEqual(lunalib_rule(["shaderLib", "lunalib"], installed, mods), (False, None, None))

    def test_a_corrupt_jar_a_string_jar_list_and_windows_separators(self) -> None:
        # Review, 2026-11-27: a corrupt deflate stream raised zlib.error out of lunalib_rule and crashed probe-group install.
        import zipfile

        from bridgeforge.probe.probe_group import graphicslib_needs_lunalib

        with resolved_temp_dir() as root:
            mods, _installed = self._mods(root, "1.12.3")
            graphicslib = mods / "GraphicsLib"
            info = graphicslib / "mod_info.json"
            info.write_text(json.dumps({"id": "shaderLib", "version": "1.12.3", "jars": ["jars\\Graphics.jar"]}), encoding="utf-8")
            backslash = graphicslib_needs_lunalib(graphicslib)
            info.write_text(json.dumps({"id": "shaderLib", "version": "1.12.3", "jars": "jars/Graphics.jar"}), encoding="utf-8")
            as_string = graphicslib_needs_lunalib(graphicslib)
            corrupt = graphicslib / "jars" / "Broken.jar"
            with zipfile.ZipFile(corrupt, "w", zipfile.ZIP_DEFLATED) as jar:
                jar.writestr("a/B.class", b"\xca\xfe\xba\xbe" + b"lunalib/lunaSettings/ " * 400)
            data = bytearray(corrupt.read_bytes())
            with zipfile.ZipFile(corrupt) as jar:
                entry = jar.infolist()[0]
            start = entry.header_offset + 30 + len(entry.filename.encode()) + len(entry.extra)
            data[start:start + 16] = b"\xff" * 16
            corrupt.write_bytes(bytes(data))
            info.write_text(json.dumps({"id": "shaderLib", "version": "1.12.3", "jars": ["jars/Broken.jar"]}), encoding="utf-8")
            broken = graphicslib_needs_lunalib(graphicslib)
        self.assertEqual((backslash, as_string, broken), (True, False, False))

    def test_contradicting_flags_are_refused(self) -> None:
        with resolved_temp_dir() as root:
            mods, installed = self._mods(root, "1.12.1")
            with self.assertRaises(ProbeGroupError):
                lunalib_rule(["shaderLib"], installed, mods, with_lunalib=True, no_lunalib=True)


if __name__ == "__main__":
    unittest.main()
