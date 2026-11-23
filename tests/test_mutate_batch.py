"""The bridgeforge-pr skill's mutate_batch.py: a verdict is reused only at the commit it ran at.

2026-11-22 (94.G2 P4): a MISSED verdict was reused after the test that catches the mutant had been committed, so the batch
reported a gap that was already closed. No mutant really runs here: run_one is replaced.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from tests.support import resolved_temp_dir, write_text as _write

SCRIPT = Path(__file__).resolve().parent.parent / ".claude" / "skills" / "bridgeforge-pr" / "scripts" / "mutate_batch.py"


def _load():
    spec = importlib.util.spec_from_file_location("mutate_batch_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True)
    return done.stdout.strip()


def _repo(root: Path) -> Path:
    repo = root / "repo"
    _write(repo / "m.py", "x = 1\n")
    _git(repo.parent, "init", "-q", str(repo))
    for key, value in (("user.email", "test@example.invalid"), ("user.name", "test"), ("commit.gpgsign", "false")):
        _git(repo, "config", key, value)
    _git(repo, "add", "m.py")
    _git(repo, "commit", "-q", "-m", "one")
    return repo


MUTANT = {"claim": "c", "name": "n", "module": "m.py", "old": "x = 1", "new": "x = 2", "selector": "tests.t"}


class ReuseTests(unittest.TestCase):
    def _run(self, repo: Path, results: Path, verdict: str = "CAUGHT") -> tuple[int, list]:
        module = _load()
        spec = results.parent / "spec.json"
        spec.write_text(json.dumps({"repo": str(repo), "mutants": [MUTANT]}), encoding="utf-8")
        calls = []

        def fake_run_one(_repo, mutant, checker=None):
            calls.append(mutant["name"])
            return {**mutant, "verdict": verdict, "output": ""}

        with mock.patch.object(module, "run_one", fake_run_one), contextlib.redirect_stdout(io.StringIO()):
            code = module.main(str(spec), str(results))
        return code, calls

    def test_a_verdict_of_this_commit_is_reused_and_records_its_head(self) -> None:
        with resolved_temp_dir() as root:
            repo, results = _repo(root), root / "results.json"
            self.assertEqual(self._run(repo, results, "MISSED"), (1, ["n"]))
            recorded = json.loads(results.read_text(encoding="utf-8"))
            self.assertEqual(recorded[0]["head"], _git(repo, "rev-parse", "HEAD"))
            self.assertEqual(self._run(repo, results, "CAUGHT")[1], [])  # same commit: not run again

    def test_a_verdict_of_another_commit_runs_again(self) -> None:
        with resolved_temp_dir() as root:
            repo, results = _repo(root), root / "results.json"
            self._run(repo, results, "MISSED")
            _write(repo / "test_new.py", "# the test that catches it\n")
            _git(repo, "add", "test_new.py")
            _git(repo, "commit", "-q", "-m", "two")
            code, calls = self._run(repo, results, "CAUGHT")
            recorded = json.loads(results.read_text(encoding="utf-8"))
        self.assertEqual((code, calls), (0, ["n"]))
        self.assertEqual([r["verdict"] for r in recorded], ["CAUGHT"])  # the stale MISSED is not kept


if __name__ == "__main__":
    unittest.main()
