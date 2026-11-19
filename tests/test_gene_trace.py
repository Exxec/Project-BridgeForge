"""94.G1 WP3 (GR-4): `gene trace ID` and the cross-repository check of the sister roadmaps and their contract pins."""
from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path

from bridgeforge.genome.sisters import PIN_PATH, check_entry, check_sisters, known_phases, section12
from bridgeforge.genome.trace import id_pattern, trace
from bridgeforge.paths import checkout_root
from tests.support import resolved_temp_dir
from tests.support import write_text as _write

PIN = "a" * 64


def _git(root: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.invalid", "GIT_CONFIG_NOSYSTEM": "1", "HOME": str(root)}
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True, env=env).stdout


class IdPatternTests(unittest.TestCase):
    def test_an_id_matches_only_whole(self) -> None:
        pattern = id_pattern("96.1")
        self.assertTrue(pattern.search("see 96.1."))
        self.assertTrue(pattern.search("(96.1, 96.2)"))
        self.assertFalse(pattern.search("96.10"))
        self.assertFalse(pattern.search("96.1.2"))
        self.assertFalse(id_pattern("94.G2").search("94.G21"))


class TraceTests(unittest.TestCase):
    def test_commits_their_pull_request_tests_and_documents_are_listed(self) -> None:
        with resolved_temp_dir() as root:
            _git(root, "init", "-q", "-b", "main")
            _write(root / "README.md", "start\n")
            _git(root, "add", "-A"); _git(root, "commit", "-q", "-m", "Initial")
            _git(root, "checkout", "-q", "-b", "feat")
            _write(root / "docs" / "plan.md", "Done under 94.G2.\nNot this: 94.G21\n")
            _write(root / "tests" / "test_thing.py", '"""94.G2: a test."""\n')
            _git(root, "add", "-A"); _git(root, "commit", "-q", "-m", "Add item 94.G2: the thing")
            _write(root / "other.md", "94.G21 only\n")
            _git(root, "add", "-A"); _git(root, "commit", "-q", "-m", "Add item 94.G21: another")
            _git(root, "checkout", "-q", "main")
            _git(root, "merge", "-q", "--no-ff", "feat", "-m", "Merge pull request #7 from owner/feat")
            result = trace("94.G2", root)
        self.assertEqual([c["subject"] for c in result["commits"]], ["Add item 94.G2: the thing"])
        self.assertEqual([p["pr"] for p in result["pull_requests"]], [7])
        self.assertEqual([t["path"] for t in result["tests"]], ["tests/test_thing.py"])
        self.assertEqual([(d["path"], d["count"]) for d in result["documents"]], [("docs/plan.md", 1)])


SECTION = """# Doc

## 12. Sister-repository entries

| Repository | Phases | Entry | Pull request |
|---|---|---|---|
| Alpha | 94.G3, 94.G5 | [`ROADMAP.md`, item 1](https://github.com/Owner/Alpha/blob/main/ROADMAP.md) | [Alpha#5](https://github.com/Owner/Alpha/pull/5) |
| Beta | 94.G6 | [`docs/R.md`](https://github.com/Owner/Beta/blob/master/docs/R.md#genome) | [Beta#6](https://github.com/Owner/Beta/pull/6) |

## 13. Next
"""
ROADMAP = "\n".join(f"- 94.G{n} **Phase {n}**" for n in range(1, 8)) + "\n"
GOOD = "Genome track: BridgeForge 94.G3 and 94.G5 (phases 94.G1-94.G7). GD-2, GR-1, GR-4. docs/FEATURE_GENOME_ROADMAP.md\n"


class SisterCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.row = section12(SECTION)[0]
        self.known = known_phases(ROADMAP)

    def test_section12_rows_give_phases_and_the_entry_file(self) -> None:
        rows = section12(SECTION)
        self.assertEqual([(r["repository"], r["phases"], r["owner"], r["repo"], r["ref"], r["path"]) for r in rows],
                         [("Alpha", ["94.G3", "94.G5"], "Owner", "Alpha", "main", "ROADMAP.md"),
                          ("Beta", ["94.G6"], "Owner", "Beta", "master", "docs/R.md")])
        self.assertEqual(self.known, {f"94.G{n}" for n in range(1, 8)})

    def test_a_complete_entry_passes_and_the_track_range_is_only_noted(self) -> None:
        result = check_entry(self.row, GOOD, self.known, None, PIN)
        self.assertEqual(result["problems"], [])
        self.assertIn("also mentions 94.G1, 94.G7 (not its phases in section 12)", result["notes"])
        self.assertTrue(any("no gene contract pin" in n for n in result["notes"]))

    def test_each_broken_promise_is_a_problem(self) -> None:
        cases = {
            "does not cite 94.G5, which section 12 lists for it": GOOD.replace(" and 94.G5", ""),
            "cites 94.G9, which ROADMAP-3 does not define": GOOD + "See 94.G9.\n",
            "does not cite GR-4": GOOD.replace(", GR-4", ""),
            "does not link docs/FEATURE_GENOME_ROADMAP.md": GOOD.replace("docs/FEATURE_GENOME_ROADMAP.md", ""),
        }
        for problem, text in cases.items():
            with self.subTest(problem):
                self.assertIn(problem, check_entry(self.row, text, self.known, None, PIN)["problems"])
        self.assertIn("entry file ROADMAP.md could not be read", check_entry(self.row, None, self.known, None, PIN)["problems"])

    def test_pin_drift_is_a_problem_and_a_current_pin_a_note(self) -> None:
        drift = check_entry(self.row, GOOD, self.known, "b" * 64 + "\n", PIN)
        self.assertTrue(any(p.startswith("pin drift:") for p in drift["problems"]), drift)
        current = check_entry(self.row, GOOD, self.known, PIN + "  CONTRACT.json\n", PIN)
        self.assertEqual(current["problems"], [])
        self.assertIn("gene contract pin current", current["notes"])
        self.assertIn(f"{PIN_PATH} holds no SHA-256", check_entry(self.row, GOOD, self.known, "pending\n", PIN)["problems"])

    def test_check_sisters_reads_each_entry_and_pin_through_the_reader(self) -> None:
        files = {("Alpha", "ROADMAP.md"): GOOD, ("Alpha", PIN_PATH): PIN,
                 ("Beta", "docs/R.md"): "94.G6 GD-2 GR-1 GR-4 FEATURE_GENOME_ROADMAP"}
        asked = []

        def read(owner, repo, ref, path):
            asked.append((owner, repo, ref, path))
            return files.get((repo, path))

        result = check_sisters(SECTION, ROADMAP, read, PIN)
        self.assertTrue(result["ok"], result)
        self.assertIn(("Owner", "Beta", "master", "docs/R.md"), asked)
        files[("Beta", "docs/R.md")] = "nothing here"
        self.assertFalse(check_sisters(SECTION, ROADMAP, read, PIN)["ok"])

    def test_the_real_section12_lists_six_linked_sister_repositories(self) -> None:
        doc = (checkout_root() / "docs" / "FEATURE_GENOME_ROADMAP.md").read_text(encoding="utf-8")
        rows = section12(doc)
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(r["path"] and r["phases"] for r in rows), rows)


if __name__ == "__main__":
    unittest.main()
