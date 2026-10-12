"""Lenient JSON parsing that mirrors RC8's org.json, tolerance findings, and the CSV/JSON loaders the scan checks share."""
from __future__ import annotations

import csv
import json
import re
from .models import ScanResult
from pathlib import Path


def _without_trailing_commas(text: str) -> str:
    result: list[str] = []
    in_string = False
    escaped = False
    index = 0
    while index < len(text):
        character = text[index]
        if in_string:
            result.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            index += 1
            continue
        if character == '"':
            in_string = True
        if character == ",":
            next_index = index + 1
            while next_index < len(text) and text[next_index].isspace():
                next_index += 1
            if next_index < len(text) and text[next_index] in "}]":
                index += 1
                continue
        result.append(character)
        index += 1
    return "".join(result)


def _strip_line_comments(text: str) -> tuple[str, set[str]]:
    """Remove `#` and `//` line comments, quote-aware for both `'` and `"`.

    Single quotes are not valid JSON syntax, but this pass runs before single
    quotes are converted to double quotes -- at this point a mod's
    single-quoted scalar (e.g. a URL like `'https://example.com/mod'`, or a
    value like `'costs #500 credits'`) is still single-quoted, so a `#`/`//`
    inside it must not be mistaken for the start of a comment. Tracking only
    double quotes would let exactly that happen.
    """
    result: list[str] = []
    tolerances: set[str] = set()
    string_delim: str | None = None
    escaped = False
    index = 0
    length = len(text)
    while index < length:
        character = text[index]
        if string_delim is not None:
            result.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == string_delim:
                string_delim = None
            index += 1
            continue
        if character in "\"'":
            string_delim = character
            result.append(character)
            index += 1
            continue
        if character == "#":
            tolerances.add("hash-comments")
            while index < length and text[index] not in "\r\n":
                index += 1
            continue
        if character == "/" and index + 1 < length and text[index + 1] == "/":
            tolerances.add("slash-comments")
            while index < length and text[index] not in "\r\n":
                index += 1
            continue
        result.append(character)
        index += 1
    return "".join(result), tolerances


def _convert_single_quoted_strings(text: str) -> str:
    """Rewrite `'...'` string tokens (outside double-quoted strings) as `"..."`.

    Observed in real mod_info.json files for scalar-looking values, e.g.
    `{"major": '1', "minor": '5'}`. An apostrophe inside a normal
    double-quoted string is left untouched because conversion only happens
    while not already inside a `"..."` span. An unterminated single-quoted
    token raises ValueError rather than being "repaired" by treating
    end-of-input as an implicit closing quote.
    """
    result: list[str] = []
    in_double = False
    index = 0
    length = len(text)
    while index < length:
        character = text[index]
        if in_double:
            result.append(character)
            if character == "\\" and index + 1 < length:
                result.append(text[index + 1])
                index += 2
                continue
            if character == '"':
                in_double = False
            index += 1
            continue
        if character == '"':
            in_double = True
            result.append(character)
            index += 1
            continue
        if character == "'":
            cursor = index + 1
            content: list[str] = []
            while cursor < length and text[cursor] != "'":
                if text[cursor] == "\\" and cursor + 1 < length:
                    escaped_char = text[cursor + 1]
                    if escaped_char == "'":
                        # The only escape meaningful to a single-quoted string that isn't
                        # already valid JSON escape syntax: drop the backslash, since a
                        # bare "'" needs no escaping inside a double-quoted string.
                        content.append("'")
                    elif escaped_char == '"':
                        content.append('\\"')
                    else:
                        # Any other escape (\\, \n, \t, \uXXXX, ...) is already valid JSON
                        # escape syntax and carries over unchanged.
                        content.append(text[cursor])
                        content.append(escaped_char)
                    cursor += 2
                    continue
                if text[cursor] == '"':
                    content.append('\\"')
                    cursor += 1
                    continue
                content.append(text[cursor])
                cursor += 1
            if cursor >= length:
                raise ValueError(f"Unterminated single-quoted string starting at position {index}")
            inner = "".join(content)
            result.append(f'"{inner}"')
            index = cursor + 1
            continue
        result.append(character)
        index += 1
    return "".join(result)


