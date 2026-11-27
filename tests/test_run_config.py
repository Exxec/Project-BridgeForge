"""ROADMAP-3 93.29: `probe-group report` reads its own run's probe config, not the rig's current one. 2026-11-17: group 3's report
after `install 4` named Tania instead of KoC; 2026-11-26: post_run's report of RC9NC-LIVE6 read Station Augments' group."""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import unittest
from pathlib import Path
from unittest import mock

from bridgeforge.run_manifest import (CONFIG_RELATIVE, ManifestError, config_for_run, manifest_path, prepare_run, run_config_path)
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
    (rig / CONFIG_RELATIVE).write_bytes(config)


def _launch(rig: Path, run_id: str) -> None:
    prepare_run(rig, run_id, "campaign", targets=[], expected=["main_menu"])


class RunConfigTests(unittest.TestCase):
    def test_the_run_keeps_its_own_config_and_the_report_reads_it_after_the_next_install(self) -> None:
        with resolved_temp_dir() as root:
            rig = _rig_with_config(root, GROUP_3)
            _launch(rig, "G3")
            kept = run_config_path(rig, "G3").read_bytes()
            _install(rig, GROUP_4)
            raw, source = config_for_run(rig, "G3")
        self.assertEqual((kept, raw), (GROUP_3, GROUP_3))
        self.assertIn("the run's own copy (G3.probe-config.data)", source)

    def test_an_older_run_without_a_copy_reads_the_rig_only_while_it_is_unchanged(self) -> None:
        with resolved_temp_dir() as root:
            rig = _rig_with_config(root, GROUP_3)
            _launch(rig, "G3")
            run_config_path(rig, "G3").unlink()  # a run launched before 93.29
            raw, source = config_for_run(rig, "G3")
            _install(rig, GROUP_4)
            with self.assertRaises(ManifestError) as refused:
                config_for_run(rig, "G3")
        self.assertEqual(raw, GROUP_3)
        self.assertIn("unchanged since the run started", source)
        self.assertIn("changed since run G3 started", str(refused.exception))

    def test_a_copy_that_does_not_match_the_manifest_is_not_trusted(self) -> None:
        with resolved_temp_dir() as root:
            rig = _rig_with_config(root, GROUP_3)
            _launch(rig, "G3")
            run_config_path(rig, "G3").write_bytes(GROUP_4)  # edited after launch
            raw, source = config_for_run(rig, "G3")  # the rig still holds the launch config
            _install(rig, GROUP_4)
            with self.assertRaises(ManifestError):
                config_for_run(rig, "G3")
        self.assertEqual(raw, GROUP_3)
        self.assertIn("unchanged since the run started", source)

    def test_a_run_without_a_manifest_reads_the_current_config_and_says_so(self) -> None:
        with resolved_temp_dir() as root:
            rig = _rig_with_config(root, GROUP_4)
            raw, source = config_for_run(rig, "OLD-RUN")
            empty = _rig_with_config(root / "b", None)
            with self.assertRaises(ManifestError):
                config_for_run(empty, "OLD-RUN")
        self.assertEqual(raw, GROUP_4)
        self.assertIn("this run has no manifest", source)

    def test_a_rig_without_a_config_keeps_no_copy(self) -> None:
        with resolved_temp_dir() as root:
            rig = _rig_with_config(root, None)
            _launch(rig, "G0")
            self.assertTrue(manifest_path(rig, "G0").is_file())
            self.assertFalse(run_config_path(rig, "G0").exists())


class ReportCommandTests(unittest.TestCase):
    def _report(self, rig: Path, log: Path):
        from bridgeforge.probe import cmd_probe_group, probe_record

        seen = {}

        def report(log_, config, **_kwargs):
            seen["config"] = config
            return {"fatal": 0, "mod_errors": 0, "content_ids_ran": True, "members": {}, "unattributed": []}

        args = argparse.Namespace(log=log, json=False)
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(probe_record, "group_report", report), \
                mock.patch.object(probe_record, "accepted_probe_findings", return_value={}), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cmd_probe_group._probe_report(args, rig.parent, rig)
        return code, seen.get("config"), out.getvalue(), err.getvalue()

    def test_the_report_of_an_earlier_group_reads_that_groups_config(self) -> None:
        with resolved_temp_dir() as root:
            rig = _rig_with_config(root, GROUP_3)
            _launch(rig, "G3")
            _install(rig, GROUP_4)
            result, config, out, _err = self._report(rig, rig / "logs" / "G3.stdout.log")
        self.assertEqual(config, json.loads(GROUP_3))
        self.assertIsInstance(result, dict)
        self.assertIn("probe config: the run's own copy", out)

    def test_the_report_refuses_when_the_runs_config_is_gone(self) -> None:
        with resolved_temp_dir() as root:
            rig = _rig_with_config(root, GROUP_3)
            _launch(rig, "G3")
            run_config_path(rig, "G3").unlink()
            _install(rig, GROUP_4)
            code, config, _out, err = self._report(rig, rig / "logs" / "G3.stdout.log")
        self.assertEqual((code, config), (2, None))
        self.assertIn("changed since run G3 started", err)


if __name__ == "__main__":
    unittest.main()
