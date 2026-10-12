"""Text and encoding hygiene checks: non-English text, work files, non-ASCII names, fullwidth numbers, CSV slash quotes."""
from __future__ import annotations

import fnmatch
import re
from .models import ScanResult
from collections import Counter
from pathlib import Path
from .scan_common import DESIGN_TYPE_CSV_TARGETS, _relative
from .scan_javatext import _blank_java_comments
from .scan_json import _csv_header, _load_lenient_json_file, _read_csv_rows_lenient


_DESIGN_TYPE_SOURCES = ("data/hulls/ship_data.csv", "data/weapons/weapon_data.csv", "data/hullmods/hull_mods.csv", "data/campaign/special_items.csv")


def _design_type_color_keys(settings: Path) -> list[str]:
    """designTypeColors keys in file order, duplicates kept (a parsed dict would hide them)."""
    try:
        text = settings.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return []
    start = re.search(r'"designTypeColors"\s*:\s*\{', text)
    if not start:
        return []
    end = text.find("}", start.end())
    block = _blank_java_comments(text[start.end(): end if end >= 0 else len(text)])
    # Starsector JSON also takes '#' line comments; drop them unless the '#' is inside a string.
    lines = []
    for line in block.splitlines():
        in_string = False
        for index, char in enumerate(line):
            if char == '"' and (index == 0 or line[index - 1] != "\\"):
                in_string = not in_string
            elif char == "#" and not in_string:
                line = line[:index]
                break
        lines.append(line)
    return [match.group(1) for match in re.finditer(r'"((?:\\.|[^"\\])*)"\s*:\s*\[', "\n".join(lines))]


def _scan_design_type_colors(root: Path, result: ScanResult, vanilla_core: Path | None) -> None:
    """designTypeColors keys must equal tech/manufacturer text exactly (found translating Blackrock, 2026-09-13).

    A translated manufacturer with an untranslated colour key (or the reverse) loses its colour silently;
    two keys translating to the same text become a duplicate key, and only one survives.
    """
    keys = _design_type_color_keys(root / "data" / "config" / "settings.json")
    if not keys:
        return
    relative = "data/config/settings.json"
    duplicates = sorted(key for key, count in Counter(keys).items() if count > 1)
    if duplicates:
        result.add(id="design-type-color-duplicate-key", category="assets", severity="medium", classification="REVIEW", confidence="DETERMINISTIC", explanation="settings.json designTypeColors repeats a key; only one of the colours survives. Usually two source-language keys translated to the same text.", file=relative, evidence=duplicates)
    manufacturers: set[str] = set()
    for rel in _DESIGN_TYPE_SOURCES:
        for row in _read_csv_rows_lenient(root / rel) or []:
            value = (row.get("tech/manufacturer") or "").strip()
            if value and not value.startswith("#"):
                manufacturers.add(value)
    vanilla_keys: set[str] = set(_design_type_color_keys(vanilla_core / "data" / "config" / "settings.json")) if vanilla_core is not None else set()
    unused = sorted(set(keys) - manufacturers - vanilla_keys)
    if unused:
        result.add(id="design-type-color-unused", category="assets", severity="low", classification="REVIEW", confidence="HIGH" if vanilla_core is not None else "MEDIUM", explanation="A designTypeColors key matches no tech/manufacturer value in this mod" + (" or vanilla" if vanilla_core is not None else "") + ". Keys must equal the manufacturer text exactly, so a translated or renamed manufacturer loses its colour. It may also be meant for another mod's ships.", file=relative, evidence=unused)
    if vanilla_core is not None:
        uncoloured = sorted(manufacturers - set(keys) - vanilla_keys)
        if uncoloured:
            result.add(id="design-type-without-color", category="assets", severity="low", classification="REVIEW", confidence="HIGH", explanation="These tech/manufacturer values have no designTypeColors entry here or in vanilla, so the codex and refit screens show them uncoloured. Cosmetic; usually a manufacturer renamed or translated without its colour key.", file=relative, evidence=uncoloured)


_CJK_TEXT = re.compile(r"[\u3000-\u303f\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uff00-\uffef]")


_PLAYER_TEXT_SUFFIXES = {".csv", ".json", ".faction", ".ship", ".skin", ".wpn", ".variant", ".system", ".proj"}