_JSON_STRING_TOKEN_PATTERN = r'"(?:\\.|[^"\\])*"'


_JAVA_NUMBER_SUFFIX_PATTERN = re.compile(
    # 0.5f and 2d, plus the dotted forms Java's Double.valueOf also takes: 1.f and .0f (Magellan engine_styles).
    _JSON_STRING_TOKEN_PATTERN + r"|(?<![\w.])-?(?:\d+\.?\d*|\.\d+)[fFdD](?![\w.])"
)


# org.json's nextValue reads an unquoted value up to one of these delimiters or a control character
# (spaces included, then trimmed); stringToValue makes it true/false/null in any case, a number, or
# else the text itself. Every case was run through RC8's json.jar on 2026-09-14.
_ORGJSON_UNQUOTED_RUN = r'[^\x00-\x1f,:\]}/\\"\[{;=#]*'


_BAREWORD_TOKEN_PATTERN = re.compile(
    _JSON_STRING_TOKEN_PATTERN
    # STATIONS, or Foundation of Borken's displayName:博尔肯基金会（F.O.B）
    + r"|(?<![\w.$])(?:[A-Za-z_$]|[^\x00-\x7f\s])" + _ORGJSON_UNQUOTED_RUN
    # A digit-led run that isn't a number stays text: Erexeus Tech Complex's "patch":0b. A leading
    # '+' is part of a number: SCY's "renderOrderMod":+5.
    + r"|(?<![\w.$])\+?[0-9]" + _ORGJSON_UNQUOTED_RUN
)


_LOOSE_NUMBER_PATTERN = re.compile(r"\d+(?:\.\d*)?(?:[eE][+-]?\d+)?", re.ASCII)


_HEX_NUMBER_PATTERN = re.compile(r"0[xX][0-9a-fA-F]+")


_RAW_CONTROL_IN_STRING_PATTERN = re.compile(r'"(?:\\.|[^"\\\r\n])*"')


_JSON_LITERAL_TOKENS = {"true", "false", "null"}


def _normalize_string_contents(text: str) -> tuple[str, set[str]]:
    """Bring double-quoted string contents that org.json accepts into strict-JSON shape.

    org.json's nextString rejects only NUL, `\\n` and `\\r` inside a string, and it reads `\\'` as an
    apostrophe (RC8's json.jar, 2026-09-14). Metelson Industries has raw tabs in its description;
    Magellan and Foundation of Borken escape apostrophes. Strict JSON rejects both. Line breaks and
    illegal escapes such as `\\%` are left alone, because the game rejects them too.
    """
    tolerances: set[str] = set()

    def replace(match: re.Match[str]) -> str:
        token = match.group(0)
        unescaped = re.sub(r"\\(.)", lambda escape: "'" if escape.group(1) == "'" else escape.group(0), token, flags=re.S)
        if unescaped != token:
            tolerances.add("apostrophe-escapes")
        escaped = re.sub(r"[\x01-\x09\x0b\x0c\x0e-\x1f]", lambda char: f"\\u{ord(char.group(0)):04x}", unescaped)
        if escaped != unescaped:
            tolerances.add("raw-control-chars")
        return escaped

    return _RAW_CONTROL_IN_STRING_PATTERN.sub(replace, text), tolerances


def _fill_empty_array_elements(text: str) -> tuple[str, bool]:
    """Write `null` for an empty array element, as org.json's JSONArray reads it.

    `["a",,"b"]` and `[,"a"]` load in game with a null element (RC8's json.jar, 2026-09-14; Valhalla
    Starworks' startShipsCombatLarge). Objects get no such leniency, and a comma before `]` stays a
    trailing comma, which is dropped later.
    """
    out: list[str] = []
    stack: list[str] = []
    in_string = escaped = found = False
    for index, char in enumerate(text):
        out.append(char)
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "[{":
            stack.append(char)
        elif char in "]}" and stack:
            stack.pop()
        if char in "[," and stack and stack[-1] == "[":
            ahead = index + 1
            while ahead < len(text) and text[ahead] in " \t\r\n":
                ahead += 1
            if ahead < len(text) and text[ahead] == ",":
                out.append("null")
                found = True
    return "".join(out), found


