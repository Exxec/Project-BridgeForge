from __future__ import annotations

import ast
import unittest
from pathlib import Path

SCANNER_PATH = Path(__file__).resolve().parent.parent / "bridgeforge" / "scanner.py"

# ROADMAP P14 item 24: every function that builds a hull-id set from *.ship files or
# _ship_file_index must also resolve a .skin's baseHullId chain, or be on this exemption list
# with its reasoning written down - never by silent omission. Exemptions confirmed by item 17's
# manual audit (2026-09-20): both iterate ship_data.csv's own base-hull rows, which are never skin
# ids, so there is nothing to chase.
EXEMPT_SKIN_CHAIN_RESOLUTION = {
    "_scan_carrier_bays_proposal": "iterates ship_data.csv's own base-hull rows, never skin ids",
    "_scan_description_missing": "iterates ship_data.csv's own base-hull rows, never skin ids",
}

# Any of these appearing in a function body counts as "resolves the skin chain."
SKIN_RESOLUTION_MARKERS = ("_skin_index", "_resolve_hull_id")

HULL_ID_BUILDER_CALLS = ("_ship_file_index",)


def _calls_declared_spec_ids_for_ships(node: ast.Call) -> bool:
    if not (isinstance(node.func, ast.Name) and node.func.id == "_declared_spec_ids"):
        return False
    for arg in node.args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value == "*.ship":
            return True
    return False


def _calls_hull_id_builder(node: ast.Call) -> bool:
    return isinstance(node.func, ast.Name) and node.func.id in HULL_ID_BUILDER_CALLS


def find_unresolved_hull_id_builders() -> list[str]:
    """Function names in scanner.py that build a hull-id set without resolving the skin chain.

    Empty when every call site either resolves skins or is on EXEMPT_SKIN_CHAIN_RESOLUTION.
    """
    source = SCANNER_PATH.read_text(encoding="utf-8")
    lines = source.splitlines()
    tree = ast.parse(source)
    offenders: list[str] = []
    for func in ast.walk(tree):
        if not isinstance(func, ast.FunctionDef):
            continue
        builds_hull_ids = any(
            isinstance(node, ast.Call) and (_calls_declared_spec_ids_for_ships(node) or _calls_hull_id_builder(node))
            for node in ast.walk(func)
        )
        if not builds_hull_ids:
            continue
        if func.name in EXEMPT_SKIN_CHAIN_RESOLUTION:
            continue
        body_text = "\n".join(lines[func.lineno - 1 : func.end_lineno])
        if not any(marker in body_text for marker in SKIN_RESOLUTION_MARKERS):
            offenders.append(func.name)
    return offenders


class SkinChainResolutionAuditTests(unittest.TestCase):
    """A dev-facing check for the exact blind spot BF-SKIN-01 exposed (ROADMAP P14 items 17/24):
    a function that builds a "known hull ids" set from *.ship files or _ship_file_index but never
    chases a .skin's baseHullId chain will false-flag real, campaign-wired content that only
    exists as a skin (found by hand on Leon-Heavy-Industries, 2026-09-20). This fails at review
    time if a new such function is added without either resolving skins or being added to
    EXEMPT_SKIN_CHAIN_RESOLUTION with its reasoning written down.
    """

    def test_every_hull_id_builder_resolves_skins_or_is_exempt(self) -> None:
        offenders = find_unresolved_hull_id_builders()
        self.assertEqual(
            offenders, [],
            "These scanner.py functions build a hull-id set from *.ship/_ship_file_index without "
            "resolving a .skin's baseHullId chain, and are not on EXEMPT_SKIN_CHAIN_RESOLUTION: "
            f"{offenders}. Either make them consult _skin_index/_resolve_hull_id, or add them to "
            "the exemption list with the reason (see BF-SKIN-01 in docs/BUG_CLASSES.md).",
        )

    def test_exemption_list_entries_still_exist_and_are_unresolved_by_design(self) -> None:
        source = SCANNER_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        func_names = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        for name in EXEMPT_SKIN_CHAIN_RESOLUTION:
            self.assertIn(name, func_names, f"exempted function {name!r} no longer exists in scanner.py - remove it from the exemption list")

    def test_at_least_the_known_skin_resolving_functions_still_resolve(self) -> None:
        # Guards against the check itself going stale/silent if scanner.py is refactored so no
        # function matches the AST pattern at all (e.g. the call is renamed) - the known-good
        # instances from item 17's audit must still be found and still pass.
        source = SCANNER_PATH.read_text(encoding="utf-8")
        lines = source.splitlines()
        tree = ast.parse(source)
        known_resolving = {
            "_scan_campaign_fleet_references",
            "_scan_mission_local_fleet_references",
            "_scan_variant_validity",
        }
        found = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name in known_resolving}
        self.assertEqual(found, known_resolving, "one of item 17's known skin-resolving functions was renamed or removed - update this test")
        for func in ast.walk(tree):
            if isinstance(func, ast.FunctionDef) and func.name in known_resolving:
                body_text = "\n".join(lines[func.lineno - 1 : func.end_lineno])
                self.assertTrue(
                    any(marker in body_text for marker in SKIN_RESOLUTION_MARKERS),
                    f"{func.name} no longer resolves the skin chain",
                )


if __name__ == "__main__":
    unittest.main()
