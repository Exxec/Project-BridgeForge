"""S1 prepared local archives: immutable inputs, fresh qualification, recoverable publication.

Existing archive gates run in private convention-layout copies, never against the source.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
import shutil
import uuid
import zipfile

from .archive import archive_mod
from .case_identity import digest, file_digest, require_digest, tree_digest, tree_files
from .case_qualification import engine_identity, qualify_case
from .case_store import CaseStore
from .case_workspace import _physical
from .copy_drift import _collect
from .safeio import atomic_write_json


class OperationError(ValueError):
    """Operation refused or interrupted; all prior artifacts are preserved."""


def _read(path: Path) -> dict:
    _physical(path)
    value = json.loads(path.read_text(encoding='utf-8'))
    if (not isinstance(value, dict) or set(value) != {'schema', 'schema_version', 'content', 'record_id'}
            or value['schema'] != 'bridgeforge.case-operation' or type(value['schema_version']) is not int
            or value['schema_version'] != 1 or not isinstance(value['content'], dict)
            or value['record_id'] != digest(value['content'])):
        raise OperationError('Unsupported or damaged operation record')
    return value['content']


def _write(path: Path, content: dict) -> None:
    _physical(path)
    atomic_write_json(path, {'schema': 'bridgeforge.case-operation', 'schema_version': 1,
                             'record_id': digest(content), 'content': content})


def _overlap(a: Path, b: Path) -> bool:
    return a.is_relative_to(b) or b.is_relative_to(a)


def _destination(store: CaseStore, case: str, candidate: dict, destination: Path) -> Path:
    destination = _physical(Path(destination).expanduser())
    view = store.workspace(case)
    forbidden = [store.root, view.root]
    for group in candidate['content']['context']['inputs'].values():
        forbidden.extend(Path(item['path']) for item in (group or {}).values())
    if any(_overlap(destination, path) for path in forbidden):
        raise OperationError('Archive destination overlaps case state, workspace or selected context')
    return destination


def _current(store: CaseStore, case: str, candidate: str) -> None:
    if store.assess_candidate(case, candidate)['state'] != 'CURRENT':
        raise OperationError('Candidate or context changed; prepare a new candidate')


def _copy(source: Path, target: Path, inventory: dict) -> None:
    target.mkdir(parents=True, exist_ok=False)
    for relative, expected in inventory.items():
        before = _physical(source / relative)
        if file_digest(before) != expected:
            raise OperationError('Source changed during preparation: ' + relative)
        after = target / relative
        after.parent.mkdir(parents=True, exist_ok=True)
        # Each attempt is new. Never overwrite even an interrupted copy.
        with before.open('rb') as src, after.open('xb') as dst:
            shutil.copyfileobj(src, dst)
        if file_digest(after) != expected:
            raise OperationError('Copied bytes do not match candidate: ' + relative)
    if tree_files(target) != inventory:
        raise OperationError('Prepared input inventory mismatch')


def prepare_case(store: CaseStore, case_id: str, candidate_id: str, *, archive_root: Path) -> dict:
    """Freeze an already chosen version; do not bump or edit workspace/mod files."""
    candidate = store.load_candidate(case_id, candidate_id)
    destination = _destination(store, case_id, candidate, archive_root)
    plan = {'case_id': case_id, 'candidate_id': candidate_id, 'archive_root': str(destination),
            'engine_id': engine_identity(), 'scope': 'local-new-game-archive', 'version_action': 'KEEP_PRESELECTED'}
    operation_id = digest(plan)
    root = _physical(store.root / case_id / 'operations' / operation_id)
    with store._write_lock():
        _current(store, case_id, candidate_id)
        if (root / 'plan.json').exists():
            if _read(root / 'plan.json') != plan:
                raise OperationError('Operation identity collision')
        else:
            _write(root / 'plan.json', plan)
        checkpoint = root / 'checkpoint.json'
        if checkpoint.exists():
            state = _read(checkpoint)
            _prepared(root, state, candidate)
            return {'operation_id': operation_id, **state}
        view = store.workspace(case_id)
        original, working = tree_files(view.original), tree_files(view.working)
        if tree_digest(original) != candidate['content']['original']['sha256']:
            raise OperationError('Original identity changed')
        attempt = root / 'prepare-attempts' / uuid.uuid4().hex
        workspace = attempt / ('case-' + case_id)
        # Incomplete attempts remain available for diagnosis; retry uses a fresh location.
        _copy(view.original, workspace / 'original', original)
        _copy(view.working, workspace / 'working', working)
        _current(store, case_id, candidate_id)
        if engine_identity() != plan['engine_id']:
            raise OperationError('Evaluator changed during preparation')
        state = {'operation_id': operation_id, 'state': 'PREPARED',
                 'prepared_relative': workspace.relative_to(root).as_posix(),
                 'original_files': original, 'working_files': working}
        _prepared(root, state, candidate)
        _write(checkpoint, state)
        return dict(state)


def _prepared(root: Path, state: dict, candidate: dict) -> Path:
    from .case_workspace import _components
    relative = state['prepared_relative']
    _components(relative, 'prepared workspace')
    if not re.fullmatch(r'prepare-attempts/[0-9a-f]{32}/case-' + root.parent.parent.name, relative):
        raise OperationError('Prepared path is outside this operation namespace')
    workspace = _physical(root / relative)
    if state.get('operation_id') != root.name or state.get('state') not in {'PREPARED', 'PACKAGED', 'COMPLETE'}:
        raise OperationError('Unsupported operation state')
    if (tree_files(workspace / 'original') != state['original_files']
            or tree_files(workspace / 'working') != state['working_files']):
        raise OperationError('Prepared inputs changed; no automatic repair or overwrite')
    shipped = {name: file_digest(path) for name, path in _collect(workspace / 'working').items()}
    if shipped != candidate['content']['payload']['files']:
        raise OperationError('Prepared payload differs from candidate')
    if tree_digest(state['original_files']) != candidate['content']['original']['sha256']:
        raise OperationError('Prepared original differs from candidate')
    return workspace


def _verify_archive(path: Path, folder_name: str, candidate: dict, inventory: dict | None = None) -> dict:
    current = tree_files(path)
    if inventory is not None and current != inventory:
        raise OperationError('Published/private archive changed; refusing recovery')
    if tree_digest(tree_files(path / 'original')) != candidate['content']['original']['sha256']:
        raise OperationError('Archived original differs from preserved original')
    shipped = tree_files(path / folder_name)
    if shipped != candidate['content']['payload']['files']:
        raise OperationError('Archive payload differs from tested candidate')
    zips = list(path.glob(folder_name + '-*.zip'))
    zips = [item for item in zips if not item.name.endswith('-original-descriptions.zip')]
    if len(zips) != 1:
        raise OperationError('Expected exactly one main archive zip')
    from hashlib import sha256
    with zipfile.ZipFile(zips[0]) as archive:
        entries = archive.infolist()
        expected = {folder_name + '/' + name: hashed for name, hashed in shipped.items()}
        if len(entries) != len(expected) or {item.filename for item in entries} != set(expected):
            raise OperationError('Zip inventory differs from tested payload')
        for entry in entries:
            relative = entry.filename[len(folder_name) + 1:]
            if entry.file_size != (path / folder_name / relative).stat().st_size:
                raise OperationError('Zip member size differs from tested file')
            # Compare bounded streams; no extraction and no unbounded read.
            hashed = sha256()
            with archive.open(entry) as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                    hashed.update(chunk)
            if hashed.hexdigest() != expected[entry.filename]:
                raise OperationError('Zip bytes differ from tested payload')
    return current


def finalize_case(store: CaseStore, case_id: str, operation_id: str, *, run_compile: bool = False,
                  live: tuple[Path, str] | None = None) -> dict:
    """Requalify, privately package using legacy gates, verify, publish once; never refresh."""
    require_digest(operation_id)
    store.load_case(case_id)
    root = _physical(store.root / case_id / 'operations' / operation_id)
    with store._write_lock():
        plan = _read(root / 'plan.json')
        if digest(plan) != operation_id or plan['case_id'] != case_id:
            raise OperationError('Operation plan/path mismatch')
        candidate = store.load_candidate(case_id, plan['candidate_id'])
        destination = _destination(store, case_id, candidate, Path(plan['archive_root']))
        state = _read(root / 'checkpoint.json')
        workspace = _prepared(root, state, candidate)
        if engine_identity() != plan['engine_id']:
            raise OperationError('Evaluator changed; prepare an operation with the current evaluator')
        report = qualify_case(store, case_id, plan['candidate_id'], run_compile=run_compile, live=live)
        if report['state'] != 'QUALIFIED_FOR_DECLARED_SCOPE':
            return {'operation_id': operation_id, 'state': 'REFUSED', 'qualification': report}
        if state['state'] in {'PACKAGED', 'COMPLETE'} and state.get('qualification_id') != digest(report):
            raise OperationError('Qualification artifacts/run changed since packaging; preserve archive and prepare a new operation')
        final = destination / operation_id
        _physical(final)
        if state['state'] == 'PREPARED':
            if final.exists():
                raise OperationError('Unrecorded destination exists; preserve it and recover explicitly')
            attempt = destination / '.bridgeforge-attempts' / operation_id / uuid.uuid4().hex
            _physical(attempt)
            policy = Path(candidate['content']['context']['inputs']['policy']['release']['path'])
            # Changelog/master-log side effects stay inside this private attempt.
            packaged = archive_mod(workspace, attempt / 'done', policy_path=policy)
            archive = _physical(Path(packaged['archive']))
            inventory = _verify_archive(archive, workspace.name, candidate)
            _prepared(root, state, candidate)
            _current(store, case_id, plan['candidate_id'])
            # Include qualification separately from payload; never change tested mod files.
            _write(archive / 'CASE_QUALIFICATION.json', {'operation_id': operation_id, 'qualification': report})
            inventory = _verify_archive(archive, workspace.name, candidate)
            state.update(state='PACKAGED', archive_relative=archive.relative_to(destination).as_posix(), archive_files=inventory,
                         qualification_id=digest(report))
            _write(root / 'checkpoint.json', state)
        from .case_workspace import _components
        _components(state['archive_relative'], 'private archive')
        if not re.fullmatch(r'\.bridgeforge-attempts/' + operation_id + r'/[0-9a-f]{32}/done/' + workspace.name,
                            state['archive_relative']):
            raise OperationError('Private archive is outside this operation namespace')
        archive = _physical(destination / state['archive_relative'])
        # Reconcile only an exact previously journaled move. Unknown targets are never adopted.
        if final.exists():
            if archive.exists():
                raise OperationError('Destination collision; private and published copies both exist')
            _verify_archive(final, workspace.name, candidate, state['archive_files'])
        else:
            if state['state'] == 'COMPLETE':
                raise OperationError('Completed archive is missing; refusing automatic republication')
            _verify_archive(archive, workspace.name, candidate, state['archive_files'])
            _current(store, case_id, plan['candidate_id'])
            if engine_identity() != plan['engine_id']:
                raise OperationError('Evaluator changed before publication')
            for path, hashed in report['dimensions']['live']['artifacts'].items():
                if file_digest(Path(path)) != hashed:
                    raise OperationError('Live artifacts changed before publication')
            destination.mkdir(parents=True, exist_ok=True)
            # Move one newly built directory; previous archives are never renamed/deleted.
            os.rename(archive, final)
            _verify_archive(final, workspace.name, candidate, state['archive_files'])
        _current(store, case_id, plan['candidate_id'])
        state.update(state='COMPLETE')
        _write(root / 'checkpoint.json', state)
        return {'operation_id': operation_id, 'state': 'COMPLETE', 'archive': str(final), 'qualification': report}


def prepare_case_run(store: CaseStore, case_id: str, operation_id: str, *, rig: Path, run_id: str,
                     run_compile: bool = False) -> dict:
    """Bind an already staged isolated rig; do not launch or overwrite staged mods/configs."""
    from .case_qualification import _binding, _run_context
    from .live.live_run import LIVE_EXPECTED_MILESTONES
    from .run_manifest import read_staging_state
    from .run_manifest import (_enabled_ids, _staged_entries, check_run_id, prepare_run, read_manifest,
                               OWNER_FILE, manifest_path, refuse_if_owned, rig_owner, runtime_hashes,
                               _launcher_files, _resolve_java_executable)
    from .scan.scanner import _load_lenient_json_file
    require_digest(operation_id)
    store.load_case(case_id)
    check_run_id(run_id)
    root = _physical(store.root / case_id / 'operations' / operation_id)
    rig = _physical(Path(rig).expanduser())
    with store._write_lock():
        plan = _read(root / 'plan.json')
        if digest(plan) != operation_id or plan['case_id'] != case_id:
            raise OperationError('Operation identity mismatch')
        candidate = store.load_candidate(case_id, plan['candidate_id'])
        body = candidate['content']
        state = _read(root / 'checkpoint.json')
        _prepared(root, state, candidate)
        if state['state'] != 'PREPARED' or engine_identity() != plan['engine_id']:
            raise OperationError('Run requires a prepared operation with the current evaluator')
        report = qualify_case(store, case_id, plan['candidate_id'], run_compile=run_compile)
        unresolved = {name: value for name, value in report['dimensions'].items()
                      if name != 'live' and value['status'] not in {'PASS', 'NOT_APPLICABLE'}}
        if unresolved:
            return {'state': 'REFUSED', 'operation_id': operation_id, 'unresolved': unresolved}
        working = store.workspace(case_id).working
        info = _load_lenient_json_file(working / 'mod_info.json')
        launcher = _binding(body, 'launcher', 'game', 'file')
        reference = root / 'runs' / (digest({'rig': str(rig), 'run_id': run_id}) + '.json')
        if reference.exists():
            recorded = _read(reference)
            manifest = read_manifest(rig, run_id)
            if recorded.get('manifest_id') != manifest['manifest_id']:
                raise OperationError('Previously bound run manifest changed')
        else:
            owner = rig_owner(rig)
            if (rig / 'logs' / OWNER_FILE).exists() and not owner:
                raise OperationError('Unreadable rig ownership record; refusing preparation')
            if not (manifest_path(rig, run_id).exists() and (owner or {}).get('run_id') == run_id):
                refuse_if_owned(rig, 'case run preparation')
            # Inspect the selected command before runtime_hashes may invoke java -version.
            # A bound launcher must not cause an unrelated executable to be observed.
            jdk = _binding(body, 'tools', 'jdk', 'tree')
            if launcher is None or jdk is None or jdk.is_relative_to(working):
                raise OperationError('Run needs a bound launcher and external runtime JDK')
            _, java = _launcher_files(rig, launcher)
            expected_java = jdk / 'bin' / ('java.exe' if os.name == 'nt' else 'java')
            if _resolve_java_executable(rig, launcher, java) != expected_java:
                raise OperationError('Launcher selects an unbound Java executable')
            staged_candidates = read_staging_state(rig).get('candidates') or {}
            if set(staged_candidates) != {info['id']} or Path(staged_candidates[info['id']]['working']).resolve() != working:
                raise OperationError('Staging state must select only this case candidate for the live harness')
            expected = {'rig_core': str((rig / 'starsector-core').resolve()),
                        'runtime': runtime_hashes(rig, launcher),
                        'enabled': _staged_entries(rig, _enabled_ids(rig)),
                        'targets': {info['id']: {'working': str(working), 'candidate_sha256': body['payload']['sha256']}},
                        'expected_milestones': list(LIVE_EXPECTED_MILESTONES)}
            mismatch = _run_context(body, working, info, expected, rig)
            if mismatch is not None:
                return {'state': 'REFUSED', 'operation_id': operation_id, 'run_context': mismatch}
            _current(store, case_id, plan['candidate_id'])
            manifest = prepare_run(rig, run_id, 'live', targets=[info['id']], expected=list(LIVE_EXPECTED_MILESTONES), scenario='probe-group live',
                                   candidates={info['id']: working}, launcher=launcher)
        mismatch = _run_context(body, working, info, manifest, rig)
        if mismatch is not None:
            raise OperationError('Prepared run context changed: ' + mismatch['reason'])
        _current(store, case_id, plan['candidate_id'])
        record = {'state': 'RUN_PREPARED', 'operation_id': operation_id, 'rig': str(rig), 'run_id': run_id,
                  'candidate_id': plan['candidate_id'], 'manifest_id': manifest['manifest_id']}
        if reference.exists() and _read(reference) != record:
            raise OperationError('Run receipt collision')
        _write(reference, record)
        return record
