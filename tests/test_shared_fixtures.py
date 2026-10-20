"""Hashed fixture trees stay byte-identical to the Project Go checkout (ROADMAP 77.23).

Runs only when PROJECT_GO_FIXTURES names a Project Go checkout; CI sets it in the `shared-fixtures` job. Every file under
each shared folder must exist at the same relative path in that checkout with the same bytes.
"""

import os
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SHARED_FIXTURE_DIRS = ("fixtures/runtime-context", "fixtures/translation-conformance")
ENV_VAR = "PROJECT_GO_FIXTURES"


def _files_under(folder: Path) -> list[Path]:
    return sorted(path for path in folder.rglob("*") if path.is_file())


@unittest.skipUnless(os.environ.get(ENV_VAR), f"set {ENV_VAR} to a Project Go checkout to compare shared fixtures")
class SharedFixturesTest(unittest.TestCase):
    def test_shared_fixture_files_are_byte_identical(self):
        project_go = Path(os.environ[ENV_VAR]).expanduser()
        self.assertTrue(project_go.is_dir(), f"{ENV_VAR} is not a directory: {project_go}")
        differences: list[str] = []
        checked = 0
        for relative in SHARED_FIXTURE_DIRS:
            local_folder = REPO / relative
            self.assertTrue(local_folder.is_dir(), f"missing shared fixture folder {local_folder}")
            for local_file in _files_under(local_folder):
                checked += 1
                rel_path = local_file.relative_to(REPO).as_posix()
                remote_file = project_go / rel_path
                if not remote_file.is_file():
                    differences.append(f"missing in Project Go: {rel_path}")
                elif local_file.read_bytes() != remote_file.read_bytes():
                    differences.append(f"bytes differ: {rel_path}")
        self.assertGreater(checked, 0, "no shared fixture files were found to compare")
        self.assertEqual(differences, [], "shared fixtures diverge from Project Go:\n" + "\n".join(differences))


if __name__ == "__main__":
    unittest.main()
