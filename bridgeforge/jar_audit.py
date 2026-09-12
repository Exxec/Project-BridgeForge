from __future__ import annotations

import hashlib
import io
import struct
import zipfile
from pathlib import Path

# Library packages a "rebuilt" jar may legitimately bundle because javac compiled the library's
# sources off the classpath rather than the mod's own sources; real case: every Exigency rebuild
# carried 40 GraphicsLib classes (190 vs. the original's 165) before this was caught.
LIBRARY_PACKAGE_PREFIXES = ("org/dark/", "org/lazywizard/", "org/magiclib/", "lunalib/", "exerelin/", "org/json/")

# RC8's script sandbox throws SecurityException at class-load time for reflection, File, or NIO use;
# a class referencing these needs manual review, not an automatic catch of ReflectiveOperationException
# or IOException (neither of those symbols share these prefixes).
REFLECTION_SYMBOL_PREFIXES = ("java/lang/reflect/", "java/io/File", "java/nio/file/")

_CONSTANT_UTF8 = 1
_CONSTANT_INTEGER = 3
_CONSTANT_FLOAT = 4
_CONSTANT_LONG = 5
_CONSTANT_DOUBLE = 6
_CONSTANT_CLASS = 7
_CONSTANT_STRING = 8
_CONSTANT_FIELDREF = 9
_CONSTANT_METHODREF = 10
_CONSTANT_INTERFACE_METHODREF = 11
_CONSTANT_NAME_AND_TYPE = 12
_CONSTANT_METHOD_HANDLE = 15
_CONSTANT_METHOD_TYPE = 16
_CONSTANT_DYNAMIC = 17
_CONSTANT_INVOKE_DYNAMIC = 18
_CONSTANT_MODULE = 19
_CONSTANT_PACKAGE = 20


class ClassFileError(ValueError):
    """Raised when class-file bytes cannot be parsed as a constant pool."""


def parse_constant_pool(data: bytes) -> list[tuple | None]:
    """Parse a .class file's constant pool. Returns a 1-indexed list (index 0 is a placeholder)."""
    if len(data) < 10 or data[:4] != b"\xca\xfe\xba\xbe":
        raise ClassFileError("Not a valid Java class file (bad magic).")
    pool_count = struct.unpack_from(">H", data, 8)[0]
    offset = 10
    entries: list[tuple | None] = [None]
    index = 1
    try:
        while index < pool_count:
            tag = data[offset]
            offset += 1
            if tag == _CONSTANT_UTF8:
                length = struct.unpack_from(">H", data, offset)[0]
                offset += 2
                raw = data[offset:offset + length]
                offset += length
                entries.append((tag, raw.decode("utf-8", errors="replace")))
            elif tag in (_CONSTANT_CLASS, _CONSTANT_STRING, _CONSTANT_METHOD_TYPE, _CONSTANT_MODULE, _CONSTANT_PACKAGE):
                value = struct.unpack_from(">H", data, offset)[0]
                offset += 2
                entries.append((tag, value))
            elif tag in (_CONSTANT_FIELDREF, _CONSTANT_METHODREF, _CONSTANT_INTERFACE_METHODREF, _CONSTANT_NAME_AND_TYPE, _CONSTANT_DYNAMIC, _CONSTANT_INVOKE_DYNAMIC):
                a, b = struct.unpack_from(">HH", data, offset)
                offset += 4
                entries.append((tag, a, b))
            elif tag in (_CONSTANT_INTEGER, _CONSTANT_FLOAT):
                offset += 4
                entries.append((tag, None))
            elif tag in (_CONSTANT_LONG, _CONSTANT_DOUBLE):
                offset += 8
                entries.append((tag, None))
                entries.append(None)  # long/double occupy two constant-pool slots
                index += 1
            elif tag == _CONSTANT_METHOD_HANDLE:
                offset += 3
                entries.append((tag, None))
            else:
                raise ClassFileError(f"Unsupported constant-pool tag {tag}.")
            index += 1
    except (struct.error, IndexError) as exc:
        raise ClassFileError(f"Truncated or malformed constant pool: {exc}") from exc
    return entries


def referenced_class_names(entries: list[tuple | None]) -> set[str]:
    """Return the internal class names (e.g. 'java/lang/reflect/Field') a constant pool references."""
    names: set[str] = set()
    for entry in entries:
        if entry is not None and entry[0] == _CONSTANT_CLASS:
            name_index = entry[1]
            if 0 < name_index < len(entries) and entries[name_index] is not None and entries[name_index][0] == _CONSTANT_UTF8:
                names.add(entries[name_index][1])
    return names


def _classes_from_zip(archive: zipfile.ZipFile) -> dict[str, bytes]:
    classes: dict[str, bytes] = {}
    for info in archive.infolist():
        if info.is_dir() or not info.filename.lower().endswith(".class"):
            continue
        classes[info.filename] = archive.read(info.filename)
    return classes


def _is_jar_zip(archive: zipfile.ZipFile) -> bool:
    """A jar (as opposed to a release .zip) has .class entries directly in it.

    Backups from real revival work are routinely renamed with extra suffixes
    (e.g. "al_arkleg.jar.pre-ring-guard.bak"), so detection must not depend on
    the file's extension — only on whether it is a zip and what it contains.
    """
    return any(info.filename.lower().endswith(".class") for info in archive.infolist())


