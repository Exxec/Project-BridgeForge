"""Built distributions must not absorb ignored state or lookalike namespaces."""
import json
from pathlib import Path
import subprocess
import sys
import tomllib
import unittest
import zipfile

from tests.support import resolved_temp_dir


class PackageDiscoveryTests(unittest.TestCase):
    def test_real_backend_excludes_state_and_keeps_runtime_subpackages_and_data(self):
        repo = Path(__file__).resolve().parent.parent
        version = tomllib.loads((repo / 'pyproject.toml').read_text())['project']['version']
        metadata = 'bridgeforge-' + version + '.dist-info/'
        with resolved_temp_dir() as root:
            (root / 'pyproject.toml').write_bytes((repo / 'pyproject.toml').read_bytes())
            fixtures = {
                'bridgeforge/__init__.py': '',
                'bridgeforge/cli.py': 'def main(): return 0\n',
                'bridgeforge/scan/__init__.py': '',
                'bridgeforge/scan/scanner.py': 'VALUE = 1\n',
                'bridgeforge/java/fixture.java': '// synthetic package resource\n',
                'bridgeforge/release_policy.json': '{}',
                'bridgeforge-state/private.py': 'PRIVATE_STATE = True\n',
                'bridgeforge-state/env/Lib/site-packages/bridgeforge/secret.py': 'PRIVATE_ENV = True\n',
                'bridgeforge_extra/__init__.py': 'NOT_RUNTIME = True\n',
            }
            for name, content in fixtures.items():
                path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(content)
            result = subprocess.run([sys.executable, '-c',
                'from setuptools.build_meta import build_wheel; build_wheel("dist")'], cwd=root,
                capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, (result.stdout + result.stderr)[-4000:])
            wheel = next((root / 'dist').glob('*.whl'))
            with zipfile.ZipFile(wheel) as archive:
                names = set(archive.namelist())
                self.assertTrue(all(name.startswith(('bridgeforge/', metadata)) for name in names), sorted(names))
                self.assertTrue({'bridgeforge/scan/scanner.py', 'bridgeforge/java/fixture.java',
                                 'bridgeforge/release_policy.json'}.issubset(names))
                self.assertEqual(json.loads(archive.read('bridgeforge/release_policy.json')), {})
