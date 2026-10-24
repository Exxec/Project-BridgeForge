"""Explicit operator surface for the S1 case library; legacy commands keep their contracts."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import uuid

from .case_identity import CONTEXT_ROLES, capture_candidate, digest
from .case_operations import finalize_case, prepare_case, prepare_case_run
from .case_qualification import TARGET, qualify_case
from .case_store import CaseStore, _unique
from .case_workspace import _physical, open_workspace_view


def load_inputs(path: Path) -> dict:
    _physical(path)
    record = json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=_unique)
    if (not isinstance(record, dict) or set(record) != {'schema_version', 'inputs'}
            or type(record['schema_version']) is not int or record['schema_version'] != 1
            or not isinstance(record['inputs'], dict) or set(record['inputs']) - set(CONTEXT_ROLES)):
        raise ValueError('Inputs file needs schema_version 1 and supported named inputs groups')
    inputs = {}
    for role, group in record['inputs'].items():
        if group is None:
            inputs[role] = None
            continue
        if not isinstance(group, dict):
            raise ValueError(role + ': expected named path inputs or null')
        inputs[role] = {}
        for name, value in group.items():
            if not isinstance(value, str) or not value.strip() or not Path(value).is_absolute():
                raise ValueError(role + '.' + name + ': provide an absolute input path')
            inputs[role][name] = Path(value)
    return inputs


def status(store: CaseStore, case_id: str) -> dict:
    case = store.load_case(case_id)
    store.workspace(case_id)
    folder = _physical(store.root / case_id / 'candidates')
    candidates = []
    for path in sorted(folder.glob('*.json')):
        try:
            value = store.assess_candidate(case_id, path.stem)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            value = {'state': 'INCOMPLETE', 'reason': str(exc)}
        candidates.append({'candidate_id': path.stem, **value})
    from .case_operations import _read
    operations = []
    operation_root = _physical(store.root / case_id / 'operations')
    for path in sorted(operation_root.iterdir() if operation_root.exists() else []):
        try:
            plan = _read(path / 'plan.json')
            if digest(plan) != path.name or plan.get('case_id') != case_id:
                raise ValueError('Operation plan identity/path mismatch')
            checkpoint = _read(path / 'checkpoint.json')
            if checkpoint.get('operation_id') != path.name or checkpoint.get('state') not in {'PREPARED', 'PACKAGED', 'COMPLETE'}:
                raise ValueError('Unsupported operation checkpoint')
            row = {'operation_id': path.name, 'state': 'RECORDED', 'recorded_state': checkpoint['state'],
                   'candidate_id': plan['candidate_id'], 'archive_root': plan['archive_root'],
                   'authority': 'HISTORICAL_CHECKPOINT_NOT_CURRENT_QUALIFICATION'}
        except (OSError, ValueError, KeyError, TypeError) as exc:
            row = {'operation_id': path.name, 'state': 'INCOMPLETE', 'reason': str(exc)}
        operations.append(row)
    return {'schema_version': 1, 'case_id': case_id, 'scope': case['content']['declared_scope'],
            'workspace': case['content']['workspace'], 'candidates': candidates, 'operations': operations,
            'state': 'CURRENT_INPUTS' if candidates and all(row['state'] == 'CURRENT' for row in candidates) and all(row['state'] == 'RECORDED' for row in operations) else 'INCOMPLETE',
            'authority': 'INPUT_IDENTITY_ONLY_NOT_QUALIFICATION'}


def add_parser(subcommands) -> None:
    command = subcommands.add_parser('case', help='reproducible local-new-game cases: capture, qualify, prepare, bind a run and finalize a local archive')
    sub = command.add_subparsers(dest='case_command', required=True)
    for name, help_text in (
        ('open', 'open either workspace layout and capture explicit inputs; never move originals'),
        ('capture', 'capture current case inputs, optionally superseding a previous candidate'),
        ('status', 'recheck candidate identities; current inputs are not qualification'),
        ('qualify', 'evaluate fresh evidence for the declared local-new-game scope'),
        ('prepare', 'freeze an already selected version for a new local archive operation'),
        ('prepare-run', 'bind an already staged isolated rig; never launch or overwrite mods'),
        ('finalize', 'requalify and publish exact tested bytes to a fresh local archive directory'),
    ):
        parser = sub.add_parser(name, help=help_text)
        parser.add_argument('--store', type=Path, required=True, help='case state directory outside the workspace and selected inputs')
        parser.add_argument('--json', action='store_true', help='print structured results')
        if name == 'open':
            parser.add_argument('workspace', type=Path)
            parser.add_argument('--case-id', help='explicit 32-hex identity for retrying an interrupted open')
            parser.add_argument('--original-relative', help='explicit selected mod within a legacy original container')
        else:
            parser.add_argument('case_id')
        if name in {'open', 'capture'}:
            parser.add_argument('--inputs', type=Path, required=True, help='schema-1 JSON input paths; absolute paths only')
        if name == 'capture':
            parser.add_argument('--predecessor', help='previous candidate ID, preserved as lineage')
        if name in {'qualify', 'prepare'}:
            parser.add_argument('candidate_id')
        if name == 'prepare':
            parser.add_argument('--archive-root', type=Path, required=True)
        if name in {'prepare-run', 'finalize'}:
            parser.add_argument('operation_id')
        if name in {'qualify', 'prepare-run', 'finalize'}:
            parser.add_argument('--compile', action='store_true', dest='run_compile', help='run full applicable loose-source javac and RC8 Janino checks')
            parser.add_argument('--rig', type=Path, required=name != 'qualify')
            parser.add_argument('--run-id', required=name != 'qualify')


def run_cli(args) -> int:
    try:
        store = CaseStore(args.store)
        command = args.case_command
        if command == 'open':
            view, inputs = open_workspace_view(args.workspace, original_relative=args.original_relative), load_inputs(args.inputs)
            case_id = args.case_id or uuid.uuid4().hex
            # Validate physical input bytes before creating a durable case. Any later
            # interruption can be recovered with the printed/persisted case identity.
            capture_candidate(view, case_id=case_id, target_profile=TARGET, inputs=inputs)
            case = store.create_case(view, target_profile=TARGET, declared_scope='local-new-game', case_id=case_id)
            candidate = store.add_candidate(case_id, inputs=inputs)
            value = {'state': 'CAPTURED', 'case_id': case['content']['case_id'], 'candidate_id': candidate['record_id'],
                     'missing_context': candidate['content']['context']['missing_roles']}
        elif command == 'capture':
            candidate = store.add_candidate(args.case_id, inputs=load_inputs(args.inputs), predecessor=args.predecessor)
            value = {'state': 'CAPTURED', 'case_id': args.case_id, 'candidate_id': candidate['record_id'],
                     'missing_context': candidate['content']['context']['missing_roles']}
        elif command == 'status':
            value = status(store, args.case_id)
        elif command == 'prepare':
            value = prepare_case(store, args.case_id, args.candidate_id, archive_root=args.archive_root)
        else:
            if bool(args.rig) != bool(args.run_id):
                raise ValueError('--rig and --run-id must be supplied together')
            if command == 'qualify':
                live = (args.rig, args.run_id) if args.rig else None
                value = qualify_case(store, args.case_id, args.candidate_id, run_compile=args.run_compile, live=live)
            elif command == 'prepare-run':
                value = prepare_case_run(store, args.case_id, args.operation_id, rig=args.rig, run_id=args.run_id, run_compile=args.run_compile)
            else:
                value = finalize_case(store, args.case_id, args.operation_id, run_compile=args.run_compile, live=(args.rig, args.run_id))
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        print('bridgeforge case: ' + str(exc), file=sys.stderr)
        if getattr(args, 'case_command', '') == 'open' and 'case_id' in locals():
            print('Resume with --case-id ' + case_id + '; inspect --store before retrying.', file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(value, indent=2, ensure_ascii=False))
    else:
        print(value['state'])
        for key in ('case_id', 'candidate_id', 'operation_id', 'archive'):
            if key in value:
                print(key + ': ' + str(value[key]))
        if command == 'status':
            for row in value['candidates']:
                print(row['candidate_id'] + ': ' + row['state'])
            for row in value['operations']:
                print(row['operation_id'] + ': historical ' + row.get('recorded_state', 'INCOMPLETE'))
        if command in {'qualify', 'finalize'}:
            report = value.get('qualification', value)
            for name, row in report.get('dimensions', {}).items():
                print(name + ': ' + row['status'] + ' - ' + row['reason'])
    return 1 if value['state'] in {'REFUSED', 'INCOMPLETE'} else 0