def _scan_non_english_text(root: Path, result: ScanResult) -> None:
    """Chinese/Japanese/Korean text in data files, outside comments (P13, non-English intake).

    Not a defect in itself; it tells a reviewer the mod needs translation (translate-export) before
    English testing, and after a translation it finds what was missed. Jar string constants are not
    counted here; translate-check covers them.
    """
    counts: Counter[str] = Counter()
    paths = [root / "mod_info.json"] + [path for path in (root / "data").rglob("*") if path.suffix.lower() in _PLAYER_TEXT_SUFFIXES]
    for path in paths:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            stripped = line.lstrip()
            if stripped.startswith("#") or stripped.startswith("//"):
                continue
            hits = len(_CJK_TEXT.findall(line))
            if hits:
                counts[_relative(root, path)] += hits
    if counts:
        result.add(id="player-text-non-english", category="localization", severity="low", classification="REVIEW", confidence="DETERMINISTIC", explanation=f"{len(counts)} data file(s) hold CJK text outside comments ({sum(counts.values())} characters). RC8's fonts have no CJK glyphs, so it shows as '???' in game (RC8-19, FlowerGod 2026-09-28). Translate with translate-export / translate-apply before English live tests; translate-check also covers jar strings.", evidence=[f"{path}: {count}" for path, count in counts.most_common(15)] + ([f"... {len(counts) - 15} more file(s)"] if len(counts) > 15 else []))


# Design docs and IDE files came from the Chinese mods (2026-09-13): .docx/.sai2 notes, IntelliJ .iml.
# Archives and Windows shortcuts: Omega-Trauma ships a .rar and "... - 快捷方式.lnk" files (2026-09-14).
_WORK_FILE_GLOBS = ("*.psd", "*.xcf", "*.kra", "*.sai", "*.sai2", "*.blend", "*.blend1", "*.docx", "*.iml", "*.tmp", "*.orig", "*.old", "*.log", "*~", "*.swp", "*.rej", "*.diff", "*.patch", "*.rar", "*.7z", "*.zip", "*.lnk", "*.url")


def _scan_shippable_work_files(root: Path, result: ScanResult) -> None:
    """Editor/work files a release would ship (release packs copy_drift's file set).

    OS litter (Thumbs.db, .DS_Store, __MACOSX, .git...) is excluded from releases outright; these are
    left to a person because a mod could, rarely, read one on purpose.
    """
    from .copy_drift import _collect

    found = sorted(relative for relative in _collect(root) if any(fnmatch.fnmatch(relative.rsplit("/", 1)[-1].lower(), pattern) for pattern in _WORK_FILE_GLOBS))
    if found:
        result.add(id="shippable-work-file", category="packaging", severity="low", classification="REVIEW", confidence="DETERMINISTIC", explanation="Editor or work files sit in folders a release ships (image-editor sources, temp/backup copies, logs, patches). The game never loads them; move them out of the working copy before packaging.", evidence=found[:25] + ([f"... {len(found) - 25} more"] if len(found) > 25 else []))


_SPEC_ID_KEYS = {".ship": ("hullId",), ".skin": ("skinHullId",), ".variant": ("variantId",), ".wpn": ("id",), ".proj": ("id",), ".faction": ("id",), ".system": ("id",)}