def _strip_java_number_suffixes(text: str) -> tuple[str, bool]:
    """Drop a trailing f/F/d/D from Java-style float/double literals (e.g. `0.5f`, `2d`).

    Restricted to tokens outside double-quoted strings so a legitimate string
    value ending in one of those letters is never touched.
    """
    found = False

    def replace(match: re.Match[str]) -> str:
        nonlocal found
        token = match.group(0)
        if token.startswith('"'):
            return token
        found = True
        return token[:-1]

    return _JAVA_NUMBER_SUFFIX_PATTERN.sub(replace, text), found


# org.json reads `098` / `000` (leading zeros) and `.7` (leading dot) as numbers; strict JSON rejects
# both. Seen in Mirfak Parcel Service colours ([255,098,000,205]) and Blackrock skins ("baseValueMult":.7).
_LENIENT_NUMBER_PATTERN = re.compile(
    _JSON_STRING_TOKEN_PATTERN + r"|(?<![\w.])(-?)(?:0+(\d+(?:\.\d+)?)|\.(\d+))(?![\w.])"
)


def _normalize_lenient_numbers(text: str) -> tuple[str, bool]:
    """Rewrite leading-zero and leading-dot numbers outside strings into strict JSON numbers."""
    found = False

    def replace(match: re.Match[str]) -> str:
        nonlocal found
        token = match.group(0)
        if token.startswith('"'):
            return token
        found = True
        sign, digits, fraction = match.group(1), match.group(2), match.group(3)
        return f"{sign}{digits}" if digits is not None else f"{sign}0.{fraction}"

    return _LENIENT_NUMBER_PATTERN.sub(replace, text), found


def _orgjson_separators(text: str) -> tuple[str, set[str]]:
    """org.json also accepts `;` between pairs/elements and `=` or `=>` between key and value.

    Xenoargh's Rebal settings.json has `"baseNumOfficers":45;` and loads in-game (verified against
    starsector-core/json.jar, 2026-09-14). Rewritten outside double-quoted strings only; single quotes
    are already converted by the time this runs.
    """
    out: list[str] = []
    tolerances: set[str] = set()
    in_string = escaped = False
    index = 0
    while index < len(text):
        char = text[index]
        if in_string:
            out.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            out.append(char)
        elif char == ";":
            tolerances.add("semicolon-separators")
            out.append(",")
        elif char == "=":
            tolerances.add("equals-key-separators")
            out.append(":")
            if index + 1 < len(text) and text[index + 1] == ">":
                index += 1
        else:
            out.append(char)
        index += 1
    return "".join(out), tolerances


def _quote_barewords_and_keys(text: str) -> tuple[str, set[str]]:
    """Wrap unquoted identifiers (object keys or bareword scalar values) in double quotes.

    `true`/`false`/`null` are left as literals. Whether a given identifier is
    followed (ignoring whitespace) by `:` distinguishes an unquoted key from a
    bareword value for tolerance reporting; both are rewritten the same way.
    """
    tolerances: set[str] = set()

    def replace(match: re.Match[str]) -> str:
        raw = match.group(0)
        if raw.startswith('"'):
            return raw
        token = raw.rstrip(" ")  # org.json trims the unquoted run
        trailing = raw[len(token):]
        if token.lower() in _JSON_LITERAL_TOKENS:
            if token != token.lower():
                tolerances.add("bareword-values")  # org.json: equalsIgnoreCase("true") and so on
            return token.lower() + trailing
        if token[0] == "+" and _LOOSE_NUMBER_PATTERN.fullmatch(token[1:]):
            tolerances.add("lenient-numbers")  # org.json: new Long("+5"), Double.valueOf("+0.5")
            token, raw = token[1:], raw[1:]
        # ASCII digits only: org.json reads a full-width １.0 as text (Traverser Design Bureau).
        if token[0] in "0123456789":
            if re.fullmatch(r"[0-9]+\.", token):
                tolerances.add("lenient-numbers")  # Dassault-Mikoyan's "pitch":1.
                return token + "0" + trailing
            if _LOOSE_NUMBER_PATTERN.fullmatch(token):
                return raw
            if _HEX_NUMBER_PATTERN.fullmatch(token) and int(token, 16) <= 0x7FFFFFFF:
                tolerances.add("lenient-numbers")  # org.json: Integer.parseInt(hex, 16)
                return str(int(token, 16)) + trailing
        lookahead = match.end()
        while lookahead < len(text) and text[lookahead] in " \t\r\n":
            lookahead += 1
        if lookahead < len(text) and text[lookahead] == ":":
            tolerances.add("unquoted-keys")
        else:
            tolerances.add("bareword-values")
        return f'"{token}"' + trailing

    return _BAREWORD_TOKEN_PATTERN.sub(replace, text), tolerances


