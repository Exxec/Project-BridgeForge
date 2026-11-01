"""S2.3 recipe trials: real fixer on private copies, holdout separation, abstention, failures and the promotion gate."""
import json
import unittest
from pathlib import Path
from unittest import mock

from bridgeforge import recipe_trial as rt
from bridgeforge.fixers import FixerError
from bridgeforge.fixers.common import FileChange, FixPlan
from tests.support import link_dir, resolved_temp_dir

RECIPE = "mod-info-game-version-inexact"


def make_mod(root: Path, version: str = "0.95a-RC15") -> Path:
    root.mkdir(parents=True)
    (root / "mod_info.json").write_text(json.dumps({"id": root.name, "name": root.name, "version": "1", "gameVersion": version}), encoding="utf-8")
    return root


def fake_scan(*findings: dict):
    return lambda root, core, compile_check: [dict(f) for f in findings]


def finding(ident: str = RECIPE, classification: str = "SAFE", **extra) -> dict:
    return {"id": ident, "classification": classification, "file": "mod_info.json", "evidence": [], "category": "", **extra}


def recipe(outcome: str, name: str = RECIPE, reasons: tuple = ()) -> dict:
    return {"finding": name, "outcome": outcome, "reasons": list(reasons), "changed_files": [], "compile_checked": False}


def case(name: str, split: str, *recipes: dict) -> dict:
    return {"name": name, "split": split, "input_digest": name, "recipes": list(recipes), "errors": []}


class RealFixerTrial(unittest.TestCase):
    def test_real_fixer_verifies_on_a_copy_and_leaves_the_input_unchanged(self):
        with resolved_temp_dir() as tmp:
            mod = make_mod(Path(tmp) / "Mod")
            before = (mod / "mod_info.json").read_bytes()
            result = rt.trial_case({"name": "Mod", "split": "training", "path": str(mod)}, core=None)
            row = next(r for r in result["recipes"] if r["finding"] == RECIPE)
            self.assertEqual(row["outcome"], rt.VERIFIED, row["reasons"])
            self.assertEqual(row["changed_files"], ["mod_info.json"])
            self.assertEqual((mod / "mod_info.json").read_bytes(), before)
            self.assertEqual(result["errors"], [])
            self.assertEqual(sorted(p.name for p in mod.iterdir()), ["mod_info.json"])

    def test_already_fixed_input_asks_for_no_recipe(self):
        with resolved_temp_dir() as tmp:
            mod = make_mod(Path(tmp) / "Mod", "0.98a-RC8")
            result = rt.trial_case({"name": "Mod", "split": "training", "path": str(mod)}, core=None)
            self.assertNotIn(RECIPE, [r["finding"] for r in result["recipes"]])


class Abstention(unittest.TestCase):
    def _try(self, source: Path, base: Path, group: list[dict], ident: str = RECIPE, scan=None) -> dict:
        return rt.try_recipe(source, ident, group, group, base, "0", core=None, scan=scan or fake_scan())

    def test_manual_unknown_save_and_balance_abstain_without_touching_a_copy(self):
        with resolved_temp_dir() as tmp:
            source = make_mod(Path(tmp) / "Mod")
            base = Path(tmp) / "copies"
            for group in ([finding(classification="MANUAL")], [finding(classification="UNKNOWN")], [finding(category="save")], [finding(category="balance")]):
                row = self._try(source, base, group)
                self.assertEqual(row["outcome"], rt.ABSTAINED)
                self.assertFalse(base.exists())

    def test_a_tier_other_than_auto_abstains(self):
        with resolved_temp_dir() as tmp, mock.patch.object(rt, "tier_for", return_value="decision"):
            row = self._try(make_mod(Path(tmp) / "Mod"), Path(tmp) / "copies", [finding()])
            self.assertEqual(row["outcome"], rt.ABSTAINED)
            self.assertIn("decision", row["reasons"][0])

    def test_a_refusing_fixer_is_a_refusal_with_the_temp_path_scrubbed(self):
        with resolved_temp_dir() as tmp, mock.patch.object(rt, "compute_fix", side_effect=lambda root, *_: (_ for _ in ()).throw(FixerError(f"no at {root}"))):
            base = Path(tmp) / "copies"
            row = self._try(make_mod(Path(tmp) / "Mod"), base, [finding()])
            self.assertEqual(row["outcome"], rt.REFUSED)
            self.assertNotIn(str(base), row["reasons"][0])


