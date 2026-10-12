"""Checks on rules.csv, person names, duplicate JSON keys and other data-file defects."""
from __future__ import annotations

import csv
import json
import re
from .models import ScanResult
from pathlib import Path
from .scan_common import _relative
from .scan_json import _csv_header, _load_lenient_json_file, _parse_json


# Banner forms only. A bare, case-insensitive "broken" also matched the real mod name "Broken Star"
# after its "(BROEKN MAYBE)" banner was removed, so "BROKEN" must be all-caps or parenthesised.
MOD_INFO_TRIAGE_BANNER_PATTERN = re.compile(
    r"\bBROKEN\b|(?i:\(\s*broken|BROEKN|UNREVIVED|NEEDS TO BE UPDATED|fetch an old game version)"
)


def _person_names_duplicate_lines(path: Path) -> list[int]:
    """1-based line numbers of rows that repeat an earlier row of the same file (blank rows ignored)."""
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return []
    seen: set[tuple[str, ...]] = set()
    repeats = []
    for number, line in enumerate(text.splitlines()[1:], start=2):
        cells = tuple(cell.strip() for cell in next(csv.reader([line]), []))
        if not any(cells) or cells[0].startswith("#"):
            continue
        if cells in seen:
            repeats.append(number)
        seen.add(cells)
    return repeats


def _csv_first_cells(text: str) -> list[tuple[int, int, str, bool]]:
    """(start, end, value, quoted) of the first cell of every record of a CSV, by text offset. A quoted cell may hold newlines."""
    cells: list[tuple[int, int, str, bool]] = []
    i, n = 0, len(text)
    while i < n:
        start, quoted, value = i, text[i] == '"', ""
        if quoted:
            i += 1
            chars = []
            while i < n:
                if text[i] == '"':
                    if i + 1 < n and text[i + 1] == '"':
                        chars.append('"')
                        i += 2
                        continue
                    i += 1
                    break
                chars.append(text[i])
                i += 1
            value = "".join(chars)
        else:
            while i < n and text[i] not in ",\r\n":
                i += 1
            value = text[start:i]
        cells.append((start, i, value, quoted))
        in_quotes = False
        while i < n:  # skip the rest of the record
            c = text[i]
            if c == '"':
                in_quotes = not in_quotes
            elif c == "\n" and not in_quotes:
                i += 1
                break
            i += 1
    return cells


def _rules_duplicate_id_cells(text: str) -> list[tuple[int, int, str, bool, int]]:
    """Later copies of a rule id in rules.csv: (start, end, id, quoted, occurrence number from 2). The header record and
    blank or `#` comment ids are not rules."""
    seen: dict[str, int] = {}
    repeats = []
    for index, (start, end, value, quoted) in enumerate(_csv_first_cells(text)):
        key = value.strip()
        if index == 0 or not key or key.startswith("#"):
            continue
        seen[key] = seen.get(key, 0) + 1
        if seen[key] > 1:
            repeats.append((start, end, key, quoted, seen[key]))
    return repeats


def _scan_rules_csv_duplicate_id(root: Path, result: ScanResult) -> None:
    """RC8 refuses two rules.csv rows with the same id: Fatal 'Duplicate key [marketPostOpenPiratesHostile | ] while loading
    data/campaign/rules.csv' (Ironclads, GRP10J-20261005). 0.7.2 told same-id rules apart by their conditions, so a mod written
    then repeats ids (Ironclads: one rule per faction under one id)."""
    path = root / "data" / "campaign" / "rules.csv"
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return
    repeats = _rules_duplicate_id_cells(text)
    if repeats:
        result.add(
            id="rules-csv-duplicate-id",
            category="content",
            severity="high",
            classification="REVIEW",
            confidence="DETERMINISTIC",
            explanation=f"{len(repeats)} rules.csv row(s) repeat an earlier row's id. RC8 stops at startup with a Fatal 'Duplicate key' "
                        "dialog. `fix` renames each later copy to <id>_2, <id>_3; the rule's conditions and text are untouched.",
            file=_relative(root, path),
            evidence=sorted({f"id:{key}" for _s, _e, key, _q, _n in repeats})[:20],
        )


