"""ROADMAP item 75 R6: the save-upgrade planner/evaluator refuses gaps and separates proxy from serialization evidence."""
from __future__ import annotations

import copy
import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout

from bridgeforge.cli import main
from bridgeforge.save.save_upgrade import CASES, STAGE_ORDER, UpgradeError, evaluate_upgrade, plan_upgrade
from tests.support import resolved_temp_dir

H = {name: format(i, "x") * 64 for i, name in enumerate(["old", "new", "orig", "mid", "out1", "out2", "state", "state2"], 1)}
NEW = H["new"]


def _spec(case: str = "missing-colonies") -> dict:
    return {
        "schema_version": 1, "subject_mod": "zorg", "case": case,
        "old_candidate": {"version": "1.0+bf.9", "shipped_hash": H["old"], "files": {"mod_info.json": H["old"]}},
        "new_candidate": {"version": "1.0+bf.10", "shipped_hash": NEW, "files": {"mod_info.json": NEW}},
        "save_identity": {"original_hash": H["orig"], "copy_hash": H["orig"], "rig_slot": "zorg_old", "result_slot": "zorg_new"},
    }


def _evidence(case: str = "missing-colonies", kind: str = "serialization") -> dict:
    observed = {"unrelated_state_unchanged": True, **{k: (c["min"] + 0 if isinstance(c, dict) else c) for k, c in CASES[case].items()}}
    rows = [
        {"stage": "preconditions", "save_out_hash": H["orig"], "original_hash_after": H["orig"], "evidence_kind": "proxy"},
        {"stage": "load_old_with_new", "candidate_hash": NEW, "save_in_hash": H["orig"], "save_out_hash": H["orig"]},
        {"stage": "migration_check", "candidate_hash": NEW, "save_in_hash": H["orig"], "save_out_hash": H["orig"], "observations": observed},
        {"stage": "save_slot", "candidate_hash": NEW, "save_in_hash": H["orig"], "save_out_hash": H["out1"], "slot": "zorg_new"},
        {"stage": "reload_saved", "candidate_hash": NEW, "save_in_hash": H["out1"], "save_out_hash": H["out1"]},
        {"stage": "repeat_idempotence", "candidate_hash": NEW, "save_in_hash": H["out1"], "save_out_hash": H["out2"],
         "state_hash_before": H["state"], "state_hash_after": H["state"], "observations": {"migration_applied": False}},
    ]
    for number, row in enumerate(rows, 1):
        row["seq"] = number
        row.setdefault("evidence_kind", kind)
    return {"run_id": "run-1", "stages": rows}


class PlanTests(unittest.TestCase):
    def test_plan_lists_every_stage_in_order_with_case_expectations(self) -> None:
        plan = plan_upgrade(_spec("id-conflict"))
        self.assertEqual([s["stage"] for s in plan["stages"]], list(STAGE_ORDER))
        self.assertEqual(plan["status"], "LIVE_PENDING")
        check = next(s for s in plan["stages"] if s["stage"] == "migration_check")
        self.assertTrue(check["required_observations"]["conflicting_entity_untouched"])

    def test_plan_refuses_an_unusable_spec(self) -> None:
        for mutate in (
            lambda s: s.update(case="made-up"),
            lambda s: s["new_candidate"].update(shipped_hash=H["old"]),
            lambda s: s["new_candidate"].update(files={}),
            lambda s: s["new_candidate"]["files"].update({"../x": H["new"]}),
            lambda s: s["save_identity"].update(copy_hash=H["mid"]),
            lambda s: s["save_identity"].update(result_slot="zorg_old"),
            lambda s: s["save_identity"].pop("original_hash"),
            lambda s: s.update(schema_version=2),
        ):
            spec = _spec()
            mutate(spec)
            with self.assertRaises(UpgradeError, msg=str(spec)):
                plan_upgrade(spec)


