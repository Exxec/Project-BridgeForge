"""96.5 A7: MOD_CHANGELOG entries and release decisions are fragments, so two machines never edit the same lines."""
from __future__ import annotations

import io
import json
import shutil
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from bridgeforge import mod_changelog
from bridgeforge.master_log import _timeline
from bridgeforge.release import ReleaseError, _load_policy, assemble_policy, policy_fragments, record_policy_decision
from bridgeforge.release_notes import run_cli
from tests.support import resolved_temp_dir

ROOT = Path(__file__).resolve().parents[1]
BASE = "# Mod changelog\n\nintro\n\n## 2026-11-01\n\n- **Old** 1.0: revived\n"


class ModChangelogFragmentTests(unittest.TestCase):
    def test_an_entry_is_a_fragment_and_the_file_is_untouched(self) -> None:
        with resolved_temp_dir() as root:
            path = root / "MOD_CHANGELOG.md"
            path.write_bytes(BASE.encode("utf-8"))
            line = mod_changelog.add_entry("Radar", "fixed the ring", version="3.0", day="2026-11-18", path=path)
            self.assertEqual(path.read_bytes(), BASE.encode("utf-8"))
            fragments = mod_changelog.pending_fragments(path)
            self.assertEqual(len(fragments), 1)
            self.assertEqual(fragments[0].read_bytes(), (line + "\n").encode("utf-8"))  # LF, as the repository keeps it
            self.assertIn("## 2026-11-18\n\n- **Radar** 3.0: fixed the ring", mod_changelog.merged_text(path))
            self.assertIn("- **Old** 1.0: revived", mod_changelog.merged_text(path))

    def test_the_same_entry_twice_or_on_two_machines_is_one_file(self) -> None:
        with resolved_temp_dir() as first, resolved_temp_dir() as second:
            for root in (first, first, second):
                mod_changelog.add_entry("Radar", "fixed the ring", version="3.0", day="2026-11-18", path=root / "MOD_CHANGELOG.md")
            names = [[p.name for p in mod_changelog.pending_fragments(root / "MOD_CHANGELOG.md")] for root in (first, second)]
        self.assertEqual(len(names[0]), 1)
        self.assertEqual(names[0], names[1])  # same name on both machines: git sees one file, not a conflict

    def test_an_entry_already_in_the_file_is_not_added_again(self) -> None:
        with resolved_temp_dir() as root:
            path = root / "MOD_CHANGELOG.md"
            path.write_bytes(BASE.encode("utf-8"))
            mod_changelog.add_entry("Old", "revived", version="1.0", day="2026-11-01", path=path)
            self.assertEqual(mod_changelog.pending_fragments(path), [])

    def test_assemble_folds_the_fragments_into_the_file(self) -> None:
        with resolved_temp_dir() as root:
            path = root / "MOD_CHANGELOG.md"
            path.write_bytes(BASE.encode("utf-8"))
            mod_changelog.add_entry("Radar", "fixed the ring", day="2026-11-18", path=path)
            merged = mod_changelog.merged_text(path)
            self.assertEqual(len(mod_changelog.assemble(path, dry_run=True)), 1)
            self.assertEqual(len(mod_changelog.pending_fragments(path)), 1)  # a dry run changes nothing
            folded = mod_changelog.assemble(path)
            self.assertEqual(len(folded), 1)
            self.assertEqual(mod_changelog.pending_fragments(path), [])
            self.assertEqual(path.read_text(encoding="utf-8"), merged)

    def test_the_master_log_timeline_sees_pending_entries(self) -> None:
        with resolved_temp_dir() as root:
            path = root / "MOD_CHANGELOG.md"
            path.write_bytes(BASE.encode("utf-8"))
            mod_changelog.add_entry("Radar", "fixed the ring", day="2026-11-18", path=path)
            self.assertEqual(_timeline(path)[0], ("2026-11-18", "**Radar**: fixed the ring"))
            path.unlink()  # fragments alone still read
            self.assertEqual(_timeline(path), [("2026-11-18", "**Radar**: fixed the ring")])


