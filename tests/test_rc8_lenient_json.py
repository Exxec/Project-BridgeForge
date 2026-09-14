from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.scanner import _parse_json, scan_mod


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _findings(result, finding_id: str):
    return [item for item in result.findings if item.id == finding_id]


class ParseJsonToleranceTests(unittest.TestCase):
    def test_strict_valid_json_is_unchanged(self) -> None:
        data, tolerances = _parse_json('{"id": "a", "n": 1}')
        self.assertEqual(data, {"id": "a", "n": 1})
        self.assertEqual(tolerances, set())

    def test_hash_comment_tolerance(self) -> None:
        data, tolerances = _parse_json('{\n  "id": "a", # note\n  "n": 1\n}')
        self.assertEqual(data, {"id": "a", "n": 1})
        self.assertIn("hash-comments", tolerances)

    def test_slash_comment_tolerance(self) -> None:
        data, tolerances = _parse_json('{\n  "id": "a", // note\n  "n": 1\n}')
        self.assertEqual(data, {"id": "a", "n": 1})
        self.assertIn("slash-comments", tolerances)

    def test_trailing_comma_tolerance(self) -> None:
        data, tolerances = _parse_json('{"id": "a", "deps": ["x", "y",], "n": 1,}')
        self.assertEqual(data, {"id": "a", "deps": ["x", "y"], "n": 1})
        self.assertIn("trailing-commas", tolerances)

    def test_single_quoted_scalar_tolerance(self) -> None:
        data, tolerances = _parse_json("{'id':'x', \"n\": 1}")
        self.assertEqual(data, {"id": "x", "n": 1})
        self.assertIn("single-quotes", tolerances)

    def test_unquoted_key_tolerance(self) -> None:
        data, tolerances = _parse_json('{id:"copyplayer"}')
        self.assertEqual(data, {"id": "copyplayer"})
        self.assertIn("unquoted-keys", tolerances)

    def test_bareword_value_tolerance(self) -> None:
        data, tolerances = _parse_json('{"tags": [STATIONS]}')
        self.assertEqual(data, {"tags": ["STATIONS"]})
        self.assertIn("bareword-values", tolerances)

    def test_bareword_true_false_null_stay_literal(self) -> None:
        data, tolerances = _parse_json('{"a": true, "b": false, "c": null, "d": [X]}')
        self.assertEqual(data, {"a": True, "b": False, "c": None, "d": ["X"]})
        self.assertIn("bareword-values", tolerances)

    def test_leading_zero_numbers_tolerance(self) -> None:
        # Mirfak Parcel Service colours: [255,098,000,205]. Strings keep their zeros.
        data, tolerances = _parse_json('{"c": [255,098,000,205], "s": "098", "n": -007}')
        self.assertEqual(data, {"c": [255, 98, 0, 205], "s": "098", "n": -7})
        self.assertIn("lenient-numbers", tolerances)

    def test_leading_dot_numbers_tolerance(self) -> None:
        # Blackrock skins: "baseValueMult":.7
        data, tolerances = _parse_json('{"m":.7, "n":-.5, "v": 1.5, "id": "a.7"}')
        self.assertEqual(data, {"m": 0.7, "n": -0.5, "v": 1.5, "id": "a.7"})
        self.assertIn("lenient-numbers", tolerances)

    def test_ordinary_numbers_are_strict(self) -> None:
        self.assertEqual(_parse_json('{"a": 0, "b": 0.5, "c": 10, "d": -0.25}'), ({"a": 0, "b": 0.5, "c": 10, "d": -0.25}, set()))

    def test_stray_brackets_after_root_are_ignored_like_the_game(self) -> None:
        data, tolerances = _parse_json('{"a": 1}\n    }\n}')
        self.assertEqual(data, {"a": 1})
        self.assertIn("trailing-data", tolerances)
        self.assertNotIn("trailing-content", tolerances)

    def test_keys_after_an_early_closing_brace_are_flagged(self) -> None:
        # Blackrock br_consortium.faction: an extra '}' closes the root, so later keys never load.
        data, tolerances = _parse_json('{"id": "x", "a": {"b": 1}},\n "factionDoctrine": {"w": 2}\n}')
        self.assertEqual(data, {"id": "x", "a": {"b": 1}})
        self.assertIn("trailing-content", tolerances)

    def test_java_number_suffix_tolerance(self) -> None:
        data, tolerances = _parse_json('{"half": 0.5f, "two": 2d, "n": -3.5F}')
        self.assertEqual(data, {"half": 0.5, "two": 2, "n": -3.5})
        self.assertIn("java-number-suffix", tolerances)

    def test_raw_tab_inside_a_string_is_kept_like_org_json(self) -> None:
        # Metelson Industries' mod_info.json: literal tabs in the description, plus inline # comments.
        data, tolerances = _parse_json('{\n  "id":"m", # internal id\n  "description":"a\tb"\n}')
        self.assertEqual(data, {"id": "m", "description": "a\tb"})
        self.assertIn("raw-control-chars", tolerances)

    def test_raw_line_break_inside_a_string_still_fails(self) -> None:
        # org.json's nextString throws "Unterminated string" on \n and \r.
        with self.assertRaises(json.JSONDecodeError):
            _parse_json('{"d": "a\nb", # x\n}')

    def test_digit_led_bareword_is_text_and_hex_is_a_number_like_org_json(self) -> None:
        # Erexeus Tech Complex: "version":{"major":1, "minor":2, "patch":0b}
        data, tolerances = _parse_json('{"version":{"major":1, "minor":2, "patch":0b}, "e": 2E-3, "big": 1e10, "h": 0x1F}')
        self.assertEqual(data, {"version": {"major": 1, "minor": 2, "patch": "0b"}, "e": 2e-3, "big": 1e10, "h": 31})
        self.assertIn("bareword-values", tolerances)

    # The cases below were run through RC8's own org.json (starsector-core/json.jar) on 2026-09-14.
    def test_trailing_dot_and_dotted_java_suffix_numbers(self) -> None:
        # Dassault-Mikoyan: "pitch":1. and "commanderSkillLevelPerLevel":0.; Magellan: "contrailMaxSpeedMult":.0f
        data, tolerances = _parse_json('{"pitch":1., "lvl":0., "m":.0f, "n":1.f, "v": 2.5}')
        self.assertEqual(data, {"pitch": 1.0, "lvl": 0.0, "m": 0.0, "n": 1.0, "v": 2.5})
        self.assertIn("lenient-numbers", tolerances)

    def test_escaped_apostrophe_inside_a_double_quoted_string(self) -> None:
        # Magellan and Foundation of Borken strings.json: "...how it sounds t' them...\'"
        text = '{"q": "it~' + "'" + 's", # c\n}'
        data, tolerances = _parse_json(text.replace("~", chr(92)))
        self.assertEqual(data, {"q": "it's"})
        self.assertIn("apostrophe-escapes", tolerances)

    def test_unicode_bareword_value_is_one_string(self) -> None:
        # Foundation of Borken's backup faction file: displayName:博尔肯基金会（F.O.B）,
        data, tolerances = _parse_json('{displayName:博尔肯基金会（F.O.B）, "x": 1, "t": TRUE}')
        self.assertEqual(data, {"displayName": "博尔肯基金会（F.O.B）", "x": 1, "t": True})
        self.assertIn("bareword-values", tolerances)

    def test_plus_signs_empty_array_elements_and_fullwidth_digits(self) -> None:
        # SCY "renderOrderMod":+5, VAO "luddic_church":+0.5, Valhalla [["a",,"b"]], and Traverser
        # Design Bureau's "pixelsPerTexel":１.0, which org.json keeps as text.
        data, tolerances = _parse_json('{"r":+5, "l":+0.5, "s":[["a",,"b"]], "t":[,"x"], "p":１.0, "e": 2E+3, "k": [1,],}')
        self.assertEqual(data, {"r": 5, "l": 0.5, "s": [["a", None, "b"]], "t": [None, "x"], "p": "１.0", "e": 2000.0, "k": [1]})
        self.assertTrue({"lenient-numbers", "empty-array-elements", "bareword-values"} <= tolerances)

    def test_what_org_json_rejects_still_fails(self) -> None:
        # Hiigaran Descendants' polaris.json misses a comma between array items; org.json throws
        # "Expected a ',' or ']'". An illegal escape such as \% throws "Illegal escape.".
        # Tyrador Safeguard Coalition's blacklist.json has "TSC_DroneKaburaya"::TRUE ("Missing value").
        for text in ('{"c": ["organics_common"\n "habitable"], # x\n}', '{"q": "50~%", # x\n}'.replace("~", chr(92)), '{"a"::TRUE, # x\n}'):
            with self.assertRaises(json.JSONDecodeError):
                _parse_json(text)

    def test_scientific_notation_number_is_not_corrupted_by_bareword_pass(self) -> None:
        data, tolerances = _parse_json('{"big": 1e10, "small": 2E-3}')
        self.assertEqual(data, {"big": 1e10, "small": 2e-3})

    def test_apostrophe_inside_hash_comment_does_not_corrupt_parsing(self) -> None:
        text = "{\n  # a mod author's note, it's fine\n  \"id\": \"a\"\n}"
        data, tolerances = _parse_json(text)
        self.assertEqual(data, {"id": "a"})
        self.assertIn("hash-comments", tolerances)

    def test_hash_inside_single_quoted_value_is_preserved(self) -> None:
        text = "{'description': 'costs #500 credits'}"
        data, tolerances = _parse_json(text)
        self.assertEqual(data, {"description": "costs #500 credits"})
        self.assertIn("single-quotes", tolerances)
        self.assertNotIn("hash-comments", tolerances)

    def test_slashes_inside_single_quoted_url_are_preserved(self) -> None:
        text = "{'source': 'https://example.com/mod'}"
        data, tolerances = _parse_json(text)
        self.assertEqual(data, {"source": "https://example.com/mod"})
        self.assertIn("single-quotes", tolerances)
        self.assertNotIn("slash-comments", tolerances)

    def test_escaped_quote_inside_single_quoted_string(self) -> None:
        text = r"{'note': 'it\'s a trap'}"
        data, tolerances = _parse_json(text)
        self.assertEqual(data, {"note": "it's a trap"})
        self.assertIn("single-quotes", tolerances)

    def test_unterminated_single_quote_still_fails(self) -> None:
        with self.assertRaises(Exception):
            _parse_json("{'id': 'unterminated}")

    def test_real_copyplayer_faction_shape_parses(self) -> None:
        # Modeled on FlowerGod's data/world/factions/copyplayer.faction: unquoted key on line 2.
        text = '{\n\tid:"copyplayer",\n\t"displayName":"Player Copy"\n}'
        data, tolerances = _parse_json(text)
        self.assertEqual(data["id"], "copyplayer")
        self.assertIn("unquoted-keys", tolerances)


