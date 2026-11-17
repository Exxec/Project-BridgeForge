"""`intake --strip-junk` (ROADMAP-3 item 92.4, 2026-11-16): Scrapyard Armories (four *.png~) and Navarchy of Tania (two *.png~
and a desktop.ini) were blocked by archive-junk-member and rebuilt by hand."""
from __future__ import annotations

import json
import unittest
import zipfile
from pathlib import Path

from bridgeforge.intake import intake_archive
from tests.support import resolved_temp_dir

JUNK = ["Mod-1.0/graphics/ship.png~", "Mod-1.0/data/config/desktop.ini"]


def _archive(root: Path) -> Path:
    archive = root / "Mod-1.0.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("Mod-1.0/mod_info.json", '{"id":"junkmod","name":"Junk Mod","version":"1"}')
        output.writestr("Mod-1.0/graphics/ship.png", b"\x89PNG")
        for entry in JUNK:
            output.writestr(entry, b"x")
    return archive


class StripJunkTests(unittest.TestCase):
    def test_junk_only_archive_is_intaken_from_a_clean_copy(self) -> None:
        with resolved_temp_dir() as root:
            archive = _archive(root)
            raw_bytes = archive.read_bytes()
            repo = root / "repo"
            repo.mkdir()
            result = intake_archive(archive, repo, strip_junk=True)
            manifest = json.loads((Path(result["destination"]) / "reports" / "intake.json").read_text(encoding="utf-8"))
            working = sorted(p.relative_to(Path(result["working"])).as_posix() for p in Path(result["working"]).rglob("*") if p.is_file())
            clean_names = zipfile.ZipFile(root / "Mod-1.0-clean.zip").namelist()
            raw_kept = archive.read_bytes() == raw_bytes
        self.assertTrue(raw_kept)
        self.assertEqual(manifest["stripped_members"], sorted(JUNK))
        self.assertEqual(manifest["raw_archive"], "Mod-1.0.zip")
        self.assertEqual(working, ["graphics/ship.png", "mod_info.json"])
        self.assertFalse(any(name in clean_names for name in JUNK))

    def test_without_the_flag_the_error_names_the_hazards(self) -> None:
        with resolved_temp_dir() as root:
            archive = _archive(root)
            repo = root / "repo"
            repo.mkdir()
            with self.assertRaises(ValueError) as raised:
                intake_archive(archive, repo)
        message = str(raised.exception)
        self.assertIn("archive-junk-member", message)
        self.assertIn("ship.png~", message)
        self.assertIn("--strip-junk", message)

    def test_an_existing_clean_copy_is_never_overwritten(self) -> None:
        with resolved_temp_dir() as root:
            archive = _archive(root)
            (root / "Mod-1.0-clean.zip").write_bytes(b"someone else's")
            repo = root / "repo"
            repo.mkdir()
            with self.assertRaises(ValueError):
                intake_archive(archive, repo, strip_junk=True)
            kept = (root / "Mod-1.0-clean.zip").read_bytes()
        self.assertEqual(kept, b"someone else's")


class BatchIntakeTests(unittest.TestCase):
    """ROADMAP-3 item 92.5: several sources per call and loose names resolved in a mods folder."""

    def test_loose_names_resolve_to_one_folder_or_are_refused(self) -> None:
        from bridgeforge.intake import resolve_mod_folder

        with resolved_temp_dir() as root:
            for name in ("Everybody loves KoC-1.05.49a", "Eridani Combine-1.0.3.6", "Kazeron Navarchy-1.8.0",
                         "Navarchy of Tania-1.0.1", "MagicLib-1.5.6", "MagicLib-1.6.1"):
                (root / name).mkdir()
            self.assertEqual(resolve_mod_folder("koch", root).name, "Everybody loves KoC-1.05.49a")
            self.assertEqual(resolve_mod_folder("eridiani combine", root).name, "Eridani Combine-1.0.3.6")
            self.assertEqual(resolve_mod_folder("navarchy of tania", root).name, "Navarchy of Tania-1.0.1")
            with self.assertRaises(ValueError):
                resolve_mod_folder("magiclib", root)  # two versions: a tie is refused
            with self.assertRaises(ValueError):
                resolve_mod_folder("unrelated", root)

    def test_several_sources_in_one_call(self) -> None:
        import contextlib
        import io

        from bridgeforge.cli import main

        with resolved_temp_dir() as root:
            mods = root / "mods"
            for folder, mod_id in (("Alpha Mod-1.0", "alpha"), ("Beta Mod-2.0", "beta")):
                (mods / folder).mkdir(parents=True)
                (mods / folder / "mod_info.json").write_text(json.dumps({"id": mod_id, "name": folder, "version": "1"}), encoding="utf-8")
            repo = root / "repo"
            repo.mkdir()
            err = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                code = main(["intake", "alpha", "beta", "nonesuch", "--from-mods", str(mods), "--repo-root", str(repo)])
            made = sorted(p.name for p in (repo / "In operation").iterdir() if p.is_dir() and not p.name.startswith("_"))
        self.assertEqual(made, ["alpha", "beta"])
        self.assertIn("alpha -> Alpha Mod-1.0", err.getvalue())
        self.assertIn("nonesuch", err.getvalue())
        self.assertEqual(code, 2)  # one source failed; the others were still taken in


if __name__ == "__main__":
    unittest.main()
