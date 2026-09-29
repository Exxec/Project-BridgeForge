"""`bridgeforge revive-queue` (ROADMAP P15 item 31.2): revive across a queue, filtered, resumable."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from bridgeforge.revive_queue import CHECKPOINT_FILE, RESULT_FILE, revive_queue
from tests.support import resolved_temp_dir


def _workspace(queue: Path, name: str, status: str | None) -> None:
    (queue / name / "working").mkdir(parents=True)
    (queue / name / "working" / "mod_info.json").write_text('{"id": "%s"}' % name, encoding="utf-8")
    if status:
        (queue / name / "reports" / "revive").mkdir(parents=True)
        (queue / name / "reports" / "revive" / "REVIVE.json").write_text(json.dumps({"status": status}), encoding="utf-8")


class ReviveQueueTests(unittest.TestCase):
    def test_filters_and_resumes_from_the_checkpoint(self) -> None:
        calls = []

        def fake(workspace, **_kwargs):
            calls.append(workspace.name)
            if workspace.name == "B" and calls.count("B") == 1:
                raise KeyboardInterrupt  # interrupted mid-run
            return {"status": "UNATTENDED_DONE", "packets": []}

        with resolved_temp_dir() as queue:
            _workspace(queue, "A", "ESCALATED")
            _workspace(queue, "B", "ESCALATED")
            _workspace(queue, "C", "UNATTENDED_DONE")
            _workspace(queue, "D", None)
            with self.assertRaises(KeyboardInterrupt):
                revive_queue(queue, only_status={"ESCALATED"}, quiet=True, revive_one=fake)
            result = revive_queue(queue, only_status={"ESCALATED"}, quiet=True, revive_one=fake)
            never = revive_queue(queue, never_revived=True, quiet=True, revive_one=fake)
            written = json.loads((queue / RESULT_FILE).read_text(encoding="utf-8"))
            checkpoint_left = (queue / CHECKPOINT_FILE).exists()
        self.assertEqual(calls, ["A", "B", "B", "D"])  # A was not revived again after the interruption
        self.assertEqual([m["workspace"] for m in result["mods"]], ["A", "B"])
        self.assertEqual([m["workspace"] for m in never["mods"]], ["D"])
        self.assertEqual(written["counts"], {"UNATTENDED_DONE": 1})
        self.assertFalse(checkpoint_left)


if __name__ == "__main__":
    unittest.main()