class ScanMetadataLenientJsonFindingsTests(unittest.TestCase):
    def test_single_quoted_mod_info_produces_safe_finding_not_unparsed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "mod_info.json", "{'id':'fixture', 'name':'Fixture'}")
            result = scan_mod(root)
            self.assertEqual(result.metadata.get("id"), "fixture")
            self.assertEqual(_findings(result, "unverified-mod-info-syntax"), [])
            self.assertTrue(_findings(result, "json-single-quoted-string"))

    def test_unquoted_key_faction_no_longer_unparsed(self) -> None:
        # .faction files are checked via _load_lenient_json_file, which (like the other
        # domain-specific data-file readers) discards the tolerance set rather than
        # emitting a json-* SAFE finding; the requirement here is only that this real
        # shape parses instead of tripping faction-file-unparsed.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "mod_info.json", '{"id":"fixture"}')
            _write(
                root / "data" / "world" / "factions" / "copyplayer.faction",
                '{\n\tid:"copyplayer",\n\t"displayName":"Player Copy"\n}',
            )
            result = scan_mod(root)
            self.assertEqual(_findings(result, "faction-file-unparsed"), [])

    def test_raw_tab_in_mod_info_is_a_safe_finding_not_unparsed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "mod_info.json", '{\n "id":"metelson", # internal id\n "name":"M",\n "description":"simple.\tLazyLib required.",\n "version":{"major":1, "patch":0b}\n}')
            result = scan_mod(root)
            self.assertEqual(result.metadata.get("id"), "metelson")
            self.assertEqual(_findings(result, "unverified-mod-info-syntax"), [])
            self.assertTrue(_findings(result, "json-raw-control-char"))

    def test_empty_array_element_is_a_review_finding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "mod_info.json", '{"id":"valhalla","name":"V","version":"1","gameVersion":"0.95.1a-RC6","tags":["a",,"b"],}')
            result = scan_mod(root)
            self.assertEqual(result.metadata.get("id"), "valhalla")
            findings = _findings(result, "json-empty-array-element")
            self.assertTrue(findings)
            self.assertEqual(findings[0].classification, "REVIEW")

    def test_escaped_apostrophe_in_strings_json_is_a_safe_finding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "mod_info.json", '{"id":"magellan","name":"M","version":"1","gameVersion":"0.95.1a-RC6"}')
            _write(root / "data" / "strings" / "strings.json", ('{"q": "sounds t~' + "'" + ' them", # quote\n}').replace("~", chr(92)))
            result = scan_mod(root)
            self.assertEqual(_findings(result, "unverified-json-syntax"), [])
            self.assertTrue(_findings(result, "json-escaped-apostrophe"))

    def test_generic_asset_json_emits_new_tolerance_findings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "mod_info.json", '{"id":"fixture"}')
            _write(
                root / "data" / "config" / "settings.json",
                "{tag:[STATIONS], \"half\": 0.5f, \"note\": 'a // b'}",
            )
            result = scan_mod(root)
            self.assertEqual(_findings(result, "unverified-json-syntax"), [])
            self.assertTrue(_findings(result, "json-unquoted-key"))
            self.assertTrue(_findings(result, "json-bareword-value"))
            self.assertTrue(_findings(result, "json-java-number-suffix"))
            self.assertTrue(_findings(result, "json-single-quoted-string"))


if __name__ == "__main__":
    unittest.main()
