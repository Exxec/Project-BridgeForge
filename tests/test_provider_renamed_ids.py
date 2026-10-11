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


if __name__ == "__main__":
    unittest.main()
