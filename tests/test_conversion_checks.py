"""Total-conversion checks found on Ironclads (GRP10B-GRP10F, 2026-10-05)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bridgeforge.fixers import FixerError, apply_fix, compute_fix
from bridgeforge.scanner import _load_lenient_json_file, scan_mod


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


FACTION = ('{\n\t"id":"hegemony",\n\t"shipRoles":{\n\t\t"combatSmall":{\n\t\t\t"includeDefault":true,\n\t\t\t"gremlin_Strike":10,\n'
           '\t\t\t"kept_Std":5,\n\t\t},\n\t},\n}\n')


def _fixture(directory: str, *, replaces_hulls: bool = True, stub: str | None = None) -> tuple[Path, Path]:
    base = Path(directory)
    mod, core = base / "mod", base / "core"
    _write(core / "data" / "world" / "factions" / "hegemony.faction", FACTION)
    _write(core / "data" / "world" / "factions" / "factions.csv", "faction\ndata/world/factions/neutral.faction\ndata/world/factions/hegemony.faction\n")
    _write(core / "data" / "variants" / "gremlin_Strike.variant", '{"variantId":"gremlin_Strike","hullId":"gremlin"}')
    _write(core / "data" / "variants" / "kept_Std.variant", '{"variantId":"kept_Std","hullId":"kept"}')
    replace = '"data/hulls/ship_data.csv",' if replaces_hulls else ""
    _write(mod / "mod_info.json", '{"id":"conv",\n"replace":[\n%s\n"data/other.json",\n]}' % replace)
    _write(mod / "data" / "hulls" / "ship_data.csv", "id,name\nkept,Kept\n")
    if stub is not None:
        _write(mod / "data" / "world" / "factions" / "hegemony.faction", stub)
    return mod, core


class FactionNamesRemovedHullTests(unittest.TestCase):
    def test_flagged_and_fixed_with_a_replaced_copy_listed_in_mod_info(self) -> None:
        # Ironclads: "Ship hull variant [gremlin_Strike] not found!" from vanilla's hegemony.faction (GRP10C-20261005)
        with tempfile.TemporaryDirectory() as directory:
            mod, core = _fixture(directory, stub='{\n\t"showInIntelTab":false,\n}\n')
            found = [f for f in scan_mod(mod, vanilla_core=core).findings if f.id == "conversion-faction-names-removed-hull"]
            apply_fix(compute_fix(mod, "conversion-faction-names-removed-hull", {"vanilla_core": core}))
            text = (mod / "data" / "world" / "factions" / "hegemony.faction").read_text(encoding="utf-8")
            data = _load_lenient_json_file(mod / "data" / "world" / "factions" / "hegemony.faction")
            info = _load_lenient_json_file(mod / "mod_info.json")
            after = [f for f in scan_mod(mod, vanilla_core=core).findings if f.id == "conversion-faction-names-removed-hull"]
        self.assertEqual(found[0].evidence, ["hegemony.faction:gremlin_Strike"])
        self.assertNotIn("gremlin_Strike", text.split("\n\t\"id\"")[1])
        self.assertEqual(data["shipRoles"]["combatSmall"], {"includeDefault": True, "kept_Std": 5})
        self.assertIs(data["showInIntelTab"], False)
        self.assertIn("data/world/factions/hegemony.faction", info["replace"])
        self.assertEqual(info["replace"][0], "data/hulls/ship_data.csv")
        self.assertEqual(after, [])

    def test_a_mod_that_keeps_vanilla_hulls_is_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod, core = _fixture(directory, replaces_hulls=False)
            found = [f for f in scan_mod(mod, vanilla_core=core).findings if f.id == "conversion-faction-names-removed-hull"]
        self.assertEqual(found, [])

    def test_an_overlay_with_real_content_is_left_for_the_owner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod, core = _fixture(directory, stub='{"id":"hegemony","displayName":"Mine"}')
            with self.assertRaises(FixerError) as caught:
                compute_fix(mod, "conversion-faction-names-removed-hull", {"vanilla_core": core})
        self.assertIn("more than a showInIntelTab stub", str(caught.exception))


class FactionsCsvRelistsNeutralTests(unittest.TestCase):
    def test_neutral_row_is_flagged_and_removed_keeping_line_endings(self) -> None:
        # Ironclads GRP10D-20261005: neutral loaded after other factions, NullPointerException in Faction.<clinit>
        with tempfile.TemporaryDirectory() as directory:
            mod, core = _fixture(directory)
            listing = mod / "data" / "world" / "factions" / "factions.csv"
            listing.parent.mkdir(parents=True, exist_ok=True)
            listing.write_bytes(b"faction\r\ndata/world/factions/pirates.faction\r\ndata/world/factions/neutral.faction\r\ndata/world/factions/mine.faction\r\n")
            found = [f for f in scan_mod(mod, vanilla_core=core).findings if f.id == "factions-csv-relists-neutral"]
            after = compute_fix(mod, "factions-csv-relists-neutral").changes[0].after
        self.assertEqual(len(found), 1)
        self.assertEqual(after, b"faction\r\ndata/world/factions/pirates.faction\r\ndata/world/factions/mine.faction\r\n")


if __name__ == "__main__":
    unittest.main()