def _csv_record_cells(text: str) -> list[list[tuple[int, int, str, bool]]]:
    """Every record of a CSV as a list of (start, end, value, quoted) cells by text offset. A quoted cell may hold newlines;
    `""` inside one is a quote. The end offset excludes the delimiter."""
    records: list[list[tuple[int, int, str, bool]]] = []
    i, n = 0, len(text)
    while i < n:
        record: list[tuple[int, int, str, bool]] = []
        while True:
            start, quoted = i, i < n and text[i] == '"'
            if quoted:
                i += 1
                chars = []
                while i < n:
                    if text[i] == '"':
                        if i + 1 < n and text[i + 1] == '"':
                            chars.append('"')
                            i += 2
                            continue
                        i += 1
                        break
                    chars.append(text[i])
                    i += 1
                value = "".join(chars)
            else:
                while i < n and text[i] not in ",\r\n":
                    i += 1
                value = text[start:i]
            record.append((start, i, value, quoted))
            if i < n and text[i] == ",":
                i += 1
                continue
            if i < n and text[i] == "\r":
                i += 1
            if i < n and text[i] == "\n":
                i += 1
            break
        records.append(record)
    return records


def _rules_whitespace_only_line_cells(text: str) -> list[tuple[int, int, str, str]]:
    """(start, end, column, fixed value) for each conditions/script cell of a real rule holding a whitespace-only line. RC8 skips
    an empty line but stops at one holding spaces: RuleException 'No tokens found in string: []' (Ironclads ngcSmugglerOption,
    GRP10K-20261005); vanilla has none outside a commented-out row."""
    records = _csv_record_cells(text)
    if not records:
        return []
    header = [cell[2].strip() for cell in records[0]]
    wanted = [(header.index(name), name) for name in ("conditions", "script") if name in header]
    found = []
    for record in records[1:]:
        rule_id = record[0][2].strip() if record else ""
        if not rule_id or rule_id.startswith("#"):
            continue
        for index, name in wanted:
            if index >= len(record):
                continue
            start, end, value, quoted = record[index]
            fixed_lines, changed = [], False
            for line in value.split("\n"):
                body = line.rstrip("\r")
                if body and not body.strip(" \t"):
                    fixed_lines.append(line[len(body):])
                    changed = True
                else:
                    fixed_lines.append(line)
            if changed:
                found.append((start, end, name, "\n".join(fixed_lines)))
    return found


def _scan_rules_csv_whitespace_only_line(root: Path, result: ScanResult) -> None:
    path = root / "data" / "campaign" / "rules.csv"
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return
    cells = _rules_whitespace_only_line_cells(text)
    if cells:
        result.add(
            id="rules-csv-whitespace-only-line",
            category="content",
            severity="high",
            classification="SAFE",
            confidence="DETERMINISTIC",
            explanation=f"{len(cells)} rules.csv conditions/script cell(s) hold a line of only spaces. RC8 skips an empty line but "
                        "stops at startup on one with spaces (RuleException 'No tokens found in string: []', Ironclads "
                        "GRP10K-20261005). `fix` empties those lines; nothing else changes.",
            file=_relative(root, path),
            evidence=[f"{name}-cell-at:{start}" for start, _e, name, _v in cells][:20],
        )


_CURLY_OPEN, _CURLY_CLOSE = "\u201c", "\u201d"


_OR_LINE = re.compile(r"\r?\n[ \t]*OR[ \t]*\r?\n")


def _alternative_needs_straight_quotes(alternative: str) -> bool:
    """A rules.csv text alternative whose curly double quotes RC8 cannot read: an opening quote with no closing one, or a
    comma between a pair. Metelson Industries' greetingMIHostileWeaker/Stronger (a curly opening quote closed by a straight
    one, "speaks quickly, <U+201C>If our lives are already written, it would...") stopped RC8 at startup with 'Mismatched
    quotes in the string' (alternatives bisected on the rig, BIS4E-BIS4H 2026-10-06; the straight-quote version loaded).
    A balanced pair with no comma inside loads (Faction Relationships Uniquified, live validated), so it is left alone."""
    opens, closes = alternative.count(_CURLY_OPEN), alternative.count(_CURLY_CLOSE)
    if opens != closes:
        return True
    position = 0
    while True:
        start = alternative.find(_CURLY_OPEN, position)
        if start < 0:
            return False
        end = alternative.find(_CURLY_CLOSE, start)
        if end < 0 or "," in alternative[start:end]:
            return True
        position = end + 1


