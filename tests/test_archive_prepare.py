"""ROADMAP-3 96.6: `archive` does what `probe-group record --archive` does before it archives. On 2026-11-17 all four plain archives
were refused, for differences `audit-explain --auto` then proved and for want of the licence decision the owner's standing rule
gives; Eridani Combine's translation went unproven because translate-batch kept its records in scratch/translate-work/."""
from __future__ import annotations

import io
import json
import shutil
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from bridgeforge.cli import main
from bridgeforge.live.live_trust import auto_explain_shipped, shipped_hash
from bridgeforge.release import record_policy_decision
from tests.support import resolved_temp_dir

REPO_POLICY = Path(__file__).resolve().parent.parent / "bridgeforge" / "release_policy.json"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _workspace(root: Path, *, unexplained: bool = False) -> Path:
    """A revival whose only difference from the original is the credits file BridgeForge adds (and, with `unexplained`, an
    edited CSV nothing explains), with a CURRENT live result."""
    ws = root / "In operation" / "Radar"
    original = ws / "original" / "Radar 3.0"
    _write(original / "mod_info.json", '{"id": "bf_fixture_radar", "name": "Radar", "author": "LazyWizard", "version": "3.0"}')
    _write(original / "data" / "campaign" / "rules.csv", "id,trigger\nr1,OpenCommLink\n")
    shutil.copytree(original, ws / "working")
    _write(ws / "working" / "BRIDGEFORGE_CREDITS.txt", "Radar: BridgeForge revival credits\n")
    _write(ws / "working" / "reports" / "REVIVAL_REPORT.md", "# Report\n\nLIVE_VALIDATED\n")
    if unexplained:
        _write(ws / "working" / "data" / "campaign" / "rules.csv", "id,trigger\nr1,SomethingElse\n")
    line = {"test_id": "T1", "date": "2026-11-17", "verdict": "PASS", "shipped_sha256": shipped_hash(ws / "working"), "version": "3.0"}
    _write(ws / "reports" / "live_runs.jsonl", json.dumps(line) + "\n")
    return ws


def _policy(root: Path) -> Path:
    policy = root / "policy.json"
    shutil.copy2(REPO_POLICY, policy)
    return policy


def _archive(root: Path, ws: Path, policy: Path) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(["archive", str(ws), "--done", str(root / "Done"), "--policy", str(policy)])
    return code, out.getvalue(), err.getvalue()


class PlainArchiveTests(unittest.TestCase):
    def test_a_proven_difference_and_no_licence_decision_no_longer_stop_a_plain_archive(self) -> None:
        with resolved_temp_dir() as root:
            ws, policy = _workspace(root), _policy(root)
            code, out, err = _archive(root, ws, policy)
            entry = json.loads(policy.read_text(encoding="utf-8"))["mods"].get("bf_fixture_radar")
            shipped = json.loads((ws / "reports" / "SHIPPED_CHANGES.json").read_text(encoding="utf-8"))["files"]
            archived = (root / "Done" / "Radar" / "ARCHIVE_NOTE.md").is_file()
        self.assertEqual(code, 0, err)
        self.assertTrue(archived)
        self.assertIn("auto-explained 1 file(s): revival credits file added by BridgeForge", out)
        self.assertIn("BRIDGEFORGE_CREDITS.txt", shipped)
        self.assertTrue(entry["local_only"])
        self.assertIn("live-validated 2026-11-17", entry["reason"])
        self.assertIn("owner decision 2026-09-27", entry["reason"])
        self.assertIn("Licence: LOCAL_ONLY recorded", out)

    def test_a_decision_already_recorded_is_kept(self) -> None:
        with resolved_temp_dir() as root:
            ws, policy = _workspace(root), _policy(root)
            record_policy_decision("bf_fixture_radar", local_only=False, reason="the author's open licence (forum post)", policy_path=policy)
            code, out, err = _archive(root, ws, policy)
            entry = json.loads(policy.read_text(encoding="utf-8"))["mods"]["bf_fixture_radar"]
        self.assertEqual(code, 0, err)
        self.assertEqual((entry["local_only"], entry["reason"]), (False, "the author's open licence (forum post)"))
        self.assertNotIn("Licence: LOCAL_ONLY recorded", out)

    def test_a_refused_archive_records_no_licence_and_names_what_it_proved(self) -> None:
        with resolved_temp_dir() as root:
            ws, policy = _workspace(root, unexplained=True), _policy(root)
            code, _out, err = _archive(root, ws, policy)
            entry = json.loads(policy.read_text(encoding="utf-8"))["mods"].get("bf_fixture_radar")
            archived = (root / "Done" / "Radar").exists()
        self.assertEqual(code, 2)
        self.assertFalse(archived)
        self.assertIsNone(entry)
        self.assertIn("data/campaign/rules.csv", err)
        self.assertIn("proven and recorded: 1 file(s): revival credits file added by BridgeForge", err)
        self.assertIn("explain the rest with", err)

    def test_a_refusal_after_the_gate_leaves_the_policy_as_it_was(self) -> None:
        # Review 2026-11-17: the decision was written before archive_mod's own refusals, here an existing Done/<Mod>.
        with resolved_temp_dir() as root:
            ws, policy = _workspace(root), _policy(root)
            _write(root / "Done" / "Radar" / "ARCHIVE_NOTE.md", "# Radar 3.0: archive note\n")
            before = policy.read_bytes()
            code, _out, err = _archive(root, ws, policy)
            after = policy.read_bytes()
        self.assertEqual(code, 2, err)
        self.assertEqual(after, before)

    def test_a_waived_live_result_gets_no_standing_decision(self) -> None:
        # The standing reason says "live-validated <date>"; a waiver has no run date to give it (review 2026-11-17).
        with resolved_temp_dir() as root:
            ws, policy = _workspace(root), _policy(root)
            (ws / "reports" / "live_runs.jsonl").unlink()
            _write(ws / "reports" / "SHIPPED_CHANGES.json", json.dumps({"schema_version": 1, "files": {},
                                                                          "live": {"reason": "validated before run records existed", "date": "2026-10-01"}}))
            before = policy.read_bytes()
            code, _out, err = _archive(root, ws, policy)
            after = policy.read_bytes()
        self.assertEqual(code, 2)
        self.assertIn("no licence decision", err)
        self.assertEqual(after, before)

    def test_an_unreadable_record_refuses_without_a_traceback(self) -> None:
        with resolved_temp_dir() as root:
            ws, policy = _workspace(root), _policy(root)
            _write(ws / "reports" / "SHIPPED_CHANGES.json", "{not json")
            code, _out, err = _archive(root, ws, policy)
        self.assertEqual(code, 2)
        self.assertIn("archive refused", err)
        self.assertNotIn("Traceback", err)

    def test_a_recorded_decision_is_written_with_lf(self) -> None:
        with resolved_temp_dir() as root:
            policy = _policy(root)
            record_policy_decision("bf_fixture_radar", local_only=True, reason="author unreachable", policy_path=policy)
            self.assertNotIn(b"\r\n", policy.read_bytes())


