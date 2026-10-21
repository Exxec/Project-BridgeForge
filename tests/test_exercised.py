"""What a probe run exercised, per mod (ROADMAP item 75 R1): the log parser, the HOLLOW flag and the run record."""
from __future__ import annotations

import json
import unittest

from bridgeforge.exercised import hollow_mods, hollow_warnings, parse_exercised
from bridgeforge.probe_config import build_probe_config
from bridgeforge.probe_group import merge_configs, record_group
from tests.bound_runs import bound_run
from tests.support import resolved_temp_dir
from tests.test_probe_group import _workspace

PREFIX = "9 [Thread-2] INFO  com.bridgeforge.probe.ProbeLog  - "
FULL = "hulls_built=3,variants_resolved=1,wings_resolved=0,items=0,planets=0,rings=0,markets=0,submarkets=0,missions=0,fleets=2,classes=0,hullmods=0,combat_ships=4"
ZERO = ",".join(item.split("=")[0] + "=0" for item in FULL.split(","))


def _line(mod: str, counts: str, version: str = "0.2.27") -> str:
    return f"{PREFIX}BF-PROBE|{version}|exercised|mod={mod}|{counts}"


class ParserTests(unittest.TestCase):
    def test_a_line_per_mod_becomes_a_stage_map(self) -> None:
        found = parse_exercised("\n".join([_line("mod_a", FULL), _line("mod_b", ZERO)]))
        self.assertEqual(found["mod_a"]["hulls_built"], 3)
        self.assertEqual(found["mod_a"]["combat_ships"], 4)
        self.assertEqual(set(found), {"mod_a", "mod_b"})
        self.assertEqual(sum(found["mod_b"].values()), 0)

    def test_repeated_lines_keep_the_highest_count_per_stage(self) -> None:
        early = "hulls_built=3,combat_ships=0"
        late = "hulls_built=3,combat_ships=5"
        found = parse_exercised("\n".join([_line("mod_a", late), _line("mod_a", early)]))
        self.assertEqual(found["mod_a"], {"hulls_built": 3, "combat_ships": 5})

    def test_malformed_counts_and_other_lines_are_ignored(self) -> None:
        found = parse_exercised("\n".join([_line("mod_a", "hulls_built=x,rings=2,=3,fleets"), "noise", f"{PREFIX}BF-PROBE|0.2.27|run|manifest_id=abc"]))
        self.assertEqual(found, {"mod_a": {"rings": 2}})

    def test_a_log_without_the_lines_gives_nothing(self) -> None:
        self.assertEqual(parse_exercised(f"{PREFIX}BF-PROBE|0.2.9|content-ids|OK|all-content|checked=2 failed=0"), {})


class HollowTests(unittest.TestCase):
    def test_all_zero_is_hollow_and_any_count_is_not(self) -> None:
        found = parse_exercised("\n".join([_line("mod_a", FULL), _line("mod_b", ZERO), _line("mod_c", ZERO)]))
        self.assertEqual(hollow_mods(found), ["mod_b", "mod_c"])
        self.assertEqual(hollow_mods(found, ["mod_a", "mod_b"]), ["mod_b"])

    def test_no_line_for_a_mod_is_not_hollow(self) -> None:
        self.assertEqual(hollow_mods(parse_exercised(_line("mod_a", FULL)), ["mod_a", "mod_z"]), [])

    def test_warning_text_names_the_mod(self) -> None:
        self.assertEqual(len(hollow_warnings(["mod_b"])), 1)
        self.assertIn("HOLLOW: mod_b", hollow_warnings(["mod_b"])[0])


class RecordTests(unittest.TestCase):
    def _record(self, lines: list[str]):
        with resolved_temp_dir() as root:
            queue = root / "In operation"
            a = _workspace(queue, "A", "mod_a", "hull_a")
            b = _workspace(queue, "B", "mod_b", "hull_b")
            merged = merge_configs([build_probe_config(a), build_probe_config(b)])
            rig, log = bound_run(root, {"mod_a": queue / "A", "mod_b": queue / "B"}, "GRP-X",
                                 [f"{PREFIX}BF-PROBE|0.2.27|content-ids|OK|all-content|checked=2 failed=0", *lines], expected=("content_ids",))
            result = record_group(log, merged, queue, rig, test_id="GRP-X", today="2026-10-20")
            run = json.loads((queue / "_live" / "GRP-X.json").read_text(encoding="utf-8"))
        return result, run

    def test_record_keeps_the_map_and_warns_about_a_hollow_member(self) -> None:
        result, run = self._record([_line("mod_a", FULL), _line("mod_b", ZERO)])
        self.assertEqual(run["exercised"]["mod_a"]["hulls_built"], 3)
        self.assertEqual(result["hollow"], ["mod_b"])
        self.assertTrue(result["warnings"][0].startswith("HOLLOW: mod_b"))
        self.assertEqual(sorted(result["recorded"]), ["A", "B"])  # a warning, not a failure

    def test_a_log_without_lines_has_no_map_and_no_warning(self) -> None:
        result, run = self._record([])
        self.assertNotIn("exercised", run)
        self.assertEqual((result["hollow"], result["warnings"]), ([], []))


if __name__ == "__main__":
    unittest.main()