def _rules_curly_quote_cells(text: str) -> list[tuple[int, int, str]]:
    """(start, end, fixed value) for each text cell of a real rule with an alternative that needs straight quotes; the fixed
    value changes only the curly double quotes of those alternatives to straight ones."""
    records = _csv_record_cells(text)
    if not records:
        return []
    header = [cell[2].strip() for cell in records[0]]
    if "text" not in header:
        return []
    index = header.index("text")
    found = []
    for record in records[1:]:
        rule_id = record[0][2].strip() if record else ""
        if not rule_id or rule_id.startswith("#") or index >= len(record):
            continue
        start, end, value, _quoted = record[index]
        pieces, separators, position = [], [], 0
        for match in _OR_LINE.finditer(value):
            pieces.append(value[position:match.start()])
            separators.append(match.group(0))
            position = match.end()
        pieces.append(value[position:])
        changed = False
        for number, piece in enumerate(pieces):
            if (_CURLY_OPEN in piece or _CURLY_CLOSE in piece) and _alternative_needs_straight_quotes(piece):
                pieces[number] = piece.replace(_CURLY_OPEN, '"').replace(_CURLY_CLOSE, '"')
                changed = True
        if changed:
            fixed = pieces[0] + "".join(sep + piece for sep, piece in zip(separators, pieces[1:]))
            found.append((start, end, fixed))
    return found


def _scan_rules_csv_curly_quotes(root: Path, result: ScanResult) -> None:
    path = root / "data" / "campaign" / "rules.csv"
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return
    cells = _rules_curly_quote_cells(text)
    if cells:
        result.add(
            id="rules-csv-curly-quote-unreadable",
            category="content",
            severity="high",
            classification="REVIEW",
            confidence="HIGH",
            explanation=f"{len(cells)} rules.csv text cell(s) hold a curly double quote RC8 cannot read: an opening quote with no "
                        "closing one, or a comma between a pair. RC8 stops at startup with 'Mismatched quotes in the string' "
                        "(Metelson Industries' greetingMIHostileWeaker and greetingMIHostileStronger, GRP4A-20261006). `fix` "
                        "changes only the curly double quotes of those alternatives to straight ones, the same punctuation; "
                        "balanced pairs without a comma are left alone.",
            file=_relative(root, path),
            evidence=[f"text-cell-at:{start}" for start, _e, _v in cells][:20],
        )


def _scan_person_names_duplicate_row(root: Path, result: ScanResult) -> None:
    """RC8 keys person_names.csv rows by every column and stops at startup on a repeat inside one file:
    'Duplicate key [Mao |  | f | xle | ] while loading [data/characters/person_names.csv' (Ironclads, a Fatal dialog,
    GRP10B-20261005). A row also present in vanilla's file is fine: Ironclads shares 1010 rows with it."""
    path = root / "data" / "characters" / "person_names.csv"
    if not path.is_file():
        return
    repeats = _person_names_duplicate_lines(path)
    if repeats:
        result.add(
            id="person-names-duplicate-row",
            category="content",
            severity="high",
            classification="SAFE",
            confidence="DETERMINISTIC",
            explanation=f"{len(repeats)} row(s) repeat an earlier row of person_names.csv. RC8 stops at startup with a "
                        "Fatal 'Duplicate key' dialog. Removing the repeat keeps the name; `fix` does it.",
            file=_relative(root, path),
            evidence=[f"line:{number}" for number in repeats[:20]],
        )


_DUPLICATE_KEY_SUFFIXES = (".json", ".faction", ".ship", ".variant", ".wpn", ".proj", ".skin", ".system")


def _json_duplicate_keys(text: str) -> list[str]:
    """Keys repeated inside one object, in reading order. Empty when the text does not parse."""
    repeats: list[str] = []

    def hook(pairs):
        seen = set()
        for key, _value in pairs:
            if key in seen:
                repeats.append(key)
            seen.add(key)
        return dict(pairs)

    try:
        _parse_json(text, object_pairs_hook=hook)
    except (json.JSONDecodeError, ValueError):
        return []
    return repeats


