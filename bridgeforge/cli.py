"""The `bridgeforge` command line. Each command's parser and handler live in a `cmd_<group>.py` module listed in
`cli_commands.COMMAND_MODULES` (ROADMAP 70 H2.1); this file keeps the argv rewrites, stream setup and dispatch."""
from __future__ import annotations

import argparse
import sys

from .cli_commands import dispatch, register_all


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bridgeforge", description="Safe, explainable legacy Starsector mod analysis and migration.")
    subcommands = parser.add_subparsers(dest="command", required=True)
    register_all(subcommands)
    return parser


def _reconfigure_streams_for_pipes(streams=None) -> list:
    """Switch stdout/stderr to UTF-8 (errors="replace") when they aren't an interactive console.

    Windows' default piped/redirected-output codepage (cp1252) corrupts the non-ASCII text several
    modules print (`--json` output built with `ensure_ascii=False`, translate-check's CJK strings,
    ...) -- `UnicodeEncodeError` piping `bridgeforge ... --json > out.json` on Windows (task A9).
    An interactive console is left exactly as the user configured it: this only touches a stream
    that exposes `TextIOWrapper.reconfigure` and whose `isatty()` returns false (a pipe or a
    redirected file) -- a real console's own encoding is never overridden. A stream with no
    `isatty` at all (unusual for real stdout/stderr, but true of some test doubles) is treated as
    non-interactive and reconfigured; one whose `isatty()` call itself raises is left untouched,
    since that failure means the stream's state can't be trusted either way. Returns the streams
    actually reconfigured, so this can be asserted on directly in a test.
    """
    reconfigured = []
    for stream in streams if streams is not None else (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        isatty = getattr(stream, "isatty", None)
        if isatty is not None:
            try:
                if isatty():
                    continue
            except (OSError, ValueError):
                continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            continue
        reconfigured.append(stream)
    return reconfigured


def main(argv: list[str] | None = None) -> int:
    if argv and argv[0] == "dependency-graph" and "--repo-root" in argv:
        argv = ["dependency-graph-local", *argv[1:]]
    if argv and argv[0] == "rebuild-from-reference" and "--current-core" in argv:
        argv = ["rebuild-from-reference-local", *argv[1:]]
    _reconfigure_streams_for_pipes()
    args = build_parser().parse_args(argv)
    registered = dispatch(args)
    return 2 if registered is None else registered
