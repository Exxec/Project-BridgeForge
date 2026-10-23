"""B3 guard: internal code must use moved implementations, never consumer shims."""
from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
import unittest

from bridgeforge.source_paths import python_sources

ROOT = Path(__file__).resolve().parent.parent
MOVES = json.loads(Path(__file__).with_name("refactor_module_moves.json").read_text(encoding="utf-8"))


class RefactorImportTests(unittest.TestCase):
    def test_internal_imports_never_use_moved_paths_or_consumer_shims(self) -> None:
        old_modules = set(MOVES["moves"])
        shims = set(MOVES["shims"])
        new_modules = set(MOVES["moves"].values())
        problems = []
        for path in python_sources(ROOT / "bridgeforge"):
            relative = path.relative_to(ROOT).with_suffix("")
            module = ".".join(relative.parts)
            if module in shims:
                continue
            package = ".".join(relative.parent.parts)
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    target = importlib.util.resolve_name("." * node.level + (node.module or ""), package) if node.level else node.module
                    if target:
                        imported = [target + "." + alias.name for alias in node.names]
                        names = imported if all(name in new_modules for name in imported) else [target, *imported]
                elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                    if node.value.startswith("bridgeforge."):
                        names = [node.value]
                for name in names:
                    if any(name == new or name.startswith(new + ".") for new in new_modules):
                        continue
                    if any(name == old or name.startswith(old + ".") for old in old_modules):
                        problems.append(f"{path.relative_to(ROOT)}:{node.lineno}: {name}")
        self.assertEqual(problems, [], "internal code must import the moved implementation, not a compatibility path")


    def test_consumer_shims_reexport_implementation_objects(self) -> None:
        for old in MOVES["shims"]:
            shim = importlib.import_module(old)
            implementation = importlib.import_module(MOVES["moves"][old])
            names = [name for name in vars(implementation) if not name.startswith("_")]
            if old == "bridgeforge.scanner":
                names.append("_load_lenient_json_file")
            for name in names:
                with self.subTest(module=old, name=name):
                    self.assertIs(getattr(shim, name), getattr(implementation, name))


if __name__ == "__main__":
    unittest.main()
