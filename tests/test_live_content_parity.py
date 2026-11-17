"""ROADMAP 77.17: live content parity (expected ids from working/, judged against the probe's content-parity lines)."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from bridgeforge.live.live_content_parity import expected_content, parity_findings
from bridgeforge.probe.probe_config import build_probe_config
from bridgeforge.probe.probe_group import group_report, merge_configs
from tests.support import resolved_temp_dir

_LINE = "9 [Thread-2] INFO  com.bridgeforge.probe.ProbeLog  - BF-PROBE|0.2.27|content-parity|{status}|mod={mod}|{detail}\n"


def _mod(root: Path, mod_id: str, *, rules: bool = True) -> Path:
    working = root / mod_id / "working"
    for folder in ("hulls", "weapons", "campaign"):
        (working / "data" / folder).mkdir(parents=True)
    (working / "mod_info.json").write_text(json.dumps({"id": mod_id, "gameVersion": "0.98a-RC8"}), encoding="utf-8")
    (working / "data" / "hulls" / "ship_data.csv").write_text("id,hints\nhull_a,\nhull_b,\n", encoding="utf-8")
    (working / "data" / "hulls" / "wing_data.csv").write_text("id,\nwing_a,\n", encoding="utf-8")
    (working / "data" / "hulls" / "hull_mods.csv").write_text("name,id\nMod A,hm_a\n", encoding="utf-8")
    (working / "data" / "weapons" / "weapon_data.csv").write_text("name,id\n#comment,#skip\nGun,gun_a\n", encoding="utf-8")
    (working / "data" / "campaign" / "industries.csv").write_text("name,id\nInd,ind_a\n", encoding="utf-8")
    (working / "data" / "campaign" / "market_conditions.csv").write_text("name,id\nCond,cond_a\n", encoding="utf-8")
    (working / "data" / "campaign" / "submarkets.csv").write_text("name,id\nSub,sub_a\n", encoding="utf-8")
    if rules:
        (working / "data" / "campaign" / "rules.csv").write_text("id,trigger\nrule_1,T\nrule_2,T\nrule_2,T\n", encoding="utf-8")
    return working


class ExpectedContentTests(unittest.TestCase):
    def test_every_kind_is_read_by_id_and_comments_and_duplicates_dropped(self) -> None:
        with resolved_temp_dir() as root:
            expected = expected_content(_mod(root, "m"), systems=["Sys"], body_types=["t1"])
        self.assertEqual(expected["rules"], ["rule_1", "rule_2"])
        self.assertEqual(expected["hulls"], ["hull_a", "hull_b"])
        self.assertEqual(expected["weapons"], ["gun_a"])
        self.assertEqual((expected["wings"], expected["hullmods"], expected["industries"]), (["wing_a"], ["hm_a"], ["ind_a"]))
        self.assertEqual((expected["conditions"], expected["submarkets"]), (["cond_a"], ["sub_a"]))
        self.assertEqual((expected["systems"], expected["planet_types"]), (["Sys"], ["t1"]))

    def test_a_row_whose_first_cell_is_a_comment_is_skipped_whatever_its_id(self) -> None:
        # Navarchy of Tania 1.0.1's "#Weapon Name,id,..." template row (G4-LIVE-0985a-20261117): the game skips it, so must we.
        with resolved_temp_dir() as root:
            working = _mod(root, "m")
            (working / "data" / "weapons" / "weapon_data.csv").write_text("name,id,tier\nGun,gun_a,1\n#Weapon Name,id,1\n", encoding="utf-8")
            expected = expected_content(working)
        self.assertEqual(expected["weapons"], ["gun_a"])

    def test_an_absent_rules_file_expects_no_rules(self) -> None:
        with resolved_temp_dir() as root:
            expected = expected_content(_mod(root, "m", rules=False))
        self.assertNotIn("rules", expected)

    def test_the_probe_config_carries_the_expectations_per_mod(self) -> None:
        with resolved_temp_dir() as root:
            config = build_probe_config(_mod(root, "m"))
            merged = merge_configs([config, build_probe_config(_mod(root, "n", rules=False))])
        self.assertEqual(config["content_parity"]["m"]["rules"], ["rule_1", "rule_2"])
        self.assertEqual(sorted(merged["content_parity"]), ["m", "n"])
        self.assertNotIn("rules", merged["content_parity"]["n"])


class ParityVerdictTests(unittest.TestCase):
    def _report(self, root: Path, lines: str) -> dict:
        merged = merge_configs([build_probe_config(_mod(root, "mod_a")), build_probe_config(_mod(root, "mod_b"))])
        log = root / "run.log"
        log.write_text("5 [main] INFO x - Starting\n9 [t] INFO x - BF-PROBE|0.2.27|content-ids|OK|all-content|checked=1 failed=0\n" + lines,
                       encoding="utf-8")
        return {"report": group_report(log, merged), "findings": parity_findings(log, merged)}

    def test_fix_001_shape_rules_csv_not_loaded_fails_only_that_member(self) -> None:
        rest = "hulls=2/2,weapons=1/1,wings=1/1,hullmods=1/1,industries=1/1,conditions=1/1,submarkets=1/1,src_hulls=2"
        with resolved_temp_dir() as root:
            result = self._report(
                root,
                _LINE.format(status="INFO", mod="mod_a", detail="rules=0/2," + rest)
                + _LINE.format(status="FAIL", mod="mod_a", detail="kind=rules missing 0/2: rule_1,rule_2")
                + _LINE.format(status="INFO", mod="mod_b", detail="rules=2/2," + rest))
        members = result["report"]["members"]
        self.assertEqual(members["mod_a"]["verdict"], "FAIL")
        self.assertIn("rule_1, rule_2", members["mod_a"]["failures"][0])
        self.assertEqual(members["mod_b"]["verdict"], "PASS")
        self.assertEqual(result["findings"]["mod_a"]["missing"], {"rules": ["rule_1", "rule_2"]})
        self.assertEqual(result["findings"]["mod_b"]["status"], "PASS")

    def test_excess_is_information_and_never_a_failure(self) -> None:
        with resolved_temp_dir() as root:
            result = self._report(
                root,
                _LINE.format(status="INFO", mod="mod_a", detail="hulls=2/2,src_hulls=5")
                + _LINE.format(status="INFO", mod="mod_b", detail="hulls=2/2,src_hulls=2"))
        self.assertEqual(result["findings"]["mod_a"]["excess"], {"hulls": 3})
        self.assertEqual(result["report"]["members"]["mod_a"]["verdict"], "PASS")

    def test_a_probe_without_the_stage_is_not_observed_rather_than_failed(self) -> None:
        with resolved_temp_dir() as root:
            result = self._report(root, "")
        self.assertEqual(result["findings"]["mod_a"]["status"], "NOT_OBSERVED")
        self.assertEqual(result["report"]["members"]["mod_a"]["verdict"], "PASS")

    def test_the_listed_missing_ids_are_capped_but_the_count_is_true(self) -> None:
        ids = ",".join(f"r{n}" for n in range(40)) + " ..."
        with resolved_temp_dir() as root:
            result = self._report(root, _LINE.format(status="FAIL", mod="mod_a", detail=f"kind=rules missing 10/100: {ids}"))
        self.assertEqual(result["findings"]["mod_a"]["missing_counts"], {"rules": 90})
        self.assertEqual(len(result["findings"]["mod_a"]["missing"]["rules"]), 40)


class ParityAcceptanceTests(unittest.TestCase):
    """Owner-accepted missing ids: probe_accepted.json entries with "check": "content-parity", "subject": "<kind>:<id>"
    (Musashi Manufactorum's CSV rows with no .ship/.wpn file, owner 2026-11-17)."""

    def _report(self, root: Path, lines: str, accepted: dict) -> dict:
        merged = merge_configs([build_probe_config(_mod(root, "mod_a")), build_probe_config(_mod(root, "mod_b"))])
        log = root / "run.log"
        log.write_text("5 [main] INFO x - Starting\n9 [t] INFO x - BF-PROBE|0.2.27|content-ids|OK|all-content|checked=1 failed=0\n" + lines,
                       encoding="utf-8")
        return group_report(log, merged, accepted=accepted)

    @staticmethod
    def _accept(*subjects: str) -> dict:
        return {"mod_a": [{"check": "content-parity", "subject": subject, "reason": "test"} for subject in subjects]}

    def test_every_missing_id_accepted_passes_the_member_and_lists_them(self) -> None:
        with resolved_temp_dir() as root:
            report = self._report(root, _LINE.format(status="FAIL", mod="mod_a", detail="kind=hulls missing 0/2: hull_a,hull_b"),
                                  self._accept("hulls:hull_a", "hulls:hull_b"))
        member = report["members"]["mod_a"]
        self.assertEqual(member["verdict"], "PASS")
        self.assertEqual(member["failures"], [])
        self.assertIn("content-parity|hulls|missing 2 accepted: hull_a, hull_b", member["accepted"])
        self.assertEqual(report["content_parity"]["mod_a"]["status"], "PASS")

    def test_an_id_not_accepted_still_fails_with_the_true_count(self) -> None:
        with resolved_temp_dir() as root:
            report = self._report(root, _LINE.format(status="FAIL", mod="mod_a", detail="kind=hulls missing 0/2: hull_a,hull_b"),
                                  self._accept("hulls:hull_a"))
        member = report["members"]["mod_a"]
        self.assertEqual(member["verdict"], "FAIL")
        self.assertEqual(member["failures"], ["content-parity|hulls|missing 1: hull_b"])

    def test_a_bare_kind_or_another_check_accepts_nothing(self) -> None:
        with resolved_temp_dir() as root:
            report = self._report(root, _LINE.format(status="FAIL", mod="mod_a", detail="kind=hulls missing 1/2: hull_b"),
                                  {"mod_a": [{"check": "content-parity", "subject": "hulls", "reason": "t"},
                                             {"check": "faction-fleet-gen", "subject": "hulls:hull_b", "reason": "t"}]})
        self.assertEqual(report["members"]["mod_a"]["verdict"], "FAIL")
        self.assertNotIn("accepted", report["members"]["mod_a"])

    def test_a_capped_list_keeps_failing_for_the_unlisted_ids(self) -> None:
        ids = [f"r{n}" for n in range(40)]
        with resolved_temp_dir() as root:
            report = self._report(root, _LINE.format(status="FAIL", mod="mod_a", detail=f"kind=rules missing 10/100: {','.join(ids)} ..."),
                                  self._accept(*(f"rules:{ident}" for ident in ids)))
        member = report["members"]["mod_a"]
        self.assertEqual(member["verdict"], "FAIL")
        self.assertEqual(member["failures"], ["content-parity|rules|missing 50: "])


if __name__ == "__main__":
    unittest.main()
