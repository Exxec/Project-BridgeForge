"""S2 pure-fact reuse must preserve isolation, context and explicit limits."""
import json
import os
from pathlib import Path
import tempfile
import unittest

from bridgeforge.analysis_reuse import ParseReuse, parsed_facts, reuse_parses
from bridgeforge.scan.scan_classfile import _parse_class_file
from bridgeforge.scan.scan_json import _load_lenient_json_file, _parse_json
from tests.test_personality_ids import _class_with_strings


class AnalysisReuseTests(unittest.TestCase):
    def test_same_path_size_timestamp_change_reads_actual_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "provider.json"
            path.write_text('{"id":"old"}', encoding="utf-8")
            stat = path.stat()
            with reuse_parses(max_entries=10, max_payload_bytes=4096) as cache:
                self.assertEqual(_load_lenient_json_file(path), {"id": "old"})
                path.write_text('{"id":"new"}', encoding="utf-8")
                os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
                self.assertEqual(_load_lenient_json_file(path), {"id": "new"})
                self.assertEqual(cache.misses, 2)

    def test_changed_bytes_and_extractor_do_not_share(self):
        calls = []
        cache = ParseReuse(max_entries=4, max_payload_bytes=4096)
        def produce():
            calls.append(True)
            return {"a": []}
        first = cache.facts("a/v1", b"one", produce)
        first["a"].append("mutation")
        self.assertEqual(cache.facts("a/v1", b"one", produce), {"a": []})
        cache.facts("a/v1", b"two", produce)
        cache.facts("a/v2", b"one", produce)
        self.assertEqual(len(calls), 3)
        self.assertEqual(cache.hits, 1)

    def test_limits_and_lru(self):
        cache = ParseReuse(max_entries=2, max_payload_bytes=1024)
        for content in (b"a", b"b", b"a", b"c", b"b"):
            cache.facts("v1", content, lambda: [1])
        self.assertEqual(cache.hits, 1)
        self.assertEqual(cache.evictions, 2)
        self.assertEqual(cache.stats()["entries"], 2)
        tiny = ParseReuse(max_entries=5, max_payload_bytes=1)
        self.assertEqual(tiny.facts("v1", b"a", lambda: [1]), [1])
        self.assertEqual(tiny.stats()["entries"], 0)
        self.assertEqual(tiny.oversized, 1)
        bounded = ParseReuse(max_entries=100, max_payload_bytes=50)
        for i in range(20):
            bounded.facts("v1", str(i).encode(), lambda: ["hello"])
            self.assertLessEqual(bounded.payload_bytes, 50)
        for entries, size in ((0, 1), (1, 0), (-1, 1)):
            with self.assertRaises(ValueError):
                ParseReuse(max_entries=entries, max_payload_bytes=size)

    def test_scope_restored_after_exception_and_no_default_cache(self):
        calls = []
        def produce():
            calls.append(True)
            return 1
        with reuse_parses(max_entries=4, max_payload_bytes=1024) as outer:
            parsed_facts("v1", b"a", produce)
            with self.assertRaisesRegex(RuntimeError, "stop"):
                with reuse_parses(max_entries=4, max_payload_bytes=1024):
                    parsed_facts("v1", b"a", produce)
                    raise RuntimeError("stop")
            parsed_facts("v1", b"a", produce)
            self.assertEqual(outer.hits, 1)
        parsed_facts("v1", lambda: self.fail("disabled cache hashed content"), produce)
        self.assertEqual(len(calls), 3)

    def test_json_tolerances_hooks_and_errors(self):
        text = '{# comment\n"a": [1,],}'
        expected = _parse_json(text)
        with reuse_parses(max_entries=10, max_payload_bytes=4096) as cache:
            value, tolerances = _parse_json(text)
            value["a"].append(2)
            tolerances.clear()
            self.assertEqual(_parse_json(text), expected)
            calls = []
            def hook(pairs):
                calls.append(pairs)
                return dict(pairs)
            _parse_json('{"a": 1}', object_pairs_hook=hook)
            _parse_json('{"a": 1}', object_pairs_hook=hook)
            self.assertEqual(len(calls), 2)
            for _ in range(2):
                with self.assertRaises(json.JSONDecodeError):
                    _parse_json('{"broken":')
            self.assertEqual(cache.hits, 1)
            self.assertEqual(cache.stats()["entries"], 1)

    def test_class_facts_are_independent_including_unknown(self):
        data = _class_with_strings("data/M", ["hello"], ["method"])
        with reuse_parses(max_entries=10, max_payload_bytes=10000) as cache:
            first = _parse_class_file(data)
            first.string_constants.clear()
            first.methods.append(("changed", "()V", True))
            second = _parse_class_file(data)
            self.assertEqual(second.string_constants, {"hello"})
            self.assertEqual(second.methods, [])
            self.assertIsNone(_parse_class_file(b"unknown"))
            self.assertIsNone(_parse_class_file(b"unknown"))
            self.assertEqual(cache.hits, 2)
