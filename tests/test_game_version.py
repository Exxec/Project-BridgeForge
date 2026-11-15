"""game_version (ROADMAP-3 item 89, 2026-11-15): a core's version from its starfarer_obf.jar, so `revive --vanilla-core`
writes that version into mod_info.json instead of a fixed 0.98a-RC8."""
from __future__ import annotations

import unittest
import zipfile

from bridgeforge.game_version import core_game_version
from tests.support import resolved_temp_dir


class GameVersionTests(unittest.TestCase):
    def test_the_newest_version_string_in_the_obfuscated_jar_wins(self) -> None:
        with resolved_temp_dir() as root:
            core = root / "starsector-core"
            core.mkdir()
            with zipfile.ZipFile(core / "starfarer_obf.jar", "w") as jar:
                # Both real jars also carry a legacy "0.9.1a-RC8" constant (2026-11-15).
                jar.writestr("com/fs/A.class", b"\xca\xfe\xba\xbe..0.9.1a-RC8..")
                jar.writestr("com/fs/B.class", b"\xca\xfe\xba\xbe..0.98.5a-RC3..0.98a-RC10..")
                jar.writestr("notes.txt", b"0.99a-RC1")  # not a class: ignored
            self.assertEqual(core_game_version(core), "0.98.5a-RC3")

    def test_no_core_or_no_jar_is_none(self) -> None:
        with resolved_temp_dir() as root:
            self.assertIsNone(core_game_version(None))
            self.assertIsNone(core_game_version(root))

    def test_revive_defaults_its_target_to_the_core_version(self) -> None:
        from bridgeforge.cli import main
        import contextlib
        import io

        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            main(["revive", "--help"])
        self.assertIn("--vanilla-core's own version", " ".join(out.getvalue().split()))


if __name__ == "__main__":
    unittest.main()
