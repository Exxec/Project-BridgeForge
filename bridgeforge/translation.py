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
import json
import os
import re
import shutil
import stat
import time
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from .safeio import verify_written
from bridgeforge.scan.scanner import _blank_java_comments, _loaded_mod_jars, _parse_class_file, _parse_json
from bridgeforge.zipsafe import MAX_CLASS_BYTES, read_limited
# Reading and rewriting each file format lives in translation_formats (96.5 A6); TranslationError is this module's error.
from .translation_formats import (_JAVA_STRING, MAX_TRANSLATION_BYTES, TranslationError, _aligned_reference_constants,
                                  _class_string_constants, _csv_cells, _csv_quote, _csv_row_keys, _csv_shape,
                                  _decode_java_string, _encode_java_string, _has_cjk, _is_text_line_file, _jsonlike_strings,
                                  _lookup_path, _rewrite_class_strings, _text_line_units, _translation_csv_text,
                                  _translation_text, _units)
from bridgeforge.file_hash import sha256_file as _sha256  # 96.5 A10

SCHEMA_VERSION = 1
EXCLUDED_DIRS = {"src", "out", "build", "target", ".idea", ".vscode", ".git", "__macosx", "meta-inf", "disabled_files", "reports", "scratch"}
# Tokens a translation must carry over unchanged: Java format specifiers, Starsector $variables and
# the \u0001 highlight marker used by getText/format helpers.
# No space flag and only real conversion letters, so English prose like "50% faster" is not a token.
# $variables are ASCII-only: Python's \w also matches CJK, so "$LTHS_Person1标记的NPC" would otherwise
# swallow the Chinese sentence into one "placeholder" no translation can keep (Mirfak rules notes).
# A dot belongs to a $variable only when a name follows it ($player.name), never a sentence period
# ("... $playerName." in Blackrock's rules text).
_PLACEHOLDER = re.compile(r"%(?:\d+\$)?[-#+0,(]*\d*(?:\.\d+)?[sdfxXeEgGcbhno%]|\$[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*|\x01")


# ---- shared helpers ------------------------------------------------------------------------------


def _is_excluded(rel: Path) -> bool:
    # src-decompiled*/ is BridgeForge's decompile of a jar, never loaded: its strings are the jar's own, exported from
    # the jar (FlowerGod 2026-09-29: 960 duplicate entries from src-decompiled/).
    return any(part.lower() in EXCLUDED_DIRS or part.lower() == ".ssmt-backup" or part.lower().startswith("src-decompiled") for part in rel.parts[:-1])


