"""ROADMAP item 73 E1/E2 with item 75 R3: report-only eligibility, a refused --auto-accept, and a tested application path."""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

from bridgeforge import escalation_policy as policy_module
from bridgeforge.escalation import EscalationError, load_packet, run_packet
from bridgeforge.escalation_policy import (
    FAIL, INCOMPLETE, NOT_APPLICABLE, PASS, POLICY_NAME, AutoAcceptError, _regression_check, _scope_check, apply_attempt,
    bindings, evaluate_attempt, recover, workspace_apply_lock,
)
from bridgeforge.escalation_review import review_attempt, review_sheet
from bridgeforge.revive import append_ledger, revive
from bridgeforge.workspace_tools import review_applied
from tests.support import resolved_temp_dir
from tests.test_revive import AGENT_FIX, AGENT_PACKET, SETTINGS, _agent, _workspace

POLICY = {"schema_version": 1, "approved": {"json-empty-array-element": {"suffixes": [".json"], "max_files": 1}}}
FLAGGED_FIX = AGENT_FIX.replace("'255,,0', '255,0')", "'255,,0', '255,0').replace('\"x\": 1', '\"x\": 1,\\n  \"Random\": 2')")


def _policy(workspace: Path, data: dict | None = POLICY) -> None:
    if data is not None:
        (workspace.parent / POLICY_NAME).write_text(json.dumps(data), encoding="utf-8")


def _ledger(workspace: Path) -> list[dict]:
    path = workspace / "reports" / "escalations" / "ledger.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _status(result: dict) -> dict[str, str]:
    return {c["check"]: c["status"] for c in result["checks"]}


def _only_failing(result: dict) -> set[str]:
    return {c["check"] for c in result["checks"] if c["status"] not in (PASS, NOT_APPLICABLE)}


def _verified(root: Path, *, policy: dict | None = POLICY, fix: str = AGENT_FIX):
    workspace = _workspace(root)
    revive(workspace)
    _policy(workspace, policy)
    result = run_packet(workspace, AGENT_PACKET, _agent(root, fix))
    packet = load_packet(workspace, AGENT_PACKET)
    sandbox = workspace / "scratch" / "escalations" / AGENT_PACKET / "attempt-1" / "working"
    return workspace, packet, sandbox, result


