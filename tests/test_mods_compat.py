"""mods-compat (ROADMAP 50): hooks claimed by two or more mods in a real mods folder."""
from __future__ import annotations

import unittest

from bridgeforge.mods_compat import mods_compat
from tests.support import resolved_temp_dir

HEADER = "id,name,cost mult,build time,income,upkeep,downgrade,upgrade,tags,data,image,plugin,desc,order\n"


class ModsCompatTests(unittest.TestCase):
    def test_two_mods_claiming_one_hook_is_a_conflict(self) -> None:
        with resolved_temp_dir() as root:
            core = root / "core"
            (core / "data" / "campaign").mkdir(parents=True)
            (core / "data" / "campaign" / "industries.csv").write_text(HEADER + "population,Pop,,,,,,,,,,com.fs.Pop,,1\n", encoding="utf-8")
            (core / "data" / "scripts" / "plugins").mkdir(parents=True)
            (core / "data" / "scripts" / "plugins" / "LevelupPluginImpl.java").write_text("class L {}", encoding="utf-8")
            mods = root / "mods"
            for name, plugin in (("A", "a.Pop"), ("B", "b.Pop")):
                (mods / name / "data" / "campaign").mkdir(parents=True)
                (mods / name / "mod_info.json").write_text('{"id": "%s"}' % name.lower(), encoding="utf-8")
                (mods / name / "data" / "campaign" / "industries.csv").write_text(HEADER + f"population,Pop,,,,,,,,,,{plugin},,1\n", encoding="utf-8")
            (mods / "C" / "data" / "scripts" / "plugins").mkdir(parents=True)
            (mods / "C" / "mod_info.json").write_text('{"id": "c"}', encoding="utf-8")
            (mods / "C" / "data" / "scripts" / "plugins" / "LevelupPluginImpl.java").write_text("class L {}", encoding="utf-8")
            result = mods_compat(mods, core, root / "out", quiet=True)
            checkpoint_left = (root / "out" / "MODS_COMPAT.partial.jsonl").exists()
        self.assertEqual([(c["kind"], c["key"], [o["mod"] for o in c["mods"]]) for c in result["conflicts"]],
                         [("industry-plugin", "population", ["A", "B"])])  # C's lone shadow is not a conflict
        self.assertFalse(checkpoint_left)


if __name__ == "__main__":
    unittest.main()
