"""ROADMAP 70 H1.1/H1.2 ratchet: bare `.write_text(` and `shutil.rmtree(` call sites per module may only shrink.

Before bridgeforge/safeio.py existed there were 182 in-place writes and 15 unguarded tree deletes. New code uses
`atomic_write_text` / `safe_rmtree`; old call sites are converted as they are touched, and `tests/safeio_baseline.json` records what is
left. Regenerate it with `python -m tests.test_safeio_ratchet --write` only after converting sites, never to admit new ones.

Zip and jar entries (ROADMAP-3 93.33) have no baseline: every entry read goes through `zipsafe.read_limited`, `zipsafe.entry_sha256`
or a chunked stream, so an unbounded `ZipFile.read` anywhere in the package fails the test.
"""
from __future__ import annotations

import ast
import json
import re
import sys
import unittest
from pathlib import Path

from bridgeforge.source_paths import python_sources

PACKAGE = Path(__file__).resolve().parent.parent / "bridgeforge"
BASELINE = Path(__file__).resolve().parent / "safeio_baseline.json"
PATTERNS = {"write_text": re.compile(r"\.write_text\("), "rmtree": re.compile(r"shutil\.rmtree\(")}
EXEMPT = {"safeio.py"}  # the module that implements the safe versions
ZIP_EXEMPT = {"zipsafe.py"}  # the module that implements the bounded reads


def _is_zipfile(node: ast.AST) -> bool:
    target = node.func if isinstance(node, ast.Call) else node
    return (isinstance(target, ast.Attribute) and target.attr == "ZipFile") or (isinstance(target, ast.Name) and target.id == "ZipFile")


def _mentions_zipfile(node: ast.AST | None) -> bool:
    """An expression with a ZipFile in it anywhere: `ZipFile(...)` inside `cache.get(s) or cache.setdefault(s, ZipFile(p))`
    (supersession, missed until the 2026-11-17 review), or an annotation such as `zipfile.ZipFile | None`."""
    return node is not None and any(_is_zipfile(sub) for sub in ast.walk(node) if isinstance(sub, (ast.Call, ast.Attribute, ast.Name)))


def _scopes(tree: ast.Module) -> list[list[ast.AST]]:
    """The nodes of the module's own statements, then of each function (with the functions nested in it, for closures). Names
    are matched per scope: matched module-wide, a plain `with open(q, 'rb') as h: h.read()` was flagged because another
    function used `with a.open(i) as h` (review 2026-11-17)."""
    functions = (ast.FunctionDef, ast.AsyncFunctionDef)
    top = [node for statement in tree.body if not isinstance(statement, (*functions, ast.ClassDef)) for node in ast.walk(statement)]
    return [top, *[list(ast.walk(node)) for node in ast.walk(tree) if isinstance(node, functions)]]


def _zip_open(node: ast.AST, zips: set[str]) -> bool:
    """`z.open(...)` on a zip name of the scope, or `ZipFile(...).open(...)`."""
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "open"):
        return False
    owner = node.func.value
    return (isinstance(owner, ast.Name) and owner.id in zips) or (isinstance(owner, ast.Call) and _is_zipfile(owner))


def _scope_reads(nodes: list[ast.AST]) -> set[int]:
    zips: set[str] = set()
    for node in nodes:
        if isinstance(node, (ast.With, ast.AsyncWith)):
            zips |= {item.optional_vars.id for item in node.items
                     if isinstance(item.optional_vars, ast.Name) and isinstance(item.context_expr, ast.Call) and _is_zipfile(item.context_expr)}
        elif isinstance(node, ast.Assign) and _mentions_zipfile(node.value):
            zips |= {target.id for target in node.targets if isinstance(target, ast.Name)}
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and (_mentions_zipfile(node.value) or _mentions_zipfile(node.annotation)):
            zips.add(node.target.id)
        elif isinstance(node, ast.arg) and _mentions_zipfile(node.annotation):
            zips.add(node.arg)
    handles: set[str] = set()
    for node in nodes:
        if isinstance(node, (ast.With, ast.AsyncWith)):
            handles |= {item.optional_vars.id for item in node.items if isinstance(item.optional_vars, ast.Name) and _zip_open(item.context_expr, zips)}
        elif isinstance(node, ast.Assign) and _zip_open(node.value, zips):
            handles |= {target.id for target in node.targets if isinstance(target, ast.Name)}
    lines: set[int] = set()
    for node in nodes:
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "read"):
            continue
        owner, bare = node.func.value, not node.args and not node.keywords
        if (isinstance(owner, ast.Call) and _is_zipfile(owner)) or (isinstance(owner, ast.Name) and owner.id in zips):
            lines.add(node.lineno)
        elif bare and ((isinstance(owner, ast.Name) and owner.id in handles) or _zip_open(owner, zips)):
            lines.add(node.lineno)
    return lines


