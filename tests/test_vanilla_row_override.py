"""csv-vanilla-row-override: rows of a mod's own data tables that repeat an id RC8 defines (Yellowjackets, 2026-10-10)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bridgeforge.fixers import FixerError, apply_fix, compute_fix
from bridgeforge.scan.scanner import scan_mod

CHECK = "csv-vanilla-row-override"
INFO = '{"id":"demo","name":"Demo","version":"1.0","gameVersion":"0.98a-RC8"%s}'


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _fixture(directory: str, *, replace_table: bool = False) -> tuple[Path, Path]:
    base = Path(directory)
    mod, core = base / "mod", base / "core"
    _write(core / "data" / "hulls" / "ship_data.csv", "name,id,hitpoints\r\nBrawler,brawler,2000\r\nAtlas,atlas,3000\r\n")
    replace = ',"replace":["data/hulls/ship_data.csv"]' if replace_table else ""
    _write(mod / "mod_info.json", INFO % replace)
    # a quoted cell with a line break inside the vanilla row's record: the whole record must go
    _write(mod / "data" / "hulls" / "ship_data.csv",
           'name,id,hitpoints\r\nTermite,yj_termite,1500\r\nBrawler,brawler,1800\r\n"Atlas\r\nMk",atlas,2900\r\nBee,yj_bee,900\r\n')
    return mod, core


class VanillaRowOverrideTests(unittest.TestCase):
    def test_vanilla_rows_are_flagged_and_removed_keeping_the_mods_own(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod, core = _fixture(directory)
            found = [f for f in scan_mod(mod, vanilla_core=core).findings if f.id == CHECK]
            apply_fix(compute_fix(mod, CHECK, {"vanilla_core": core}))
            text = (mod / "data" / "hulls" / "ship_data.csv").read_bytes().decode("utf-8")
            after = [f for f in scan_mod(mod, vanilla_core=core).findings if f.id == CHECK]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].classification, "REVIEW")
        self.assertEqual(sorted(e.split(":")[1] for e in found[0].evidence), ["atlas", "brawler"])
        self.assertEqual(text, "name,id,hitpoints\r\nTermite,yj_termite,1500\r\nBee,yj_bee,900\r\n")
        self.assertEqual(after, [])

    def test_a_table_the_mod_replaces_is_its_own_whole_table(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod, core = _fixture(directory, replace_table=True)
            found = [f for f in scan_mod(mod, vanilla_core=core).findings if f.id == CHECK]
        self.assertEqual(found, [])

    def test_nothing_is_claimed_without_vanilla_core(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod, _core = _fixture(directory)
            found = [f for f in scan_mod(mod).findings if f.id == CHECK]
        self.assertEqual(found, [])

    def test_the_fixer_needs_vanilla_core_and_refuses_a_clean_mod(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod, core = _fixture(directory)
            with self.assertRaises(FixerError):
                compute_fix(mod, CHECK, {})
            apply_fix(compute_fix(mod, CHECK, {"vanilla_core": core}))
            with self.assertRaises(FixerError):
                compute_fix(mod, CHECK, {"vanilla_core": core})


if __name__ == "__main__":
    unittest.main()
