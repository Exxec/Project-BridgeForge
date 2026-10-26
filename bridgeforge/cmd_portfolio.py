"""Explicit read-only portfolio scan; no default concurrency expansion."""
import argparse
import json
from pathlib import Path
import sys

from .case_store import CaseStore
from .portfolio import _read, scan_portfolio


def add_parser(subcommands):
    parser = subcommands.add_parser('portfolio-scan', help='bounded read-only analysis of explicit S1 candidates; never qualification')
    parser.add_argument('selection', type=Path, help='schema-1 JSON with cases: [{case_id, candidate_id}]')
    parser.add_argument('--store', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='private results outside workspaces/store/selected inputs')
    parser.add_argument('--jobs', type=int, choices=(1, 2), default=1)
    parser.add_argument('--memory-mib', type=int, required=True, help='sampled worker-family RSS stop threshold; coordinator additional')
    parser.add_argument('--timeout', type=float, default=900, help='seconds per worker')
    parser.add_argument('--reuse-parses', action='store_true', help='opt into the measured bounded invocation-local parsing cache')
    parser.add_argument('--quiet', action='store_true')
    parser.add_argument('--json', action='store_true')


def run_cli(args: argparse.Namespace) -> int:
    try:
        selection = _read(args.selection)
        if set(selection) != {'schema_version', 'cases'} or type(selection['schema_version']) is not int or selection['schema_version'] != 1:
            raise ValueError('Expected schema-1 portfolio candidate selection')
        result = scan_portfolio(CaseStore(args.store), selection['cases'], args.output, jobs=args.jobs,
                                memory_mib=args.memory_mib, timeout=args.timeout,
                                reuse_parses=args.reuse_parses, quiet=args.quiet)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        print('bridgeforge portfolio-scan: ' + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2) if args.json else result['state'] + '; qualification NOT_EVALUATED')
    return 0 if result['state'] == 'COMPLETE' else 1
