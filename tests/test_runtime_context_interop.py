"""Synthetic producer fixture shared with Project Go; no game launch or live proof."""
import json
import shutil
import unittest
from pathlib import Path
from unittest import mock

from bridgeforge.live.live_trust import shipped_hash, write_run_record
from tests.support import resolved_temp_dir

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/runtime-context"


def produce_record(root: Path, exit_code):
    workspace = root / "q" / "B"
    shutil.copytree(FIXTURE / "candidate", workspace / "working")
    digest = shipped_hash(workspace / "working")
    manifest = {"manifest_id": "synthetic-context-manifest", "kind": "campaign", "scenario": "synthetic-only",
                "targets": ["mod_b"], "enabled": [], "expected_milestones": ["main_menu", "campaign_load"],
                "java_version": "17.0.1", "runtime": {"java_executable": "synthetic-jdk/bin/java.exe", "java_version": "17.0.1"}}
    evidence = {"status": "ACCEPTABLE", "run_id": "CONTEXT", "manifest_id": manifest["manifest_id"],
                "log": {"path": "synthetic.log", "sha256": "0" * 64, "size": 0},
                "milestones": {"main_menu": True, "campaign_load": True, "save": False},
                "members": {"mod_b": {"ok": True, "candidate_sha256": digest}}}
    record = write_run_record(root / "q", "CONTEXT", [workspace], triage={"counts": {}}, verdicts={"mod_b": "PASS"},
                              manifest=manifest, evidence=evidence, today="2026-10-19", process_exit_code=exit_code)
    # A stable fixture clock and build digest are synthetic inputs, never claims about an installed game.
    record["recorded_at"] = "2026-10-19T00:00:00+00:00"
    record["core_baseline_sha256"] = "1" * 64
    return record


class RuntimeContextInteropTests(unittest.TestCase):
    def test_current_producer_matches_the_shared_fixture_with_an_explicit_exit_code(self):
        with resolved_temp_dir() as root:
            actual = produce_record(root, 0)
        expected = json.loads((FIXTURE / "observed-zero.synthetic.json").read_text(encoding="utf-8"))
        self.assertEqual(actual, expected)

    def test_unknown_exit_matches_shared_fixture_and_is_never_defaulted_to_success(self):
        with resolved_temp_dir() as root:
            actual = produce_record(root, None)
        expected = json.loads((FIXTURE / "unknown-exit.synthetic.json").read_text(encoding="utf-8"))
        self.assertEqual(actual, expected)
        self.assertIsNone(actual["process_exit_code"])

    def test_missing_runtime_is_not_replaced_with_the_host_jdk(self):
        from bridgeforge.run_manifest import _java_version
        with resolved_temp_dir() as root, mock.patch("bridgeforge.run_manifest.subprocess.run") as launch:
            self.assertIsNone(_java_version(root, None, None))
            launch.assert_not_called()

    def test_batch_variables_and_bare_path_commands_do_not_guess_the_host_runtime(self):
        from bridgeforge.run_manifest import _java_version
        with resolved_temp_dir() as root, mock.patch("bridgeforge.run_manifest.subprocess.run") as launch:
            for command in ("%JAVA_HOME%/bin/java.exe", "${JAVA_HOME}/bin/java.exe", "java.exe"):
                self.assertIsNone(_java_version(root, root / "launch.bat", command))
            launch.assert_not_called()

    def test_explicit_relative_runtime_is_bound_to_the_rig_even_without_a_launcher_path(self):
        from bridgeforge.run_manifest import _java_version
        with resolved_temp_dir() as root:
            java = root / "jdk/bin/java.exe"
            java.parent.mkdir(parents=True)
            java.write_bytes(b"synthetic executable placeholder")
            (root / "jdk/release").write_text('JAVA_VERSION="17.0.1"\n', encoding="utf-8")
            self.assertEqual(_java_version(root, None, "jdk/bin/java.exe"), "17.0.1")
