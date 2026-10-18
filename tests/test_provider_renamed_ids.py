"""content-id-renamed-by-provider (ROADMAP 60d): Tritachyon asked for BOGGLED_AI_STATION, TASC 10.0.9 calls it BOGGLED_REMNANT_STATION."""
from __future__ import annotations

import unittest
import zipfile
from pathlib import Path

from bridgeforge.provider_renamed_ids import closest_known
from bridgeforge.scanner import scan_mod
from tests.support import resolved_temp_dir

MOD_INFO = '{"id":"demo","name":"Demo","version":"1.0","gameVersion":"0.98a-RC8","dependencies":[{"id":"tasc","name":"TASC"}]}'
PROVIDER_INFO = '{"id":"tasc","name":"TASC","version":"10.0.9","gameVersion":"0.98a-RC8"}'
CSV = "name,id,order\nStation,BOGGLED_REMNANT_STATION,1\nOther,BOGGLED_OUTPOST,2\n"
SOURCE_WITH_CALL = 'class Gen { void run(Object m) { m.addIndustry("%s"); } }\n'


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _fixture(base: Path, code: str) -> tuple[Path, Path, Path]:
    mod, core, providers = base / "mod", base / "core", base / "providers"
    _write(mod / "mod_info.json", MOD_INFO)
    _write(mod / "data" / "scripts" / "Gen.java", code)
    _write(core / "data" / "campaign" / "industries.csv", "name,id,order\nPop,population,1\n")
    _write(providers / "TASC" / "mod_info.json", PROVIDER_INFO)
    _write(providers / "TASC" / "data" / "campaign" / "industries.csv", CSV)
    return mod, core, providers


def _utf8(text: str) -> bytes:
    raw = text.encode("utf-8")
    return bytes([1]) + len(raw).to_bytes(2, "big") + raw


def _class_with_pool(method_name: str, literal: str) -> bytes:
    """Just enough class file for the constant-pool reader: Utf8 method name, Utf8 literal, String -> literal."""
    pool = _utf8(method_name) + _utf8(literal) + bytes([8, 0, 2])
    return bytes([0xCA, 0xFE, 0xBA, 0xBE, 0, 0, 0, 61]) + (4).to_bytes(2, "big") + pool


def _hits(mod: Path, core: Path, providers: Path | None):
    result = scan_mod(mod, vanilla_core=core, provider_roots=[providers] if providers else None)
    return [f for f in result.findings if f.id == "content-id-renamed-by-provider"]


class RenamedIndustryIdTests(unittest.TestCase):
    def test_old_id_with_a_renamed_sibling_in_the_provider_is_flagged(self) -> None:
        with resolved_temp_dir() as base:
            mod, core, providers = _fixture(base, SOURCE_WITH_CALL % "BOGGLED_AI_STATION")
            hits = _hits(mod, core, providers)
        self.assertEqual(len(hits), 1)
        self.assertTrue(any(e.startswith("BOGGLED_AI_STATION->BOGGLED_REMNANT_STATION") for e in hits[0].evidence))

    def test_id_the_provider_defines_is_quiet(self) -> None:
        with resolved_temp_dir() as base:
            mod, core, providers = _fixture(base, SOURCE_WITH_CALL % "BOGGLED_REMNANT_STATION")
            self.assertEqual(_hits(mod, core, providers), [])

    def test_without_the_provider_nothing_is_claimed(self) -> None:
        with resolved_temp_dir() as base:
            mod, core, _ = _fixture(base, SOURCE_WITH_CALL % "BOGGLED_AI_STATION")
            self.assertEqual(_hits(mod, core, None), [])

    def test_string_in_a_class_with_no_industry_call_is_ignored(self) -> None:
        with resolved_temp_dir() as base:
            mod, core, providers = _fixture(base, 'class Gen { String s = "BOGGLED_AI_STATION"; }\n')
            self.assertEqual(_hits(mod, core, providers), [])

    def test_unrelated_id_is_not_matched(self) -> None:
        self.assertIsNone(closest_known("ZORG_TOTALLY_NEW", {"BOGGLED_REMNANT_STATION"}))
        self.assertIsNotNone(closest_known("BOGGLED_AI_STATION", {"BOGGLED_REMNANT_STATION"}))

    def test_jar_constant_in_an_industry_api_class_is_flagged(self) -> None:
        with resolved_temp_dir() as base:
            mod, core, providers = _fixture(base, "class Gen {}\n")
            (mod / "jars").mkdir()
            with zipfile.ZipFile(mod / "jars" / "Gen.jar", "w") as archive:
                archive.writestr("a/Gen.class", _class_with_pool("addIndustry", "BOGGLED_AI_STATION"))
            hits = _hits(mod, core, providers)
        self.assertEqual(len(hits), 1)
        self.assertTrue(any("Gen.jar!a/Gen.class" in e for e in hits[0].evidence))


