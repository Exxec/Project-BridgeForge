"""Small fixes from ROADMAP-3 item 92 (2026-11-16): a missing dependency names itself (92.12); the credits file names the
revived mod's own game version (92.16)."""
from __future__ import annotations

import contextlib
import io
import json
import unittest
from unittest.mock import patch

from tests.support import resolved_temp_dir


class SmallFixesTests(unittest.TestCase):
    def test_a_missing_dependency_is_named_not_a_traceback(self) -> None:
        from bridgeforge import cli

        err = io.StringIO()
        with patch.object(cli, "build_parser", side_effect=ModuleNotFoundError("No module named 'psutil'", name="psutil")), \
                contextlib.redirect_stderr(err):
            code = cli.main(["--help"])
        self.assertEqual(code, 2)
        self.assertIn("missing dependency 'psutil'", err.getvalue())
        self.assertIn("pip install -e .", err.getvalue())

    def test_credits_name_the_revived_game_version(self) -> None:
        from bridgeforge.descriptions import _credits

        with resolved_temp_dir() as root:
            (root / "mod_info.json").write_text(json.dumps({"name": "Mod", "author": "a", "gameVersion": "0.98.5a-RC7"}), encoding="utf-8")
            _credits(root, [("emp_station", "SHIP_SYSTEM")])
            text = (root / "BRIDGEFORGE_CREDITS.txt").read_text(encoding="utf-8")
        self.assertIn("Revival for Starsector 0.98.5a-RC7", text)
        self.assertNotIn("0.98a-RC8", text)


if __name__ == "__main__":
    unittest.main()
