"""`gates check|lint|record` (ROADMAP-3 80.6, 80.2). The session plan itself is `board --live-pending`."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .gates import RECORDABLE, lint_gates, load_gates, record_gate


def add_parser(subcommands) -> None:
    gates = subcommands.add_parser("gates", help="check, lint or update a repo's gates.json (schema 1)")
    sub = gates.add_subparsers(dest="gates_command", required=True)
    for name, text in (("check", "validate gates.json against the schema"),
                       ("lint", "fail when a cited status line does not contain the gate's state word")):
        cmd = sub.add_parser(name, help=text)
        cmd.add_argument("repo_dir", type=Path)
    record = sub.add_parser("record", help="write a result back into gates.json (that file only)")
    record.add_argument("gate_id")
    record.add_argument("--repo", type=Path, required=True)
    record.add_argument("--state", required=True, choices=list(RECORDABLE))
    record.add_argument("--evidence", nargs="*", default=[], help="paths or run ids")


def run_cli(args: argparse.Namespace) -> int:
    try:
        if args.gates_command == "record":
            gate = record_gate(args.repo, args.gate_id, args.state, args.evidence)
            print(f"{gate['id']}: {gate['state']} ({gate['updated']}); update the cited status doc to match, then `gates lint`.")
            return 0
        data = load_gates(args.repo_dir)
        if args.gates_command == "check":
            print(f"OK: {len(data['gates'])} gate(s) in {args.repo_dir}")
            return 0
        problems = lint_gates(args.repo_dir, data)
    except (ValueError, OSError) as exc:
        print(f"bridgeforge: {exc}", file=sys.stderr)
        return 2
    for problem in problems:
        print(f"LINT: {problem}")
    print(f"{'FAIL' if problems else 'OK'}: {len(problems)} contradiction(s)")
    return 1 if problems else 0