def _mod_id(mod_dir: Path) -> str:
    try:
        data, _ = _parse_json((mod_dir / "mod_info.json").read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TranslationError(f"{mod_dir / 'mod_info.json'} is missing or unreadable: {exc}") from exc
    return str(data.get("id") or "") if isinstance(data, dict) else ""


# ---- export --------------------------------------------------------------------------------------


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
                        data = read_limited(archive, name, MAX_CLASS_BYTES)
                    except (zipfile.BadZipFile, OSError) as exc:
                        # The Chinese Nightcross jar had entries with bad CRCs; report, don't abort.
                        unreadable.append(f"{rel}!{name}: {exc}")
                        continue
                    if _parse_class_file(data) is None:
                        continue
                    for index, value in _class_string_constants(data).items():
                        if _has_cjk(value):
                            found.append({"id": f"jar:{rel}!{name[:-6]}#{index}", "file": rel, "kind": "jar", "context": {"class": name[:-6], "cp_index": index}, "source": value})
        elif path.suffix.lower() == ".class":
            try:
                if path.stat().st_size > MAX_TRANSLATION_BYTES:
                    raise OSError("Class exceeds size limit")
                data = path.read_bytes()
                if _parse_class_file(data) is None:
                    raise ValueError("Invalid class file")
                for index, value in _class_string_constants(data).items():
                    if _has_cjk(value):
                        found.append({"id": f"class:{rel}#{index}", "file": rel, "kind": "class", "context": {"cp_index": index}, "source": value})
            except (OSError, ValueError, IndexError, KeyError) as exc:
                unreadable.append(f"{rel}: {exc}")
        else:
            try:
                found = list(_units(mod_dir, rel, path))
            except (OSError, UnicodeDecodeError) as exc:
                found = []
                if path.suffix.lower() == ".txt" and _is_text_line_file(rel):
                    unreadable.append(f"{rel}: {exc}")
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
                text, _, _ = _translation_csv_text(ref_path.read_bytes())
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
    # "%%" is a literal percent sign, not a value to carry over: Chinese sources write a full-width "％" that English
    # must write as "%%" where the game runs String.format (hull_mods.csv, as Nexerelin's and SWP's do) and as "%"
    # elsewhere (FlowerGod, 2026-09-29), so it is left out of the comparison on both sides.
    # Format specifiers count by the argument each one consumes (_format_arguments), so "%1$s" and "%s" match.
    return Counter(token for token in _PLACEHOLDER.findall(text) if token != "%%" and not token.startswith("%")) \
        + Counter(f"%{index}{conversion}" for index, conversion in _format_arguments(text))


_FORMAT_SPEC = re.compile(r"%(?:(\d+)\$)?[-#+0,(]*\d*(?:\.\d+)?([sdfxXeEgGcbhno%])")


def _format_arguments(text: str) -> list[tuple[int, str]]:
    """(argument index, conversion) for each String.format specifier, in the order Java reads them: an unindexed
    one takes the next argument, "%2$s" the second. A reordering translation must index its specifiers;
    FlowerGod's "%s posts an emergency bounty of %d credits on %s" fed the name to %d and crashed
    (IllegalFormatConversionException, GRP5B-20261005), which an unordered count of tokens let through."""
    found, ordinary = [], 0
    for match in _FORMAT_SPEC.finditer(text):
        if match.group(2) == "%":
            continue
        if match.group(1):
            found.append((int(match.group(1)), match.group(2)))
        else:
            ordinary += 1
            found.append((ordinary, match.group(2)))
    return found


def reindex_format_slots(source: str, english: str) -> str | None:
    """The English text with its String.format slots numbered (`%1$s ... %3$d ... %2$s`) so each takes the argument the
    source's slot of the same conversion takes, or None when no such rewrite is needed or provable. The k-th slot of a
    conversion in the English maps to the k-th of that conversion in the source. FlowerGod's "%s ... %d ... %s" against
    the source's "%s ... %s ... %d" fed the person's name to %d (GRP5B-20261005)."""
    src = [m for m in _FORMAT_SPEC.finditer(source) if m.group(2) != "%"]
    eng = [m for m in _FORMAT_SPEC.finditer(english) if m.group(2) != "%"]
    if not src or len(src) != len(eng) or any(m.group(1) for m in eng):
        return None
    source_args = _format_arguments(source)
    used: set[int] = set()
    mapping = []
    for match in eng:
        candidates = [index for index, conversion in source_args if conversion == match.group(2) and index not in used]
        if not candidates:
            return None
        mapping.append(candidates[0])
        used.add(candidates[0])
    if mapping == list(range(1, len(mapping) + 1)):
        return None
    out, last = [], 0
    for match, index in zip(eng, mapping):
        out.append(english[last:match.start()])
        out.append("%" + str(index) + "$" + match.group(0)[1:])
        last = match.end()
    out.append(english[last:])
    rewritten = "".join(out)
    return rewritten if _placeholders(rewritten) == _placeholders(source) else None


def _resolved(document: dict) -> tuple[dict[str, dict], list[str]]:
    glossary = document.get("glossary") or {}
    by_file: dict[str, dict] = defaultdict(dict)
    problems: list[str] = []
    for entry in document["entries"]:
        value = entry.get("translation") or glossary.get(entry["source"], "")
        if not value:
            continue
        if _placeholders(value) != _placeholders(entry["source"]):
            reindexed = reindex_format_slots(entry["source"], value)
            if reindexed is not None:
                if entry["id"] not in document.setdefault("_reindexed", []):
                    document["_reindexed"].append(entry["id"])
                value = reindexed
        if _placeholders(value) != _placeholders(entry["source"]):
            problems.append(f"{entry['id']}: placeholders differ ({sorted(_placeholders(entry['source']).elements())} vs {sorted(_placeholders(value).elements())})")
            continue
        by_file[entry["file"]][entry["id"]] = {**entry, "translation": value}
    return by_file, problems


def apply_translation(mod_dir: Path, document: dict, out_dir: Path | None = None, in_place: bool = False) -> dict[str, object]:
    """Validate source-bound extensions before applying; linked copies publish as one staged operation."""
    from .translation_contract import apply_with_contract
    try:
        return apply_with_contract(mod_dir, document, out_dir, in_place, export_translation, _apply_translation)
    except (ValueError, TypeError, KeyError, OSError) as exc:
        raise TranslationError(str(exc)) from exc


def _apply_translation(mod_dir: Path, document: dict, out_dir: Path | None = None, in_place: bool = False) -> dict[str, object]:
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
        elif kind == "class":
            _apply_class(path, entries, applied, problems)
        elif kind == "text-line":
            _apply_text_lines(path, rel, entries, applied, problems)
        elif kind == "csv":
            _apply_csv(path, rel, entries, applied, problems)
        elif kind in ("json", "json-key"):
            _apply_jsonlike(path, rel, entries, applied, problems)
        elif kind == "java":
            _apply_java(path, rel, entries, applied, problems)
    _mirror_jar_strings_to_sources(target, by_file, applied)
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
        "format_slots_reindexed": document.get("_reindexed", []),
        "leftover_cjk_units": remaining,
    }


