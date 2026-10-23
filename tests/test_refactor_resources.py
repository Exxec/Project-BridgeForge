"""Resource locations must retain their meaning when source modules move."""
import importlib
import json
from pathlib import Path
import unittest

from bridgeforge.atlas import atlas_predictions


class RefactorResourceTests(unittest.TestCase):
    def test_atlas_predictions_still_uses_the_repo_docs_file(self) -> None:
        expected = Path(__file__).resolve().parent.parent / "docs" / "atlas_predictions.json"
        self.assertEqual(atlas_predictions.DEFAULT_PATH, expected)
        self.assertTrue(expected.is_file())

    def test_moved_resources_keep_their_original_locations(self) -> None:
        root = Path(__file__).resolve().parent.parent
        moves = json.loads((root / "tests/refactor_module_moves.json").read_text())["moves"]
        resources = [
            ("probe_config", "PROFILE_DIR", False, "bridgeforge/probe_profiles"),
            ("probe_mod_build", "_JANINO_HARNESS", False, "bridgeforge/java/JaninoCheck.java"),
            ("rig_doctor", "_repo_root", True, "."),
            ("bytecode", "_source", True, "bridgeforge/java/BridgeforgeBytecode.java"),
            ("java_ast", "_helper_source", True, "bridgeforge/java/BridgeforgeAst.java"),
            ("java_toolchain", "REPO_ROOT", False, "."),
        ]
        for leaf, attr, call, relative in resources:
            old = "bridgeforge." + leaf
            if old not in moves:
                continue
            with self.subTest(module=leaf):
                value = getattr(importlib.import_module(moves[old]), attr)
                value = value() if call else value
                self.assertEqual(value.resolve(), (root / relative).resolve())
                self.assertTrue(value.exists())
