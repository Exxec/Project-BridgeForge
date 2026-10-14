"""Decision sheet with precedent (ROADMAP item 73, C1) and the precedent lookup it and packets share (C2)."""
from __future__ import annotations

import csv
import json
import unittest
from pathlib import Path
from unittest import mock

from bridgeforge.escalation_precedent import RULINGS_FILE, precedents, question_shape, standing_answer
from bridgeforge.escalation_sheet import COLUMNS, apply_sheet, build_sheet, read_sheet, write_sheet
from tests.support import resolved_temp_dir

FINDING = "settings-json-override-breadth"


def _explanation(count: int, key: str) -> str:
    return f"This mod's data/config/settings.json changes {count} value(s); first is \"{key}\" in data/config/{key}.json."


def _workspace(queue: Path, name: str, explanation: str, finding: str = FINDING, tier: str = "decision") -> None:
    reports = queue / name / "reports"
    (reports / "revive").mkdir(parents=True)
    (reports / "escalations").mkdir(parents=True)
    (queue / name / "working").mkdir()
    (reports / "revive" / "REVIVE.json").write_text(json.dumps({"status": "ESCALATED", "packets": [{"id": f"{finding}--mod", "finding": finding, "tier": tier, "kind": "owner"}]}), encoding="utf-8")
    packet = {"id": f"{finding}--mod", "finding": finding, "tier": tier, "kind": "owner",
              "findings": [{"id": finding, "file": "data/config/settings.json", "evidence": [f"overridden:{name}"], "explanation": explanation}]}
    (reports / "escalations" / f"{finding}--mod.json").write_text(json.dumps(packet), encoding="utf-8")


