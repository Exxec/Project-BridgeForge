"""B6 (ROADMAP item 73): local-weapon-spec-unregistered row fixer.

Fixture: Valkyrians `original/` (laserblaster.wpn is unregistered; valk_minimi is a registered BALLISTIC SMALL
projectile weapon), trimmed to the columns that matter.
"""
from __future__ import annotations

import csv
import io
import unittest
from pathlib import Path

from bridgeforge.fixers import SUPPORTED_FINDINGS, FixerError, compute_fix
from bridgeforge.scanner import scan_mod
from tests.support import resolved_temp_dir

FINDING = "local-weapon-spec-unregistered"
HEADER = "name,id,tier,rarity,base value,range,damage/second,damage/shot,emp,impact,turn rate,OPs,type,hints,tags,tech/manufacturer"
CSV_TEXT = "\n".join([
    HEADER,
    "#small,,,,,,,,,,,,,,,",
    'Minimi DSC,valk_minimi,1,,2600,650,,20,,5,35,8,KINETIC,,"kinetic9,valk_enigma_bp",Valkyrie - Enigma Inc.',
    'Big Gun,valk_big,3,,9000,900,,200,,5,10,20,HIGH_EXPLOSIVE,,"he9",Valkyrie - Enigma Inc.',
    "",
])


def _wpn(weapon: str, kind: str = "BALLISTIC", size: str = "SMALL", spec_class: str = "projectile", sprite: str = "graphics/w/base.png") -> str:
    return (
        "{\n"
        f'\t"id":"{weapon}",  # this id must match what\'s in the spreadsheet\n'
        f'\t"specClass":"{spec_class}",\n\t"type":"{kind}",\n\t"size":"{size}",\n'
        f'\t"turretSprite":"{sprite}",\n\t"hardpointSprite":"{sprite}",\n'
        '\t"barrelMode":"ALTERNATING", # or LINKED\n}\n'
    )


def _mod(root: Path, extra_wpn: str | None = None, csv_text: str = CSV_TEXT, sprite: bool = True) -> Path:
    weapons = root / "data" / "weapons"
    weapons.mkdir(parents=True)
    (weapons / "weapon_data.csv").write_bytes(csv_text.encode())
    (weapons / "valk_minimi.wpn").write_text(_wpn("valk_minimi"), encoding="utf-8")
    (weapons / "valk_big.wpn").write_text(_wpn("valk_big", size="LARGE"), encoding="utf-8")
    (weapons / "laserblaster.wpn").write_text(extra_wpn or _wpn("laserblaster"), encoding="utf-8")
    if sprite:
        (root / "graphics" / "w").mkdir(parents=True)
        (root / "graphics" / "w" / "base.png").write_bytes(b"png")
    (root / "mod_info.json").write_text('{"id":"m","name":"m","version":"1","gameVersion":"0.98a-RC8"}', encoding="utf-8")
    return root


def _rows(path: Path) -> list[list[str]]:
    return list(csv.reader(io.StringIO(path.read_text(encoding="utf-8"), newline="")))


class LocalWeaponRowTests(unittest.TestCase):
    def test_supported(self) -> None:
        self.assertIn(FINDING, SUPPORTED_FINDINGS)

    def test_adds_a_row_copied_from_the_same_type_and_size_and_the_finding_clears(self) -> None:
        with resolved_temp_dir() as root:
            _mod(root)
            self.assertIn(FINDING, [f.id for f in scan_mod(root).findings])
            plan = compute_fix(root, FINDING, {})
            for change in plan.changes:
                change.path.write_bytes(change.after)
            rows = _rows(root / "data/weapons/weapon_data.csv")
            after = [f.id for f in scan_mod(root).findings]
        new = rows[-1]
        header = rows[0]
        record = dict(zip(header, new))
        self.assertEqual((record["name"], record["id"]), ("laserblaster", "laserblaster"))
        self.assertEqual((record["range"], record["damage/shot"], record["OPs"], record["type"]), ("650", "20", "8", "KINETIC"))
        self.assertEqual((record["tags"], record["hints"], record["tech/manufacturer"]), ("", "", ""))
        self.assertTrue(rows[-2][0].startswith("# BridgeForge proposal for laserblaster: copied from valk_minimi"))
        self.assertIn("range=650", rows[-2][0])
        self.assertEqual(len(rows[-2]), len(header))
        self.assertNotIn(FINDING, after)

    def test_second_run_computes_no_change(self) -> None:
        with resolved_temp_dir() as root:
            _mod(root)
            for change in compute_fix(root, FINDING, {}).changes:
                change.path.write_bytes(change.after)
            with self.assertRaises(FixerError):
                compute_fix(root, FINDING, {})

    def test_prefers_a_sibling_with_the_same_spec_class(self) -> None:
        with resolved_temp_dir() as root:
            _mod(root)
            (root / "data/weapons/valk_big.wpn").write_text(_wpn("valk_big", spec_class="beam"), encoding="utf-8")
            (root / "data/weapons/laserblaster.wpn").write_text(_wpn("laserblaster", spec_class="beam"), encoding="utf-8")
            plan = compute_fix(root, FINDING, {})
        self.assertIn("copied from valk_big", plan.changes[0].after.decode("utf-8"))

    def test_keeps_crlf_line_endings_and_existing_bytes(self) -> None:
        text = CSV_TEXT.replace("\n", "\r\n")
        with resolved_temp_dir() as root:
            _mod(root, csv_text=text)
            plan = compute_fix(root, FINDING, {})
        after = plan.changes[0].after
        self.assertTrue(after.startswith(text.encode()))
        self.assertEqual(after.count(b"\n"), after.count(b"\r\n"))

    def test_refuses_without_a_sibling_of_the_same_type_and_size(self) -> None:
        with resolved_temp_dir() as root:
            _mod(root, _wpn("laserblaster", kind="MISSILE"))
            with self.assertRaisesRegex(FixerError, "no registered weapon of type MISSILE and size SMALL"):
                compute_fix(root, FINDING, {})

    def test_refuses_when_a_sprite_is_missing(self) -> None:
        with resolved_temp_dir() as root:
            _mod(root, sprite=False)
            with self.assertRaisesRegex(FixerError, "sprite not found: graphics/w/base.png"):
                compute_fix(root, FINDING, {})

    def test_a_sprite_in_the_vanilla_core_counts(self) -> None:
        with resolved_temp_dir() as root:
            core = root / "core"
            (core / "graphics" / "w").mkdir(parents=True)
            (core / "graphics" / "w" / "base.png").write_bytes(b"png")
            mod = root / "mod"
            mod.mkdir()
            _mod(mod, sprite=False)
            plan = compute_fix(mod, FINDING, {"vanilla_core": core})
        self.assertIn("laserblaster", plan.changes[0].after.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
