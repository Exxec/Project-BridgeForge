"""Minimal pure-Python Java class-file reader for the Mod Atlas (no javap needed).

Reads the constant pool, the class/super/interface names and the field and method tables. Attributes (code, annotations)
are skipped. Only what the Atlas needs is kept: string literals, called method names, field-ref names, field
descriptors and method names. Malformed input raises `ClassFormatError`.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

ACC_STATIC = 0x0008
ACC_TRANSIENT = 0x0080


class ClassFormatError(ValueError):
    pass


@dataclass
class ClassInfo:
    name: str = ""
    super_name: str = ""
    interfaces: list[str] = field(default_factory=list)
    strings: list[str] = field(default_factory=list)  # CONSTANT_String literals, in pool order
    called_methods: set[str] = field(default_factory=set)  # names from Methodref/InterfaceMethodref
    field_refs: set[str] = field(default_factory=set)  # names from Fieldref
    fields: list[tuple[str, str, int]] = field(default_factory=list)  # (name, descriptor, access flags)
    methods: list[str] = field(default_factory=list)  # declared method names


# tag -> payload size for fixed-size entries (Utf8 handled separately; Long/Double take two slots)
_FIXED = {3: 4, 4: 4, 5: 8, 6: 8, 7: 2, 8: 2, 9: 4, 10: 4, 11: 4, 12: 4, 15: 3, 16: 2, 17: 4, 18: 4, 19: 2, 20: 2}


def parse_class(data: bytes) -> ClassInfo:
    try:
        return _parse(data)
    except (struct.error, IndexError, KeyError) as exc:
        raise ClassFormatError(str(exc)) from exc


def _parse(data: bytes) -> ClassInfo:
    if data[:4] != b"\xca\xfe\xba\xbe":
        raise ClassFormatError("not a class file")
    count = struct.unpack_from(">H", data, 8)[0]
    pos = 10
    utf8: dict[int, str] = {}
    entries: dict[int, tuple[int, int, int]] = {}  # index -> (tag, a, b)
    index = 1
    while index < count:
        tag = data[pos]
        pos += 1
        if tag == 1:
            length = struct.unpack_from(">H", data, pos)[0]
            utf8[index] = data[pos + 2:pos + 2 + length].decode("utf-8", errors="replace")
            pos += 2 + length
        elif tag in _FIXED:
            size = _FIXED[tag]
            a = b = 0
            if tag in (7, 8, 16, 19, 20):
                a = struct.unpack_from(">H", data, pos)[0]
            elif tag in (9, 10, 11, 12):
                a, b = struct.unpack_from(">HH", data, pos)
            entries[index] = (tag, a, b)
            pos += size
            if tag in (5, 6):
                index += 1
        else:
            raise ClassFormatError(f"bad constant tag {tag}")
        index += 1
    info = ClassInfo()
    for tag, a, b in entries.values():
        if tag == 8:
            info.strings.append(utf8.get(a, ""))
        elif tag in (10, 11):
            info.called_methods.add(utf8.get(entries[b][1], "") if b in entries else "")
        elif tag == 9:
            info.field_refs.add(utf8.get(entries[b][1], "") if b in entries else "")

    def class_name(idx: int) -> str:
        entry = entries.get(idx)
        return utf8.get(entry[1], "") if entry and entry[0] == 7 else ""

    pos += 2  # access flags
    this_idx, super_idx, iface_count = struct.unpack_from(">HHH", data, pos)
    pos += 6
    info.name, info.super_name = class_name(this_idx), class_name(super_idx)
    for _ in range(iface_count):
        info.interfaces.append(class_name(struct.unpack_from(">H", data, pos)[0]))
        pos += 2
    for table in ("fields", "methods"):
        member_count = struct.unpack_from(">H", data, pos)[0]
        pos += 2
        for _ in range(member_count):
            flags, name_idx, desc_idx, attrs = struct.unpack_from(">HHHH", data, pos)
            pos += 8
            for _ in range(attrs):
                pos += 6 + struct.unpack_from(">I", data, pos + 2)[0]
            if table == "fields":
                info.fields.append((utf8.get(name_idx, ""), utf8.get(desc_idx, ""), flags))
            else:
                info.methods.append(utf8.get(name_idx, ""))
    return info
