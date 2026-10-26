"""S1 immutable case/candidate/receipt storage outside frozen workspace inputs."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import uuid

from .case_identity import candidate_state, capture_candidate, receipt_state, require_digest, seal, validate_record
from .case_workspace import WorkspaceView, _physical, open_workspace_view
from .safeio import atomic_write_json, safe_unlink


def _case_id(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{32}', value):
        raise ValueError('Invalid case identity')
    return value


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate record field: ' + key)
        result[key] = value
    return result


class CaseStore:
    """Local append-only records. Declared scope is not approval; hashes are not signatures.

    Writes are serialized; an abandoned lock refuses writes until explicit recovery.
    Records are atomic, content-addressed and never replaced with different bytes.
    """
    def __init__(self, root: Path):
        self.root = _physical(Path(root).expanduser())
        if self.root.exists() and not self.root.is_dir():
            raise ValueError('Case store must be a directory')

    @contextmanager
    def _write_lock(self):
        _physical(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        lock = self.root / '.write-lock'
        token = uuid.uuid4().hex
        try:
            descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise ValueError('Case store is locked; no automatic stale-lock takeover') from exc
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
                handle.write(token)
                handle.flush()
                os.fsync(handle.fileno())
            yield
        finally:
            _physical(lock)
            if lock.read_text(encoding='utf-8') != token:
                raise ValueError('Case store lock ownership changed; refusing cleanup')
            safe_unlink(lock, [self.root], missing_ok=False)

    def _outside(self, view: WorkspaceView) -> None:
        if self.root.is_relative_to(view.root):
            raise ValueError('Case store must be outside the workspace and frozen inputs')

    def _read(self, path: Path, kind: str) -> dict:
        _physical(path)
        try:
            record = json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=_unique)
        except (OSError, ValueError) as exc:
            raise ValueError(f'Missing, interrupted or malformed {kind} record: {path}') from exc
        validate_record(record, kind)
        return record

    def _publish(self, path: Path, record: dict, kind: str) -> dict:
        validate_record(record, kind)
        _physical(path)
        if path.exists():
            existing = self._read(path, kind)
            if existing != record:
                raise ValueError('Immutable record collision; refusing overwrite')
            return existing
        path.parent.mkdir(parents=True, exist_ok=True)
        _physical(path.parent)
        atomic_write_json(path, record)
        return self._read(path, kind)

    def create_case(self, view: WorkspaceView, *, target_profile: dict, declared_scope: str,
                    case_id: str | None = None) -> dict:
        self._outside(view)
        identity = _case_id(case_id) if case_id is not None else uuid.uuid4().hex
        core = {'case_id': identity, 'workspace': {'root': str(view.root), 'layout': view.layout,
                'original_relative': view.original.relative_to(view.original_container).as_posix()},
                'target_profile': target_profile, 'declared_scope': declared_scope, 'authority': 'DECLARED_NOT_APPROVED'}
        record = seal('case', {**core, 'created_at': datetime.now(timezone.utc).isoformat()})
        validate_record(record, 'case')
        path = self.root / 'cases' / f'{identity}.json'
        with self._write_lock():
            if path.exists():
                existing = self.load_case(identity)
                if {key: value for key, value in existing['content'].items() if key != 'created_at'} != core:
                    raise ValueError('Case identity already binds a different workspace/scope/profile')
                return existing
            return self._publish(path, record, 'case')

    def load_case(self, case_id: str) -> dict:
        identity = _case_id(case_id)
        record = self._read(self.root / 'cases' / f'{identity}.json', 'case')
        if record['content']['case_id'] != identity:
            raise ValueError('Case identity/path mismatch')
        return record

    def workspace(self, case_id: str) -> WorkspaceView:
        reference = self.load_case(case_id)['content']['workspace']
        view = open_workspace_view(Path(reference['root']), original_relative=reference['original_relative'])
        if view.layout != reference['layout']:
            raise ValueError('Workspace layout changed; explicit rebinding required')
        self._outside(view)
        return view

    def add_candidate(self, case_id: str, *, inputs: dict, predecessor: str | None = None) -> dict:
        identity = _case_id(case_id)
        view = self.workspace(identity)
        if not isinstance(inputs, dict):
            raise ValueError('Context inputs must be a mapping')
        for group in inputs.values():
            if group is None:
                continue
            if not isinstance(group, dict):
                raise ValueError('Context input group must be a mapping or None')
            for path in group.values():
                path = _physical(Path(path))
                if path.is_dir() and (self.root.is_relative_to(path) or path.is_relative_to(self.root)):
                    raise ValueError('Case state and context inputs overlap')
        with self._write_lock():
            if predecessor is not None:
                self.load_candidate(identity, predecessor)
            record = capture_candidate(view, case_id=identity, target_profile=self.load_case(identity)['content']['target_profile'],
                                       inputs=inputs, predecessor=predecessor)
            return self._publish(self.root / identity / 'candidates' / (record['record_id'] + '.json'), record, 'candidate')

    def load_candidate(self, case_id: str, candidate_id: str) -> dict:
        identity, key = _case_id(case_id), require_digest(candidate_id)
        record = self._read(self.root / identity / 'candidates' / f'{key}.json', 'candidate')
        if record['content']['case_id'] != identity or record['record_id'] != key:
            raise ValueError('Candidate subject/path mismatch')
        return record

    def add_receipt(self, case_id: str, record: dict) -> dict:
        identity = _case_id(case_id)
        content = validate_record(record, 'receipt')
        self.workspace(identity)
        if content['case_id'] != identity:
            raise ValueError('Receipt belongs to another case')
        with self._write_lock():
            candidate = self.load_candidate(identity, content['candidate_id'])
            if receipt_state(record, candidate)['state'] != 'CURRENT':
                raise ValueError('Receipt evidence or subject is not current')
            return self._publish(self.root / identity / 'receipts' / (record['record_id'] + '.json'), record, 'receipt')

    def load_receipt(self, case_id: str, receipt_id: str) -> dict:
        identity, key = _case_id(case_id), require_digest(receipt_id)
        record = self._read(self.root / identity / 'receipts' / f'{key}.json', 'receipt')
        if record['content']['case_id'] != identity or record['record_id'] != key:
            raise ValueError('Receipt subject/path mismatch')
        return record


    def assess_candidate(self, case_id: str, candidate_id: str) -> dict:
        record = self.load_candidate(case_id, candidate_id)
        groups = record['content']['context']['inputs']
        inputs = {role: None if group is None else {name: Path(item['path']) for name, item in group.items()}
                  for role, group in groups.items()}
        return candidate_state(record, self.workspace(case_id), inputs)