def _rulings(queue: Path, answers: list[str], finding: str = FINDING, reason: str = "tuning set is deliberate") -> None:
    lines = [json.dumps({"date": f"2026-10-0{n}", "finding": finding, "ruling": answer, "reason": reason, "mods": [f"Old{n}"]})
             for n, answer in enumerate(answers, 1)]
    (queue / RULINGS_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")


class ShapeTests(unittest.TestCase):
    def test_ids_paths_and_numbers_become_placeholders(self) -> None:
        a = question_shape(_explanation(12, "alpha_key"))
        b = question_shape(_explanation(300, "betaKey"))
        self.assertEqual(a, b)
        self.assertNotIn("12", a)
        self.assertNotEqual(a, question_shape("Something entirely different about a hull."))


class StandingAnswerTests(unittest.TestCase):
    def test_three_agreeing_prefill_but_two_or_a_dissent_do_not(self) -> None:
        entry = lambda answer: {"answer": answer, "reason": "r"}  # noqa: E731
        self.assertEqual(standing_answer([entry("accept")] * 3), {"answer": "accept", "reason": "r", "count": 3})
        self.assertIsNone(standing_answer([entry("accept")] * 2))
        self.assertIsNone(standing_answer([entry("accept")] * 3 + [entry("approve-fixer")]))


class SheetTests(unittest.TestCase):
    def test_groups_by_shape_and_lists_mods(self) -> None:
        with resolved_temp_dir() as queue:
            _workspace(queue, "A", _explanation(5, "one_key"))
            _workspace(queue, "B", _explanation(40, "twoKey"))
            _workspace(queue, "C", "A completely different question about this mod's stars.")
            rows = build_sheet(queue, quiet=True)
        self.assertEqual(len(rows), 2)
        self.assertEqual([r["mods"] for r in rows], ["A;B", "C"])
        self.assertEqual({r["prefilled"] for r in rows}, {"no"})
        self.assertEqual(tuple(rows[0]), COLUMNS)

    def test_prefill_only_with_three_agreeing_precedents(self) -> None:
        with resolved_temp_dir() as queue:
            _workspace(queue, "A", _explanation(5, "one_key"))
            _rulings(queue, ["accept", "accept"])
            two = build_sheet(queue, quiet=True)[0]
            _rulings(queue, ["accept", "accept", "accept"])
            three = build_sheet(queue, quiet=True)[0]
            _rulings(queue, ["accept", "accept", "approve-fixer"])
            split = build_sheet(queue, quiet=True)[0]
        self.assertEqual((two["prefilled"], two["answer"], two["precedent_count"]), ("no", "", 2))
        self.assertEqual((three["prefilled"], three["answer"], three["reason"], three["precedent_count"]), ("yes", "accept", "tuning set is deliberate", 3))
        self.assertEqual((split["prefilled"], split["answer"]), ("no", ""))

    def test_baseline_reasons_count_as_precedent_once(self) -> None:
        with resolved_temp_dir() as queue:
            _workspace(queue, "A", _explanation(5, "one_key"))
            for name in ("X", "Y", "Z"):
                reports = queue / name / "working" / "reports"
                reports.mkdir(parents=True)
                (reports / "baseline.json").write_text(json.dumps({"findings": [f"{FINDING}|f|e"], "reasons": {f"{FINDING}|f|e": "authored that way"},
                                                                  "stamp": {"version": "1", "date": "2026-10-01"}}), encoding="utf-8")
            # a ruling that already covers X's reason must not count twice
            (queue / RULINGS_FILE).write_text(json.dumps({"date": "2026-10-02", "finding": FINDING, "ruling": "accept", "reason": "authored that way", "mods": ["X"]}) + "\n", encoding="utf-8")
            found = precedents(queue, FINDING)
            row = build_sheet(queue, quiet=True)[0]
        self.assertEqual(len(found), 3)
        self.assertEqual((row["prefilled"], row["precedent_count"]), ("yes", 3))

    def test_write_sheet_round_trips_as_csv_and_leaves_no_checkpoint(self) -> None:
        with resolved_temp_dir() as queue:
            _workspace(queue, "A", _explanation(5, "one_key"))
            result = write_sheet(queue, queue / "SHEET.csv", quiet=True)
            rows = read_sheet(queue / "SHEET.csv")
            leftovers = sorted(p.name for p in queue.glob("*.partial.jsonl"))
        self.assertEqual((result["rows"], result["mods"]), (1, 1))
        self.assertEqual(rows[0]["finding"], FINDING)
        self.assertEqual(leftovers, [])

    def test_accepted_finding_is_not_asked_again(self) -> None:
        with resolved_temp_dir() as queue:
            _workspace(queue, "A", _explanation(5, "one_key"))
            reports = queue / "A" / "working" / "reports"
            reports.mkdir(parents=True)
            (reports / "baseline.json").write_text(json.dumps({"findings": [f"{FINDING}|data/config/settings.json|overridden:A"]}), encoding="utf-8")
            self.assertEqual(build_sheet(queue, quiet=True), [])


class ApplyTests(unittest.TestCase):
    def _sheet(self, queue: Path, rows: list[dict]) -> Path:
        path = queue / "SHEET.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=COLUMNS)
            writer.writeheader()
            for row in rows:
                writer.writerow({**{c: "" for c in COLUMNS}, "queue": str(queue), **row})
        return path

    def test_apply_calls_rule_once_per_answered_row_and_never_for_skip(self) -> None:
        with resolved_temp_dir() as queue:
            sheet = self._sheet(queue, [
                {"group": "G001", "finding": "a-id", "shape": "s1", "mods": "A;B", "answer": "accept", "reason": "authored"},
                {"group": "G002", "finding": "b-id", "shape": "s2", "mods": "C", "answer": "skip", "reason": "later"},
                {"group": "G003", "finding": "c-id", "shape": "s3", "mods": "D", "answer": "", "reason": ""},
                {"group": "G004", "finding": "d-id", "shape": "s4", "mods": "E", "answer": "approve-fixer", "reason": "trim"}])
            with mock.patch("bridgeforge.escalation_queue.rule", return_value={"ruling": "x", "mods": []}) as rule:
                result = apply_sheet(sheet)
        self.assertEqual(rule.call_count, 2)
        first = rule.call_args_list[0]
        self.assertEqual((first.args[1], first.kwargs["accept"], first.kwargs["only_mods"], first.kwargs["shape"]), ("a-id", True, {"A", "B"}, "s1"))
        self.assertTrue(rule.call_args_list[1].kwargs["approve_fixer"])
        self.assertEqual(result["skipped"], ["G002", "G003"])

    def test_prefilled_row_unchanged_or_confirmed_is_logged_as_standing_changed_is_the_owners(self) -> None:
        base = {"finding": "a-id", "shape": "s", "mods": "A", "prefilled": "yes", "precedent_count": "4", "precedent_answer": "accept", "precedent_reason": "same as before"}
        with resolved_temp_dir() as queue:
            sheet = self._sheet(queue, [
                {**base, "group": "G001", "answer": "accept", "reason": "same as before"},
                {**base, "group": "G002", "answer": "accept", "reason": "my own words", "confirm": "yes"},
                {**base, "group": "G003", "answer": "accept", "reason": "my own words"},
                {**base, "group": "G004", "answer": "approve-fixer", "reason": "different"},
                {**base, "group": "G005", "answer": "", "reason": ""}])
            with mock.patch("bridgeforge.escalation_queue.rule", return_value={"ruling": "x", "mods": []}) as rule:
                apply_sheet(sheet)
        reasons = [c.kwargs["reason"] for c in rule.call_args_list]
        self.assertEqual(reasons, ["same as before (standing approval from 4 prior rulings)", "my own words (standing approval from 4 prior rulings)",
                                   "my own words", "different"])

    def test_apply_reports_a_rule_error_and_keeps_going(self) -> None:
        with resolved_temp_dir() as queue:
            sheet = self._sheet(queue, [{"group": "G001", "finding": "a-id", "mods": "A", "answer": "approve-fixer", "reason": "r"},
                                        {"group": "G002", "finding": "b-id", "mods": "B", "answer": "bogus", "reason": "r"}])
            result = apply_sheet(sheet)
        self.assertEqual([e["group"] for e in result["errors"]], ["G001", "G002"])

    def test_rule_narrowed_by_mods_and_shape_end_to_end(self) -> None:
        from bridgeforge.escalation_queue import rule

        with resolved_temp_dir() as queue:
            _workspace(queue, "A", _explanation(5, "one_key"))
            _workspace(queue, "B", _explanation(5, "one_key"))
            shape = question_shape(_explanation(5, "one_key"))
            entry = rule(queue, FINDING, accept=True, reason="authored", only_mods={"A"}, shape=shape, today="2026-10-14")
            none = rule(queue, FINDING, accept=True, reason="authored", only_mods={"B"}, shape="another shape", today="2026-10-14")
            baseline = json.loads((queue / "A" / "working" / "reports" / "baseline.json").read_text(encoding="utf-8"))
            b_exists = (queue / "B" / "working" / "reports" / "baseline.json").exists()
        self.assertEqual((entry["mods"], none["mods"], b_exists), (["A"], [], False))
        self.assertEqual(list(baseline["reasons"].values()), ["authored"])


if __name__ == "__main__":
    unittest.main()
