"""Build a local source-backed trial kit from an exact wheel and owned checkout assets."""
from __future__ import annotations

import importlib.metadata
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
import subprocess
import time
import zipfile

from .case_identity import digest, file_digest, tree_files
from .case_qualification import PROFILE_ID, TARGET, engine_identity
from .case_workspace import _components, _physical
from .kit_resources.verify_kit import verify_kit
from .portfolio import output_lease
from .progress import Checkpoint, report
from .safeio import atomic_write_bytes, atomic_write_json
from .zipsafe import read_limited


def _assets(repo: Path) -> list[Path]:
    try:
        done = subprocess.run(['git', '-c', 'safe.directory=' + str(repo), '-C', str(repo),
                               'ls-files', '-z', '--', 'probe-mod', 'tools/bf-test.ps1'],
                              capture_output=True, check=False, timeout=30)
    except subprocess.TimeoutExpired as exc:
        raise ValueError('Owned source asset inventory timed out; no kit was published') from exc
    if done.returncode:
        raise ValueError('Kit assets require a readable validated source checkout')
    chosen = []
    for value in done.stdout.decode('utf-8').split('\0'):
        if not value:
            continue
        parts = _components(value, 'owned kit asset')
        path = _physical(repo.joinpath(*parts))
        if value == 'tools/bf-test.ps1' or (parts[0] == 'probe-mod'
                and not {'releases', 'jars', 'build'}.intersection(parts)
                and path.suffix in {'.java', '.json', '.csv', '.txt', '.md'}):
            chosen.append(path)
    if not chosen or repo / 'tools/bf-test.ps1' not in chosen or repo / 'probe-mod/mod_info.json' not in chosen:
        raise ValueError('Owned probe/harness assets are incomplete')
    return sorted(chosen)


def build_local_kit(repo: Path, wheel: Path, output: Path, *, quiet: bool = False) -> dict:
    repo, wheel, output = _physical(Path(repo)), _physical(Path(wheel)), _physical(Path(output))
    if not output.is_relative_to(repo / 'bridgeforge-state') or output.exists():
        raise ValueError('Kit output must be a new directory under this checkout bridgeforge-state')
    with ExitStack() as stack:
        stack.enter_context(output_lease(output.parent))
        return _build_local_kit(repo, wheel, output, quiet=quiet, stack=stack)


