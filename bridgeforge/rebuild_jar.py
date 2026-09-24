"""`bridgeforge rebuild-jar`: rebuild a mod's jar from its sources and prove the result matches the original.

Compiles `--sources` against RC8 (+ the mod's other jars and its declared dependencies), packages
the classes into a jar that keeps the original's manifest and any non-class resources, and compares
that rebuild with the ORIGINAL `--jar` at the class and member (method/field) level. Known
compiler-only differences (a class-file version bump, a synchronized-modifier-only change, a
Lombok `$lock`/`$LOCK` field, a synthetic `access$`/`lambda$` member) are normalized into
`expected_differences` rather than reported as changes needing review.

PASS means the rebuild is a verified equivalent of the original: nothing lost, nothing added or
changed beyond the normalized compiler noise, no forbidden sandbox references, everything parses.
REVIEW means nothing was LOST but something else is worth a look (an addition, a non-normalized
modifier change, an unparseable class, a forbidden sandbox reference). FAIL means a class or member
present in the original is missing from the rebuild and isn't one of the normalized cases -- other
code (another mod, a save, rules.csv) may still reference it. `--install` only proceeds on PASS.

Never touches original/ (read-only reference). Never writes into working/ unless --install is
given, and even then only after a PASS: the previous jar at the same working-copy path is moved to
scratch/moved-<date>/ with a MOVES.log line before the new one is copied in.
"""
from __future__ import annotations

import io
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .java_toolchain import ClasspathResult, assemble_classpath, find_jdk, run_javac
from .workspace import resolve_inside

SCHEMA_VERSION = 1

# RC8's script sandbox throws SecurityException at class-load time for these (see scanner.py's
# identical FORBIDDEN_* constants / docs/BUG_CLASSES.md); redefined locally rather than imported
# so this module has no dependency on scanner.py beyond what java_toolchain.py already needs.
_FORBIDDEN_REFLECT_PREFIX = "java/lang/reflect/"
_FORBIDDEN_NIO_FILE_PREFIX = "java/nio/file/"
_FORBIDDEN_IO_CLASSES = {
    "java/io/File", "java/io/FileInputStream", "java/io/FileOutputStream",
    "java/io/FileReader", "java/io/FileWriter", "java/io/RandomAccessFile",
}

_ACC_SYNCHRONIZED = 0x0020
_ACC_SYNTHETIC = 0x1000
_LOMBOK_LOCK_FIELD_NAMES = {"$lock", "$LOCK"}
_FIXED_DATE_TIME = (1980, 1, 1, 0, 0, 0)  # deterministic jar entry timestamp (ZIP epoch minimum)


class RebuildJarError(ValueError):
    """Raised for a refused or invalid rebuild-jar request (bad paths, no JDK-independent input, etc.)."""


# --- workspace / path resolution --------------------------------------------------------------

def _resolve_workspace(mod: Path) -> tuple[Path, Path]:
    """Return (workspace, working) from either a workspace root (holding working/) or working/ itself."""
    mod = Path(mod).expanduser().resolve()
    if mod.name == "working" and mod.is_dir():
        return mod.parent, mod
    if (mod / "working").is_dir():
        return mod, mod / "working"
    raise RebuildJarError(f"{mod} is neither a mod workspace (holding working/) nor a working copy itself.")


def _cli_path(arg: str) -> Path:
    # The documented workflow types Windows paths; accept backslash separators on POSIX too.
    return Path(arg.replace("\\", "/"))


def _resolve_sources_dir(workspace: Path, working: Path, sources_arg: str) -> Path:
    given = _cli_path(sources_arg)
    if given.is_absolute():
        if given.is_dir():
            return given
        raise RebuildJarError(f"--sources {sources_arg} is not an existing directory.")
    for base in (workspace, working):
        candidate = (base / given).resolve()
        if candidate.is_dir():
            return candidate
    raise RebuildJarError(f"--sources {sources_arg} was not found under {workspace} or {working}.")


