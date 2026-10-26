"""S1 content-bound candidate and observation records; integrity is not approval."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from .case_workspace import WorkspaceView, _components, _physical
from .copy_drift import _collect
from .run_manifest import FILESET_ALGORITHM
from .scan.scan_registry import EXCLUSION_VERSION, _excluded
from .workspace import sha256_file

CONTEXT_ROLES = ('core', 'dependencies', 'tools', 'rules', 'policy', 'launcher', 'source_authority')
OUTCOMES = ('PASS', 'FAIL', 'INCOMPLETE', 'NOT_APPLICABLE')
_HEX = re.compile(r'[0-9a-f]{64}')


def canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (ValueError, TypeError) as exc:
        raise ValueError('Record must be finite canonical JSON data') from exc


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def require_digest(value: object) -> str:
    if not isinstance(value, str) or not _HEX.fullmatch(value):
        raise ValueError('Expected a lowercase SHA-256 identity')
    return value


def seal(kind: str, content: dict) -> dict:
    return {'schema': 'bridgeforge.' + kind, 'schema_version': 1,
            'record_id': digest(content), 'content': json.loads(canonical(content))}


def validate_record(record: object, kind: str) -> dict:
    if not isinstance(record, dict) or set(record) != {'schema', 'schema_version', 'record_id', 'content'}:
        raise ValueError('Missing/unsupported record envelope')
    if record['schema'] != 'bridgeforge.' + kind or type(record['schema_version']) is not int or record['schema_version'] != 1:
        raise ValueError('Unsupported record schema/version')
    if not isinstance(record['content'], dict) or require_digest(record['record_id']) != digest(record['content']):
        raise ValueError('Record content identity mismatch')
    _validate_content(record['content'], kind)
    return record['content']


def file_digest(path: Path) -> str:
    path = _physical(Path(path))
    before = path.stat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError(f'Not a regular evidence/input file: {path}')
    value = sha256_file(path)
    after = path.stat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise ValueError(f'Input changed while hashing: {path}')
    _physical(path)
    return value


def tree_files(root: Path, *, analysis: bool = False) -> dict[str, str]:
    """Refuse links/special files before the legacy collector can traverse them."""
    root = _physical(Path(root))
    if not root.is_dir():
        raise ValueError(f'Input tree is missing: {root}')
    files = {}
    folded = set()
    def walk_error(exc):
        raise ValueError(f'Cannot enumerate input tree: {exc}') from exc
    for current, dirs, names in os.walk(root, followlinks=False, onerror=walk_error):
        for name in sorted(dirs + names):
            path = Path(current) / name
            relative = path.relative_to(root).as_posix()
            _components(relative, 'input path')
            _physical(path)
            if relative.casefold() in folded:
                raise ValueError(f'Case-colliding input paths: {relative}')
            folded.add(relative.casefold())
            if path.is_dir():
                continue
            if not stat.S_ISREG(path.stat().st_mode):
                raise ValueError(f'Non-regular input path: {path}')
            if not analysis or not _excluded(relative):
                files[relative] = file_digest(path)
    return dict(sorted(files.items()))


def tree_digest(files: dict[str, str]) -> str:
    value = hashlib.sha256()
    for relative, hashed in sorted(files.items()):
        value.update(f'{relative}\0{hashed}\n'.encode('utf-8'))
    return value.hexdigest()


def _working(view: WorkspaceView) -> dict:
    all_files = tree_files(view.working)
    selected = _collect(view.working)
    for name, path in selected.items():
        _components(name, 'shipped path')
        if name not in all_files or _physical(path) != view.working.joinpath(*name.split('/')):
            raise ValueError(f'Shipped selection escapes physical inventory: {name}')
    shipped = {name: all_files[name] for name in sorted(selected)}
    analysis_files = {name: value for name, value in all_files.items() if not _excluded(name)}
    return {'algorithm': FILESET_ALGORITHM, 'files': shipped, 'sha256': tree_digest(shipped),
            'analysis': {'algorithm': f'scan-registry-exclusions/{EXCLUSION_VERSION}', 'sha256': tree_digest(analysis_files)}}


def _context(inputs: dict[str, dict[str, Path] | None]) -> dict:
    if not isinstance(inputs, dict) or set(inputs) - set(CONTEXT_ROLES):
        raise ValueError('Unknown context role')
    groups, missing = {}, []
    for role in CONTEXT_ROLES:
        group = inputs.get(role)
        if group is None:
            groups[role] = None
            missing.append(role)
            continue
        if not isinstance(group, dict):
            raise ValueError(f'{role}: expected named inputs or None')
        groups[role] = {}
        for name, source in sorted(group.items()):
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f'{role}: input name required')
            path = _physical(Path(source))
            if path.is_dir():
                files = tree_files(path)
                item = {'kind': 'tree', 'algorithm': 'all-regular/1', 'sha256': tree_digest(files), 'file_count': len(files)}
            else:
                item = {'kind': 'file', 'sha256': file_digest(path)}
            item['path'] = str(path)
            groups[role][name] = item
    return {'inputs': groups, 'missing_roles': missing, 'provenance': 'BYTE_BOUND_NOT_QUALIFIED'}


def capture_candidate(view: WorkspaceView, *, case_id: str, target_profile: dict,
                      inputs: dict[str, dict[str, Path] | None], predecessor: str | None = None) -> dict:
    if not isinstance(case_id, str) or not re.fullmatch(r'[0-9a-f]{32}', case_id):
        raise ValueError('Invalid case identity')
    if not isinstance(target_profile, dict) or not target_profile:
        raise ValueError('Explicit target profile required')
    if predecessor is not None:
        require_digest(predecessor)
    def capture():
        original = tree_files(view.original)
        return {'case_id': case_id, 'target_profile': target_profile, 'predecessor': predecessor,
                'original': {'algorithm': 'all-regular/1', 'sha256': tree_digest(original), 'file_count': len(original)},
                'payload': _working(view), 'context': _context(inputs)}
    target_profile = json.loads(canonical(target_profile))
    first = capture()
    if canonical(first) != canonical(capture()):
        raise ValueError('Inputs changed during candidate capture; retry with stable inputs')
    record = seal('candidate', first)
    validate_record(record, 'candidate')
    return record


def candidate_state(record: dict, view: WorkspaceView, inputs: dict) -> dict:
    content = validate_record(record, 'candidate')
    current = capture_candidate(view, case_id=content['case_id'], target_profile=content['target_profile'],
                                inputs=inputs, predecessor=content['predecessor'])
    return {'state': 'CURRENT' if current['record_id'] == record['record_id'] else 'STALE',
            'candidate_id': record['record_id'], 'current_id': current['record_id'],
            'missing_context': current['content']['context']['missing_roles']}


def make_receipt(candidate: dict, *, kind: str, outcome: str, reason: str, tool: dict,
                 run_id: str, observed_at: str, evidence: list[Path]) -> dict:
    subject = validate_record(candidate, 'candidate')
    if outcome not in OUTCOMES or not all(isinstance(value, str) and value.strip() for value in (kind, reason, run_id)):
        raise ValueError('Receipt requires a known outcome, kind, reason and run ID')
    if not isinstance(tool, dict) or not tool.get('name') or not tool.get('version'):
        raise ValueError('Receipt requires explicit tool identity')
    require_digest(tool.get('sha256'))
    _stamp(observed_at)
    artifacts = {}
    for path in evidence:
        physical = _physical(Path(path))
        key = str(physical)
        if key in artifacts:
            raise ValueError('Duplicate evidence artifact')
        artifacts[key] = file_digest(physical)
    if outcome == 'PASS' and not artifacts:
        raise ValueError('PASS requires evidence artifacts')
    record = seal('receipt', {'case_id': subject['case_id'], 'candidate_id': candidate['record_id'],
                           'context_id': digest(subject['context']), 'kind': kind, 'outcome': outcome,
                           'reason': reason, 'tool': tool, 'run_id': run_id, 'observed_at': observed_at,
                           'evidence': artifacts, 'provenance': 'RECORDED_NOT_VERIFIED'})
    validate_record(record, 'receipt')
    return record


def receipt_state(record: dict, candidate: dict) -> dict:
    if not isinstance(record, dict) or 'schema' not in record:
        return {'state': 'UNKNOWN', 'reason': 'Legacy receipt has no bound identity'}
    receipt = validate_record(record, 'receipt')
    subject = validate_record(candidate, 'candidate')
    if (receipt.get('case_id') != subject['case_id'] or receipt.get('candidate_id') != candidate['record_id']
            or receipt.get('context_id') != digest(subject['context'])):
        return {'state': 'STALE', 'reason': 'Receipt subject/context mismatch'}
    try:
        if any(file_digest(Path(path)) != hashed for path, hashed in receipt['evidence'].items()):
            return {'state': 'STALE', 'reason': 'Evidence bytes changed'}
    except (OSError, ValueError):
        return {'state': 'INCOMPLETE', 'reason': 'Evidence unavailable or unsafe'}
    return {'state': 'CURRENT', 'outcome': receipt['outcome'], 'provenance': 'RECORDED_NOT_VERIFIED'}


def _text(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(field + ': nonempty text required')


def _stamp(value: object) -> None:
    if not isinstance(value, str):
        raise ValueError('Timezone-aware timestamp required')
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError('Timezone-aware timestamp required')


def _keys(value: object, fields: set[str]) -> None:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError('Unsupported record content fields')


def _validate_content(content: dict, kind: str) -> None:
    case_id = content.get('case_id')
    if not isinstance(case_id, str) or not re.fullmatch(r'[0-9a-f]{32}', case_id):
        raise ValueError('Invalid case identity')
    if kind == 'case':
        _keys(content, {'case_id', 'workspace', 'target_profile', 'declared_scope', 'authority', 'created_at'})
        _keys(content['workspace'], {'root', 'layout', 'original_relative'})
        if content['workspace']['layout'] not in {'manifest-v1', 'convention-v1'}:
            raise ValueError('Unsupported workspace layout')
        if not isinstance(content['workspace']['root'], str) or not Path(content['workspace']['root']).is_absolute():
            raise ValueError('Absolute workspace reference required')
        if content['workspace']['original_relative'] != '.':
            _components(content['workspace']['original_relative'], 'original_relative')
        if not isinstance(content['target_profile'], dict) or not content['target_profile']:
            raise ValueError('Explicit target profile required')
        _text(content['declared_scope'], 'declared_scope')
        if content['authority'] != 'DECLARED_NOT_APPROVED':
            raise ValueError('Case metadata cannot confer approval')
        _stamp(content['created_at'])
    elif kind == 'candidate':
        _keys(content, {'case_id', 'target_profile', 'predecessor', 'original', 'payload', 'context'})
        if not isinstance(content['target_profile'], dict) or not content['target_profile']:
            raise ValueError('Explicit target profile required')
        if content['predecessor'] is not None:
            require_digest(content['predecessor'])
        _keys(content['original'], {'algorithm', 'sha256', 'file_count'})
        if content['original']['algorithm'] != 'all-regular/1' or type(content['original']['file_count']) is not int or content['original']['file_count'] < 1:
            raise ValueError('Unsupported original identity')
        require_digest(content['original']['sha256'])
        payload = content['payload']
        _keys(payload, {'algorithm', 'files', 'sha256', 'analysis'})
        if payload['algorithm'] != FILESET_ALGORITHM or not isinstance(payload['files'], dict) or 'mod_info.json' not in payload['files']:
            raise ValueError('Unsupported payload file set')
        for name, value in payload['files'].items():
            _components(name, 'shipped path')
            require_digest(value)
        if payload['sha256'] != tree_digest(payload['files']):
            raise ValueError('Payload digest mismatch')
        _keys(payload['analysis'], {'algorithm', 'sha256'})
        if payload['analysis']['algorithm'] != f'scan-registry-exclusions/{EXCLUSION_VERSION}':
            raise ValueError('Unsupported analysis identity')
        require_digest(payload['analysis']['sha256'])
        context = content['context']
        _keys(context, {'inputs', 'missing_roles', 'provenance'})
        _keys(context['inputs'], set(CONTEXT_ROLES))
        if context['missing_roles'] != [role for role in CONTEXT_ROLES if context['inputs'][role] is None] or context['provenance'] != 'BYTE_BOUND_NOT_QUALIFIED':
            raise ValueError('Unsupported context provenance/completeness')
        for group in context['inputs'].values():
            if group is None:
                continue
            if not isinstance(group, dict):
                raise ValueError('Invalid context input group')
            for name, item in group.items():
                _text(name, 'context input name')
                if not isinstance(item, dict) or item.get('kind') not in {'file', 'tree'}:
                    raise ValueError('Invalid context input identity')
                _keys(item, {'kind', 'sha256', 'path'} if item['kind'] == 'file' else {'kind', 'sha256', 'path', 'algorithm', 'file_count'})
                require_digest(item['sha256'])
                if not isinstance(item['path'], str) or not Path(item['path']).is_absolute():
                    raise ValueError('Absolute context input reference required')
                if item['kind'] == 'tree' and (item['algorithm'] != 'all-regular/1' or type(item['file_count']) is not int or item['file_count'] < 0):
                    raise ValueError('Invalid context tree identity')
    elif kind == 'receipt':
        _keys(content, {'case_id', 'candidate_id', 'context_id', 'kind', 'outcome', 'reason', 'tool', 'run_id', 'observed_at', 'evidence', 'provenance'})
        require_digest(content['candidate_id']); require_digest(content['context_id'])
        for field in ('kind', 'reason', 'run_id'):
            _text(content[field], field)
        if content['outcome'] not in OUTCOMES or content['provenance'] != 'RECORDED_NOT_VERIFIED':
            raise ValueError('Unsupported receipt outcome/provenance')
        _keys(content['tool'], {'name', 'version', 'sha256'})
        _text(content['tool']['name'], 'tool name'); _text(content['tool']['version'], 'tool version')
        require_digest(content['tool']['sha256']); _stamp(content['observed_at'])
        if not isinstance(content['evidence'], dict) or (content['outcome'] == 'PASS' and not content['evidence']):
            raise ValueError('Invalid receipt evidence')
        for path, value in content['evidence'].items():
            if not isinstance(path, str) or not Path(path).is_absolute():
                raise ValueError('Absolute evidence reference required')
            require_digest(value)
    else:
        raise ValueError('Unsupported record kind')
