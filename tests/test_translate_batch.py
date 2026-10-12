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

    def test_verify_chunk_refuses_reordered_entries(self) -> None:
        original = [{"id": "a", "source": "一"}, {"id": "b", "source": "二"}]
        self.assertTrue(verify_chunk(original, [{"id": "b", "source": "二", "translation": "Two"}, {"id": "a", "source": "一", "translation": "One"}]))
        self.assertEqual(verify_chunk(original, [{"id": "a", "source": "一", "translation": "One"}, {"id": "b", "source": "二", "translation": "Two"}]), [])


if __name__ == "__main__":
    unittest.main()
