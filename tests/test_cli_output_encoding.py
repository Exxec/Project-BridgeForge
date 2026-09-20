"""`bridgeforge.cli._reconfigure_streams_for_pipes`: UTF-8-safe piped/redirected output.

Windows' default piped-output codepage (cp1252) corrupts the non-ASCII text several modules print
(`--json` output built with `ensure_ascii=False`, translate-check's CJK strings, ...); a real
`UnicodeEncodeError` was hit piping `bridgeforge ... --json` output on Windows (task A9). `main()`
calls this helper before doing anything else, so every command benefits without each print site
having to know about it.
"""
from __future__ import annotations

import unittest

from bridgeforge.cli import _reconfigure_streams_for_pipes


class _FakeStream:
    """A minimal stand-in for a TextIOWrapper. `isatty`/`reconfigure` are only bound to the
    instance when requested, so a fake without one behaves like an object that truly lacks it
    (getattr(..., None) misses it), rather than an inherited no-op class method."""

    def __init__(self, *, is_tty: bool = False, isatty_raises: bool = False, has_reconfigure: bool = True, has_isatty: bool = True) -> None:
        self._is_tty = is_tty
        self._isatty_raises = isatty_raises
        self.reconfigure_calls: list[dict[str, object]] = []
        if has_reconfigure:
            self.reconfigure = self._reconfigure
        if has_isatty:
            self.isatty = self._isatty

    def _isatty(self) -> bool:
        if self._isatty_raises:
            raise OSError("not a real console")
        return bool(self._is_tty)

    def _reconfigure(self, **kwargs: object) -> None:
        self.reconfigure_calls.append(kwargs)


class ReconfigureStreamsForPipesTests(unittest.TestCase):
    def test_a_piped_non_tty_stream_is_reconfigured_to_utf8_replace(self) -> None:
        stream = _FakeStream(is_tty=False)
        reconfigured = _reconfigure_streams_for_pipes([stream])
        self.assertEqual(reconfigured, [stream])
        self.assertEqual(stream.reconfigure_calls, [{"encoding": "utf-8", "errors": "replace"}])

    def test_an_interactive_console_is_left_untouched(self) -> None:
        stream = _FakeStream(is_tty=True)
        reconfigured = _reconfigure_streams_for_pipes([stream])
        self.assertEqual(reconfigured, [])
        self.assertEqual(stream.reconfigure_calls, [])

    def test_a_stream_with_no_reconfigure_is_skipped(self) -> None:
        stream = _FakeStream(is_tty=False, has_reconfigure=False)
        reconfigured = _reconfigure_streams_for_pipes([stream])
        self.assertEqual(reconfigured, [])

    def test_a_stream_with_no_isatty_at_all_is_treated_as_non_interactive(self) -> None:
        stream = _FakeStream(has_isatty=False)
        reconfigured = _reconfigure_streams_for_pipes([stream])
        self.assertEqual(reconfigured, [stream])
        self.assertEqual(stream.reconfigure_calls, [{"encoding": "utf-8", "errors": "replace"}])

    def test_a_stream_whose_isatty_raises_is_left_untouched(self) -> None:
        stream = _FakeStream(is_tty=False, isatty_raises=True)
        reconfigured = _reconfigure_streams_for_pipes([stream])
        self.assertEqual(reconfigured, [])
        self.assertEqual(stream.reconfigure_calls, [])

    def test_multiple_streams_are_handled_independently(self) -> None:
        console = _FakeStream(is_tty=True)
        piped = _FakeStream(is_tty=False)
        reconfigured = _reconfigure_streams_for_pipes([console, piped])
        self.assertEqual(reconfigured, [piped])

    def test_default_targets_real_sys_stdout_and_stderr(self) -> None:
        # No streams argument: it must at least run cleanly against the real (interactive-in-tests,
        # or captured-by-the-test-runner) sys.stdout/sys.stderr without raising.
        _reconfigure_streams_for_pipes()


if __name__ == "__main__":
    unittest.main()
