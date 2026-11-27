"""ROADMAP-3 93.29: `probe-group report` and `record` judge a run with its own probe config and enabled list, not the rig's
current ones. 2026-11-17: group 3's report after `install 4` named Tania instead of KoC; 2026-11-26: post_run's report of
RC9NC-LIVE6 read Station Augments' group; 2026-11-27 (review): `record` without --accept recorded the next group."""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import unittest
from pathlib import Path
from unittest import mock

from bridgeforge.run_manifest import (CONFIG_RELATIVE, ManifestError, manifest_path, prepare_run, run_config_path, run_id_of_log,
                                      run_inputs)
from tests.bound_runs import make_rig
from tests.support import resolved_temp_dir

GROUP_3 = b'{"group": 3, "members": ["koc"]}'
GROUP_4 = b'{"group": 4, "members": ["tania"]}'


def _rig_with_config(root: Path, config: bytes | None) -> Path:
    rig = make_rig(root, {"lib": []})
    (rig / "mods" / "enabled_mods.json").write_text(json.dumps({"enabledMods": ["lib"]}), encoding="utf-8")
    if config is not None:
        (rig / CONFIG_RELATIVE).parent.mkdir(parents=True, exist_ok=True)
        (rig / CONFIG_RELATIVE).write_bytes(config)
    return rig


def _install(rig: Path, config: bytes) -> None:
    (rig / CONFIG_RELATIVE).parent.mkdir(parents=True, exist_ok=True)
    (rig / CONFIG_RELATIVE).write_bytes(config)


def _launch(rig: Path, run_id: str) -> None:
    prepare_run(rig, run_id, "campaign", targets=[], expected=["main_menu"])


