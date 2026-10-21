"""`escalation triage` (ROADMAP 80.7): open decision packets grouped by the decision they wait on, with synthetic packets."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from bridgeforge.baseline import accept_findings
from bridgeforge.escalation_precedent import RULINGS_FILE, predicate_hash
from bridgeforge.escalation_triage import file_pattern, render, triage, write_result
from tests.support import resolved_temp_dir

FINDING = "vanilla-class-duplicated-in-jar"
OTHER = "description-missing"


def _finding(finding: str, file: str, evidence: list[str]) -> dict:
    return {"id": finding, "file": file, "evidence": evidence, "classification": "REVIEW", "explanation": f"{finding} question"}


def _workspace(queue: Path, name: str, findings: list[dict], tier: str = "decision", extra: list[dict] | None = None) -> Path:
    """An ESCALATED workspace with one decision packet per finding id, plus `extra` non-decision packets."""
    workspace = queue / name
    (workspace / "reports" / "revive").mkdir(parents=True)
    (workspace / "reports" / "escalations").mkdir(parents=True)
    (workspace / "working").mkdir()
    packets = []
    for finding in findings:
        packet = {"id": f"{finding['id']}--{name}", "finding": finding["id"], "tier": tier, "kind": "owner", "file": finding["file"], "findings": [finding]}
        (workspace / "reports" / "escalations" / f"{finding['id']}--{name}.json").write_text(json.dumps(packet), encoding="utf-8")
        packets.append({"id": packet["id"], "finding": finding["id"], "tier": tier, "kind": "owner"})
    packets += extra or []
    (workspace / "reports" / "revive" / "REVIVE.json").write_text(json.dumps({"status": "ESCALATED", "packets": packets}), encoding="utf-8")
    return workspace


def _group_for(result: dict, finding: str, mod: str) -> dict:
    return next(g for g in result["groups"] if g["finding"] == finding and mod in g["mods"])


class FilePatternTests(unittest.TestCase):
    def test_extension_pattern_and_fallbacks(self) -> None:
        self.assertEqual(file_pattern("data/config/settings.json"), "*.json")
        self.assertEqual(file_pattern("jars\\mod.jar!com/A.class"), "*.class")
        self.assertEqual(file_pattern("README"), "(no extension)")
        self.assertEqual(file_pattern(""), "(mod-wide)")


class TriageGroupingTests(unittest.TestCase):
    def test_same_evidence_shares_a_group_and_different_evidence_does_not(self) -> None:
        with resolved_temp_dir() as queue:
            shared = ["vanilla-source:api-jar"]
            _workspace(queue, "A", [_finding(FINDING, "jars/a.jar!x/B.class", shared)])
            _workspace(queue, "B", [_finding(FINDING, "jars/b.jar!x/C.class", shared)])
            _workspace(queue, "C", [_finding(FINDING, "jars/c.jar!x/D.class", ["vanilla-source:loose-script"])])
            result = triage(queue)
        self.assertEqual(len(result["groups"]), 2)
        self.assertEqual(sorted(_group_for(result, FINDING, "A")["mods"]), ["A", "B"])
        self.assertEqual(_group_for(result, FINDING, "C")["mods"], ["C"])

    def test_different_file_pattern_splits_a_group(self) -> None:
        with resolved_temp_dir() as queue:
            _workspace(queue, "A", [_finding(OTHER, "data/a.json", ["field:name"])])
            _workspace(queue, "B", [_finding(OTHER, "data/b.csv", ["field:name"])])
            result = triage(queue)
        self.assertEqual(len(result["groups"]), 2)

    def test_volatile_counts_do_not_split_a_group(self) -> None:
        with resolved_temp_dir() as queue:
            _workspace(queue, "A", [_finding(OTHER, "data/a.json", ["field:name", "count:3"])])
            _workspace(queue, "B", [_finding(OTHER, "data/b.json", ["field:name", "count:9"])])
            result = triage(queue)
        self.assertEqual(len(result["groups"]), 1)
        self.assertEqual(result["groups"][0]["evidence"], ["field:name"])


class TriageClearingTests(unittest.TestCase):
    def test_mod_clears_only_when_every_open_decision_is_in_the_group(self) -> None:
        with resolved_temp_dir() as queue:
            shared = ["vanilla-source:api-jar"]
            _workspace(queue, "Solo", [_finding(FINDING, "jars/a.jar!x/B.class", shared)])
            _workspace(queue, "Two", [_finding(FINDING, "jars/a.jar!x/B.class", shared), _finding(OTHER, "data/a.json", ["field:name"])])
            result = triage(queue)
        group = _group_for(result, FINDING, "Solo")
        self.assertEqual(group["cleared"], ["Solo"])
        self.assertNotIn("Two", _group_for(result, FINDING, "Two")["cleared"])
        self.assertEqual(result["groups"][0]["finding"], FINDING)  # sorted by mods cleared

    def test_non_decision_blocker_is_never_cleared(self) -> None:
        with resolved_temp_dir() as queue:
            _workspace(queue, "Agentic", [_finding(OTHER, "data/a.json", ["field:name"])],
                       extra=[{"id": "code--Agentic", "finding": "loose-script-compile-error", "tier": "code", "kind": "agent"}])
            result = triage(queue)
        group = result["groups"][0]
        self.assertEqual(group["cleared"], [])
        self.assertEqual(group["blocked_elsewhere"], ["Agentic"])

    def test_accepted_findings_leave_the_queue(self) -> None:
        with resolved_temp_dir() as queue:
            finding = _finding(OTHER, "data/a.json", ["field:name"])
            workspace = _workspace(queue, "A", [finding])
            accept_findings(workspace / "working", [f"{OTHER}|data/a.json|field:name"], "owner checked")
            result = triage(queue)
        self.assertEqual(result["groups"], [])


class TriageRulingTests(unittest.TestCase):
    def _ruling(self, ident: str, constraints: list[str], finding: str = OTHER) -> dict:
        predicate = {"version": 1, "finding": finding, "check_revision": 1, "classification": "REVIEW", "constraints": constraints}
        return {"id": ident, "finding": finding, "ruling": "accept", "reason": "deliberate", "intent": "keep", "date": "2026-10-01",
                "mods": ["Old"], "predicate": predicate, "predicate_hash": predicate_hash(predicate)}

    def test_exact_and_near_rulings_are_listed_and_revoked_ones_are_not(self) -> None:
        with resolved_temp_dir() as queue:
            _workspace(queue, "A", [_finding(OTHER, "data/a.json", ["field:name", "field:size"])])
            rulings = [self._ruling("R1", ["field:name", "field:size"]), self._ruling("R2", ["field:name", "field:size", "field:color"]),
                       self._ruling("R3", ["field:name", "field:size"])]
            revoke = {"revokes": "R3", "reason": "withdrawn"}
            (queue / RULINGS_FILE).write_text("\n".join(json.dumps(r) for r in [*rulings, revoke]) + "\n", encoding="utf-8")
            result = triage(queue)
        near = result["groups"][0]["near_rulings"]
        self.assertEqual([n["id"] for n in near], ["R1", "R2"])
        self.assertTrue(near[0]["exact"])
        self.assertFalse(near[1]["exact"])
        self.assertEqual(near[1]["similarity"], 0.67)

    def test_rulings_on_other_findings_are_ignored(self) -> None:
        with resolved_temp_dir() as queue:
            _workspace(queue, "A", [_finding(OTHER, "data/a.json", ["field:name"])])
            (queue / RULINGS_FILE).write_text(json.dumps(self._ruling("R9", ["field:name"], finding=FINDING)) + "\n", encoding="utf-8")
            result = triage(queue)
        self.assertEqual(result["groups"][0]["near_rulings"], [])


class TriageCommandTests(unittest.TestCase):
    def test_per_mod_accept_commands_and_ruling_proposal_only_when_it_covers_the_finding(self) -> None:
        with resolved_temp_dir() as queue:
            _workspace(queue, "A", [_finding(OTHER, "data/a.json", ["field:name"])])
            _workspace(queue, "B", [_finding(OTHER, "data/a.json", ["field:size"])])
            _workspace(queue, "C", [_finding(OTHER, "data/a.json", ["field:name"])])
            result = triage(queue)
        by_evidence = {tuple(g["evidence"]): g for g in result["groups"]}
        name_group = by_evidence[("field:name",)]
        self.assertFalse(name_group["ruling_proposal"])  # B is also open on this finding, outside the group
        accept_lines = [c for c in name_group["commands"] if "escalation accept" in c]
        self.assertEqual(len(accept_lines), 2)
        self.assertIn(f'"{queue / "A"}" "{OTHER}:data/a.json"', accept_lines[0])
        self.assertTrue(all("--reason" in c for c in name_group["commands"]))

    def test_ruling_proposal_when_group_covers_every_mod_with_the_finding(self) -> None:
        with resolved_temp_dir() as queue:
            _workspace(queue, "A", [_finding(OTHER, "data/a.json", ["field:name"])])
            _workspace(queue, "B", [_finding(OTHER, "data/a.json", ["field:name"])])
            result = triage(queue)
        group = result["groups"][0]
        self.assertTrue(group["ruling_proposal"])
        self.assertTrue(group["commands"][-1].startswith(f"bridgeforge escalation rule {OTHER} "))

    def test_write_result_goes_to_the_given_directory_only(self) -> None:
        with resolved_temp_dir() as queue, resolved_temp_dir() as out:
            _workspace(queue, "A", [_finding(OTHER, "data/a.json", ["field:name"])])
            result = triage(queue)
            paths = write_result(result, out)
            self.assertEqual(sorted(p.name for p in out.iterdir()), ["ESCALATION_TRIAGE.json", "ESCALATION_TRIAGE.md"])
            self.assertEqual(sorted(p.name for p in queue.iterdir()), ["A"])
            markdown = Path(paths["md"]).read_text(encoding="utf-8")
        self.assertIn("T001", markdown)
        self.assertEqual(render(result), markdown)


if __name__ == "__main__":
    unittest.main()
