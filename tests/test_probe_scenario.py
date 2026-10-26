import copy
import json
import unittest
from pathlib import Path

from bridgeforge.probe.probe_config import ProbeConfigError, write_probe_config
from bridgeforge.probe.probe_scenario import (
    FAIL, NOT_OBSERVED, PASS, ScenarioError, apply_to_verdicts, evaluate_expectations, load_scenario, probe_config_keys,
    stage_settings, validate_scenario,
)
from tests.support import link_dir, resolved_temp_dir

FIXTURES = Path(__file__).parent / "fixtures" / "probe_scenarios"


def _base() -> dict:
    return {"schema": 1, "settings": {"data/config/x.json": {"a": 1}}, "steps": [{"step": "advance_days", "days": 2}],
            "expect": [{"id": "one", "line": "HELLO", "within_days": 3}], "pass_requires": ["one"]}


def _log(*rows: str) -> str:
    return "\n".join(rows)


def _clock(ms: int, day: int) -> str:
    return f"{ms} [Thread-3] INFO  com.bridgeforge.probe.ProbeLog  - BF-PROBE|0.2.27|scenario|INFO|clock|day={day}"


def _line(ms: int, text: str) -> str:
    return f"{ms} [Thread-3] INFO  x.Y  - {text}"


class LoaderTests(unittest.TestCase):
    def test_fixtures_load(self):
        for name in ("templar_crusade", "seeker_sk6c", "domain_drones"):
            scenario = load_scenario(FIXTURES / f"{name}.json")
            self.assertEqual(scenario["schema"], 1, name)

    def test_unknown_keys_refused_at_every_level(self):
        for mutate in (lambda s: s.update(extra=1), lambda s: s["expect"][0].update(extra=1),
                       lambda s: s["steps"][0].update(extra=1)):
            data = _base()
            mutate(data)
            with self.assertRaises(ScenarioError):
                validate_scenario(data)

    def test_unknown_step_refused(self):
        data = _base()
        data["steps"] = [{"step": "open_market_dialog"}]
        with self.assertRaisesRegex(ScenarioError, "unknown step"):
            validate_scenario(data)

    def test_bad_values_refused(self):
        cases = [
            lambda s: s.update(schema=2),
            lambda s: s["settings"].update({"../x.json": {"a": 1}}),
            lambda s: s["settings"].update({"/abs.json": {"a": 1}}),
            lambda s: s["settings"].update({"data/x.txt": {"a": 1}}),
            lambda s: s["expect"][0].update(line="("),
            lambda s: s["expect"][0].update(within_seconds=5),
            lambda s: s["expect"][0].pop("within_days"),
            lambda s: s["expect"][0].update(after="nope"),
            lambda s: s.update(pass_requires=["missing"]),
            lambda s: s["steps"].__setitem__(0, {"step": "advance_days", "days": -1}),
            lambda s: s["steps"].__setitem__(0, {"step": "damage_player_module", "member_hull_id": "H", "module_index": 0, "hull_fraction": 0.5}),
            lambda s: s["steps"].__setitem__(0, {"step": "damage_player_module", "member_hull_id": "H", "module_index": 1, "hull_fraction": 1.5}),
            lambda s: s["steps"].__setitem__(0, {"step": "destroy_player_module", "member_hull_id": "H"}),
        ]
        for mutate in cases:
            data = copy.deepcopy(_base())
            mutate(data)
            with self.assertRaises(ScenarioError):
                validate_scenario(data)

    def test_after_must_reference_earlier_expectation(self):
        data = _base()
        data["expect"] = [{"id": "a", "line": "x", "within_days": 1, "after": "b"}, {"id": "b", "line": "y", "within_days": 1}]
        with self.assertRaises(ScenarioError):
            validate_scenario(data)

    def test_pass_requires_defaults_to_all(self):
        data = _base()
        del data["pass_requires"]
        self.assertEqual(validate_scenario(data)["pass_requires"], ["one"])