class EvaluateTests(unittest.TestCase):
    def test_every_case_verifies_with_complete_serialization_evidence(self) -> None:
        for case in CASES:
            result = evaluate_upgrade(_spec(case), _evidence(case))
            self.assertEqual(result["status"], "VERIFIED", (case, result))

    def test_no_evidence_is_live_pending_never_a_pass(self) -> None:
        self.assertEqual(evaluate_upgrade(_spec(), None)["status"], "LIVE_PENDING")
        self.assertEqual(evaluate_upgrade(_spec(), {"stages": []})["status"], "LIVE_PENDING")

    def test_missing_stage_is_refused(self) -> None:
        evidence = _evidence()
        evidence["stages"] = [s for s in evidence["stages"] if s["stage"] != "reload_saved"]
        result = evaluate_upgrade(_spec(), evidence)
        self.assertEqual(result["status"], "REFUSED")
        self.assertIn("missing stage: reload_saved", result["refusals"])

    def test_out_of_order_and_repeated_stages_are_refused(self) -> None:
        evidence = _evidence()
        evidence["stages"][3], evidence["stages"][4] = evidence["stages"][4], evidence["stages"][3]
        self.assertEqual(evaluate_upgrade(_spec(), evidence)["status"], "REFUSED")
        evidence = _evidence()
        evidence["stages"].append(copy.deepcopy(evidence["stages"][0]))
        self.assertEqual(evaluate_upgrade(_spec(), evidence)["status"], "REFUSED")

    def test_non_increasing_seq_is_refused(self) -> None:
        evidence = _evidence()
        evidence["stages"][2]["seq"] = 99
        self.assertEqual(evaluate_upgrade(_spec(), evidence)["status"], "REFUSED")

    def test_proxy_evidence_for_serialization_stages_is_proxy_only(self) -> None:
        result = evaluate_upgrade(_spec(), _evidence(kind="proxy"))
        self.assertEqual(result["status"], "PROXY_ONLY")
        self.assertIn("save_slot", result["proxy_stages"])

    def test_wrong_candidate_broken_lineage_and_same_slot_fail(self) -> None:
        cases = {
            "candidate": lambda e: e["stages"][1].update(candidate_hash=H["old"]),
            "lineage": lambda e: e["stages"][4].update(save_in_hash=H["mid"]),
            "slot": lambda e: e["stages"][3].update(slot="zorg_old"),
            "result is the original": lambda e: e["stages"][3].update(save_out_hash=H["orig"]),
            "original touched": lambda e: e["stages"][0].update(original_hash_after=H["mid"]),
            "not idempotent": lambda e: e["stages"][5].update(state_hash_after=H["state2"]),
        }
        for label, mutate in cases.items():
            evidence = _evidence()
            mutate(evidence)
            self.assertEqual(evaluate_upgrade(_spec(), evidence)["status"], "FAIL", label)

    def test_negative_observations_fail(self) -> None:
        negatives = {"missing-colonies": {"duplicates_created": 2}, "captured-ownership": {"ownership_preserved": False},
                     "healthy-control": {"state_changed": True}, "id-conflict": {"conflicting_entity_untouched": False}}
        for case, change in negatives.items():
            evidence = _evidence(case)
            evidence["stages"][2]["observations"].update(change)
            self.assertEqual(evaluate_upgrade(_spec(case), evidence)["status"], "FAIL", case)

    def test_unrelated_state_must_be_preserved_and_migration_must_not_repeat(self) -> None:
        evidence = _evidence()
        evidence["stages"][2]["observations"]["unrelated_state_unchanged"] = False
        self.assertEqual(evaluate_upgrade(_spec(), evidence)["status"], "FAIL")
        evidence = _evidence()
        evidence["stages"][5]["observations"]["migration_applied"] = True
        self.assertEqual(evaluate_upgrade(_spec(), evidence)["status"], "FAIL")

    def test_run_identity_is_required_and_must_name_the_new_candidate(self) -> None:
        evidence = _evidence()
        del evidence["run_id"]
        self.assertEqual(evaluate_upgrade(_spec(), evidence)["status"], "REFUSED")
        self.assertEqual(evaluate_upgrade(_spec(), evidence, {"run_id": "r", "shipped_hash": NEW})["status"], "VERIFIED")
        self.assertEqual(evaluate_upgrade(_spec(), evidence, {"run_id": "r", "shipped_hash": H["old"]})["status"], "REFUSED")


def _record(equal: bool = True, **over) -> dict:
    block = {"compare_observed": True, "equal": equal, "diff_sections": [] if equal else ["markets"]}
    record = {"run_id": "run-1", "status": "ACCEPTABLE", "shipped_hash": NEW, "milestones": {"reload_after_save": True}, "fingerprint": block}
    return {**record, **over}


