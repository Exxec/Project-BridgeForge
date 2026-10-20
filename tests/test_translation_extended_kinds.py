import json
import struct
import tempfile
import unittest
from pathlib import Path

from bridgeforge.translation import TranslationError, apply_translation, export_translation


def _utf8(text: str) -> bytes:
    raw = text.encode("utf-8")
    return b"\x01" + struct.pack(">H", len(raw)) + raw


def _class_with_string(value: str) -> bytes:
    pool = [
        _utf8("sample/Loose"), b"\x07" + struct.pack(">H", 1),
        _utf8("java/lang/Object"), b"\x07" + struct.pack(">H", 3),
        _utf8(value), b"\x08" + struct.pack(">H", 5),
        _utf8("不应导出"),
    ]
    data = b"\xca\xfe\xba\xbe" + struct.pack(">HH", 0, 52) + struct.pack(">H", len(pool) + 1)
    return data + b"".join(pool) + struct.pack(">HHH", 0x0021, 2, 4) + struct.pack(">HHHH", 0, 0, 0, 0)


def _mod(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "mod_info.json").write_text(json.dumps({"id": "test"}), encoding="utf-8")
    return root


class ExtendedTranslationKindsTests(unittest.TestCase):
    def test_invalid_class_and_undecodable_text_are_reported_unreadable(self):
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory) / "mod")
            (mod / "data/strings").mkdir(parents=True)
            (mod / "Bad.class").write_bytes(b"not a class")
            (mod / "data/strings/bad.txt").write_bytes(b"\xff")
            document = export_translation(mod)
            self.assertEqual(len(document["unreadable"]), 2)

    def test_export_text_lines_only_from_supported_locations_and_ignore_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory) / "mod")
            mission = mod / "data/missions/example/mission_text.txt"
            mission.parent.mkdir(parents=True)
            mission.write_bytes(b"\xef\xbb\xbf" + "  你好  \r\nplain\n  天空\n".encode("utf-8"))
            strings = mod / "data/strings/nested/messages.txt"
            strings.parent.mkdir(parents=True)
            strings.write_bytes("  你好\r\n再见  ".encode("gb18030"))
            ignored = mod / "data/missions/example/nested/not-a-mission-line.txt"
            ignored.parent.mkdir(parents=True)
            ignored.write_text("你好\n", encoding="utf-8")
            backup = mod / ".ssmt-backup/data/strings/old.txt"
            backup.parent.mkdir(parents=True)
            backup.write_text("旧文本\n", encoding="utf-8")

            doc = export_translation(mod)

        self.assertEqual([(e["id"], e["kind"], e["context"], e["source"]) for e in doc["entries"]], [
            ("text:data/missions/example/mission_text.txt@1", "text-line", {"line": 1}, "你好"),
            ("text:data/missions/example/mission_text.txt@3", "text-line", {"line": 3}, "天空"),
            ("text:data/strings/nested/messages.txt@1", "text-line", {"line": 1}, "你好"),
            ("text:data/strings/nested/messages.txt@2", "text-line", {"line": 2}, "再见"),
        ])

    def test_apply_text_preserves_encoding_bom_indentation_and_line_endings(self):
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory) / "mod")
            path = mod / "data/missions/example/mission_text.txt"
            path.parent.mkdir(parents=True)
            original = b"\xef\xbb\xbf" + "  你好  \r\n  天空\t\n".encode("utf-8")
            path.write_bytes(original)
            doc = export_translation(mod)
            for entry, translated in zip(doc["entries"], ("Hello", "Sky")):
                entry["translation"] = translated

            out = Path(directory) / "out"
            result = apply_translation(mod, doc, out_dir=out)

            self.assertEqual(result["status"], "OK")
            self.assertEqual((out / path.relative_to(mod)).read_bytes(), b"\xef\xbb\xbf" + b"  Hello  \r\n  Sky\t\n")
            self.assertEqual(path.read_bytes(), original)

    def test_text_apply_refuses_newlines_in_translation(self):
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory) / "mod")
            path = mod / "data/strings/text.txt"
            path.parent.mkdir(parents=True)
            path.write_text("你好\r\n", encoding="utf-8")
            doc = export_translation(mod)
            doc["entries"][0]["translation"] = "Hello\nworld"

            result = apply_translation(mod, doc, out_dir=Path(directory) / "out")

        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("cannot contain line breaks" in problem for problem in result["problems"]))

    def test_apply_text_preserves_gb18030_encoding(self):
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory) / "mod")
            path = mod / "data/strings/messages.txt"
            path.parent.mkdir(parents=True)
            path.write_bytes("你好\r\n再见\n".encode("gb18030"))
            doc = export_translation(mod)
            for entry, translated in zip(doc["entries"], ("Hello", "Goodbye")):
                entry["translation"] = translated

            out = Path(directory) / "out"
            result = apply_translation(mod, doc, out_dir=out)
            self.assertEqual(result["status"], "OK")
            self.assertEqual((out / path.relative_to(mod)).read_bytes(), "Hello\r\nGoodbye\n".encode("gb18030"))

    def test_loose_class_exports_and_applies_only_string_constants(self):
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory) / "mod")
            path = mod / "data/scripts/Loose.class"
            path.parent.mkdir(parents=True)
            original = _class_with_string("你好")
            path.write_bytes(original)

            doc = export_translation(mod)

            self.assertEqual(len(doc["entries"]), 1)
            entry = doc["entries"][0]
            self.assertEqual(entry["id"], "class:data/scripts/Loose.class#5")
            self.assertEqual(entry["kind"], "class")
            self.assertEqual(entry["context"], {"cp_index": 5})
            self.assertEqual(entry["source"], "你好")
            entry["translation"] = "Hello"
            out = Path(directory) / "out"
            result = apply_translation(mod, doc, out_dir=out)

            self.assertEqual(result["status"], "OK")
            from bridgeforge.translation import _class_string_constants
            self.assertEqual(_class_string_constants((out / path.relative_to(mod)).read_bytes())[5], "Hello")
            self.assertEqual(path.read_bytes(), original)

    def test_loose_class_apply_checks_source(self):
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory) / "mod")
            path = mod / "data/scripts/Loose.class"
            path.parent.mkdir(parents=True)
            path.write_bytes(_class_with_string("你好"))
            doc = export_translation(mod)
            doc["entries"][0]["translation"] = "Hello"
            doc["entries"][0]["source"] = "别的"

            with self.assertRaisesRegex(TranslationError, "Protected entry field differs"):
                apply_translation(mod, doc, out_dir=Path(directory) / "out")
            self.assertFalse((Path(directory) / "out").exists())


if __name__ == "__main__":
    unittest.main()
