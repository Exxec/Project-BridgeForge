"""Minimal pure-Python Java class-file reader for the Mod Atlas (no javap needed).

Reads the constant pool, class/super/interface names, the field and method tables, field `ConstantValue` and
`Signature` attributes and, per method, a linear scan of the `Code` attribute (ROADMAP item 67a). The scan attributes an
`ldc` string constant (or a `getstatic` of a String field, or the literal prefix of a StringBuilder concatenation) to the
invoke that consumes it, and notes `new X(...)` objects handed to `addScript`/`addListener` (67e). It is a heuristic
(no stack simulation), good enough to say "this call got this string". Malformed input raises `ClassFormatError`; a
Code attribute that cannot be scanned sets `code_ok = False` so callers can fall back, as UNKNOWN, to class-level facts.
"""
from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field
from typing import NamedTuple

ACC_STATIC = 0x0008
ACC_FINAL = 0x0010
ACC_TRANSIENT = 0x0080
ACC_SYNTHETIC = 0x1000
REGISTER_METHODS = frozenset({"addListener", "addTransientListener", "addScript", "addTransientScript", "addPlugin"})
MAX_PENDING = 6
_BUILDERS = {"java/lang/StringBuilder", "java/lang/StringBuffer"}
_STRINGISH = ("Ljava/lang/String;", "Ljava/lang/Object;", "Ljava/lang/CharSequence;")
_PARAMS = re.compile(r"\((.*?)\)")


class ClassFormatError(ValueError):
    pass


class Call(NamedTuple):
    owner: str
    name: str
    args: tuple  # tuple of ("str", value, "") | ("field", owner_class, field_name) | ("prefix", value, "")


@dataclass
class ClassInfo:
    name: str = ""
    super_name: str = ""
    access: int = 0
    interfaces: list[str] = field(default_factory=list)
    strings: list[str] = field(default_factory=list)  # CONSTANT_String literals, in pool order
    called_methods: set[str] = field(default_factory=set)  # names from Methodref/InterfaceMethodref
    field_refs: set[str] = field(default_factory=set)  # names from Fieldref
    fields: list[tuple[str, str, int]] = field(default_factory=list)  # (name, descriptor, access flags)
    field_signatures: dict[str, str] = field(default_factory=dict)  # field name -> generic Signature attribute
    constants: dict[str, str] = field(default_factory=dict)  # static final String field -> ConstantValue
    methods: list[str] = field(default_factory=list)  # declared method names
    code_ok: bool = True  # False when a Code attribute could not be scanned
    calls: list[Call] = field(default_factory=list)  # watched calls with the strings attributed to them
    method_calls: list[set[str]] = field(default_factory=list)  # call names per method body
    code_methods: list[str] = field(default_factory=list)  # name of the method behind each method_calls entry
    registrations: list[tuple[str, str]] = field(default_factory=list)  # (register method, internal class name of `new X`)


# tag -> payload size for fixed-size entries (Utf8 handled separately; Long/Double take two slots)
_FIXED = {3: 4, 4: 4, 5: 8, 6: 8, 7: 2, 8: 2, 9: 4, 10: 4, 11: 4, 12: 4, 15: 3, 16: 2, 17: 4, 18: 4, 19: 2, 20: 2}


def parse_class(data: bytes, watch: frozenset[str] | None = None) -> ClassInfo:
    """Parse one class. `watch` limits which call names are recorded in `calls` (None records all)."""
    try:
        return _parse(data, watch)
    except (struct.error, IndexError, KeyError) as exc:
        raise ClassFormatError(str(exc)) from exc


class _Pool:
    def __init__(self) -> None:
        self.utf8: dict[int, str] = {}
        self.entries: dict[int, tuple[int, int, int]] = {}  # index -> (tag, a, b)

    def text(self, idx: int) -> str:
        return self.utf8.get(idx, "")

    def class_name(self, idx: int) -> str:
        entry = self.entries.get(idx)
        return self.text(entry[1]) if entry and entry[0] == 7 else ""

    def string(self, idx: int) -> str | None:
        entry = self.entries.get(idx)
        return self.text(entry[1]) if entry and entry[0] == 8 else None

    def member(self, idx: int) -> tuple[str, str, str]:
        """(owner internal name, member name, descriptor) of a Fieldref/Methodref/InterfaceMethodref."""
        entry = self.entries[idx]
        nat = self.entries[entry[2]]
        return self.class_name(entry[1]), self.text(nat[1]), self.text(nat[2])


