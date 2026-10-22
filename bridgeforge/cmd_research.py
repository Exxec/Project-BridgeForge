"""`research report FEATURE --case WORKSPACE --question TEXT [--write DIR]` (ROADMAP-3 82.1, 82.2): read-only comparative research report;
`research diff OLD NEW` (82.9): readable diffs of the methods whose bytecode changed."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .atlas import DEFAULT_DB
from .research_decompile import DEFAULT_MAX_CLASSES
from .research_diff import DEFAULT_MAX_LINES, DEFAULT_MAX_METHODS, DiffError, build_diff
from .research_diff import render_markdown as render_diff_markdown
from .research_diff import stdout_summary as diff_summary
from .research_render import render_markdown, stdout_summary
from .research_report import ResearchError, build_report
from .safeio import atomic_write_json, atomic_write_text

REPORT_STEM = "research-report"
DIFF_STEM = "research-diff"


def add_parser(subcommands) -> None:
    research = subcommands.add_parser("research", help="read-only research over a case workspace (82.1 comparative report, 82.2 Atlas vs D-series reconciliation)")
    sub = research.add_subparsers(dest="research_command", required=True)
    report = sub.add_parser("report", help="answer a stated question about a feature across a case workspace, Atlas-indexed mods and the D-series; every claim labelled STATIC/OBSERVED/VALIDATED with its evidence")
    report.add_argument("feature", help="comma separated search terms: class names, rule ids, csv ids, strings; `*` is a wildcard, `name.csv` also matches that file")
    report.add_argument("--case", required=True, type=Path, help='case workspace, e.g. "In operation/Templars-0.9.8f"')
    report.add_argument("--question", required=True, help="the question the report must answer")
    report.add_argument("--write", type=Path, metavar="DIR", help=f"write {REPORT_STEM}.md and {REPORT_STEM}.json into DIR (atomic)")
    report.add_argument("--atlas-db", type=Path, help=f"atlas database (default: {DEFAULT_DB.as_posix()} here, else under the case's repo root)")
    report.add_argument("--repo", type=Path, help="repo holding gates.json (default: the nearest folder above the working directory that has one)")
    report.add_argument("--no-build", action="store_true", help="do not build archaeology in memory (about 25 s per tree); report it as missing with its command instead")
    report.add_argument("--peer", action="append", default=[], type=Path, metavar="WS", help="a sibling case workspace (or mod folder) whose own tree is compared too; repeatable; read-only")
    report.add_argument("--no-decompile", action="store_true", help="do not decompile the jar classes the terms touch (82.7); needs Vineflower and a JDK otherwise, reported as missing when absent")
    report.add_argument("--max-classes", type=int, default=DEFAULT_MAX_CLASSES, help=f"decompile at most this many top-level classes (default {DEFAULT_MAX_CLASSES}); the decompiled code is cached by jar hash under DIR/decompiled/")
    report.add_argument("--json", action="store_true", help="print the JSON report instead of the summary")
    diff = sub.add_parser("diff", help="readable version diff (82.9): the bytecode decides which methods changed, then only those methods' decompiled text is diffed (STATIC); methods carry their bytecode identity (82.8)")
    diff.add_argument("old", type=Path, help="the older version: a .jar, a mod folder (its loaded jars) or a folder holding one, e.g. a case's original/ or an old/ release folder from pairs.json")
    diff.add_argument("new", type=Path, help="the newer version, same forms, e.g. a case's working/ folder")
    diff.add_argument("--classes", default="", help="comma separated class-name terms (same matching as the report's feature terms) limiting which classes are compared")
    diff.add_argument("--max-methods", type=int, default=DEFAULT_MAX_METHODS, help=f"show at most this many changed methods (default {DEFAULT_MAX_METHODS}); the rest are only counted")
    diff.add_argument("--max-lines", type=int, default=DEFAULT_MAX_LINES, help=f"at most this many diff lines per method (default {DEFAULT_MAX_LINES})")
    diff.add_argument("--write", type=Path, metavar="DIR", help=f"write {DIFF_STEM}.md and {DIFF_STEM}.json into DIR and keep the decompiled cache in DIR/decompiled/ (atomic); refused inside OLD or NEW")
    diff.add_argument("--repo", type=Path, help="checkout holding In operation/_tools (Vineflower) when this one has none, e.g. a git worktree (default: the nearest folder above OLD that has an `In operation/`, else this checkout)")
    diff.add_argument("--json", action="store_true", help="print the JSON result instead of the summary")


def _atlas_db(args: argparse.Namespace) -> Path:
    if args.atlas_db:
        return args.atlas_db
    here = DEFAULT_DB
    return here if here.is_file() else Path(args.case).expanduser().resolve().parent.parent / DEFAULT_DB


def _home_of(path: Path) -> Path | None:
    """The nearest folder above `path` that holds `In operation/` (where Vineflower is kept), for a run from a git worktree."""
    return next((p for p in Path(path).expanduser().resolve().parents if (p / "In operation").is_dir()), None)


def _run_diff(args: argparse.Namespace) -> int:
    if args.max_methods < 1 or args.max_lines < 1:
        print("bridgeforge: --max-methods and --max-lines must be at least 1", file=sys.stderr)
        return 2
    target = Path(args.write).expanduser().resolve() if args.write else None
    for side in (args.old, args.new):
        root = Path(side).expanduser().resolve()
        root = root.parent if root.is_file() else root
        if target and (target == root or root in target.parents):
            print(f"bridgeforge: --write {target} is inside {root}; the diff never writes into a version tree", file=sys.stderr)
            return 2
    try:
        result = build_diff(args.old, args.new, classes=args.classes, max_methods=args.max_methods, max_lines=args.max_lines,
                            cache_dir=target / "decompiled" if target else None, home=args.repo or _home_of(args.old))
    except (DiffError, OSError) as exc:
        print(f"bridgeforge: {exc}", file=sys.stderr)
        return 2
    written: list[str] = []
    if target:
        written = [str(atomic_write_text(target / f"{DIFF_STEM}.md", render_diff_markdown(result), newline="")), str(atomic_write_json(target / f"{DIFF_STEM}.json", result))]
    print(json.dumps(result, indent=2, ensure_ascii=False) if args.json else diff_summary(result, written))
    return 0


def run_cli(args: argparse.Namespace) -> int:
    if args.research_command == "diff":
        return _run_diff(args)
    if args.research_command != "report":
        return 2
    if args.write:
        case = Path(args.case).expanduser().resolve()
        target = Path(args.write).expanduser().resolve()
        if target == case or case in target.parents:
            print(f"bridgeforge: --write {target} is inside the case workspace; the report never writes into a workspace", file=sys.stderr)
            return 2
    try:
        report = build_report(args.feature, args.case, args.question, atlas_db=_atlas_db(args), repo=args.repo, build=not args.no_build,
                              peer_workspaces=tuple(args.peer), decompile=not args.no_decompile, max_classes=args.max_classes,
                              cache_dir=Path(args.write).expanduser().resolve() / "decompiled" if args.write else None)
    except (ResearchError, OSError) as exc:
        print(f"bridgeforge: {exc}", file=sys.stderr)
        return 2
    written: list[str] = []
    if args.write:
        target = Path(args.write).expanduser().resolve()
        written = [str(atomic_write_text(target / f"{REPORT_STEM}.md", render_markdown(report), newline="")), str(atomic_write_json(target / f"{REPORT_STEM}.json", report))]
    print(json.dumps(report, indent=2, ensure_ascii=False) if args.json else stdout_summary(report, written))
    return 0