class EligibilityReportTests(unittest.TestCase):
    def test_a_passing_attempt_is_eligible_and_nothing_is_applied(self) -> None:
        with resolved_temp_dir() as root:
            workspace, packet, sandbox, result = _verified(root)
            gate = evaluate_attempt(packet, workspace, sandbox, [SETTINGS], [], {SETTINGS: ["-a", "+b"]})
            settings = (workspace / "working" / SETTINGS).read_text(encoding="utf-8")
        self.assertEqual(result["outcome"], "VERIFIED")
        self.assertTrue(gate["eligible"], gate["failed"])
        self.assertEqual(_status(gate)["compile"], NOT_APPLICABLE)
        self.assertEqual(_status(gate)["regression"], NOT_APPLICABLE)
        self.assertIn(",,", settings)
        for check in gate["checks"]:  # every check carries its record
            self.assertTrue({"status", "reason", "tool", "input_sha256", "output_sha256", "evidence"} <= set(check))
        self.assertEqual(next(c for c in gate["checks"] if c["check"] == "verifier")["tool"]["python"], sys.version.split()[0])

    def test_the_sheet_says_eligible_or_not_eligible_with_the_failing_gate(self) -> None:
        with resolved_temp_dir() as root:
            workspace, *_ = _verified(root)
            eligible = review_sheet(workspace)
            sheet = Path(eligible["sheet"]).read_text(encoding="utf-8")
            (workspace.parent / POLICY_NAME).unlink()
            blocked = review_sheet(workspace)
            blocked_sheet = Path(blocked["sheet"]).read_text(encoding="utf-8")
        self.assertIn(f"- `{AGENT_PACKET}`: ELIGIBLE", sheet)
        self.assertEqual(eligible["eligible"], [AGENT_PACKET])
        self.assertIn("Scan delta, findings removed: `json-empty-array-element`", sheet)
        self.assertIn(f"- `{AGENT_PACKET}`: NOT ELIGIBLE: scope FAIL: no standing auto-accept policy", blocked_sheet)
        self.assertEqual(blocked["eligible"], [])

    def test_each_gate_failing_alone_blocks(self) -> None:
        wide = {"schema_version": 1, "approved": {"json-empty-array-element": {"suffixes": [".json"], "max_files": 3}}}
        with resolved_temp_dir() as root:
            workspace, packet, sandbox, _ = _verified(root, policy=wide)
            ok = ([SETTINGS], [], {SETTINGS: ["-a", "+b"]})
            self.assertTrue(evaluate_attempt(packet, workspace, sandbox, *ok)["eligible"])
            flags = evaluate_attempt(packet, workspace, sandbox, [SETTINGS], ["reflection"], ok[2])
            self.assertEqual(_only_failing(flags), {"review-flags"})
            deleted = {SETTINGS: [f"-l{i}" for i in range(policy_module.DELETION_SLACK + 2)] + ["+one"]}
            self.assertEqual(_only_failing(evaluate_attempt(packet, workspace, sandbox, [SETTINGS], [], deleted)), {"deletions"})
            outside = evaluate_attempt(packet, workspace, sandbox, [SETTINGS, "data/other.json"], [], ok[2])
            self.assertEqual(_only_failing(outside), {"allowed-files"})
            _policy(workspace, {"schema_version": 1, "approved": {"json-empty-array-element": {"suffixes": [".csv"], "max_files": 3}}})
            self.assertEqual(_only_failing(evaluate_attempt(packet, workspace, sandbox, *ok)), {"scope"})

    def test_a_remaining_finding_fails_the_verifier_and_the_finding_gate(self) -> None:
        lazy = AGENT_FIX.replace("255,,0', '255,0'", "x', 'x'") + "Path('data/config/settings.json').write_text(Path('data/config/settings.json').read_text(encoding='utf-8').replace('\"x\": 1', '\"x\": 2'), encoding='utf-8')\n"
        with resolved_temp_dir() as root:
            workspace = _workspace(root)
            revive(workspace)
            _policy(workspace)
            result = run_packet(workspace, AGENT_PACKET, _agent(root, lazy), retries=0)
            gate = review_attempt(workspace, AGENT_PACKET, gate=True)["gate"]
        self.assertEqual(result["outcome"], "FAILED")
        self.assertTrue({"verifier", "finding-gone"} <= _only_failing(gate))
        self.assertFalse(gate["eligible"])

    def test_missing_tools_cannot_pass(self) -> None:
        # Code changed, no vanilla core and no regression fixture: both checks are INCOMPLETE, never PASS.
        both = {"schema_version": 1, "approved": {"json-empty-array-element": {"suffixes": [".json", ".java"], "max_files": 3}}}
        with resolved_temp_dir() as root:
            workspace, packet, sandbox, _ = _verified(root, policy=both)
            packet = {**packet, "allowed_files": [*packet["allowed_files"], "data/Foo.java"]}
            gate = evaluate_attempt(packet, workspace, sandbox, [SETTINGS, "data/Foo.java"], [], {})
            jar = evaluate_attempt(packet, workspace, sandbox, [SETTINGS, "jars/src/data/Foo.java"], [], {})
        self.assertEqual(_status(gate)["compile"], INCOMPLETE)
        self.assertEqual(_status(gate)["regression"], INCOMPLETE)
        self.assertFalse(gate["eligible"])
        self.assertIn("INCOMPLETE", gate["failed"])
        self.assertEqual(_status(jar)["compile"], INCOMPLETE)

    def test_a_scan_failure_is_incomplete_not_a_pass(self) -> None:
        with resolved_temp_dir() as root:
            workspace, packet, sandbox, _ = _verified(root)
            with mock.patch("bridgeforge.revive._scan", side_effect=ValueError("parser blew up")):
                gate = evaluate_attempt(packet, workspace, sandbox, [SETTINGS], [], {})
        self.assertEqual(_status(gate)["scan"], INCOMPLETE)
        self.assertFalse(gate["eligible"])

    def test_regression_fixture_results(self) -> None:
        packet = {"finding": "f"}
        with resolved_temp_dir() as root:
            def run(command, timeout=None):
                policy = {"approved": {"f": {"regression": command}}}
                with mock.patch.object(policy_module, "REGRESSION_TIMEOUT", timeout or 30):
                    return _regression_check(packet, root, ["data/Foo.java"], policy)["status"]
            self.assertEqual(run([sys.executable, "-c", "raise SystemExit(0)"]), PASS)
            self.assertEqual(run([sys.executable, "-c", "raise SystemExit(3)"]), FAIL)
            self.assertEqual(run([sys.executable, "-c", "import time; time.sleep(30)"], timeout=1), INCOMPLETE)
            self.assertEqual(run(["no-such-program-bf"]), INCOMPLETE)
            self.assertEqual(_regression_check(packet, root, ["data/Foo.java"], {"approved": {"f": {}}})["status"], INCOMPLETE)

    def test_scope_boundaries_cannot_be_bypassed(self) -> None:
        with resolved_temp_dir() as root:
            workspace, packet, _, _ = _verified(root)
            def scope(**over):
                return _scope_check({**packet, **over}, workspace, [SETTINGS], POLICY, "x")["status"]
            self.assertEqual(scope(), PASS)
            manual = [{**packet["findings"][0], "classification": "MANUAL"}]
            self.assertEqual(scope(findings=manual), FAIL)
            self.assertEqual(scope(findings=[{**manual[0], "classification": "UNKNOWN"}]), FAIL)
            self.assertEqual(scope(finding="content-reference-unresolved", merged=None), FAIL)  # decision tier
            self.assertEqual(scope(finding="campaign-memory-live-object", merged=None), FAIL)  # save/lifecycle
            self.assertEqual(scope(kind="owner"), FAIL)
            info = json.loads((workspace / "working" / "mod_info.json").read_text(encoding="utf-8"))
            maintained = {**POLICY, "maintained_third_party_mods": [info["id"]]}
            self.assertEqual(_scope_check(packet, workspace, [SETTINGS], maintained, "x")["status"], FAIL)

    def test_a_new_manual_finding_of_tier_none_still_blocks(self) -> None:
        from bridgeforge.automation import tier_for

        none_id = next(i for i in ("ashlib-api-usage", "ashlib-version-evidence") if tier_for(i) == "none")
        extra = {"id": none_id, "file": "x.java", "classification": "MANUAL", "evidence": ["e"], "explanation": "x"}
        with resolved_temp_dir() as root:
            workspace, packet, sandbox, _ = _verified(root)
            with mock.patch("bridgeforge.revive._scan", side_effect=[[extra], []]):
                gate = evaluate_attempt(packet, workspace, sandbox, [SETTINGS], [], {})
        self.assertEqual(_status(gate)["no-new-findings"], FAIL)
        self.assertFalse(gate["eligible"])


