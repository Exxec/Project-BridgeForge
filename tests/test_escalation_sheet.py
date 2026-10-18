"""Decision sheet with precedent (ROADMAP item 73, C1) and the precedent lookup it and packets share (C2)."""
from __future__ import annotations

import csv
import json
import unittest
from pathlib import Path
from unittest import mock

from bridgeforge.escalation_precedent import RULINGS_FILE, precedents, question_shape, standing_answer, standing_eligibility
from bridgeforge.escalation_sheet import COLUMNS, apply_sheet, build_sheet, read_sheet, write_sheet
from tests.support import resolved_temp_dir

FINDING = "settings-json-override-breadth"


def _explanation(count: int, key: str) -> str:
    return f"This mod's data/config/settings.json changes {count} value(s); first is \"{key}\" in data/config/{key}.json."


def _workspace(queue: Path, name: str, explanation: str, finding: str = FINDING, tier: str = "decision",
               evidence: list[str] | None = None, classification: str = "REVIEW") -> None:
    reports = queue / name / "reports"
    (reports / "revive").mkdir(parents=True)
    (reports / "escalations").mkdir(parents=True)
    (queue / name / "working").mkdir()
    (reports / "revive" / "REVIVE.json").write_text(json.dumps({"status": "ESCALATED", "packets": [{"id": f"{finding}--mod", "finding": finding, "tier": tier, "kind": "owner"}]}), encoding="utf-8")
    packet = {"id": f"{finding}--mod", "finding": finding, "tier": tier, "kind": "owner",
              "findings": [{"id": finding, "file": "data/config/settings.json", "evidence": evidence or [f"overridden:{name}"],
                              "classification": classification, "explanation": explanation}]}
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

    def test_an_untouched_suggestion_is_not_an_approval(self) -> None:
        # R4: only an edited or confirm=yes row counts as answered.
        base = {"finding": "a-id", "shape": "s", "mods": "A", "prefilled": "yes", "precedent_count": "4", "precedent_answer": "accept", "precedent_reason": "same as before"}
        with resolved_temp_dir() as queue:
            sheet = self._sheet(queue, [
                {**base, "group": "G001", "answer": "accept", "reason": "same as before"},
                {**base, "group": "G002", "answer": "accept", "reason": "same as before", "confirm": "yes"},
                {**base, "group": "G003", "answer": "accept", "reason": "my own words"},
                {**base, "group": "G004", "answer": "approve-fixer", "reason": "different"},
                {**base, "group": "G005", "answer": "", "reason": ""}])
            with mock.patch("bridgeforge.escalation_queue.rule", return_value={"ruling": "x", "mods": []}) as rule:
                result = apply_sheet(sheet)
        self.assertEqual([c.kwargs["reason"] for c in rule.call_args_list], ["same as before", "my own words", "different"])
        self.assertEqual(result["skipped"], ["G001", "G005"])

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


EVIDENCE = ["provider:magiclib", "key:xpGainMult"]


def _finding(evidence: list[str] | None = None, classification: str = "REVIEW", finding: str = FINDING, category: str = "metadata") -> dict:
    return {"id": finding, "classification": classification, "category": category, "evidence": evidence or EVIDENCE}


def _source(queue: Path, mods: list[str], *, evidence: list[str] | None = None, intent: str = "authored tuning set", operation: str = "accept",
            reason: str = "deliberate", finding: str = FINDING, extra_predicate: dict | None = None, date: str = "2026-10-01") -> str:
    from bridgeforge.escalation_precedent import predicate_hash, question_predicate, ruling_id

    predicate = {**question_predicate([_finding(evidence, finding=finding)]), **(extra_predicate or {})}
    entry = {"date": date, "finding": finding, "ruling": operation, "reason": reason, "mods": mods, "predicate": predicate,
             "predicate_hash": predicate_hash(predicate), "intent": intent}
    entry["id"] = ruling_id(entry)
    with (queue / RULINGS_FILE).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")
    return entry["id"]


