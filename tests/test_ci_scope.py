"""ROADMAP-3 96.5 C3: a pull request that changes only documents runs only the tests that read documents.

`tools/ci-scope.py` decides from the changed paths; `tests/doc_tests.json` lists the test modules that read a document; the
workflow keeps every check name reporting, since a branch rule may require any of them."""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
DOC_TESTS = ROOT / "tests" / "doc_tests.json"


def load_tool():
    spec = importlib.util.spec_from_file_location("ci_scope", ROOT / "tools" / "ci-scope.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def job_blocks(text: str) -> dict[str, list[str]]:
    """Job id -> its lines, read by indentation (two spaces under `jobs:`); the workflow has no anchors or flow style."""
    jobs: dict[str, list[str]] = {}
    inside, current = False, None
    for line in text.splitlines():
        if line.startswith("jobs:"):
            inside = True
            continue
        if not inside:
            continue
        match = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if match:
            current = match.group(1)
            jobs[current] = []
        elif current:
            jobs[current].append(line)
    return jobs


def steps(block: list[str]) -> list[list[str]]:
    found: list[list[str]] = []
    for line in block:
        if line.startswith("      - "):
            found.append([line])
        elif found and line.startswith("        "):
            found[-1].append(line)
    return found


class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.tool = load_tool()

    def test_markdown_outside_the_code_folders_is_documentation(self):
        docs = ["ROADMAP-3.md", "docs/RELEASE_0_4_1.md", "changelog.d/96-7-release.md", ".claude/skills/bridgeforge-pr/SKILL.md",
                "README.md", "docs/proposals/Old Plan.MD"]
        self.assertTrue(self.tool.docs_only(docs))

    def test_one_other_path_makes_the_change_a_full_run(self):
        docs = ["ROADMAP-3.md", "docs/INDEX.md"]
        for other in ("bridgeforge/kit_resources/TRIAL_GUIDE.md",  # package data, read by the code
                      "tests/fixtures/mod/README.md", "probe-mod/README.md", "tools/notes.md", ".github/PULL_REQUEST_TEMPLATE.md",
                      "docs/gates.json", "LICENSE", "pyproject.toml", "bridgeforge/cli.py", "docs\\..\\bridgeforge\\x.md"):
            with self.subTest(other=other):
                self.assertFalse(self.tool.docs_only([*docs, other]))

    def test_no_paths_is_a_full_run(self):
        self.assertFalse(self.tool.docs_only([]))
        self.assertFalse(self.tool.docs_only(["", "   "]))

    def test_command_line_reads_paths_and_writes_a_github_output_line(self):
        def run(paths: str) -> str:
            done = subprocess.run([sys.executable, str(ROOT / "tools" / "ci-scope.py")], input=paths, capture_output=True,
                                  text=True, check=True)
            return done.stdout

        self.assertEqual(run("ROADMAP-3.md\ndocs/INDEX.md\n"), "docs_only=true\n")
        self.assertEqual(run("ROADMAP-3.md\nbridgeforge/cli.py\n"), "docs_only=false\n")
        self.assertEqual(run(""), "docs_only=false\n")


class DocTestListTests(unittest.TestCase):
    def test_each_listed_module_exists_once_in_order(self):
        data = json.loads(DOC_TESTS.read_text(encoding="utf-8"))
        modules = data["modules"]
        self.assertTrue(modules)
        self.assertEqual(modules, sorted(set(modules)))
        for module in modules:
            with self.subTest(module=module):
                self.assertTrue((ROOT / "tests" / f"{module}.py").is_file())
        self.assertTrue(data.get("measured_on") and data.get("method"))

    def test_each_module_names_the_documents_it_read_and_they_are_documentation(self):
        data = json.loads(DOC_TESTS.read_text(encoding="utf-8"))
        self.assertEqual(sorted(data["reads"]), data["modules"])
        tool = load_tool()
        for module, documents in data["reads"].items():
            with self.subTest(module=module):
                self.assertTrue(documents)
                self.assertTrue(tool.docs_only(documents), documents)  # a change to any of them runs this module
                for document in documents:
                    self.assertTrue((ROOT / document).is_file(), document)

    def test_the_list_holds_the_tests_that_check_the_roadmap_and_the_generated_docs(self):
        modules = set(json.loads(DOC_TESTS.read_text(encoding="utf-8"))["modules"])
        self.assertLessEqual({"test_roadmap_lint", "test_checks_index"}, modules)

    def test_command_line_prints_them_for_unittest(self):
        done = subprocess.run([sys.executable, str(ROOT / "tools" / "ci-scope.py"), "--doc-tests"], capture_output=True,
                              text=True, check=True)
        modules = json.loads(DOC_TESTS.read_text(encoding="utf-8"))["modules"]
        self.assertEqual(done.stdout.split(), [f"tests.{m}" for m in modules])


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")
        self.jobs = job_blocks(self.text)

    def test_the_scope_job_decides_from_the_pull_requests_own_changes(self):
        scope = "\n".join(self.jobs["scope"])
        self.assertIn("docs_only: ${{ steps.scope.outputs.docs_only }}", scope)
        self.assertIn("fetch-depth: 2", scope)
        self.assertIn("git diff --name-only --no-renames HEAD^1 HEAD", scope)
        self.assertIn("tools/ci-scope.py", scope)
        self.assertIn('"$GITHUB_EVENT_NAME" = "pull_request"', scope)  # a push to main always runs everything

    def test_the_matrix_job_is_never_skipped_whole(self):
        """A matrix job skipped by a job-level `if` reports one check under its unexpanded name, so a required
        "ubuntu-latest / Python 3.15 / fast" would wait forever. Its steps are skipped one by one instead."""
        test = self.jobs["test"]
        self.assertEqual([line for line in test if re.match(r"^    if:", line)], ["    if: ${{ !cancelled() }}"])
        self.assertIn("    needs: scope", test)
        self.assertGreaterEqual(len(steps(test)), 5)
        for step in steps(test):
            with self.subTest(step=step[0].strip()):
                self.assertTrue(any("needs.scope.outputs.docs_only" in line for line in step), step)

    def test_single_jobs_are_skipped_whole_and_the_docs_job_runs_the_listed_tests(self):
        for name in ("coverage", "audit", "lockfile", "shared-fixtures"):
            with self.subTest(job=name):
                block = self.jobs[name]
                self.assertIn("    needs: scope", block)
                self.assertIn("    if: ${{ !cancelled() && needs.scope.outputs.docs_only != 'true' }}", block)
        docs = "\n".join(self.jobs["docs"])
        self.assertIn("    if: ${{ !cancelled() && needs.scope.outputs.docs_only == 'true' }}", docs)
        self.assertIn("tools/ci-scope.py --doc-tests", docs)
        self.assertIn("bridgeforge.test_guard", docs)
        self.assertNotIn("needs:", "\n".join(self.jobs["lint"]))  # lint is quick and always runs

    def test_a_failed_scope_job_runs_everything(self):
        """A job whose `needs` failed is skipped, and a skipped check reads as passed: without `!cancelled()` a failed scope
        job would let a pull request through untested. With it, docs_only is empty, so `!= 'true'` holds and all run."""
        needing = [name for name, block in self.jobs.items() if "    needs: scope" in block]
        self.assertEqual(sorted(needing), ["audit", "coverage", "docs", "lockfile", "shared-fixtures", "test"])
        for name in needing:
            with self.subTest(job=name):
                conditions = [line for line in self.jobs[name] if re.match(r"^    if:", line)]
                self.assertEqual(len(conditions), 1)
                self.assertIn("!cancelled()", conditions[0])


if __name__ == "__main__":
    unittest.main()
