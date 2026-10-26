"""Standalone standard-library verifier; verifies code bits, never case qualification."""
import hashlib
import importlib.metadata
import json
from pathlib import Path, PurePosixPath
import platform
import struct
import sys


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate kit field: ' + key)
        result[key] = value
    return result


def _hash(path):
    hashed = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            hashed.update(chunk)
    return hashed.hexdigest()


def verify_kit(root):
    root = Path(root).absolute()
    problems = []
    try:
        for parent in (root, *root.parents):
            if parent.is_symlink() or parent.is_junction():
                raise ValueError('Kit refuses linked roots')
        path = root / 'KIT_MANIFEST.json'
        if path.is_symlink() or path.is_junction() or path.stat().st_size > 16 * 1024 * 1024:
            raise ValueError('Invalid kit manifest file')
        record = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=_unique)
        if (set(record) != {'schema', 'schema_version', 'content', 'sha256'}
                or record['schema'] != 'bridgeforge.local-trial-kit'
                or type(record['schema_version']) is not int or record['schema_version'] != 1):
            raise ValueError('Unsupported local kit schema; obtain a compatible kit')
        body = record['content']
        canonical = json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')
        if hashlib.sha256(canonical).hexdigest() != record['sha256']:
            raise ValueError('Kit manifest content hash mismatch')
        if (body['restrictions'] != {'publication_authorized': False, 'private_payload_included': False}
                or any(type(value) is not bool for value in body['restrictions'].values())
                or not isinstance(body['files'], dict) or not body['files']):
            raise ValueError('Kit privacy/files contract is unsupported')
        expected = {'target': '0.98a-RC8', 'java': 17, 'scope': 'new-game', 'qualification_profile': 'rc8-local-new-game/v2'}
        if body['trial_profile'] != expected or body['trial_platform'] != 'windows-x64':
            raise ValueError('Unsupported trial profile/platform; obtain a compatible kit')
        for name, expected in body['files'].items():
            relative = PurePosixPath(name)
            if (not isinstance(name, str) or '\\' in name or ':' in name or relative.is_absolute()
                    or any(part in {'', '.', '..'} for part in name.split('/'))):
                raise ValueError('Unsafe kit member path')
            target = root.joinpath(*relative.parts)
            for component in (target, *target.parents):
                if component.is_symlink() or component.is_junction():
                    raise ValueError('Linked kit member')
                if component == root: break
            try:
                if not target.is_file() or _hash(target) != expected:
                    problems.append(name + ': missing or changed')
            except OSError:
                problems.append(name + ': unreadable')
        try:
            psutil = importlib.metadata.version('psutil')
        except importlib.metadata.PackageNotFoundError:
            psutil = None
        supported_platform = (platform.system() == 'Windows' and platform.machine().lower() in {'amd64', 'x86_64'}
                              and struct.calcsize('P') == 8)
        environment_ready = sys.version_info[:2] == (3, 15) and psutil == body['psutil_version'] and supported_platform
        return {'state': 'REFUSED' if problems else 'READY_FOR_LOCAL_TRIAL' if environment_ready else 'CODE_VERIFIED_SETUP_PENDING',
                'problems': problems, 'kit_sha256': record['sha256'], 'engine_id': body['engine_id'],
                'runtime': {'python': sys.version, 'psutil': psutil, 'platform': platform.platform(),
                            'pointer_bits': struct.calcsize('P') * 8}, 'environment_ready': environment_ready,
                'qualification': 'NOT_EVALUATED', 'human_operator_trial': 'NOT_OBSERVED',
                'publication': 'NOT_AUTHORIZED', 'extra_generated_files': 'NOT_ATTESTED'}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {'state': 'REFUSED', 'problems': [str(exc)], 'qualification': 'NOT_EVALUATED'}


if __name__ == '__main__':
    value = verify_kit(Path(__file__).parent)
    print(json.dumps(value, indent=2))
    raise SystemExit(0 if value['state'] == 'READY_FOR_LOCAL_TRIAL' else 1)
