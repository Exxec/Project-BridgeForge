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


class RulesCsvDuplicateIdTests(unittest.TestCase):
    def test_repeated_ids_are_flagged_and_renamed_touching_only_the_id_cell(self) -> None:
        # Ironclads: one marketPostOpenPiratesHostile rule per faction, as 0.7.2 allowed (GRP10J-20261005)
        from bridgeforge.fixers import compute_fix

        content = ('id,trigger,conditions,script,text,options,notes\r\n'
                   '# comment row,,,,,,\r\n'
                   'marketPostOpen,MarketPostOpen,$a,FireAll X,,,\r\n'
                   'marketPostOpen,MarketPostOpen,"$b\r\n$faction.id == MAR",FireAll X,"two ""quoted"" lines\r\nhere",,\r\n'
                   '"marketPostOpen",MarketPostOpen,$c,,,,\r\n'
                   'marketPostOpen_2,Other,,,,,\r\n')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "mod"
            (root / "data" / "campaign").mkdir(parents=True)
            (root / "mod_info.json").write_text('{"id": "rd"}', encoding="utf-8")
            (root / "data" / "campaign" / "rules.csv").write_bytes(content.encode("utf-8"))
            found = [f for f in scan_mod(root).findings if f.id == "rules-csv-duplicate-id"]
            after = compute_fix(root, "rules-csv-duplicate-id").changes[0].after.decode("utf-8")
        self.assertEqual(found[0].evidence, ["id:marketPostOpen"])
        expected = (content.replace("marketPostOpen,MarketPostOpen,\"$b", "marketPostOpen_3,MarketPostOpen,\"$b")
                    .replace('"marketPostOpen",MarketPostOpen,$c', '"marketPostOpen_4",MarketPostOpen,$c'))
        self.assertEqual(after, expected)


class RulesCsvWhitespaceOnlyLineTests(unittest.TestCase):
    def test_only_a_line_of_spaces_in_a_real_rules_script_is_emptied(self) -> None:
        # Ironclads ngcSmugglerOption: a one-space line between two statements stopped RC8 (GRP10K-20261005)
        from bridgeforge.fixers import compute_fix

        content = ('id,trigger,conditions,script,text,options,notes\r\n'
                   'ruleA,T,,"First 1\r\n \r\nSecond ""x"" 2\r\n\r\nThird",keep   \r\n   ,,\r\n'
                   '# comment row,,,"a\r\n  \r\nb",,,\r\n'
                   'ruleB,T,"$a\r\n\r\n$b",Run,"text\r\n  \r\nmore",,\r\n')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "mod"
            (root / "data" / "campaign").mkdir(parents=True)
            (root / "mod_info.json").write_text('{"id": "ws"}', encoding="utf-8")
            (root / "data" / "campaign" / "rules.csv").write_bytes(content.encode("utf-8"))
            found = [f for f in scan_mod(root).findings if f.id == "rules-csv-whitespace-only-line"]
            after = compute_fix(root, "rules-csv-whitespace-only-line").changes[0].after.decode("utf-8")
        self.assertEqual(len(found), 1)
        self.assertEqual(after, content.replace('"First 1\r\n \r\nSecond', '"First 1\r\n\r\nSecond'))


MISSING_CONTENT_FACTION = (
    '{\n\t"id":"hegemony",\n\t"knownShips":{\n\t\t"tags":["x"],\n\t\t"hulls":[\n\t\t\t"kept_hull",\n\t\t\t"gone_hull",\n\t\t],\n\t},\n'
    '\t"knownFighters":{\n\t\t"fighters":[\n\t\t\t"gone_wing",\n\t\t],\n\t},\n'
    '\t"knownWeapons":{\n\t\t"weapons":[\n\t\t\t"lightneedler",\n\t\t\t"kept_gun"\n\t\t],\n\t},\n}\n'
)