def _mirror_jar_strings_to_sources(target: Path, by_file: dict, applied: Counter) -> None:
    """Give a jar class's shipped source the same translated literals the jar got. Eridani Combine's 18 jar strings were
    translated while src/ kept the Chinese, so a later src-to-jar rebuild would have reverted them (ROADMAP-3 item 92.33,
    2026-11-16). Only an exact Java literal of the source string, in `<any source root>/<class path>.java`, is replaced."""
    sources: dict[str, list[Path]] = defaultdict(list)
    for path in target.rglob("*.java"):
        rel = path.relative_to(target).as_posix()
        if not rel.startswith("data/"):  # loose scripts under data/ are translated as java units already
            sources[path.stem].append(path)
    pairs: dict[Path, list[tuple[str, str]]] = defaultdict(list)
    for entries in by_file.values():
        for entry in entries.values():
            if entry.get("kind") != "jar" or not entry.get("translation"):
                continue
            class_path = entry["context"]["class"].split("$", 1)[0]
            for path in sources.get(class_path.rsplit("/", 1)[-1], []):
                if path.with_suffix("").as_posix().endswith("/" + class_path):
                    pairs[path].append((entry["source"], entry["translation"]))
    def raw_literal(value: str) -> str:  # the literal as a source file usually holds it: characters as they are
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r") + '"'

    from .safeio import atomic_write_text

    for path, replacements in pairs.items():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        new = text
        for source, translation in replacements:
            for literal in {raw_literal(source), _encode_java_string(source)}:
                new = new.replace(literal, raw_literal(translation))
        if new != text:
            atomic_write_text(path, new)
            applied["jar-source"] += 1


def _apply_csv(path: Path, rel: str, entries: dict, applied: Counter, problems: list) -> None:
    raw = path.read_bytes()
    text, encoding, bom = _translation_csv_text(raw)
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
    data = (b"\xef\xbb\xbf" if bom else b"") + new.encode(encoding)
    path.write_bytes(data)
    verify_written(path, data)
    applied["csv"] += len(edits)


def _apply_jsonlike(path: Path, rel: str, entries: dict, applied: Counter, problems: list) -> None:
    text = path.read_bytes().decode("utf-8-sig")
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
    data = (b"\xef\xbb\xbf" if had_bom else b"") + new.encode("utf-8")
    path.write_bytes(data)
    verify_written(path, data)
    applied["json"] += len(edits)


