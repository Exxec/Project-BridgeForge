"""ROADMAP item 73 G2: `probe-group regress --changed-since COMMIT` reruns only what needs it."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

from bridgeforge import regress_changed
from bridgeforge.live_trust import shipped_hash
from bridgeforge.regress_changed import RegressChangedError, run_changed, select_workspaces
from tests.support import link_dir, resolved_temp_dir
from tests.test_regress import _workspace


def _record_pass(queue: Path, name: str, verdict: str = "PASS") -> None:
    """A run record whose hash matches the files shipped now (CURRENT)."""
    log = queue / name / "reports" / "live_runs.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(json.dumps({"test_id": "T-1", "date": "2026-10-01", "verdict": verdict,
                               "shipped_sha256": shipped_hash(queue / name / "working"), "version": "1"}) + "\n", encoding="utf-8")


def _git_stub(paths: list[str]):
    def run(args: list[str], cwd: Path) -> str:
        return "\n".join(paths) if args[0] == "diff" else "abc123\n"
    return run


def _rig(root: Path) -> Path:
    rig = root / "rig"
    (rig / "mods").mkdir(parents=True)
    core = root / "core_real"
    core.mkdir()
    link_dir(core, rig / "starsector-core")
    return rig


class ChangedPathTests(unittest.TestCase):
    def test_probe_and_harness_paths_are_recognised(self) -> None:
        hits = regress_changed.probe_or_harness_changes(["probe-mod/src/Probe.java", "docs/X.md", "bridgeforge/live_run.py", "bridgeforge/scanner.py"])
        self.assertEqual(hits, ["probe-mod/src/Probe.java", "bridgeforge/live_run.py"])

    def test_an_option_like_commit_is_refused(self) -> None:
        with self.assertRaises(RegressChangedError):
            regress_changed.changed_paths(Path("."), "--output=x", _git_stub([]))

    def test_windows_separators_are_normalised(self) -> None:
        self.assertEqual(regress_changed.changed_paths(Path("."), "abc", _git_stub(["probe-mod\\a.java"])), ["probe-mod/a.java"])


class SelectionTests(unittest.TestCase):
    def test_only_a_workspace_with_changed_shipped_files_reruns_when_the_harness_is_unchanged(self) -> None:
        with resolved_temp_dir() as root:
            queue = root / "q"
            for name, mod in (("A", "mod_a"), ("B", "mod_b")):
                _workspace(queue, name, mod, "LIVE_VALIDATED")
                _record_pass(queue, name)
            (queue / "B" / "working" / "data" / "hulls" / "ship_data.csv").write_text("id,hints\nchanged,\n", encoding="utf-8")
            chosen = select_workspaces(queue, ["README.md"])
        self.assertEqual(list(chosen), ["B"])
        self.assertIn("STALE", chosen["B"])

    def test_a_probe_change_reruns_every_validated_workspace(self) -> None:
        with resolved_temp_dir() as root:
            queue = root / "q"
            for name, mod in (("A", "mod_a"), ("B", "mod_b")):
                _workspace(queue, name, mod, "LIVE_VALIDATED")
                _record_pass(queue, name)
            _workspace(queue, "C", "mod_c", "READY_FOR_LIVE_TEST")
            chosen = select_workspaces(queue, ["probe-mod/x.java"])
        self.assertEqual(sorted(chosen), ["A", "B"])
        self.assertIn("probe/harness", chosen["A"])


class RunChangedTests(unittest.TestCase):
    def _fixture(self, root: Path):
        queue = root / "q"
        for name, mod in (("A", "mod_a"), ("B", "mod_b")):
            _workspace(queue, name, mod, "LIVE_VALIDATED")
            _record_pass(queue, name)
        return queue, _rig(root)

    @staticmethod
    def _runner(verdicts: dict[str, str], seen: list):
        def runner(queue, rig, out, **kwargs):
            seen.append(kwargs["only"])
            return {"mode": "PROBE_GROUP_REGRESS", "date": "2026-10-14", "unplaced": [], "attention": [],
                    "groups": [{"group": 1, "members": dict(verdicts)}]}
        return runner

    def test_a_probe_change_runs_all_and_prints_only_changed_verdicts(self) -> None:
        with resolved_temp_dir() as root:
            queue, rig = self._fixture(root)
            seen: list = []
            out = root / "out.json"
            result = run_changed(queue, rig, out, "abc", repo_root=root, git=_git_stub(["probe-mod/p.java"]),
                                 runner=self._runner({"mod_a": "PASS", "mod_b": "FAIL"}, seen))
            written = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(seen, [["A", "B"]])
        self.assertEqual(sorted(written["archives"]), ["A", "B"])
        self.assertEqual(list(result["changed_verdicts"]), ["B"])
        self.assertEqual(written["archives"]["B"]["previous"], "PASS")
        self.assertTrue(written["archives"]["B"]["regression"])

    def test_nothing_changed_runs_nothing(self) -> None:
        with resolved_temp_dir() as root:
            queue, rig = self._fixture(root)
            seen: list = []
            result = run_changed(queue, rig, root / "out.json", "abc", repo_root=root, git=_git_stub(["README.md"]),
                                 runner=self._runner({}, seen))
        self.assertEqual(seen, [])
        self.assertEqual(result["selected"], {})
        self.assertEqual(result["groups"], [])

    def test_a_regression_writes_a_hold_that_blocks_the_next_run_until_cleared(self) -> None:
        with resolved_temp_dir() as root:
            queue, rig = self._fixture(root)
            git = _git_stub(["probe-mod/p.java"])
            result = run_changed(queue, rig, root / "out.json", "abc", repo_root=root, git=git,
                                 runner=self._runner({"mod_a": "PASS", "mod_b": "FAIL"}, []))
            self.assertTrue(Path(result["hold"]).is_file())
            with self.assertRaises(RegressChangedError):
                run_changed(queue, rig, root / "out2.json", "abc", repo_root=root, git=git, runner=self._runner({}, []))
            again = run_changed(queue, rig, root / "out3.json", "abc", repo_root=root, git=git, clear_hold=True,
                                runner=self._runner({"mod_a": "PASS", "mod_b": "PASS"}, []))
        self.assertNotIn("hold", again)
        self.assertEqual(again["changed_verdicts"], {})

    def test_a_clean_pass_writes_no_hold(self) -> None:
        with resolved_temp_dir() as root:
            queue, rig = self._fixture(root)
            result = run_changed(queue, rig, root / "out.json", "abc", repo_root=root, git=_git_stub(["probe-mod/p.java"]),
                                 runner=self._runner({"mod_a": "PASS", "mod_b": "PASS"}, []))
            self.assertFalse(regress_changed.hold_path(queue).exists())
        self.assertNotIn("hold", result)

    def test_a_rig_without_a_junction_is_refused(self) -> None:
        with resolved_temp_dir() as root:
            queue, _ = self._fixture(root)
            plain = root / "plain-rig"
            (plain / "starsector-core").mkdir(parents=True)
            with self.assertRaises(RegressChangedError):
                run_changed(queue, plain, root / "out.json", "abc", repo_root=root, git=_git_stub([]), runner=mock.Mock())


if __name__ == "__main__":
    unittest.main()
