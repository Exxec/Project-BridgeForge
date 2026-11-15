"""api_sources (ROADMAP-3 item 89, 2026-11-15): same descriptor, renamed parameter, as 0.98.5a's
Misc.getOfficerSalary(PersonAPI, boolean) went from `mercenary` to `checkIfInPopulatedSystem`."""
from __future__ import annotations

import unittest
import zipfile
from pathlib import Path

from bridgeforge.api_sources import parameter_renames, render_rename
from bridgeforge.target_impact import meaning_hits
from tests.support import resolved_temp_dir

OLD = ("package com.fs.starfarer.api.util;\npublic class Misc {\n"
       "  /** salary */\n  public static float getOfficerSalary(PersonAPI officer, boolean mercenary) { return 0; }\n"
       "  public static float getOfficerSalary(PersonAPI officer) { return 0; }\n"
       "  public static java.util.List<String> names(java.util.Map<String, Integer> byId, final int max) { return null; }\n"
       "  private static void hidden(int a) {}\n}\n")
NEW = OLD.replace("boolean mercenary", "boolean checkIfInPopulatedSystem").replace("hidden(int a)", "hidden(int b)")


def _core(root: Path, name: str, source: str) -> Path:
    core = root / name
    core.mkdir(parents=True)
    with zipfile.ZipFile(core / "starfarer.api.zip", "w") as archive:
        archive.writestr("com/fs/starfarer/api/util/Misc.java", source)
    return core


class ApiSourcesTests(unittest.TestCase):
    def test_only_a_renamed_public_parameter_with_the_same_types_is_reported(self) -> None:
        with resolved_temp_dir() as root:
            old, new = _core(root, "old", OLD), _core(root, "new", NEW)
            renames = parameter_renames(str(old / "starfarer.api.zip"), str(new / "starfarer.api.zip"))
        self.assertEqual(len(renames), 1)  # generics untouched, the private method ignored
        self.assertEqual(render_rename(renames[0]),
                         "com.fs.starfarer.api.util.Misc.getOfficerSalary(PersonAPI, boolean): boolean mercenary -> checkIfInPopulatedSystem")

    def test_target_impact_flags_a_mod_calling_it_with_that_arity(self) -> None:
        with resolved_temp_dir() as root:
            old, new = _core(root, "old", OLD), _core(root, "new", NEW)
            mod = root / "mod"
            mod.mkdir()
            (mod / "A.java").write_text("class A { float f(PersonAPI p) { return Misc.getOfficerSalary(p, true); } }", encoding="utf-8")
            (mod / "B.java").write_text("class B { float f(PersonAPI p) { return Misc.getOfficerSalary(p); } }", encoding="utf-8")
            hits = meaning_hits(mod, old, new, [])
            (mod / "A.java").unlink()
            none = meaning_hits(mod, old, new, [])
        self.assertEqual([h["kind"] for h in hits], ["parameter-meaning-changed"])
        self.assertEqual(none, [])  # the one-argument call is another method


if __name__ == "__main__":
    unittest.main()
