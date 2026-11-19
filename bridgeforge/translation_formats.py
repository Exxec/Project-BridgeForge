"""Finding and rewriting translatable text in each format a mod ships (split from translation.py, ROADMAP-3 96.5 A6).

CSV cells, JSON-like strings and keys, loose Java string literals, plain text lines and class-file string constants:
`_units` lists a file's units with exact spans, and the `_rewrite_*`/encode helpers put a translation back. translation.py
holds the export, prefill, apply and check workflows over them.
"""
from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from bridgeforge.scan.scanner import _blank_java_comments
from bridgeforge.zipsafe import MAX_CLASS_BYTES, read_limited

CJK = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
JSONLIKE_SUFFIXES = {".json", ".faction", ".ship", ".variant", ".wpn", ".proj", ".skin", ".system"}
MAX_TRANSLATION_BYTES = 64 * 1024 * 1024


class TranslationError(Exception):
    pass


def _has_cjk(text: str) -> bool:
    return bool(CJK.search(text))


# ---- CSV -----------------------------------------------------------------------------------------

def _translation_csv_text(raw: bytes) -> tuple[str, str, bool]:
    """Retain Project Go's established strict UTF-8/GB18030 CSV compatibility."""
    bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        return raw.decode("utf-8-sig"), "utf-8", bom
    except UnicodeDecodeError:
        if bom:
            raise
        return raw.decode("gb18030"), "gb18030", False


def _csv_cells(text: str):
    """Yield (row, col, start, end, value, quoted) for every cell, with raw spans."""
    i, n, row, col = 0, len(text), 0, 0
    while True:
        start = i
        quoted = i < n and text[i] == '"'
        if quoted:
            i += 1
            buf: list[str] = []
            while i < n:
                if text[i] == '"':
                    if i + 1 < n and text[i + 1] == '"':
                        buf.append('"')
                        i += 2
                        continue
                    i += 1
                    break
                buf.append(text[i])
                i += 1
            while i < n and text[i] not in ",\r\n":
                buf.append(text[i])
                i += 1
            value = "".join(buf)
        else:
            j = i
            while j < n and text[j] not in ",\r\n":
                j += 1
            value = text[i:j]
            i = j
        yield row, col, start, i, value, quoted
        if i >= n:
            return
        if text[i] == ",":
            col += 1
            i += 1
        else:
            i += 2 if text[i:i + 2] == "\r\n" else 1
            row += 1
            col = 0
            if i >= n:
                return


def _csv_row_keys(cells: list[tuple]) -> tuple[list[str], dict[int, str]]:
    header = [value.strip() for row, col, s, e, value, q in cells if row == 0]
    id_col = header.index("id") if "id" in header else 0
    type_col = header.index("type") if "type" in header else None
    by_row: dict[int, dict[int, str]] = defaultdict(dict)
    for row, col, s, e, value, q in cells:
        by_row[row][col] = value
    keys: dict[int, str] = {}
    seen: Counter = Counter()
    for row in sorted(by_row):
        if row == 0:
            continue
        base = by_row[row].get(id_col, "").strip() or f"row{row}"
        if type_col is not None and by_row[row].get(type_col, "").strip():
            base += "/" + by_row[row][type_col].strip()
        seen[base] += 1
        keys[row] = base if seen[base] == 1 else f"{base}~{seen[base]}"
    return header, keys


def _csv_quote(value: str, was_quoted: bool) -> str:
    if was_quoted or any(c in value for c in ',"\r\n') or value != value.strip():
        return '"' + value.replace('"', '""') + '"'
    return value


def _csv_shape(text: str) -> list[int]:
    return [len(r) for r in csv.reader(io.StringIO(text.lstrip("﻿")))]


# ---- JSON-like -----------------------------------------------------------------------------------

_JSONLIKE_TOKEN = re.compile(
    r"""(?P<ws>\s+)
      |(?P<comment>\#[^\n]*|//[^\n]*)
      |(?P<string>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')
      |(?P<punct>[{}\[\]:,])
      |(?P<word>[^\s{}\[\]:,"'\#]+)""",
    re.X,
)


