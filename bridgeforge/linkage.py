"""Bytecode linkage against RC8: does each call a mod's jar makes into a game class still resolve? (2026-09-30)

Too Much Information's jar calls `TooltipMakerAPI.beginTable(...)V`; in RC8 it returns `UIPanelAPI`, so the shipped
class throws NoSuchMethodError the first time the tooltip draws, and no check saw it (found through `jar-packets`).
This is the method in the 2026-09-08 linkage measurement, as a check:

- Read every Methodref/InterfaceMethodref/Fieldref in the mod's classes (the constant pool; no javap needed).
- Keep references whose owner is a class of the game's core jars (`com/fs/...` and the other jars in starsector-core),
  and that the mod's own jars do not define (mods squat in game packages).
- Resolve name + descriptor through the owner's superclasses and interfaces within the core. A hierarchy that leaves
  the core (java.lang.Object and other JDK types) is not judged: unknown, never reported.
- Report what does not resolve, with a same-name member of another descriptor as the likely successor. A change of
  return type alone is fixed by recompiling the class against RC8 (`patch-jar-class`).
"""
from __future__ import annotations

import struct
import zipfile
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

CORE_JARS = ("starfarer.api.jar", "starfarer_obf.jar", "fs.common_obf.jar", "fs.sound_obf.jar", "json.jar", "log4j-1.2.9.jar",
             "lwjgl.jar", "lwjgl_util.jar", "xstream-1.4.10.jar", "janino.jar", "commons-compiler.jar", "commons-compiler-jdk.jar",
             "jinput.jar", "jogg-0.0.7.jar", "jorbis-0.0.15.jar", "txw2-2.3.0.jar", "webp-imageio-0.1.6.jar")


OBJECT_METHODS = (("<init>", "()V"), ("getClass", "()Ljava/lang/Class;"), ("hashCode", "()I"), ("equals", "(Ljava/lang/Object;)Z"),
                  ("clone", "()Ljava/lang/Object;"), ("toString", "()Ljava/lang/String;"), ("notify", "()V"), ("notifyAll", "()V"),
                  ("wait", "()V"), ("wait", "(J)V"), ("wait", "(JI)V"), ("finalize", "()V"))


@dataclass
class ClassInfo:
    name: str
    super_name: str | None
    interfaces: list[str]
    methods: set[tuple[str, str]] = field(default_factory=set)
    fields: set[tuple[str, str]] = field(default_factory=set)
    refs: set[tuple[str, str, str, str]] = field(default_factory=set)  # (kind, owner, name, descriptor)


def parse_class(data: bytes) -> ClassInfo | None:
    if len(data) < 10 or data[:4] != b"\xca\xfe\xba\xbe":
        return None
    try:
        count = struct.unpack_from(">H", data, 8)[0]
        pos, index = 10, 1
        utf8: dict[int, str] = {}
        classes: dict[int, int] = {}
        nat: dict[int, tuple[int, int]] = {}
        refs: list[tuple[int, int, int]] = []
        while index < count:
            tag = data[pos]
            pos += 1
            if tag == 1:
                length = struct.unpack_from(">H", data, pos)[0]
                utf8[index] = data[pos + 2:pos + 2 + length].decode("utf-8", errors="replace")
                pos += 2 + length
            elif tag == 7:
                classes[index] = struct.unpack_from(">H", data, pos)[0]
                pos += 2
            elif tag in (9, 10, 11):
                owner, name_type = struct.unpack_from(">HH", data, pos)
                refs.append((tag, owner, name_type))
                pos += 4
            elif tag == 12:
                nat[index] = struct.unpack_from(">HH", data, pos)
                pos += 4
            elif tag in (3, 4, 17, 18):
                pos += 4
            elif tag in (5, 6):
                pos += 8
                index += 1
            elif tag in (8, 16, 19, 20):
                pos += 2
            elif tag == 15:
                pos += 3
            else:
                return None
            index += 1

        def class_name(i: int) -> str:
            return utf8.get(classes.get(i, -1), "")

        pos += 2
        this_index, super_index, interfaces_count = struct.unpack_from(">HHH", data, pos)
        pos += 6
        interfaces = [class_name(struct.unpack_from(">H", data, pos + 2 * k)[0]) for k in range(interfaces_count)]
        pos += 2 * interfaces_count
        info = ClassInfo(class_name(this_index), class_name(super_index) or None, interfaces)
        for members in (info.fields, info.methods):
            member_count = struct.unpack_from(">H", data, pos)[0]
            pos += 2
            for _ in range(member_count):
                _flags, name_index, descriptor_index, attr_count = struct.unpack_from(">HHHH", data, pos)
                pos += 8
                for _ in range(attr_count):
                    pos += 6 + struct.unpack_from(">I", data, pos + 2)[0]
                members.add((utf8.get(name_index, ""), utf8.get(descriptor_index, "")))
        for tag, owner, name_type in refs:
            name_index, descriptor_index = nat.get(name_type, (-1, -1))
            owner_name = class_name(owner)
            if owner_name.startswith("["):
                continue  # array clone() and the like
            info.refs.add(("field" if tag == 9 else "method", owner_name, utf8.get(name_index, ""), utf8.get(descriptor_index, "")))
        return info
    except (struct.error, IndexError):
        return None