class FingerprintEvidenceTests(unittest.TestCase):
    def _status(self, record: dict, kind: str = "serialization", reload_kind: str = "proxy") -> dict:
        evidence = _evidence(kind=kind)
        for row in evidence["stages"]:
            if row["stage"] == "reload_saved":
                row["evidence_kind"] = reload_kind
        evidence["fingerprint_records"] = [record]
        return evaluate_upgrade(_spec(), evidence)

    def test_an_observed_equal_bound_fingerprint_upgrades_a_proxy_reload_to_verified(self) -> None:
        self.assertEqual(evaluate_upgrade(_spec(), self._proxy_reload())["status"], "PROXY_ONLY")
        result = self._status(_record())
        self.assertEqual(result["status"], "VERIFIED")
        self.assertEqual(result["fingerprint_evidence"]["counted"], ["run-1"])

    def _proxy_reload(self) -> dict:
        evidence = _evidence()
        next(r for r in evidence["stages"] if r["stage"] == "reload_saved")["evidence_kind"] = "proxy"
        return evidence

    def test_a_differing_fingerprint_fails_the_run(self) -> None:
        result = self._status(_record(equal=False))
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("markets", " ".join(result["failures"]))

    def test_records_that_are_not_observed_and_bound_change_nothing(self) -> None:
        for bad in (_record(status="REFUSED"), _record(run_id="other"), _record(shipped_hash=H["old"]),
                    _record(milestones={"reload_after_save": False}), _record(fingerprint={"compare_observed": False, "equal": True})):
            result = self._status(bad)
            self.assertEqual(result["status"], "PROXY_ONLY", bad)
            self.assertEqual(result["fingerprint_evidence"]["counted"], [])
            self.assertTrue(result["fingerprint_evidence"]["rejected"])

    def test_a_fingerprint_alone_is_still_live_pending(self) -> None:
        result = evaluate_upgrade(_spec(), {"run_id": "run-1", "fingerprint_records": [_record()]})
        self.assertEqual(result["status"], "LIVE_PENDING")
        self.assertEqual(result["fingerprint_evidence"]["counted"], ["run-1"])

    def test_cli_accepts_fingerprint_record_files(self) -> None:
        with resolved_temp_dir() as base:
            spec, record = base / "spec.json", base / "record.json"
            spec.write_text(json.dumps(_spec()), encoding="utf-8")
            record.write_text(json.dumps(_record()), encoding="utf-8")
            out = io.StringIO()
            with redirect_stdout(out), redirect_stderr(io.StringIO()):
                code = main(["save-upgrade", "evaluate", str(spec), "--fingerprint-record", str(record), "--run-id", "run-1", "--run-hash", NEW, "--json"])
        self.assertEqual((code, json.loads(out.getvalue())["fingerprint_evidence"]["counted"]), (1, ["run-1"]))


class CliTests(unittest.TestCase):
    def _run(self, *argv: str) -> tuple[int, str]:
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            return main(list(argv)), out.getvalue()

    def test_plan_and_evaluate_commands(self) -> None:
        with resolved_temp_dir() as base:
            spec, good, bad = base / "spec.json", base / "good.json", base / "bad.json"
            spec.write_text(json.dumps(_spec()), encoding="utf-8")
            good.write_text(json.dumps(_evidence()), encoding="utf-8")
            bad_evidence = _evidence()
            bad_evidence["stages"].pop()
            bad.write_text(json.dumps(bad_evidence), encoding="utf-8")
            self.assertEqual(self._run("save-upgrade", "plan", str(spec))[0], 0)
            self.assertEqual(self._run("save-upgrade", "evaluate", str(spec), str(good))[0], 0)
            self.assertEqual(self._run("save-upgrade", "evaluate", str(spec), str(bad))[0], 1)
            code, text = self._run("save-upgrade", "evaluate", str(spec), "--json")
            self.assertEqual((code, json.loads(text)["status"]), (1, "LIVE_PENDING"))
            self.assertEqual(self._run("save-upgrade", "evaluate", str(base / "missing.json"))[0], 2)


if __name__ == "__main__":
    unittest.main()