class StagingTests(unittest.TestCase):
    def test_settings_touch_only_the_rig_copy(self):
        with resolved_temp_dir() as tmp:
            working, rig_copy = tmp / "working", tmp / "rig" / "mods" / "m"
            for root in (working, rig_copy):
                (root / "data" / "config").mkdir(parents=True)
                (root / "data" / "config" / "x.json").write_text('{\n # c\n "a": 0, "b": 2}', encoding="utf-8")
            before = (working / "data" / "config" / "x.json").read_bytes()
            staged = stage_settings(validate_scenario(_base()), rig_copy, working)
            self.assertEqual((working / "data" / "config" / "x.json").read_bytes(), before)
            self.assertEqual(json.loads((rig_copy / "data" / "config" / "x.json").read_text(encoding="utf-8")), {"a": 1, "b": 2})
            self.assertEqual(staged[0]["before"], {"a": 0})

    def test_refuses_working_copy_missing_file_and_escape(self):
        with resolved_temp_dir() as tmp:
            working = tmp / "working"
            (working / "data" / "config").mkdir(parents=True)
            (working / "data" / "config" / "x.json").write_text("{}", encoding="utf-8")
            scenario = validate_scenario(_base())
            with self.assertRaisesRegex(ScenarioError, "working copy"):
                stage_settings(scenario, working, working)
            other = tmp / "rig"
            other.mkdir()
            with self.assertRaisesRegex(ScenarioError, "not in the rig copy"):
                stage_settings(scenario, other, working)

    def test_write_probe_config_stages_into_rig_copy_only(self):
        with resolved_temp_dir() as tmp:
            working = tmp / "work" / "fixture_mod"
            (working / "data" / "config").mkdir(parents=True)
            (working / "reports").mkdir()
            (working / "mod_info.json").write_text('{"id":"fixture_mod"}', encoding="utf-8")
            (working / "data" / "config" / "x.json").write_text('{"a": 0}', encoding="utf-8")
            (working / "reports" / "PROBE_SCENARIO.json").write_text(json.dumps(_base()), encoding="utf-8")
            core, rig = tmp / "core", tmp / "rig"
            core.mkdir()
            rig.mkdir()
            try:
                link_dir(core, rig / "starsector-core")
            except OSError:
                self.skipTest("no junction support")
            copy = rig / "mods" / "fixture_mod"
            (copy / "data" / "config").mkdir(parents=True)
            (copy / "mod_info.json").write_text('{"id":"fixture_mod"}', encoding="utf-8")
            (copy / "data" / "config" / "x.json").write_text('{"a": 0}', encoding="utf-8")
            result = write_probe_config(working, rig)
            self.assertEqual(json.loads((working / "data" / "config" / "x.json").read_text()), {"a": 0})
            self.assertEqual(json.loads((copy / "data" / "config" / "x.json").read_text()), {"a": 1})
            self.assertEqual(result["scenario"]["settings_staged"][0]["path"], "data/config/x.json")
            self.assertEqual(result["config"]["scenario_steps"], [{"step": "advance_days", "days": 2.0}])

    def test_write_probe_config_refuses_when_rig_has_no_copy(self):
        with resolved_temp_dir() as tmp:
            working = tmp / "work" / "fixture_mod"
            (working / "reports").mkdir(parents=True)
            (working / "mod_info.json").write_text('{"id":"fixture_mod"}', encoding="utf-8")
            (working / "reports" / "PROBE_SCENARIO.json").write_text(json.dumps(_base()), encoding="utf-8")
            core, rig = tmp / "core", tmp / "rig"
            core.mkdir()
            (rig / "mods").mkdir(parents=True)
            try:
                link_dir(core, rig / "starsector-core")
            except OSError:
                self.skipTest("no junction support")
            with self.assertRaises(ProbeConfigError):
                write_probe_config(working, rig)

    def test_probe_config_keys(self):
        keys = probe_config_keys([validate_scenario(_base())])
        self.assertTrue(keys["scenario_clock"])
        self.assertEqual(len(keys["scenario_steps"]), 1)


def _scenario(**expect) -> dict:
    data = _base()
    data["expect"] = [dict(id=k, **v) for k, v in expect.items()]
    data["pass_requires"] = list(expect)
    return validate_scenario(data)