class Failures(unittest.TestCase):
    def _plan(self, working: Path, path: Path) -> FixPlan:
        return FixPlan(finding_id=RECIPE, mod_root=working, changes=[FileChange(path=path, before=path.read_bytes() if path.is_file() else b"", after=b"x", existed_before=path.is_file())])

    def test_a_plan_that_keeps_changing_is_not_idempotent(self):
        with resolved_temp_dir() as tmp:
            source, base = make_mod(Path(tmp) / "Mod"), Path(tmp) / "copies"
            with mock.patch.object(rt, "compute_fix", side_effect=lambda root, *_: self._plan(root, root / "mod_info.json")):
                row = rt.try_recipe(source, RECIPE, [finding()], [finding()], base, "0", core=None, scan=fake_scan())
            self.assertEqual(row["outcome"], rt.FAILED)
            self.assertIn("not idempotent", row["reasons"][0])

    def test_a_plan_outside_the_workspace_is_never_applied(self):
        with resolved_temp_dir() as tmp:
            source, base = make_mod(Path(tmp) / "Mod"), Path(tmp) / "copies"
            victim = Path(tmp) / "victim.txt"
            victim.write_text("keep", encoding="utf-8")
            with mock.patch.object(rt, "compute_fix", side_effect=lambda root, *_: self._plan(root, victim)):
                row = rt.try_recipe(source, RECIPE, [finding()], [finding()], base, "0", core=None, scan=fake_scan())
            self.assertEqual(row["outcome"], rt.FAILED)
            self.assertIn("outside the workspace", row["reasons"][0])
            self.assertEqual(victim.read_text(encoding="utf-8"), "keep")

    def test_a_new_finding_or_an_unmoved_one_fails(self):
        with resolved_temp_dir() as tmp:
            source = make_mod(Path(tmp) / "Mod")
            group = [finding()]
            row = rt.try_recipe(source, RECIPE, group, group, Path(tmp) / "a", "0", core=None, scan=fake_scan(finding("other-thing")))
            self.assertEqual(row["outcome"], rt.FAILED)
            self.assertIn("introduced other-thing", row["reasons"][0])
            row = rt.try_recipe(source, RECIPE, group, group, Path(tmp) / "b", "0", core=None, scan=fake_scan(finding()))
            self.assertEqual(row["outcome"], rt.FAILED)
            self.assertIn("still reported", row["reasons"][0])

    def test_changed_evidence_is_partial_and_an_informational_new_finding_is_not_a_failure(self):
        with resolved_temp_dir() as tmp:
            source = make_mod(Path(tmp) / "Mod")
            group = [finding()]
            row = rt.try_recipe(source, RECIPE, group, group, Path(tmp) / "a", "0", core=None, scan=fake_scan(finding("declared-dependencies")))
            self.assertEqual(row["outcome"], rt.VERIFIED, row["reasons"])
            self.assertEqual(row["classifications"], ["SAFE"])
            with mock.patch.object(rt, "compute_fix", side_effect=[self._plan(Path(tmp) / "b" / "0" / "working", Path(tmp) / "b" / "0" / "working" / "mod_info.json"), FixerError("nothing")]):
                row = rt.try_recipe(source, RECIPE, group, group, Path(tmp) / "b", "0", core=None, scan=fake_scan(finding(evidence=["null-guarded"])))
            self.assertEqual(row["outcome"], rt.PARTIAL, row["reasons"])

    def test_the_second_run_gets_a_fresh_scan_not_the_first_ones_numbers(self):
        with resolved_temp_dir() as tmp:
            source = make_mod(Path(tmp) / "Mod")
            seen = []

            def options(finding_id, working, target, core, findings):
                seen.append([f.get("evidence") for f in findings])
                return [{"target_game_version": "0.98a-RC8"}]

            with mock.patch.object(rt, "_fix_options", options):
                rt.try_recipe(source, RECIPE, [finding()], [finding()], Path(tmp) / "a", "0", core=None, scan=fake_scan(finding(evidence=["fresh"])))
            self.assertEqual(seen, [[[]], [["fresh"]]])

    def test_a_crashing_fixer_is_recorded_as_a_failure(self):
        with resolved_temp_dir() as tmp, mock.patch.object(rt, "compute_fix", side_effect=KeyError("boom")):
            row = rt.try_recipe(make_mod(Path(tmp) / "Mod"), RECIPE, [finding()], [finding()], Path(tmp) / "c", "0", core=None, scan=fake_scan())
            self.assertEqual(row["outcome"], rt.FAILED)
            self.assertIn("KeyError", row["reasons"][0])


