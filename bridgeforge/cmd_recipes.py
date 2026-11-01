"""Explicit recipe trials over a named cohort; reports a promotion gate and never approves anything."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

from .recipe_trial import RecipeTrialError, read_cohort, run_trial


def add_parser(subcommands):
    parser = subcommands.add_parser('recipe-trial', help='try each fixer on private copies of a training/holdout cohort and report its promotion gate; writes no input, policy or ruling')
    parser.add_argument('cohort', type=Path, help='schema-1 JSON with cases: [{name, path, split}], split training or holdout')
    parser.add_argument('--output', type=Path, required=True, help='report JSON, outside every input')
    parser.add_argument('--core', type=Path, help='vanilla starsector-core; without it, Java edits are not compile-checked')
    parser.add_argument('--policy', type=Path, help='AUTOMATION_POLICY.json, read to show which recipes are already approved')
    parser.add_argument('--queue', type=Path, help='folder holding ESCALATION_RULINGS.jsonl, read to find revoked approvals')
    parser.add_argument('--quiet', action='store_true')
    parser.add_argument('--json', action='store_true')


def run_cli(args: argparse.Namespace) -> int:
    try:
        report = run_trial(read_cohort(args.cohort), core=args.core, output=args.output, policy_path=args.policy, queue=args.queue, quiet=args.quiet)
    except (RecipeTrialError, OSError) as exc:
        print(f'recipe-trial: {exc}', file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0
    states = Counter(row['state'] for row in report['gate'])
    print(f"{len(report['cases'])} case(s), {len(report['gate'])} recipe(s): " + (', '.join(f'{count} {state}' for state, count in sorted(states.items())) or 'nothing to try'))
    for row in report['gate']:
        print(f"  {row['state']:<23} {row['finding']}{' (approved)' if row['approved'] else ''}: {'; '.join(row['why'])}")
    print(f'Report: {args.output}')
    return 0
