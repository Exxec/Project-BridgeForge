"""ROADMAP P14 item 24: no new hull-id set without skin resolution (the BF-SKIN-01 blind spot).

A variant or spawner may name a `.skin`'s id instead of a `.ship`'s, so a set of known hull ids built
from `.ship` files alone false-flags every skin reference. Item 17 found the second instance by hand.
This fails at review time instead: every function in `bridgeforge/` that builds hull ids from
`_ship_file_index(...)` or `_declared_spec_ids(..., "*.ship", ...)` must also use `_skin_index` or
`_resolve_hull_id`, or be listed in EXEMPT with the reason inline.
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "bridgeforge"
SKIN_AWARE = {"_skin_index", "_resolve_hull_id"}
EXEMPT = {
    # Both iterate ship_data.csv's own base-hull rows and look each up in the .ship index; a row id is
    # never a skin id, so there is no skin reference to resolve (item 17's audit, 2026-09-20).
    ("scanner.py", "_scan_carrier_bays_proposal"): "iterates ship_data.csv base-hull rows",
    ("scanner.py", "_scan_description_missing"): "iterates ship_data.csv base-hull rows",
}


def _called_names(node: ast.AST) -> set[str]:
    return {sub.func.id for sub in ast.walk(node) if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)}


def _builds_hull_ids(node: ast.AST) -> bool:
    for sub in ast.walk(node):
        if not (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)):
            continue
        if sub.func.id == "_ship_file_index":
            return True
        if sub.func.id == "_declared_spec_ids" and any(isinstance(arg, ast.Constant) and arg.value == "*.ship" for arg in sub.args):
            return True
    return False


def hull_id_builders() -> dict[tuple[str, str], bool]:
    """(module file, function) -> whether it is skin-aware, for every function building hull-id sets."""
    found: dict[tuple[str, str], bool] = {}
    for path in sorted(PACKAGE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _builds_hull_ids(node):
                found[(path.name, node.name)] = bool(_called_names(node) & SKIN_AWARE)
    return found


class HullIdResolutionAuditTests(unittest.TestCase):
    def test_every_hull_id_set_resolves_skins_or_is_exempt(self):
        builders = hull_id_builders()
        self.assertGreaterEqual(len(builders), 5, "the audit found too few call sites; has the helper been renamed?")
        unresolved = sorted(key for key, aware in builders.items() if not aware and key not in EXEMPT)
        self.assertEqual(unresolved, [], "these functions build hull ids from .ship files without _skin_index/_resolve_hull_id: "
                                         "resolve skins (see _scan_variant_validity) or add an EXEMPT entry with the reason")

    def test_exemptions_are_not_stale(self):
        builders = hull_id_builders()
        stale = sorted(key for key in EXEMPT if key not in builders or builders[key])
        self.assertEqual(stale, [], "these EXEMPT entries no longer build a skin-unaware hull-id set; remove them")

    def test_the_audit_catches_a_new_unresolved_builder(self):
        tree = ast.parse("def _scan_new(root, core):\n    hulls = set(_ship_file_index(root, core))\n")
        function = tree.body[0]
        self.assertTrue(_builds_hull_ids(function))
        self.assertFalse(_called_names(function) & SKIN_AWARE)
        spec = ast.parse('def f(root):\n    return _declared_spec_ids(root, "*.ship", "hullId")\n').body[0]
        self.assertTrue(_builds_hull_ids(spec))
        other = ast.parse('def f(root):\n    return _declared_spec_ids(root, "*.wpn", "id")\n').body[0]
        self.assertFalse(_builds_hull_ids(other))


if __name__ == "__main__":
    unittest.main()