def _decode_jsonlike_string(token: str) -> str:
    if token.startswith("'"):
        inner = token[1:-1].replace("\\'", "'").replace('"', '\\"')
        token = f'"{inner}"'
    try:
        return json.loads(token)
    except json.JSONDecodeError:
        return token[1:-1]


def _jsonlike_strings(text: str):
    """Yield (start, end, value, path, is_key) for every string literal, tracking its JSON path."""
    stack: list[dict] = []  # {"kind": "obj"/"arr", "key": str|None, "index": int, "expect_key": bool}
    path: list = []
    for m in _JSONLIKE_TOKEN.finditer(text):
        kind = m.lastgroup
        tok = m.group(0)
        if kind in ("ws", "comment"):
            continue
        frame = stack[-1] if stack else None
        if kind == "punct":
            if tok in "{[":
                if frame is not None:
                    path.append(frame["key"] if frame["kind"] == "obj" else frame["index"])
                stack.append({"kind": "obj" if tok == "{" else "arr", "key": None, "index": 0, "expect_key": tok == "{"})
            elif tok in "}]":
                if stack:
                    stack.pop()
                if stack and path:
                    path.pop()
            elif tok == ":" and frame is not None:
                frame["expect_key"] = False
            elif tok == "," and frame is not None:
                if frame["kind"] == "obj":
                    frame["expect_key"] = True
                else:
                    frame["index"] += 1
            continue
        value = _decode_jsonlike_string(tok) if kind == "string" else tok
        if frame is not None and frame["kind"] == "obj" and frame["expect_key"]:
            frame["key"] = value
            if kind == "string":
                yield m.start(), m.end(), value, tuple(path) + (value,), True
            continue
        if kind == "string":
            here = tuple(path) + ((frame["key"] if frame["kind"] == "obj" else frame["index"]),) if frame else ()
            yield m.start(), m.end(), value, here, False


def _lookup_path(data: object, path: tuple) -> object:
    for part in path:
        if isinstance(data, dict) and isinstance(part, str) and part in data:
            data = data[part]
        elif isinstance(data, list) and isinstance(part, int) and 0 <= part < len(data):
            data = data[part]
        else:
            return None
    return data


# ---- loose Java ----------------------------------------------------------------------------------

_JAVA_STRING = re.compile(r'"(?:\\.|[^"\\\n])*"')


def _decode_java_string(token: str) -> str:
    inner = token[1:-1]
    return re.sub(r"\\u([0-9a-fA-F]{4})|\\(.)", lambda m: chr(int(m.group(1), 16)) if m.group(1) else {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "0": "\0"}.get(m.group(2), m.group(2)), inner)


def _encode_java_string(value: str) -> str:
    out = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r")
    return '"' + "".join(c if ord(c) < 0x7F and (ord(c) >= 0x20 or c in "\n\t\r") else f"\\u{ord(c):04x}" for c in out) + '"'


# ---- class files ---------------------------------------------------------------------------------

_CP_SIZES ={3: 5, 4: 5, 5: 9, 6: 9, 7: 3, 8: 3, 9: 5, 10: 5, 11: 5, 12: 5, 15: 4, 16: 3, 17: 5, 18: 5, 19: 3, 20: 3}


def _mutf8_decode(raw: bytes) -> str:
    text = raw.replace(b"\xc0\x80", b"\x00").decode("utf-8", "surrogatepass")
    return text.encode("utf-16", "surrogatepass").decode("utf-16")


def _mutf8_encode(value: str) -> bytes:
    out = bytearray()
    for unit in value.encode("utf-16-be", "surrogatepass").decode("utf-16-be", "surrogatepass"):
        cp = ord(unit)
        if cp == 0:
            out += b"\xc0\x80"
        elif cp < 0x80:
            out.append(cp)
        elif cp < 0x800:
            out += bytes([0xC0 | cp >> 6, 0x80 | cp & 0x3F])
        elif cp < 0x10000:
            out += bytes([0xE0 | cp >> 12, 0x80 | cp >> 6 & 0x3F, 0x80 | cp & 0x3F])
        else:
            cp -= 0x10000
            for sur in (0xD800 | cp >> 10, 0xDC00 | cp & 0x3FF):
                out += bytes([0xE0 | sur >> 12, 0x80 | sur >> 6 & 0x3F, 0x80 | sur & 0x3F])
    return bytes(out)


