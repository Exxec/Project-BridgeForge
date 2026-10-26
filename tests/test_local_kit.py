"""Self-authored code-only kit fixtures; never a machine/human or game qualification."""
from contextlib import ExitStack, redirect_stdout
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch
import zipfile

from bridgeforge import local_kit as api
from bridgeforge.case_identity import digest
from bridgeforge.cli import main
from bridgeforge.kit_resources.verify_kit import verify_kit
from tests.support import resolved_temp_dir


def fixture(root):
    repo = root / 'source'; package = repo / 'bridgeforge'; package.mkdir(parents=True)
    for name in ('__init__.py', '__main__.py', 'local_kit.py'):
        (package / name).write_text('# Self-authored unit test code only\n')
    resources = Path(api.__file__).parent / 'kit_resources'
    shutil.copytree(resources, package / 'kit_resources', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    probe = repo / 'probe-mod'; probe.mkdir()
    (probe / 'mod_info.json').write_text('{"id":"self-authored-unit-fixture"}')
    tools = repo / 'tools'; tools.mkdir()
    (tools / 'bf-test.ps1').write_text('# Self-authored harness fixture, never run a game')
    (repo / 'LICENSE').write_text('Self-authored unit fixture license')
    assets = [probe / 'mod_info.json', tools / 'bf-test.ps1']
    wheel = root / 'fixture.whl'
    with zipfile.ZipFile(wheel, 'w') as archive:
        for path in package.rglob('*'):
            if path.is_file(): archive.write(path, path.relative_to(repo).as_posix())
    return repo, wheel, assets, repo / 'bridgeforge-state/kit'


class LocalKitTests(unittest.TestCase):
    def build(self, repo, wheel, assets, output, *, quiet=True):
        with ExitStack() as stack:
            stack.enter_context(patch.object(api, '__file__', str(repo / 'bridgeforge/local_kit.py')))
            stack.enter_context(patch.object(api, '_assets', return_value=assets))
            stack.enter_context(patch.object(api, 'engine_identity', return_value='e' * 64))
            return api.build_local_kit(repo, wheel, output, quiet=quiet)

    def test_code_only_kit_and_standalone_verification(self):
        with resolved_temp_dir() as root:
            repo, wheel, assets, output = fixture(root)
            value = self.build(repo, wheel, assets, output)
            self.assertEqual(value['state'], 'LOCAL_TRIAL_KIT_READY')
            self.assertEqual(value['human_operator_trial'], 'NOT_OBSERVED')
            checked = verify_kit(output)
            self.assertIn(checked['state'], {'READY_FOR_LOCAL_TRIAL', 'CODE_VERIFIED_SETUP_PENDING'})
            self.assertTrue((output / 'runtime/tools/bf-test.ps1').is_file())
            done = subprocess.run([sys.executable, str(output / 'VerifyKit.py')], cwd=root, capture_output=True, text=True, timeout=15)
            self.assertEqual(done.returncode, 0 if checked['environment_ready'] else 1, done.stderr)
            self.assertEqual(json.loads(done.stdout)['qualification'], 'NOT_EVALUATED')
            (output / 'runtime/bridgeforge/__main__.py').write_text('modified')
            self.assertEqual(verify_kit(output)['state'], 'REFUSED')
            with zipfile.ZipFile(value['archive']) as archive:
                self.assertFalse(any('/.git/' in n or '/In operation/' in n or '/saves/' in n for n in archive.namelist()))
            with self.assertRaisesRegex(ValueError, 'new directory'):
                self.build(repo, wheel, assets, output)

    def test_bad_wheel_traversal_or_foreign_namespace_never_publishes(self):
        with resolved_temp_dir() as root:
            repo, wheel, assets, output = fixture(root)
            with zipfile.ZipFile(wheel, 'a') as archive:
                archive.writestr('../escape.py', 'must not escape')
            with self.assertRaisesRegex(ValueError, 'traversal'):
                self.build(repo, wheel, assets, output)
            self.assertFalse(output.exists())
            self.assertFalse((root / 'escape.py').exists())
        with resolved_temp_dir() as root:
            repo, wheel, assets, output = fixture(root)
            with zipfile.ZipFile(wheel, 'a') as archive:
                archive.writestr('foreign/__init__.py', 'foreign')
            with self.assertRaisesRegex(ValueError, 'Foreign'):
                self.build(repo, wheel, assets, output)
            self.assertFalse(output.exists())

    def test_stale_source_missing_module_and_outside_output_refuse(self):
        with resolved_temp_dir() as root:
            repo, wheel, assets, output = fixture(root)
            (repo / 'bridgeforge/__main__.py').write_text('changed after wheel build')
            with self.assertRaisesRegex(ValueError, 'differs'):
                self.build(repo, wheel, assets, output)
            with self.assertRaisesRegex(ValueError, 'bridgeforge-state'):
                self.build(repo, wheel, assets, root / 'outside')
        with resolved_temp_dir() as root:
            repo, wheel, assets, output = fixture(root)
            (repo / 'bridgeforge/new.py').write_text('not in wheel')
            with self.assertRaisesRegex(ValueError, 'missing current Python'):
                self.build(repo, wheel, assets, output)

    def test_manifest_tamper_and_missing_dependency_stay_unqualified(self):
        with resolved_temp_dir() as root:
            repo, wheel, assets, output = fixture(root)
            self.build(repo, wheel, assets, output)
            with patch('bridgeforge.kit_resources.verify_kit.importlib.metadata.version', side_effect=api.importlib.metadata.PackageNotFoundError('psutil')):
                result = verify_kit(output)
            self.assertEqual(result['state'], 'CODE_VERIFIED_SETUP_PENDING')
            manifest = output / 'KIT_MANIFEST.json'
            record = json.loads(manifest.read_text()); record['schema_version'] = True
            manifest.write_text(json.dumps(record))
            self.assertEqual(verify_kit(output)['state'], 'REFUSED')
            record['schema_version'] = 1
            record['content']['files'] = {'../outside.txt': '0' * 64}
            record['sha256'] = digest(record['content']); manifest.write_text(json.dumps(record))
            self.assertEqual(verify_kit(output)['state'], 'REFUSED')

    def test_cli_verifier_and_bad_archive_are_actionable(self):
        with resolved_temp_dir() as root:
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(['local-kit', 'verify', str(root / 'missing')]), 1)

    def test_interrupted_copy_resumes_verified_members(self):
        with resolved_temp_dir() as root:
            repo, wheel, assets, output = fixture(root)
            write = api.atomic_write_bytes
            calls = []
            def stop(path, data):
                calls.append(1)
                if len(calls) == 3:
                    raise OSError('self-authored interruption fixture')
                return write(path, data)
            with patch.object(api, 'atomic_write_bytes', side_effect=stop):
                with self.assertRaisesRegex(OSError, 'interruption fixture'):
                    self.build(repo, wheel, assets, output)
            self.assertFalse(output.exists())
            stream = io.StringIO()
            with patch('sys.stderr', stream):
                value = self.build(repo, wheel, assets, output, quiet=False)
            self.assertEqual(value['state'], 'LOCAL_TRIAL_KIT_READY')
            self.assertIn('from checkpoint', stream.getvalue())
            self.assertFalse(output.with_name(output.name + '.kit.partial.jsonl').exists())