def _loaded_faction_paths(root: Path, vanilla_core: Path | None) -> set[str] | None:
    """data-relative paths of the faction files the game loads for this mod: those its factions.csv lists plus vanilla's
    (a mod file at a vanilla path replaces it). None when vanilla is unknown, meaning "treat every faction as loaded"."""
    if vanilla_core is None:
        return None
    paths: set[str] = set()
    for base in (root, Path(vanilla_core)):
        listing = base / "data" / "world" / "factions" / "factions.csv"
        if listing.is_file():
            for line in listing.read_text(encoding="utf-8-sig", errors="replace").splitlines()[1:]:
                cell = line.split(",")[0].strip().strip('"').replace("\\", "/")
                if cell:
                    paths.add(cell.lower())
    return paths


def _scan_json_duplicate_key(root: Path, result: ScanResult, vanilla_core: Path | None = None) -> None:
    """org.json (RC8's loader) refuses a key repeated in one object: Fatal 'Duplicate key "knownFighters"' on Ironclads'
    pirates.faction, which BridgeForge's own known-lists fixer had given a second copy (GRP10E-20261005). Python's json
    keeps the last copy silently, so nothing else here notices."""
    loaded_factions = _loaded_faction_paths(root, vanilla_core)
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in _DUPLICATE_KEY_SUFFIXES or not path.is_file():
            continue
        if (path.suffix.lower() == ".faction" and loaded_factions is not None
                and path.relative_to(root).as_posix().lower() not in loaded_factions):
            continue  # never loaded: GMDA's gmda_patrol.faction is in no factions.csv (checked 2026-10-05)
        relative = path.relative_to(root)
        if relative.parts and relative.parts[0].lower() in ("reports", "scratch", "disabled_files"):
            continue
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        if text.count('"') < 4:
            continue
        repeats = _json_duplicate_keys(text)
        if repeats:
            result.add(
                id="json-duplicate-key",
                category="content",
                severity="high",
                classification="REVIEW",
                confidence="DETERMINISTIC",
                explanation="A key appears twice in one JSON object. RC8's org.json loader stops at startup with a Fatal "
                            "'Duplicate key' dialog. Keep the copy the mod means and remove the other.",
                file=_relative(root, path),
                evidence=[f"key:{key}" for key in repeats[:10]],
            )


def _scan_supplies_legacy_column(root: Path, result: ScanResult) -> None:
    """A 0.6-era ship_data.csv has `supplies/day`; RC8 reads `supplies/rec` and `supplies/mo`, so every hull would cost
    nothing to keep fielded. The conversion is the vanilla ratio per hull size (owner rule 2026-10-05), not x30 (SEEKER's
    first conversion gave 150-600 DP hulls that could never deploy)."""
    path = root / "data" / "hulls" / "ship_data.csv"
    header = _csv_header(path) if path.is_file() else None
    if header and "supplies/day" in header and "supplies/rec" not in header and "supplies/mo" not in header:
        result.add(
            id="ship-data-supplies-legacy-column",
            category="content",
            severity="medium",
            classification="REVIEW",
            confidence="DETERMINISTIC",
            explanation="ship_data.csv has the 0.6-era supplies/day column and no supplies/rec or supplies/mo, which RC8 reads. "
                        "`fix` adds them as supplies/day times the vanilla 0.6.2 -> RC8 ratio for the hull's size (frigate 3.0, "
                        "destroyer 2.0, cruiser 2.65, capital 2.67; owner rule 2026-10-05); never x30.",
            file=_relative(root, path),
            evidence=["column:supplies/day"],
        )


def _scan_mod_info_triage_banner(root: Path, result: ScanResult) -> None:
    """A mod_info.json name/description/author still carrying a pre-release triage banner."""
    mod_info = _load_lenient_json_file(root / "mod_info.json")
    if not isinstance(mod_info, dict):
        return
    for field in ("name", "description", "author"):
        value = mod_info.get(field)
        if not isinstance(value, str) or not value:
            continue
        if not MOD_INFO_TRIAGE_BANNER_PATTERN.search(value):
            continue
        result.add(
            id="mod-info-triage-banner",
            category="metadata",
            severity="low",
            classification="REVIEW",
            confidence="HIGH",
            explanation=(
                f"mod_info.json's '{field}' still carries a pre-release triage banner (e.g. BROKEN/BROEKN/"
                "UNREVIVED/NEEDS TO BE UPDATED/'fetch an old game version'). Clean this up before release."
            ),
            file="mod_info.json",
            evidence=[f"field:{field}", f"value:{value}"],
        )
