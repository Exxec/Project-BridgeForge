from __future__ import annotations

import hashlib
import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from bridgeforge.cli import main
from bridgeforge.promotion import collect, hunks, normalise, render, shape, write_candidates
from tests.support import resolved_temp_dir

FINDING = "orbit-period-computed-unguarded"


def _attempt(queue: Path, name: str, before: str, after: str, *, packet: str = "p1", file: str = "data/Gen.java",
             outcome: str = "VERIFIED", moved: bool = False) -> Path:
    """A workspace whose working/ holds `before` and whose newest attempt holds `after`, with a verified agent ledger entry."""
    workspace = queue / name
    target = workspace / "working" / file
    target.parent.mkdir(parents=True)
    target.write_bytes(before.encode())
    attempt = workspace / "scratch" / "escalations" / packet / "attempt-1"
    (attempt / "working" / file).parent.mkdir(parents=True)
    (attempt / "working" / file).write_bytes(after.encode())
    (attempt / "START_TREE.json").write_text(json.dumps({file: hashlib.sha256(before.encode()).hexdigest()}), encoding="utf-8")
    if moved:
        target.write_bytes((before + "// changed later\n").encode())
    ledger = workspace / "reports" / "escalations" / "ledger.jsonl"
    ledger.parent.mkdir(parents=True)
    ledger.write_text(json.dumps({"packet": packet, "finding": FINDING, "runner": "agent", "outcome": outcome}) + "\n", encoding="utf-8")
    return workspace


BEFORE_A = "class A {\n    void f() {\n        float period = base * 2f;\n        planet.setOrbit(period);\n    }\n}\n"
AFTER_A = "class A {\n    void f() {\n        float period = Math.max(1f, base * 2f);\n        planet.setOrbit(period);\n    }\n}\n"
BEFORE_B = "class B {\n    void g() {\n        float days = radius * 9f;\n        moon.setOrbit(days);\n    }\n}\n"
AFTER_B = "class B {\n    void g() {\n        float days = Math.max(1f, radius * 9f);\n        moon.setOrbit(days);\n    }\n}\n"
BEFORE_C = "class C {\n    void h() {\n        star.setX(1);\n    }\n}\n"
AFTER_C = "class C {\n    void h() {\n        if (star != null) star.setX(1);\n    }\n}\n"


class NormaliseTests(unittest.TestCase):
    def test_identifiers_strings_and_numbers_become_placeholders_and_keywords_stay(self):
        self.assertEqual(normalise('  if (a.b("x y", 0.5f) != null)   return 12;'), "if (ID.ID(STR, NUM) != null) return NUM;")

    def test_hunks_split_a_unified_diff(self):
        diff = ["--- before", "+++ after", "@@ -1,2 +1,2 @@", " keep", "-old", "+fresh", "@@ -9 +9 @@", "+tail"]
        found = hunks(diff)
        self.assertEqual([(h["removed"], h["added"]) for h in found], [(["old"], ["fresh"]), ([], ["tail"])])
        self.assertEqual(found[0]["old"], ["keep", "old"])
        self.assertEqual(shape(found[0]), "- ID\n+ ID")


class PromotionTests(unittest.TestCase):
    def test_same_edit_on_different_identifiers_is_one_shape_and_a_different_edit_a_second(self):
        with resolved_temp_dir() as root:
            queue = root / "q"
            workspaces = {"A": _attempt(queue, "A", BEFORE_A, AFTER_A), "B": _attempt(queue, "B", BEFORE_B, AFTER_B),
                          "C": _attempt(queue, "C", BEFORE_C, AFTER_C)}
            collected = collect(workspaces, {FINDING})
        groups = collected["shapes"][FINDING]
        self.assertEqual(len(groups), 2)
        biggest = max(groups.values(), key=lambda slot: slot["count"])
        self.assertEqual((biggest["count"], sorted(biggest["mods"])), (2, ["A", "B"]))
        self.assertIn("        float period = base * 2f;", biggest["before"])
        self.assertIn("        float period = Math.max(1f, base * 2f);", biggest["after"])
        self.assertEqual({kind for kind, _ in groups}, {".java"})
        self.assertEqual(collected["skipped"], [])

    def test_unverified_and_moved_attempts_are_left_out_or_skipped(self):
        with resolved_temp_dir() as root:
            queue = root / "q"
            workspaces = {"A": _attempt(queue, "A", BEFORE_A, AFTER_A, outcome="FAILED"),
                          "B": _attempt(queue, "B", BEFORE_B, AFTER_B, moved=True)}
            collected = collect(workspaces, {FINDING})
        self.assertEqual(collected["shapes"][FINDING], {})
        self.assertEqual([(mod, why[:9]) for mod, _, why in collected["skipped"]], [("B", "no usable")])

    def test_render_and_example_limit(self):
        long_after = BEFORE_A + "".join(f"// extra {n}\n" for n in range(60))
        with resolved_temp_dir() as root:
            queue = root / "q"
            workspaces = {"A": _attempt(queue, "A", BEFORE_A, long_after), "B": _attempt(queue, "B", BEFORE_B, AFTER_B)}
            rows = [{"id": FINDING, "tier": "code", "verified_fixes": 3, "mods": ["A", "B", "C"]}]
            text = render(collect(workspaces, {FINDING}), rows)
            path = write_candidates(root / "out", rows, workspaces)
            written = path.read_text(encoding="utf-8")
        self.assertEqual(written, text)
        self.assertIn("## `orbit-period-computed-unguarded` (code, 3 verified fixes in 3 mods)", text)
        self.assertIn("### Shape 1: 1 hunk(s) in 1 mod(s), file kind `.java`", text)
        self.assertIn("... (", text)  # the 61-line addition is cut at 40

    def test_cli_writes_the_file_for_ids_with_enough_verified_fixes(self):
        with resolved_temp_dir() as root:
            queue = root / "q"
            for name, before, after in (("A", BEFORE_A, AFTER_A), ("B", BEFORE_B, AFTER_B), ("C", BEFORE_C, AFTER_C)):
                workspace = _attempt(queue, name, before, after)
                (workspace / "working" / "mod_info.json").write_text("{}", encoding="utf-8")
            # finding-stats needs a stored scan or mod_info per workspace; mod_info.json above suffices, and
            # PROMOTE_AFTER (3) verified fixes across 2+ mods make the id a candidate.
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(main(["finding-stats", str(queue), "--promotion", str(root / "out")]), 0)
            text = (root / "out" / "PROMOTION_CANDIDATES.md").read_text(encoding="utf-8")
        self.assertIn("`orbit-period-computed-unguarded`", text)
        self.assertIn("Shape 1: 2 hunk(s) in 2 mod(s)", text)


if __name__ == "__main__":
    unittest.main()
