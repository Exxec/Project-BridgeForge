"""ROADMAP 70 H3.3: a ROADMAP item marked Done names what proves it."""
from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from bridgeforge.cli import main
from bridgeforge.roadmap_lint import items, load_baseline, roadmap_pages, roadmap_text, violations
from tests.support import resolved_temp_dir

ROOT = Path(__file__).resolve().parent.parent

SAMPLE = """1. **First item.** **Done 2026-10-01.** Built it. Tests: `tests/test_first.py`.
2. **Second item.** **Done 2026-10-02.** Built it, nothing proves it.
3. **Third item.** **Done 2026-10-03.** Live run GRP-THIRD-20261003 passed.
4. **Fourth item.** Proposed, not started.
   - 4a. **Sub item.** **Done.** Evidence in docs/FOURTH_PLAN.md.
   - 4b. **Sub item two.** **Done.** Nothing.
1. **Numbering restarts.** **Done 2026-10-04.** See tests/test_restart.py.
"""


class RoadmapLintTests(unittest.TestCase):
    def test_done_items_without_a_test_a_live_id_or_a_doc_are_found_and_proposals_are_not(self) -> None:
        found = {v["key"].split("|")[0] for v in violations(SAMPLE)}
        self.assertEqual(found, {"2", "4b"})
        self.assertEqual(len(items(SAMPLE)), 7)  # numbering that restarts still gives each item its own entry

    def test_the_command_fails_on_a_new_violation_and_tolerates_a_baselined_one(self) -> None:
        with resolved_temp_dir() as root:
            roadmap, baseline = root / "ROADMAP.md", root / "baseline.json"
            roadmap.write_text(SAMPLE, encoding="utf-8")
            baseline.write_text(json.dumps({"items": []}), encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["roadmap-lint", "--roadmap", str(roadmap), "--baseline", str(baseline)]), 1)
            keys = [v["key"] for v in violations(SAMPLE)]
            baseline.write_text(json.dumps({"items": keys}), encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["roadmap-lint", "--roadmap", str(roadmap), "--baseline", str(baseline)]), 0)

    def test_a_paged_roadmap_is_read_as_one_text_without_its_navigation_notes(self) -> None:
        # Owner 2026-10-18: the roadmap is paged under 64k tokens; a Done item without evidence on a later page must
        # still be found, and the repeated "(continued)" heading must not create an item or a violation of its own.
        nav = "<!-- page-nav:start -->\n> Page {} of 2.\n<!-- page-nav:end -->\n"
        with resolved_temp_dir() as root:
            first = root / "ROADMAP.md"
            first.write_text("# Roadmap\n\n" + nav.format(1) + "\n## Track\n\n" + SAMPLE.split("3. ")[0], encoding="utf-8")
            (root / "ROADMAP-2.md").write_text(nav.format(2) + "\n## Track (continued)\n\n3. " + SAMPLE.split("3. ", 1)[1],
                                               encoding="utf-8")
            self.assertEqual([p.name for p in roadmap_pages(first)], ["ROADMAP.md", "ROADMAP-2.md"])
            text = roadmap_text(first)
            self.assertNotIn("page-nav", text)
            self.assertNotIn("(continued)", text)
            self.assertEqual({v["key"].split("|")[0] for v in violations(text)}, {"2", "4b"})
            self.assertEqual(len(items(text)), 7)

    def test_the_real_roadmap_has_no_new_done_item_without_evidence_and_the_baseline_only_shrinks(self) -> None:
        text = roadmap_text(ROOT / "ROADMAP.md")  # every page of the paged roadmap
        tolerated = load_baseline(ROOT / "tests" / "roadmap_lint_baseline.json")
        current = {v["key"] for v in violations(text)}
        self.assertEqual(sorted(current - tolerated), [], "a Done item needs a test file, a Tests: line, a live test id or a docs/ file")
        self.assertEqual(sorted(tolerated - current), [], "a baselined item now has evidence: remove it from tests/roadmap_lint_baseline.json")


if __name__ == "__main__":
    unittest.main()
