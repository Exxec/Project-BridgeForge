"""ROADMAP-3 93.51: compiled helpers live in a private per-user folder; a .bat adapter never gets cmd.exe metacharacters."""
from __future__ import annotations

import os
import stat
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from bridgeforge.bytecode import helper_cache, java_ast
from bridgeforge.bytecode.helper_cache import HelperCacheUnsafe, helper_cache_root
from bridgeforge.decompiler import create_decompiler_review, run_decompiler_review
from tests.support import resolved_temp_dir
from tests.support import write_text as _write


def _fake_stat(mode: int, uid: int) -> os.stat_result:
    return os.stat_result((mode, 0, 0, 1, uid, 0, 0, 0, 0, 0))


class HelperCacheTests(unittest.TestCase):
    def test_the_root_is_per_user_and_reused(self) -> None:
        with resolved_temp_dir() as base:
            first = helper_cache_root(base)
            self.assertTrue(first.name.startswith("bridgeforge-helpers-"))
            self.assertEqual(helper_cache_root(base), first)
            if hasattr(os, "getuid"):
                self.assertEqual(stat.S_IMODE(first.stat().st_mode), 0o700)

    def test_a_folder_of_another_user_or_open_to_others_or_a_link_is_refused(self) -> None:
        with resolved_temp_dir() as base:
            cases = {"another user": _fake_stat(stat.S_IFDIR | 0o700, 4242),
                     "open to others": _fake_stat(stat.S_IFDIR | 0o777, 1000),
                     "a link": _fake_stat(stat.S_IFLNK | 0o777, 1000)}
            for name, fake in cases.items():
                with self.subTest(name=name), mock.patch.object(os, "getuid", create=True, return_value=1000), \
                        mock.patch.object(helper_cache.os, "lstat", return_value=fake), self.assertRaises(HelperCacheUnsafe):
                    helper_cache_root(base)
            with mock.patch.object(os, "getuid", create=True, return_value=1000), \
                    mock.patch.object(helper_cache.os, "lstat", return_value=_fake_stat(stat.S_IFDIR | 0o700, 1000)):
                self.assertEqual(helper_cache_root(base).name, "bridgeforge-helpers-1000")  # the user's own private folder passes

    @unittest.skipUnless(hasattr(os, "getuid"), "POSIX permissions and symlinks")
    def test_a_real_link_or_open_folder_is_refused_on_posix(self) -> None:
        with resolved_temp_dir() as base, resolved_temp_dir() as elsewhere:
            (base / f"bridgeforge-helpers-{os.getuid()}").symlink_to(elsewhere, target_is_directory=True)
            with self.assertRaises(HelperCacheUnsafe):
                helper_cache_root(base)
        with resolved_temp_dir() as base:
            root = helper_cache_root(base)
            root.chmod(0o755)
            with self.assertRaisesRegex(HelperCacheUnsafe, "open to other users"):
                helper_cache_root(base)

    def test_an_unsafe_folder_is_the_caller_s_unavailable_error_so_a_scan_degrades(self) -> None:
        from bridgeforge.bytecode.bytecode import BytecodeUnavailable

        with mock.patch.object(helper_cache, "helper_cache_root", side_effect=HelperCacheUnsafe("planted")):
            with self.assertRaisesRegex(java_ast.AstUnavailable, "planted"):
                java_ast._helper_directory()
            with self.assertRaisesRegex(BytecodeUnavailable, "planted"):
                helper_cache.helper_directory("bytecode", "d", BytecodeUnavailable)
            with self.assertRaises(HelperCacheUnsafe):
                helper_cache.helper_directory("bytecode", "d")

    def test_the_helpers_use_the_private_root(self) -> None:
        with resolved_temp_dir() as base, mock.patch.object(helper_cache.tempfile, "gettempdir", return_value=str(base)):
            self.assertEqual(java_ast._helper_directory().parent.parent, helper_cache_root(base))
            for source, kind in (("bytecode/bytecode.py", '"bytecode"'), ("bytecode/bytecode.py", '"bytecode-rewrite"'),
                                 ("delegate_method.py", '"delegate"')):
                text = (Path(java_ast.__file__).parent.parent / source).read_text(encoding="utf-8")
                self.assertIn(f"helper_directory({kind}", text)
                self.assertNotIn("gettempdir()) / \"bridgeforge-", text)


class BatAdapterTests(unittest.TestCase):
    def _plan(self, root: Path, adapter_name: str, jar_name: str, extra: tuple[str, ...] = ()) -> Path:
        jar = root / "in" / jar_name
        jar.parent.mkdir(parents=True)
        jar.write_bytes(b"PK")
        adapter = root / "tools" / adapter_name
        _write(adapter, "@echo off\n")
        output = root / "review"
        create_decompiler_review(jar, output, adapter, ["{input}", "{output}", *extra])
        return output

    def test_every_character_cmd_acts_on_is_refused_in_any_argument(self) -> None:
        for value in ('--x="y"', "--x=!y!", "--x=a|b", "--x=a\nb", "--x=a<b", "--x=a>b"):
            with self.subTest(value=value), resolved_temp_dir() as root:
                output = self._plan(root, "decompile.cmd", "plain.jar", (value,))
                with mock.patch.object(subprocess, "run") as run, self.assertRaisesRegex(ValueError, "cmd.exe would act on"):
                    run_decompiler_review(output, execute=True)
                run.assert_not_called()

    def test_a_trailing_dot_or_space_still_counts_as_a_batch_file(self) -> None:
        from bridgeforge.decompiler import _refuse_cmd_metacharacters

        for name in ("x.bat.", "x.BAT ", "x.Cmd. "):
            with self.subTest(name=name), self.assertRaises(ValueError):
                _refuse_cmd_metacharacters(Path("C:/tools") / name, ["C:/tools/x.bat", "a&b"])

    def test_a_bat_adapter_refuses_an_argument_cmd_would_act_on(self) -> None:
        for jar_name in ("a&calc.jar", "a%PATH%.jar", "a^b.jar"):
            with self.subTest(jar=jar_name), resolved_temp_dir() as root:
                output = self._plan(root, "decompile.bat", jar_name)
                with mock.patch.object(subprocess, "run") as run, self.assertRaisesRegex(ValueError, "cmd.exe would act on"):
                    run_decompiler_review(output, execute=True)
                run.assert_not_called()

    def test_a_plain_path_or_a_non_batch_adapter_still_runs(self) -> None:
        done = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        for adapter, jar_name in (("decompile.bat", "plain.jar"), ("decompile.exe", "a&b.jar")):
            with self.subTest(adapter=adapter), resolved_temp_dir() as root:
                output = self._plan(root, adapter, jar_name)
                with mock.patch.object(subprocess, "run", return_value=done) as run:
                    self.assertEqual(run_decompiler_review(output, execute=True)["status"], "PASS")
                run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