def _read_pool(data: bytes) -> tuple[_Pool, int]:
    count = struct.unpack_from(">H", data, 8)[0]
    pos, index, pool = 10, 1, _Pool()
    while index < count:
        tag = data[pos]
        pos += 1
        if tag == 1:
            length = struct.unpack_from(">H", data, pos)[0]
            pool.utf8[index] = data[pos + 2:pos + 2 + length].decode("utf-8", errors="replace")
            pos += 2 + length
        elif tag in _FIXED:
            a = b = 0
            if tag in (7, 8, 16, 19, 20):
                a = struct.unpack_from(">H", data, pos)[0]
            elif tag in (9, 10, 11, 12):
                a, b = struct.unpack_from(">HH", data, pos)
            pool.entries[index] = (tag, a, b)
            pos += _FIXED[tag]
            if tag in (5, 6):
                index += 1
        else:
            raise ClassFormatError(f"bad constant tag {tag}")
        index += 1
    return pool, pos


def _parse(data: bytes, watch: frozenset[str] | None) -> ClassInfo:
    if data[:4] != b"\xca\xfe\xba\xbe":
        raise ClassFormatError("not a class file")
    pool, pos = _read_pool(data)
    info = ClassInfo()
    for tag, a, b in pool.entries.values():
        if tag == 8:
            info.strings.append(pool.text(a))
        elif tag in (10, 11):
            info.called_methods.add(pool.text(pool.entries[b][1]) if b in pool.entries else "")
        elif tag == 9:
            info.field_refs.add(pool.text(pool.entries[b][1]) if b in pool.entries else "")
    info.access = struct.unpack_from(">H", data, pos)[0]
    this_idx, super_idx, iface_count = struct.unpack_from(">HHH", data, pos + 2)
    pos += 8
    info.name, info.super_name = pool.class_name(this_idx), pool.class_name(super_idx)
    for _ in range(iface_count):
        info.interfaces.append(pool.class_name(struct.unpack_from(">H", data, pos)[0]))
        pos += 2
    for table in ("fields", "methods"):
        member_count = struct.unpack_from(">H", data, pos)[0]
        pos += 2
        for _ in range(member_count):
            pos = _read_member(data, pos, pool, info, table == "fields", watch)
    return info


def _read_member(data: bytes, pos: int, pool: _Pool, info: ClassInfo, is_field: bool, watch: frozenset[str] | None) -> int:
    flags, name_idx, desc_idx, attrs = struct.unpack_from(">HHHH", data, pos)
    pos += 8
    name = pool.text(name_idx)
    for _ in range(attrs):
        attr_name, length = pool.text(struct.unpack_from(">H", data, pos)[0]), struct.unpack_from(">I", data, pos + 2)[0]
        body = pos + 6
        if is_field and attr_name == "ConstantValue" and flags & ACC_STATIC and flags & ACC_FINAL:
            value = pool.string(struct.unpack_from(">H", data, body)[0])
            if value is not None:
                info.constants[name] = value
        elif is_field and attr_name == "Signature":
            info.field_signatures[name] = pool.text(struct.unpack_from(">H", data, body)[0])
        elif not is_field and attr_name == "Code":
            _scan_method(data[body:body + length], pool, info, watch)
            if len(info.method_calls) > len(info.code_methods):
                info.code_methods.append(name)
        pos = body + length
    if is_field:
        info.fields.append((name, pool.text(desc_idx), flags))
    else:
        info.methods.append(name)
    return pos


# ---------------------------------------------------------------- bytecode scan

_STORES = {0x3a, 0x4b, 0x4c, 0x4d, 0x4e, 0x53, 0xb0, 0xb3, 0xb5}  # astore*, aastore, areturn, putstatic, putfield
_OPERAND_BYTES = {0x10: 1, 0x11: 2, 0x12: 1, 0x13: 2, 0x14: 2, 0x84: 2, 0xa9: 1, 0xbc: 1, 0xbd: 2, 0xc0: 2, 0xc1: 2,
                  0xc5: 3, 0xc8: 4, 0xc9: 4, 0xba: 4, 0xb9: 4}


def _operand_bytes(op: int) -> int:
    if op in _OPERAND_BYTES:
        return _OPERAND_BYTES[op]
    if 0x15 <= op <= 0x19 or 0x36 <= op <= 0x3a:
        return 1
    if 0x99 <= op <= 0xa8 or 0xb2 <= op <= 0xb8 or op in (0xbb, 0xc6, 0xc7):
        return 2
    if op <= 0xc3:
        return 0
    raise ClassFormatError(f"unknown opcode {op:#x}")


