"""probe-group live-queue (ROADMAP-3 95.3): a plan's groups installed, played, judged and, with --archive, recorded in order."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from bridgeforge.live_queue import CONFIG_RELATIVE, live_queue
from tests.support import resolved_temp_dir


class LiveQueueTests(unittest.TestCase):
    PLAN = {"groups": [{"group": 1, "members": [{"workspace": "Vayra"}, {"workspace": "Yunru"}]},
                       {"group": 2, "members": [{"workspace": "BrokenStar"}]},
                       {"group": 3, "members": [{"workspace": "Other"}]}]}

    def _run(self, root: Path, outcomes: dict[int, str], verdicts: dict[str, str] | None = None, **options):
        """Run the queue with stand-ins; `outcomes` maps a group number to its live verdict (LIVE_DONE or LIVE_STUCK)."""
        rig = root / "rig"
        (rig / CONFIG_RELATIVE).parent.mkdir(parents=True, exist_ok=True)
        (rig / CONFIG_RELATIVE).write_text("{}", encoding="utf-8")
        plan = root / "plan.json"
        plan.write_text(json.dumps(self.PLAN), encoding="utf-8")
        calls: list[tuple] = []
        installed: list[int] = []

        def install(_plan, number):
            installed.append(number)
            calls.append(("install", number))

        def play(_rig, test_id):
            number = installed[-1]
            log = root / f"{test_id}.stdout.log"
            log.write_text("log\n", encoding="utf-8")
            calls.append(("play", test_id))
            verdict = outcomes.get(number, "LIVE_DONE")
            return SimpleNamespace(verdict=verdict, stage=None if verdict == "LIVE_DONE" else "combat-round-1", detail="d", log=str(log))

        def judge(_log, _config):
            members = [m["workspace"] for g in self.PLAN["groups"] if g["group"] == installed[-1] for m in g["members"]]
            return {"members": {m: {"verdict": (verdicts or {}).get(m, "PASS")} for m in members}}

        def record(_log, _config, test_id):
            calls.append(("record", test_id))
            members = [m["workspace"] for g in self.PLAN["groups"] if g["group"] == installed[-1] for m in g["members"]]
            passed = [m for m in members if (verdicts or {}).get(m, "PASS") == "PASS"]
            return {"recorded": passed, "archived": passed, "skipped": [{"mod_id": m, "verdict": (verdicts or {}).get(m)} for m in members if m not in passed]}

        out = root / "out" / "lq.json"
        result = live_queue(plan, root, rig, out, play=play, install=install, judge=judge, record=record, quiet=True,
                            test_prefix="LQ", **options)
        return result, calls, out

    def test_passing_groups_are_archived_and_a_stuck_one_is_not(self) -> None:
        with resolved_temp_dir() as root:
            result, calls, out = self._run(root, {2: "LIVE_STUCK"}, archive=True)
            written = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual([c for c in calls if c[0] == "record"], [("record", "LQ-G1"), ("record", "LQ-G3")])
        rows = {r["group"]: r for r in result["groups"]}
        self.assertEqual(rows[1]["archived"], ["Vayra", "Yunru"])
        self.assertNotIn("archived", rows[2])
        self.assertEqual(rows[2]["triage"]["log"], str(root / "LQ-G2.stdout.log"))
        self.assertEqual([r["group"] for r in result["attention"]], [2])
        self.assertEqual(written["groups"], result["groups"])

    def test_without_archive_nothing_is_recorded(self) -> None:
        with resolved_temp_dir() as root:
            result, calls, _ = self._run(root, {})
        self.assertFalse([c for c in calls if c[0] == "record"])
        self.assertEqual(result["groups"][0]["verdicts"], {"Vayra": "PASS", "Yunru": "PASS"})

    def test_a_failing_member_is_left_out_and_listed(self) -> None:
        with resolved_temp_dir() as root:
            result, _, _ = self._run(root, {}, verdicts={"Yunru": "FAIL"}, archive=True, groups=[1])
        row = result["groups"][0]
        self.assertEqual((row["archived"], row["not_recorded"]), (["Vayra"], [{"mod_id": "Yunru", "verdict": "FAIL"}]))
        self.assertEqual([r["group"] for r in result["attention"]], [1])

    def test_a_pass_left_unarchived_is_listed_with_why(self) -> None:
        # Vayra's Sector, 2026-11-19: PASS live, then record stopped on an uncovered caught exception, and archive on
        # unexplained shipped files. A PASS is not done until it is archived.
        with resolved_temp_dir() as root:
            rig = root / "rig"
            (rig / CONFIG_RELATIVE).parent.mkdir(parents=True)
            (rig / CONFIG_RELATIVE).write_text("{}", encoding="utf-8")
            plan = root / "plan.json"
            plan.write_text(json.dumps({"groups": [self.PLAN["groups"][0]]}), encoding="utf-8")
            log = root / "x.log"
            log.write_text("x", encoding="utf-8")

            def record(_log, _config, _test_id):
                return {"recorded": ["Vayra", "Yunru"], "archived": ["Yunru"],
                        "skipped": [{"mod_id": "vayrasector", "verdict": "PASS", "archive": "shipped-copy audit FAIL: a.csv"}]}

            result = live_queue(plan, root, rig, root / "lq.json", archive=True, quiet=True, test_prefix="LQ",
                                install=lambda *_: None,
                                play=lambda *_: SimpleNamespace(verdict="LIVE_DONE", stage=None, detail=None, log=str(log)),
                                judge=lambda *_: {"members": {"Vayra": {"verdict": "PASS"}, "Yunru": {"verdict": "PASS"}}},
                                record=record)
        self.assertEqual([r["group"] for r in result["attention"]], [1])
        self.assertIn("not archived: vayrasector (shipped-copy audit FAIL: a.csv)", result["groups"][0]["summary"])

    def test_only_the_chosen_groups_run(self) -> None:
        with resolved_temp_dir() as root:
            _, calls, _ = self._run(root, {}, groups=[2, 3])
        self.assertEqual([c[1] for c in calls if c[0] == "install"], [2, 3])

    def test_an_interrupted_queue_resumes_after_its_last_finished_group(self) -> None:
        with resolved_temp_dir() as root:
            rig = root / "rig"
            (rig / CONFIG_RELATIVE).parent.mkdir(parents=True)
            (rig / CONFIG_RELATIVE).write_text("{}", encoding="utf-8")
            plan = root / "plan.json"
            plan.write_text(json.dumps(self.PLAN), encoding="utf-8")
            out = root / "lq.json"
            played: list[str] = []
            interrupt_at = {2}

            def install(_plan, number):
                if number in interrupt_at:
                    raise KeyboardInterrupt  # the operator stops the queue; not caught like a group's own error

            def play(_rig, test_id):
                played.append(test_id)
                return SimpleNamespace(verdict="LIVE_STUCK", stage="main-menu", detail="d", log=None)

            kwargs = dict(install=install, play=play, judge=None, record=None, quiet=True, test_prefix="LQ")
            with self.assertRaises(KeyboardInterrupt):
                live_queue(plan, root, rig, out, **kwargs)
            self.assertTrue(out.with_name("lq.partial.jsonl").is_file())
            interrupt_at.clear()
            result = live_queue(plan, root, rig, out, **kwargs)
            self.assertFalse(out.with_name("lq.partial.jsonl").exists())  # removed once the summary is written
        self.assertEqual(played, ["LQ-G1", "LQ-G2", "LQ-G3"])  # group 1 played once, then taken from the checkpoint
        self.assertEqual([r["group"] for r in result["groups"]], [1, 2, 3])

    def test_a_group_that_errors_does_not_stop_the_queue(self) -> None:
        with resolved_temp_dir() as root:
            rig = root / "rig"
            (rig / CONFIG_RELATIVE).parent.mkdir(parents=True)
            (rig / CONFIG_RELATIVE).write_text("{}", encoding="utf-8")
            plan = root / "plan.json"
            plan.write_text(json.dumps(self.PLAN), encoding="utf-8")
            played: list[str] = []

            def install(_plan, number):
                if number == 1:
                    raise RuntimeError("provider missing")

            def play(_rig, test_id):
                played.append(test_id)
                return SimpleNamespace(verdict="LIVE_STUCK", stage="main-menu", detail="d", log=None)

            result = live_queue(plan, root, rig, root / "lq.json", install=install, play=play, judge=None, record=None,
                                quiet=True, test_prefix="LQ")
        self.assertEqual(result["groups"][0]["error"], "RuntimeError: provider missing")
        self.assertEqual(played, ["LQ-G2", "LQ-G3"])


if __name__ == "__main__":
    unittest.main()
