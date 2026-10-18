"""ROADMAP item 75 R8: a snapshot restores only into a new isolated folder and is proven by hashes, never claimed recoverable offline."""
from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from bridgeforge.cli import main
from bridgeforge.snapshot_restore import MANIFEST_DIR, MANIFEST_NAME, RestoreRefused, restore_check
from bridgeforge.state_snapshot import take_snapshot
from tests.support import link_dir, resolved_temp_dir
from tests.test_state_snapshot import _tree


def _snapshot(base: Path) -> tuple[Path, Path]:
    root, dest = _tree(base / "repo"), base / "backup"
    take_snapshot(root, dest, base / "home", quiet=True, stamp="s1")
    return root, dest


class RestoreTests(unittest.TestCase):
    def test_safe_restore_verifies_hashes_and_keeps_verdicts_apart(self) -> None:
        with resolved_temp_dir() as base:
            root, snap = _snapshot(base)
            result = restore_check(snap, base / "restored", source_root=root, quiet=True)
            self.assertEqual(result["verdict"], "RESTORED_OFFLINE")
            self.assertFalse(result["recoverable"])
            self.assertEqual(result["rig_scenario"]["status"], "LIVE_PENDING")
            self.assertEqual(result["environment"]["status"], "NOT_RECONSTRUCTED")
            self.assertEqual((result["hashes"]["files"], result["hashes"]["verified"]), (3, 3))
            self.assertEqual((base / "restored" / "Done" / "ModA" / "a.txt").read_text(encoding="utf-8"), "one")
            manifest = json.loads((base / "restored" / MANIFEST_DIR / MANIFEST_NAME).read_text(encoding="utf-8"))
            self.assertEqual(manifest["snapshot"]["stamp"], "s1")
            self.assertEqual(manifest["snapshot"]["snapshot_format"], 1)
            self.assertIn("In operation/W1/working", manifest["required_state"])
            self.assertFalse((base / "restored.bfrestore-staging").exists())
            self.assertFalse((base / "restored.restore.partial.jsonl").exists())

    def test_an_existing_empty_destination_is_accepted(self) -> None:
        with resolved_temp_dir() as base:
            root, snap = _snapshot(base)
            (base / "empty").mkdir()
            self.assertEqual(restore_check(snap, base / "empty", source_root=root, quiet=True)["verdict"], "RESTORED_OFFLINE")

    def test_unsafe_destinations_are_refused_and_nothing_is_written(self) -> None:
        with resolved_temp_dir() as base:
            root, snap = _snapshot(base)
            (base / "populated").mkdir()
            (base / "populated" / "keep.txt").write_text("mine", encoding="utf-8")
            (base / "elsewhere").mkdir()
            link_dir(base / "elsewhere", base / "link")
            forbidden = base / "install"
            forbidden.mkdir()
            cases = {
                "traversal": Path(str(base / "x" / ".." / "y")),
                "same as snapshot": snap,
                "inside snapshot": snap / "current" / "again",
                "around snapshot": base,
                "same as source": root,
                "inside source": root / "Done" / "new",
                "populated": base / "populated",
                "junction itself": base / "link",
                "through a junction": base / "link" / "child",
                "forbidden root": forbidden / "child",
            }
            for label, destination in cases.items():
                with self.subTest(label), self.assertRaises(RestoreRefused):
                    restore_check(snap, destination, source_root=root, forbid=[forbidden], quiet=True)
            self.assertEqual((base / "populated" / "keep.txt").read_text(encoding="utf-8"), "mine")
            self.assertEqual(list((base / "elsewhere").iterdir()), [])

    def test_bad_snapshots_are_refused(self) -> None:
        def broken(mutate) -> Path:
            with_base = resolved_temp_dir()
            self.addCleanup(with_base.__exit__, None, None, None)
            base = with_base.__enter__()
            _, snap = _snapshot(base)
            mutate(snap)
            return snap

        identity = lambda snap: snap / "snapshot-s1.json"  # noqa: E731
        edit = lambda snap, **kw: identity(snap).write_text(json.dumps({**json.loads(identity(snap).read_text(encoding="utf-8")), **kw}), encoding="utf-8")  # noqa: E731
        cases = {
            "no identity file": lambda s: identity(s).unlink(),
            "corrupt identity": lambda s: identity(s).write_text("{not json", encoding="utf-8"),
            "wrong format version": lambda s: edit(s, snapshot_format=99),
            "renamed identity": lambda s: identity(s).rename(s / "snapshot-other.json"),
            "recorded errors": lambda s: edit(s, errors=["x: failed"]),
            "unfinished run": lambda s: (s / "snapshot.partial.jsonl").write_text("{}\n", encoding="utf-8"),
            "missing required state": lambda s: __import__("shutil").rmtree(s / "current" / "bridgeforge-state"),
            "no current": lambda s: __import__("shutil").rmtree(s / "current"),
        }
        for label, mutate in cases.items():
            snap = broken(mutate)
            with self.subTest(label), self.assertRaises(RestoreRefused):
                restore_check(snap, snap.parent / "out", quiet=True)
            self.assertFalse((snap.parent / "out").exists())

    def test_a_link_inside_the_snapshot_is_refused(self) -> None:
        with resolved_temp_dir() as base:
            root, snap = _snapshot(base)
            (base / "outside").mkdir()
            (base / "outside" / "secret.txt").write_text("s", encoding="utf-8")
            link_dir(base / "outside", snap / "current" / "Done" / "escape")
            with self.assertRaises(RestoreRefused):
                restore_check(snap, base / "restored", source_root=root, quiet=True)
            self.assertFalse((base / "restored").exists())

    def test_corruption_since_an_earlier_manifest_fails_the_check(self) -> None:
        with resolved_temp_dir() as base:
            root, snap = _snapshot(base)
            restore_check(snap, base / "r1", source_root=root, quiet=True)
            earlier = base / "r1" / MANIFEST_DIR / MANIFEST_NAME
            (snap / "current" / "Done" / "ModA" / "a.txt").write_text("rot", encoding="utf-8")
            second = restore_check(snap, base / "r2", source_root=root, compare_to=earlier, quiet=True)
            self.assertEqual(second["verdict"], "FAIL")
            self.assertTrue(any("a.txt" in problem for problem in second["hashes"]["problems"]))

    def test_unusable_restored_layout_fails_the_status_check(self) -> None:
        with resolved_temp_dir() as base:
            root, snap = _snapshot(base)
            (snap / "current" / "bridgeforge-state" / "s.json").write_text("{broken", encoding="utf-8")
            result = restore_check(snap, base / "restored", source_root=root, quiet=True)
            self.assertEqual((result["verdict"], result["status_check"]["status"]), ("FAIL", "FAIL"))

    def test_cli_reports_exit_codes_and_progress(self) -> None:
        with resolved_temp_dir() as base:
            root, snap = _snapshot(base)
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = main(["snapshot-restore-check", str(snap), "--to", str(base / "restored"), "--source-root", str(root)])
            self.assertEqual(code, 0)
            self.assertIn("RESTORED_OFFLINE", out.getvalue())
            self.assertIn("[1/3] hash Done:", err.getvalue())
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(main(["snapshot-restore-check", str(snap), "--to", str(base / "restored"), "--source-root", str(root)]), 2)


if __name__ == "__main__":
    unittest.main()