def _apply_java(path: Path, rel: str, entries: dict, applied: Counter, problems: list) -> None:
    original = path.read_bytes().decode("utf-8")
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
    data = new.encode("utf-8")
    path.write_bytes(data)
    verify_written(path, data)
    applied["java"] += len(edits)


def _apply_jar(path: Path, entries: dict, applied: Counter, problems: list) -> None:
    by_class: dict[str, dict[int, dict]] = defaultdict(dict)
    for entry in entries.values():
        by_class[entry["context"]["class"]][int(entry["context"]["cp_index"])] = entry
    tmp = path.parent / (path.name + ".translate.tmp")
    count = 0
    with zipfile.ZipFile(path) as src, zipfile.ZipFile(tmp, "w") as dst:
        for info in src.infolist():
            data = read_limited(src, info)
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
            data = read_limited(check, info)  # CRC verified on read
            if info.filename.endswith(".class") and _parse_class_file(data) is None:
                raise TranslationError(f"{info.filename} does not parse after rewriting")
    # A freshly copied jar is often held briefly by antivirus or an indexer on Windows (seen on
    # Nightcross and Blackrock): retry the swap for a few seconds before giving up.
    expected = tmp.read_bytes()
    for attempt in range(8):
        try:
            tmp.replace(path)
            break
        except PermissionError:
            if attempt == 7:
                raise TranslationError(f"{path} stayed locked; the translated jar is at {tmp}") from None
            time.sleep(1.0)
    verify_written(path, expected)
    applied["jar"] += count


def _apply_class(path: Path, entries: dict, applied: Counter, problems: list) -> None:
    try:
        if path.stat().st_size > MAX_TRANSLATION_BYTES:
            raise OSError("Class exceeds size limit")
        data = path.read_bytes()
        strings = _class_string_constants(data) if _parse_class_file(data) is not None else {}
    except (OSError, ValueError, IndexError, KeyError) as exc:
        problems.append(f"{path.name}: could not read class: {exc}")
        return
    replacements = {}
    for entry in entries.values():
        index = int(entry["context"]["cp_index"])
        if strings.get(index) != entry["source"]:
            problems.append(f"{entry['id']}: constant differs in the class")
            continue
        replacements[index] = entry["translation"]
    if not replacements:
        return
    new = _rewrite_class_strings(data, replacements)
    if _parse_class_file(new) is None:
        problems.append(f"{path.name}: class would not parse; file left untouched")
        return
    data = new
    path.write_bytes(data)
    verify_written(path, data)
    applied["class"] += len(replacements)


def _apply_text_lines(path: Path, rel: str, entries: dict, applied: Counter, problems: list) -> None:
    raw = path.read_bytes()
    if len(raw) > MAX_TRANSLATION_BYTES:
        problems.append(f"{rel}: text exceeds size limit; file left untouched")
        return
    try:
        text, encoding, bom = _translation_text(raw, path)
    except (UnicodeDecodeError, LookupError) as exc:
        problems.append(f"{rel}: could not decode text: {exc}")
        return
    edits = []
    for line, start, end, value in _text_line_units(rel, text):
        entry = entries.get(f"text:{rel}@{line}")
        if entry is None:
            continue
        if entry["source"] != value:
            problems.append(f"{entry['id']}: source text differs in the file")
            continue
        translated = entry["translation"]
        if "\r" in translated or "\n" in translated:
            problems.append(f"{entry['id']}: text-line translations cannot contain line breaks; file left untouched")
            return
        edits.append((start, end, translated))
    new = text
    for start, end, translated in sorted(edits, reverse=True):
        new = new[:start] + translated + new[end:]
    data = (b"\xef\xbb\xbf" if bom else b"") + new.encode(encoding)
    path.write_bytes(data)
    verify_written(path, data)
    applied["text"] += len(edits)


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
