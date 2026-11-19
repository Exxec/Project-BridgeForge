"""96.5 C7/C8: CI jobs share one setup step, carry a timeout, run tests buffered, and use the ruff the hooks use.

weekly.yml kept its own copy of the setup steps, drifted from ci.yml's and failed five weeks running (2026-10-19 to
2026-11-16). ruff was unpinned in CI and in the hooks, so a ruff release could fail one and not the other."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
SHARED_SETUP = "./.github/actions/setup-bridgeforge"
JOB = re.compile(r"^  ([A-Za-z0-9_-]+):\n", re.MULTILINE)


def jobs(workflow_text: str) -> dict[str, str]:
    """Each job's text under `jobs:`, by job id."""
    body = workflow_text[workflow_text.index("\njobs:\n"):]
    marks = list(JOB.finditer(body))
    return {match.group(1): body[match.end():(marks[i + 1].start() if i + 1 < len(marks) else len(body))]
            for i, match in enumerate(marks)}


def ruff_pin() -> str:
    match = re.search(r'^required-version = "==(.+)"$', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.MULTILINE)
    assert match, "pyproject.toml [tool.ruff] has no required-version pin"
    return match.group(1)


class WorkflowShapeTests(unittest.TestCase):
    def all_jobs(self) -> dict[str, str]:
        found = {}
        for workflow in sorted(WORKFLOWS.glob("*.yml")):
            for job, text in jobs(workflow.read_text(encoding="utf-8")).items():
                found[f"{workflow.name}:{job}"] = text
        self.assertGreater(len(found), 5)
        return found

    def test_every_job_has_a_timeout(self) -> None:
        # Without one, a hung job holds a runner for GitHub's default, six hours.
        for name, text in self.all_jobs().items():
            with self.subTest(job=name):
                self.assertRegex(text, r"\n    timeout-minutes: \d+\n")

    def test_jobs_that_run_the_suite_use_the_shared_setup(self) -> None:
        for name, text in self.all_jobs().items():
            if "bridgeforge.test_guard" not in text:
                continue
            with self.subTest(job=name):
                self.assertIn(f"uses: {SHARED_SETUP}", text)
                self.assertNotIn("actions/setup-java", text)

    def test_the_jdk_is_set_up_only_in_the_shared_action(self) -> None:
        for workflow in sorted(WORKFLOWS.glob("*.yml")):
            with self.subTest(workflow=workflow.name):
                self.assertNotIn("actions/setup-java", workflow.read_text(encoding="utf-8"))
        self.assertIn("actions/setup-java", (ROOT / SHARED_SETUP / "action.yml").read_text(encoding="utf-8"))

    def test_the_job_reader_splits_jobs(self) -> None:
        text = "on: push\njobs:\n  a:\n    runs-on: x\n    steps:\n      - run: one\n  b-c:\n    runs-on: y\n"
        self.assertEqual(sorted(jobs(text)), ["a", "b-c"])
        self.assertIn("run: one", jobs(text)["a"])
        self.assertNotIn("run: one", jobs(text)["b-c"])


class RuffPinTests(unittest.TestCase):
    def test_ci_runs_the_pinned_ruff(self) -> None:
        lint = jobs((WORKFLOWS / "ci.yml").read_text(encoding="utf-8"))["lint"]
        self.assertIn(f'version: "{ruff_pin()}"', lint)

    def test_the_hooks_and_the_pr_script_run_the_pinned_ruff(self) -> None:
        for path in ("tools/precommit-check.ps1", "tools/prepush-check.ps1"):
            with self.subTest(path=path):
                text = (ROOT / path).read_text(encoding="utf-8")
                self.assertIn('"ruff@$ruffPin"', text)
                self.assertIn("required-version", text)
        checks = (ROOT / ".claude" / "skills" / "bridgeforge-pr" / "scripts" / "checks.sh").read_text(encoding="utf-8")
        self.assertIn('uvx "ruff@${RUFF_PIN', checks)
        self.assertIn("required-version", checks)


class BufferedRunnerTests(unittest.TestCase):
    def test_suite_runners_buffer_test_output(self) -> None:
        # A passing test's prints buried the failures in CI logs; buffer=True shows a test's output only when it fails.
        for path in ("tests/run_partitioned.py", "tests/run_reversed.py"):
            with self.subTest(path=path):
                self.assertRegex((ROOT / path).read_text(encoding="utf-8"), r"TextTestRunner\([^)]*buffer=True")
        coverage = jobs((WORKFLOWS / "ci.yml").read_text(encoding="utf-8"))["coverage"]
        self.assertIn("unittest discover -b -s tests", coverage)


if __name__ == "__main__":
    unittest.main()