class RunInputsTests(unittest.TestCase):
    def test_the_run_keeps_its_own_config_and_the_report_reads_it_after_the_next_install(self) -> None:
        with resolved_temp_dir() as root:
            rig = _rig_with_config(root, GROUP_3)
            _launch(rig, "G3")
            kept = run_config_path(rig, "G3").read_bytes()
            _install(rig, GROUP_4)
            found = run_inputs(rig, "G3")
        self.assertEqual((kept, found["config"]), (GROUP_3, GROUP_3))
        self.assertIn("the run's own copy (G3.probe-config.data)", found["source"])
        self.assertEqual(found["enabled"], ["lib"])  # the run's own list, from its manifest

    def test_an_older_run_without_a_copy_reads_the_rig_only_while_it_is_unchanged(self) -> None:
        with resolved_temp_dir() as root:
            rig = _rig_with_config(root, GROUP_3)
            _launch(rig, "G3")
            run_config_path(rig, "G3").unlink()  # a run launched before 93.29
            found = run_inputs(rig, "G3")
            _install(rig, GROUP_4)
            with self.assertRaises(ManifestError) as refused:
                run_inputs(rig, "G3")
        self.assertEqual(found["config"], GROUP_3)
        self.assertIn("unchanged since the run started", found["source"])
        self.assertIn("changed since run G3 started", str(refused.exception))
        self.assertIn("--config FILE", str(refused.exception))

    def test_a_copy_that_does_not_match_the_manifest_is_not_trusted(self) -> None:
        with resolved_temp_dir() as root:
            rig = _rig_with_config(root, GROUP_3)
            _launch(rig, "G3")
            run_config_path(rig, "G3").write_bytes(GROUP_4)  # edited after launch
            found = run_inputs(rig, "G3")  # the rig still holds the launch config
            _install(rig, GROUP_4)
            with self.assertRaises(ManifestError):
                run_inputs(rig, "G3")
        self.assertEqual(found["config"], GROUP_3)
        self.assertIn("unchanged since the run started", found["source"])

    def test_a_manifest_that_cannot_be_trusted_refuses(self) -> None:
        # Review, 2026-11-27: an edited manifest fell back to the current config, labelled "this run has no manifest".
        with resolved_temp_dir() as root:
            rig = _rig_with_config(root, GROUP_3)
            _launch(rig, "G3")
            path = manifest_path(rig, "G3")
            data = json.loads(path.read_text(encoding="utf-8"))
            data["scenario"] = "edited"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(ManifestError) as refused:
                run_inputs(rig, "G3")
        self.assertIn("does not match its own manifest id", str(refused.exception))

    def test_a_run_without_a_manifest_reads_the_current_config_and_says_so(self) -> None:
        with resolved_temp_dir() as root:
            rig = _rig_with_config(root, GROUP_4)
            found = run_inputs(rig, "OLD-RUN")
            odd = run_inputs(rig, "not a run id!")  # an id prepare_run refuses never had a manifest
            empty = _rig_with_config(root / "b", None)
            with self.assertRaises(ManifestError):
                run_inputs(empty, "OLD-RUN")
        self.assertEqual((found["config"], found["enabled"]), (GROUP_4, None))
        self.assertIn("this run has no manifest", found["source"])
        self.assertEqual(odd["config"], GROUP_4)

    def test_a_run_that_started_without_a_config_says_so(self) -> None:
        with resolved_temp_dir() as root:
            rig = _rig_with_config(root, None)
            _launch(rig, "G0")
            self.assertTrue(manifest_path(rig, "G0").is_file())
            self.assertFalse(run_config_path(rig, "G0").exists())
            _install(rig, GROUP_4)
            with self.assertRaises(ManifestError) as refused:
                run_inputs(rig, "G0")
        self.assertIn("started with no probe config", str(refused.exception))

    def test_the_copy_is_written_before_the_manifest_and_on_a_repeat_prepare(self) -> None:
        from bridgeforge import run_manifest

        with resolved_temp_dir() as root:
            rig = _rig_with_config(root, GROUP_3)
            with mock.patch.object(run_manifest, "keep_run_config", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    _launch(rig, "G3")
            self.assertFalse(manifest_path(rig, "G3").exists())  # no manifest without its copy
            _launch(rig, "G3")
            run_config_path(rig, "G3").unlink()
            run_manifest.release_run(rig, "G3")
            _launch(rig, "G3")  # the same manifest again: the copy comes back
            self.assertEqual(run_config_path(rig, "G3").read_bytes(), GROUP_3)

    def test_a_config_that_changed_after_it_was_hashed_is_not_kept(self) -> None:
        from bridgeforge.run_manifest import keep_run_config

        with resolved_temp_dir() as root:
            rig = _rig_with_config(root, GROUP_4)
            with self.assertRaises(ManifestError):
                keep_run_config(rig, "G3", "0" * 64)
            self.assertFalse(run_config_path(rig, "G3").exists())
            self.assertIsNone(keep_run_config(rig, "G3", None))

    def test_the_run_id_of_a_log(self) -> None:
        self.assertEqual(run_id_of_log(Path("x/G3.stdout.log")), "G3")
        self.assertEqual(run_id_of_log(Path("x/G3-reload.STDOUT.LOG")), "G3-reload")
        self.assertEqual(run_id_of_log(Path("x/starsector.log")), "starsector.log")


class CommandTests(unittest.TestCase):
    def _report(self, rig: Path, log: Path, json_out: bool = False, config: Path | None = None):
        from bridgeforge.probe import cmd_probe_group, probe_record

        seen = {}

        def report(log_, config_, **kwargs):
            seen.update(config=config_, enabled=kwargs.get("enabled"))
            return {"fatal": 0, "mod_errors": 0, "content_ids_ran": True, "members": {}, "unattributed": []}

        args = argparse.Namespace(log=log, json=json_out, config=config)
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(probe_record, "group_report", report), \
                mock.patch.object(probe_record, "accepted_probe_findings", return_value={}), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cmd_probe_group._probe_report(args, rig.parent, rig)
        return code, seen, out.getvalue(), err.getvalue()

    def test_the_report_of_an_earlier_group_reads_that_groups_config_and_enabled_list(self) -> None:
        with resolved_temp_dir() as root:
            rig = _rig_with_config(root, GROUP_3)
            _launch(rig, "G3")
            _install(rig, GROUP_4)
            (rig / "mods" / "enabled_mods.json").write_text(json.dumps({"enabledMods": ["tania"]}), encoding="utf-8")
            result, seen, out, _err = self._report(rig, rig / "logs" / "G3.stdout.log")
            as_json, _seen, json_out, _err = self._report(rig, rig / "logs" / "G3.stdout.log", json_out=True)
        self.assertEqual((seen["config"], seen["enabled"]), (json.loads(GROUP_3), ["lib"]))
        self.assertIn("probe config: the run's own copy", out)
        self.assertIn("the run's own copy", result["probe_config_source"])
        self.assertEqual(json_out, "")  # --json prints nothing but the result, which the CLI writes
        self.assertIn("the run's own copy", as_json["probe_config_source"])

    def test_the_report_refuses_when_the_runs_config_is_gone_and_takes_one_given(self) -> None:
        with resolved_temp_dir() as root:
            rig = _rig_with_config(root, GROUP_3)
            _launch(rig, "G3")
            run_config_path(rig, "G3").unlink()
            _install(rig, GROUP_4)
            code, seen, _out, err = self._report(rig, rig / "logs" / "G3.stdout.log")
            given = root / "g3.data"
            given.write_bytes(GROUP_3)
            result, seen_given, out, _err = self._report(rig, rig / "logs" / "G3.stdout.log", config=given)
        self.assertEqual((code, seen), (2, {}))
        self.assertIn("changed since run G3 started", err)
        self.assertEqual(seen_given["config"], json.loads(GROUP_3))
        self.assertIn("the config given with --config", out)

    def test_record_without_accept_judges_the_run_with_its_own_group(self) -> None:
        # Review, 2026-11-27: after `install 2`, `record G1` judged G1's log with group 2's config and wrote LIVE_VALIDATED
        # into group 2's report.
        from bridgeforge.cli import main
        from bridgeforge.probe.probe_config import build_probe_config
        from bridgeforge.probe.probe_group import merge_configs
        from bridgeforge.run_manifest import release_run
        from tests.bound_runs import PROBE, stage
        from tests.test_probe_group import _workspace

        with resolved_temp_dir() as root:
            queue = root / "In operation"
            a = _workspace(queue, "A", "mod_a", "hull_a")
            b = _workspace(queue, "B", "mod_b", "hull_b")
            rig = make_rig(root)
            stage(rig, {"mod_a": queue / "A"})
            _install(rig, json.dumps(merge_configs([build_probe_config(a)]), indent=2, sort_keys=True).encode("utf-8"))
            prepare_run(rig, "G1", "campaign", targets=["mod_a"], expected=["main_menu"])
            (rig / "logs" / "G1.stdout.log").write_text(PROBE + "BF-PROBE|0.2.9|content-ids|OK|all-content|checked=1 failed=0\n",
                                                        encoding="utf-8")
            release_run(rig, "G1")
            stage(rig, {"mod_b": queue / "B"})  # what `probe-group install 2` leaves
            _install(rig, json.dumps(merge_configs([build_probe_config(b)]), indent=2, sort_keys=True).encode("utf-8"))
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                main(["probe-group", "record", "G1", "--queue", str(queue), "--rig", str(rig)])
            b_report = (queue / "B" / "working" / "reports" / "REVIVAL_REPORT.md")
            b_text = b_report.read_text(encoding="utf-8") if b_report.is_file() else ""
        self.assertNotIn("Recorded LIVE_VALIDATED (0.2.9): B", out.getvalue())
        self.assertNotIn("G1", b_text)
        self.assertIn("probe config: the run's own copy (G1.probe-config.data)", out.getvalue())


if __name__ == "__main__":
    unittest.main()
