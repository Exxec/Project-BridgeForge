"""Read-only import of Project Go observations; no approval or compatibility inference."""
import hashlib
import json
import os
import re
import stat
import struct
from pathlib import Path

SCHEMA = 'ssmt-localization-coverage-1'
MAX_MANIFEST_BYTES, MAX_FILES, MAX_SOURCE_BYTES = 8 * 1024 * 1024, 100000, 128 * 1024 * 1024
FIELDS = {'schemaVersion', 'inputKind', 'selectedRoot', 'candidateSha256', 'archiveSha256', 'coverageStatus', 'files', 'supportedFileCount', 'skippedFileCount', 'extractedStringCount', 'totalSupportedStringCount', 'jsonGapCount', 'csvGapCount', 'limitations'}
STATUSES = {'OBSERVED_STANDARD_EXTRACTION', 'NOT_ASSESSED', 'NOT_ASSESSED_INVALID_JAR', 'INCOMPLETE_SOURCE_PARSE'}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _path(value, empty=False):
    _require(isinstance(value, str), 'Path must be text')
    if empty and not value:
        return
    _require(bool(value) and not any(c in value for c in '\\:\x00') and not value.startswith('/'), 'Unsafe path')
    _require(all(p not in ('', '.', '..') for p in value.split('/')), 'Unsafe path component')
    value.encode('utf-8')


def _count(value):
    _require(type(value) is int and 0 <= value <= 2147483647, 'Invalid count')


def _hash(value, empty=False):
    _require(isinstance(value, str) and (empty and value == '' or re.fullmatch('[0-9a-f]{64}', value)), 'Invalid SHA256')


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, 'Duplicate JSON field')
        result[key] = value
    return result


def read_manifest(path):
    """Read and strictly validate one bounded report, without changing it."""
    path = Path(os.path.abspath(path))
    for ancestor in (path, *path.parents):
        _safe_stat(ancestor)
    before = _safe_stat(path)
    _require(stat.S_ISREG(before.st_mode), 'Manifest must be a regular file')
    with Path(path).open('rb') as stream:
        raw = stream.read(MAX_MANIFEST_BYTES + 1)
    _require(_stamp(before) == _stamp(_safe_stat(Path(path))), 'Manifest changed during read')
    _require(len(raw) <= MAX_MANIFEST_BYTES, 'Manifest exceeds byte budget')
    report = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                        parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite number')))
    _require(type(report) is dict and set(report) == FIELDS, 'Invalid manifest fields')
    _require(report['schemaVersion'] == SCHEMA, 'Unsupported schema')
    _require(report['inputKind'] in ('DIRECTORY', 'ZIP'), 'Unsupported input kind')
    _path(report['selectedRoot'], empty=True)
    _hash(report['candidateSha256'], empty=True)
    _hash(report['archiveSha256'], empty=report['inputKind'] == 'DIRECTORY')
    _require(report['inputKind'] != 'DIRECTORY' or report['archiveSha256'] == '', 'Unexpected archive hash')
    _require(isinstance(report['coverageStatus'], str) and report['coverageStatus'] in STATUSES, 'Unknown coverage status')
    _require(type(report['files']) is list and len(report['files']) <= MAX_FILES, 'Invalid file rows')
    names, supported, skipped, strings = set(), 0, 0, 0
    for row in report['files']:
        _require(type(row) is dict and set(row) == {'path', 'handler', 'status', 'strings', 'reason'}, 'Invalid file row')
        _path(row['path'])
        _require(row['path'] not in names, 'Duplicate file row')
        names.add(row['path'])
        _count(row['strings'])
        _require(isinstance(row['handler'], str) and isinstance(row['reason'], str) and row['reason'], 'Missing row evidence')
        _require(isinstance(row['status'], str) and row['status'] in ('UNSUPPORTED', 'SUPPORTED_NO_STRINGS', 'EXTRACTED'), 'Unknown file status')
        if row['status'] == 'UNSUPPORTED':
            _require(row['strings'] == 0 and row['handler'] == '', 'Invalid unsupported row')
            skipped += 1
        else:
            _require(bool(row['handler']), 'Supported row requires handler')
            _require((row['status'] == 'EXTRACTED') == (row['strings'] > 0), 'Inconsistent string status')
            supported += 1
        strings += row['strings']
    for key in ('supportedFileCount', 'skippedFileCount', 'extractedStringCount', 'jsonGapCount', 'csvGapCount'):
        _count(report[key])
    _require((supported, skipped, strings) == (report['supportedFileCount'], report['skippedFileCount'], report['extractedStringCount']), 'Counts disagree with file rows')
    if report['totalSupportedStringCount'] is not None:
        _count(report['totalSupportedStringCount'])
        _require(report['totalSupportedStringCount'] >= strings, 'Total below observed strings')
    _require(type(report['limitations']) is list and all(isinstance(x, str) and x for x in report['limitations']), 'Invalid limitations')
    return report


