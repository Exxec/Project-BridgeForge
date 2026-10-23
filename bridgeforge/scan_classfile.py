"""Class-file parsing and jar class iteration used by the jar-level scan checks."""
from __future__ import annotations

import zipfile
from pathlib import Path, PurePosixPath
from .scan_common import MAX_JAR_ENTRIES
from .scan_json import _load_lenient_json_file


def mod_jar_class_names(root: Path) -> set[str]:
    """Every fully-qualified class name compiled into one of this mod's own jars.

    Factored out of `_scan_loose_script_janino_risk` (ROADMAP P14 items 14/25/26) so "is this loose
    script actually jar-shadowed" has exactly one real implementation - real jar-class-file parsing
    via `_iter_jar_class_files`/`_parse_class_file` - reachable outside a full scan. E12 found a
    `Path.is_file()` path-existence check trusted as proof of jar-shadowing at least once (Rebal's
    50 `.java` files, none of which were actually jar-shadowed); this is the function any future
    "is this shadowed" claim should call instead of reimplementing the check.
    """
    jar_classes: set[str] = set()
    for _jar, _member, data in _iter_jar_class_files(root):
        info = _parse_class_file(data)
        if info is not None and info.this_class:
            jar_classes.add(info.this_class.replace("/", "."))
    return jar_classes


def loose_script_jar_shadowed_class(root: Path, source: Path) -> str | None:
    """The fully-qualified class name `source` shares with one of this mod's own jars, or None.

    `source` may be absolute or relative to `root`. Only the mod's OWN jars are checked (matching
    `loose-script-shadowed-by-jar`'s existing scope) - a dependency's jar shadowing a mod's own
    override is the separate, still-open item 12/25 gap, not this one.
    """
    try:
        relative = source.relative_to(root) if source.is_absolute() else source
    except ValueError:
        return None
    class_name = ".".join(relative.with_suffix("").parts)
    jar_classes = mod_jar_class_names(root)
    return class_name if class_name in jar_classes else None


def _iter_class_files_in(target: Path):
    """Yield (jar_path, member_name, class_bytes) for readable .class members under `target`.

    `target` may be a single jar file, or a directory searched recursively for jars (e.g. a
    starsector-core install, a rig's mods folder, or a dependency mod's own directory). Unlike
    `_iter_jar_class_files`, this does not consult a mod's own `mod_info.json` "jars" list - the
    caller names the jar set explicitly, which is the whole point of `verify_shadow` (ROADMAP P14
    item 26): a direct answer for an arbitrary jar-or-core-dir, not just "this mod's loaded jars."
    """
    jars = [target] if target.is_file() else sorted(target.rglob("*.jar"))
    for jar in jars:
        try:
            with zipfile.ZipFile(jar) as archive:
                entries = archive.infolist()
                if len(entries) > MAX_JAR_ENTRIES:
                    continue
                for item in entries:
                    if not item.filename.endswith(".class"):
                        continue
                    member = PurePosixPath(item.filename.replace("\\", "/"))
                    if member.is_absolute() or ".." in member.parts:
                        continue
                    try:
                        with archive.open(item) as class_file:
                            data = class_file.read()
                    except (OSError, zipfile.BadZipFile, KeyError):
                        continue
                    yield jar, item.filename.replace("\\", "/"), data
        except (OSError, zipfile.BadZipFile):
            continue


def _dependency_jar_class_names(root: Path, provider_roots: list[Path] | None = None) -> dict[str, str]:
    """{fully-qualified class name: provider mod name} for every class in a declared dependency's
    own jars (ROADMAP P14 item 12). Only declared dependencies are checked - an undeclared mod
    happening to share a class name is a coincidence, not a real shadowing risk this check should
    claim (and `undeclared-library-dependency`/`source-import-unresolved` are its own checks).

    Deliberately requires an EXPLICIT `provider_roots` - no default fallback to
    `java_toolchain.DEFAULT_PROVIDER_ROOTS` here. That default (this repo's own `In operation`
    folder) is fine for an explicit, single-purpose command like `compile-check`/`fix`, but this
    function is called from `_scan_loose_script_janino_risk`, which runs on *every* `scan_mod` call
    unconditionally - a silent fallback here made every scan of a mod with declared dependencies
    walk this repo's real, ~325-mod `In operation` folder regardless of what was actually being
    scanned, turning a 75-second test suite into an 8-minute one before this was caught. Pass
    `scan --providers`/`corpus_recheck`'s own default, etc. explicitly to opt in, same as
    `compile-check` already requires.
    """
    from .substitutes import provider_index

    if not provider_roots:
        return {}
    from bridgeforge.bytecode.java_toolchain import declared_dependencies

    deps = declared_dependencies(root)
    if not deps:
        return {}
    roots = [Path(entry) for entry in provider_roots]
    providers = provider_index(roots, exclude=root)
    by_id = {provider.mod_id: provider for provider in providers}
    classes: dict[str, str] = {}
    for dep_id in deps:
        provider = by_id.get(dep_id)
        if provider is None:
            continue
        for _jar, _member, data in _iter_class_files_in(Path(provider.path)):
            info = _parse_class_file(data)
            if info is not None and info.this_class:
                classes.setdefault(info.this_class.replace("/", "."), provider.name)
    return classes