def _resolve_original_jar(workspace: Path, working: Path, jar_arg: str) -> tuple[Path, str]:
    """Resolve --jar (the ORIGINAL to rebuild and compare against).

    Tried in order: relative to the workspace root; relative to each single subfolder of
    original/ (the archive's own top folder, per the intake layout -- original/ is never
    written to, only read here); relative to working/ itself, as a last resort for a mod with
    no original/ snapshot. Returns (resolved path, posix-style path relative to whichever base
    matched) -- the second value is reused to compute the working-copy install destination.
    """
    given = _cli_path(jar_arg)
    if given.is_absolute():
        if given.is_file():
            return given, given.name
        raise RebuildJarError(f"--jar {jar_arg} is not an existing file.")
    tried: list[Path] = []
    candidate = workspace / given
    tried.append(candidate)
    if candidate.is_file():
        return candidate.resolve(), given.as_posix()
    original_dir = workspace / "original"
    if original_dir.is_dir():
        for sub in sorted(p for p in original_dir.iterdir() if p.is_dir()):
            candidate = sub / given
            tried.append(candidate)
            if candidate.is_file():
                return candidate.resolve(), given.as_posix()
    candidate = working / given
    tried.append(candidate)
    if candidate.is_file():
        return candidate.resolve(), given.as_posix()
    raise RebuildJarError("--jar " + jar_arg + " was not found; tried: " + ", ".join(str(p) for p in tried))


# --- minimal class-file parsing (members + version + referenced classes) ----------------------
# A third small constant-pool walker in this codebase (scanner._parse_class_file and jar_audit's
# parse_constant_pool are the other two), kept self-contained here because this one needs raw
# access_flags and the class-file version, which neither existing parser retains.

def _u2(data: bytes, pos: int) -> tuple[int, int]:
    return int.from_bytes(data[pos:pos + 2], "big"), pos + 2


def _u4(data: bytes, pos: int) -> tuple[int, int]:
    return int.from_bytes(data[pos:pos + 4], "big"), pos + 4


def _skip_attributes(data: bytes, pos: int, count: int) -> int:
    for _ in range(count):
        pos += 2
        length, pos = _u4(data, pos)
        pos += length
    return pos


@dataclass(frozen=True)
class _Member:
    name: str
    descriptor: str
    access_flags: int


@dataclass(frozen=True)
class _ParsedClass:
    class_name: str
    major_version: int
    minor_version: int
    methods: dict[tuple[str, str], _Member] = field(default_factory=dict)
    fields: dict[tuple[str, str], _Member] = field(default_factory=dict)
    referenced_classes: set[str] = field(default_factory=set)


def _parse_class(data: bytes) -> _ParsedClass | None:
    """Parse a .class file's version, declared members (with raw access flags) and CONSTANT_Class refs.

    Returns None for anything not a well-formed, currently-understood class file; callers must
    treat that as "unknown", never as "no differences".
    """
    if len(data) < 10 or data[:4] != b"\xca\xfe\xba\xbe":
        return None
    try:
        minor, _ = _u2(data, 4)
        major, _ = _u2(data, 6)
        pos = 8
        constant_pool_count, pos = _u2(data, pos)
        utf8: dict[int, str] = {}
        class_name_index: dict[int, int] = {}
        index = 1
        while index < constant_pool_count:
            tag = data[pos]
            pos += 1
            if tag == 1:  # Utf8
                length, pos = _u2(data, pos)
                utf8[index] = data[pos:pos + length].decode("utf-8", errors="replace")
                pos += length
            elif tag == 7:  # Class
                name_index, pos = _u2(data, pos)
                class_name_index[index] = name_index
            elif tag in (9, 10, 11, 12, 17, 18):  # Fieldref/Methodref/IfaceMethodref/NameAndType/Dynamic/InvokeDynamic
                pos += 4
            elif tag == 8:  # String
                pos += 2
            elif tag in (3, 4):  # Integer/Float
                pos += 4
            elif tag in (5, 6):  # Long/Double (two constant-pool slots)
                pos += 8
                index += 1
            elif tag == 15:  # MethodHandle
                pos += 3
            elif tag == 16:  # MethodType
                pos += 2
            elif tag in (19, 20):  # Module/Package
                pos += 2
            else:
                return None
            index += 1
        referenced_classes = {utf8[i] for i in class_name_index.values() if i in utf8}
        pos += 2  # class access_flags
        this_index, pos = _u2(data, pos)
        this_class = utf8.get(class_name_index.get(this_index, -1), "")
        pos += 2  # super_class
        interfaces_count, pos = _u2(data, pos)
        pos += 2 * interfaces_count
        fields_count, pos = _u2(data, pos)
        fields: dict[tuple[str, str], _Member] = {}
        for _ in range(fields_count):
            access_flags, pos = _u2(data, pos)
            name_index, pos = _u2(data, pos)
            descriptor_index, pos = _u2(data, pos)
            attr_count, pos = _u2(data, pos)
            pos = _skip_attributes(data, pos, attr_count)
            name, descriptor = utf8.get(name_index, ""), utf8.get(descriptor_index, "")
            fields[(name, descriptor)] = _Member(name, descriptor, access_flags)
        methods_count, pos = _u2(data, pos)
        methods: dict[tuple[str, str], _Member] = {}
        for _ in range(methods_count):
            access_flags, pos = _u2(data, pos)
            name_index, pos = _u2(data, pos)
            descriptor_index, pos = _u2(data, pos)
            attr_count, pos = _u2(data, pos)
            pos = _skip_attributes(data, pos, attr_count)
            name, descriptor = utf8.get(name_index, ""), utf8.get(descriptor_index, "")
            methods[(name, descriptor)] = _Member(name, descriptor, access_flags)
        return _ParsedClass(this_class, major, minor, methods, fields, referenced_classes)
    except (IndexError, KeyError, UnicodeDecodeError):
        return None


