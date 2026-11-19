"""Where BridgeForge keeps its compiled Java helpers: a private, per-user folder in the temp directory (ROADMAP-3 93.51).

The AST, bytecode, bytecode-rewrite and delegate-method helpers are compiled once and reused from the temp folder. They
were kept in a shared `<temp>/bridgeforge-<kind>/` and reused without a check, so on a shared POSIX `/tmp` another local
user could plant a class there that BridgeForge would then run. Each user now has their own folder: created with mode
0700, and refused when it is a link, belongs to another user or others may write to it. Windows' temp folder is already
per user, so there only the folder name changes.
"""
from __future__ import annotations

import getpass
import os
import stat
import tempfile
from pathlib import Path


class HelperCacheUnsafe(RuntimeError):
    """The helper cache folder could hold another user's files."""


def _owner_tag() -> str:
    getuid = getattr(os, "getuid", None)
    if getuid is not None:
        return str(getuid())
    return "".join(ch for ch in getpass.getuser() if ch.isalnum() or ch in "-_") or "user"


_ELSEWHERE = "or set TMPDIR to a folder only you can write to"


def _check_private(folder: Path) -> None:
    # On Windows only the link test runs (a junction is not S_ISLNK): this relies on %TEMP% being per user, as it is by
    # default. A TEMP/TMP pointed at a shared folder would need an ACL check here.
    info = os.lstat(folder)
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise HelperCacheUnsafe(f"{folder} is not a plain folder; remove it, {_ELSEWHERE}.")
    if hasattr(os, "getuid"):
        if info.st_uid != os.getuid():
            raise HelperCacheUnsafe(f"{folder} belongs to another user; ask an administrator to remove it, {_ELSEWHERE}.")
        if info.st_mode & 0o077:
            raise HelperCacheUnsafe(f"{folder} is open to other users (mode {oct(info.st_mode & 0o777)}); remove it, {_ELSEWHERE}.")


def helper_cache_root(base: Path | None = None) -> Path:
    """This user's private helper cache folder, created if missing and checked every time."""
    root = Path(base if base is not None else tempfile.gettempdir()) / f"bridgeforge-helpers-{_owner_tag()}"
    try:
        root.mkdir(mode=0o700)
    except FileExistsError:
        pass
    _check_private(root)
    return root


def helper_directory(kind: str, digest: str, unavailable: type[Exception] = HelperCacheUnsafe) -> Path:
    """The folder for one compiled helper (`kind`, e.g. "ast") at one source digest, inside the private root.

    An unsafe folder raises `unavailable`, the caller's own "helper unavailable" error, so a scan degrades as it does
    without a JDK instead of ending (a planted folder would otherwise stop every scan)."""
    try:
        return helper_cache_root() / kind / digest
    except HelperCacheUnsafe as exc:
        if unavailable is HelperCacheUnsafe:
            raise
        raise unavailable(str(exc)) from exc