def _scan_non_ascii_names(root: Path, result: ScanResult) -> None:
    """Non-ASCII spec ids and shipped file paths (P13, from the Chinese mods, 2026-09-13).

    The game may accept them, but a translation pass that translates an id breaks every reference to
    it, and tools BridgeForge drives (Project Go's ssmt-cli.bat, some unzippers and launchers) mangle
    non-ASCII paths.
    """
    ids: list[str] = []
    data = root / "data"
    for path in sorted(data.rglob("*.csv")) if data.is_dir() else []:
        for row in _read_csv_rows_lenient(path) or []:
            value = (row.get("id") or "").strip()
            # Whitespace means prose spilled into the id column (Omega-Trauma description.csv); that is
            # csv-row-extra-columns' finding, not an id.
            if value and not value.startswith("#") and not value.isascii() and not re.search(r"\s", value):
                ids.append(f"{_relative(root, path)}: {value}")
    for suffix, keys in _SPEC_ID_KEYS.items():
        for path in sorted(data.rglob(f"*{suffix}")) if data.is_dir() else []:
            spec = _load_lenient_json_file(path)
            if isinstance(spec, dict):
                for key in keys:
                    value = spec.get(key)
                    if isinstance(value, str) and not value.isascii():
                        ids.append(f"{_relative(root, path)}: {key}={value}")
    if ids:
        result.add(id="non-ascii-identifier", category="localization", severity="medium", classification="REVIEW", confidence="DETERMINISTIC", explanation="Spec ids contain non-ASCII characters. Ids are references, not player text: never translate them, and keep them identical everywhere they are used (data files, rules.csv, code, saves). Renaming one breaks existing saves.", evidence=ids[:25] + ([f"... {len(ids) - 25} more"] if len(ids) > 25 else []))
    from .copy_drift import _collect

    paths = sorted(relative for relative in _collect(root) if not relative.isascii())
    if paths:
        result.add(id="non-ascii-file-path", category="packaging", severity="medium", classification="REVIEW", confidence="DETERMINISTIC", explanation="Shipped files have non-ASCII names. Data files that reference them by path must match byte for byte, and some unzippers, launchers and tools (Project Go's CLI) mangle such names. Prefer ASCII file names.", evidence=paths[:25] + ([f"... {len(paths) - 25} more"] if len(paths) > 25 else []))


def _scan_data_encoding(root: Path, result: ScanResult) -> None:
    """Data text files that are not valid UTF-8 (P13). Chinese mods are often saved as GBK.

    Starsector reads its data as UTF-8, so other encodings show as garbled text. Vanilla's own
    descriptions.csv has a few stray CP-1252 bytes, hence REVIEW/low rather than an error.
    """
    bad: list[str] = []
    data = root / "data"
    paths = [root / "mod_info.json"] + ([path for path in data.rglob("*") if path.suffix.lower() in _PLAYER_TEXT_SUFFIXES] if data.is_dir() else [])
    for path in sorted(paths):
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            line = raw.count(b"\n", 0, exc.start) + 1
            guess = ""
            for encoding in ("gb18030", "cp1252"):
                try:
                    raw.decode(encoding)
                except UnicodeDecodeError:
                    continue
                guess = f", decodes as {encoding}"
                break
            bad.append(f"{_relative(root, path)}: line {line}{guess}")
    if bad:
        result.add(id="data-file-not-utf8", category="localization", severity="low", classification="REVIEW", confidence="DETERMINISTIC", explanation="Data files contain bytes that are not valid UTF-8. Starsector reads data as UTF-8, so the text renders garbled. Re-save the file as UTF-8 from its real encoding (often GB18030/GBK in Chinese mods) rather than editing the bytes.", evidence=bad[:25] + ([f"... {len(bad) - 25} more"] if len(bad) > 25 else []))


_FULLWIDTH_NUMBER_CHARS = re.compile(r"[０-９，．。－＋％]")


_NUMBER_CELL = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)%?")


def _scan_fullwidth_numbers(root: Path, result: ScanResult) -> None:
    """CSV cells that are numbers written with full-width characters (P13; FlowerGod used '，' in its CSVs).

    "１５" or "0。5" reads as a number to a person but not to the loader, which rejects the row or
    silently uses a default. Only cells that become a plain number after normalisation are reported,
    so prose with Chinese punctuation is left alone.
    """
    import unicodedata

    hits: list[str] = []
    data = root / "data"
    for path in sorted(data.rglob("*.csv")) if data.is_dir() else []:
        for index, row in enumerate(_read_csv_rows_lenient(path) or [], start=2):
            for column, value in row.items():
                if not isinstance(value, str) or not _FULLWIDTH_NUMBER_CHARS.search(value):
                    continue
                normalised = unicodedata.normalize("NFKC", value.replace("。", ".")).strip()
                if _NUMBER_CELL.fullmatch(normalised):
                    hits.append(f"{_relative(root, path)} row {index} [{column}]: {value!r} -> {normalised}")
    if hits:
        result.add(id="csv-fullwidth-number", category="assets", severity="high", classification="SAFE", confidence="DETERMINISTIC", explanation="CSV cells hold numbers written with full-width digits or punctuation. The loader can't parse them; converting to ASCII keeps the value the author wrote.", evidence=hits[:25] + ([f"... {len(hits) - 25} more"] if len(hits) > 25 else []))