def _missing_content_fixture(directory: str, *, replaces: tuple[str, ...] = ("data/hulls/ship_data.csv", "data/weapons/weapon_data.csv", "data/hulls/wing_data.csv"),
                             stub: str | None = None) -> tuple[Path, Path]:
    base = Path(directory)
    mod, core = base / "mod", base / "core"
    _write(core / "data" / "world" / "factions" / "hegemony.faction", MISSING_CONTENT_FACTION)
    _write(mod / "mod_info.json", '{"id":"conv",\n"replace":[\n%s\n]}' % ",\n".join('"%s"' % item for item in replaces))
    _write(mod / "data" / "hulls" / "ship_data.csv", "id,name\nkept_hull,Kept\n")
    _write(mod / "data" / "hulls" / "wing_data.csv", "id,name\nkept_wing,Kept\n")
    _write(mod / "data" / "weapons" / "weapon_data.csv", "id,name\nkept_gun,Kept\n")
    if stub is not None:
        _write(mod / "data" / "world" / "factions" / "hegemony.faction", stub)
    return mod, core


class FactionNamesMissingContentTests(unittest.TestCase):
    def test_flagged_and_fixed_by_a_replaced_copy_without_the_missing_ids(self) -> None:
        # Ironclads: "Weapon spec [lightneedler] not found!" then "Ship hull spec [crig] not found!" from vanilla factions
        # whose known lists outlived the replaced tables (GRP10U/GRP10V-20261005)
        check = "conversion-faction-names-missing-content"
        with tempfile.TemporaryDirectory() as directory:
            mod, core = _missing_content_fixture(directory, stub='{\n\t"showInIntelTab":false,\n}\n')
            found = [f for f in scan_mod(mod, vanilla_core=core).findings if f.id == check]
            apply_fix(compute_fix(mod, check, {"vanilla_core": core}))
            path = mod / "data" / "world" / "factions" / "hegemony.faction"
            data = _load_lenient_json_file(path)
            info = _load_lenient_json_file(mod / "mod_info.json")
            after = [f for f in scan_mod(mod, vanilla_core=core).findings if f.id == check]
        self.assertEqual(len(found), 1)
        self.assertEqual(sorted(found[0].evidence), ["hegemony.faction:fighters:1:gone_wing", "hegemony.faction:hulls:1:gone_hull",
                                                     "hegemony.faction:weapons:1:lightneedler"])
        self.assertEqual(data["knownShips"]["hulls"], ["kept_hull"])
        self.assertEqual(data["knownFighters"]["fighters"], [])
        self.assertEqual(data["knownWeapons"]["weapons"], ["kept_gun"])
        self.assertEqual(data["knownShips"]["tags"], ["x"])
        self.assertIs(data["showInIntelTab"], False)
        self.assertIn("data/world/factions/hegemony.faction", info["replace"])
        self.assertEqual(after, [])

    def test_a_table_the_mod_does_not_replace_is_not_checked(self) -> None:
        check = "conversion-faction-names-missing-content"
        with tempfile.TemporaryDirectory() as directory:
            mod, core = _missing_content_fixture(directory, replaces=("data/weapons/weapon_data.csv",))
            found = [f for f in scan_mod(mod, vanilla_core=core).findings if f.id == check]
        self.assertEqual([f.evidence for f in found], [["hegemony.faction:weapons:1:lightneedler"]])

    def test_no_replaced_table_means_no_finding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod, core = _missing_content_fixture(directory, replaces=())
            found = [f for f in scan_mod(mod, vanilla_core=core).findings if f.id == "conversion-faction-names-missing-content"]
        self.assertEqual(found, [])

    def test_an_overlay_with_real_content_is_left_for_the_owner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod, core = _missing_content_fixture(directory, stub='{"id":"hegemony","displayName":"Mine"}')
            with self.assertRaises(FixerError) as caught:
                compute_fix(mod, "conversion-faction-names-missing-content", {"vanilla_core": core})
        self.assertIn("more than a showInIntelTab stub", str(caught.exception))
