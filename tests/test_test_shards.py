"""96.5 C2: CI's time-balanced shards cover every test module exactly once, deterministically, and stay balanced."""
from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

from tests.run_partitioned import TIMINGS, flatten, module_of, select_shard, shard_modules

ROOT = Path(__file__).resolve().parents[1]


class _Case(unittest.TestCase):
    def runTest(self) -> None:  # pragma: no cover - never run
        pass


def _cases(ids: list[str]) -> list[unittest.TestCase]:
    cases = []
    for case_id in ids:
        case = _Case()
        case.id = (lambda value: (lambda: value))(case_id)  # discovery's id, without importing a real module
        cases.append(case)
    return cases


class ShardTests(unittest.TestCase):
    def test_every_module_lands_in_exactly_one_shard(self) -> None:
        weights = {"test_a": 9.0, "test_b": 5.0, "test_c": 4.0, "test_d": 1.0}
        shards = shard_modules(["test_a", "test_b", "test_c", "test_d", "test_new"], weights, 3)
        flat = [module for shard in shards for module in shard]
        self.assertEqual(sorted(flat), ["test_a", "test_b", "test_c", "test_d", "test_new"])
        self.assertEqual(len(flat), len(set(flat)))

    def test_longest_first_to_the_least_loaded_shard(self) -> None:
        weights = {"test_a": 9.0, "test_b": 5.0, "test_c": 4.0, "test_d": 1.0}
        self.assertEqual(shard_modules(list(weights), weights, 2), [["test_a", "test_d"], ["test_b", "test_c"]])
        self.assertEqual(shard_modules(list(reversed(weights)), weights, 2), shard_modules(list(weights), weights, 2))

    def test_an_unmeasured_module_counts_as_the_median(self) -> None:
        weights = {"test_a": 10.0, "test_b": 2.0, "test_c": 1.0}
        shards = shard_modules(["test_a", "test_b", "test_c", "test_new"], weights, 2)
        self.assertEqual(shards, [["test_a"], ["test_b", "test_new", "test_c"]])  # test_new weighs 2.0

    def test_selecting_a_shard_keeps_whole_modules_and_the_order(self) -> None:
        ids = ["test_a.A.one", "test_b.B.one", "test_a.A.two", "test_c.C.one"]
        weights = {"test_a": 9.0, "test_b": 5.0, "test_c": 4.0}
        one, two = select_shard(_cases(ids), "1/2", weights), select_shard(_cases(ids), "2/2", weights)
        self.assertEqual([c.id() for c in one], ["test_a.A.one", "test_a.A.two"])
        self.assertEqual([c.id() for c in two], ["test_b.B.one", "test_c.C.one"])

    def test_a_bad_shard_spec_is_refused(self) -> None:
        for spec in ("0/4", "5/4", "x/4", "1-4"):
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                select_shard(_cases(["test_a.A.one"]), spec, {})

    def test_the_measured_weights_cover_the_suite_and_balance_four_shards(self) -> None:
        document = json.loads(TIMINGS.read_text(encoding="utf-8"))
        weights = document["modules"]
        modules = sorted({module_of(case.id()) for case in flatten(unittest.defaultTestLoader.discover(str(ROOT / "tests")))})
        unmeasured = [m for m in modules if m not in weights]
        self.assertLessEqual(len(unmeasured), len(modules) // 10, f"refresh with tools/module-timings.py: {unmeasured[:10]}")
        loads = [sum(weights.get(m, 0.0) for m in shard) for shard in shard_modules(modules, weights, 4)]
        self.assertLess(max(loads) - min(loads), 0.1 * max(loads), loads)

    def test_the_weights_tool_sums_cases_per_module_and_keeps_the_slowest_run(self) -> None:
        spec = importlib.util.spec_from_file_location("module_timings", ROOT / "tools" / "module-timings.py")
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        reports = [{"seconds": {"test_a.A.one": 1.0, "test_a.A.two": 2.0, "test_b.B.one": 0.5}},
                   {"seconds": {"test_a.A.one": 0.5, "test_b.B.one": 4.0}}]
        self.assertEqual(tool.module_weights(reports), {"test_a": 3.0, "test_b": 4.0})


if __name__ == "__main__":
    unittest.main()