class StandingRulingTests(unittest.TestCase):
    """R4: a standing ruling needs three independent mods on the same versioned predicate."""

    def _eligible(self, queue: Path, findings: list[dict] | None = None, mod: str = "T"):
        from bridgeforge.escalation_precedent import standing_eligibility

        return standing_eligibility(queue, findings or [_finding()], mod)

    def test_three_independent_mods_with_the_same_predicate_are_eligible(self) -> None:
        with resolved_temp_dir() as queue:
            _source(queue, ["S1"])
            _source(queue, ["S2"], reason="other words")
            two = self._eligible(queue)
            _source(queue, ["S3"])
            three = self._eligible(queue)
        self.assertFalse(two["eligible"])
        self.assertIn("2 independent prior mod(s)", two["reasons"][0])
        self.assertTrue(three["eligible"])
        self.assertEqual(three["independent_mods"], ["S1", "S2", "S3"])
        self.assertEqual(len(three["sources"]), 3)

    def test_repeated_rulings_for_one_mod_are_one_mod(self) -> None:
        with resolved_temp_dir() as queue:
            for day in ("2026-10-01", "2026-10-02", "2026-10-03"):
                _source(queue, ["S1"], date=day)
            verdict = self._eligible(queue)
        self.assertFalse(verdict["eligible"])
        self.assertIn("1 independent prior mod(s)", verdict["reasons"][0])

    def test_superficially_similar_questions_do_not_share_approval(self) -> None:
        # Same finding id and the same question text, but another provider and key: a different predicate.
        with resolved_temp_dir() as queue:
            for mod in ("S1", "S2", "S3"):
                _source(queue, [mod], evidence=["provider:lazylib", "key:maxShipsInFleet"])
            verdict = self._eligible(queue)
        self.assertFalse(verdict["eligible"])
        self.assertIn("0 independent prior mod(s)", verdict["reasons"][0])

    def test_a_contradicting_ruling_stops_reuse(self) -> None:
        with resolved_temp_dir() as queue:
            for mod in ("S1", "S2", "S3"):
                _source(queue, [mod])
            _source(queue, ["S4"], intent="a stale copy of old settings")
            verdict = self._eligible(queue)
        self.assertFalse(verdict["eligible"])
        self.assertTrue(any("conflicting rulings" in r for r in verdict["reasons"]))

    def test_a_revoked_or_expired_ruling_no_longer_counts(self) -> None:
        from bridgeforge.escalation_precedent import revoke_ruling

        with resolved_temp_dir() as queue:
            first = _source(queue, ["S1"])
            _source(queue, ["S2"])
            _source(queue, ["S3"])
            before = self._eligible(queue)["eligible"]
            revoke_ruling(queue, first, "wrong mod")
            after = self._eligible(queue)
            with self.assertRaises(ValueError):
                revoke_ruling(queue, first, "again")
        self.assertTrue(before)
        self.assertFalse(after["eligible"])
        self.assertIn("2 independent", after["reasons"][0])

    def test_unknown_predicate_fields_refuse_instead_of_matching_anything(self) -> None:
        with resolved_temp_dir() as queue:
            _source(queue, ["S1"])
            _source(queue, ["S2"])
            _source(queue, ["S3"], extra_predicate={"wildcard": "*"})
            verdict = self._eligible(queue)
        self.assertFalse(verdict["eligible"])
        self.assertEqual(verdict["sources"], [])

    def test_historical_free_text_rulings_are_precedent_only(self) -> None:
        with resolved_temp_dir() as queue:
            _rulings(queue, ["accept", "accept", "accept"])
            verdict = self._eligible(queue)
            shown = precedents(queue, FINDING)
        self.assertFalse(verdict["eligible"])
        self.assertEqual(len(shown), 3)
        self.assertTrue(all("precedent only" in e["predicate_problem"] for e in shown))

    def test_incomplete_evidence_and_person_only_findings_refuse(self) -> None:
        with resolved_temp_dir() as queue:
            for mod in ("S1", "S2", "S3"):
                _source(queue, [mod], evidence=["line:12"])
                _source(queue, [mod], finding="save-thing", evidence=EVIDENCE)
            bare = self._eligible(queue, [_finding(["line:12", "count:3"])])
            manual = self._eligible(queue, [_finding(classification="MANUAL")])
            save = self._eligible(queue, [_finding(finding="save-thing")])
            fixer = standing_eligibility(queue, [_finding()], "T", operation="approve-fixer")
        self.assertTrue(any("incomplete evidence" in r for r in bare["reasons"]))
        self.assertTrue(any("person-only" in r for r in manual["reasons"]))
        self.assertTrue(any("person-only" in r for r in save["reasons"]))
        self.assertFalse(fixer["eligible"])

    def test_apply_uses_standing_for_open_mods_logs_sources_and_revocation_propagates(self) -> None:
        from bridgeforge.escalation_precedent import load_log, revoke_ruling

        with resolved_temp_dir() as queue:
            sources = [_source(queue, [mod]) for mod in ("S1", "S2", "S3")]
            _workspace(queue, "T", _explanation(5, "one_key"), evidence=EVIDENCE)
            _workspace(queue, "U", _explanation(5, "one_key"), evidence=["provider:other", "key:other"])
            sheet = queue / "SHEET.csv"
            written = write_sheet(queue, sheet, quiet=True)
            rows = read_sheet(sheet)
            result = apply_sheet(sheet)
            baseline_t = queue / "T" / "working" / "reports" / "baseline.json"
            keys_before = json.loads(baseline_t.read_text(encoding="utf-8"))["findings"]
            u_baseline_exists = (queue / "U" / "working" / "reports" / "baseline.json").exists()
            derived = [r for r in load_log(queue) if r.get("derived_from")]
            revoke_ruling(queue, sources[0], "S1 was a mistake")
            keys_after = json.loads(baseline_t.read_text(encoding="utf-8"))["findings"]
        self.assertEqual(written["standing"], 1)
        self.assertEqual(rows[0]["standing_mods"], "T")
        self.assertEqual((rows[0]["prefilled"], rows[0]["answer"]), ("yes", "accept"))  # only a suggestion; standing came from the predicate
        self.assertEqual(len(keys_before), 1)
        self.assertFalse(u_baseline_exists)  # a different predicate: left open
        self.assertEqual(len(derived), 1)
        self.assertEqual(sorted(derived[0]["derived_from"]), sorted(sources))
        self.assertIn("standing approval from 3 prior rulings", derived[0]["reason"])
        self.assertIn(derived[0]["predicate_hash"], derived[0]["reason"])
        self.assertEqual(result["applied"][0]["mods"], ["T"])
        self.assertEqual(keys_after, [])  # the derived approval fell with its source

    def test_skip_keeps_a_standing_mod_open(self) -> None:
        with resolved_temp_dir() as queue:
            for mod in ("S1", "S2", "S3"):
                _source(queue, [mod])
            _workspace(queue, "T", _explanation(5, "one_key"), evidence=EVIDENCE)
            sheet = queue / "SHEET.csv"
            write_sheet(queue, sheet, quiet=True)
            rows = read_sheet(sheet)
            rows[0]["answer"], rows[0]["reason"] = "skip", "decide later"
            with sheet.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=COLUMNS)
                writer.writeheader()
                writer.writerows(rows)
            result = apply_sheet(sheet)
        self.assertEqual(result["applied"], [])
        self.assertEqual(result["skipped"], [rows[0]["group"]])