def _class_string_constants(data: bytes) -> dict[int, str]:
    """Utf8 entries referenced by CONSTANT_String (i.e. string literals), by constant-pool index."""
    count = int.from_bytes(data[8:10], "big")
    i, idx = 10, 1
    utf8: dict[int, str] = {}
    string_refs: set[int] = set()
    while idx < count:
        tag = data[i]
        if tag == 1:
            ln = int.from_bytes(data[i + 1:i + 3], "big")
            utf8[idx] = _mutf8_decode(data[i + 3:i + 3 + ln])
            i += 3 + ln
        else:
            if tag == 8:
                string_refs.add(int.from_bytes(data[i + 1:i + 3], "big"))
            i += _CP_SIZES[tag]
            if tag in (5, 6):
                idx += 1
        idx += 1
    return {k: utf8[k] for k in sorted(string_refs) if k in utf8}


def _class_utf8_table(data: bytes) -> tuple[int, dict[int, str]]:
    """(constant_pool_count, every Utf8 entry by index)."""
    count = int.from_bytes(data[8:10], "big")
    i, idx = 10, 1
    table: dict[int, str] = {}
    while idx < count:
        tag = data[i]
        if tag == 1:
            ln = int.from_bytes(data[i + 1:i + 3], "big")
            table[idx] = _mutf8_decode(data[i + 3:i + 3 + ln])
            i += 3 + ln
        else:
            i += _CP_SIZES[tag]
            if tag in (5, 6):
                idx += 1
        idx += 1
    return count, table


def _aligned_reference_constants(own_jar: Path, ref_jar: Path, class_name: str, threshold: float = 0.9) -> dict[int, str] | None:
    """The reference class's Utf8 table, if its constant-pool layout matches ours.

    A translator who swapped constants in place (no recompile) keeps every index. Accept the
    reference only when the pool sizes are equal and >= threshold of our non-CJK Utf8 entries sit
    at the same index with the same text; otherwise the builds differ and positions mean nothing.
    """
    member = class_name + ".class"
    try:
        with zipfile.ZipFile(own_jar) as own, zipfile.ZipFile(ref_jar) as ref:
            own_count, own_table = _class_utf8_table(read_limited(own, member, MAX_CLASS_BYTES))
            ref_count, ref_table = _class_utf8_table(read_limited(ref, member, MAX_CLASS_BYTES))
    except (OSError, KeyError, zipfile.BadZipFile, IndexError):
        return None
    if own_count != ref_count:
        return None
    anchors = [index for index, text in own_table.items() if not _has_cjk(text)]
    if not anchors or sum(ref_table.get(index) == own_table[index] for index in anchors) / len(anchors) < threshold:
        return None
    return ref_table


def _rewrite_class_strings(data: bytes, replacements: dict[int, str]) -> bytes:
    count = int.from_bytes(data[8:10], "big")
    out = bytearray(data[:10])
    i, idx = 10, 1
    while idx < count:
        tag = data[i]
        if tag == 1:
            ln = int.from_bytes(data[i + 1:i + 3], "big")
            if idx in replacements:
                enc = _mutf8_encode(replacements[idx])
                if len(enc) > 0xFFFF:
                    raise TranslationError(f"constant #{idx} is too long after translation")
                out += b"\x01" + len(enc).to_bytes(2, "big") + enc
            else:
                out += data[i:i + 3 + ln]
            i += 3 + ln
        else:
            size = _CP_SIZES[tag]
            out += data[i:i + size]
            i += size
            if tag in (5, 6):
                idx += 1
        idx += 1
    out += data[i:]
    return bytes(out)