def _parse_json(text: str, object_pairs_hook=None) -> tuple[object, set[str]]:
    """Parse JSON the way Starsector's lenient (org.json-based) loader does.

    Strict `json.loads` is tried first so the common, well-formed case is not
    slowed down by unnecessary rewriting. On failure, a sequence of
    string-aware rewrites brings the text into strict-JSON shape: strip `#`/
    `//` comments, convert single-quoted strings to double-quoted, strip Java
    float/double suffixes, quote unquoted keys/bareword values, then strip
    trailing commas. Each tolerance actually used is recorded so callers can
    report it rather than silently "fixing" the file.
    """
    try:
        return json.loads(text, object_pairs_hook=object_pairs_hook), set()
    except json.JSONDecodeError as original_error:
        tolerances: set[str] = set()
        try:
            without_comments, comment_tolerances = _strip_line_comments(text)
            tolerances |= comment_tolerances
            without_single_quotes = _convert_single_quoted_strings(without_comments)
            if without_single_quotes != without_comments:
                tolerances.add("single-quotes")
            without_number_suffix, suffix_found = _strip_java_number_suffixes(without_single_quotes)
            if suffix_found:
                tolerances.add("java-number-suffix")
            without_number_suffix, lenient_numbers = _normalize_lenient_numbers(without_number_suffix)
            if lenient_numbers:
                tolerances.add("lenient-numbers")
            without_number_suffix, separator_tolerances = _orgjson_separators(without_number_suffix)
            tolerances |= separator_tolerances
            without_barewords, bareword_tolerances = _quote_barewords_and_keys(without_number_suffix)
            tolerances |= bareword_tolerances
            without_barewords, empty_found = _fill_empty_array_elements(without_barewords)
            if empty_found:
                tolerances.add("empty-array-elements")
            without_commas = _without_trailing_commas(without_barewords)
            # Starsector also accepts a comma after the root object's closing brace (e.g. Exigency factions).
            without_commas = re.sub(r"([}\]])\s*,\s*\Z", r"\1", without_commas)
            if without_commas != without_barewords:
                tolerances.add("trailing-commas")
            without_commas, string_tolerances = _normalize_string_contents(without_commas)
            tolerances |= string_tolerances
        except ValueError:
            # An unterminated single-quoted string is malformed, not a dialect
            # we tolerate; "repairing" it would hide a genuinely broken file.
            raise original_error from None  # the original parse error is the useful one; the repair attempt's ValueError is noise
        try:
            data = json.loads(without_commas, object_pairs_hook=object_pairs_hook)
        except json.JSONDecodeError as rewritten_error:
            if rewritten_error.msg != "Extra data":
                # Say where the lenient rewrite really stopped: Rebal's file failed on a ';' at line 29
                # while the report only showed the strict parser's complaint about a '#' at line 3.
                raise json.JSONDecodeError(
                    f"{original_error.msg} (after lenient rewrites it still fails: {rewritten_error.msg} at line {rewritten_error.lineno} column {rewritten_error.colno})",
                    original_error.doc,
                    original_error.pos,
                ) from rewritten_error
            # org.json (Starsector's loader) stops after the first complete value and ignores the
            # rest -- including real keys when an extra '}' closes the root early (Blackrock's
            # br_consortium.faction loses its factionDoctrine this way).
            stripped = without_commas.lstrip()
            data, end = json.JSONDecoder(object_pairs_hook=object_pairs_hook).raw_decode(stripped)
            tolerances.add("trailing-data")
            if re.search(r'["\w]', stripped[end:]):
                tolerances.add("trailing-content")
        if not tolerances:
            raise original_error from None  # the original parse error is the useful one; the repair attempt's ValueError is noise
        return data, tolerances