def _class_pool_u2(data: bytes, pos: int) -> tuple[int, int]:
    return int.from_bytes(data[pos:pos + 2], "big"), pos + 2


def _class_pool_u4(data: bytes, pos: int) -> tuple[int, int]:
    return int.from_bytes(data[pos:pos + 4], "big"), pos + 4


def _skip_attributes(data: bytes, pos: int, count: int) -> int:
    for _ in range(count):
        pos += 2  # attribute_name_index
        length, pos = _class_pool_u4(data, pos)
        pos += length
    return pos


class _ClassFileInfo:
    """Parsed facts about one .class file, resolved from its constant pool."""

    __slots__ = ("this_class", "referenced_classes", "methods", "super_class", "interfaces", "fields", "string_constants", "utf8_values", "transient_fields")

    def __init__(
        self,
        this_class: str,
        referenced_classes: set[str],
        methods: list[tuple[str, str, bool]],
        super_class: str = "",
        interfaces: list[str] | None = None,
        fields: list[tuple[str, str, bool, bool]] | None = None,
        string_constants: set[str] | None = None,
        utf8_values: frozenset[str] = frozenset(),
    ) -> None:
        self.this_class = this_class
        self.referenced_classes = referenced_classes
        self.methods = methods
        self.super_class = super_class
        self.interfaces = interfaces or []
        # (name, descriptor, is_static, is_final) per declared field
        self.fields = fields or []
        self.transient_fields: frozenset[str] = frozenset()
        # Java string literals (CONSTANT_String), and every Utf8 entry (member names referenced, etc.)
        self.string_constants = string_constants or set()
        self.utf8_values = utf8_values


def _parse_class_file(data: bytes) -> _ClassFileInfo | None:
    """Parse a .class file's constant pool and method table.

    Returns the internal (slash-separated) class names referenced via CONSTANT_Class
    entries and (name, descriptor, is_public) for each declared method. This is a
    proper constant-pool walk (not a substring search) so that, for example,
    "java/io/FileSystemNotFoundException" is never confused with "java/io/File".
    Returns None for anything that is not a well-formed, currently-understood class
    file; callers must treat that as "unknown", not "no forbidden references".
    """
    if len(data) < 10 or data[:4] != b"\xca\xfe\xba\xbe":
        return None
    try:
        pos = 8  # magic(4) + minor_version(2) + major_version(2)
        constant_pool_count, pos = _class_pool_u2(data, pos)
        utf8: dict[int, str] = {}
        class_name_index: dict[int, int] = {}
        string_indexes: list[int] = []
        index = 1
        while index < constant_pool_count:
            tag = data[pos]
            pos += 1
            if tag == 1:  # Utf8
                length, pos = _class_pool_u2(data, pos)
                raw = data[pos:pos + length]
                pos += length
                utf8[index] = raw.decode("utf-8", errors="replace")
            elif tag == 7:  # Class
                name_index, pos = _class_pool_u2(data, pos)
                class_name_index[index] = name_index
            elif tag in (9, 10, 11, 12, 17, 18):  # Fieldref/Methodref/IfaceMethodref/NameAndType/Dynamic/InvokeDynamic
                pos += 4
            elif tag == 8:  # String
                string_index, pos = _class_pool_u2(data, pos)
                string_indexes.append(string_index)
            elif tag in (3, 4):  # Integer/Float
                pos += 4
            elif tag in (5, 6):  # Long/Double (occupies two constant-pool entries)
                pos += 8
                index += 1
            elif tag == 15:  # MethodHandle
                pos += 3
            elif tag == 16:  # MethodType
                pos += 2
            elif tag in (19, 20):  # Module/Package
                pos += 2
            else:
                return None  # unrecognized constant-pool tag; do not guess
            index += 1
        referenced_classes = {utf8[name_index] for name_index in class_name_index.values() if name_index in utf8}
        pos += 2  # access_flags
        this_class_index, pos = _class_pool_u2(data, pos)
        this_class = utf8.get(class_name_index.get(this_class_index, -1), "")
        super_index, pos = _class_pool_u2(data, pos)
        super_class = utf8.get(class_name_index.get(super_index, -1), "")
        interfaces_count, pos = _class_pool_u2(data, pos)
        interfaces: list[str] = []
        for _ in range(interfaces_count):
            interface_index, pos = _class_pool_u2(data, pos)
            interfaces.append(utf8.get(class_name_index.get(interface_index, -1), ""))
        fields_count, pos = _class_pool_u2(data, pos)
        fields: list[tuple[str, str, bool, bool]] = []
        transient: set[str] = set()
        for _ in range(fields_count):
            field_flags, pos = _class_pool_u2(data, pos)
            field_name_index, pos = _class_pool_u2(data, pos)
            field_descriptor_index, pos = _class_pool_u2(data, pos)
            attr_count, pos = _class_pool_u2(data, pos)
            pos = _skip_attributes(data, pos, attr_count)
            fields.append((utf8.get(field_name_index, ""), utf8.get(field_descriptor_index, ""), bool(field_flags & 0x0008), bool(field_flags & 0x0010)))
            if field_flags & 0x0080:  # ACC_TRANSIENT
                transient.add(utf8.get(field_name_index, ""))
        methods_count, pos = _class_pool_u2(data, pos)
        methods: list[tuple[str, str, bool]] = []
        for _ in range(methods_count):
            access_flags, pos = _class_pool_u2(data, pos)
            name_index, pos = _class_pool_u2(data, pos)
            descriptor_index, pos = _class_pool_u2(data, pos)
            attr_count, pos = _class_pool_u2(data, pos)
            pos = _skip_attributes(data, pos, attr_count)
            methods.append((utf8.get(name_index, ""), utf8.get(descriptor_index, ""), bool(access_flags & 0x0001)))
        string_constants = {utf8[string_index] for string_index in string_indexes if string_index in utf8}
        parsed = _ClassFileInfo(this_class, referenced_classes, methods, super_class, interfaces, fields, string_constants, frozenset(utf8.values()))
        parsed.transient_fields = frozenset(transient)
        return parsed
    except (IndexError, KeyError, UnicodeDecodeError):
        return None