def _build_local_kit(repo: Path, wheel: Path, output: Path, *, quiet: bool, stack: ExitStack) -> dict:
    repo, wheel, output = _physical(Path(repo)), _physical(Path(wheel)), _physical(Path(output))
    if repo / 'bridgeforge' != Path(__file__).resolve().parent:
        raise ValueError('Build the trial kit from the currently loaded validated checkout')
    if wheel.suffix.casefold() != '.whl':
        raise ValueError('A built .whl file is required for the local kit')
    if not output.is_relative_to(repo / 'bridgeforge-state') or output.exists():
        raise ValueError('Kit output must be a new directory under this checkout bridgeforge-state')
    archive_path = output.with_name(output.name + '.zip')
    if archive_path.exists():
        raise ValueError('Kit archive already exists; choose a new output name')
    engine, wheel_hash = engine_identity(), file_digest(wheel)
    assets = _assets(repo)
    sources = {str(path): file_digest(path) for path in assets}
    resources = Path(__file__).parent / 'kit_resources'
    sources.update({str(path): file_digest(path) for path in [repo / 'LICENSE', *resources.iterdir()]
                    if path.is_file() and path.suffix != '.pyc'})
    version = importlib.metadata.version('psutil')
    header = {'schema_version': 1, 'engine': engine, 'wheel_sha256': wheel_hash, 'wheel_name': wheel.name,
              'sources': dict(sources), 'output': str(output), 'psutil_version': version}
    stage = _physical(output.with_name('.' + output.name + '-partial-' + digest(header)[:16]))
    stage.mkdir(parents=True, exist_ok=True)
    runtime = stage / 'runtime'
    runtime.mkdir(exist_ok=True)
    checkpoint_path = _physical(output.with_name(output.name + '.kit.partial.jsonl'))
    checkpoint = stack.enter_context(Checkpoint(checkpoint_path, header))
    number, total = 0, 0
    published = set()

    def publish(relative, data):
        nonlocal number
        started = time.perf_counter()
        path = _physical(stage / relative)
        hashed = sha256(data).hexdigest()
        saved = checkpoint.get(relative)
        reused = False
        if saved and saved.get('sha256') == hashed:
            try:
                reused = file_digest(path) == hashed
            except OSError:
                pass
        if not reused:
            atomic_write_bytes(path, data)
            checkpoint.add(relative, {'sha256': hashed})
        number += 1
        published.add(relative)
        if not quiet: report(number, total, relative, 'verified code-kit member', None if reused else time.perf_counter() - started)

    seen, python = set(), set()
    with zipfile.ZipFile(wheel) as archive:
        if len(archive.infolist()) > 20000 or sum(item.file_size for item in archive.infolist()) > 128 * 1024 * 1024:
            raise ValueError('Wheel exceeds local kit file/byte limits')
        total = sum(not item.is_dir() for item in archive.infolist()) + len(assets) + 6
        for item in archive.infolist():
            if item.is_dir():
                continue
            parts = _components(item.filename, 'wheel member')
            if item.filename != '/'.join(parts):
                raise ValueError('Wheel member names must use canonical portable separators')
            folded = item.filename.casefold()
            if folded in seen or (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Duplicate/linked wheel member')
            seen.add(folded)
            if parts[0] != 'bridgeforge' and not (parts[0].startswith('bridgeforge-') and parts[0].endswith('.dist-info')):
                raise ValueError('Foreign wheel namespace')
            data = read_limited(archive, item, max_bytes=32 * 1024 * 1024)
            if parts[0] == 'bridgeforge':
                source = _physical(repo.joinpath(*parts))
                if not source.is_file() or data != source.read_bytes():
                    raise ValueError('Wheel runtime payload differs from current source: ' + item.filename)
                sources[str(source)] = sha256(data).hexdigest()
                if source.suffix == '.py': python.add(source)
            publish('runtime/' + '/'.join(parts), data)
    expected = {path for path in (repo / 'bridgeforge').rglob('*.py') if '__pycache__' not in path.parts}
    if python != expected:
        raise ValueError('Wheel is missing current Python modules')
    for source in assets:
        data = source.read_bytes()
        if sha256(data).hexdigest() != sources[str(source)]:
            raise ValueError('Owned kit asset changed while reading')
        publish('runtime/' + source.relative_to(repo).as_posix(), data)
    publish('LICENSE', (repo / 'LICENSE').read_bytes())
    publish(wheel.name, wheel.read_bytes())
    publish('VerifyKit.py', (resources / 'verify_kit.py').read_bytes())
    publish('BridgeForge.ps1', (resources / 'BridgeForge.ps1').read_bytes())
    guide = (resources / 'TRIAL_GUIDE.md').read_text(encoding='utf-8').replace('__PSUTIL_VERSION__', version).replace('__PROFILE_ID__', PROFILE_ID)
    publish('TRIAL_GUIDE.md', guide.encode('utf-8'))
    publish('requirements-setup.txt', ('psutil==' + version + '\n').encode('utf-8'))
    files = {name: hashed for name, hashed in tree_files(stage).items() if name != 'KIT_MANIFEST.json'}
    if set(files) != published:
        raise ValueError('Unexpected/missing files in partial code kit; refusing publication')
    content = {'engine_id': engine, 'files': files, 'psutil_version': version,
               'trial_profile': TARGET, 'trial_platform': 'windows-x64',
               'operator_trial': 'NOT_OBSERVED', 'support_commitment': 'NOT_APPROVED',
               'restrictions': {'publication_authorized': False, 'private_payload_included': False},
               'private_inputs': 'TRANSFER_SEPARATELY; explicit restored case/context bindings required'}
    record = {'schema': 'bridgeforge.local-trial-kit', 'schema_version': 1, 'content': content, 'sha256': digest(content)}
    atomic_write_json(stage / 'KIT_MANIFEST.json', record)
    if (engine_identity() != engine or file_digest(wheel) != wheel_hash or _assets(repo) != assets
            or any(file_digest(Path(path)) != h for path, h in sources.items())):
        raise ValueError('Kit source inputs changed during packaging; preserve partial output and rebuild')
    checked = verify_kit(stage)
    if checked['state'] not in {'READY_FOR_LOCAL_TRIAL', 'CODE_VERIFIED_SETUP_PENDING'}:
        raise ValueError('Prepared kit failed its code/environment verification: ' + str(checked))
    if output.exists():
        raise ValueError('Kit output appeared during build; refusing replacement')
    stage.rename(output)
    # This archive contains only the verified source-backed code kit, never private inputs.
    with zipfile.ZipFile(archive_path, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted({**content['files'], 'KIT_MANIFEST.json': ''}):
            archive.write(output / name, arcname=output.name + '/' + name)
    checkpoint.finish()
    return {'state': 'LOCAL_TRIAL_KIT_READY', 'directory': str(output), 'archive': str(archive_path),
            'archive_sha256': file_digest(archive_path), 'kit_sha256': record['sha256'], 'engine_id': engine,
            'files': len(content['files']), 'publication': 'NOT_AUTHORIZED', 'private_payload': 'NOT_INCLUDED',
            'human_operator_trial': 'NOT_OBSERVED', 'support_commitment': 'NOT_APPROVED', 'qualification': 'NOT_EVALUATED'}
