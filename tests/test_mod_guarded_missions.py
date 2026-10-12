"""REG-20261012: a mission's variants inside an `if (otherModEnabled)` block are not this mod's missing references."""
from __future__ import annotations

import unittest

from bridgeforge.probe_config import _mission_fleet_refs
from bridgeforge.scan_javatext import _blank_java_comments, _blank_mod_guarded_blocks
from tests.support import resolved_temp_dir

SOURCE = """
boolean swp = Global.getSettings().getModManager().isModEnabled("swp");
boolean vsp = Global.getSettings().getModManager().isModEnabled("vayrashippack");
api.addToFleet(FleetSide.PLAYER, "own_ship", FleetMemberType.SHIP, true);
if (swp) {
    api.addToFleet(FleetSide.ENEMY, "swp_gryphon", FleetMemberType.SHIP, false);
    if (x) { api.addToFleet(FleetSide.ENEMY, "swp_nested", FleetMemberType.SHIP, false); }
}
if (vsp && swp) {
    api.addToFleet(FleetSide.ENEMY, "vayra_both", FleetMemberType.SHIP, false);
} else {
    api.addToFleet(FleetSide.ENEMY, "else_ship", FleetMemberType.SHIP, false);
}
if (!swp) {
    api.addToFleet(FleetSide.ENEMY, "negated_ship", FleetMemberType.SHIP, false);
}
if (Global.getSettings().getModManager().isModEnabled("Imperium")) {
    api.addToFleet(FleetSide.ENEMY, "ii_direct", FleetMemberType.SHIP, false);
}
if (somethingElse) {
    api.addToFleet(FleetSide.ENEMY, "plain_ship", FleetMemberType.SHIP, false);
}
api.addToFleet(FleetSide.ENEMY, "unguarded_missing", FleetMemberType.SHIP, false);
"""


class GuardedBlockTests(unittest.TestCase):
    def test_only_blocks_that_test_for_another_mod_are_blanked(self) -> None:
        blanked = _blank_mod_guarded_blocks(_blank_java_comments(SOURCE))
        for kept in ("own_ship", "else_ship", "negated_ship", "plain_ship", "unguarded_missing"):
            self.assertIn(kept, blanked)
        for dropped in ("swp_gryphon", "swp_nested", "vayra_both", "ii_direct"):
            self.assertNotIn(dropped, blanked)
        self.assertEqual(blanked.count("\n"), SOURCE.count("\n"))

    def test_the_probe_config_lists_only_the_unguarded_references(self) -> None:
        with resolved_temp_dir() as root:
            mission = root / "data" / "missions" / "m1"
            mission.mkdir(parents=True)
            (mission / "MissionDefinition.java").write_text(SOURCE, encoding="utf-8")
            refs = _mission_fleet_refs(root)
        self.assertEqual(refs["ship"], ["else_ship", "negated_ship", "own_ship", "plain_ship", "unguarded_missing"])


if __name__ == "__main__":
    unittest.main()


class LoadClassOrThrowTests(unittest.TestCase):
    """REG7-20261012: Vayra's Ship Pack stopped at load without LazyLib but declared no dependency."""

    def test_a_loadclass_check_whose_catch_throws_makes_the_library_required(self) -> None:
        from bridgeforge.scan_libraries import _loads_library_class_or_throws
        required = 'try { Global.getSettings().getScriptClassLoader().loadClass("org.lazywizard.lazylib.ModUtils"); } catch (ClassNotFoundException e) { throw new ClassNotFoundException("LazyLib is required"); }'
        optional = 'try { Global.getSettings().getScriptClassLoader().loadClass("org.lazywizard.lazylib.ModUtils"); } catch (ClassNotFoundException e) { log.info("no lazylib"); }'
        self.assertTrue(_loads_library_class_or_throws(required, "LazyLib"))
        self.assertFalse(_loads_library_class_or_throws(optional, "LazyLib"))
        self.assertFalse(_loads_library_class_or_throws("int x = 1;", "LazyLib"))
        # a probe whose catch only sets a flag, followed by an unrelated later try that throws (Neutrino's NCModPlugin)
        probe_then_throw = ('try { x.loadClass("org.lazywizard.lazylib.ModUtils"); ok = true; } catch (ClassNotFoundException e) { ok = false; }'
                            ' try { y(); } catch (Exception e) { throw new RuntimeException(e); }')
        self.assertFalse(_loads_library_class_or_throws(probe_then_throw, "LazyLib"))