def _safe_stat(path):
    item = path.lstat()
    _require(not stat.S_ISLNK(item.st_mode) and not (getattr(item, 'st_file_attributes', 0) & 0x400), 'Linked candidate path')
    _require(stat.S_ISREG(item.st_mode) or stat.S_ISDIR(item.st_mode), 'Special candidate path')
    _require(not stat.S_ISREG(item.st_mode) or item.st_nlink == 1, 'Hardlinked candidate file')
    return item


def _stamp(item):
    return item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns, item.st_ctime_ns, item.st_mode


def inventory(candidate):
    """Hash every candidate file, rejecting links/special files and bounded by total bytes."""
    root = Path(os.path.abspath(candidate))
    for ancestor in (root, *root.parents):
        _safe_stat(ancestor)
    _require(root.is_dir(), 'Candidate must be a directory')
    rows, states, budget, pending = [], [], 0, [root]
    while pending:
        path = pending.pop()
        before = _safe_stat(path)
        name = path.relative_to(root).as_posix()
        if stat.S_ISDIR(before.st_mode):
            with os.scandir(path) as children:
                pending.extend(Path(item.path) for item in children)
            _require(len(pending) + len(states) <= MAX_FILES * 2, 'Tree entry budget exceeded')
        else:
            _path(name)
            _require(len(rows) < MAX_FILES, 'File budget exceeded')
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                for data in iter(lambda: stream.read(65536), b''):
                    budget += len(data)
                    _require(budget <= MAX_SOURCE_BYTES, 'Source byte budget exceeded')
                    digest.update(data)
            rows.append((name, before.st_size, digest.digest()))
        _require(_stamp(before) == _stamp(_safe_stat(path)), 'Source changed during hashing')
        states.append((name, _stamp(before)))
    digest = hashlib.sha256(b'ProjectGo-inventory-v1\0')
    for name, size, content_hash in sorted(rows, key=lambda row: row[0].encode('utf-16-be')):
        encoded = name.encode('utf-8')
        digest.update(struct.pack('>i', len(encoded)) + encoded + struct.pack('>q', size) + content_hash)
    return digest.hexdigest(), frozenset(row[0] for row in rows), sorted(states)


def observe(manifest, candidate):
    """Join report with exact current bytes; identity match does not establish full coverage."""
    report = read_manifest(manifest)
    before = inventory(candidate)
    after = inventory(candidate)
    _require(before == after, 'Source changed between inventories')
    identity = 'UNKNOWN' if not report['candidateSha256'] else 'MATCH' if before[0] == report['candidateSha256'] else 'MISMATCH'
    paths = {row['path'] for row in report['files']}
    if identity == 'MATCH':
        _require(paths <= before[1], 'Report names absent candidate files')
        if report['coverageStatus'] == 'OBSERVED_STANDARD_EXTRACTION':
            _require(paths == before[1], 'Observed inventory omits candidate files')
    return {'schemaVersion': SCHEMA, 'candidateIdentity': identity, 'observedCandidateSha256': before[0],
            'coverageStatus': report['coverageStatus'], 'completeCoverageEstablished': False,
            'scope': 'SELECTED_STRINGS_ONLY' if report['coverageStatus'] == 'OBSERVED_STANDARD_EXTRACTION' else 'PARTIAL_OR_UNKNOWN',
            'runtime': 'NOT_TESTED', 'approval': 'NOT_ASSESSED', 'rights': 'NOT_ASSESSED',
            'archiveIdentity': 'NOT_VERIFIED', 'report': report}