class PromotionGate(unittest.TestCase):
    TRAINING = [case(n, "training", recipe(rt.VERIFIED)) for n in "abc"]

    def _state(self, cases: list[dict], revoked: set[str] = frozenset()) -> dict:
        return rt.gate(cases, {RECIPE}, set(revoked))[0]

    def test_three_training_positives_and_a_verified_holdout_reach_owner_review(self):
        row = self._state([*self.TRAINING, case("h", "holdout", recipe(rt.VERIFIED))])
        self.assertEqual(row["state"], "READY_FOR_OWNER_REVIEW")
        self.assertTrue(row["approved"])

    def test_holdout_positives_never_stand_in_for_training(self):
        cases = [case(n, "holdout", recipe(rt.VERIFIED)) for n in "abcd"]
        self.assertEqual(self._state(cases)["state"], "NEEDS_MORE_EVIDENCE")

    def test_no_holdout_observation_is_not_enough(self):
        self.assertEqual(self._state(self.TRAINING)["state"], "NEEDS_MORE_EVIDENCE")

    def test_a_holdout_failure_blocks_and_names_the_case(self):
        row = self._state([*self.TRAINING, case("h", "holdout", recipe(rt.FAILED, reasons=("broke",)))])
        self.assertEqual(row["state"], "BLOCKED")
        self.assertEqual(row["failures"], [{"case": "h", "split": "holdout", "reasons": ["broke"]}])

    def test_abstentions_stay_visible_and_are_not_positives(self):
        row = self._state([*self.TRAINING[:2], case("c", "training", recipe(rt.ABSTAINED)), case("h", "holdout", recipe(rt.VERIFIED))])
        self.assertEqual(row["state"], "NEEDS_MORE_EVIDENCE")
        self.assertEqual(row["training"][rt.ABSTAINED], ["c"])

    def test_a_revoked_approval_wins_over_good_evidence(self):
        row = self._state([*self.TRAINING, case("h", "holdout", recipe(rt.VERIFIED))], {RECIPE})
        self.assertEqual(row["state"], "REVOKED")

    def test_revocation_is_read_from_the_ruling_log(self):
        with resolved_temp_dir() as tmp:
            queue = Path(tmp)
            rows = [{"id": "R1", "ruling": "approve-fixer", "finding": RECIPE}, {"id": "R2", "ruling": "approve-fixer", "finding": "kept"}, {"revokes": "R1", "reason": "x"}]
            (queue / "ESCALATION_RULINGS.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
            self.assertEqual(rt._revoked_fixers(queue), {RECIPE})


class Cohort(unittest.TestCase):
    def _cohort(self, tmp: Path, cases: object, schema: int = 1) -> Path:
        path = tmp / "cohort.json"
        path.write_text(json.dumps({"schema_version": schema, "cases": cases}), encoding="utf-8")
        return path

    def test_bad_cohorts_are_refused(self):
        with resolved_temp_dir() as tmp:
            tmp = Path(tmp)
            mod = make_mod(tmp / "Mod")
            good = {"name": "Mod", "path": str(mod), "split": "training"}
            for cases, schema in (([], 1), ([good], 2), ([{**good, "split": "other"}], 1), ([good, good], 1),
                                  ([{"name": "x", "path": str(tmp), "split": "holdout"}], 1), ([{**good, "extra": 1}], 1)):
                with self.assertRaises(rt.RecipeTrialError):
                    rt.read_cohort(self._cohort(tmp, cases, schema))
            with self.assertRaises(rt.RecipeTrialError):
                rt.read_cohort(tmp / "absent.json")
            self.assertEqual(rt.read_cohort(self._cohort(tmp, [good]))[0]["name"], "Mod")

    def test_a_linked_tree_is_refused(self):
        with resolved_temp_dir() as tmp:
            tmp = Path(tmp)
            mod = make_mod(tmp / "Mod")
            (tmp / "elsewhere").mkdir()
            link_dir(tmp / "elsewhere", mod / "linked")
            with self.assertRaises(rt.RecipeTrialError):
                rt.tree_digest(mod)


class RunTrial(unittest.TestCase):
    def _cases(self, tmp: Path) -> list[dict]:
        return [{"name": n, "split": s, "path": str(make_mod(tmp / n))} for n, s in (("A", "training"), ("B", "holdout"))]

    def test_repeat_runs_select_the_same_work_and_write_no_policy(self):
        with resolved_temp_dir() as tmp:
            tmp = Path(tmp)
            cases = self._cases(tmp)
            policy = tmp / "AUTOMATION_POLICY.json"
            policy.write_text(json.dumps({"approved_fixers": {RECIPE: {"reason": "r"}}}), encoding="utf-8")
            first = rt.run_trial(cases, core=None, output=tmp / "one.json", policy_path=policy, quiet=True)
            second = rt.run_trial(cases, core=None, output=tmp / "two.json", policy_path=policy, quiet=True)
            self.assertEqual(first["selection_digest"], second["selection_digest"])
            self.assertEqual(json.loads(policy.read_text(encoding="utf-8")), {"approved_fixers": {RECIPE: {"reason": "r"}}})
            row = next(r for r in first["gate"] if r["finding"] == RECIPE)
            self.assertTrue(row["approved"])
            self.assertFalse((tmp / "one.json.partial.jsonl").exists())
            self.assertEqual(json.loads((tmp / "one.json").read_text(encoding="utf-8"))["schema"], rt.SCHEMA)

    def test_an_interrupted_run_resumes_and_a_changed_input_is_tried_again(self):
        with resolved_temp_dir() as tmp:
            tmp = Path(tmp)
            cases = self._cases(tmp)
            calls = []
            real = rt.trial_case

            def interrupted(case, **kwargs):
                if case["name"] == "B":
                    raise KeyboardInterrupt
                return real(case, **kwargs)

            with mock.patch.object(rt, "trial_case", interrupted), self.assertRaises(KeyboardInterrupt):
                rt.run_trial(cases, core=None, output=tmp / "out.json", quiet=True)

            def counted(case, **kwargs):
                calls.append(case["name"])
                return real(case, **kwargs)

            with mock.patch.object(rt, "trial_case", counted):
                rt.run_trial(cases, core=None, output=tmp / "out.json", quiet=True)
            self.assertEqual(calls, ["B"])

    def test_output_inside_an_input_is_refused(self):
        with resolved_temp_dir() as tmp:
            tmp = Path(tmp)
            cases = self._cases(tmp)
            with self.assertRaises(rt.RecipeTrialError):
                rt.run_trial(cases, core=None, output=tmp / "A" / "out.json", quiet=True)


if __name__ == "__main__":
    unittest.main()
