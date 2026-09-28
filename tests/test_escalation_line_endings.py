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


class ResolveAgentCommandTests(unittest.TestCase):
    """ROADMAP P15 item 20.13: find the VS Code extension's claude binary when claude is not on PATH."""

    def test_extension_binary_is_used_when_claude_is_not_on_path(self) -> None:
        import os
        from unittest import mock

        from bridgeforge.escalation import resolve_agent_command
        from tests.support import resolved_temp_dir

        binary = "claude.exe" if os.name == "nt" else "claude"
        with resolved_temp_dir() as home, mock.patch("bridgeforge.escalation.shutil.which", return_value=None):
            for version in ("2.1.9", "2.1.283"):
                target = home / ".vscode" / "extensions" / f"anthropic.claude-code-{version}-win32-x64" / "resources" / "native-binary" / binary
                target.parent.mkdir(parents=True)
                target.write_bytes(b"")
            resolved = resolve_agent_command("claude -p --permission-mode acceptEdits", home=home)
            other = resolve_agent_command("python agent.py", home=home)
        self.assertIn("anthropic.claude-code-2.1.283", resolved)  # newest by number, not by name
        self.assertTrue(resolved.endswith(' -p --permission-mode acceptEdits'))
        self.assertEqual(other, "python agent.py")