# Bytes each opcode's operands take (JVM spec, chapter 6); -1: variable (tableswitch/lookupswitch/wide).
_OPERAND_BYTES = [0] * 256


for _op in (0x10, 0x12, 0x15, 0x16, 0x17, 0x18, 0x19, 0x36, 0x37, 0x38, 0x39, 0x3A, 0xA9, 0xBC):
    _OPERAND_BYTES[_op] = 1


for _op in (0x11, 0x13, 0x14, 0x84, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6, 0xB7, 0xB8, 0xBB, 0xBD, 0xC0, 0xC1, 0xC6, 0xC7) + tuple(range(0x99, 0xA9)):
    _OPERAND_BYTES[_op] = 2


for _op in (0xC5,):
    _OPERAND_BYTES[_op] = 3


for _op in (0xB9, 0xBA, 0xC8, 0xC9):
    _OPERAND_BYTES[_op] = 4


for _op in (0xAA, 0xAB, 0xC4):
    _OPERAND_BYTES[_op] = -1


def _instance_fields_written_outside_constructors(data: bytes) -> set[tuple[str, str]] | None:
    """(owner class, field name) for every putfield in a method other than <init>.

    A hull mod field written only in its constructor is set once per object (configuration such as
    RogueSynth's flavourText/rarity), not per-ship state; only writes elsewhere can leak between ships.
    None when the class file cannot be walked (the caller then keeps the declaration-only rule).
    """
    import struct

    try:
        pos = 8
        count = struct.unpack_from(">H", data, pos)[0]
        pos += 2
        utf8, classes, name_types, fieldrefs = {}, {}, {}, {}
        index = 1
        while index < count:
            tag = data[pos]
            pos += 1
            if tag == 1:
                length = struct.unpack_from(">H", data, pos)[0]
                utf8[index] = data[pos + 2:pos + 2 + length].decode("utf-8", errors="replace")
                pos += 2 + length
            elif tag in (3, 4):
                pos += 4
            elif tag in (5, 6):
                pos += 8
                index += 1
            elif tag in (7, 8, 16, 19, 20):
                if tag == 7:
                    classes[index] = struct.unpack_from(">H", data, pos)[0]
                pos += 2
            elif tag in (9, 10, 11, 12, 17, 18):
                a, b = struct.unpack_from(">HH", data, pos)
                if tag == 9:
                    fieldrefs[index] = (a, b)
                elif tag == 12:
                    name_types[index] = (a, b)
                pos += 4
            elif tag == 15:
                pos += 3
            else:
                return None
            index += 1
        pos += 6  # access_flags, this_class, super_class
        pos += 2 + 2 * struct.unpack_from(">H", data, pos)[0]

        def skip_attributes(p: int) -> int:
            n = struct.unpack_from(">H", data, p)[0]
            p += 2
            for _ in range(n):
                p += 6 + struct.unpack_from(">I", data, p + 2)[0]
            return p

        n_fields = struct.unpack_from(">H", data, pos)[0]
        pos += 2
        for _ in range(n_fields):
            pos = skip_attributes(pos + 6)
        n_methods = struct.unpack_from(">H", data, pos)[0]
        pos += 2
        written: set[tuple[str, str]] = set()
        for _ in range(n_methods):
            name = utf8.get(struct.unpack_from(">H", data, pos + 2)[0], "")
            pos += 6
            n_attrs = struct.unpack_from(">H", data, pos)[0]
            pos += 2
            for _ in range(n_attrs):
                attr_name = utf8.get(struct.unpack_from(">H", data, pos)[0], "")
                attr_len = struct.unpack_from(">I", data, pos + 2)[0]
                body = pos + 6
                if attr_name == "Code" and name != "<init>":
                    code_len = struct.unpack_from(">I", data, body + 4)[0]
                    start = body + 8
                    i = 0
                    while i < code_len:
                        op = data[start + i]
                        if op == 0xB5:
                            ref = fieldrefs.get(struct.unpack_from(">H", data, start + i + 1)[0])
                            if ref and ref[1] in name_types:
                                written.add((utf8.get(classes.get(ref[0], -1), ""), utf8.get(name_types[ref[1]][0], "")))
                        size = _OPERAND_BYTES[op]
                        if size >= 0:
                            i += 1 + size
                        elif op == 0xC4:  # wide
                            i += 6 if data[start + i + 1] == 0x84 else 4
                        else:
                            pad = (4 - ((i + 1) % 4)) % 4
                            j = i + 1 + pad
                            if op == 0xAA:
                                low, high = struct.unpack_from(">ii", data, start + j + 4)
                                i = j + 12 + 4 * (high - low + 1)
                            else:
                                pairs = struct.unpack_from(">i", data, start + j + 4)[0]
                                i = j + 8 + 8 * pairs
                pos = body + attr_len
        return written
    except (IndexError, struct.error):
        return None