def _non_strict_json_finding(result: ScanResult, category: str, file: str) -> None:
    result.add(id="non-strict-json-trailing-comma", category=category, severity="medium", classification="REVIEW", confidence="DETERMINISTIC", explanation="Trailing-comma JSON was accepted by the verified target parser compatibility path; retain it unchanged and recheck the selected game parser before modifying this file.", file=file)


def _hash_comment_json_finding(result: ScanResult, category: str, file: str) -> None:
    result.add(id="json-hash-comment", category=category, severity="info", classification="SAFE", confidence="DETERMINISTIC", explanation="The file uses # comments outside JSON strings, matching Starsector 0.98a core data conventions. BridgeForge parsed them structurally and does not recommend removing or rewriting them.", file=file)


def _slash_comment_json_finding(result: ScanResult, category: str, file: str) -> None:
    result.add(id="json-slash-comment", category=category, severity="info", classification="SAFE", confidence="DETERMINISTIC", explanation="The file uses // comments outside JSON strings. Starsector's lenient (org.json-based) loader accepts them; BridgeForge parsed them structurally and does not recommend removing or rewriting them.", file=file)


def _single_quote_json_finding(result: ScanResult, category: str, file: str) -> None:
    result.add(id="json-single-quoted-string", category=category, severity="info", classification="SAFE", confidence="DETERMINISTIC", explanation="The file uses single-quoted strings in place of double quotes. Starsector's lenient loader accepts them; BridgeForge parsed them structurally and does not recommend rewriting them to double quotes.", file=file)


def _unquoted_key_json_finding(result: ScanResult, category: str, file: str) -> None:
    result.add(id="json-unquoted-key", category=category, severity="info", classification="SAFE", confidence="DETERMINISTIC", explanation="The file has one or more unquoted object keys. Starsector's lenient loader accepts them; BridgeForge parsed them structurally and does not recommend adding quotes.", file=file)


def _bareword_value_json_finding(result: ScanResult, category: str, file: str) -> None:
    result.add(id="json-bareword-value", category=category, severity="info", classification="SAFE", confidence="DETERMINISTIC", explanation="The file has one or more unquoted bareword values, which Starsector's lenient loader reads as plain strings. BridgeForge parsed them structurally and does not recommend adding quotes.", file=file)


def _java_number_suffix_json_finding(result: ScanResult, category: str, file: str) -> None:
    result.add(id="json-java-number-suffix", category=category, severity="info", classification="SAFE", confidence="DETERMINISTIC", explanation="The file has one or more Java-style numeric literal suffixes (e.g. 0.5f, 2d). Starsector's lenient loader reads them as plain numbers; BridgeForge parsed them structurally and does not recommend rewriting them.", file=file)


def _lenient_number_json_finding(result: ScanResult, category: str, file: str) -> None:
    result.add(id="json-lenient-number", category=category, severity="info", classification="SAFE", confidence="DETERMINISTIC", explanation="The file has numbers with leading zeros (e.g. 098), a leading or trailing dot (e.g. .7 or 1.), or hex digits (0x1F). Starsector's lenient loader reads them as plain numbers; BridgeForge parsed them structurally and does not recommend rewriting them.", file=file)


def _json_trailing_data_finding(result: ScanResult, category: str, file: str, tolerances: set[str]) -> None:
    if "trailing-content" in tolerances:
        result.add(id="json-content-after-root", category=category, severity="medium", classification="REVIEW", confidence="DETERMINISTIC", explanation="The root object closes before the end of the file, and keys follow it. Starsector's loader stops at the first complete object, so everything after it never loads. Usually an extra '}' earlier closed the root too soon (Blackrock's br_consortium.faction lost its factionDoctrine this way). Find the stray brace; don't just delete the tail.", file=file)
    else:
        result.add(id="json-trailing-brackets", category=category, severity="info", classification="SAFE", confidence="DETERMINISTIC", explanation="Stray closing brackets or commas follow the root object. Starsector's loader ignores anything after the first complete object, so nothing is lost.", file=file)


