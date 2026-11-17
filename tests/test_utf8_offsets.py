"""ROADMAP-3 96.5 P6: `_invalid_utf8_offsets` in one pass gives exactly the offsets of the old loop, which re-decoded the rest of
the file after every bad byte (quadratic: the suite's slowest test, a large CP-1252 rules.csv, took 24-38 s)."""
from __future__ import annotations

import random
import unittest
from concurrent.futures import ThreadPoolExecutor

from bridgeforge.fixers.encoding import _invalid_utf8_offsets


def _old_loop(raw: bytes) -> list[int]:
    """The implementation before P6, kept as the reference."""
    offsets, start = [], 0
    while start < len(raw):
        try:
            raw[start:].decode("utf-8")
            break
        except UnicodeDecodeError as exc:
            offsets.append(start + exc.start)
            start += exc.start + 1
    return offsets


# Valid ASCII and multi-byte sequences, CP-1252 punctuation, truncated sequences, overlong forms, encoded surrogates, bytes above
# U+10FFFF, stray continuation bytes and bytes that never start a sequence.
_PIECES = (b"a", b"\n", b"\xe2\x80\x99", b"\xf0\x9f\x98\x80", b"\x92", b"\x93", b"\xa0", b"\xe2\x80", b"\xe2", b"\xc3",
           b"\xf0\x9f\x98", b"\xc0\xaf", b"\xe0\x80\xaf", b"\xed\xa0\x80", b"\xf4\x90\x80\x80", b"\x80", b"\xbf", b"\xff", b"\xfe")


def _cases() -> list[bytes]:
    rng = random.Random(20261117)
    fixed = [b"", b"plain ascii", b"\x92", b"\xe2", b"ab\xe2\x82", b"ab\xe2\x82A", b"\xe2\x80\x99 fine", b"\xff\xfe\xfd",
             b"caf\xe9 au lait", b"x" * 1000 + b"\x92" + b"y" * 1000]
    return fixed + [b"".join(rng.choice(_PIECES) for _ in range(rng.randint(0, 48))) for _ in range(600)]


class InvalidUtf8OffsetsTests(unittest.TestCase):
    def test_the_one_pass_offsets_equal_the_old_loops(self) -> None:
        for raw in _cases():
            with self.subTest(raw=raw[:60]):
                self.assertEqual(_invalid_utf8_offsets(raw), _old_loop(raw))

    def test_threads_never_share_their_offsets(self) -> None:
        # The error handler is registered once, globally; each thread collects into its own list.
        cases = _cases()
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(_invalid_utf8_offsets, cases * 4))
        self.assertEqual(results, [_old_loop(raw) for raw in cases] * 4)

    def test_a_large_cp1252_file_is_one_pass(self) -> None:
        # About 120,000 isolated CP-1252 bytes in 2.4 MB: the old loop re-decoded the remainder 120,000 times.
        raw = (b"id,text\n" + b"row,It\x92s \x93quoted\x94 text\n" * 40000)
        offsets = _invalid_utf8_offsets(raw)
        self.assertEqual(len(offsets), 120000)
        self.assertEqual(offsets[:3], [raw.index(b"\x92"), raw.index(b"\x93"), raw.index(b"\x94")])


if __name__ == "__main__":
    unittest.main()
