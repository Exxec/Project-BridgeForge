"""Private metadata transfer and explicit unqualified rebinding, never payload publication."""
import json
from pathlib import Path
import sys

from .case_exchange import export_private_case, import_private_case, read_exchange, exchange_summary
from .case_store import CaseStore
from .cmd_case import load_inputs


def add_parser(subcommands):
    root = subcommands.add_parser('case-exchange', help='private case metadata exchange; restore payload separately and requalify')
    sub = root.add_subparsers(dest='exchange_command', required=True)
    for name in ('export', 'import', 'summary', 'requirements'):
        parser = sub.add_parser(name)
        parser.add_argument('--json', action='store_true')
        if name == 'export':
            parser.add_argument('case_id'); parser.add_argument('candidate_id')
            parser.add_argument('--output', type=Path, required=True)
        else:
            parser.add_argument('manifest', type=Path)
        if name in {'export', 'import'}:
            parser.add_argument('--store', type=Path, required=True)
        if name == 'import':
            parser.add_argument('--workspace', type=Path, required=True, help='already restored isolated workspace')
            parser.add_argument('--inputs', type=Path, required=True, help='explicit schema-1 path bindings on this machine')
            parser.add_argument('--allow-context-change', action='store_true', help='capture changed external analysis context unqualified; policy/review bytes cannot change')


def run_cli(args):
    try:
        if args.exchange_command == 'export':
            value = export_private_case(CaseStore(args.store), args.case_id, args.candidate_id, args.output)
        else:
            record = read_exchange(args.manifest)
            if args.exchange_command == 'import':
                value = import_private_case(record, CaseStore(args.store), args.workspace, load_inputs(args.inputs),
                                            allow_context_change=args.allow_context_change)
            elif args.exchange_command == 'summary':
                value = exchange_summary(record)
            else:
                groups = record['content']['candidate']['content']['context']['inputs']
                value = {'schema_version': 1, 'expected': {role: None if group is None else {
                    name: {k: v for k, v in item.items() if k != 'path'} for name, item in group.items()}
                    for role, group in groups.items()},
                    'binding_template': {'schema_version': 1, 'inputs': {role: None if group is None else {
                        name: 'ABSOLUTE_PATH_REQUIRED' for name in group} for role, group in groups.items()}},
                    'payload': 'RESTORE_SEPARATELY_USING_PRIVATE_SNAPSHOT', 'publication_authorized': False}
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        print('bridgeforge case-exchange: ' + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(value, indent=2, ensure_ascii=False))
    return 0
