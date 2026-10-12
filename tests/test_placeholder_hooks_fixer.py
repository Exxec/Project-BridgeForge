"""runtime-placeholder-unsupported-operation fixer: Neutrino's IDE-stub *Override hooks (2026-10-11)."""
from __future__ import annotations

import unittest

from bridgeforge.fixers import FixerError, _fix_runtime_placeholder_hooks
from tests.support import resolved_temp_dir

STUB = '        throw new UnsupportedOperationException("Not supported yet."); //To change body of generated methods, choose Tools | Templates.\n'
SCRIPT = (
    "public class S implements ShipSystemStatsScript {\n"
    "    @Override\n    public float getActiveOverride(ShipAPI ship) {\n" + STUB + "    }\n"
    "    @Override\n    public int getUsesOverride(com.fs.starfarer.api.combat.ShipAPI ship) {\n" + STUB + "    }\n"
    "    @Override\n    public Object other() {\n" + STUB + "    }\n"
    "}\n")


def _run(text: str, rel: str = "src/data/shipsystems/scripts/S.java"):
    with resolved_temp_dir() as root:
        path = root / rel
        path.parent.mkdir(parents=True)
        path.write_text(text, encoding="utf-8")
        finding = {"id": "runtime-placeholder-unsupported-operation", "file": rel, "evidence": []}
        return _fix_runtime_placeholder_hooks(root, {"scan_findings": [finding]})


def _text(changes) -> str:
    return changes[0].after.decode("utf-8").replace(chr(13) + chr(10), chr(10))


class PlaceholderHookTests(unittest.TestCase):
    def test_override_hooks_return_minus_one_with_the_right_type(self) -> None:
        text = _text(_run(SCRIPT))
        self.assertIn("getActiveOverride(ShipAPI ship) {\n        return -1f;", text)
        self.assertIn("getUsesOverride(com.fs.starfarer.api.combat.ShipAPI ship) {\n        return -1;", text)

    def test_other_placeholders_stay_untouched(self) -> None:
        text = _text(_run(SCRIPT))
        self.assertEqual(text.count("UnsupportedOperationException"), 1)
        self.assertIn("public Object other() {\n" + STUB, text)

    def test_a_file_with_only_other_placeholders_is_refused(self) -> None:
        with self.assertRaises(FixerError):
            _run("class X { public Object other() {\n" + STUB + "} }\n")


class BlackHoleFlagFixerTests(unittest.TestCase):
    PLANETS = ('{\n\t"neut_star_blackhole":{\n\t\t"name":"V404",\n\t\t"isStar":true,\n\t\t"lightPosition":[0,0,10],\n\t},\n'
               '\t"other_star":{\n\t\t"isStar":true,\n\t},\n}\n')

    def _fix(self, text: str, type_id: str = "neut_star_blackhole"):
        from bridgeforge.fixers import _fix_black_hole_type_missing_flag

        with resolved_temp_dir() as root:
            path = root / "data" / "config" / "planets.json"
            path.parent.mkdir(parents=True)
            path.write_text(text, encoding="utf-8", newline="")
            finding = {"id": "black-hole-type-missing-flag", "file": "data/config/planets.json", "evidence": [f"type:{type_id}"]}
            return _fix_black_hole_type_missing_flag(root, {"scan_findings": [finding]})[0].after.decode("utf-8")

    def test_flag_is_added_to_the_named_type_only(self) -> None:
        text = self._fix(self.PLANETS)
        self.assertEqual(text.count("isBlackHole"), 1)
        self.assertLess(text.index("isBlackHole"), text.index("other_star"))

    def test_last_key_without_a_comma_still_gets_valid_placement(self) -> None:
        text = self._fix('{\n\t"bh":{\n\t\t"isStar":true\n\t},\n}\n', "bh")
        self.assertIn('"isStar":true,', text)
        self.assertIn('"isBlackHole":true', text)

    def test_unknown_type_is_refused(self) -> None:
        with self.assertRaises(FixerError):
            self._fix(self.PLANETS, "missing_type")


if __name__ == "__main__":
    unittest.main()
