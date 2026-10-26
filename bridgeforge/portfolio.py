"""Bounded read-only S1 candidate analysis; completed analysis is never qualification."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
import uuid

import psutil

from .case_identity import (digest, file_digest, make_receipt, receipt_state, tree_digest,
                            tree_files, validate_record, _working)
from .case_qualification import TARGET, _binding, _dependencies, engine_identity
from .case_store import CaseStore, _unique
from .case_workspace import _physical
from .portfolio_process import AnalysisProcess
from .progress import Checkpoint, report
from .safeio import atomic_write_json
from .scan.scan_json import _load_lenient_json_file


@contextmanager
def output_lease(root: Path):
    """Kernel file lock releases on coordinator death; never take over a live owner."""
    root = _physical(root)
    root.mkdir(parents=True, exist_ok=True)
    path = _physical(root / '.portfolio-lock')
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(fd, 'r+b') as stream:
        if not path.stat().st_size:
            stream.write(b'0'); stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ValueError('Portfolio output already has an active coordinator') from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _read(path: Path) -> dict:
    _physical(path)
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError('Analysis artifact exceeds 64 MiB limit')
    value = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=_unique)
    if not isinstance(value, dict):
        raise ValueError('Expected an analysis record object')
    return value


def _subjects(store: CaseStore, selections: list[dict], output: Path) -> list[dict]:
    if not isinstance(selections, list) or not selections:
        raise ValueError('Nonempty explicit candidate selection required')
    rows, roots = [], []
    for selected in selections:
        if not isinstance(selected, dict) or set(selected) != {'case_id', 'candidate_id'}:
            raise ValueError('Each selection must contain case_id and candidate_id only')
        candidate = store.load_candidate(**selected)
        body = candidate['content']
        view = store.workspace(selected['case_id'])
        if body['target_profile'] != TARGET:
            raise ValueError('Portfolio supports only the declared RC8 local-new-game target')
        if any(view.working == old or view.working.is_relative_to(old) or old.is_relative_to(view.working) for old in roots):
            raise ValueError('Duplicate/overlapping workspace aliases in portfolio')
        roots.append(view.working)
        protected = [view.root, store.root]
        for group in body['context']['inputs'].values():
            protected.extend(Path(item['path']) for item in (group or {}).values())
        if any(output.is_relative_to(path) or path.is_relative_to(output) for path in protected):
            raise ValueError('Portfolio output must be separate from workspace, store and selected inputs')
        core = _binding(body, 'core', 'starsector', 'tree')
        python = _binding(body, 'tools', 'python', 'file')
        jdk = _binding(body, 'tools', 'jdk', 'tree')
        if core is None or python != Path(sys.executable).resolve():
            raise ValueError('Analysis requires bound core and current Python without fallback')
        needs_java = bool(list(view.working.rglob('*.java')) or list(view.working.rglob('*.jar')))
        if needs_java and jdk is None:
            raise ValueError('Java analysis requires an explicit bound JDK')
        if body['context']['inputs']['dependencies'] is None:
            raise ValueError('Provider selection is unknown; explicit empty or named selection required')
        providers = [item['path'] for item in body['context']['inputs']['dependencies'].values()]
        if any(item['kind'] != 'tree' for item in body['context']['inputs']['dependencies'].values()):
            raise ValueError('Providers must be explicit physical mod directories')
        info = _load_lenient_json_file(view.working / 'mod_info.json')
        if not isinstance(info, dict):
            raise ValueError('Mod metadata is unavailable')
        resolution, _ = _dependencies(body, info)
        rows.append({**selected, 'candidate': candidate, 'view': view, 'needs_java': needs_java,
                     'dependency_resolution': resolution,
                     'request': {'working': str(view.working), 'core': str(core), 'providers': providers,
                                 'compile': False, 'jdk': str(jdk) if jdk else None}})
    return sorted(rows, key=lambda item: item['case_id'])


def _fresh(rows: list[dict]) -> dict[str, str]:
    """One fresh content-hash epoch; shared immutable inputs hashed once per pass."""
    memo, errors = {}, {}
    for row in rows:
        body, view = row['candidate']['content'], row['view']
        try:
            if _working(view) != body['payload']:
                raise ValueError('Working input changed')
            files = tree_files(view.original)
            if tree_digest(files) != body['original']['sha256'] or len(files) != body['original']['file_count']:
                raise ValueError('Original input changed')
            for group in body['context']['inputs'].values():
                for item in (group or {}).values():
                    path = _physical(Path(item['path']))
                    key = (str(path), item['kind'])
                    if key not in memo:
                        if item['kind'] == 'tree':
                            files = tree_files(path)
                            memo[key] = (tree_digest(files), len(files))
                        else:
                            memo[key] = (file_digest(path), None)
                    hashed, count = memo[key]
                    if hashed != item['sha256'] or (count is not None and count != item['file_count']):
                        raise ValueError('Selected context changed: ' + str(path))
        except (OSError, ValueError) as exc:
            errors[row['case_id']] = str(exc)
    return errors


def _response(path):
    value = _read(path)
    if (type(value.get('schema_version')) is not int or value['schema_version'] != 1
            or value.get('compile') is not None or not isinstance(value.get('findings'), list)
            or not isinstance(value.get('metadata'), dict)):
        raise ValueError('Invalid read-only analysis response')
    return value


def scan_portfolio(store: CaseStore, selections: list[dict], output: Path, *, memory_mib: int,
                   jobs: int = 1, timeout: float = 900, reuse_parses: bool = False,
                   quiet: bool = False, cancelled=None) -> dict:
    """Analyze exact candidates, resume verified receipts, preserve incomplete attempts.

    The memory budget is a sampled worker-family stop threshold, excluding coordinator
    memory, not a hard OS limit. One or two workers; no repair, compile, live or archive.
    """
    if type(jobs) is not int or jobs not in (1, 2) or type(memory_mib) is not int or memory_mib <= 0:
        raise ValueError('Use jobs=1 or 2 and an explicit positive memory_mib budget')
    if type(timeout) not in (int, float) or not 0 < timeout <= 86400:
        raise ValueError('Worker timeout must be positive and at most 86400 seconds')
    output = _physical(Path(output))
    if os.name == 'nt' and len(str(output)) + 43 > 240:
        raise ValueError('Windows analysis output path is too long; choose a shorter output directory')
    rows = _subjects(store, selections, output)
    engine, began = engine_identity(), time.perf_counter()
    with output_lease(output):
        errors = _fresh(rows)
        if errors:
            raise ValueError('Stale portfolio candidates: ' + json.dumps(errors, sort_keys=True))
        preflight_seconds = time.perf_counter() - began
        config = {'jobs': jobs, 'memory_mib': memory_mib, 'timeout': timeout, 'reuse_parses': reuse_parses}
        active, completed, pending = {}, {}, []
        peak = maximum = 0
        stop_reason = None
        invocation = uuid.uuid4().hex
        checkpoint = Checkpoint(output / 'portfolio.partial.jsonl', {'schema_version': 1, 'store': str(store.root)})
        try:
            for row in rows:
                row['key'] = digest({'case_id': row['case_id'], 'candidate_id': row['candidate_id'], 'engine': engine})
                # Compact storage names are not identities: full input keys and receipt
                # subjects are verified inside every record, including prefix collisions.
                bucket = _physical(output / 'attempts' / row['key'][:16])
                reused = None
                for path in sorted(bucket.glob('*/receipt.json')) if bucket.exists() else []:
                    try:
                        if (path.parent / 'invalidated.json').exists():
                            continue
                        record = _read(path)
                        content = validate_record(record, 'receipt')
                        if (content['kind'] != 'portfolio-analysis' or content['outcome'] != 'PASS'
                                or content['tool'] != {'name': 'bridgeforge.portfolio', 'version': '1', 'sha256': engine}
                                or receipt_state(record, row['candidate'])['state'] != 'CURRENT'
                                or set(content['evidence']) != {str(path.parent / 'response.json'), str(path.parent / 'metrics.json')}):
                            continue
                        _response(path.parent / 'response.json')
                        reused = {'state': 'REUSED', 'receipt_id': record['record_id'], 'raw': str(path.parent / 'response.json'),
                                  'artifact_sha256': content['evidence']}
                        break
                    except (OSError, ValueError, KeyError, TypeError):
                        continue  # Preserve corrupt/incomplete attempts and recompute safely.
                if reused:
                    completed[row['case_id']] = {**row_selection(row), **reused}
                    if not quiet: report(len(completed), len(rows), row['case_id'], 'verified prior analysis; not qualification', None)
                else:
                    recovered = None
                    for path in sorted(bucket.glob('*/completion.json')) if bucket.exists() else []:
                        try:
                            if (path.parent / 'invalidated.json').exists():
                                continue
                            record = _read(path)
                            body = record['content']
                            artifacts = {str(path.parent / name) for name in ('response.json', 'metrics.json')}
                            if (set(record) != {'content', 'sha256'} or set(body) != {'key', 'artifacts', 'observed_at'}
                                    or record['sha256'] != digest(body)
                                    or body['key'] != row['key'] or set(body['artifacts']) != artifacts
                                    or any(file_digest(Path(p)) != h for p, h in body['artifacts'].items())):
                                continue
                            _response(path.parent / 'response.json')
                            recovered = {**row_selection(row), 'state': 'RECOVERING', 'attempt': str(path.parent),
                                         'raw': str(path.parent / 'response.json'), 'artifact_sha256': body['artifacts'],
                                         'observed_at': body['observed_at']}
                            break
                        except (OSError, ValueError, KeyError, TypeError):
                            continue
                    if recovered:
                        completed[row['case_id']] = recovered
                        if not quiet: report(len(completed), len(rows), row['case_id'], 'recovering completed scan; validation pending', None)
                    else:
                        pending.append(row)
            parent_created = psutil.Process().create_time()
            while pending or active:
                if cancelled is not None and cancelled():
                    stop_reason = 'CANCELLED'
                if stop_reason:
                    break
                while pending and len(active) < jobs:
                    row = pending.pop(0)
                    folder = _physical(output / 'attempts' / row['key'][:16] / uuid.uuid4().hex[:16])
                    folder.mkdir(parents=True)
                    atomic_write_json(folder / 'request.json', {'parent_pid': os.getpid(), 'parent_created': parent_created,
                        'engine_id': engine, 'scan': row['request'],
                        'parse_reuse': {'max_entries': 32768, 'max_payload_bytes': 67108864} if reuse_parses else None})
                    env = dict(os.environ)
                    env.update(PYTHONPATH=str(Path(__file__).resolve().parent.parent), TMP=str(folder), TEMP=str(folder), TMPDIR=str(folder))
                    env.pop('JAVA_HOME', None)
                    env['PATH'] = str(Path(sys.executable).parent)
                    if row['needs_java']:
                        env['JAVA_HOME'] = row['request']['jdk']
                        env['PATH'] = str(Path(row['request']['jdk']) / 'bin') + os.pathsep + env['PATH']
                    process = AnalysisProcess([sys.executable, '-m', 'bridgeforge.portfolio_worker', str(folder)], folder=folder, env=env)
                    active[row['case_id']] = (row, folder, process, time.perf_counter())
                    atomic_write_json(folder / 'start.json', {'invocation': invocation})
                    maximum = max(maximum, len(active))
                rss = sum(value[2].rss() for value in active.values())
                peak = max(peak, rss)
                if rss > memory_mib * 1024 * 1024:
                    stop_reason = 'MEMORY_STOP'
                    break
                for case_id, (row, folder, process, started) in list(active.items()):
                    timed_out = time.perf_counter() - started > timeout
                    code = process.poll()
                    if code is None and not timed_out:
                        continue
                    process.close()
                    del active[case_id]
                    state = 'TIMEOUT' if timed_out else 'FAILED' if code else 'SCANNED'
                    value = {**row_selection(row), 'state': state, 'attempt': str(folder)}
                    if state == 'SCANNED':
                        try:
                            _response(folder / 'response.json')
                            metrics = _read(folder / 'metrics.json')
                            value.update(raw=str(folder / 'response.json'), scan_seconds=metrics['seconds'])
                            content = {'key': row['key'], 'observed_at': datetime.now(timezone.utc).isoformat(),
                                       'artifacts': {str(folder / name): file_digest(folder / name)
                                                                     for name in ('response.json', 'metrics.json')}}
                            atomic_write_json(folder / 'completion.json', {'content': content, 'sha256': digest(content)})
                            value['artifact_sha256'] = content['artifacts']
                            value['observed_at'] = content['observed_at']
                        except (OSError, ValueError, KeyError, TypeError):
                            value['state'] = 'FAILED'
                    completed[case_id] = value
                    if not quiet: report(len(completed), len(rows), case_id, value['state'] + '; not qualification', time.perf_counter() - started)
                    checkpoint.add(row['key'], value)
                time.sleep(.025)
        except KeyboardInterrupt:
            stop_reason = 'CANCELLED'
        finally:
            for row, folder, process, _ in active.values():
                process.close()
                completed[row['case_id']] = {**row_selection(row), 'state': stop_reason or 'INTERRUPTED', 'attempt': str(folder)}
            checkpoint.close()
        verify_began = time.perf_counter()
        errors = _fresh(rows)
        if engine_identity() != engine:
            errors.update({row['case_id']: 'Engine changed during analysis' for row in rows})
        for row in rows:
            case_id = row['case_id']
            value = completed.setdefault(case_id, {**row_selection(row), 'state': stop_reason or 'QUEUED'})
            try:
                if any(file_digest(Path(path)) != hashed for path, hashed in value.get('artifact_sha256', {}).items()):
                    errors[case_id] = 'Analysis evidence changed during evaluation'
            except (OSError, ValueError):
                errors[case_id] = 'Analysis evidence became unavailable'
            if case_id in errors:
                value.update(state='STALE', reason=errors[case_id])
                if 'raw' in value:
                    marker = _physical(Path(value['raw']).parent / 'invalidated.json')
                    if not marker.exists():
                        atomic_write_json(marker, {'invocation': invocation, 'reason': errors[case_id], 'engine_id': engine})
            elif value['state'] in {'SCANNED', 'RECOVERING'}:
                folder = Path(value['attempt'])
                record = make_receipt(row['candidate'], kind='portfolio-analysis', outcome='PASS',
                    reason='Read-only scan completed on bound inputs; findings are not qualification or approval',
                    tool={'name': 'bridgeforge.portfolio', 'version': '1', 'sha256': engine},
                    run_id=folder.name, observed_at=value['observed_at'],
                    evidence=[folder / 'response.json', folder / 'metrics.json'])
                store.add_receipt(case_id, record)
                atomic_write_json(folder / 'receipt.json', record)
                value.update(state='RECOVERED' if value['state'] == 'RECOVERING' else 'ANALYZED', receipt_id=record['record_id'])
        result = {'schema_version': 1, 'state': 'COMPLETE' if all(v['state'] in {'ANALYZED', 'REUSED', 'RECOVERED'} for v in completed.values()) else 'INCOMPLETE',
                  'engine_id': engine, 'invocation': invocation, 'configuration': config,
                  'cases': [completed[row['case_id']] for row in rows], 'stop_reason': stop_reason,
                  'max_active_workers': maximum, 'sampled_peak_worker_family_rss': peak,
                  'preflight_seconds': preflight_seconds, 'postflight_seconds': time.perf_counter() - verify_began,
                  'elapsed_seconds': time.perf_counter() - began, 'qualification': 'NOT_EVALUATED',
                  'memory_scope': 'sampled worker/descendant RSS; coordinator excluded; not a hard OS limit'}
        runs = _physical(output / 'runs')
        runs.mkdir(exist_ok=True)
        atomic_write_json(runs / (invocation + '.json'), result)
        if result['state'] == 'COMPLETE': checkpoint.finish()
        return result


def row_selection(row):
    return {key: row[key] for key in ('case_id', 'candidate_id', 'dependency_resolution')}