def _scan_csv_design_type_column(root: Path, result: ScanResult) -> None:
    """0.8a's tech/manufacturer column drives the RC8 UI's design-type label; without it every row shows 'Common'."""
    for parts in DESIGN_TYPE_CSV_TARGETS:
        path = root.joinpath(*parts)
        if not path.is_file():
            continue
        header = _csv_header(path)
        if header is None:
            continue
        normalized = [cell.strip().lower() for cell in header]
        if any("tech" in cell or "manufacturer" in cell for cell in normalized):
            continue
        result.add(
            id="csv-missing-design-type-column",
            category="assets",
            severity="low",
            classification="REVIEW",
            confidence="DETERMINISTIC",
            explanation=(
                f"{path.name} has no 'tech' or 'manufacturer' column, the 0.8a-era design-type source column. "
                "0.98a reads it to classify each item's design type in the UI; without it, every row in this file "
                "displays as design type 'Common'. If a custom design type is intended, also add a matching entry "
                "under the settings.json 'designTypeColors' key."
            ),
            file=_relative(root, path),
            evidence=[f"columns:{len(header)}", f"header:{','.join(header)[:200]}"],
        )


# A quoted phrase written with a backslash or slash before each quote (C style) inside a CSV field. Standard CSV
# escapes a quote by doubling it, so BridgeForge's reader splits the row (SEEKER 0.6.6 special_items.csv
# `/"brute force/"`: the probe config got a fragment as special item "0"). The game's reader did not make that stray
# row (getSpecialItemSpec("0") was null, SEEKER-SOLO-20260928), so the harm is tools misreading the file, and the
# slashes shown in-game. Exotica Technologies' special_items.csv has the backslash form (2026-09-28 sweep).
CSV_SLASH_QUOTE = re.compile(r'[/\\]"([^",\r\n]{1,80}?)[/\\]"')


def _scan_csv_slash_quote(root: Path, result: ScanResult) -> None:
    data_dir = root / "data"
    if not data_dir.is_dir():
        return
    for path in sorted(data_dir.rglob("*.csv")):
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        matches = list(CSV_SLASH_QUOTE.finditer(text))
        if not matches:
            continue
        result.add(
            id="csv-slash-quote-escape",
            category="data",
            severity="medium",
            classification="SAFE",
            confidence="HIGH",
            explanation="A CSV field quotes a phrase with a slash or backslash before each quote. Standard CSV escapes a "
                        "quote by doubling it, so BridgeForge (and the probe config it builds) splits the row; the game "
                        "reads past it but shows the slashes. The fix writes the doubled-quote escape vanilla's "
                        "descriptions.csv uses, so the game and the tools read the same text.",
            file=_relative(root, path),
            evidence=[m.group(0) for m in matches[:10]],
        )


def _scan_working_copy_tool_debris(root: Path, result: ScanResult) -> None:
    """A `scratch/` folder belongs beside `working/`/`original/` (this project's own workspace
    layout - see CLAUDE.md), never inside the mod itself.

    Real case (Leon-Heavy-Industries, found 2026-09-21 building `revival-report-draft`): a refused
    `scan --output <path inside working/>/scratch` command's stderr/stdout redirection landed at
    `working/scratch/` anyway (the shell creates the redirect target before the refused command even
    runs), and only surfaced later as an opaque `unverified-json-syntax` UNKNOWN finding on the
    resulting empty `scan_before.json` - never as what it actually was: tool debris inside the mod's
    own copy that a release built straight from `working/` would ship. No real Starsector mod ships
    a folder literally named `scratch`, so this is safe and generic for any mod root, not just a
    revival workspace's `working/`.
    """
    if (root / "scratch").is_dir():
        result.add(
            id="working-copy-tool-debris",
            category="workspace",
            severity="medium",
            classification="MANUAL",
            confidence="DETERMINISTIC",
            explanation=(
                "This mod's own root holds a 'scratch' folder. In this project's workspace layout, scratch/ "
                "is a sibling of working/ and original/, never inside the mod itself - a release built from "
                "this copy would ship it. Move its contents to the workspace-root scratch/ folder (never "
                "delete, log the move in scratch/MOVES.log) and remove this one."
            ),
            file="scratch",
        )
