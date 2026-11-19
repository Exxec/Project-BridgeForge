"""ROADMAP-3 95.5 / 93.27: digests reused across a run's prepare, release and evaluate while a file is unchanged."""
from __future__ import annotations

import json
import os
import unittest

from bridgeforge import file_hash
from bridgeforge.file_hash import cached_hashes, sha256_cached, sha256_file, sha256_many
from tests.support import resolved_temp_dir
from tests.support import write_text as _write


class HashCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        context = resolved_temp_dir()
        self.tmp = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        self.files = [self.tmp / "mod" / f"f{i}.txt" for i in range(5)]
        for i, path in enumerate(self.files):
            _write(path, f"content {i}\n" * (i + 1))
        self.cache_file = self.tmp / "rig" / "rig_hash_cache.json"

    def test_digests_equal_sha256_file_inside_and_outside_a_scope(self) -> None:
        expected = {path: sha256_file(path) for path in self.files}
        self.assertEqual(sha256_many(self.files), expected)
        with cached_hashes(self.cache_file):
            self.assertEqual(sha256_many(self.files), expected)
        with cached_hashes(self.cache_file):
            self.assertEqual(sha256_many(self.files), expected)  # now from the saved cache
            self.assertEqual(sha256_cached(self.files[0]), expected[self.files[0]])

    def test_second_scope_reuses_the_saved_cache(self) -> None:
        with cached_hashes(self.cache_file) as first:
            sha256_many(self.files)
        self.assertEqual((first.hits, first.misses), (0, 5))
        saved = json.loads(self.cache_file.read_text(encoding="utf-8"))
        self.assertEqual(saved["schema"], file_hash.CACHE_SCHEMA)
        self.assertEqual(len(saved["files"]), 5)
        with cached_hashes(self.cache_file) as second:
            sha256_many(self.files)
        self.assertEqual((second.hits, second.misses), (5, 0))

    def test_a_changed_file_is_hashed_again(self) -> None:
        with cached_hashes(self.cache_file):
            sha256_many(self.files)
        changed = self.files[2]
        stat = changed.stat()
        _write(changed, "other bytes, same moment\n")
        os.utime(changed, ns=(stat.st_atime_ns, stat.st_mtime_ns))  # size changed, time restored
        touched = self.files[3]
        before = touched.stat().st_mtime_ns
        os.utime(touched, ns=(before + 5_000_000_000, before + 5_000_000_000))  # same bytes, newer time
        with cached_hashes(self.cache_file) as cache:
            digests = sha256_many(self.files)
        self.assertEqual(digests[changed], sha256_file(changed))
        self.assertEqual((cache.hits, cache.misses), (3, 2))

    def test_no_scope_writes_no_cache(self) -> None:
        sha256_many(self.files)
        sha256_cached(self.files[0])
        self.assertFalse(self.cache_file.exists())
        self.assertIsNone(file_hash._active.get())

    def test_an_enclosing_scope_is_kept_and_saved_once(self) -> None:
        inner_file = self.tmp / "elsewhere" / "inner.json"
        with cached_hashes(self.cache_file) as outer:
            with cached_hashes(inner_file) as inner:
                self.assertIs(inner, outer)
                sha256_many(self.files)
        self.assertTrue(self.cache_file.is_file())
        self.assertFalse(inner_file.exists())

    def test_an_unreadable_or_foreign_cache_starts_empty(self) -> None:
        for text in ("not json", json.dumps({"schema": 99, "files": {}}), json.dumps([1, 2])):
            _write(self.cache_file, text)
            with cached_hashes(self.cache_file) as cache:
                self.assertEqual(sha256_many(self.files[:1]), {self.files[0]: sha256_file(self.files[0])})
            self.assertEqual((cache.hits, cache.misses), (0, 1))

    def test_a_cache_entry_with_a_wrong_digest_is_trusted_only_while_the_stamp_holds(self) -> None:
        # The cache is a speed-up keyed by size and time, not proof: a changed stamp always re-hashes.
        with cached_hashes(self.cache_file):
            sha256_many(self.files[:1])
        data = json.loads(self.cache_file.read_text(encoding="utf-8"))
        key = next(iter(data["files"]))
        data["files"][key][1] += 1  # the recorded time no longer matches the file
        _write(self.cache_file, json.dumps(data))
        with cached_hashes(self.cache_file) as cache:
            sha256_many(self.files[:1])
        self.assertEqual((cache.hits, cache.misses), (0, 1))


class TreeHashThroughCacheTests(unittest.TestCase):
    def test_shipped_and_tree_hash_are_unchanged_by_the_cache(self) -> None:
        from bridgeforge.live.live_trust import shipped_hash
        from bridgeforge.run_manifest import HASH_CACHE_FILE, _tree_hash

        context = resolved_temp_dir()
        tmp = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        mod = tmp / "prepatcher"
        _write(mod / "mod_info.json", json.dumps({"id": "starsector_prepatcher", "name": "P", "version": "1"}))
        _write(mod / "data" / "a.csv", "id\nx\n")
        _write(mod / "logs" / "prepatcher.log", "runtime output\n")
        plain = tmp / "plain"
        _write(plain / "mod_info.json", json.dumps({"id": "plain", "name": "P", "version": "1"}))
        _write(plain / "data" / "b.csv", "id\ny\n")
        before = (_tree_hash(mod), shipped_hash(plain), _tree_hash(plain))
        cache_file = tmp / "rig" / HASH_CACHE_FILE
        with cached_hashes(cache_file):
            first = (_tree_hash(mod), shipped_hash(plain), _tree_hash(plain))
        with cached_hashes(cache_file) as cache:
            second = (_tree_hash(mod), shipped_hash(plain), _tree_hash(plain))
        self.assertEqual(first, before)
        self.assertEqual(second, before)
        self.assertGreater(cache.hits, 0)
        self.assertEqual(cache.misses, 0)


if __name__ == "__main__":
    unittest.main()
