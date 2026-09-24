"""Generated reference docs stay current, and untested finding ids can only shrink (2026-09-14)."""

import json
import unittest
from pathlib import Path

from bridgeforge.checks_index import UNTESTED_BASELINE, bug_class_links, build_checks_index, build_commands_index, collect, gather

REPO = Path(__file__).resolve().parent.parent

SAMPLE = '''
RULES = {
    "sun.misc": ("internal-jvm-api", "An internal JVM API import. It may break."),
    "java.security.SecurityManager": ("security-manager", "SecurityManager is obsolete."),
}

def _scan_sources(text, result):
    for needle, (rule_id, explanation) in RULES.items():
        if needle in text:
            result.add(id=rule_id, category="c", severity="high", classification="REVIEW", confidence="HIGH", explanation=explanation)

def _scan_thing(root, result):
    guarded = True
    result.add(id="thing-found", category="c", severity="low" if guarded else "medium",
               classification="SAFE" if guarded else "REVIEW", confidence="HIGH",
               explanation="First sentence here. Second sentence is dropped.")
    for library in ("A", "B"):
        result.add(id=f"bundled-{library.lower()}", category="c", severity="info", classification="REVIEW",
                   confidence="HIGH", explanation=f"Bundled {library} archive detected. More.")
    seen = set()
    seen.add("not-a-finding")

def audit():
    _issue("claim-stale", "WARNING", "Report says so. More.", [])
'''

REGISTRY = """| Bug class | Symptom | Root cause | Check / probe assertion | Test file | First mod hit |
| --- | --- | --- | --- | --- | --- |
| EX-NPE-001 / FLX-KNOWN-01 | x | y | `faction-known-lists-missing` | `tests/test_scanner.py` | Exigency |
| EX-MARKET-01 | x | y | `faction-known-lists-missing`; probe assertion `submarket-stock` | t | Exigency |
"""


class ChecksIndexTests(unittest.TestCase):
    def test_conditional_values_table_and_computed_ids_are_extracted(self) -> None:
        checks, issues = collect(SAMPLE, "sample.py")
        self.assertEqual(sorted(checks), ["bundled-{...}", "internal-jvm-api", "security-manager", "thing-found"])
        self.assertEqual(checks["thing-found"].classifications, {"SAFE", "REVIEW"})
        self.assertEqual(checks["thing-found"].severities, {"low", "medium"})
        self.assertEqual(checks["thing-found"].where, {"sample.py:_scan_thing"})
        self.assertEqual(checks["thing-found"].explanation, "First sentence here.")
        self.assertEqual(checks["bundled-{...}"].explanation, "Bundled {...} archive detected.")
        self.assertEqual(checks["internal-jvm-api"].explanation, "An internal JVM API import.")
        self.assertEqual(sorted(issues), ["claim-stale"])

    def test_bug_class_links_split_combined_rows(self) -> None:
        links = bug_class_links(REGISTRY)
        self.assertEqual(links["faction-known-lists-missing"], ["EX-MARKET-01", "EX-NPE-001", "FLX-KNOWN-01"])
        self.assertEqual(links["submarket-stock"], ["EX-MARKET-01"])

    def test_committed_docs_are_current(self) -> None:
        for name, text in (("CHECKS.md", build_checks_index(REPO)), ("COMMANDS.md", build_commands_index())):
            committed = (REPO / "docs" / name).read_text(encoding="utf-8").splitlines()
            self.assertEqual(committed, text.splitlines(), f"docs/{name} is stale: run `python -m bridgeforge docs-index`")

    def test_path_defaults_render_the_same_on_every_os(self) -> None:
        import argparse
        from pathlib import PureWindowsPath

        from bridgeforge.checks_index import _argument_rows

        parser = argparse.ArgumentParser()
        parser.add_argument("--db", default=PureWindowsPath("bridgeforge-state") / "corpus-index.sqlite")
        self.assertIn("default bridgeforge-state/corpus-index.sqlite", "\n".join(_argument_rows(parser)))

    def test_commands_index_covers_nested_subcommands(self) -> None:
        text = build_commands_index()
        for heading in ("## scan", "## compat-set install", "## expect approve", "## docs-index", "## preset-check"):
            self.assertIn(heading, text)

    def test_untested_findings_can_only_shrink(self) -> None:
        # Every new finding id needs a test that names it; ids leave the baseline once one does.
        baseline = set(json.loads((REPO / UNTESTED_BASELINE).read_text(encoding="utf-8"))["untested"])
        current = set(gather(REPO).untested)
        self.assertFalse(current - baseline, f"new finding ids without a test naming them: {sorted(current - baseline)}")
        self.assertFalse(baseline - current, f"now tested (or gone): remove from {UNTESTED_BASELINE.as_posix()}: {sorted(baseline - current)}")


if __name__ == "__main__":
    unittest.main()
