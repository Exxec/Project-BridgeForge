from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout

from bridgeforge.cli import main
from bridgeforge.progress import LONG_RUNNING_COMMANDS, Checkpoint, report
from tests.support import resolved_temp_dir


class CheckpointTests(unittest.TestCase):
    def test_same_header_resumes_other_header_restarts_and_finish_removes(self):
        with resolved_temp_dir() as root:
            path = root / "run.partial.jsonl"
            with Checkpoint(path, {"inputs": 1}) as saved:
                saved.add("a", {"n": 1})
                saved.add("b", {"n": 2})
            with open(path, "a", encoding="utf-8") as handle:
                handle.write('{"key": "c", "val')  # cut short
            again = Checkpoint(path, {"inputs": 1})
            self.assertEqual((again.get("a"), again.get("b"), again.get("c")), ({"n": 1}, {"n": 2}, None))
            again.close()
            other = Checkpoint(path, {"inputs": 2})
            self.assertIsNone(other.get("a"))
            other.close()
            self.assertEqual(json.loads(path.read_text(encoding="utf-8").splitlines()[0]), {"inputs": 2})
            other.finish()
            self.assertFalse(path.exists())
            nothing = Checkpoint(None, {})
            nothing.add("x", {})
            nothing.finish()

    def test_a_grown_item_list_resumes_and_a_shrunk_one_restarts(self):
        # ROADMAP 49: the 2026-10-04 queue pass restarted from 0 because two workspaces had been added.
        with resolved_temp_dir() as root:
            path = root / "run.partial.jsonl"
            with Checkpoint(path, {"queue": "q", "workspaces": ["A", "B"]}) as saved:
                saved.add("A", {"n": 1})
            grown = Checkpoint(path, {"queue": "q", "workspaces": ["A", "B", "C"]})
            self.assertEqual(grown.get("A"), {"n": 1})
            grown.add("C", {"n": 3})
            grown.close()
            self.assertEqual(json.loads(path.read_text(encoding="utf-8").splitlines()[0])["workspaces"], ["A", "B", "C"])
            again = Checkpoint(path, {"queue": "q", "workspaces": ["A", "B", "C"]})
            self.assertEqual((again.get("A"), again.get("C")), ({"n": 1}, {"n": 3}))
            again.close()
            shrunk = Checkpoint(path, {"queue": "q", "workspaces": ["A"]})  # B dropped: different inputs
            self.assertIsNone(shrunk.get("A"))
            shrunk.close()
            other = Checkpoint(path, {"queue": "other", "workspaces": ["A"]})
            self.assertIsNone(other.get("A"))
            other.finish()

    def test_report_format(self):
        err = io.StringIO()
        with redirect_stderr(err):
            report(3, 10, "Mod", "2 finding(s)", 1.25)
            report(4, 10, "Other", "done", None)
        self.assertEqual(err.getvalue().splitlines(), ["[3/10] Mod: 2 finding(s) (1.2s)", "[4/10] Other: done (from checkpoint)"])


class LongRunningCommandRuleTests(unittest.TestCase):
    """House rule 2026-09-27 (CLAUDE.md): a command that walks a whole queue or archive prints
    per-item progress and resumes from a checkpoint. Each listed command must at least offer --quiet,
    which only exists where progress is printed."""

    def test_every_long_running_command_offers_quiet(self):
        for command in LONG_RUNNING_COMMANDS:
            out = io.StringIO()
            with self.subTest(command=" ".join(command)), redirect_stdout(out), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    main([*command, "--help"])
            self.assertIn("--quiet", out.getvalue(), f"{' '.join(command)} prints no progress")


class _Interrupted(Exception):
    pass