def _instruction_length(code: bytes, pc: int) -> int:
    op = code[pc]
    if op == 0xaa:  # tableswitch
        base = pc + 1 + (-(pc + 1)) % 4
        low, high = struct.unpack_from(">ii", code, base + 4)
        return base + 12 + 4 * (high - low + 1) - pc
    if op == 0xab:  # lookupswitch
        base = pc + 1 + (-(pc + 1)) % 4
        pairs = struct.unpack_from(">i", code, base + 4)[0]
        return base + 8 + 8 * pairs - pc
    if op == 0xc4:  # wide
        return 6 if code[pc + 1] == 0x84 else 4
    return 1 + _operand_bytes(op)


def _has_string_param(descriptor: str) -> bool:
    match = _PARAMS.match(descriptor)
    return bool(match) and any(kind in match.group(1) for kind in _STRINGISH)


def _has_params(descriptor: str) -> bool:
    return not descriptor.startswith("()")


class _MethodScan:
    """State of one linear scan: strings waiting for the call that consumes them, finished `new` objects, builder prefix."""

    def __init__(self, pool: _Pool, info: ClassInfo, watch: frozenset[str] | None) -> None:
        self.pool, self.info, self.watch = pool, info, watch
        self.pending: list[tuple] = []
        self.built: list[str] = []
        self.names: set[str] = set()
        self.builder_active, self.builder_seen, self.builder_prefix = False, False, ""

    def push(self, arg: tuple) -> None:
        self.pending.append(arg)
        del self.pending[:-MAX_PENDING]

    def invoke(self, idx: int) -> None:
        owner, name, descriptor = self.pool.member(idx)
        self.names.add(name)
        if owner in _BUILDERS:
            return self._builder(name, descriptor)
        if name == "<init>":
            if not owner.startswith("java/"):
                self.built.append(owner)
        elif name in REGISTER_METHODS and self.built:
            self.info.registrations.append((name, self.built[-1]))
            self.built.clear()
        else:
            self.built.clear()
        if not _has_params(descriptor):
            return  # a getter nested inside the arguments of an outer call: keep the strings waiting
        args = tuple(self.pending) if _has_string_param(descriptor) else ()
        self.pending.clear()
        if self.watch is None or name in self.watch:
            self.info.calls.append(Call(owner, name, args))

    def _builder(self, name: str, descriptor: str) -> None:
        takes_text = _has_string_param(descriptor)
        literal = self.pending.pop()[1] if takes_text and self.pending and self.pending[-1][0] == "str" else None
        if name == "<init>" and literal is not None:
            self.builder_prefix, self.builder_seen = literal, True
        elif name == "append" and self.builder_active and not self.builder_seen:
            self.builder_prefix, self.builder_seen = literal or "", True
        elif name == "toString" and self.builder_prefix:
            self.push(("prefix", self.builder_prefix, ""))
            self.builder_active, self.builder_prefix = False, ""

    def new_object(self, idx: int) -> None:
        if self.pool.class_name(idx) in _BUILDERS:
            self.builder_active, self.builder_seen, self.builder_prefix = True, False, ""


def _scan_method(attr: bytes, pool: _Pool, info: ClassInfo, watch: frozenset[str] | None) -> None:
    try:
        length = struct.unpack_from(">I", attr, 4)[0]
        code = attr[8:8 + length]
        scan = _MethodScan(pool, info, watch)
        pc = 0
        while pc < len(code):
            op = code[pc]
            if op in (0x12, 0x13):
                value = pool.string(code[pc + 1] if op == 0x12 else struct.unpack_from(">H", code, pc + 1)[0])
                if value is not None:
                    scan.push(("str", value, ""))
            elif op == 0xb2:
                owner, fname, desc = pool.member(struct.unpack_from(">H", code, pc + 1)[0])
                if desc == "Ljava/lang/String;":
                    scan.push(("field", owner, fname))
            elif op == 0xbb:
                scan.new_object(struct.unpack_from(">H", code, pc + 1)[0])
            elif op in (0xb6, 0xb7, 0xb8, 0xb9):
                scan.invoke(struct.unpack_from(">H", code, pc + 1)[0])
            elif op in _STORES:
                scan.pending.clear()
            pc += _instruction_length(code, pc)
        info.method_calls.append(scan.names)
    except (ClassFormatError, struct.error, IndexError, KeyError):
        info.code_ok = False
