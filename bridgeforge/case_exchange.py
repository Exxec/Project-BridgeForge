"""S4 private case metadata exchange. Payload transfer and qualification stay separate."""
from __future__ import annotations

import json
from pathlib import Path
import platform
import sys
import uuid

from .case_identity import canonical, capture_candidate, digest, require_digest, tree_files, validate_record
from .case_qualification import TARGET, LEGACY_TARGET, engine_identity
from .case_store import CaseStore, _unique
from .case_workspace import _physical, open_workspace_view
from .portfolio import output_lease
from .safeio import atomic_write_json

SCHEMA = 'bridgeforge.private-case-exchange'
RESTRICTIONS = {'transport': 'LOCAL_PRIVATE_ONLY', 'publication_authorized': False,
                'payload_included': False, 'historical_receipts': 'NEVER_REBOUND_OR_ACCEPTED'}


def _validate(record: dict) -> dict:
    if (not isinstance(record, dict) or set(record) != {'schema', 'schema_version', 'content', 'sha256'}
            or record['schema'] != SCHEMA or type(record['schema_version']) is not int or record['schema_version'] != 1):
        raise ValueError('Unsupported case exchange schema; use a compatible exporter or migrate explicitly')
    content = record['content']
    if not isinstance(content, dict) or record['sha256'] != digest(content):
        raise ValueError('Case exchange content hash mismatch')
    if set(content) != {'case', 'candidate', 'receipts', 'reports', 'checkpoints', 'restrictions', 'export_engine'}:
        raise ValueError('Unsupported case exchange fields')
    if canonical(content['restrictions']) != canonical(RESTRICTIONS):
        raise ValueError('Exchange cannot broaden privacy, publication or historical acceptance')
    case = validate_record(content['case'], 'case')
    candidate = validate_record(content['candidate'], 'candidate')
    require_digest(content['export_engine'])
    if candidate['case_id'] != case['case_id'] or candidate['target_profile'] != case['target_profile']:
        raise ValueError('Exchange subject/profile mismatch')
    if not isinstance(content['receipts'], list):
        raise ValueError('Expected explicit historical receipt records')
    for receipt in content['receipts']:
        body = validate_record(receipt, 'receipt')
        if body['case_id'] != case['case_id'] or body['candidate_id'] != content['candidate']['record_id']:
            raise ValueError('Historical receipt belongs to another subject')
    return content


def read_exchange(path: Path) -> dict:
    path = _physical(Path(path))
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError('Case exchange exceeds the 64 MiB metadata limit')
    record = json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=_unique)
    _validate(record)
    return record


def _auxiliary(view) -> dict:
    return {name: tree_files(path) if path is not None else None
            for name, path in (('reports', view.reports), ('checkpoints', view.checkpoints))}


def export_private_case(store: CaseStore, case_id: str, candidate_id: str, output: Path) -> dict:
    output = _physical(Path(output))
    view = store.workspace(case_id)
    candidate = store.load_candidate(case_id, candidate_id)
    protected = [view.root, store.root]
    protected.extend(Path(item['path']) for group in candidate['content']['context']['inputs'].values()
                     for item in (group or {}).values())
    if output.exists() or any(output.is_relative_to(root) or root.is_relative_to(output) for root in protected):
        raise ValueError('Export requires a new metadata file outside workspace/store/selected inputs')
    with output_lease(output.parent), store._write_lock():
        if output.exists():
            raise ValueError('Export never overwrites an existing metadata file')
        if store.assess_candidate(case_id, candidate_id)['state'] != 'CURRENT':
            raise ValueError('Export requires current candidate inputs')
        auxiliary = _auxiliary(view)
        receipts = []
        folder = store.root / case_id / 'receipts'
        for path in sorted(folder.glob('*.json')) if folder.exists() else []:
            record = store.load_receipt(case_id, path.stem)
            if record['content']['candidate_id'] == candidate_id:
                receipts.append(record)
        content = {'case': store.load_case(case_id), 'candidate': candidate, 'receipts': receipts,
                   **auxiliary, 'restrictions': dict(RESTRICTIONS), 'export_engine': engine_identity()}
        record = {'schema': SCHEMA, 'schema_version': 1, 'content': content, 'sha256': digest(content)}
        _validate(record)
        if store.assess_candidate(case_id, candidate_id)['state'] != 'CURRENT' or auxiliary != _auxiliary(view):
            raise ValueError('Case changed during export; retry after its writers stop')
        atomic_write_json(output, record)
    return {'state': 'EXPORTED_PRIVATE_METADATA', 'path': str(output), 'sha256': record['sha256'],
            'payload': 'NOT_INCLUDED', 'publication': 'NOT_AUTHORIZED', 'qualification': 'NOT_EVALUATED'}


