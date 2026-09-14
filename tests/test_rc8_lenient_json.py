from __future__ import annotations

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
