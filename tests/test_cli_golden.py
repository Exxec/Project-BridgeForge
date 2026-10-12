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
from pathlib import Path

from bridgeforge.cli import build_parser

GOLDEN = Path(__file__).with_name("cli_help_golden.json")
HELP_COLUMNS = "100"


def _walk(parser: argparse.ArgumentParser, prefix: str, out: dict[str, str]) -> None:
    out[prefix or "bridgeforge"] = hashlib.sha256(parser.format_help().encode("utf-8")).hexdigest()[:16]
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
