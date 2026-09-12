from __future__ import annotations

import re
import unittest
from pathlib import Path

from bridgeforge.fixers import SUPPORTED_FINDINGS

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = REPO_ROOT / "docs" / "BUG_CLASSES.md"
SCANNER_PATH = REPO_ROOT / "bridgeforge" / "scanner.py"
PROBE_MOD_DIR = REPO_ROOT / "probe-mod"

_ID_RE = re.compile(r"`([a-z][a-z0-9-]*)`")


def _table_rows(markdown: str) -> list[list[str]]:
    rows = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 6:
            continue
        if set(cells[0]) <= {"-"}:  # the "|---|---|" separator row
            continue
        if cells[0] == "Bug class":
            continue
        rows.append(cells)
    return rows


def _probe_source() -> str:
    if not PROBE_MOD_DIR.is_dir():
        return ""
    return "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in PROBE_MOD_DIR.rglob("*.java"))


class BugClassRegistryTests(unittest.TestCase):
    def test_registry_file_exists_and_has_rows(self) -> None:
        self.assertTrue(REGISTRY_PATH.is_file())
        rows = _table_rows(REGISTRY_PATH.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(rows), 10, "expected at least 10 documented bug classes")

    def test_every_row_has_a_check_id_or_a_written_reason(self) -> None:
        rows = _table_rows(REGISTRY_PATH.read_text(encoding="utf-8"))
        for row in rows:
            bug_class, _symptom, _cause, check_cell, _test_file, _mod = row
            ids = _ID_RE.findall(check_cell)
            has_written_reason = check_cell.strip().upper().startswith("NONE (WRITTEN REASON:")
            self.assertTrue(
                ids or has_written_reason,
                f"{bug_class}: check column must name a real check id or start with 'NONE (written reason: ...)', got: {check_cell!r}",
            )

    def test_every_listed_check_id_exists_somewhere_in_the_codebase(self) -> None:
        scanner_src = SCANNER_PATH.read_text(encoding="utf-8")
        probe_src = _probe_source()
        rows = _table_rows(REGISTRY_PATH.read_text(encoding="utf-8"))
        missing: list[str] = []
        for row in rows:
            bug_class, _symptom, _cause, check_cell, _test_file, _mod = row
            for check_id in _ID_RE.findall(check_cell):
                in_scanner = f'id="{check_id}"' in scanner_src
                in_fixers = check_id in SUPPORTED_FINDINGS
                in_probe = f'"{check_id}"' in probe_src
                if not (in_scanner or in_fixers or in_probe):
                    missing.append(f"{bug_class}: `{check_id}` not found in scanner.py, fixers.SUPPORTED_FINDINGS, or probe-mod sources")
        self.assertEqual(missing, [], "\n".join(missing))

    def test_every_row_names_a_test_file_or_probe_source(self) -> None:
        rows = _table_rows(REGISTRY_PATH.read_text(encoding="utf-8"))
        for row in rows:
            bug_class, _symptom, _cause, _check_cell, test_file_cell, _mod = row
            self.assertNotEqual(test_file_cell.strip(), "", f"{bug_class}: test-file column is empty")


if __name__ == "__main__":
    unittest.main()