def _forbidden_refs(referenced: set[str]) -> list[str]:
    return sorted(
        name for name in referenced
        if name.startswith(_FORBIDDEN_REFLECT_PREFIX) or name.startswith(_FORBIDDEN_NIO_FILE_PREFIX) or name in _FORBIDDEN_IO_CLASSES
    )


def _is_synthetic_name(name: str) -> bool:
    return name.startswith("access$") or name.startswith("lambda$")


def _label(key: tuple[str, str]) -> str:
    return f"{key[0]}{key[1]}"


def _diff_members(kind: str, old: dict[tuple[str, str], _Member], new: dict[tuple[str, str], _Member]) -> tuple[list[str], list[str], list[dict], list[str]]:
    """(removed, added, modified, expected_difference_notes) for one member kind ("method"/"field")."""
    removed, added, modified, expected = [], [], [], []
    for key in sorted(set(old) - set(new)):
        member = old[key]
        if member.access_flags & _ACC_SYNTHETIC or _is_synthetic_name(member.name) or (kind == "field" and member.name in _LOMBOK_LOCK_FIELD_NAMES):
            expected.append(f"{kind} {_label(key)} removed (expected -- synthetic/compiler-generated or Lombok lock field)")
        else:
            removed.append(_label(key))
    for key in sorted(set(new) - set(old)):
        member = new[key]
        if member.access_flags & _ACC_SYNTHETIC or _is_synthetic_name(member.name) or (kind == "field" and member.name in _LOMBOK_LOCK_FIELD_NAMES):
            expected.append(f"{kind} {_label(key)} added (expected -- synthetic/compiler-generated or Lombok lock field)")
        else:
            added.append(_label(key))
    for key in sorted(set(old) & set(new)):
        old_member, new_member = old[key], new[key]
        if old_member.access_flags == new_member.access_flags:
            continue
        if kind == "method" and (old_member.access_flags ^ new_member.access_flags) == _ACC_SYNCHRONIZED:
            expected.append(f"{kind} {_label(key)}: synchronized modifier changed (expected -- lock-object refactor)")
        else:
            modified.append({"member": _label(key), "before_flags": old_member.access_flags, "after_flags": new_member.access_flags})
    return removed, added, modified, expected


