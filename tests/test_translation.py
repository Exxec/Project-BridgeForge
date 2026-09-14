"""Translation export / prefill / apply / check (plan B for the 2026-09-13 Chinese intake)."""

import json
import os
import stat
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path

from bridgeforge.translation import (
    TranslationError,
    _class_string_constants,
    apply_translation,
    check_translation,
    export_translation,
    prefill_from_record,
    prefill_from_reference,
)


def _utf8(text: str) -> bytes:
    raw = text.encode("utf-8")
    return b"\x01" + struct.pack(">H", len(raw)) + raw


def _class_with_string(this_name: str, value: str) -> bytes:
    pool = [
        _utf8(this_name), b"\x07" + struct.pack(">H", 1),
        _utf8("java/lang/Object"), b"\x07" + struct.pack(">H", 3),
        _utf8(value), b"\x08" + struct.pack(">H", 5),  # #5 Utf8, #6 String -> #5
        _utf8("描述字段名不是字面量"),  # #7 CJK Utf8 NOT referenced by a String: must be ignored
    ]
    body = b"\xca\xfe\xba\xbe" + struct.pack(">HH", 0, 52) + struct.pack(">H", len(pool) + 1) + b"".join(pool)
    return body + struct.pack(">HHH", 0x0021, 2, 4) + struct.pack(">HHHH", 0, 0, 0, 0)


