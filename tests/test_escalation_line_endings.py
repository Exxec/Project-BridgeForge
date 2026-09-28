"""ROADMAP P15 item 20.14: an agent's LF-only edit of a CRLF file keeps CRLF when copied back."""
import unittest

from bridgeforge.escalation import _keep_line_endings


class KeepLineEndingsTests(unittest.TestCase):
    def test_crlf_original_restores_crlf(self) -> None:
        self.assertEqual(_keep_line_endings(b"a\r\nb\r\n", b"a\nc\n"), b"a\r\nc\r\n")

    def test_lf_original_and_binary_are_untouched(self) -> None:
        self.assertEqual(_keep_line_endings(b"a\nb\n", b"a\nc\n"), b"a\nc\n")
        self.assertEqual(_keep_line_endings(b"a\r\n", b"\x00\x01\n"), b"\x00\x01\n")
        self.assertEqual(_keep_line_endings(b"", b"new\n"), b"new\n")


if __name__ == "__main__":
    unittest.main()