class RefusedAndEnabledTests(unittest.TestCase):
    def test_auto_accept_is_refused_naming_the_prerequisites(self) -> None:
        with resolved_temp_dir() as root:
            workspace = _workspace(root)
            revive(workspace)
            _policy(workspace)
            before = (workspace / "working" / SETTINGS).read_bytes()
            with self.assertRaises(EscalationError) as caught:
                run_packet(workspace, AGENT_PACKET, _agent(root, AGENT_FIX), auto_accept=True)
            after = (workspace / "working" / SETTINGS).read_bytes()
            attempted = (workspace / "scratch" / "escalations" / AGENT_PACKET).exists()
        for name in ("R1", "R2", "R4"):
            self.assertIn(name, str(caught.exception))
        self.assertEqual(before, after)
        self.assertFalse(attempted)
        self.assertFalse(policy_module.ENABLED)

    def test_when_enabled_an_eligible_attempt_is_applied_and_logged_not_live_accepted(self) -> None:
        with resolved_temp_dir() as root:
            workspace = _workspace(root)
            revive(workspace)
            _policy(workspace)
            with mock.patch.object(policy_module, "ENABLED", True):
                result = run_packet(workspace, AGENT_PACKET, _agent(root, AGENT_FIX), auto_accept=True)
            settings = (workspace / "working" / SETTINGS).read_text(encoding="utf-8")
            entry = _ledger(workspace)[-1]
            listed = review_applied(workspace.parent, "2000-01-01")["auto_accepted"]
        self.assertEqual(result["outcome"], "APPLIED")
        self.assertNotIn(",,", settings)
        self.assertTrue(entry["auto_accepted"])
        self.assertFalse(entry["live_accepted"])
        self.assertEqual(entry["auto_accept_checks"]["compile"], NOT_APPLICABLE)
        self.assertEqual([r["packet"] for r in listed], [AGENT_PACKET])

    def test_when_enabled_an_ineligible_attempt_is_left_for_the_sheet(self) -> None:
        with resolved_temp_dir() as root:
            workspace = _workspace(root)
            revive(workspace)
            _policy(workspace)
            with mock.patch.object(policy_module, "ENABLED", True):
                result = run_packet(workspace, AGENT_PACKET, _agent(root, FLAGGED_FIX), auto_accept=True)
            settings = (workspace / "working" / SETTINGS).read_text(encoding="utf-8")
        self.assertEqual(result["outcome"], "VERIFIED")
        self.assertIn("review-flags", result["auto_accept_blocked"])
        self.assertIn(",,", settings)