NON_MOD_JAR_DIRS = {"build", "out", "tmp", "target"}


def _loaded_mod_jars(root: Path) -> list[Path]:
    """Jars Starsector actually loads: mod_info.json's "jars" list, else every jar outside build-output dirs.

    Bytecode checks must not read compile-classpath caches (e.g. build/cp/ holding vanilla's own jar), unloaded
    legacy jars, or backups; those produced thousands of false findings on real revival working copies.
    """
    mod_info = _load_lenient_json_file(root / "mod_info.json")
    declared = mod_info.get("jars") if isinstance(mod_info, dict) else None
    if isinstance(declared, list):
        jars = [root / entry for entry in declared if isinstance(entry, str) and (root / entry).is_file()]
        if jars:
            return sorted(jars)
    return sorted(
        jar for jar in root.rglob("*.jar")
        if not NON_MOD_JAR_DIRS.intersection(part.lower() for part in jar.relative_to(root).parts[:-1])
    )


def _iter_jar_class_files(root: Path):
    """Yield (jar_path, member_name, class_bytes) for readable .class members of the mod's loaded jars."""
    yield from iter_class_files_in_jars(_loaded_mod_jars(root))


def iter_class_files_in_jars(jars, unreadable: list[str] | None = None, max_entries: int = MAX_JAR_ENTRIES):
    """Yield (jar_path, member_name, class_bytes) for readable .class members of the given jars.

    The one jar-walking loop behind `mod_jar_class_names` and `verify-shadow` (ROADMAP P14 item 26).
    A jar that cannot be opened or exceeds MAX_JAR_ENTRIES is skipped; pass `unreadable` to learn
    which, so a "not shadowed" answer can say what it did not look inside.
    """
    for jar in jars:
        try:
            with zipfile.ZipFile(jar) as archive:
                entries = archive.infolist()
                if len(entries) > max_entries:
                    if unreadable is not None:
                        unreadable.append(f"{jar}: more than {max_entries} entries")
                    continue
                for item in entries:
                    if not item.filename.endswith(".class"):
                        continue
                    member = PurePosixPath(item.filename.replace("\\", "/"))
                    if member.is_absolute() or ".." in member.parts:
                        continue
                    try:
                        with archive.open(item) as class_file:
                            data = class_file.read()
                    except (OSError, zipfile.BadZipFile, KeyError):
                        continue
                    yield jar, item.filename.replace("\\", "/"), data
        except (OSError, zipfile.BadZipFile) as exc:
            if unreadable is not None:
                unreadable.append(f"{jar}: {exc}")
            continue