def _resolve_jar_classes(path: Path, rebuilt_name: str | None, error_prefix: str) -> dict[str, bytes]:
    """Resolve a path to its jar's compiled classes, sniffing zip content rather than trusting the extension.

    A zip magic (PK\\x03\\x04) file with .class entries at top level is treated as the jar itself
    (whatever it is named); otherwise, if it is a zip containing a .jar member, that inner jar is
    used. A file that is not a zip at all keeps the original, extension-based error message.
    """
    if not zipfile.is_zipfile(path):
        raise ValueError(f"{error_prefix} must be an existing .jar file or a .zip archive containing one.")
    with zipfile.ZipFile(path) as archive:
        if _is_jar_zip(archive):
            return _classes_from_zip(archive)
        jar_entries = [info for info in archive.infolist() if not info.is_dir() and info.filename.lower().endswith(".jar")]
        if not jar_entries:
            raise ValueError(f"{error_prefix} must be an existing .jar file or a .zip archive containing one.")
        if rebuilt_name is not None:
            name_matches = [info for info in jar_entries if Path(info.filename).name.lower() == rebuilt_name.lower()]
        else:
            name_matches = []
        if name_matches:
            chosen = name_matches[0]
        elif len(jar_entries) == 1:
            chosen = jar_entries[0]
        else:
            chosen = max(jar_entries, key=lambda info: info.file_size)
        jar_bytes = archive.read(chosen)
    with zipfile.ZipFile(io.BytesIO(jar_bytes)) as inner:
        return _classes_from_zip(inner)


def _load_original_classes(original: Path, rebuilt_name: str) -> dict[str, bytes]:
    original = Path(original).expanduser().resolve()
    if not original.is_file():
        raise ValueError(f"{original} is not an existing .jar file or a .zip archive containing one.")
    return _resolve_jar_classes(original, rebuilt_name, "--original")


def _package_of(class_entry_name: str) -> str:
    posix = class_entry_name.replace("\\", "/")
    return posix.rsplit("/", 1)[0] if "/" in posix else ""


def audit_jar(rebuilt_path: Path, original_path: Path) -> dict[str, object]:
    """Compare a rebuilt mod jar with its ORIGINAL; never writes either input."""
    rebuilt_path = Path(rebuilt_path).expanduser().resolve()
    if not rebuilt_path.is_file():
        raise ValueError(f"{rebuilt_path} is not an existing file.")
    rebuilt_classes = _resolve_jar_classes(rebuilt_path, None, "rebuilt jar")
    original_classes = _load_original_classes(original_path, rebuilt_path.name)

    rebuilt_names = set(rebuilt_classes)
    original_names = set(original_classes)
    removed = sorted(original_names - rebuilt_names)
    added = sorted(rebuilt_names - original_names)
    common = rebuilt_names & original_names
    changed = sorted(name for name in common if hashlib.sha256(rebuilt_classes[name]).digest() != hashlib.sha256(original_classes[name]).digest())
    unchanged_count = len(common) - len(changed)

    rebuilt_packages = {_package_of(name) for name in rebuilt_names}
    original_packages = {_package_of(name) for name in original_names}
    new_packages = sorted(rebuilt_packages - original_packages)
    bundled_library_packages = sorted(pkg for pkg in new_packages if any(pkg.startswith(prefix.rstrip("/")) for prefix in LIBRARY_PACKAGE_PREFIXES))
    unexpected_new_packages = sorted(pkg for pkg in new_packages if pkg not in bundled_library_packages)

    reflection_findings = []
    parse_errors = []
    for name in sorted(rebuilt_classes):
        try:
            entries = parse_constant_pool(rebuilt_classes[name])
        except ClassFileError as exc:
            parse_errors.append({"class": name, "error": str(exc)})
            continue
        flagged = sorted(symbol for symbol in referenced_class_names(entries) if any(symbol.startswith(prefix) for prefix in REFLECTION_SYMBOL_PREFIXES))
        if flagged:
            reflection_findings.append({"class": name, "referenced_symbols": flagged})

    status = "PASS"
    if removed or unexpected_new_packages:
        status = "REVIEW"
    if bundled_library_packages or reflection_findings:
        status = "MANUAL"

    return {
        "schema_version": 1,
        "mode": "READ_ONLY_JAR_AUDIT",
        "rebuilt": str(rebuilt_path),
        "original": str(Path(original_path).expanduser().resolve()),
        "rebuilt_class_count": len(rebuilt_names),
        "original_class_count": len(original_names),
        "removed_classes": [{"class": name, "classification": "REVIEW"} for name in removed],
        "added_classes": added,
        "changed_class_count": len(changed),
        "unchanged_class_count": unchanged_count,
        "changed_classes": changed,
        "bundled_library_packages": [
            {"package": pkg, "classification": "MANUAL", "reason": "bundled library classes — javac compiled library sources from the classpath"}
            for pkg in bundled_library_packages
        ],
        "unexpected_new_packages": [{"package": pkg, "classification": "REVIEW"} for pkg in unexpected_new_packages],
        "reflection_findings": [
            {
                "class": finding["class"],
                "referenced_symbols": finding["referenced_symbols"],
                "classification": "MANUAL",
                "reason": "RC8 script sandbox throws SecurityException at load for reflection/File/NIO API use; requires manual review.",
            }
            for finding in reflection_findings
        ],
        "parse_errors": parse_errors,
        "status": status,
    }