def unbounded_zip_reads(text: str) -> list[int]:
    """Lines that read a zip entry whole with no size bound: `.read(...)` on a ZipFile, or `.read()` without an argument on a
    handle from its `.open(...)` (named, or chained as `z.open(x).read()`)."""
    return sorted(set().union(*(_scope_reads(nodes) for nodes in _scopes(ast.parse(text)))))


def unbounded_zip_reads_by_module() -> dict[str, list[int]]:
    found: dict[str, list[int]] = {}
    for path in python_sources(PACKAGE):
        relative = path.relative_to(PACKAGE).as_posix()
        if relative in ZIP_EXEMPT:
            continue
        lines = unbounded_zip_reads(path.read_text(encoding="utf-8", errors="replace"))
        if lines:
            found[relative] = lines
    return found


def counts() -> dict[str, dict[str, int]]:
    found: dict[str, dict[str, int]] = {}
    for path in python_sources(PACKAGE):
        if path.relative_to(PACKAGE).as_posix() in EXEMPT:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        row = {name: len(pattern.findall(text)) for name, pattern in PATTERNS.items()}
        if any(row.values()):
            found[path.relative_to(PACKAGE).as_posix()] = {k: v for k, v in row.items() if v}
    return found


class SafeIoRatchetTests(unittest.TestCase):
    def test_bare_writes_and_tree_deletes_only_shrink(self) -> None:
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))["modules"]
        problems = []
        for module, row in counts().items():
            allowed = baseline.get(module, {})
            for kind, number in row.items():
                if number > allowed.get(kind, 0):
                    problems.append(f"{module}: {number} bare {kind}() call site(s), baseline {allowed.get(kind, 0)}")
        self.assertEqual(problems, [], "use bridgeforge.safeio (atomic_write_text / safe_rmtree) for new code, or convert the site instead of raising the baseline")

    def test_the_baseline_is_not_stale_after_conversions(self) -> None:
        """A converted site must lower the baseline too, or the next bare write hides under the old number."""
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))["modules"]
        current = counts()
        stale = [f"{m}: {k} baseline {n}, now {current.get(m, {}).get(k, 0)}" for m, row in baseline.items() for k, n in row.items()
                 if current.get(m, {}).get(k, 0) < n]
        self.assertEqual(stale, [], "run `python -m tests.test_safeio_ratchet --write` to record the lower counts")


class BoundedZipReadTests(unittest.TestCase):
    """ROADMAP-3 93.33: a hostile jar entry must not be read into memory whole."""

    def test_no_module_reads_a_zip_entry_without_a_bound(self) -> None:
        self.assertEqual(unbounded_zip_reads_by_module(), {},
                         "read zip and jar entries with bridgeforge.zipsafe.read_limited, hash them with entry_sha256, or stream them in chunks")

    def test_the_detector_finds_each_unbounded_form_and_passes_the_bounded_ones(self) -> None:
        cases = {
            "import zipfile\nwith zipfile.ZipFile(p) as a:\n    a.read('x')\n": [3],
            "import zipfile\ndef f(a: zipfile.ZipFile):\n    return a.read('x')\n": [3],
            "from zipfile import ZipFile\njar = ZipFile(p)\ndata = jar.read('x')\n": [3],
            "import zipfile\nzipfile.ZipFile(p).read('x')\n": [2],
            "import zipfile\nwith zipfile.ZipFile(p) as a:\n    with a.open(i) as h:\n        h.read()\n": [4],
            "import zipfile\nwith zipfile.ZipFile(p) as a:\n    with a.open(i) as h:\n        h.read(1024)\n": [],
            "import zipfile\nwith zipfile.ZipFile(p) as a:\n    read_limited(a, 'x')\n": [],
            "with open(p, 'rb') as h:\n    h.read()\n": [],
            # Forms the 2026-11-17 review found the first detector missed, and the false positive it found.
            "import zipfile\nhandle = cache.get(s) or cache.setdefault(s, zipfile.ZipFile(p))\nhandle.read('x')\n": [3],
            "import zipfile\ndef f(a: zipfile.ZipFile | None):\n    return a.read('x')\n": [3],
            "from zipfile import ZipFile\na: ZipFile = ZipFile(p)\na.read('x')\n": [3],
            "import zipfile\nwith zipfile.ZipFile(p) as a:\n    a.open('x').read()\n": [3],
            "import zipfile\nwith zipfile.ZipFile(p) as a:\n    h = a.open('x')\n    h.read()\n": [4],
            ("import zipfile\ndef f(p):\n    with zipfile.ZipFile(p) as a:\n        with a.open('x') as h:\n            h.read(10)\n"
             "def g(q):\n    with open(q, 'rb') as h:\n        return h.read()\n"): [],
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(unbounded_zip_reads(source), expected)


if __name__ == "__main__":
    if "--write" in sys.argv:
        BASELINE.write_text(json.dumps({"schema_version": 1, "modules": counts()}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        total = {k: sum(r.get(k, 0) for r in counts().values()) for k in PATTERNS}
        print("wrote", BASELINE, total)
    else:
        unittest.main()