def _emit_json_tolerance_findings(result: ScanResult, category: str, file: str, tolerances: set[str]) -> None:
    if "lenient-numbers" in tolerances:
        _lenient_number_json_finding(result, category, file)
    if tolerances & {"semicolon-separators", "equals-key-separators"}:
        used = sorted(tolerances & {"semicolon-separators", "equals-key-separators"})
        result.add(id="json-orgjson-separator", category=category, severity="info", classification="SAFE", confidence="DETERMINISTIC", explanation="The file separates entries with ';' or keys from values with '=' / '=>'. Starsector's org.json loader accepts both (verified against starsector-core/json.jar); BridgeForge parsed them structurally and does not recommend rewriting them, though strict tools will reject the file.", file=file, evidence=used)
    if "trailing-data" in tolerances:
        _json_trailing_data_finding(result, category, file, tolerances)
    if "trailing-commas" in tolerances:
        _non_strict_json_finding(result, category, file)
    if "hash-comments" in tolerances:
        _hash_comment_json_finding(result, category, file)
    if "slash-comments" in tolerances:
        _slash_comment_json_finding(result, category, file)
    if "single-quotes" in tolerances:
        _single_quote_json_finding(result, category, file)
    if "unquoted-keys" in tolerances:
        _unquoted_key_json_finding(result, category, file)
    if "bareword-values" in tolerances:
        _bareword_value_json_finding(result, category, file)
    if "java-number-suffix" in tolerances:
        _java_number_suffix_json_finding(result, category, file)
    if "raw-control-chars" in tolerances:
        result.add(id="json-raw-control-char", category=category, severity="info", classification="SAFE", confidence="DETERMINISTIC", explanation="A string holds a raw tab or other control character. Starsector's org.json loader keeps it (its nextString rejects only NUL and line breaks; verified against starsector-core/json.jar), but strict JSON tools reject the file. BridgeForge parsed it structurally and does not recommend rewriting it.", file=file)
    if "empty-array-elements" in tolerances:
        result.add(id="json-empty-array-element", category=category, severity="medium", classification="REVIEW", confidence="DETERMINISTIC", explanation="An array has an empty element, such as [a,,b] or [,a]. Starsector's org.json loader reads it as null (verified against starsector-core/json.jar), so the file loads, but code that reads the list (ship, faction or blueprint lists) may fail on the null or drop the entry. Check what the author meant.", file=file)
    if "apostrophe-escapes" in tolerances:
        result.add(id="json-escaped-apostrophe", category=category, severity="info", classification="SAFE", confidence="DETERMINISTIC", explanation="A double-quoted string escapes an apostrophe as \\'. Starsector's org.json loader reads it as a plain apostrophe (verified against starsector-core/json.jar), but strict JSON rejects the escape. BridgeForge parsed it structurally and does not recommend rewriting it.", file=file)


_JSON_VALUE_END = re.compile(r"""(?:"|\]|\}|\d|\btrue|\bfalse|\bnull|[A-Za-z_]\w*)\s*$""")


def _repair_missing_commas(text: str, limit: int = 20) -> tuple[str, list[int]] | None:
    """Insert the commas a strict parse says are missing between two lines, until the file parses the way RC8's
    org.json does (`_parse_json`); None when it still fails or the gap is not line-ended. org.json rejects a missing
    separator ("Expected a ',' or ']'", JSONArray/JSONObject in starsector-core/json.jar), so this is a real load
    error, not a tolerance. Hiigaran's polaris.json lacked one after "organics_common" (ROADMAP 34.16, 2026-10-04)."""
    lines = text.split("\n")
    fixed: list[int] = []
    for _ in range(limit):
        try:
            _parse_json("\n".join(lines))
            return ("\n".join(lines), fixed) if fixed else None
        except json.JSONDecodeError as exc:
            # _parse_json reports the strict error and, in its message, where the lenient pass failed.
            inner = re.search(r"Expecting ',' delimiter at line (\d+)", exc.msg)
            if inner:
                target = int(inner.group(1)) - 1
            elif exc.msg.startswith("Expecting ',' delimiter"):
                target = exc.lineno - 1
            else:
                return None
            if not 0 <= target < len(lines):
                return None
            previous = target - 1
            while previous >= 0 and re.sub(r"(#|//).*$", "", lines[previous]).strip() == "":
                previous -= 1
            if previous < 0 or previous in fixed:
                return None
            content = re.sub(r"\s*(#|//)[^\"]*$", "", lines[previous].rstrip("\r"))
            if not _JSON_VALUE_END.search(content):
                return None
            tail = lines[previous].rstrip("\r")[len(content):]
            lines[previous] = content + "," + tail + ("\r" if lines[previous].endswith("\r") else "")
            fixed.append(previous + 1)
    return None