class PacketPrecedentTests(unittest.TestCase):
    """C2: a decision packet shows "Answered before"."""

    def _packet(self, workspace: Path, tier: str = "decision") -> dict:
        finding = {"id": FINDING, "classification": "REVIEW", "severity": "low", "confidence": "DETERMINISTIC", "explanation": "e", "file": "f", "evidence": []}
        return {"id": f"{FINDING}--mod", "workspace": str(workspace), "finding": FINDING, "tier": tier, "kind": "owner", "findings": [finding], "file": None}

    def test_section_lists_at_most_five_rulings_newest_first_and_is_absent_without_any(self) -> None:
        from bridgeforge.revive import attach_precedent, render_packet

        with resolved_temp_dir() as queue:
            workspace = queue / "Me"
            workspace.mkdir()
            packet = self._packet(workspace)
            attach_precedent([packet], workspace)
            bare = render_packet(packet)
            _rulings(queue, ["accept"] * 7)
            attach_precedent([packet], workspace)
            shown = render_packet(packet)
            agent = self._packet(workspace, tier="code")
            attach_precedent([agent], workspace)
        self.assertNotIn("Answered before", bare)
        self.assertIn("## Answered before", shown)
        bullets = [line for line in shown.splitlines() if line.startswith("- 2026-")]
        self.assertEqual(len(bullets), 5)
        self.assertTrue(bullets[0].startswith("- 2026-10-07: **accept** for Old7 - tuning set is deliberate"))
        self.assertNotIn("precedent", agent)

    def test_packet_shows_predicate_precedent_only_and_revoked_status(self) -> None:
        from bridgeforge.escalation_precedent import revoke_ruling
        from bridgeforge.revive import attach_precedent, render_packet

        with resolved_temp_dir() as queue:
            workspace = queue / "Me"
            workspace.mkdir()
            good, gone = _source(queue, ["S1"], date="2026-10-03"), _source(queue, ["S2"], evidence=["key:other"], date="2026-10-02")
            with (queue / RULINGS_FILE).open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"date": "2026-10-01", "finding": FINDING, "ruling": "accept", "reason": "old chat", "mods": ["S3"]}) + "\n")
            revoke_ruling(queue, gone, "mistaken")
            packet = self._packet(workspace)
            attach_precedent([packet], workspace)
            text = render_packet(packet)
        self.assertIn("predicate ", text)
        self.assertIn("check revision 1", text)
        self.assertIn("[revoked]", text)
        self.assertIn("precedent only: no predicate", text)
        self.assertIsNotNone(good)

    def test_own_baseline_reason_is_not_shown_to_its_own_packet(self) -> None:
        with resolved_temp_dir() as queue:
            for name in ("Me", "Other"):
                reports = queue / name / "working" / "reports"
                reports.mkdir(parents=True)
                (reports / "baseline.json").write_text(json.dumps({"findings": [f"{FINDING}|f|e"], "reasons": {f"{FINDING}|f|e": f"why {name}"}}), encoding="utf-8")
            found = precedents(queue, FINDING, exclude="Me")
        self.assertEqual([e["reason"] for e in found], ["why Other"])


if __name__ == "__main__":
    unittest.main()