class ApplicationTests(unittest.TestCase):
    def _setup(self, root: Path, names=("a.json", "b.json")):
        workspace = root / "ws"
        sandbox = workspace / "scratch" / "escalations" / "p" / "attempt-1" / "working"
        for name in names:
            (workspace / "working" / name).parent.mkdir(parents=True, exist_ok=True)
            (workspace / "working" / name).write_text(f"old {name}\n", encoding="utf-8")
            sandbox.mkdir(parents=True, exist_ok=True)
            (sandbox / name).write_text(f"new {name}\n", encoding="utf-8")
        (workspace / "reports" / "escalations").mkdir(parents=True)
        (workspace / "reports" / "escalations" / "p.json").write_text("{}", encoding="utf-8")
        packet = {"id": "p", "finding": "f", "tier": "code"}
        assessment = {"eligible": True, "checks": [{"check": "verifier", "status": PASS}], "bindings": bindings(workspace, "p", sandbox, list(names))}
        return workspace, packet, sandbox, assessment

    def test_all_files_are_staged_journaled_and_committed(self) -> None:
        with resolved_temp_dir() as root:
            workspace, packet, _, assessment = self._setup(root)
            apply_attempt(workspace, packet, 1, assessment)
            texts = [(workspace / "working" / n).read_text(encoding="utf-8") for n in ("a.json", "b.json")]
            journal = json.loads((workspace / "scratch/escalations/p" / policy_module.JOURNAL_NAME).read_text(encoding="utf-8"))
            backup = (workspace / "working" / "a.json.pre-bf-escalation-p.bak").read_text(encoding="utf-8")
            leftovers = list((workspace / "working").glob("*.bf-stage"))
        self.assertEqual(texts, ["new a.json\n", "new b.json\n"])
        self.assertEqual(journal["state"], "DONE")
        self.assertEqual(backup, "old a.json\n")
        self.assertEqual(leftovers, [])

    def test_a_changed_attempt_file_is_refused(self) -> None:
        with resolved_temp_dir() as root:
            workspace, packet, sandbox, assessment = self._setup(root)
            (sandbox / "a.json").write_text("tampered\n", encoding="utf-8")
            with self.assertRaises(AutoAcceptError):
                apply_attempt(workspace, packet, 1, assessment)
            self.assertEqual((workspace / "working" / "a.json").read_text(encoding="utf-8"), "old a.json\n")

    def test_changed_working_packet_and_policy_are_refused(self) -> None:
        for what in ("working", "packet", "policy"):
            with self.subTest(what), resolved_temp_dir() as root:
                workspace, packet, _, assessment = self._setup(root)
                if what == "working":
                    (workspace / "working" / "b.json").write_text("hand edit\n", encoding="utf-8")
                elif what == "packet":
                    (workspace / "reports" / "escalations" / "p.json").write_text('{"x": 1}', encoding="utf-8")
                else:
                    (workspace.parent / POLICY_NAME).write_text("{}", encoding="utf-8")
                with self.assertRaises(AutoAcceptError):
                    apply_attempt(workspace, packet, 1, assessment)
                self.assertEqual((workspace / "working" / "a.json").read_text(encoding="utf-8"), "old a.json\n")

    def test_an_ineligible_assessment_and_a_path_escape_are_refused(self) -> None:
        with resolved_temp_dir() as root:
            workspace, packet, _, assessment = self._setup(root)
            with self.assertRaises(AutoAcceptError):
                apply_attempt(workspace, packet, 1, {**assessment, "eligible": False})
            escaping = {**assessment, "bindings": {**assessment["bindings"], "attempt": {"../evil.json": "x"}, "working": {"../evil.json": None}}}
            with self.assertRaises(AutoAcceptError):
                apply_attempt(workspace, packet, 1, escaping)

    def test_a_failure_part_way_rolls_every_file_back(self) -> None:
        with resolved_temp_dir() as root:
            workspace, packet, _, assessment = self._setup(root)
            real, calls = os.replace, []

            def flaky(src, dst):
                calls.append(dst)
                if len(calls) == 2:
                    raise OSError("disk full")
                return real(src, dst)

            with mock.patch.object(policy_module.os, "replace", flaky), self.assertRaises(OSError):
                apply_attempt(workspace, packet, 1, assessment)
            texts = [(workspace / "working" / n).read_text(encoding="utf-8") for n in ("a.json", "b.json")]
            state = json.loads((workspace / "scratch/escalations/p" / policy_module.JOURNAL_NAME).read_text(encoding="utf-8"))["state"]
        self.assertEqual(texts, ["old a.json\n", "old b.json\n"])
        self.assertEqual(state, "ROLLED_BACK")

    def test_a_crash_after_a_replace_is_recovered_from_the_journal(self) -> None:
        with resolved_temp_dir() as root:
            workspace, packet, sandbox, assessment = self._setup(root)
            target = workspace / "working" / "a.json"
            backup = workspace / "working" / "a.json.pre-bf-escalation-p.bak"
            backup.write_bytes(target.read_bytes())
            import hashlib
            sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()  # noqa: E731
            entry = {"path": "a.json", "target": str(target), "backup": str(backup), "stage": None, "before_sha": sha(target),
                     "after_sha": sha(sandbox / "a.json"), "committed": False}
            target.write_bytes((sandbox / "a.json").read_bytes())  # replaced, then the process died before the journal said so
            journal = workspace / "scratch/escalations/p" / policy_module.JOURNAL_NAME
            journal.write_text(json.dumps({"state": "COMMITTING", "entries": [entry]}), encoding="utf-8")
            first = recover(workspace, "p")
            second = recover(workspace, "p")
            text = target.read_text(encoding="utf-8")
        self.assertEqual(first["restored"], ["a.json"])
        self.assertEqual(second["restored"], [])
        self.assertEqual(text, "old a.json\n")

    def test_a_second_application_is_refused_while_the_lock_is_held(self) -> None:
        with resolved_temp_dir() as root:
            workspace = root / "ws"
            lock = workspace / "scratch" / "escalations" / policy_module.LOCK_NAME
            lock.parent.mkdir(parents=True)
            lock.write_text(f"{os.getppid()}\n", encoding="utf-8")  # a live process that is not this one
            with self.assertRaises(AutoAcceptError), workspace_apply_lock(workspace):
                pass


class ReviveReviewListingTests(unittest.TestCase):
    def test_auto_accepted_ledger_entries_are_listed_since_a_date(self) -> None:
        with resolved_temp_dir() as root:
            workspace = _workspace(root)
            append_ledger(workspace, {"packet": "p1", "finding": "f", "outcome": "APPLIED", "changed": ["a.json"], "auto_accepted": True,
                                      "auto_accept_checks": {"verifier": PASS}})
            listed = review_applied(workspace.parent, "2000-01-01")["auto_accepted"]
            later = review_applied(workspace.parent, "2999-01-01")["auto_accepted"]
        self.assertEqual([(r["workspace"], r["packet"]) for r in listed], [("OldMod", "p1")])
        self.assertEqual(later, [])


if __name__ == "__main__":
    unittest.main()