def _unverified_json_syntax_finding(result: ScanResult, category: str, file: str, exc: Exception) -> None:
    result.add(id="unverified-json-syntax", category=category, severity="medium", classification="UNKNOWN", confidence="DETERMINISTIC", explanation=f"A strict JSON parser rejected this file ({exc}). This is not proof that the target game parser rejects it; no matching parser-tolerance evidence is available.", file=file)


def _json_encoding_finding(result: ScanResult, category: str, file: str, exc: UnicodeDecodeError) -> None:
    result.add(id="json-encoding-unverified", category=category, severity="medium", classification="REVIEW", confidence="DETERMINISTIC", explanation=f"JSON could not be decoded as UTF-8 ({exc}). Encoding is separate from JSON structure; verify the target loader before conversion.", file=file)


def _load_lenient_json_file(path: Path) -> object | None:
    """Read a Starsector-legacy JSON file (# comments, trailing commas) or return None."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None
    try:
        data, _ = _parse_json(text)
    except json.JSONDecodeError:
        return None
    return data


def _csv_header(path: Path) -> list[str] | None:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return next(csv.reader(handle), None)
    except (OSError, UnicodeDecodeError, csv.Error):
        return None


def _read_csv_rows(path: Path) -> list[dict[str, str]] | None:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    except (OSError, UnicodeDecodeError, csv.Error):
        return None


def _read_csv_rows_lenient(path: Path) -> list[dict[str, str]] | None:
    """Like _read_csv_rows, but tolerates non-UTF-8 bytes (errors='replace').

    Vanilla's own data/strings/descriptions.csv is not valid UTF-8 (it has stray CP-1252 curly-quote
    bytes). Vanilla content is only ever consulted here as fallback lookup data, never audited for
    its own encoding, so a byte-level decode error must not silently drop the whole file (which would
    make every id it describes look undescribed).
    """
    try:
        with path.open("r", encoding="utf-8-sig", newline="", errors="replace") as handle:
            return list(csv.DictReader(handle))
    except (OSError, csv.Error):
        return None


def _csv_first_column_ids(path: Path) -> set[str]:
    """IDs from a procgen CSV's first column (data rows only, comments skipped)."""
    if not path.is_file():
        return set()
    ids: set[str] = set()
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = csv.reader(handle)
            next(rows, None)
            for row in rows:
                if not row:
                    continue
                first = row[0].strip()
                if not first or first.startswith("#"):
                    continue
                ids.add(first)
    except (OSError, UnicodeDecodeError, csv.Error):
        return set()
    return ids


def _wing_ids_set(path: Path) -> set[str]:
    rows = _read_csv_rows(path)
    if not rows:
        return set()
    ids: set[str] = set()
    for row in rows:
        wing_id = (row.get("id") or "").strip()
        if wing_id and not wing_id.startswith("#"):
            ids.add(wing_id)
    return ids


def _wing_id_variant_map(path: Path) -> dict[str, str]:
    """wing_data.csv's own `id` -> `variant` columns: the correct `shipRoles` replacement for a
    wing id (`shiproles-wing-id`'s fixer)."""
    rows = _read_csv_rows(path)
    if not rows:
        return {}
    mapping: dict[str, str] = {}
    for row in rows:
        wing_id = (row.get("id") or "").strip()
        variant_id = (row.get("variant") or "").strip()
        if wing_id and variant_id and not wing_id.startswith("#"):
            mapping[wing_id] = variant_id
    return mapping