class EvaluationTests(unittest.TestCase):
    def test_pass_fail_and_not_observed_by_days(self):
        scenario = _scenario(early={"line": "EARLY", "within_days": 1}, late={"line": "LATE", "within_days": 1},
                             never={"line": "NEVER", "within_days": 1}, open_={"line": "OPEN", "within_days": 5})
        log = _log(_line(1, "EARLY before clock"), _clock(10, 0), _line(11, "EARLY ok"), _clock(20, 1), _clock(30, 2),
                   _line(31, "LATE too late"), _clock(40, 3))
        block = evaluate_expectations(log, scenario)["expectations"]
        self.assertEqual(block["early"]["status"], PASS)
        self.assertIn("EARLY ok", block["early"]["evidence"])
        self.assertEqual(block["late"]["status"], FAIL)
        self.assertEqual(block["never"]["status"], FAIL)
        self.assertEqual(block["open_"]["status"], NOT_OBSERVED)

    def test_lines_before_the_scenario_clock_do_not_count_and_no_clock_is_not_observed(self):
        scenario = _scenario(x={"line": "HELLO", "within_days": 3})
        self.assertEqual(evaluate_expectations(_line(1, "HELLO"), scenario)["expectations"]["x"]["status"], NOT_OBSERVED)
        result = evaluate_expectations(_log(_line(1, "HELLO"), _clock(5, 0)), scenario)
        self.assertEqual(result["expectations"]["x"]["status"], NOT_OBSERVED)

    def test_count_min(self):
        scenario = _scenario(x={"line": "HELLO", "within_days": 3, "count_min": 2})
        one = evaluate_expectations(_log(_clock(1, 0), _line(2, "HELLO")), scenario)
        two = evaluate_expectations(_log(_clock(1, 0), _line(2, "HELLO"), _line(3, "HELLO")), scenario)
        self.assertEqual(one["expectations"]["x"]["status"], NOT_OBSERVED)
        self.assertEqual(two["expectations"]["x"]["status"], PASS)

    def test_ordering_with_after(self):
        scenario = _scenario(a={"line": "AAA", "within_days": 5}, b={"line": "BBB", "within_days": 5, "after": "a"})
        ordered = evaluate_expectations(_log(_clock(1, 0), _line(2, "AAA"), _line(3, "BBB")), scenario)
        reversed_ = evaluate_expectations(_log(_clock(1, 0), _line(2, "BBB"), _line(3, "AAA"), _clock(9, 6)), scenario)
        self.assertEqual(ordered["verdict"], PASS)
        self.assertEqual(reversed_["expectations"]["b"]["status"], FAIL)
        self.assertEqual(reversed_["verdict"], FAIL)
        missing_a = evaluate_expectations(_log(_clock(1, 0), _line(3, "BBB")), scenario)
        self.assertIn("not satisfied", missing_a["expectations"]["b"]["reason"])

    def test_within_seconds_uses_log_milliseconds(self):
        scenario = _scenario(x={"line": "HELLO", "within_seconds": 2})
        ok = evaluate_expectations(_log(_clock(1000, 0), _line(2500, "HELLO")), scenario)
        slow = evaluate_expectations(_log(_clock(1000, 0), _line(4500, "HELLO")), scenario)
        pending = evaluate_expectations(_log(_clock(1000, 0), _line(1500, "other")), scenario)
        self.assertEqual(ok["expectations"]["x"]["status"], PASS)
        self.assertEqual(slow["expectations"]["x"]["status"], FAIL)
        self.assertEqual(pending["expectations"]["x"]["status"], NOT_OBSERVED)

    def test_only_required_expectations_decide_the_verdict(self):
        data = _base()
        data["expect"] = [{"id": "a", "line": "AAA", "within_days": 1}, {"id": "b", "line": "BBB", "within_days": 1}]
        data["pass_requires"] = ["a"]
        block = evaluate_expectations(_log(_clock(1, 0), _line(2, "AAA"), _clock(3, 2)), validate_scenario(data))
        self.assertEqual(block["expectations"]["b"]["status"], FAIL)
        self.assertEqual(block["verdict"], PASS)

    def test_apply_to_verdicts(self):
        members = {"m1": {"verdict": "PASS", "failures": []}, "m2": {"verdict": "PASS", "failures": []}, "m3": {"verdict": "FAIL", "failures": ["x"]}}
        apply_to_verdicts(members, {"m1": {"verdict": "FAIL", "required": ["a"], "failed": ["a"]},
                                    "m2": {"verdict": "INCOMPLETE", "required": ["a"], "failed": []},
                                    "m3": {"verdict": "INCOMPLETE", "required": ["a"], "failed": []}})
        self.assertEqual((members["m1"]["verdict"], members["m2"]["verdict"], members["m3"]["verdict"]), ("FAIL", "INCOMPLETE", "FAIL"))
        self.assertTrue(members["m1"]["failures"])


class RecordWiringTests(unittest.TestCase):
    def test_member_scenarios_are_judged_from_the_workspace_file(self):
        from bridgeforge.probe.probe_group import evaluate_member_scenarios

        with resolved_temp_dir() as tmp:
            workspace = tmp / "ws"
            (workspace / "working" / "reports").mkdir(parents=True)
            (workspace / "working" / "reports" / "PROBE_SCENARIO.json").write_text(json.dumps(_base()), encoding="utf-8")
            bad = tmp / "bad"
            (bad / "working" / "reports").mkdir(parents=True)
            (bad / "working" / "reports" / "PROBE_SCENARIO.json").write_text('{"schema": 1, "oops": 1}', encoding="utf-8")
            plain = tmp / "plain"
            (plain / "working").mkdir(parents=True)
            log = tmp / "run.log"
            log.write_text(_log(_clock(1, 0), _line(2, "HELLO")), encoding="utf-8")
            blocks = evaluate_member_scenarios(log, {"m": workspace, "b": bad, "p": plain})
            self.assertEqual(blocks["m"]["verdict"], PASS)
            self.assertEqual(blocks["b"]["verdict"], "INCOMPLETE")
            self.assertIn("unknown key", blocks["b"]["error"])
            self.assertNotIn("p", blocks)


if __name__ == "__main__":
    unittest.main()
