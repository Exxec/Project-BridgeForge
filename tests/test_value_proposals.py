"""Value proposals from comparable rows (ROADMAP item 73 B5): wing op cost and carrier fighter bays."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from bridgeforge.fixers import FixerError, apply_fix, compute_fix
from bridgeforge.models import TargetProfile
from bridgeforge.scanner import scan_mod
from bridgeforge.value_proposals import (
    ValueProposalError,
    apply_sheet,
    approved_values,
    build_sheet,
    propose_wing_costs,
    read_sheet,
    write_sheet,
)
from tests.support import resolved_temp_dir

WING_HEADER = "id,variant,tags,tier,rarity,fleet pts,op cost,formation,range,attackRunRange,attackPositionOffset,num,role,role desc,refit,base value\n"
MOD_WINGS = (WING_HEADER
             + "my_a_wing,my_a_Fighter,,0,,6,8,V,0,500,,3,FIGHTER,Fighter,10,0\n"
             + "my_b_wing,my_b_Fighter,,0,,6,10,V,0,500,,3,FIGHTER,Fighter,10,0\n"
             + "my_c_wing,my_c_Fighter,,0,,6,13,V,0,500,,3,FIGHTER,Fighter,10,0\n"
             + "my_two_wing,my_two_Fighter,,0,,6,20,V,0,500,,2,FIGHTER,Fighter,10,0\n"
             + "my_blank_wing,my_blank_Fighter,,0,,6,,V,0,500,,3,FIGHTER,Fighter,10,0\n"
             + "my_support_wing,my_support_Fighter,,0,,7,,V,0,500,,2,SUPPORT,Support,10,0\n")
CORE_WINGS = (WING_HEADER
              + "broadsword_wing,broadsword_Fighter,,0,,6,8,V,0,500,,2,SUPPORT,Support,10,0\n"
              + "xyphos_wing,xyphos_Fighter,,0,,7,18,V,0,500,,2,SUPPORT,Support,10,0\n"
              + "zero_wing,zero_Fighter,,0,,7,0,V,0,500,,2,SUPPORT,Support,10,0\n")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _wing_workspace(root: Path) -> tuple[Path, Path]:
    workspace, core = root / "ws", root / "core"
    _write(workspace / "working" / "mod_info.json", '{"id":"fixture","name":"Fixture","gameVersion":"0.98a"}')
    _write(workspace / "working" / "data" / "hulls" / "wing_data.csv", MOD_WINGS)
    _write(core / "data" / "hulls" / "wing_data.csv", CORE_WINGS)
    return workspace, core


class WingProposalTests(unittest.TestCase):
    def test_median_from_three_comparable_own_rows_and_vanilla_fallback(self) -> None:
        with resolved_temp_dir() as root:
            workspace, core = _wing_workspace(root)
            by_target = {r["target"]: r for r in propose_wing_costs(workspace / "working", core)}
        own = by_target["my_blank_wing"]
        self.assertEqual(own["proposed"], "10")  # median of 8, 10, 13 (role FIGHTER, size 3); the size-2 wing is not comparable
        self.assertIn("3 own wing(s)", own["basis"])
        self.assertIn("my_a_wing=8", own["comparison"])
        self.assertNotIn("my_two_wing", own["comparison"])
        support = by_target["my_support_wing"]
        self.assertEqual(support["proposed"], "13")  # RC8 SUPPORT size 2: 8 and 18, the 0-cost wing ignored; 13 is the median
        self.assertIn("RC8", support["basis"])
        self.assertNotIn("zero_wing", support["comparison"])

    def test_no_comparable_row_leaves_the_proposal_blank(self) -> None:
        with resolved_temp_dir() as root:
            workspace, _ = _wing_workspace(root)
            by_target = {r["target"]: r for r in propose_wing_costs(workspace / "working", None)}
        self.assertEqual(by_target["my_support_wing"]["proposed"], "")
        self.assertEqual(by_target["my_blank_wing"]["proposed"], "10")


class SheetApplyTests(unittest.TestCase):
    def test_only_approved_rows_are_applied_and_the_finding_clears(self) -> None:
        with resolved_temp_dir() as root:
            workspace, core = _wing_workspace(root)
            sheet = root / "sheet.csv"
            rows = build_sheet(workspace, core)
            write_sheet(rows, sheet)
            self.assertEqual({r["target"] for r in read_sheet(sheet)}, {"my_blank_wing", "my_support_wing"})
            # approve one row as proposed, leave the other row unapproved
            lines = sheet.read_text(encoding="utf-8").splitlines()
            sheet.write_text("\n".join(line + ("yes" if "my_blank_wing" in line else "") for line in lines) + "\n", encoding="utf-8")
            outcome = apply_sheet(workspace, sheet)
            wing_text = (workspace / "working" / "data" / "hulls" / "wing_data.csv").read_text(encoding="utf-8")
        self.assertEqual(outcome["approved"], {"wing-op-cost": {"my_blank_wing": "10"}, "carrier-bays": {}})
        self.assertIn("my_blank_wing,my_blank_Fighter,,0,,6,10,V", wing_text)
        self.assertIn("my_support_wing,my_support_Fighter,,0,,7,,V", wing_text)  # unapproved: untouched

    def test_a_number_in_the_approved_column_overrides_the_proposal(self) -> None:
        rows = [{"kind": "wing-op-cost", "target": "w", "file": "f", "proposed": "10", "basis": "", "comparison": "", "approved": "12"},
                {"kind": "wing-op-cost", "target": "x", "file": "f", "proposed": "10", "basis": "", "comparison": "", "approved": "no"},
                {"kind": "wing-op-cost", "target": "y", "file": "f", "proposed": "", "basis": "", "comparison": "", "approved": "yes"}]
        with self.assertRaises(ValueProposalError):  # "yes" on a row with no proposal is not a number
            approved_values(rows)
        self.assertEqual(approved_values(rows[:2])["wing-op-cost"], {"w": "12"})

    def test_the_fixer_takes_proposals_without_a_vanilla_core_and_rejects_bad_costs(self) -> None:
        with resolved_temp_dir() as root:
            workspace, _ = _wing_workspace(root)
            mod = workspace / "working"
            for bad in ("0", "abc", "1000", "-3"):
                with self.assertRaises(FixerError):
                    compute_fix(mod, "wing-op-cost-blank", {"proposals": {"my_blank_wing": bad}})
            apply_fix(compute_fix(mod, "wing-op-cost-blank", {"proposals": {"my_blank_wing": "11", "my_support_wing": "15"}}))
            after = [f.id for f in scan_mod(mod, TargetProfile("0.98a-RC8", 17)).findings]
            with self.assertRaises(FixerError):  # idempotent: nothing blank is left to fill
                compute_fix(mod, "wing-op-cost-blank", {"proposals": {"my_blank_wing": "11"}})
        self.assertNotIn("wing-op-cost-blank", after)

    def test_command_writes_a_sheet_then_dry_run_changes_nothing(self) -> None:
        import contextlib
        import io

        from bridgeforge.cli import main

        with resolved_temp_dir() as root:
            workspace, core = _wing_workspace(root)
            sheet = root / "sheet.csv"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["value-proposals", str(workspace), "--write", str(sheet), "--vanilla-core", str(core)]), 0)
                sheet.write_text(sheet.read_text(encoding="utf-8").replace(",\n", ",yes\n"), encoding="utf-8")
                self.assertEqual(main(["value-proposals", str(workspace), "--apply", str(sheet), "--dry-run"]), 0)
            unchanged = (workspace / "working" / "data" / "hulls" / "wing_data.csv").read_text(encoding="utf-8")
        self.assertEqual(unchanged, MOD_WINGS)

    def test_a_sheet_without_the_columns_is_refused(self) -> None:
        with resolved_temp_dir() as root:
            bad = root / "bad.csv"
            bad.write_text("a,b\n1,2\n", encoding="utf-8")
            with self.assertRaises(ValueProposalError):
                read_sheet(bad)


class BayProposalTests(unittest.TestCase):
    def test_hull_without_slots_gets_the_median_of_own_carriers_of_its_size(self) -> None:
        def ship(hull_id: str, size: str, bays: int) -> str:
            slots = [{"id": f"WS{i}", "type": "LAUNCH_BAY", "angle": 0, "arc": 360, "mount": "HIDDEN", "size": "MEDIUM", "locations": [0, 0]} for i in range(bays)]
            return json.dumps({"hullId": hull_id, "hullName": hull_id, "hullSize": size, "weaponSlots": slots})

        with resolved_temp_dir() as root:
            workspace, core = root / "ws", root / "core"
            mod = workspace / "working"
            _write(mod / "mod_info.json", '{"id":"fixture","name":"Fixture","gameVersion":"0.95a"}')
            _write(mod / "data" / "hulls" / "ship_data.csv", "name,id,designation,hangar\nA,a_hull,,3\nB,b_hull,,2\nC,c_hull,,4\nD,d_hull,,1\n")
            for hull_id, size, bays in (("a_hull", "CRUISER", 2), ("b_hull", "CRUISER", 4), ("c_hull", "CRUISER", 0), ("d_hull", "DESTROYER", 0)):
                _write(mod / "data" / "hulls" / f"{hull_id}.ship", ship(hull_id, size, bays))
            _write(core / "data" / "hulls" / "ship_data.csv", "name,id,fighter bays\nVan,van_hull,3\nVan2,van2_hull,1\n")
            _write(core / "data" / "hulls" / "van_hull.ship", ship("van_hull", "DESTROYER", 0))
            _write(core / "data" / "hulls" / "van2_hull.ship", ship("van2_hull", "DESTROYER", 0))
            by_target = {r["target"]: r for r in build_sheet(workspace, core) if r["kind"] == "carrier-bays"}
            sheet = root / "bays.csv"
            write_sheet(list(by_target.values()), sheet)
            sheet.write_text(sheet.read_text(encoding="utf-8").replace(",\n", ",yes\n"), encoding="utf-8")
            outcome = apply_sheet(workspace, sheet)
            ship_data = (mod / "data" / "hulls" / "ship_data.csv").read_text(encoding="utf-8")
        self.assertEqual(by_target["a_hull"]["proposed"], "2")  # the hull's own slots
        self.assertEqual(by_target["b_hull"]["proposed"], "4")
        self.assertEqual(by_target["c_hull"]["proposed"], "3")  # no slots: median of own cruisers (2, 4)
        self.assertIn("own carrier", by_target["c_hull"]["basis"])
        self.assertEqual(by_target["d_hull"]["proposed"], "2")  # no own destroyer: RC8 destroyers 3 and 1 -> 2
        self.assertIn("RC8", by_target["d_hull"]["basis"])
        self.assertEqual(outcome["approved"]["carrier-bays"], {"a_hull": "2", "b_hull": "4", "c_hull": "3", "d_hull": "2"})
        self.assertIn("fighter bays", ship_data.splitlines()[0])


if __name__ == "__main__":
    unittest.main()
