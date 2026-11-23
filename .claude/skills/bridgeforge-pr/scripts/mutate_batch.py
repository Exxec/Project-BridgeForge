"""Run a spec of mutants through mutate_check.py, one at a time, and record each verdict.

Usage: python mutate_batch.py SPEC.json RESULTS.json   (run from the checkout root, as mutate_check.py is)

SPEC.json:
{
  "repo": "optional: the checkout the mutants edit; default the current folder",
  "mutants": [
    {"claim": "ROADMAP-3 96.9 (L784)", "name": "no retry", "module": "bridgeforge/x.py",
     "old": "exact text, found once", "new": "replacement", "selector": "tests.test_x.SomeTests",
     "source": "transcript | reconstructed"}
  ]
}

Each mutant runs mutate_check.py as its own process (cwd and PYTHONPATH = the repo, so a worktree tests its own code), so a
crash cannot leave the next one mutated. Snippets are written to files byte for byte, so CRLF modules work. After every
mutant the repo's `git status --porcelain` must be empty, or the batch stops. RESULTS.json is rewritten after each mutant,
so an interrupted batch keeps what finished; a mutant already in it (same claim and name) is skipped on a re-run.
Verdicts: CAUGHT (the only one to claim), MISSED, NOT RUN, INVALID, TIMEOUT. Exit 0 only when every verdict is CAUGHT.
Used for the re-run of 2026-11-22's claims (ROADMAP-3 94.G2, "Mutation re-run").
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

CHECKER = Path(__file__).resolve().with_name("mutate_check.py")
VERDICTS = {0: "CAUGHT", 1: "MISSED", 2: "NOT RUN", 3: "INVALID", 4: "TIMEOUT"}


def _key(mutant: dict) -> str:
    return f"{mutant['claim']}|{mutant['name']}"


def _dirty(repo: Path) -> str:
    done = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True, check=True)
    return done.stdout.strip()


def run_one(repo: Path, mutant: dict, checker: Path = CHECKER) -> dict:
    """One mutant through mutate_check.py: the mutant with its verdict and the tail of the checker's output."""
    with tempfile.TemporaryDirectory(prefix="mutbatch-") as scratch:
        old_file = Path(scratch) / "old.txt"
        new_file = Path(scratch) / "new.txt"
        old_file.write_bytes(mutant["old"].encode("utf-8"))
        new_file.write_bytes(mutant["new"].encode("utf-8"))
        env = dict(os.environ, PYTHONPATH=str(repo))
        done = subprocess.run([sys.executable, str(checker), mutant["module"], f"@{old_file}", f"@{new_file}",
                               mutant["selector"]], cwd=repo, env=env, capture_output=True, text=True, check=False)
    verdict = VERDICTS.get(done.returncode, f"EXIT {done.returncode}")
    return {**mutant, "verdict": verdict, "output": (done.stdout + done.stderr)[-1200:]}


def main(spec_path: str, results_path: str) -> int:
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    repo = Path(spec.get("repo") or ".").resolve()
    out = Path(results_path)
    results = json.loads(out.read_text(encoding="utf-8")) if out.exists() else []
    done_keys = {_key(r) for r in results}
    if _dirty(repo):
        print(f"{repo} has changes before the batch: stopped\n{_dirty(repo)}")
        return 2
    todo = [m for m in spec["mutants"] if _key(m) not in done_keys]
    for index, mutant in enumerate(todo, 1):
        result = run_one(repo, mutant)
        results.append(result)
        out.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"[{index}/{len(todo)}] {result['verdict']:8} {mutant['claim']} :: {mutant['name']}", flush=True)
        left = _dirty(repo)
        if left:
            print(f"the repo is not clean after this mutant: stopped\n{left}")
            return 2
    counts: dict[str, int] = {}
    for r in results:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    print("totals:", json.dumps(counts, sort_keys=True))
    return 0 if set(counts) <= {"CAUGHT"} else 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
