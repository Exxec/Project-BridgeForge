"""Translation export / prefill / apply / check for mods whose player-visible text is not English.

Built for Starsector's own lenient formats, so no input normalisation is needed:
- CSV: raw cell spans (quoted or not, padded rows, embedded newlines)
- JSON-like (.json/.faction/.ship/.variant/.wpn/.proj/.skin/.system): string literals and object
  keys, found by a path-tracking tokenizer that understands # and // comments, single quotes and
  barewords
- loose Janino .java scripts outside src/: string literals
- loaded jars: CONSTANT_Utf8 entries referenced by CONSTANT_String (string literals only)

Every unit has a stable id, and export records a hash per file. `apply` refuses changed sources,
works on a copy (or an explicit in-place working copy), edits only each unit's exact span, and
re-verifies CSV structure, JSON-like parsing and class-file parsing afterwards.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import shutil
import stat
import time
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from .scanner import _blank_java_comments, _loaded_mod_jars, _parse_class_file, _parse_json

SCHEMA_VERSION = 1
CJK = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
JSONLIKE_SUFFIXES = {".json", ".faction", ".ship", ".variant", ".wpn", ".proj", ".skin", ".system"}
EXCLUDED_DIRS = {"src", "out", "build", "target", ".idea", ".vscode", ".git", "__macosx", "meta-inf"}
# Tokens a translation must carry over unchanged: Java format specifiers, Starsector $variables and
# the \u0001 highlight marker used by getText/format helpers.
# No space flag and only real conversion letters, so English prose like "50% faster" is not a token.
# $variables are ASCII-only: Python's \w also matches CJK, so "$LTHS_Person1标记的NPC" would otherwise
# swallow the Chinese sentence into one "placeholder" no translation can keep (Mirfak rules notes).
# A dot belongs to a $variable only when a name follows it ($player.name), never a sentence period
# ("... $playerName." in Blackrock's rules text).
_PLACEHOLDER = re.compile(r"%(?:\d+\$)?[-#+0,(]*\d*(?:\.\d+)?[sdfxXeEgGcbhno%]|\$[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*|\x01")


class TranslationError(Exception):
    pass


# ---- shared helpers ------------------------------------------------------------------------------

def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_excluded(rel: Path) -> bool:
    return any(part.lower() in EXCLUDED_DIRS for part in rel.parts[:-1])


def _has_cjk(text: str) -> bool:
    return bool(CJK.search(text))


def _mod_id(mod_dir: Path) -> str:
    try:
        data, _ = _parse_json((mod_dir / "mod_info.json").read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TranslationError(f"{mod_dir / 'mod_info.json'} is missing or unreadable: {exc}") from exc
    return str(data.get("id") or "") if isinstance(data, dict) else ""


# ---- CSV -----------------------------------------------------------------------------------------

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

_CP_SIZES = {3: 5, 4: 5, 5: 9, 6: 9, 7: 3, 8: 3, 9: 5, 10: 5, 11: 5, 12: 5, 15: 4, 16: 3, 17: 5, 18: 5, 19: 3, 20: 3}


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
            own_count, own_table = _class_utf8_table(own.read(member))
            ref_count, ref_table = _class_utf8_table(ref.read(member))
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


# ---- export --------------------------------------------------------------------------------------

def _units(mod_dir: Path, rel: str, path: Path):
    suffix = path.suffix.lower()
    if suffix == ".csv":
        text = path.read_bytes().decode("utf-8-sig", "replace")
        cells = list(_csv_cells(text))
        header, keys = _csv_row_keys(cells)
        for row, col, s, e, value, q in cells:
            if row and _has_cjk(value):
                column = header[col] if col < len(header) else f"#{col}"
                yield {"id": f"csv:{rel}#{keys.get(row, row)}:{column}", "file": rel, "kind": "csv", "context": {"row": keys.get(row), "column": column}, "source": value}
    elif suffix in JSONLIKE_SUFFIXES or rel == "mod_info.json":
        text = path.read_text(encoding="utf-8-sig", errors="replace")
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


def export_translation(mod_dir: Path) -> dict[str, object]:
    """Collect every non-English (CJK) player-visible string with a stable id; never writes the mod."""
    mod_dir = Path(mod_dir).expanduser().resolve()
    mod_id = _mod_id(mod_dir)
    entries: list[dict] = []
    hashes: dict[str, str] = {}
    unreadable: list[str] = []
    jars = {jar.resolve() for jar in _loaded_mod_jars(mod_dir)}
    for path in sorted(p for p in mod_dir.rglob("*") if p.is_file()):
        rel_path = path.relative_to(mod_dir)
        if _is_excluded(rel_path):
            continue
        rel = rel_path.as_posix()
        found = []
        if path.suffix.lower() == ".jar" and path.resolve() in jars:
            with zipfile.ZipFile(path) as archive:
                for name in archive.namelist():
                    if not name.endswith(".class"):
                        continue
                    try:
                        data = archive.read(name)
                    except (zipfile.BadZipFile, OSError) as exc:
                        # The Chinese Nightcross jar had entries with bad CRCs; report, don't abort.
                        unreadable.append(f"{rel}!{name}: {exc}")
                        continue
                    if _parse_class_file(data) is None:
                        continue
                    for index, value in _class_string_constants(data).items():
                        if _has_cjk(value):
                            found.append({"id": f"jar:{rel}!{name[:-6]}#{index}", "file": rel, "kind": "jar", "context": {"class": name[:-6], "cp_index": index}, "source": value})
        else:
            try:
                found = list(_units(mod_dir, rel, path))
            except (OSError, UnicodeDecodeError):
                found = []
        if found:
            hashes[rel] = _sha256(path)
            entries.extend(found)
    for entry in entries:
        entry["translation"] = ""
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "TRANSLATION_EXPORT",
        "mod_id": mod_id,
        "source_language": "zh",
        "target_language": "en",
        "instructions": (
            "Translate each entries[].source into natural Starsector English in entries[].translation "
            "(or fill glossary[source] once for repeated strings). Keep %s/%d/$variables/\\u0001 markers, "
            "ids, file paths and punctuation structure unchanged. json-key entries are identifiers used as "
            "keys (e.g. designTypeColors): translate them exactly like the matching tech/manufacturer text."
        ),
        "file_hashes": hashes,
        "unreadable": unreadable,
        "entry_count": len(entries),
        "unique_source_count": len({e["source"] for e in entries}),
        "entries": entries,
        "glossary": {},
    }


# ---- prefill -------------------------------------------------------------------------------------

def prefill_from_record(document: dict, record_paths: list[Path]) -> dict[str, int]:
    """Fill blanks from zh/en record files: JSON arrays of objects with "zh" and "en" (or "c")."""
    pairs: dict[str, set[str]] = defaultdict(set)
    for record in record_paths:
        for path in sorted(Path(record).rglob("*.json")) if Path(record).is_dir() else [Path(record)]:
            try:
                items = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for item in items if isinstance(items, list) else []:
                if isinstance(item, dict) and isinstance(item.get("zh"), str) and isinstance(item.get("en", item.get("c")), str):
                    pairs[item["zh"]].add(item.get("en", item.get("c")))
    filled = ambiguous = 0
    for entry in document["entries"]:
        if entry["translation"]:
            continue
        options = pairs.get(entry["source"], set())
        if len(options) == 1:
            entry["translation"] = next(iter(options))
            entry["provenance"] = "record"
            filled += 1
        elif options:
            entry["candidates"] = sorted(options)
            ambiguous += 1
    return {"filled": filled, "ambiguous": ambiguous}


def prefill_from_reference(document: dict, mod_dir: Path, reference_dir: Path) -> dict[str, int]:
    """Fill blanks from an English copy of the same mod: CSV by row key + column, JSON-like by path,
    jar string constants by index when the class layout matches (see _aligned_reference_constants).

    Then spread each learned source -> English pair to other entries with the identical source.
    """
    mod_dir, reference_dir = Path(mod_dir).resolve(), Path(reference_dir).resolve()
    csv_cache: dict[str, dict] = {}
    json_cache: dict[str, object] = {}
    jar_cache: dict[tuple, dict | None] = {}
    filled = 0
    learned: dict[str, set[str]] = defaultdict(set)
    for entry in document["entries"]:
        if entry["translation"] or entry["kind"] not in ("csv", "json", "jar"):
            continue
        ref_path = reference_dir / entry["file"]
        if not ref_path.is_file():
            continue
        english = None
        if entry["kind"] == "jar":
            key = (entry["file"], entry["context"]["class"])
            if key not in jar_cache:
                jar_cache[key] = _aligned_reference_constants(mod_dir / entry["file"], ref_path, entry["context"]["class"])
            table = jar_cache[key]
            english = table.get(int(entry["context"]["cp_index"])) if table else None
        elif entry["kind"] == "csv":
            if entry["file"] not in csv_cache:
                text = ref_path.read_bytes().decode("utf-8-sig", "replace")
                cells = list(_csv_cells(text))
                header, keys = _csv_row_keys(cells)
                table: dict[tuple, str] = {}
                for row, col, s, e, value, q in cells:
                    if row and col < len(header):
                        table[(keys.get(row), header[col])] = value
                csv_cache[entry["file"]] = table
            english = csv_cache[entry["file"]].get((entry["context"]["row"], entry["context"]["column"]))
        else:
            if entry["file"] not in json_cache:
                try:
                    json_cache[entry["file"]], _ = _parse_json(ref_path.read_text(encoding="utf-8-sig"))
                except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                    json_cache[entry["file"]] = None
            english = _lookup_path(json_cache[entry["file"]], tuple(entry["context"]["path"]))
        if isinstance(english, str) and english.strip() and not _has_cjk(english):
            if _placeholders(english) != _placeholders(entry["source"]):
                # The port changed this text since the English copy (e.g. Blackrock's brfluxmod
                # description gained a %s): the old English is stale. Keep it only as a hint.
                entry["reference_hint"] = english
                continue
            entry["translation"] = english
            entry["provenance"] = "reference"
            learned[entry["source"]].add(english)
            filled += 1
    spread = 0
    for entry in document["entries"]:
        if not entry["translation"] and len(learned.get(entry["source"], ())) == 1:
            entry["translation"] = next(iter(learned[entry["source"]]))
            entry["provenance"] = "reference-same-text"
            spread += 1
    return {"filled": filled, "spread": spread}


# ---- apply ---------------------------------------------------------------------------------------

def _placeholders(text: str) -> Counter:
    return Counter(_PLACEHOLDER.findall(text))


def _resolved(document: dict) -> tuple[dict[str, dict], list[str]]:
    glossary = document.get("glossary") or {}
    by_file: dict[str, dict] = defaultdict(dict)
    problems: list[str] = []
    for entry in document["entries"]:
        value = entry.get("translation") or glossary.get(entry["source"], "")
        if not value:
            continue
        if _placeholders(value) != _placeholders(entry["source"]):
            problems.append(f"{entry['id']}: placeholders differ ({sorted(_placeholders(entry['source']).elements())} vs {sorted(_placeholders(value).elements())})")
            continue
        by_file[entry["file"]][entry["id"]] = {**entry, "translation": value}
    return by_file, problems


def apply_translation(mod_dir: Path, document: dict, out_dir: Path | None = None, in_place: bool = False) -> dict[str, object]:
    """Write translations into a copy of mod_dir (or into mod_dir itself with in_place=True)."""
    mod_dir = Path(mod_dir).expanduser().resolve()
    if (out_dir is None) == (not in_place):
        raise TranslationError("give exactly one of out_dir or in_place=True")
    changed_sources = [rel for rel, digest in (document.get("file_hashes") or {}).items() if not (mod_dir / rel).is_file() or _sha256(mod_dir / rel) != digest]
    if changed_sources:
        raise TranslationError(f"source files changed since export (re-export first): {changed_sources[:5]}")
    by_file, problems = _resolved(document)
    target = mod_dir
    if out_dir is not None:
        target = Path(out_dir).expanduser().resolve()
        if target.exists():
            raise TranslationError(f"{target} already exists; choose a new output folder")
        if target == mod_dir or mod_dir in target.parents:
            raise TranslationError("the output folder must not be inside the source mod")
        shutil.copytree(mod_dir, target)
        # copytree keeps the read-only attribute, and Mirfak's source has read-only files: writing the
        # translation into our own copy then failed half-way (2026-09-14). The source is left as it is.
        for path in target.rglob("*"):
            if path.is_file() and not os.access(path, os.W_OK):
                path.chmod(path.stat().st_mode | stat.S_IWRITE)
    applied: Counter = Counter()
    for rel, entries in sorted(by_file.items()):
        path = target / rel
        kind = next(iter(entries.values()))["kind"]
        if kind == "jar":
            _apply_jar(path, entries, applied, problems)
        elif kind == "csv":
            _apply_csv(path, rel, entries, applied, problems)
        elif kind in ("json", "json-key"):
            _apply_jsonlike(path, rel, entries, applied, problems)
        elif kind == "java":
            _apply_java(path, rel, entries, applied, problems)
    total = sum(1 for e in document["entries"])
    remaining = check_translation(target)["leftover_count"]
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "TRANSLATION_APPLY",
        "status": "OK" if not problems and remaining == 0 else ("PARTIAL" if sum(applied.values()) else "FAIL"),
        "target": str(target),
        "entries": total,
        "applied": dict(applied),
        "problems": problems,
        "leftover_cjk_units": remaining,
    }


def _apply_csv(path: Path, rel: str, entries: dict, applied: Counter, problems: list) -> None:
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    cells = list(_csv_cells(text))
    header, keys = _csv_row_keys(cells)
    edits = []
    for row, col, s, e, value, quoted in cells:
        if not row:
            continue
        column = header[col] if col < len(header) else f"#{col}"
        entry = entries.get(f"csv:{rel}#{keys.get(row, row)}:{column}")
        if entry is None:
            continue
        if entry["source"] != value:
            problems.append(f"{entry['id']}: source text differs in the file")
            continue
        edits.append((s, e, _csv_quote(entry["translation"], quoted)))
    new = text
    for s, e, replacement in sorted(edits, reverse=True):
        new = new[:s] + replacement + new[e:]
    if _csv_shape(new) != _csv_shape(text):
        problems.append(f"{rel}: CSV structure would change; file left untouched")
        return
    path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + new.encode("utf-8"))
    applied["csv"] += len(edits)


def _apply_jsonlike(path: Path, rel: str, entries: dict, applied: Counter, problems: list) -> None:
    text = path.read_text(encoding="utf-8-sig")
    had_bom = path.read_bytes().startswith(b"\xef\xbb\xbf")
    tokens = list(_jsonlike_strings(text))
    # Keys per object, so a translated key never duplicates a sibling. Blackrock's CN settings.json
    # has both "黑石船坞" and "Blackrock" in designTypeColors; org.json may reject a duplicate key.
    siblings: dict[tuple, set[str]] = defaultdict(set)
    for s, e, value, jpath, is_key in tokens:
        if is_key:
            siblings[tuple(jpath[:-1])].add(value)
    edits, ordinal = [], 0
    for s, e, value, jpath, is_key in tokens:
        if not _has_cjk(value):
            continue
        entry = entries.get(f"json:{rel}@{ordinal}")
        ordinal += 1
        if entry is None:
            continue
        if entry["source"] != value:
            problems.append(f"{entry['id']}: source text differs in the file")
            continue
        if is_key and entry["translation"] in siblings[tuple(jpath[:-1])]:
            problems.append(f"{entry['id']}: key {entry['translation']!r} already exists in the same object; left unchanged to avoid a duplicate key")
            continue
        edits.append((s, e, json.dumps(entry["translation"], ensure_ascii=False)))
    new = text
    for s, e, replacement in sorted(edits, reverse=True):
        new = new[:s] + replacement + new[e:]
    try:
        _parse_json(text)
        parsed_before = True
    except json.JSONDecodeError:
        parsed_before = False
    if parsed_before:
        try:
            _parse_json(new)
        except json.JSONDecodeError:
            problems.append(f"{rel}: would no longer parse; file left untouched")
            return
    path.write_bytes((b"\xef\xbb\xbf" if had_bom else b"") + new.encode("utf-8"))
    applied["json"] += len(edits)


def _apply_java(path: Path, rel: str, entries: dict, applied: Counter, problems: list) -> None:
    original = path.read_text(encoding="utf-8")
    blanked = _blank_java_comments(original)
    edits, ordinal = [], 0
    for m in _JAVA_STRING.finditer(blanked):
        value = _decode_java_string(m.group(0))
        if not _has_cjk(value):
            continue
        entry = entries.get(f"java:{rel}@{ordinal}")
        ordinal += 1
        if entry is None:
            continue
        if entry["source"] != value:
            problems.append(f"{entry['id']}: source text differs in the file")
            continue
        edits.append((m.start(), m.end(), _encode_java_string(entry["translation"])))
    new = original
    for s, e, replacement in sorted(edits, reverse=True):
        new = new[:s] + replacement + new[e:]
    path.write_text(new, encoding="utf-8")
    applied["java"] += len(edits)


def _apply_jar(path: Path, entries: dict, applied: Counter, problems: list) -> None:
    by_class: dict[str, dict[int, dict]] = defaultdict(dict)
    for entry in entries.values():
        by_class[entry["context"]["class"]][int(entry["context"]["cp_index"])] = entry
    tmp = path.parent / (path.name + ".translate.tmp")
    count = 0
    with zipfile.ZipFile(path) as src, zipfile.ZipFile(tmp, "w") as dst:
        for info in src.infolist():
            data = src.read(info)
            wanted = by_class.get(info.filename[:-6]) if info.filename.endswith(".class") else None
            if wanted:
                strings = _class_string_constants(data)
                replacements = {}
                for index, entry in wanted.items():
                    if strings.get(index) != entry["source"]:
                        problems.append(f"{entry['id']}: constant differs in the jar")
                        continue
                    replacements[index] = entry["translation"]
                if replacements:
                    new = _rewrite_class_strings(data, replacements)
                    if _parse_class_file(new) is None:
                        problems.append(f"{info.filename}: class would not parse; left untouched")
                    else:
                        data = new
                        count += len(replacements)
            dst.writestr(info, data, compress_type=info.compress_type)
    with zipfile.ZipFile(tmp) as check:
        for info in check.infolist():
            data = check.read(info)  # CRC verified on read
            if info.filename.endswith(".class") and _parse_class_file(data) is None:
                raise TranslationError(f"{info.filename} does not parse after rewriting")
    # A freshly copied jar is often held briefly by antivirus or an indexer on Windows (seen on
    # Nightcross and Blackrock): retry the swap for a few seconds before giving up.
    for attempt in range(8):
        try:
            tmp.replace(path)
            break
        except PermissionError:
            if attempt == 7:
                raise TranslationError(f"{path} stayed locked; the translated jar is at {tmp}")
            time.sleep(1.0)
    applied["jar"] += count


# ---- Project Go translation-memory export ----------------------------------------------------------

# English recovered from the original author (a translator's record or an English copy of the mod)
# outranks machine/AI work in Project Go's provenance order.
_AUTHOR_PROVENANCE = {"record", "reference", "reference-same-text"}


def export_project_go_tm(document: dict, context: str = "") -> dict[str, object]:
    """Project Go (SSMT) translation-memory JSON for `ssmt tm import <db> json <file>`.

    One entry per distinct Chinese source that has a translation (entry translation or glossary).
    Strings kept unchanged (ids, code keys) are skipped. Exact-match lookups in Project Go ignore
    `context`; only fuzzy matching filters on it, so an empty context reuses most widely.
    """
    glossary = document.get("glossary") or {}
    chosen: dict[str, tuple[str, str]] = {}
    for entry in document["entries"]:
        source = entry["source"]
        value = entry.get("translation") or glossary.get(source, "")
        if not value or value == source or not _has_cjk(source):
            continue
        provenance = "AUTHOR_LOCALIZATION" if entry.get("provenance") in _AUTHOR_PROVENANCE else "AI_TRANSLATED"
        current = chosen.get(source)
        if current is None or (current[1] != "AUTHOR_LOCALIZATION" and provenance == "AUTHOR_LOCALIZATION"):
            chosen[source] = (value, provenance)
    return {
        "schemaVersion": 1,
        "entries": [
            {
                "sourceText": source,
                "sourceLanguage": document.get("source_language", "zh"),
                "targetLanguage": document.get("target_language", "en"),
                "translatedText": value,
                "context": context,
                "provenance": provenance,
            }
            for source, (value, provenance) in sorted(chosen.items())
        ],
    }


# ---- check ---------------------------------------------------------------------------------------

def check_translation(mod_dir: Path) -> dict[str, object]:
    """Leftover CJK units, plus designTypeColors keys that no tech/manufacturer value uses (and vice versa)."""
    mod_dir = Path(mod_dir).expanduser().resolve()
    leftover = export_translation(mod_dir)["entries"]
    by_file = Counter(entry["file"] for entry in leftover)
    keys: set[str] = set()
    settings = mod_dir / "data" / "config" / "settings.json"
    if settings.is_file():
        try:
            data, _ = _parse_json(settings.read_text(encoding="utf-8-sig"))
            colors = data.get("designTypeColors") if isinstance(data, dict) else None
            keys = set(colors) if isinstance(colors, dict) else set()
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            pass
    manufacturers: set[str] = set()
    for rel in ("data/hulls/ship_data.csv", "data/weapons/weapon_data.csv", "data/hullmods/hull_mods.csv", "data/campaign/special_items.csv"):
        path = mod_dir / rel
        if path.is_file():
            with path.open(encoding="utf-8-sig", newline="", errors="replace") as handle:
                for row in csv.DictReader(handle):
                    value = (row.get("tech/manufacturer") or "").strip()
                    if value and not value.startswith("#"):
                        manufacturers.add(value)
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "TRANSLATION_CHECK",
        "status": "OK" if not leftover and not (keys and (keys - manufacturers)) else "ATTENTION",
        "leftover_count": len(leftover),
        "leftover_by_file": dict(by_file.most_common()),
        "design_type_keys_unused": sorted(keys - manufacturers),
        "manufacturers_without_design_color": sorted(manufacturers - keys) if keys else [],
    }
