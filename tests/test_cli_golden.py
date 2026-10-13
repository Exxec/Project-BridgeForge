"""ROADMAP 70 H2.1: the command line must not change when cli.py is split.

`tests/cli_help_golden.json` holds a hash of the --help text of every command and sub-command. A refactor that drops, renames or
re-words an option fails here and names the commands. A deliberate change regenerates the file:
`python -m tests.test_cli_golden --write`, and the diff is reviewed in the commit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import unittest
from pathlib import Path, PurePath

from bridgeforge.cli import build_parser

GOLDEN = Path(__file__).with_name("cli_help_golden.json")
HELP_COLUMNS = "100"


def _plain(value: object) -> object:
    """A default as the same text on every machine: paths with forward slashes and the home folder as ~."""
    if isinstance(value, PurePath):
        return value.as_posix().replace(Path.home().as_posix(), "~")
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value if isinstance(value, (str, int, float, bool, type(None))) else repr(value)


def _help_text(parser: argparse.ArgumentParser, prefix: str) -> str:
    """What --help says, as data rather than formatted text: argparse lays the text out differently on each Python (CI runs 3.10 to
    3.13 and differed from the 3.14 golden, 2026-10-13), and a default may name this machine's home folder. For the top-level parser
    the command list is sorted, since the order commands register in is not part of the interface."""
    if not prefix:
        listed = sorted((action.dest, action.help or "") for sub in parser._actions if isinstance(sub, argparse._SubParsersAction)
                        for action in sub._choices_actions)
        return json.dumps([parser.prog, parser.description, listed])
    actions = []
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            actions.append(["subcommands", sorted((a.dest, a.help or "") for a in action._choices_actions)])
            continue
        actions.append([list(action.option_strings), action.dest, str(action.nargs), _plain(action.default), _plain(action.const),
                        list(action.choices) if action.choices and not isinstance(action.choices, dict) else None,
                        bool(action.required), " ".join((action.help or "").split()), _plain(action.metavar),
                        type(action).__name__])
    return json.dumps([parser.description, " ".join((parser.epilog or "").split()), actions], sort_keys=True, default=str)


def _walk(parser: argparse.ArgumentParser, prefix: str, out: dict[str, str]) -> None:
    out[prefix or "bridgeforge"] = hashlib.sha256(_help_text(parser, prefix).encode("utf-8")).hexdigest()[:16]
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, child in sorted(action.choices.items()):
                _walk(child, f"{prefix} {name}".strip(), out)


def snapshot() -> dict[str, str]:
    previous = os.environ.get("COLUMNS")
    os.environ["COLUMNS"] = HELP_COLUMNS  # argparse wraps to the terminal width
    try:
        out: dict[str, str] = {}
        _walk(build_parser(), "", out)
        return out
    finally:
        if previous is None:
            os.environ.pop("COLUMNS", None)
        else:
            os.environ["COLUMNS"] = previous


class CliGoldenTests(unittest.TestCase):
    def test_every_command_and_option_help_is_unchanged(self) -> None:
        golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
        current = snapshot()
        removed = sorted(set(golden) - set(current))
        added = sorted(set(current) - set(golden))
        changed = sorted(name for name in set(golden) & set(current) if golden[name] != current[name])
        self.assertEqual((removed, added, changed), ([], [], []),
                         "command line changed; if deliberate run `python -m tests.test_cli_golden --write` and review the diff")


if __name__ == "__main__":
    if "--write" in sys.argv:
        GOLDEN.write_text(json.dumps(snapshot(), indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {GOLDEN} ({len(snapshot())} commands)")
    else:
        unittest.main()