def _write(path: Path, text: str) -> None:
    # Exact bytes: text-mode writes turn "\n" into "\r\n" on Windows, which changes quoted CSV cells.
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _jar(path: Path, classes: dict[str, bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in classes.items():
            archive.writestr(name, data)


def _mod(root: Path) -> Path:
    _write(root / "mod_info.json", '{\n  "id": "fx",\n  "name": "测试模组", # comment\n  "jars": ["jars/fx.jar"],\n}\n')
    _write(
        root / "data" / "hulls" / "ship_data.csv",
        'name,id,tech/manufacturer,notes\n'
        '"护卫舰, 甲型",fx_frigate,天船三,plain\n'
        'Cruiser,fx_cruiser,天船三,"多行\n说明"\n'
        '巡洋舰,fx_cruiser,天船三,dup-id\n'
        'Padded,fx_pad,Common,,,,\n',
    )
    _write(root / "data" / "config" / "settings.json", '{\n  "designTypeColors": {\n    "天船三": [232,209,16,255], # key\n  },\n}\n')
    _write(root / "data" / "world" / "factions" / "fx.faction", "{\n  id:\"fx\",\n  displayName:'天船', # single quotes\n  ranks:{posts:{patrolCommander:{name:\"巡逻指挥官\"}}},\n  tags:[STATION, \"舰队\"],\n}\n")
    _write(root / "data" / "scripts" / "Loose.java", 'class Loose {\n  // "注释里的字符串"\n  String a = "获得 %s 点\\n声望";\n  String b = "ascii only";\n}\n')
    _write(root / "src" / "Ignored.java", 'class Ignored { String a = "源码不导出"; }\n')
    (root / "jars").mkdir(parents=True)
    with zipfile.ZipFile(root / "jars" / "fx.jar", "w") as archive:
        archive.writestr("data/scripts/Hud.class", _class_with_string("data/scripts/Hud", "当前加成：\x01%"))
    return root


ENGLISH = {
    "测试模组": "Test Mod",
    "护卫舰, 甲型": "Frigate, Type A",
    "天船三": "Mirfak",
    "多行\n说明": "Multi-line\nnote",
    "巡洋舰": "Cruiser B",
    "天船": "Mirfak Parcel",
    "巡逻指挥官": "Patrol Commander",
    "舰队": "fleet",
    "获得 %s 点\n声望": "Gain %s points\nof reputation",
    "当前加成：\x01%": "Current bonus: \x01%",
}


class ExportTests(unittest.TestCase):
    def test_export_finds_every_unit_kind_with_stable_ids_and_skips_src(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            doc = export_translation(_mod(Path(directory)))
        kinds = {}
        for e in doc["entries"]:
            kinds.setdefault(e["kind"], []).append(e["source"])
        self.assertEqual(sorted(kinds["csv"]), sorted(["护卫舰, 甲型", "天船三", "天船三", "多行\n说明", "巡洋舰", "天船三"]))
        self.assertEqual(kinds["json-key"], ["天船三"])
        self.assertIn("巡逻指挥官", kinds["json"])
        self.assertEqual(kinds["java"], ["获得 %s 点\n声望"])
        self.assertEqual(kinds["jar"], ["当前加成：\x01%"])  # the unreferenced Utf8 is not a literal
        ids = [e["id"] for e in doc["entries"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("csv:data/hulls/ship_data.csv#fx_cruiser~2:name", ids)  # duplicate id gets an occurrence suffix
        faction = next(e for e in doc["entries"] if e["source"] == "巡逻指挥官")
        self.assertEqual(faction["context"]["path"], ["ranks", "posts", "patrolCommander", "name"])
        self.assertFalse(any("Ignored.java" in e["file"] for e in doc["entries"]))


class ProjectGoMemoryTests(unittest.TestCase):
    def test_tm_export_matches_project_go_schema_and_ranks_author_english(self) -> None:
        from bridgeforge.translation import export_project_go_tm
        doc = {
            "source_language": "zh", "target_language": "en",
            "entries": [
                {"source": "黑石船坞", "translation": "Blackrock Drive Yards", "provenance": "reference"},
                {"source": "黑石船坞", "translation": "Blackrock Yards", "provenance": "glossary"},
                {"source": "护卫", "translation": ""},
                {"source": "brdy_id", "translation": "brdy_id"},
                {"source": "保持原样", "translation": "保持原样"},
            ],
            "glossary": {"护卫": "Frigate"},
        }
        memory = export_project_go_tm(doc)
        self.assertEqual(memory["schemaVersion"], 1)
        by_source = {e["sourceText"]: e for e in memory["entries"]}
        self.assertEqual(sorted(by_source), ["护卫", "黑石船坞"])
        self.assertEqual(by_source["黑石船坞"]["translatedText"], "Blackrock Drive Yards")
        self.assertEqual(by_source["黑石船坞"]["provenance"], "AUTHOR_LOCALIZATION")
        self.assertEqual(by_source["护卫"]["provenance"], "AI_TRANSLATED")
        self.assertEqual(set(by_source["护卫"]), {"sourceText", "sourceLanguage", "targetLanguage", "translatedText", "context", "provenance"})


class PlaceholderTests(unittest.TestCase):
    def test_memory_key_glued_to_chinese_stays_ascii(self) -> None:
        from bridgeforge.translation import _placeholders
        self.assertEqual(_placeholders("$LTHS_Person1标记的NPC进行此对话"), _placeholders("Talk to the NPC marked by $LTHS_Person1"))
        self.assertEqual(sorted(_placeholders("获得 %s 点 $player.name").elements()), ["$player.name", "%s"])

    def test_sentence_period_is_not_part_of_a_variable(self) -> None:
        # Blackrock rules text: "...welcome, $playerName." vs the Chinese "...$playerName。"
        from bridgeforge.translation import _placeholders
        self.assertEqual(_placeholders("欢迎，$playerName。"), _placeholders("Welcome, $playerName."))

    def test_stale_reference_english_with_different_placeholders_is_only_a_hint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "mod"
            _write(root / "mod_info.json", '{"id":"fx"}')
            _write(root / "data" / "hullmods" / "hull_mods.csv", "id,desc\nfxmod,提升 %s 幅能容量\n")
            ref = Path(directory) / "english"
            _write(ref / "data" / "hullmods" / "hull_mods.csv", "id,desc\nfxmod,Increases flux capacity.\n")
            doc = export_translation(root)
            prefill_from_reference(doc, root, ref)
        entry = doc["entries"][0]
        self.assertEqual(entry["translation"], "")
        self.assertEqual(entry["reference_hint"], "Increases flux capacity.")


class CorruptJarTests(unittest.TestCase):
    def test_entry_with_bad_crc_is_reported_not_fatal(self) -> None:
        # The Chinese Nightcross jar carried class entries with bad CRCs (e.g. AfterburnerStats.class).
        with tempfile.TemporaryDirectory() as directory:
            root = _mod(Path(directory))
            jar = root / "jars" / "fx.jar"
            with zipfile.ZipFile(jar, "a", compression=zipfile.ZIP_STORED) as archive:
                archive.writestr("data/scripts/Broken.class", _class_with_string("data/scripts/Broken", "坏的"))
            with zipfile.ZipFile(jar) as archive:
                offset = archive.getinfo("data/scripts/Broken.class").header_offset
            raw = bytearray(jar.read_bytes())
            position = raw.find("坏的".encode("utf-8"), offset)  # inside the Broken entry only
            raw[position] ^= 0xFF  # corrupt the stored bytes so the CRC no longer matches
            jar.write_bytes(bytes(raw))
            doc = export_translation(root)
        self.assertEqual(len(doc["unreadable"]), 1)
        self.assertIn("Broken.class", doc["unreadable"][0])
        self.assertEqual([e["source"] for e in doc["entries"] if e["kind"] == "jar"], ["当前加成：\x01%"])


class ApplyTests(unittest.TestCase):
    def _translated(self, root: Path) -> dict:
        doc = export_translation(root)
        for entry in doc["entries"]:
            entry["translation"] = ENGLISH[entry["source"]]
        return doc

    def test_apply_to_a_copy_translates_everything_and_keeps_structure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _mod(Path(directory) / "mod")
            before = (root / "data" / "hulls" / "ship_data.csv").read_bytes()
            result = apply_translation(root, self._translated(root), out_dir=Path(directory) / "out")
            out = Path(directory) / "out"
            self.assertEqual(result["status"], "OK", result)
            self.assertEqual((root / "data" / "hulls" / "ship_data.csv").read_bytes(), before)  # source untouched
            csv_text = (out / "data" / "hulls" / "ship_data.csv").read_text(encoding="utf-8")
            self.assertIn('"Frigate, Type A",fx_frigate,Mirfak,plain', csv_text)
            self.assertIn('"Multi-line\nnote"', csv_text)
            self.assertIn("Padded,fx_pad,Common,,,,", csv_text)
            self.assertIn('"Mirfak": [232,209,16,255], # key', (out / "data" / "config" / "settings.json").read_text(encoding="utf-8"))
            self.assertIn('"Gain %s points\\nof reputation"', (out / "data" / "scripts" / "Loose.java").read_text(encoding="utf-8"))
            self.assertIn('// "注释里的字符串"', (out / "data" / "scripts" / "Loose.java").read_text(encoding="utf-8"))
            with zipfile.ZipFile(out / "jars" / "fx.jar") as archive:
                self.assertEqual(list(_class_string_constants(archive.read("data/scripts/Hud.class")).values()), ["Current bonus: \x01%"])
            self.assertEqual(check_translation(out)["leftover_count"], 0)
            self.assertEqual(check_translation(out)["design_type_keys_unused"], [])

    def test_translated_key_never_duplicates_a_sibling_key(self) -> None:
        # Blackrock CN settings.json: designTypeColors has "黑石船坞" AND "Blackrock".
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "mod"
            _write(root / "mod_info.json", '{"id":"fx"}')
            _write(root / "data" / "config" / "settings.json", '{"designTypeColors":{"黑石船坞":[1,2,3,4],"Blackrock":[1,2,3,4]}}')
            doc = export_translation(root)
            doc["entries"][0]["translation"] = "Blackrock"
            result = apply_translation(root, doc, out_dir=Path(directory) / "out")
            text = (Path(directory) / "out" / "data" / "config" / "settings.json").read_text(encoding="utf-8")
        self.assertTrue(any("already exists" in p for p in result["problems"]))
        self.assertIn('"黑石船坞"', text)
        self.assertEqual(text.count('"Blackrock"'), 1)

    def test_changed_source_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _mod(Path(directory) / "mod")
            doc = self._translated(root)
            _write(root / "data" / "config" / "settings.json", '{"designTypeColors": {"天船三": [1,2,3,4]}}')
            with self.assertRaises(TranslationError):
                apply_translation(root, doc, out_dir=Path(directory) / "out")

    def test_lost_placeholder_is_reported_and_not_applied(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _mod(Path(directory) / "mod")
            doc = self._translated(root)
            next(e for e in doc["entries"] if e["kind"] == "java")["translation"] = "Gain points"
            result = apply_translation(root, doc, out_dir=Path(directory) / "out")
            self.assertEqual(result["status"], "PARTIAL")
            self.assertTrue(any("placeholders differ" in p for p in result["problems"]))
            self.assertIn("获得 %s 点", (Path(directory) / "out" / "data" / "scripts" / "Loose.java").read_text(encoding="utf-8"))

    def test_glossary_fills_repeated_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _mod(Path(directory) / "mod")
            doc = self._translated(root)
            for entry in doc["entries"]:
                if entry["source"] == "天船三":
                    entry["translation"] = ""
            doc["glossary"] = {"天船三": "Mirfak"}
            result = apply_translation(root, doc, out_dir=Path(directory) / "out")
            self.assertEqual(result["status"], "OK", result)

    def test_read_only_source_files_are_translated_in_the_copy(self) -> None:
        # Mirfak's source had read-only files; copytree carried the attribute and apply failed half-way.
        with tempfile.TemporaryDirectory() as directory:
            root = _mod(Path(directory) / "mod")
            doc = self._translated(root)
            source = root / "data" / "hulls" / "ship_data.csv"
            source.chmod(stat.S_IREAD)
            try:
                result = apply_translation(root, doc, out_dir=Path(directory) / "out")
                self.assertEqual(result["status"], "OK", result)
                self.assertIn("fx_frigate", (Path(directory) / "out" / "data" / "hulls" / "ship_data.csv").read_text(encoding="utf-8"))
                self.assertFalse(os.access(source, os.W_OK))  # the source keeps its attribute
            finally:
                for path in Path(directory).rglob("*"):
                    if path.is_file():
                        path.chmod(stat.S_IREAD | stat.S_IWRITE)


class PrefillTests(unittest.TestCase):
    def test_record_prefill_uses_unique_pairs_and_marks_ambiguity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _mod(Path(directory) / "mod")
            record = Path(directory) / "record.json"
            record.write_text(json.dumps([{"zh": "天船三", "en": "Mirfak"}, {"zh": "舰队", "en": "fleet"}, {"zh": "舰队", "c": "Fleet"}], ensure_ascii=False), encoding="utf-8")
            doc = export_translation(root)
            stats = prefill_from_record(doc, [record])
        self.assertEqual(stats["filled"], 4)  # 3 CSV cells + the settings key
        self.assertEqual(stats["ambiguous"], 1)

    def test_reference_prefill_by_csv_row_and_json_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _mod(Path(directory) / "mod")
            ref = Path(directory) / "english"
            _write(ref / "data" / "hulls" / "ship_data.csv", 'name,id,tech/manufacturer,notes\n"Frigate, Type A",fx_frigate,Mirfak,plain\n')
            _write(ref / "data" / "world" / "factions" / "fx.faction", '{"id":"fx","ranks":{"posts":{"patrolCommander":{"name":"Patrol Commander"}}}}')
            doc = export_translation(root)
            stats = prefill_from_reference(doc, root, ref)
            by_source = {e["source"]: e["translation"] for e in doc["entries"]}
        self.assertEqual(by_source["护卫舰, 甲型"], "Frigate, Type A")
        self.assertEqual(by_source["巡逻指挥官"], "Patrol Commander")
        self.assertEqual(by_source["天船三"], "Mirfak")  # learned from one row, spread to the identical text
        self.assertGreaterEqual(stats["spread"], 1)

    def test_reference_prefill_aligns_jar_constants_only_when_the_class_layout_matches(self) -> None:
        # A translator who swapped constants in place leaves the class layout identical to the English jar.
        with tempfile.TemporaryDirectory() as directory:
            root = _mod(Path(directory) / "mod")
            ref = Path(directory) / "english"
            _jar(ref / "jars" / "fx.jar", {"data/scripts/Hud.class": _class_with_string("data/scripts/Hud", "Current bonus: \x01%")})
            doc = export_translation(root)
            prefill_from_reference(doc, root, ref)
            jar_entry = next(e for e in doc["entries"] if e["kind"] == "jar")
            self.assertEqual(jar_entry["translation"], "Current bonus: \x01%")

            other = Path(directory) / "english-other-build"
            _jar(other / "jars" / "fx.jar", {"data/scripts/Hud.class": _class_with_string("data/scripts/RenamedHud", "Current bonus: \x01%")})
            doc = export_translation(root)
            prefill_from_reference(doc, root, other)
            self.assertEqual(next(e for e in doc["entries"] if e["kind"] == "jar")["translation"], "")


if __name__ == "__main__":
    unittest.main()