class LongRunningListTests(unittest.TestCase):
    """ROADMAP-3 96.5 A3: `escalation run --all` had no progress and no checkpoint, and `auto-open` and `atlas migrations`
    printed progress but were missing from LONG_RUNNING_COMMANDS (2026-11-17)."""

    def test_every_command_offering_quiet_is_listed(self):
        """--quiet exists only where a command prints per-item progress, so a command that offers it belongs in the list."""
        import argparse

        from bridgeforge.cli import build_parser

        def walk(parser, path):
            yield path, {option for action in parser._actions for option in action.option_strings}
            for action in parser._actions:
                if isinstance(action, argparse._SubParsersAction):
                    for name, child in action.choices.items():
                        yield from walk(child, (*path, name))

        listed = set(LONG_RUNNING_COMMANDS)
        missing = sorted({" ".join(path) for path, options in walk(build_parser(), ()) if path and "--quiet" in options and path not in listed})
        self.assertEqual(missing, [])

    def test_escalation_run_all_resumes_after_the_last_finished_packet(self):
        import argparse
        from unittest import mock

        from bridgeforge import cmd_revive
        from bridgeforge.escalation import escalation

        calls = []

        def run_packet(workspace, name, agent, **_kwargs):
            calls.append(name)
            if name == "p2" and calls.count("p2") == 1:
                raise _Interrupted
            return {"packet": name, "outcome": "VERIFIED", "attempts": [{}]}

        with resolved_temp_dir() as root:
            args = argparse.Namespace(workspace=root, all=True, quiet=False, agent="x", apply=False, retries=1, timeout=1,
                                      auto_accept=False)
            err = io.StringIO()
            with mock.patch.object(escalation, "run_packet", side_effect=run_packet), redirect_stderr(err):
                with self.assertRaises(_Interrupted):
                    cmd_revive.run_packets(args, ["p1", "p2"])
                results = cmd_revive.run_packets(args, ["p1", "p2"])
            self.assertFalse((escalation.packets_dir(root) / "run-all.partial.jsonl").exists())
        self.assertEqual(calls, ["p1", "p2", "p2"])
        self.assertEqual([result["packet"] for result in results], ["p1", "p2"])
        self.assertIn("[1/2] p1: VERIFIED (from checkpoint)", err.getvalue())

    def test_auto_open_resumes_after_the_last_finished_workspace(self):
        from unittest import mock

        from bridgeforge import auto_open as module

        calls = []

        def explain(workspace, standing):
            calls.append(workspace.name)
            if workspace.name == "ModB" and calls.count("ModB") == 1:
                raise _Interrupted
            return [{"id": "x", "count": 1, "reason": "NOT_APPROVED", "detail": workspace.name}]

        with resolved_temp_dir() as queue:
            for name in ("ModA", "ModB"):
                (queue / name / "reports").mkdir(parents=True)
            checkpoint = queue / module.CHECKPOINT_NAME
            with mock.patch.object(module, "explain_workspace", side_effect=explain):
                with self.assertRaises(_Interrupted):
                    module.auto_open(queue, checkpoint=checkpoint)
                result = module.auto_open(queue, checkpoint=checkpoint)
            self.assertFalse(checkpoint.exists())
        self.assertEqual(calls, ["ModA", "ModB", "ModB"])
        self.assertEqual(sorted(result["mods"]), ["ModA", "ModB"])

    def test_atlas_migrations_resume_after_the_last_finished_pair(self):
        from unittest import mock

        from bridgeforge.atlas import atlas_migrations as module

        calls = []
        row = ("OldApi.x", "NewApi.x", "method", "renamed", "compatible", "old example", "new example", "Cls")

        def replacements(old, new, catalogue):
            calls.append(old.parent.name)
            if old.parent.name == "b" and calls.count("b") == 1:
                raise _Interrupted
            return [row]

        with resolved_temp_dir() as root:
            pairs = []
            for name in ("a", "b"):
                (root / name / "old").mkdir(parents=True)
                (root / name / "new").mkdir(parents=True)
                pairs.append(module.Pair(f"{name}: old -> new", root / name / "old", root / name / "new"))
            checkpoint = root / "MIGRATIONS.partial.jsonl"
            with mock.patch.object(module, "pair_replacements", side_effect=replacements):
                with self.assertRaises(_Interrupted):
                    module.mine(pairs, None, None, checkpoint=checkpoint)
                data = module.mine(pairs, None, None, checkpoint=checkpoint)
            self.assertFalse(checkpoint.exists())
        self.assertEqual(calls, ["a", "b", "b"])
        self.assertEqual([pair["replacements"] for pair in data["pairs"]], [1, 1])
        self.assertEqual((data["rules"][0]["old"], data["rules"][0]["new"]), ("OldApi.x", "NewApi.x"))

    def _escalation_calls_after_a_change(self, change: str) -> list[str]:
        """Interrupt `escalation run --all` at p2, apply `change`, run again; returns the packets the agent ran."""
        import argparse
        from unittest import mock

        from bridgeforge import cmd_revive
        from bridgeforge.escalation import escalation

        calls = []

        def run_packet(workspace, name, agent, **_kwargs):
            calls.append(name)
            if name == "p2" and calls.count("p2") == 1:
                raise _Interrupted
            return {"packet": name, "outcome": "VERIFIED", "attempts": [{}]}

        with resolved_temp_dir() as root:
            packets = escalation.packets_dir(root)
            packets.mkdir(parents=True)
            for name in ("p1", "p2"):
                (packets / f"{name}.json").write_text(json.dumps({"id": name}), encoding="utf-8")
            args = argparse.Namespace(workspace=root, all=True, quiet=True, agent="x", apply=False, retries=1, timeout=1,
                                      auto_accept=False)
            with mock.patch.object(escalation, "run_packet", side_effect=run_packet):
                with self.assertRaises(_Interrupted):
                    cmd_revive.run_packets(args, ["p1", "p2"])
                if change == "packet rewritten":
                    (packets / "p1.json").write_text(json.dumps({"id": "p1", "finding": "another"}), encoding="utf-8")
                elif change == "timeout":
                    args.timeout = 2
                elif change == "auto-accept":
                    args.auto_accept = True
                cmd_revive.run_packets(args, ["p1", "p2"])
        return calls

    def test_escalation_run_all_starts_afresh_when_a_packet_or_an_option_changed(self):
        """A packet that `revive` wrote afresh, or another --timeout or --auto-accept, is not skipped as finished."""
        self.assertEqual(self._escalation_calls_after_a_change("nothing"), ["p1", "p2", "p2"])
        for change in ("packet rewritten", "timeout", "auto-accept"):
            with self.subTest(change=change):
                self.assertEqual(self._escalation_calls_after_a_change(change), ["p1", "p2", "p1", "p2"])

    def test_auto_open_starts_afresh_when_a_workspace_was_revived_in_between(self):
        from unittest import mock

        from bridgeforge import auto_open as module

        calls = []

        def explain(workspace, standing):
            calls.append(workspace.name)
            if workspace.name == "ModB" and calls.count("ModB") == 1:
                raise _Interrupted
            return []

        with resolved_temp_dir() as queue:
            for name in ("ModA", "ModB"):
                (queue / name / "reports" / "revive").mkdir(parents=True)
            checkpoint = queue / module.CHECKPOINT_NAME
            with mock.patch.object(module, "explain_workspace", side_effect=explain):
                with self.assertRaises(_Interrupted):
                    module.auto_open(queue, checkpoint=checkpoint)
                (queue / "ModA" / "reports" / "revive" / "REVIVE.json").write_text("{}", encoding="utf-8")
                module.auto_open(queue, checkpoint=checkpoint)
        self.assertEqual(calls, ["ModA", "ModB", "ModA", "ModB"])

    def test_atlas_migrations_start_afresh_with_other_api_jars(self):
        from unittest import mock

        from bridgeforge.atlas import atlas_migrations as module

        calls = []

        def replacements(old, new, catalogue):
            calls.append(old.parent.name)
            if old.parent.name == "b" and calls.count("b") == 1:
                raise _Interrupted
            return []

        with resolved_temp_dir() as root:
            pairs = []
            for name in ("a", "b"):
                (root / name / "old").mkdir(parents=True)
                (root / name / "new").mkdir(parents=True)
                pairs.append(module.Pair(f"{name}: old -> new", root / name / "old", root / name / "new"))
            checkpoint = root / "MIGRATIONS.partial.jsonl"
            first = {"old": {"sha256": "1" * 64}, "new": {"sha256": "2" * 64}}
            other = {"old": {"sha256": "1" * 64}, "new": {"sha256": "3" * 64}}
            with mock.patch.object(module, "pair_replacements", side_effect=replacements):
                with self.assertRaises(_Interrupted):
                    module.mine(pairs, first, None, checkpoint=checkpoint)
                module.mine(pairs, other, None, checkpoint=checkpoint)
        self.assertEqual(calls, ["a", "b", "a", "b"])


if __name__ == "__main__":
    unittest.main()
