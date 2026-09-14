"""P13 checks from the Chinese mods (2026-09-14): non-ASCII ids/paths, non-UTF-8 data, full-width numbers."""

import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.models import TargetProfile
from bridgeforge.scanner import scan_mod


def _mod(root: Path) -> Path:
    mod = root / "mod"
    (mod / "data" / "hulls").mkdir(parents=True)
    (mod / "mod_info.json").write_text(json.dumps({"id": "fx", "name": "fx", "version": "1", "gameVersion": "0.98a-RC8"}), encoding="utf-8")
    return mod


def _ids(result, finding_id: str) -> list:
    return [f for f in result.findings if f.id == finding_id]


class NonAsciiNameTests(unittest.TestCase):
    def test_non_ascii_ids_and_shipped_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory))
            # The last row is prose spilled into the id column (Omega-Trauma): not an id.
            (mod / "data" / "hulls" / "ship_data.csv").write_text("name,id\n护卫舰,fx_frigate\nB,fx_护卫\n#注释,#x\nC,\"On the peak， a tower\"\n", encoding="utf-8")
            (mod / "data" / "hulls" / "a.ship").write_text(json.dumps({"hullId": "fx_舰"}), encoding="utf-8")
            (mod / "graphics").mkdir()
            (mod / "graphics" / "舰.png").write_bytes(b"x")
            (mod / "graphics" / "ok.png").write_bytes(b"x")
            result = scan_mod(mod, TargetProfile())
        ids = _ids(result, "non-ascii-identifier")
        self.assertEqual(len(ids), 1)
        self.assertEqual(ids[0].evidence, ["data/hulls/ship_data.csv: fx_护卫", "data/hulls/a.ship: hullId=fx_舰"])  # names are player text: fine
        self.assertEqual(_ids(result, "non-ascii-file-path")[0].evidence, ["graphics/舰.png"])


class DataEncodingTests(unittest.TestCase):
    def test_gbk_file_is_reported_with_its_likely_encoding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory))
            (mod / "data" / "hulls" / "ship_data.csv").write_bytes("name,id\nA,fx_a\n护卫舰,fx_b\n".encode("gbk"))
            (mod / "data" / "hulls" / "b.ship").write_text(json.dumps({"hullId": "fx_b", "hullName": "护卫舰"}), encoding="utf-8")
            result = scan_mod(mod, TargetProfile())
        bad = _ids(result, "data-file-not-utf8")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0].evidence, ["data/hulls/ship_data.csv: line 3, decodes as gb18030"])


class FullwidthNumberTests(unittest.TestCase):
    def test_numbers_in_fullwidth_are_reported_but_prose_is_not(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory))
            (mod / "data" / "hulls" / "ship_data.csv").write_text("name,id,hitpoints,max speed,designation\nA,fx_a,１５００,0。5,护卫舰，快速\nB,fx_b,1500,50,\"3，000 tons\"\n", encoding="utf-8")
            result = scan_mod(mod, TargetProfile())
        hits = _ids(result, "csv-fullwidth-number")
        self.assertEqual(len(hits), 1)
        self.assertEqual(len(hits[0].evidence), 2)
        self.assertIn("[hitpoints]: '１５００' -> 1500", hits[0].evidence[0])
        self.assertIn("[max speed]: '0。5' -> 0.5", hits[0].evidence[1])


if __name__ == "__main__":
    unittest.main()