def exchange_summary(record: dict) -> dict:
    """Path-free, payload-free summary for local review; still no publication grant."""
    content = _validate(record)
    body = content['candidate']['content']
    return {'schema_version': 1, 'exchange_sha256': record['sha256'], 'source_case_id': body['case_id'],
            'source_candidate_id': content['candidate']['record_id'],
            'target_profile': body['target_profile'] if body['target_profile'] in (TARGET, LEGACY_TARGET)
                              else {'unsupported_profile_sha256': digest(body['target_profile'])},
            'payload_file_count': len(body['payload']['files']), 'payload_sha256': body['payload']['sha256'],
            'historical_receipts': len(content['receipts']), 'publication_authorized': False,
            'private_paths_and_payload': 'OMITTED', 'qualification': 'NOT_EVALUATED'}


def import_private_case(record: dict, store: CaseStore, workspace: Path, inputs: dict, *,
                        allow_context_change: bool = False) -> dict:
    """Bind a restored workspace to a NEW unqualified case; never relocate old acceptance.

    Existing snapshot/restore machinery transports private files. This function copies
    no game/mod/save payload and never follows historical source or artifact paths.
    """
    content = _validate(record)
    old = content['candidate']['content']
    source_case = content['case']['content']
    if old['target_profile'] != TARGET or source_case['declared_scope'] != 'local-new-game':
        raise ValueError('Unsupported imported profile/scope; migrate explicitly with a compatible evaluator')
    view = open_workspace_view(Path(workspace), original_relative=source_case['workspace']['original_relative'])
    if view.root == Path(source_case['workspace']['root']):
        raise ValueError('Import must use an isolated restored workspace, never the source workspace')
    if view.layout != source_case['workspace']['layout']:
        raise ValueError('Restored workspace layout differs; an explicit layout migration is required')
    if _auxiliary(view) != {name: content[name] for name in ('reports', 'checkpoints')}:
        raise ValueError('Restored reports/checkpoints are incomplete or changed; preserve decisions before rebinding')
    identity = uuid.uuid5(uuid.NAMESPACE_URL, record['sha256'] + ':' + str(view.root) + ':' + str(store.root)).hex
    if identity == old['case_id']:
        raise ValueError('Imported identity must differ from historical source')
    preview = capture_candidate(view, case_id=identity, target_profile=TARGET, inputs=inputs)
    current = preview['content']
    if current['original'] != old['original'] or current['payload'] != old['payload']:
        raise ValueError('Restored original/working bytes differ; import never changes payload or credits')
    changes = []
    for role, group in old['context']['inputs'].items():
        observed = current['context']['inputs'][role]
        expected = None if group is None else {name: {k: v for k, v in item.items() if k != 'path'} for name, item in group.items()}
        actual = None if observed is None else {name: {k: v for k, v in item.items() if k != 'path'} for name, item in observed.items()}
        if actual != expected:
            if role in {'policy', 'source_authority'}:
                raise ValueError('Import may not change policy/review authority bytes; retain them as historical decisions')
            changes.append(role)
    if changes and not allow_context_change:
        raise ValueError('Changed external context requires explicit allow_context_change and fresh qualification: ' + ', '.join(changes))
    # Preserve historical records as metadata only, outside active candidate/receipt namespaces.
    with store._write_lock():
        history = _physical(store.root / 'exchange-history' / (record['sha256'] + '.json'))
        if history.exists():
            if read_exchange(history) != record:
                raise ValueError('Historical exchange identity collision')
        else:
            atomic_write_json(history, record)
    store.create_case(view, target_profile=TARGET, declared_scope='local-new-game', case_id=identity)
    candidate = store.add_candidate(identity, inputs=inputs)
    if candidate['record_id'] != preview['record_id']:
        raise ValueError('Restored input changed while rebinding; no qualification was performed')
    result = {'state': 'IMPORTED_UNQUALIFIED', 'case_id': identity, 'candidate_id': candidate['record_id'],
              'source_case_id': old['case_id'], 'source_candidate_id': content['candidate']['record_id'],
              'exchange_sha256': record['sha256'], 'context_changes': changes,
              'historical_receipts': 'PRESERVED_ONLY_NOT_IMPORTED_AS_CURRENT',
              'publication': 'NOT_AUTHORIZED', 'transport': 'LOCAL_PRIVATE_ONLY', 'qualification': 'NOT_EVALUATED',
              'runtime': {'python': sys.version, 'platform': platform.platform()},
              'next': 'Fresh review, qualification and exact-context live evidence; import grants no acceptance'}
    with store._write_lock():
        link = _physical(store.root / identity / 'exchange-lineage' / (candidate['record_id'] + '.json'))
        if not link.exists():
            atomic_write_json(link, result)
    return result
