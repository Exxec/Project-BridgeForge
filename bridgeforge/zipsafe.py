"""Bounded reads of zip and jar entries (ROADMAP 70 H2.4).

Mods, jars and the 42 GB backlog are untrusted input. `ZipFile.read` loads a whole entry into memory, and an entry's declared size can
lie, so a hostile or corrupt archive could exhaust memory in any command that reads jars. `read_limited` refuses an entry whose declared
size is over the limit. (Python's `zipfile` stops reading at the declared size, so a header that understates it fails the CRC check
instead of returning more data; the length check after the read is a backstop.) The error is an `OSError`, which the jar
readers already catch per entry, so a refused entry is skipped and (in the scanner) listed with the entry's other read failures.
"""
from __future__ import annotations

import zipfile

MAX_ENTRY_BYTES = 200 * 1024 * 1024  # any resource a real mod ships is far below this
MAX_CLASS_BYTES = 32 * 1024 * 1024  # a compiled class is a few hundred KB at most


class ZipEntryTooLarge(OSError):
    """An archive entry is larger than the limit the caller allows."""


def read_limited(archive: zipfile.ZipFile, member: str | zipfile.ZipInfo, max_bytes: int = MAX_ENTRY_BYTES) -> bytes:
    info = member if isinstance(member, zipfile.ZipInfo) else archive.getinfo(member)
    if info.file_size > max_bytes:
        raise ZipEntryTooLarge(f"{info.filename}: declared size {info.file_size} bytes is over the {max_bytes} byte limit")
    with archive.open(info) as handle:
        data = handle.read(max_bytes + 1)  # reading to the end also checks the CRC
    if len(data) > max_bytes:
        raise ZipEntryTooLarge(f"{info.filename}: holds more than the {max_bytes} bytes its header declared")
    return data
