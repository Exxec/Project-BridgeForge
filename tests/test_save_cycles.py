"""save-doctor --cycles and --break-cycle (ROADMAP 60g(3), RC8-31) on a small synthetic campaign.xml shaped like the real one."""
from __future__ import annotations

import hashlib
import unittest
from pathlib import Path

from bridgeforge.save.save_cycles import SaveCycleError, break_cycle, find_cycles
from bridgeforge.save.save_doctor import diagnose
from tests.support import resolved_temp_dir

INNER = '<memory cl="Memory" ref="2"></memory>'
CYCLE = f"""<CampaignEngine z="0">
<market cl="PCMarket" z="1">
<memory cl="Memory" z="2">
<d>
<e>
<st>$SA_stationAugmentListMemId</st>
<list z="3">
<station cl="Entity" z="4">
<market cl="PCMarket" z="5">
  {INNER}
</market>
</station>
</list>
</e>
</d>
</memory>
</market>
</CampaignEngine>
"""
# A reference to the memory from OUTSIDE any PCMarket nested in it is ordinary sharing, not the cycle.
SHARED = CYCLE.replace(INNER, "<other>x</other>").replace("</CampaignEngine>", '<holder cl="Entity" z="9"><memory cl="Memory" ref="2"></memory></holder>\n</CampaignEngine>')


def _save(root: Path, body: str) -> Path:
    save = root / "save"
    save.mkdir()
    (save / "campaign.xml").write_text(body, encoding="utf-8", newline="")
    return save


def _digest(save: Path) -> str:
    return hashlib.sha256((save / "campaign.xml").read_bytes()).hexdigest()


class FindCyclesTests(unittest.TestCase):
    def test_the_inner_reference_is_found_with_line_ids_and_keys(self) -> None:
        with resolved_temp_dir() as root:
            cycles = find_cycles(_save(root, CYCLE))
        self.assertEqual(len(cycles), 1)
        found = cycles[0]
        self.assertEqual((found["line"], found["memory"], found["pcmarket"]), (10, "2", "5"))
        self.assertEqual(found["keys"], ["$SA_stationAugmentListMemId"])
        self.assertEqual(found["text"], INNER)

    def test_a_reference_from_outside_the_nested_market_is_not_a_cycle(self) -> None:
        with resolved_temp_dir() as root:
            self.assertEqual(find_cycles(_save(root, SHARED)), [])

    def test_save_doctor_runs_on_campaign_xml_alone_and_reports_the_cycle_when_asked(self) -> None:
        with resolved_temp_dir() as root:
            (root / "mods").mkdir()
            save = _save(root, CYCLE)
            plain = diagnose(save, root / "mods")
            asked = diagnose(save, root / "mods", cycles=True)
        self.assertEqual(plain["verdict"], "NO_KNOWN_PROBLEM")
        self.assertTrue(any("descriptor.xml is missing" in s for s in plain["skipped"]))
        self.assertEqual(asked["verdict"], "WILL_LIKELY_FAIL")
        self.assertEqual([p["pcmarket"] for p in asked["problems"] if p["class"] == "MEMORY_CYCLE"], ["5"])


class BreakCycleTests(unittest.TestCase):
    def test_the_line_is_replaced_in_a_copy_and_the_original_is_untouched(self) -> None:
        with resolved_temp_dir() as root:
            save = _save(root, CYCLE)
            before = _digest(save)
            result = break_cycle(save, root / "repaired")
            copy_lines = (root / "repaired" / "campaign.xml").read_text(encoding="utf-8").splitlines()
            after = _digest(save)
        self.assertEqual(before, after)
        self.assertEqual(result["changed_lines"], [{"line": 10, "memory": "2", "pcmarket": "5"}])
        self.assertEqual((result["cycles_before"], result["cycles_after"]), (1, 0))
        self.assertEqual(copy_lines[9], '  <memory cl="Memory"><d></d></memory>')
        self.assertEqual(len(copy_lines), len(CYCLE.splitlines()))

    def test_bad_requests_are_refused_and_leave_nothing_behind(self) -> None:
        with resolved_temp_dir() as root:
            save = _save(root, CYCLE)
            (root / "taken").mkdir()
            for target in (root / "taken", save / "inside"):
                with self.assertRaises(SaveCycleError):
                    break_cycle(save, target)
            clean = root / "clean"
            clean.mkdir()
            (clean / "campaign.xml").write_text(SHARED, encoding="utf-8")
            with self.assertRaises(SaveCycleError):
                break_cycle(clean, root / "repaired")
            self.assertFalse((root / "repaired").exists())

    def test_a_line_that_is_not_the_expected_text_aborts_the_repair(self) -> None:
        import bridgeforge.save.save_cycles as module

        with resolved_temp_dir() as root:
            save = _save(root, CYCLE)
            real = module.find_cycles
            calls = {"n": 0}

            def lying(path):
                calls["n"] += 1
                found = real(path)
                if calls["n"] == 1:
                    found[0] = {**found[0], "line": found[0]["line"] - 1}
                return found

            module.find_cycles = lying
            try:
                with self.assertRaises(SaveCycleError):
                    break_cycle(save, root / "repaired")
            finally:
                module.find_cycles = real
            self.assertFalse((root / "repaired").exists())


if __name__ == "__main__":
    unittest.main()


class BaseRateTests(unittest.TestCase):
    """ROADMAP 70 H3.4: a diagnosis says how common the surrounding shape is, so a culprit is never named from one cycle alone."""

    def test_the_scan_counts_condition_markets_and_those_sharing_a_memory(self) -> None:
        from bridgeforge.save.save_cycles import scan_cycles

        with resolved_temp_dir() as root:
            cycles, rate = scan_cycles(_save(root, CYCLE))
        self.assertEqual(len(cycles), 1)
        self.assertEqual(rate, {"pcmarkets": 2, "pcmarkets_sharing_a_memory": 1})  # the outer market (own memory) and the inner copy (a reference)

    def test_a_save_doctor_cycle_problem_carries_the_base_rate(self) -> None:
        from bridgeforge.save.save_doctor import diagnose

        with resolved_temp_dir() as root:
            result = diagnose(_save(root, CYCLE), root / "no-mods", cycles=True)
        cycle = next(p for p in result["problems"] if p["class"] == "MEMORY_CYCLE")
        self.assertIn("1 cycle(s) among 2 condition market(s)", cycle["base_rate"])