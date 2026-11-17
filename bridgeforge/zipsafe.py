"""Bounded reads of zip and jar entries (ROADMAP 70 H2.4).

Mods, jars and the 42 GB backlog are untrusted input. `ZipFile.read` loads a whole entry into memory, and an entry's declared size can
lie, so a hostile or corrupt archive could exhaust memory in any command that reads jars. `read_limited` refuses an entry whose declared
size is over the limit. (Python's `zipfile` stops reading at the declared size, so a header that understates it fails the CRC check
instead of returning more data; the length check after the read is a backstop.) The error is an `OSError`. Readers that catch it per
entry skip the entry (the scanner lists it in `skipped_entries`); a walk over every class of a jar uses `read_class`, which returns
None for an oversize class, because a walk that caught the error per jar would let one huge entry hide every class after it
(ROADMAP-3 93.33, review 2026-11-17).

An entry's name is untrusted too. `javap_class_name` turns a class entry into an argument for javap only when it cannot be read as
anything but a class name (ROADMAP-3 93.45).
"""
from __future__ import annotations

import re
import zipfile

MAX_ENTRY_BYTES = 200 * 1024 * 1024  # any resource a real mod ships is far below this
MAX_CLASS_BYTES = 32 * 1024 * 1024  # a compiled class is a few hundred KB at most

# javap's launcher reads any argument starting with -J as a JVM option, wherever it stands on the command line: a jar entry
# named "-J-version.class" made the JVM print its version instead of running javap (JDK 25, 2026-11-17). javap also reads
# "@file" as an argument file, "x.class" as a file path and "a:b" as a URL. So a name from an untrusted jar reaches javap
# only as a plain binary class name: ASCII letters, digits, _ and $, separated by single dots. ASCII only, so the check
# does not depend on a code page: on Windows javap gets its arguments in the ANSI code page, and a character outside it
# arrives changed (U+FF0D arrived as "?" on cp1252, 2026-11-17).
_PLAIN_BINARY_NAME = re.compile(r"[A-Za-z0-9_$]+(?:\.[A-Za-z0-9_$]+)*")


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


def read_class(archive: zipfile.ZipFile, member: str | zipfile.ZipInfo) -> bytes | None:
    """A class entry, or None when it is over MAX_CLASS_BYTES: the caller skips it and goes on with the rest of the jar."""
    try:
        return read_limited(archive, member, MAX_CLASS_BYTES)
    except ZipEntryTooLarge:
        return None


def javap_class_name(entry: str) -> str | None:
    """The binary class name to give javap for a jar's class entry (`a/b/C.class` -> `a.b.C`), or None when the entry's name
    could be read as anything else: an option, an argument file, a path or a URL. Callers skip such an entry."""
    if not entry.endswith(".class"):
        return None
    name = entry[:-len(".class")].replace("/", ".")
    if not _PLAIN_BINARY_NAME.fullmatch(name) or name.endswith(".class"):
        return None
    return name


def entry_sha256(archive: zipfile.ZipFile, member: str | zipfile.ZipInfo, chunk_bytes: int = 1 << 20) -> str:
    """The SHA-256 of an entry, read in chunks: hashing needs no limit, only bounded memory (ROADMAP-3 93.33)."""
    import hashlib

    digest = hashlib.sha256()
    with archive.open(member) as handle:
        for block in iter(lambda: handle.read(chunk_bytes), b""):
            digest.update(block)
    return digest.hexdigest()
