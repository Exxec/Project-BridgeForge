"""Translated jar strings reach the class's shipped source too (ROADMAP-3 item 92.33, 2026-11-16): Eridani Combine's 18 ECE.jar
strings were translated while src/ kept the Chinese, so a src-to-jar rebuild would have reverted them."""
from __future__ import annotations

import unittest

from bridgeforge.translation import apply_translation, export_translation
from tests.support import resolved_temp_dir
from tests.test_translation import _class_with_string, _jar, _write


class JarSourceMirrorTests(unittest.TestCase):
    def test_a_translated_jar_string_is_mirrored_into_src(self) -> None:
        with resolved_temp_dir() as root:
            mod = root / "mod"
            _write(mod / "mod_info.json", '{"id": "fx", "name": "Fx", "jars": ["jars/fx.jar"]}\n')
            _jar(mod / "jars" / "fx.jar", {"data/scripts/Gen.class": _class_with_string("data/scripts/Gen", "当前加成")})
            _write(mod / "src" / "data" / "scripts" / "Gen.java",
                   'package data.scripts;\nclass Gen { String s = "当前加成"; String other = "保持"; }\n')
            document = export_translation(mod)
            for entry in document["entries"]:
                if entry["kind"] == "jar":
                    entry["translation"] = "Current bonus"
            result = apply_translation(mod, document, in_place=True)
            source = (mod / "src" / "data" / "scripts" / "Gen.java").read_text(encoding="utf-8")
        self.assertIn('String s = "Current bonus";', source)
        self.assertIn('"保持"', source)  # a literal the jar entry does not name is left alone
        self.assertEqual(result["applied"].get("jar-source"), 1)


if __name__ == "__main__":
    unittest.main()