def jar_classes(jar: Path) -> dict[str, ClassInfo]:
    found: dict[str, ClassInfo] = {}
    try:
        with zipfile.ZipFile(jar) as archive:
            for name in archive.namelist():
                if name.endswith(".class"):
                    info = parse_class(archive.read(name))
                    if info and info.name:
                        found[info.name] = info
    except (OSError, zipfile.BadZipFile):
        pass
    return found


def _class_names(jar: Path) -> frozenset[str]:
    # A revive scans each mod several times and each scan reads every other rig mod's jars: cache by file state
    # (the first queue run spent minutes on one mod, 2026-09-30).
    try:
        stat = jar.stat()
    except OSError:
        return frozenset()
    return _class_names_cached(str(jar.resolve()), stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=512)
def _class_names_cached(path: str, _mtime: int, _size: int) -> frozenset[str]:
    # Entry names are enough for a provider (a class sits at its package path); no class file is parsed.
    try:
        with zipfile.ZipFile(path) as archive:
            return frozenset(name[:-6] for name in archive.namelist() if name.endswith(".class"))
    except (OSError, zipfile.BadZipFile):
        return frozenset()


@lru_cache(maxsize=4)
def core_index(vanilla_core: str) -> dict[str, ClassInfo]:
    root = Path(vanilla_core)
    index: dict[str, ClassInfo] = {}
    for name in CORE_JARS:
        if (root / name).is_file():
            for class_name, info in jar_classes(root / name).items():
                info.refs = set()  # only members matter for the core
                index.setdefault(class_name, info)
    if index:
        # Every hierarchy ends here (an interface's class file names Object as its superclass); without it no call
        # on a game interface could be judged.
        index["java/lang/Object"] = ClassInfo("java/lang/Object", None, [], methods=set(OBJECT_METHODS))
    return index


def _resolve(core: dict[str, ClassInfo], owner: str, kind: str, name: str, descriptor: str) -> bool | None:
    """True if found, False if the whole hierarchy is in the core and it is not there, None if the hierarchy leaves it."""
    seen, stack, left_core = set(), [owner], False
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        info = core.get(current)
        if info is None:
            left_core = True
            continue
        if (name, descriptor) in (info.fields if kind == "field" else info.methods):
            return True
        stack += [c for c in (info.super_name, *info.interfaces) if c]
    return None if left_core else False


def _same_name(core: dict[str, ClassInfo], owner: str, kind: str, name: str) -> list[str]:
    seen, stack, found = set(), [owner], []
    while stack:
        current = stack.pop()
        if current in seen or current not in core:
            continue
        seen.add(current)
        info = core[current]
        found += sorted(d for n, d in (info.fields if kind == "field" else info.methods) if n == name)
        stack += [c for c in (info.super_name, *info.interfaces) if c]
    return found


def unresolved_references(mod_jars: list[Path], vanilla_core: Path, extra_jars: list[Path] | None = None) -> dict[str, list[dict]]:
    """{jar-relative class entry: [unresolved reference, ...]} for the mod's jars against the core."""
    core = core_index(str(Path(vanilla_core).resolve()))
    if not core:
        return {}
    mod_classes: dict[str, tuple[Path, ClassInfo]] = {}
    for jar in mod_jars:
        for class_name, info in jar_classes(jar).items():
            mod_classes.setdefault(class_name, (jar, info))
    provided = set(mod_classes)
    for jar in extra_jars or []:
        provided |= _class_names(jar)
    result: dict[str, list[dict]] = {}
    for class_name, (jar, info) in sorted(mod_classes.items()):
        problems = []
        for kind, owner, name, descriptor in sorted(info.refs):
            if owner in provided or not (owner in core or owner.startswith("com/fs/")):
                continue
            if owner not in core:
                problems.append({"kind": "class", "owner": owner, "name": name, "descriptor": descriptor, "candidates": []})
                continue
            if _resolve(core, owner, kind, name, descriptor) is False:
                candidates = _same_name(core, owner, kind, name)
                returns_only = kind == "method" and any(c.split(")")[0] == descriptor.split(")")[0] for c in candidates)
                problems.append({"kind": kind, "owner": owner, "name": name, "descriptor": descriptor, "candidates": candidates[:4],
                                 "return_type_only": returns_only})
        if problems:
            result[f"{jar.name}!{class_name}.class"] = problems
    return result