def _diff_class(class_name: str, old: _ParsedClass, new: _ParsedClass) -> dict | None:
    expected: list[str] = []
    if (old.major_version, old.minor_version) != (new.major_version, new.minor_version):
        expected.append(f"class-file version {old.major_version}.{old.minor_version} -> {new.major_version}.{new.minor_version} (expected -- different compiler/JDK)")
    methods_removed, methods_added, methods_modified, method_expected = _diff_members("method", old.methods, new.methods)
    fields_removed, fields_added, fields_modified, field_expected = _diff_members("field", old.fields, new.fields)
    expected += method_expected + field_expected
    forbidden = [name.replace("/", ".") for name in _forbidden_refs(new.referenced_classes)]
    if not (methods_removed or methods_added or methods_modified or fields_removed or fields_added or fields_modified or expected or forbidden):
        return None
    return {
        "class": class_name,
        "methods_removed": methods_removed, "methods_added": methods_added, "methods_modified": methods_modified,
        "fields_removed": fields_removed, "fields_added": fields_added, "fields_modified": fields_modified,
        "expected_differences": expected,
        "forbidden_sandbox_references": sorted(forbidden),
    }


def _classes_from_jar(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {info.filename.replace("\\", "/"): archive.read(info) for info in archive.infolist() if not info.is_dir() and info.filename.lower().endswith(".class")}


def compare_jars(original_bytes: bytes, new_bytes: bytes) -> dict:
    """Compare a rebuilt jar with the original: class list added/removed, per-class member diff."""
    original_classes = _classes_from_jar(original_bytes)
    new_classes = _classes_from_jar(new_bytes)
    added_classes = sorted(set(new_classes) - set(original_classes))
    removed_classes = sorted(set(original_classes) - set(new_classes))
    common = sorted(set(original_classes) & set(new_classes))

    class_changes: list[dict] = []
    unparseable: list[str] = []
    forbidden_overall: list[dict[str, object]] = []
    for name in common:
        old_info = _parse_class(original_classes[name])
        new_info = _parse_class(new_classes[name])
        if old_info is None or new_info is None:
            unparseable.append(name)
            continue
        diff = _diff_class(name, old_info, new_info)
        if diff is not None:
            class_changes.append(diff)
            if diff["forbidden_sandbox_references"]:
                forbidden_overall.append({"class": name, "symbols": diff["forbidden_sandbox_references"]})
    for name in added_classes:
        info = _parse_class(new_classes[name])
        if info is None:
            unparseable.append(name)
            continue
        forbidden = [symbol.replace("/", ".") for symbol in _forbidden_refs(info.referenced_classes)]
        if forbidden:
            forbidden_overall.append({"class": name, "symbols": sorted(forbidden)})

    unexpected_member_loss = any(entry["methods_removed"] or entry["fields_removed"] for entry in class_changes)
    unexpected_addition = bool(added_classes) or any(entry["methods_added"] or entry["fields_added"] or entry["methods_modified"] or entry["fields_modified"] for entry in class_changes)
    return {
        "original_class_count": len(original_classes), "new_class_count": len(new_classes),
        "added_classes": added_classes, "removed_classes": removed_classes,
        "class_changes": class_changes, "unparseable_classes": sorted(unparseable),
        "forbidden_sandbox_references": forbidden_overall,
        "unexpected_member_or_class_loss": bool(removed_classes) or unexpected_member_loss,
        "has_unreviewed_additions": unexpected_addition,
    }


def _comparison_status(comparison: dict) -> str:
    if comparison["unexpected_member_or_class_loss"]:
        return "FAIL"
    if comparison["unparseable_classes"] or comparison["forbidden_sandbox_references"] or comparison["has_unreviewed_additions"]:
        return "REVIEW"
    return "PASS"


# --- jar packaging (keeps the original manifest and any non-class resources) ------------------

def _package_jar(original_jar: Path, classes_dir: Path, output_jar: Path) -> list[str]:
    """Rebuild original_jar's content, replacing/adding compiled classes; every other entry (the
    manifest included) is copied through unchanged. Mirrors build.py's package_compiled_jar."""
    class_files = sorted(path for path in classes_dir.rglob("*.class") if path.is_file())
    replacements = {path.relative_to(classes_dir).as_posix(): path for path in class_files}
    with zipfile.ZipFile(original_jar) as original:
        original_entries = {info.filename: original.read(info) for info in original.infolist() if not info.is_dir()}
    contents = {name: (replacements[name].read_bytes() if name in replacements else data) for name, data in original_entries.items()}
    contents.update({name: path.read_bytes() for name, path in replacements.items()})
    output_jar.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_jar, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(contents):
            info = zipfile.ZipInfo(name, date_time=_FIXED_DATE_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, contents[name])
    return sorted(contents)


# --- orchestration --------------------------------------------------------------------------

def rebuild_jar(
    mod: Path, sources: str, jar: str, *,
    vanilla_core: Path | None = None, jdk: Path | None = None,
    provider_roots: list[Path] | None = None, output: Path | None = None, install: bool = False,
) -> dict:
    workspace, working = _resolve_workspace(Path(mod))
    sources_dir = _resolve_sources_dir(workspace, working, sources)
    original_jar, relative_jar = _resolve_original_jar(workspace, working, jar)

    base = {
        "schema_version": SCHEMA_VERSION, "mode": "REBUILD_JAR", "mod": str(workspace),
        "sources": str(sources_dir), "original_jar": str(original_jar), "relative_jar": relative_jar,
    }

    jdk_info = find_jdk(jdk)
    if jdk_info is None:
        return {**base, "status": "UNAVAILABLE", "reason": "No JDK found (checked --jdk, In operation/_rig/jdk-*, JAVA_HOME, PATH).", "installed": False, "install_note": None}

    java_sources = sorted(path for path in sources_dir.rglob("*.java") if "disabled_files" not in path.relative_to(sources_dir).parts)
    if not java_sources:
        return {**base, "status": "FAIL", "reason": f"No .java sources found under {sources_dir}.", "installed": False, "install_note": None}

    classpath_result: ClasspathResult = assemble_classpath(working, vanilla_core, provider_roots)
    working_jar = working / relative_jar
    excluded = {str(working_jar)}
    classpath = classpath_result.classpath(exclude=excluded)

    output_dir = Path(output).expanduser().resolve() if output is not None else Path(tempfile.mkdtemp(prefix="bf-rebuild-jar-"))
    classes_dir = output_dir / "classes"
    run = run_javac(jdk_info.javac, classpath, java_sources, classes_dir)

    classpath_summary = classpath_result.summary()
    classpath_summary["excluded_from_compile"] = sorted(entry for entry in classpath_result.mod_jars if Path(entry).resolve() == working_jar.resolve())
    result = {
        **base, "output": str(output_dir),
        "jdk": {"home": str(jdk_info.home), "source": jdk_info.source},
        "classpath": classpath_summary,
        "compile": {"success": run.success, "errors": run.errors, "error_count": len(run.errors), "returncode": run.returncode},
        "installed": False, "install_note": None,
    }
    if not run.success:
        return {**result, "status": "FAIL", "new_jar": None, "comparison": None}

    new_jar_path = output_dir / original_jar.name
    _package_jar(original_jar, classes_dir, new_jar_path)
    comparison = compare_jars(original_jar.read_bytes(), new_jar_path.read_bytes())
    status = _comparison_status(comparison)
    result = {**result, "new_jar": str(new_jar_path), "comparison": comparison, "status": status}

    if install:
        if status != "PASS":
            result["install_note"] = f"refused: status is {status}, not PASS"
            return result
        target = resolve_inside(working, relative_jar)
        scratch = workspace / "scratch"
        scratch.mkdir(exist_ok=True)
        today = date.today().isoformat()
        moved_to: Path | None = None
        if target.is_file():
            moved_dir = scratch / f"moved-{today}"
            destination = moved_dir / relative_jar
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                stem, suffix, n = destination.stem, destination.suffix, 2
                while destination.exists():
                    destination = destination.parent / f"{stem}-{n}{suffix}"
                    n += 1
            shutil.move(str(target), str(destination))
            moved_to = destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(new_jar_path, target)
        log_relative_from = str(Path("working") / relative_jar).replace("/", "\\")
        with (scratch / "MOVES.log").open("a", encoding="utf-8") as handle:
            if moved_to is not None:
                log_relative_to = str(moved_to.relative_to(scratch))
                handle.write(f"{today} moved {log_relative_from} -> scratch\\{log_relative_to} (rebuild-jar: verified PASS against original, installed)\n")
            else:
                handle.write(f"{today} added {log_relative_from} (rebuild-jar: verified PASS against original, installed; no previous working jar present)\n")
        result["installed"] = True
        result["install_note"] = None
        result["moved_original_to"] = str(moved_to) if moved_to is not None else None
        result["installed_to"] = str(target)

    return result