class TranslateBatchProofTests(unittest.TestCase):
    def test_a_translate_batch_work_folder_proves_a_translation(self) -> None:
        with resolved_temp_dir() as root:
            ws = root / "In operation" / "Eri"
            original = ws / "original" / "Eri 1"
            _write(original / "mod_info.json", '{"id": "eri", "name": "Eri", "version": "1"}')
            _write(original / "data" / "variants" / "x.variant", '{"displayName":"鱼雷轰炸机","hullId":"x"}')
            shutil.copytree(original, ws / "working")
            _write(ws / "working" / "data" / "variants" / "x.variant", '{"displayName":"Torpedo Bomber","hullId":"x"}')
            export = {"schema_version": 1, "mode": "TRANSLATION_EXPORT", "entries": [{"source": "鱼雷轰炸机", "translation": "Torpedo Bomber"}]}
            _write(ws / "scratch" / "translate-work" / "export.json", json.dumps(export, ensure_ascii=False))
            _write(ws / "scratch" / "translate-work" / "translations.json", json.dumps(export, ensure_ascii=False))
            _write(ws / "scratch" / "other" / "export.json", json.dumps({"mode": "SOMETHING_ELSE"}))
            groups = auto_explain_shipped(ws)
            copied = sorted(p.name for p in (ws / "reports" / "translation").iterdir())
        self.assertEqual(copied, ["translate-work-export.json", "translate-work-translations.json"])
        proven = {file: reason for reason, files in groups.items() for file in files}
        self.assertIn("translation", proven["data/variants/x.variant"])

    def test_a_translation_record_proves_nothing_but_a_translation(self) -> None:
        # Review 2026-11-17: an aborted translate-batch leaves export.json only, and the proof was CJK counts alone. A CSV that
        # lost a Chinese row and a jar with fewer CJK-looking bytes passed as translations.
        with resolved_temp_dir() as root:
            ws = root / "In operation" / "Eri"
            original = ws / "original" / "Eri 1"
            _write(original / "mod_info.json", '{"id": "eri", "name": "Eri", "version": "1"}')
            _write(original / "data" / "strings" / "names.csv", "id,name\na,鱼雷\nb,轰炸机\n")
            _write(original / "data" / "variants" / "x.variant", '{"displayName":"鱼雷轰炸机","hullId":"x"}')
            _write(original / "jars" / "x.jar", "PK 鱼雷轰炸机鱼雷轰炸机")
            shutil.copytree(original, ws / "working")
            _write(ws / "working" / "data" / "strings" / "names.csv", "id,name\na,鱼雷\n")  # a row lost, not translated
            _write(ws / "working" / "data" / "variants" / "x.variant", '{"displayName":"Torpedo Bomber","hullId":"y"}')  # an id changed too
            _write(ws / "working" / "jars" / "x.jar", "PK changed by hand")
            _write(ws / "scratch" / "translate-work" / "export.json", json.dumps({"schema_version": 1, "mode": "TRANSLATION_EXPORT", "entries": []}))
            groups = auto_explain_shipped(ws)
        proven = {file for files in groups.values() for file in files}
        self.assertEqual(proven & {"data/strings/names.csv", "data/variants/x.variant", "jars/x.jar"}, set())


if __name__ == "__main__":
    unittest.main()