def _units(mod_dir: Path, rel: str, path: Path):
    suffix = path.suffix.lower()
    if suffix == ".csv":
        text, _, _ = _translation_csv_text(path.read_bytes())
        cells = list(_csv_cells(text))
        header, keys = _csv_row_keys(cells)
        # A row whose first cell starts with '#' is a comment the game skips: never player text (FSF's rules.csv
        # "#通用的舰队招呼" rows came back blank from the agent and blocked the whole mod, 2026-10-04).
        commented = {row for row, col, s, e, value, q in cells if col == 0 and value.lstrip().startswith("#")}
        for row, col, s, e, value, q in cells:
            if row and row not in commented and _has_cjk(value):
                column = header[col] if col < len(header) else f"#{col}"
                yield {"id": f"csv:{rel}#{keys.get(row, row)}:{column}", "file": rel, "kind": "csv", "context": {"row": keys.get(row), "column": column}, "source": value}
    elif suffix in JSONLIKE_SUFFIXES or rel == "mod_info.json":
        text = path.read_bytes().decode("utf-8-sig", errors="replace")
        ordinal = 0
        for s, e, value, jpath, is_key in _jsonlike_strings(text):
            if _has_cjk(value):
                yield {"id": f"json:{rel}@{ordinal}", "file": rel, "kind": "json-key" if is_key else "json", "context": {"path": list(jpath)}, "source": value}
                ordinal += 1
    elif suffix == ".java":
        text = _blank_java_comments(path.read_text(encoding="utf-8", errors="replace"))
        ordinal = 0
        for m in _JAVA_STRING.finditer(text):
            value = _decode_java_string(m.group(0))
            if _has_cjk(value):
                yield {"id": f"java:{rel}@{ordinal}", "file": rel, "kind": "java", "context": {"line": text.count("\n", 0, m.start()) + 1}, "source": value}
                ordinal += 1
    elif suffix == ".txt" and _is_text_line_file(rel):
        if path.stat().st_size > MAX_TRANSLATION_BYTES:
            raise OSError("Text exceeds size limit")
        raw = path.read_bytes()
        text, _, _ = _translation_text(raw, path)
        for line, start, end, value in _text_line_units(rel, text):
            if _has_cjk(value):
                yield {"id": f"text:{rel}@{line}", "file": rel, "kind": "text-line", "context": {"line": line}, "source": value}


def _is_text_line_file(rel: str) -> bool:
    parts = rel.replace("\\", "/").split("/")
    if not parts or parts[-1].rsplit(".", 1)[-1].lower() != "txt":
        return False
    lower = [part.lower() for part in parts]
    for index in range(len(lower) - 1):
        if lower[index:index + 2] == ["data", "strings"] and index + 2 < len(parts):
            return True
        if lower[index:index + 2] == ["data", "missions"] and index + 4 == len(parts):
            return True
    return False


def _translation_text(raw: bytes, path: Path) -> tuple[str, str, bool]:
    bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        return raw.decode("utf-8-sig"), "utf-8", bom
    except UnicodeDecodeError:
        if path.suffix.lower() != ".txt" or bom:
            raise
        return raw.decode("gb18030"), "gb18030", False


def _java_whitespace(ch: str) -> bool:
    code = ord(ch)
    return ch in "\t\n\v\f\r\x1c\x1d\x1e\x1f" or (
        unicodedata.category(ch) in {"Zs", "Zl", "Zp"} and code not in (0x00A0, 0x2007, 0x202F)
    )


def _text_line_units(rel: str, text: str):
    line_start = 0
    line = 1
    while line_start <= len(text):
        newline = text.find("\n", line_start)
        line_end = len(text) if newline < 0 else newline
        start, end = line_start, line_end
        while start < end and _java_whitespace(text[start]):
            start += 1
        while end > start and _java_whitespace(text[end - 1]):
            end -= 1
        yield line, start, end, text[start:end]
        if newline < 0:
            break
        line_start = newline + 1
        line += 1