class ReleaseDecisionFragmentTests(unittest.TestCase):
    def _policy(self, root: Path) -> Path:
        policy = root / "release_policy.json"
        policy.write_text(json.dumps({"schema_version": 1, "default": {"local_only": True},
                                      "mods": {"ExiGency": {"local_only": True, "reason": "old"}}}), encoding="utf-8")
        return policy

    def test_a_decision_is_a_fragment_laid_over_the_file(self) -> None:
        with resolved_temp_dir() as root:
            policy = self._policy(root)
            before = policy.read_bytes()
            result = record_policy_decision("exigency", local_only=False, reason="permission", on="2026-11-18", policy_path=policy)
            self.assertEqual(policy.read_bytes(), before)
            self.assertEqual(Path(result["file"]).name, "ExiGency.json")  # the existing key's spelling
            self.assertEqual(_load_policy(policy)["mods"]["ExiGency"], {"local_only": False, "reason": "permission", "recorded_on": "2026-11-18"})
            self.assertEqual(result["previous"], {"local_only": True, "reason": "old"})

    def test_assemble_folds_decisions_into_the_file(self) -> None:
        with resolved_temp_dir() as root:
            policy = self._policy(root)
            record_policy_decision("newmod", local_only=True, reason="no licence", on="2026-11-18", policy_path=policy)
            self.assertEqual(assemble_policy(policy, dry_run=True), ["newmod.json"])
            self.assertEqual(len(policy_fragments(policy)), 1)
            self.assertEqual(assemble_policy(policy), ["newmod.json"])
            self.assertEqual(policy_fragments(policy), [])
            self.assertEqual(json.loads(policy.read_text(encoding="utf-8"))["mods"]["newmod"]["reason"], "no licence")
            self.assertNotIn(b"\r\n", policy.read_bytes())

    def test_a_malformed_decision_is_refused(self) -> None:
        with resolved_temp_dir() as root:
            policy = self._policy(root)
            (root / "release_policy.d").mkdir()
            (root / "release_policy.d" / "bad.json").write_text('{"local_only": true}', encoding="utf-8")
            with self.assertRaises(ReleaseError):
                _load_policy(policy)

    def test_the_decisions_ship_in_the_wheel(self) -> None:
        self.assertIn('"release_policy.d/*.json"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"))


class ReleaseNotesFoldsRecordsTests(unittest.TestCase):
    def _repo(self, root: Path) -> None:
        (root / "changelog.d").mkdir()
        (root / "CHANGELOG.md").write_text("# Changelog\n\n## 9.9.9 (unreleased)\n", encoding="utf-8")
        (root / "MOD_CHANGELOG.md").write_bytes(BASE.encode("utf-8"))
        (root / "bridgeforge").mkdir()
        shutil.copy2(ROOT / "bridgeforge" / "release_policy.json", root / "bridgeforge" / "release_policy.json")
        mod_changelog.add_entry("Radar", "fixed the ring", day="2026-11-18", path=root / "MOD_CHANGELOG.md")
        record_policy_decision("newmod", local_only=True, reason="no licence", policy_path=root / "bridgeforge" / "release_policy.json")

    def _run(self, *argv: str) -> tuple[int, str]:
        from bridgeforge.cli import build_parser

        out = io.StringIO()
        with redirect_stdout(out):
            code = run_cli(build_parser().parse_args(["release-notes", *argv]))
        return code, out.getvalue()

    def test_check_lists_and_assemble_folds_the_records(self) -> None:
        with resolved_temp_dir() as root:
            self._repo(root)
            code, out = self._run("--check", "--root", str(root))
            self.assertEqual(code, 1)
            self.assertIn("1 pending mod-changelog.d fragment(s)", out)
            self.assertIn("1 pending bridgeforge/release_policy.d fragment(s)", out)
            code, out = self._run("assemble", "--root", str(root))
            self.assertEqual(code, 0, out)
            self.assertIn("- **Radar**: fixed the ring", (root / "MOD_CHANGELOG.md").read_text(encoding="utf-8"))
            self.assertIn("newmod", json.loads((root / "bridgeforge" / "release_policy.json").read_text(encoding="utf-8"))["mods"])
            code, out = self._run("--check", "--root", str(root))
            self.assertEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main()
