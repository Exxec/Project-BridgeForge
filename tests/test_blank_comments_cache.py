"""ROADMAP-3 96.5 P4: a Java file's comments are blanked once per process, not once per source check.

A Sunrider scan (86 .java files) called `_blank_java_comments` 4,523 times, about 5 s of a 25 s scan: some 40 checks each
blank every file again. The result is now kept per (text, strings) in a bounded cache.
"""
from __future__ import annotations

import threading
import unittest
from unittest import mock

from bridgeforge.scan import scan_javatext
from bridgeforge.scan.scan_javatext import _blank_java_comments

SAMPLES = [
    'int a = 1; // note\nString s = "http://x"; /* block\n spans */ char c = \'/\';\n',
    'String t = "esc \\" // not a comment"; // real\n',
    "/* unterminated\n comment",
    'log("couldn\'t find the class for a System"); class Real {}\n',
    "",
]


class BlankCommentsCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        scan_javatext.clear_blank_cache()
        self.addCleanup(scan_javatext.clear_blank_cache)

    def test_cached_results_equal_the_uncached_ones(self) -> None:
        for text in SAMPLES:
            for strings in (False, True):
                expected = scan_javatext._blank_java_comments_uncached(text, strings)
                self.assertEqual(_blank_java_comments(text, strings), expected)
                self.assertEqual(_blank_java_comments(text, strings=strings), expected)  # the cached path

    def test_each_text_and_mode_is_blanked_once(self) -> None:
        real = scan_javatext._blank_java_comments_uncached
        with mock.patch.object(scan_javatext, "_blank_java_comments_uncached", side_effect=real) as uncached:
            for _ in range(40):  # one scan's source checks
                for text in SAMPLES:
                    _blank_java_comments(text)
                    _blank_java_comments(text, strings=True)
        self.assertEqual(uncached.call_count, 2 * len(SAMPLES))

    def test_an_equal_text_read_again_is_a_hit(self) -> None:
        # Each check reads the file again, so the text is a new, equal string object.
        text = "int x; // c\n" * 50
        with mock.patch.object(scan_javatext, "_blank_java_comments_uncached",
                               side_effect=scan_javatext._blank_java_comments_uncached) as uncached:
            _blank_java_comments(text)
            _blank_java_comments("".join(list(text)))
        self.assertEqual(uncached.call_count, 1)

    def test_the_cache_stays_within_its_character_budget(self) -> None:
        with mock.patch.object(scan_javatext, "BLANK_CACHE_MAX_CHARS", 1000):
            for index in range(50):
                _blank_java_comments(f"int v{index}; // {'x' * 80}\n")
            self.assertLessEqual(scan_javatext._blank_cache_chars(), 1000)
            big = "// " + "y" * 2000 + "\n"  # larger than the whole budget: blanked, not kept
            self.assertEqual(_blank_java_comments(big), scan_javatext._blank_java_comments_uncached(big))
            self.assertLessEqual(scan_javatext._blank_cache_chars(), 1000)

    def test_threads_get_correct_results(self) -> None:
        texts = [f"int t{i}; /* {i} */ // tail {i}\n" * (i % 7 + 1) for i in range(64)]
        failures: list[str] = []

        def work(offset: int) -> None:
            for step in range(len(texts)):
                text = texts[(offset + step) % len(texts)]
                if _blank_java_comments(text) != scan_javatext._blank_java_comments_uncached(text):
                    failures.append(text)

        threads = [threading.Thread(target=work, args=(n,)) for n in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
