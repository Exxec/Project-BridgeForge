"""Fresh exact-input comparison of named S3 scenario observations."""
import json
from pathlib import Path
import sys

from .behavior_comparison import compare_behavior_scenarios
from .case_store import _unique
from .case_workspace import _physical


def add_parser(subcommands):
    parser = subcommands.add_parser('case-behavior-compare', help='compare bound named probe assertion vectors; never whole-feature qualification')
    parser.add_argument('selection', type=Path, help='schema-1 object with candidate selector and reference selector or null')
    parser.add_argument('--deviation', type=Path, help='exact scoped owner decision; cannot waive a failing assertion')
    parser.add_argument('--json', action='store_true')


def run_cli(args):
    try:
        path = _physical(args.selection)
        if path.stat().st_size > 1024 * 1024:
            raise ValueError('Comparison selection exceeds 1 MiB')
        selected = json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=_unique)
        if (not isinstance(selected, dict) or set(selected) != {'schema_version', 'candidate', 'reference'}
                or type(selected['schema_version']) is not int or selected['schema_version'] != 1):
            raise ValueError('Comparison selection requires schema_version 1, candidate and reference')
        value = compare_behavior_scenarios(selected['candidate'], selected['reference'], deviation=args.deviation)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        print('bridgeforge case-behavior-compare: ' + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(value, indent=2) if args.json else value['state'] + '; qualification NOT_EVALUATED')
    return 0 if value['state'] in {'ASSERTION_VECTOR_MATCH', 'EXPECTED_SCOPED_DEVIATION'} else 1
