"""`fix --finding carrier-bays-proposal --hull-zero-no-evidence`: 0 bays where the data shows nothing can launch (2026-10-10)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bridgeforge.fixers import FixerError, apply_fix, compute_fix
from bridgeforge.scanner import carrier_bays_without_evidence

SHIP_DATA = ("name,id,designation,system id,hangar,hints\r\n"
             "Termite,yj_termite,Frigate,,5,\r\n"          # hangar value, no bay slot, no wings: nothing can launch
             "Carrier,yj_carrier,Cruiser,,3,\r\n"          # has a LAUNCH_BAY slot: a real carrier, left to the owner
             "Winged,yj_winged,Destroyer,,2,\r\n"          # a variant carries wings: left to the owner
             "Plain,yj_plain,Frigate,,,\r\n")              # no hangar value: nothing to resolve


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _mod(directory: str) -> Path:
    root = Path(directory) / "mod"
    _write(root / "mod_info.json", '{"id":"demo","name":"Demo","version":"1.0","gameVersion":"0.98a-RC8"}')
    _write(root / "data" / "hulls" / "ship_data.csv", SHIP_DATA)
    for hull, slots in (("yj_termite", ['{"type":"ENERGY"}']), ("yj_carrier", ['{"type":"LAUNCH_BAY"}', '{"type":"LAUNCH_BAY"}']),
                        ("yj_winged", ['{"type":"ENERGY"}']), ("yj_plain", ['{"type":"ENERGY"}'])):
        _write(root / "data" / "hulls" / f"{hull}.ship", '{"hullId":"%s","hullSize":"FRIGATE","weaponSlots":[%s]}' % (hull, ",".join(slots)))
    _write(root / "data" / "variants" / "yj_winged_std.variant", '{"hullId":"yj_winged","variantId":"yj_winged_std","wings":["talon_wing"]}')
    return root


class CarrierBaysZeroTests(unittest.TestCase):
    def test_only_hulls_with_a_hangar_value_and_no_way_to_launch_are_named(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            found = carrier_bays_without_evidence(_mod(directory), None)
        self.assertEqual(found, ["yj_termite"])

    def test_the_option_writes_zero_for_those_hulls_and_leaves_the_rest_blank(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _mod(directory)
            apply_fix(compute_fix(root, "carrier-bays-proposal", {"hull_zero_no_evidence": True}))
            lines = (root / "data" / "hulls" / "ship_data.csv").read_text(encoding="utf-8").splitlines()
        header = lines[0].split(",")
        bays = header.index("fighter bays")
        by_id = {line.split(",")[1]: line.split(",")[bays] for line in lines[1:]}
        self.assertEqual(by_id, {"yj_termite": "0", "yj_carrier": "", "yj_winged": "", "yj_plain": ""})

    def test_an_explicit_hull_value_wins_and_a_mod_with_nothing_to_resolve_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _mod(directory)
            apply_fix(compute_fix(root, "carrier-bays-proposal", {"hulls": ["yj_termite=1"], "hull_zero_no_evidence": True}))
            text = (root / "data" / "hulls" / "ship_data.csv").read_text(encoding="utf-8")
            self.assertIn("Termite,yj_termite,Frigate,,5,,1", text)
            with self.assertRaises(FixerError):
                compute_fix(root, "carrier-bays-proposal", {"hull_zero_no_evidence": True})


if __name__ == "__main__":
    unittest.main()
