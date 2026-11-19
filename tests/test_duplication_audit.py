"""94.G1 WP6: re-implementations of class indexing, mod identity, save reading and lenient JSON can only go down.

`tests/duplication_baseline.json` lists every function each rule of `bridgeforge.duplication_audit` finds. A new one fails
(call the canonical function the rule names instead); one that is gone fails too, so the baseline shrinks with each
consolidation. After a deliberate change: `python -m tests.test_duplication_audit --write`, and review the diff.
"""
from __future__ import annotations

import ast
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from bridgeforge import duplication_audit as dup
from bridgeforge.cli import main

PACKAGE = Path(dup.__file__).resolve().parent
BASELINE = Path(__file__).resolve().parent / "duplication_baseline.json"


def _hits(source: str, module: str = "x.py") -> list[str]:
    tree = ast.parse(source)
    return dup._rules_hit(tree.body[0], module)


class RatchetTests(unittest.TestCase):
    def test_no_new_re_implementation_and_no_stale_entry(self) -> None:
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))["rules"]
        found = dup.audit(PACKAGE)
        new = [f"{rule}: {name}" for rule, names in found.items() for name in names if name not in baseline.get(rule, [])]
        gone = [f"{rule}: {name}" for rule, names in baseline.items() for name in names if name not in found.get(rule, [])]
        self.assertEqual(new, [], "call the canonical function the rule names (bridgeforge/duplication_audit.py RULES)")
        self.assertEqual(gone, [], "a re-implementation is gone: run `python -m tests.test_duplication_audit --write` to lower the baseline")


class RuleTests(unittest.TestCase):
    def test_each_rule_finds_its_shape(self) -> None:
        self.assertIn("classfile-pool", _hits("def f(d):\n    tag = d[0]\n    if tag in (5, 6):\n        pass\n"))
        self.assertIn("classfile-pool", _hits("def f(d):\n    if tag in (C_LONG, C_DOUBLE):\n        pass\n"))
        self.assertIn("jar-class-walk", _hits("def f(z):\n    return [n for n in z.namelist() if n.endswith('.class')]\n"))
        self.assertIn("mod-info-read", _hits("def f(r):\n    return _load_lenient_json_file(r / 'mod_info.json')\n"))
        self.assertIn("version-text", _hits("def f(v):\n    return '.'.join(str(v[k]) for k in ('major', 'minor', 'patch'))\n"))
        self.assertIn("save-xml-read", _hits("def f(s):\n    return (s / 'descriptor.xml').read_text()\n"))
        self.assertIn("save-xml-read", _hits("def f(lines):\n    return [_TAG.match(x) for x in lines]\n", "save/x.py"))
        self.assertIn("json-comment-strip", _hits("def f(t):\n    return t.split('#')[0].split('//')[0]\n"))

    def test_what_the_canonical_way_looks_like_is_not_flagged(self) -> None:
        # A function that reads mod_info through read_mod_info may still parse another file itself.
        self.assertEqual(_hits("def f(r):\n    info = read_mod_info(r) or {}\n    return info, (r / 'mod_info.json'), json.loads('{}')\n"), [])
        self.assertEqual(_hits("def f(z, out):\n    for n in z.namelist():\n        if n.endswith('.class'):\n            out.writestr(n, b'')\n"), [])
        self.assertEqual(_hits("def f(lines):\n    return [_TAG.match(x) for x in lines]\n", "scan/x.py"), [])

    def test_a_nested_function_is_credited_once_and_the_audit_skips_itself(self) -> None:
        from tests.support import resolved_temp_dir, write_text as _write

        with resolved_temp_dir() as root:
            _write(root / "m.py", "def outer(z):\n    def inner():\n        return [n for n in z.namelist() if n.endswith('.class')]\n"
                                  "    return inner()\n")
            _write(root / dup.SELF, "def f(t):\n    return t.split('#')[0].split('//')[0]\n")
            found = dup.audit(root)
        self.assertEqual(found["jar-class-walk"], ["m.py::outer.inner"])
        self.assertEqual(found["json-comment-strip"], [])

    def test_the_cli_prints_the_report(self) -> None:
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(["duplication-audit"]), 0)
        self.assertIn("classfile-pool:", out.getvalue())
        self.assertIn("besides scan/scan_classfile.py::_parse_class_file_uncached", out.getvalue())


def write_baseline() -> None:
    from bridgeforge.safeio import atomic_write_text

    found = dup.audit(PACKAGE)
    atomic_write_text(BASELINE, json.dumps({"rules": found, "canonical": dup.RULES}, indent=2) + "\n", newline="")
    print(f"wrote {BASELINE} ({sum(len(v) for v in found.values())} functions)")


if __name__ == "__main__":
    if "--write" in sys.argv:
        write_baseline()
    else:
        unittest.main()
