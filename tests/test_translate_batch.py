"""`translate-batch` (ROADMAP 34.28): export, chunked translation, strict checks, apply, resume."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from bridgeforge.translate_batch import translate_batch, verify_chunk
from tests.support import resolved_temp_dir

ENGLISH = {"重型战斗机": "Heavy Fighter", "拦截机": "Interceptor", "能量武器射程提升%s": "Energy weapon range +%s"}


def _mod(root: Path) -> Path:
    mod = root / "mod"
    (mod / "data" / "hulls").mkdir(parents=True)
    (mod / "mod_info.json").write_text('{"id": "fixture", "name": "Fixture"}', encoding="utf-8")
    (mod / "data" / "hulls" / "ship_data.csv").write_text(
        "name,id,designation\n重型战斗机,fx_a,拦截机\n能量武器射程提升%s,fx_b,Frigate\n", encoding="utf-8")
    return mod


def _translator(table=ENGLISH, calls=None, wreck=False, limit_after=None):
    def run(chunk_file: Path) -> str:
        if calls is not None:
            calls.append(chunk_file.name)
        if limit_after is not None and len(calls) > limit_after:
            return "You've hit your session limit"
        data = json.loads(chunk_file.read_text(encoding="utf-8"))
        for entry in data["entries"]:
            entry["translation"] = table.get(entry["source"], "")
            if wreck:
                entry["translation"] = entry["translation"].replace("%s", "")
        chunk_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return "done"
    return run


class TranslateBatchTests(unittest.TestCase):
    def test_produces_a_complete_translated_copy(self) -> None:
        with resolved_temp_dir() as root:
            mod = _mod(root)
            result = translate_batch(mod, translator=_translator(), work_dir=root / "work", out_dir=root / "mod-en", chunk=2, quiet=True)
            copy = (root / "mod-en" / "data" / "hulls" / "ship_data.csv").read_text(encoding="utf-8")
            source = (mod / "data" / "hulls" / "ship_data.csv").read_text(encoding="utf-8")
            checkpoint_left = (root / "work" / "translate-batch.partial.jsonl").exists()
        self.assertEqual(result["translated"], 3)
        self.assertEqual(result["check"]["leftover_count"], 0)
        self.assertIn("Heavy Fighter,fx_a,Interceptor", copy)
        self.assertIn("重型战斗机", source)  # the source mod is untouched
        self.assertFalse(checkpoint_left)

    def test_a_changed_placeholder_rejects_the_chunk_and_nothing_is_applied(self) -> None:
        with resolved_temp_dir() as root:
            mod = _mod(root)
            result = translate_batch(mod, translator=_translator(wreck=True), work_dir=root / "work", out_dir=root / "mod-en", chunk=10, quiet=True)
            applied = (root / "mod-en").exists()
        self.assertEqual(list(result["failed_chunks"]), [1])
        self.assertIn("placeholders differ", " ".join(result["failed_chunks"][1]))
        self.assertIsNone(result["applied"])
        self.assertFalse(applied)

    def test_a_usage_limit_stops_and_a_rerun_resumes_from_the_checkpoint(self) -> None:
        with resolved_temp_dir() as root:
            mod = _mod(root)
            calls: list[str] = []
            first = translate_batch(mod, translator=_translator(calls=calls, limit_after=1), work_dir=root / "work",
                                    out_dir=root / "mod-en", chunk=1, quiet=True)
            calls_after_first = list(calls)
            second_calls: list[str] = []
            second = translate_batch(mod, translator=_translator(calls=second_calls), work_dir=root / "work",
                                     out_dir=root / "mod-en", chunk=1, quiet=True)
        self.assertEqual(first["stopped"], "usage limit at chunk0002")
        self.assertEqual(calls_after_first, ["chunk0001.json", "chunk0002.json"])
        self.assertEqual(second_calls, ["chunk0002.json", "chunk0003.json"])  # chunk 1 came from the checkpoint
        self.assertIsNotNone(second["applied"])

    def test_known_strings_come_from_the_memory_and_only_new_ones_reach_the_agent(self) -> None:
        # D2: two strings are in the memory (one with a placeholder), one is new -> the stub translator sees one string.
        with resolved_temp_dir() as root:
            mod = _mod(root)
            memory = root / "memory.json"
            memory.write_text(json.dumps({"schemaVersion": 1, "entries": [
                {"sourceText": "重型战斗机", "sourceLanguage": "zh", "targetLanguage": "en", "translatedText": "Heavy Fighter", "context": "", "provenance": "AUTHOR_LOCALIZATION"},
                {"sourceText": "能量武器射程提升%s", "sourceLanguage": "zh", "targetLanguage": "en", "translatedText": "Energy weapon range +%s", "context": "", "provenance": "AI_TRANSLATED"},
            ]}, ensure_ascii=False), encoding="utf-8")
            seen: list[str] = []

            def spy(chunk_file: Path) -> str:
                seen.extend(e["source"] for e in json.loads(chunk_file.read_text(encoding="utf-8"))["entries"])
                return _translator()(chunk_file)

            result = translate_batch(mod, translator=spy, work_dir=root / "work", out_dir=root / "mod-en", quiet=True, memory=memory)
            copy = (root / "mod-en" / "data" / "hulls" / "ship_data.csv").read_text(encoding="utf-8")
            stored = json.loads(memory.read_text(encoding="utf-8"))["entries"]
            review = (root / "work" / "REVIEW.md").read_text(encoding="utf-8")
        self.assertEqual(seen, ["拦截机"])
        self.assertEqual(result["prefilled"]["memory"]["reused"], 2)
        self.assertEqual((result["sent_to_agent"], result["memory_added"]), (1, 1))
        self.assertIn("Heavy Fighter,fx_a,Interceptor", copy)
        self.assertEqual(sorted(e["sourceText"] for e in stored), sorted(ENGLISH))
        self.assertEqual({e["sourceText"]: e["provenance"] for e in stored}["重型战斗机"], "AUTHOR_LOCALIZATION")  # kept as it was
        self.assertIn("| 拦截机 | Interceptor | agent |", review)
        self.assertIn("| 重型战斗机 | Heavy Fighter | memory |", review)

    def test_retranslating_a_translated_mod_sends_nothing_to_the_agent(self) -> None:
        with resolved_temp_dir() as root:
            mod = _mod(root)
            memory = root / "memory.json"
            translate_batch(mod, translator=_translator(), work_dir=root / "w1", out_dir=root / "en1", quiet=True, memory=memory)
            calls: list[str] = []
            again = translate_batch(mod, translator=_translator(calls=calls), work_dir=root / "w2", out_dir=root / "en2", quiet=True, memory=memory)
        self.assertEqual(calls, [])
        self.assertEqual((again["sent_to_agent"], again["chunks"], again["memory_added"]), (0, 0, 0))
        self.assertEqual(again["check"]["leftover_count"], 0)

    def test_a_memory_translation_with_other_placeholders_is_not_reused(self) -> None:
        with resolved_temp_dir() as root:
            mod = _mod(root)
            memory = root / "memory.json"
            memory.write_text(json.dumps({"schemaVersion": 1, "entries": [
                {"sourceText": "能量武器射程提升%s", "translatedText": "Energy weapon range up", "provenance": "AI_TRANSLATED"}]}, ensure_ascii=False), encoding="utf-8")
            result = translate_batch(mod, translator=_translator(), work_dir=root / "work", out_dir=root / "mod-en", quiet=True, memory=memory)
        self.assertEqual(result["prefilled"]["memory"], {"reused": 0, "skipped": 1})
        self.assertEqual(result["sent_to_agent"], 3)

    def test_verify_chunk_refuses_reordered_entries(self) -> None:
        original = [{"id": "a", "source": "一"}, {"id": "b", "source": "二"}]
        self.assertTrue(verify_chunk(original, [{"id": "b", "source": "二", "translation": "Two"}, {"id": "a", "source": "一", "translation": "One"}]))
        self.assertEqual(verify_chunk(original, [{"id": "a", "source": "一", "translation": "One"}, {"id": "b", "source": "二", "translation": "Two"}]), [])


if __name__ == "__main__":
    unittest.main()
