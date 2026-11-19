"""96.5 A5: each command module's run_cli dispatches through a table, one handler per command, and long functions only shrink."""
from __future__ import annotations

import argparse
import ast
import importlib
import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from bridgeforge.cli_commands import COMMAND_MODULES
from tests.support import resolved_temp_dir  # importing tests.support also installs the registry guard (96.5 C4)

PACKAGE = Path(__file__).resolve().parent.parent / "bridgeforge"
SPLIT = ("rig.cmd_rig", "corpus.cmd_corpus", "cmd_archive", "cmd_bytecode", "cmd_translate", "cmd_analysis", "cmd_revive",
         "scan.cmd_scan", "save.cmd_save")
LONG_LINES = 200
# Functions over LONG_LINES lines on 2026-11-18, after the split. Remove a name when it is split; never add one.
LONG_ALLOWED = {"behavior_discovery.py:build_archaeology", "scan/scan_ships.py:_scan_variant_validity",
                "scan/scan_sources.py:_scan_sources"}


class HandlerTableTests(unittest.TestCase):
    def test_every_registered_command_has_a_handler_and_no_other(self) -> None:
        for name in SPLIT:
            with self.subTest(module=name):
                module = importlib.import_module(f"bridgeforge.{name}")
                self.assertEqual(set(module._HANDLERS), set(COMMAND_MODULES[name]))
                self.assertTrue(all(callable(handler) for handler in module._HANDLERS.values()))

    def test_an_unknown_command_still_returns_2(self) -> None:
        for name in (*SPLIT, "probe.cmd_probe_group"):
            with self.subTest(module=name):
                module = importlib.import_module(f"bridgeforge.{name}")
                self.assertEqual(module.run_cli(argparse.Namespace(command="no-such-command")), 2)

    def test_probe_group_sub_commands_match_its_parser(self) -> None:
        from bridgeforge.probe import cmd_probe_group

        parser = argparse.ArgumentParser()
        cmd_probe_group.add_parser(parser.add_subparsers(dest="command"))
        group = parser._subparsers._group_actions[0].choices["probe-group"]
        choices = set(group._subparsers._group_actions[0].choices)
        self.assertEqual(set(cmd_probe_group._SUB_COMMANDS) | {"report"}, choices)


class HandlerBehaviourTests(unittest.TestCase):
    """The paths the split could have changed: a compound branch's fall-through and probe-group's early exits."""

    def test_compat_set_with_another_sub_command_returns_2(self) -> None:
        from bridgeforge.save import cmd_save

        self.assertEqual(cmd_save.run_cli(argparse.Namespace(command="compat-set", compat_set_command="other")), 2)

    def _probe(self, sub: str, rig: Path, **extra) -> tuple[int, str]:
        from bridgeforge.probe import cmd_probe_group

        args = argparse.Namespace(command="probe-group", probe_group_command=sub, queue=rig.parent, rig=rig, json=True, **extra)
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = cmd_probe_group.run_cli(args)
        return code, out.getvalue()

    def test_a_failed_smoke_prints_its_json_once_and_returns_1(self) -> None:
        failed = {"verdict": "SMOKE_FAIL", "boot": {}, "fatal": 1, "mod_errors": 0, "load_errors": []}
        with resolved_temp_dir() as root, mock.patch("bridgeforge.probe.probe_group.smoke_group", return_value=failed):
            code, out = self._probe("smoke", root / "_rig", bat=None, timeout=1, log_name=None)
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out), failed)  # one document: a second print would not parse

    def test_a_sub_command_error_still_returns_2(self) -> None:
        from bridgeforge.probe.probe_group import ProbeGroupError

        with resolved_temp_dir() as root, mock.patch("bridgeforge.probe.probe_group.smoke_group", side_effect=ProbeGroupError("no rig")):
            code, out = self._probe("smoke", root / "_rig", bat=None, timeout=1, log_name=None)
        self.assertEqual((code, out), (2, ""))

    def test_a_stopped_record_returns_1_after_its_json(self) -> None:
        from bridgeforge.probe.probe_config import CONFIG_FILE

        stopped = {"stopped": "a member failed", "recorded": [], "skipped": []}
        with resolved_temp_dir() as root:
            rig = root / "_rig"
            (rig / "saves" / "common").mkdir(parents=True)
            (rig / "saves" / "common" / CONFIG_FILE).write_text("{}", encoding="utf-8")
            with mock.patch("bridgeforge.probe.probe_group.record_group", return_value=stopped):
                code, out = self._probe("record", rig, test_id="T1", archive=False, refresh=False, accept=False, note=None,
                                        observe_exit=False)
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out), stopped)


class LongFunctionRatchetTests(unittest.TestCase):
    def test_no_new_function_over_200_lines(self) -> None:
        found = set()
        for path in sorted(PACKAGE.rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.end_lineno - node.lineno + 1 > LONG_LINES:
                    found.add(f"{path.relative_to(PACKAGE).as_posix()}:{node.name}")
        self.assertEqual(found - LONG_ALLOWED, set(), "split the new long function(s)")
        self.assertEqual(LONG_ALLOWED - found, set(), "a listed function is now short: remove it from LONG_ALLOWED")


if __name__ == "__main__":
    unittest.main()
