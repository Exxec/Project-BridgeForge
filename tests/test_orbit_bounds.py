"""The interval proof behind the orbit-period clamp (ROADMAP item 73 B1 / item 75 R4)."""
from __future__ import annotations

import unittest

from bridgeforge.orbit_bounds import Unproven, prove


class OrbitBoundsTests(unittest.TestCase):
    def test_zero_and_negative_literals_have_exact_bounds(self) -> None:
        self.assertEqual(prove("0f", ""), (0.0, 0.0))
        self.assertEqual(prove("-3f * 2", ""), (-6.0, -6.0))
        self.assertEqual(prove("Math.random() * 4f - 6f", ""), (-6.0, -2.0))

    def test_division_by_a_divisor_bounded_away_from_zero_is_finite(self) -> None:
        low, high = prove("5f / (10f + Math.random() * 5f)", "")
        self.assertAlmostEqual(low, 5 / 15)
        self.assertAlmostEqual(high, 0.5)

    def test_integer_division_widens_by_one(self) -> None:
        self.assertEqual(prove("7 / 2", ""), (2.5, 4.5))

    def test_nan_and_infinity_sources_are_unproven(self) -> None:
        for expression in ("0f / 0f", "1f / 0", "1f / (Math.random())", "1f / (Math.random() - 0.5f)", "Float.NaN", "Float.POSITIVE_INFINITY",
                           "Double.NaN * 2"):
            with self.subTest(expression=expression), self.assertRaises(Unproven):
                prove(expression, "")

    def test_side_effects_and_unknown_members_are_unproven(self) -> None:
        for expression in ("i++", "--i", "i = 3", "i += 1", "foo()", "this.x", "a[0]", "x > 1 ? 2 : 3", "Math.sqrt(4)"):
            with self.subTest(expression=expression), self.assertRaises(Unproven):
                prove(expression, "")

    def test_variables_need_one_assignment_and_a_provable_initializer(self) -> None:
        self.assertEqual(prove("d", "float d = Math.random() * 2f;"), (0.0, 2.0))
        with self.assertRaises(Unproven):
            prove("d", "float d = Math.random(); d = 5f;")
        with self.assertRaises(Unproven):
            prove("d", "float d = foo();")
        with self.assertRaises(Unproven):
            prove("param", "void m(float param) { }")
        with self.assertRaises(Unproven):
            prove("d", "float d = d / 2f;")


if __name__ == "__main__":
    unittest.main()
