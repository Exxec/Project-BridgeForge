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


if __name__ == "__main__":
    unittest.main()