KIND_CASES = (
    ("hullmod", 'class Gen { void run(Object v) { v.addPermaMod("tasc_old_armor"); } }\n', "data/hullmods/hull_mods.csv", "tasc_new_armor"),
    ("commodity", 'class Gen { void run(Object c) { c.addCommodity("tasc_rare_ore", 5); } }\n', "data/campaign/commodities.csv", "tasc_rare_ore2"),
    ("condition", 'class Gen { void run(Object m) { m.addCondition("tasc_ruins_big"); } }\n', "data/campaign/market_conditions.csv", "tasc_ruins_bigger"),
)


class RenamedOtherKindsTests(unittest.TestCase):
    """Item 73 F3: hull mod, commodity and condition ids get the same declared-provider-only rule."""

    def _build(self, base: Path, code: str, table: str, provider_id: str):
        mod, core, providers = base / "mod", base / "core", base / "providers"
        _write(mod / "mod_info.json", MOD_INFO)
        _write(mod / "data" / "scripts" / "Gen.java", code)
        _write(core / table, "name,id\nVanilla,vanilla_thing\n")
        _write(providers / "TASC" / "mod_info.json", PROVIDER_INFO)
        _write(providers / "TASC" / table, f"name,id\nNew,{provider_id}\n")
        return mod, core, providers

    def test_renamed_id_of_each_kind_is_flagged_with_its_kind(self) -> None:
        for kind, code, table, provider_id in KIND_CASES:
            with self.subTest(kind=kind), resolved_temp_dir() as base:
                mod, core, providers = self._build(base, code, table, provider_id)
                hits = _hits(mod, core, providers)
                self.assertEqual(len(hits), 1)
                self.assertTrue(any(e.startswith(f"kind:{kind}:") for e in hits[0].evidence))

    def test_id_the_provider_defines_is_quiet_for_each_kind(self) -> None:
        for kind, code, table, provider_id in KIND_CASES:
            with self.subTest(kind=kind), resolved_temp_dir() as base:
                mod, core, providers = self._build(base, code.replace(code.split('"')[1], provider_id), table, provider_id)
                self.assertEqual(_hits(mod, core, providers), [])

    def test_vanilla_only_sibling_is_not_a_suggestion(self) -> None:
        with resolved_temp_dir() as base:
            mod, core, providers = self._build(base, 'class Gen { void run(Object v) { v.addMod("vanilla_thingy"); } }\n',
                                               "data/hullmods/hull_mods.csv", "other_zzz")
            self.assertEqual(_hits(mod, core, providers), [])

    def test_id_defined_by_another_kinds_table_is_not_a_hull_mod_candidate(self) -> None:
        with resolved_temp_dir() as base:
            mod, core, providers = self._build(base, 'class Gen { void run(Object v) { v.addMod("tasc_old_armor"); } }\n',
                                               "data/hullmods/hull_mods.csv", "tasc_new_armor")
            _write(providers / "TASC" / "data" / "weapons" / "weapon_data.csv", "name,id\nW,tasc_old_armor\n")
            self.assertEqual(_hits(mod, core, providers), [])


if __name__ == "__main__":
    unittest.main()
