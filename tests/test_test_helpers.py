"""96.5 C9: one shared fixture writer instead of a copy per test module."""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

from tests.support import resolved_temp_dir, write_text

ROOT = Path(__file__).resolve().parents[1]


def canonical_copies(source: str) -> list[int]:
    """Lines of top-level `_write(path, text)` functions that only make the parent folder and write `text`: the copy
    tests/support.write_text replaces. Variants (other parameters, a return value, bytes or JSON) are not counted."""
    found = []
    for node in ast.parse(source).body:
        if not isinstance(node, ast.FunctionDef) or node.name != "_write":
            continue
        if [a.arg for a in node.args.args] != ["path", "text"] or node.args.defaults:
            continue
        body = [stmt for stmt in node.body if not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant))]
        calls = [ast.unparse(stmt.value) for stmt in body if isinstance(stmt, ast.Expr)]
        if len(body) == 2 and len(calls) == 2 and calls[0].startswith("path.parent.mkdir(") and \
                calls[1].startswith(("path.write_text(text", "path.write_bytes(text.encode(")):
            found.append(node.lineno)
    return found


class SharedWriterTests(unittest.TestCase):
    def test_the_writer_makes_folders_and_writes_lf_utf8(self) -> None:
        with resolved_temp_dir() as root:
            target = root / "a" / "b" / "c.txt"
            write_text(target, "one\ntwo é\n")
            self.assertEqual(target.read_bytes(), "one\ntwo é\n".encode("utf-8"))  # LF on Windows too

    def test_no_test_module_keeps_its_own_copy(self) -> None:
        copies = {}
        for path in sorted((ROOT / "tests").glob("test_*.py")):
            lines = canonical_copies(path.read_text(encoding="utf-8-sig"))
            if lines:
                copies[path.name] = lines
        self.assertEqual(copies, {}, "use `from tests.support import write_text as _write`")

    def test_the_detector_finds_the_copy_and_leaves_variants(self) -> None:
        source = ("def _write(path: Path, text: str) -> None:\n    path.parent.mkdir(parents=True, exist_ok=True)\n"
                  "    path.write_text(text, encoding='utf-8')\n\n"
                  "def _write(path: Path, data: object) -> None:\n    path.parent.mkdir(parents=True, exist_ok=True)\n"
                  "    path.write_text(json.dumps(data), encoding='utf-8')\n")
        self.assertEqual(canonical_copies(source), [1])


if __name__ == "__main__":
    unittest.main()
