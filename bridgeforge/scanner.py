from __future__ import annotations

import csv
import fnmatch
import hashlib
import json
import re
import zipfile
from collections import Counter
from pathlib import Path
from pathlib import PurePosixPath

from .models import ScanResult, TargetProfile
from .java_ast import AstUnavailable, analyze_sources
from .ashlib_compat import scan_ashlib_compat
from .graphicslib_compat import scan_graphicslib_compat
from .lazylib_compat import scan_lazylib_compat
from .magiclib_compat import scan_magiclib_compat

CLASS_MAJOR_TO_JAVA = {51: 7, 52: 8, 55: 11, 61: 17, 65: 21, 69: 25}
MAX_JAR_ENTRIES = 10_000
MAX_JAR_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
MAX_JAR_COMPRESSION_RATIO = 100
LARGE_BUNDLED_JAR_BYTES = 25 * 1024 * 1024
LIBRARY_PATTERNS = {
    "LazyLib": re.compile(r"lazylib", re.I),
    "MagicLib": re.compile(r"magiclib", re.I),
    "AshLib": re.compile(r"ashlib", re.I),
    "GraphicsLib": re.compile(r"graphicslib", re.I),
    "LunaLib": re.compile(r"lunalib", re.I),
    "Nexerelin": re.compile(r"nexerelin", re.I),
    "Kotlin runtime": re.compile(r"kotlin-(stdlib|reflect)|kotlinx-coroutines", re.I),
    "Gson": re.compile(r"gson", re.I),
}
LIBRARY_PACKAGES = {
    "LazyLib": ("org.lazywizard.lazylib",),
    "MagicLib": ("org.magiclib", "data.scripts.util"),
    "Nexerelin": ("exerelin.",),
}
EXTERNAL_MOD_API_PACKAGES = {
    "Console Commands": ("org.lazywizard.console.",),
    "Industrial Evolution": ("com.fs.starfarer.api.impl.campaign.ids.IndEvo_ids", "indevo.ids."),
    "MagicLib": ("data.scripts.util.",),
}
EXTERNAL_CAMPAIGN_MEMORY_PREFIXES = {
    "Nexerelin": "$nex_",
}
LEGACY_API_RULES = {
    "com.fs.starfarer.api.util.Misc.getHyperspaceTerrain": (
        "legacy-api-hyperspace-terrain",
        "A legacy Starsector utility reference was found. Confirm its replacement against the target API before changing it.",
    ),
    "sun.misc": (
        "internal-jvm-api",
        "An internal JVM API import was found; it may not be supported by the selected Java runtime.",
    ),
    "java.security.SecurityManager": (
        "security-manager",
        "SecurityManager APIs are obsolete on modern Java runtimes and require manual review.",
    ),
}
RUNTIME_PLACEHOLDER_PATTERN = re.compile(
    r"\bthrow\s+new\s+(?:java\.lang\.)?UnsupportedOperationException\s*\(", re.M
)
PERCENT_MULTIPLIER_PATTERN = re.compile(
    r"\.modifyPercent\s*\(\s*[^,]+,\s*1f\s*-\s*[A-Za-z_$][\w$]*\s*\*\s*0\.01f\s*\)"
)
HARDCODED_SYSTEM_LOOKUP_PATTERN = re.compile(r"\bgetStarSystem\s*\(\s*\"([^\"]+)\"\s*\)")
HARDCODED_ENTITY_LOOKUP_PATTERN = re.compile(r"\bgetEntityById\s*\(\s*\"([^\"]+)\"\s*\)")
CAMPAIGN_SYSTEM_CREATION_PATTERN = re.compile(r"\b(?:createStarSystem|addStarSystem)\s*\(\s*\"([^\"]+)\"")
CAMPAIGN_ENTITY_CREATION_PATTERN = re.compile(r"\b(?:addCustomEntity|addEntity)\s*\(\s*\"([^\"]+)\"")
MISSION_FLEET_REFERENCE_PATTERN = re.compile(
    r"\baddToFleet\s*\(\s*FleetSide\.(?:PLAYER|ENEMY)\s*,\s*\"([^\"]+)\"\s*,\s*FleetMemberType\.(SHIP|FIGHTER_WING)"
)
CUSTOM_UI_PLUGIN_PATTERN = re.compile(r"\b(?:implements\s+CustomUIPanelPlugin|new\s+CustomUIPanelPlugin\s*\(\s*\)\s*\{)")
CUSTOM_DIALOG_DELEGATE_PATTERN = re.compile(r"\bimplements\s+CustomDialogDelegate\b")
RELEASE_BLOCKING_TODO_PATTERN = re.compile(
    r"//[^\r\n]*\b(?:TODO|FIXME)\b[^\r\n]*\b(?:remove|delete|disable)\b[^\r\n]*\b(?:final|release)\b",
    re.I,
)
ROBOT_INPUT_INJECTION_PATTERN = re.compile(r"\bnew\s+(?:java\.awt\.)?Robot\s*\(")
TARGET_INTERFACE_CONTRACTS = {
    "LevelupPlugin": {
        "implements": re.compile(r"\bimplements\s+(?:[\w.]+\.)?LevelupPlugin\b"),
        "method": re.compile(r"\bpublic\s+int\s+getBonusXPUseMultAtMaxLevel\s*\(\s*\)"),
        "signature": "int getBonusXPUseMultAtMaxLevel()",
        "suggestion": "For a settings-driven level-up curve, return (int) Global.getSettings().getFloat(\"bonusXPUseMultAtMaxLevel\").",
    },
    "OnHitEffectPlugin.onHit": {
        "interface": "OnHitEffectPlugin",
        "implements": re.compile(r"\bimplements\s+(?:[\w.]+\.)?OnHitEffectPlugin\b"),
        "method": re.compile(r"\bonHit\s*\([^)]*\bApplyDamageResultAPI\b[^)]*\)"),
        "signature": "void onHit(..., ApplyDamageResultAPI, CombatEngineAPI)",
        "suggestion": "The target callback inserts ApplyDamageResultAPI before CombatEngineAPI; preserve the existing effect body and validate it in combat.",
    },
    "AutofireAIPlugin.getTargetMissile": {
        "interface": "AutofireAIPlugin",
        "implements": re.compile(r"\bimplements\s+(?:[\w.]+\.)?AutofireAIPlugin\b"),
        "method": re.compile(r"\b(?:[\w.]+\.)?MissileAPI\s+getTargetMissile\s*\(\s*\)"),
        "signature": "MissileAPI getTargetMissile()",
        "suggestion": "Return the tracked missile target when the legacy AI has one; a null return requires combat validation.",
    },
    "ShipSystemStatsScript.getActiveOverride": {
        "interface": "ShipSystemStatsScript",
        "implements": re.compile(r"\bimplements\s+(?:[\w.]+\.)?ShipSystemStatsScript\b"),
        "method": re.compile(r"\bfloat\s+getActiveOverride\s*\(\s*(?:[\w.]+\.)?ShipAPI\s+\w+\s*\)"),
        "signature": "float getActiveOverride(ShipAPI)",
        "suggestion": "Establish the intended active duration override; the target default sentinel is behavior-sensitive.",
    },
    "ShipSystemStatsScript.getInOverride": {
        "interface": "ShipSystemStatsScript",
        "implements": re.compile(r"\bimplements\s+(?:[\w.]+\.)?ShipSystemStatsScript\b"),
        "method": re.compile(r"\bfloat\s+getInOverride\s*\(\s*(?:[\w.]+\.)?ShipAPI\s+\w+\s*\)"),
        "signature": "float getInOverride(ShipAPI)",
        "suggestion": "Establish the intended activation-in duration override; the target default sentinel is behavior-sensitive.",
    },
    "ShipSystemStatsScript.getOutOverride": {
        "interface": "ShipSystemStatsScript",
        "implements": re.compile(r"\bimplements\s+(?:[\w.]+\.)?ShipSystemStatsScript\b"),
        "method": re.compile(r"\bfloat\s+getOutOverride\s*\(\s*(?:[\w.]+\.)?ShipAPI\s+\w+\s*\)"),
        "signature": "float getOutOverride(ShipAPI)",
        "suggestion": "Establish the intended activation-out duration override; the target default sentinel is behavior-sensitive.",
    },
    "ShipSystemStatsScript.getUsesOverride": {
        "interface": "ShipSystemStatsScript",
        "implements": re.compile(r"\bimplements\s+(?:[\w.]+\.)?ShipSystemStatsScript\b"),
        "method": re.compile(r"\bint\s+getUsesOverride\s*\(\s*(?:[\w.]+\.)?ShipAPI\s+\w+\s*\)"),
        "signature": "int getUsesOverride(ShipAPI)",
        "suggestion": "Establish the intended uses override; the target default sentinel is behavior-sensitive.",
    },
    "ShipSystemStatsScript.getRegenOverride": {
        "interface": "ShipSystemStatsScript",
        "implements": re.compile(r"\bimplements\s+(?:[\w.]+\.)?ShipSystemStatsScript\b"),
        "method": re.compile(r"\bfloat\s+getRegenOverride\s*\(\s*(?:[\w.]+\.)?ShipAPI\s+\w+\s*\)"),
        "signature": "float getRegenOverride(ShipAPI)",
        "suggestion": "Establish the intended regeneration override; the target default sentinel is behavior-sensitive.",
    },
    "ShipSystemStatsScript.getDisplayNameOverride": {
        "interface": "ShipSystemStatsScript",
        "implements": re.compile(r"\bimplements\s+(?:[\w.]+\.)?ShipSystemStatsScript\b"),
        "method": re.compile(r"\bString\s+getDisplayNameOverride\s*\(\s*(?:[\w.]+\.)?(?:ShipSystemStatsScript\.)?State\s+\w+\s*,\s*float\s+\w+\s*\)"),
        "signature": "String getDisplayNameOverride(ShipSystemStatsScript.State, float)",
        "suggestion": "Return the intended dynamic display name or the target default sentinel, then validate combat UI text.",
    },
    "HullModEffect.showInRefitScreenModPickerFor": {
        "interface": "HullModEffect",
        "implements": re.compile(r"\bimplements\s+(?:[\w.]+\.)?HullModEffect\b"),
        "method": re.compile(r"\bboolean\s+showInRefitScreenModPickerFor\s*\(\s*(?:[\w.]+\.)?ShipAPI\s+\w+\s*\)"),
        "signature": "boolean showInRefitScreenModPickerFor(ShipAPI)",
        "suggestion": "Prefer extending the target BaseHullMod where behavior permits; otherwise establish picker visibility explicitly and run the full compile for all remaining obligations.",
    },
}
MEMORY_SELF_STORE_PATTERN = re.compile(
    r"(?:\b\w*(?:memory|mem)\w*\s*|\.getMemoryWithoutUpdate\(\)\s*)\.set\s*\(\s*[^,]+\s*,\s*this\b",
    re.I,
)
FACTION_SPECIAL_ROLE_KEYS = {"doctrine", "includeDefault", "fallback", "fallback2"}
OBSOLETE_FIGHTER_ROLE_NAMES = {"interceptor", "fighter", "bomber"}
BLACK_HOLE_HINT_PATTERN = re.compile(r"black[_\s]?hole|bhole", re.I)
SHADOW_PATH_EXTENSIONS = {".system", ".ship", ".wpn", ".variant", ".skin", ".java"}
GAME_VERSION_RC_PATTERN = re.compile(r"^\d+(?:\.\d+)*[a-zA-Z]*-RC\d+$")

# RC8 script-sandbox classloader forbids these at load time (SecurityException:
# "File access and reflection are not allowed to scripts"). java.lang.ReflectiveOperationException
# and java.io.IOException are deliberately NOT in these sets/prefixes; they load fine.
FORBIDDEN_REFLECT_PREFIX = "java/lang/reflect/"
FORBIDDEN_NIO_FILE_PREFIX = "java/nio/file/"
FORBIDDEN_IO_CLASSES = {
    "java/io/File",
    "java/io/FileInputStream",
    "java/io/FileOutputStream",
    "java/io/FileReader",
    "java/io/FileWriter",
    "java/io/RandomAccessFile",
}
FORBIDDEN_SANDBOX_SOURCE_PATTERN = re.compile(
    r"\bjava\.lang\.reflect\.[A-Za-z_$][\w$]*"
    r"|\bjava\.nio\.file\.[A-Za-z_$][\w$]*"
    r"|\bjava\.io\.(?:File|FileInputStream|FileOutputStream|FileReader|FileWriter|RandomAccessFile)\b"
)
BUNDLED_LIBRARY_PACKAGE_PREFIXES = {
    "GraphicsLib": ("org/dark/",),
    "LazyLib": ("org/lazywizard/",),
    "MagicLib": ("org/magiclib/", "data/scripts/util/Magic"),
    "LunaLib": ("lunalib/",),
    "Nexerelin": ("exerelin/",),
    "JSON": ("org/json/",),
    "LWJGL": ("org/lwjgl/",),
}
LIBRARY_DEPENDENCY_IDS = {
    "GraphicsLib": "shaderlib",
    "LazyLib": "lw_lazylib",
    "MagicLib": "magiclib",
    "LunaLib": "lunalib",
    "Nexerelin": "nexerelin",
}
DESIGN_TYPE_CSV_TARGETS = (
    ("data", "hulls", "ship_data.csv"),
    ("data", "weapons", "weapon_data.csv"),
)


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _java_for_major(major: int) -> str:
    if major in CLASS_MAJOR_TO_JAVA:
        return str(CLASS_MAJOR_TO_JAVA[major])
    return f"class-file major {major}"


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


def _parse_json(text: str) -> tuple[object, set[str]]:
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
        return json.loads(text), set()
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
            raise original_error
        try:
            data = json.loads(without_commas)
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
            data, end = json.JSONDecoder().raw_decode(stripped)
            tolerances.add("trailing-data")
            if re.search(r'["\w]', stripped[end:]):
                tolerances.add("trailing-content")
        if not tolerances:
            raise original_error
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


def _unverified_json_syntax_finding(result: ScanResult, category: str, file: str, exc: Exception) -> None:
    result.add(id="unverified-json-syntax", category=category, severity="medium", classification="UNKNOWN", confidence="DETERMINISTIC", explanation=f"A strict JSON parser rejected this file ({exc}). This is not proof that the target game parser rejects it; no matching parser-tolerance evidence is available.", file=file)


def _json_encoding_finding(result: ScanResult, category: str, file: str, exc: UnicodeDecodeError) -> None:
    result.add(id="json-encoding-unverified", category=category, severity="medium", classification="REVIEW", confidence="DETERMINISTIC", explanation=f"JSON could not be decoded as UTF-8 ({exc}). Encoding is separate from JSON structure; verify the target loader before conversion.", file=file)


def _scan_metadata(root: Path, result: ScanResult) -> None:
    path = root / "mod_info.json"
    if not path.exists():
        result.add(id="missing-mod-info", category="metadata", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation="mod_info.json was not found at the mod root.")
        nested_roots = [child.name for child in root.iterdir() if child.is_dir() and (child / "mod_info.json").is_file()]
        if len(nested_roots) == 1:
            result.add(id="wrapper-directory-layout", category="metadata", severity="medium", classification="REVIEW", confidence="DETERMINISTIC", explanation="A single nested directory contains mod_info.json. Select that directory after extracting the release archive; Bridgeforge will not implicitly change the input root.", evidence=nested_roots)
        return
    try:
        metadata_text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        _json_encoding_finding(result, "metadata", "mod_info.json", exc)
        return
    except OSError as exc:
        result.add(id="unreadable-mod-info", category="metadata", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation=f"mod_info.json could not be read: {exc}", file="mod_info.json")
        return
    try:
        metadata, tolerances = _parse_json(metadata_text)
    except json.JSONDecodeError as exc:
        result.add(id="unverified-mod-info-syntax", category="metadata", severity="high", classification="UNKNOWN", confidence="DETERMINISTIC", explanation=f"A strict JSON parser rejected mod_info.json ({exc}). Metadata could not be trusted for environment inference.", file="mod_info.json")
        return
    if not isinstance(metadata, dict):
        result.add(id="invalid-mod-info", category="metadata", severity="critical", classification="MANUAL", confidence="DETERMINISTIC", explanation="mod_info.json must contain a JSON object.", file="mod_info.json")
        return
    result.metadata = metadata
    result.metadata_parse_mode = "STRICT" if not tolerances else "+".join(sorted(tolerances)).upper()
    _emit_json_tolerance_findings(result, "metadata", "mod_info.json", tolerances)
    game_version = metadata.get("gameVersion") or metadata.get("game_version")
    if game_version:
        result.declared_starsector = str(game_version)
        result.estimated_starsector = str(game_version)
    dependencies = metadata.get("dependencies") or metadata.get("requiredDependencies") or []
    if dependencies:
        result.add(id="declared-dependencies", category="dependencies", severity="info", classification="SAFE", confidence="DETERMINISTIC", explanation="Dependency declarations were found.", file="mod_info.json", evidence=[str(item) for item in dependencies])


def _scan_jars(root: Path, result: ScanResult) -> list[Path]:
    jars = _loaded_mod_jars(root)
    bundled: Counter[str] = Counter()
    for jar in jars:
        entry: dict[str, object] = {"path": _relative(root, jar), "class_file_majors": [], "java_levels": []}
        try:
            with zipfile.ZipFile(jar) as archive:
                entries = archive.infolist()
                uncompressed_bytes = sum(item.file_size for item in entries)
                compressed_bytes = sum(item.compress_size for item in entries)
                ratio = uncompressed_bytes / max(compressed_bytes, 1)
                if len(entries) > MAX_JAR_ENTRIES or uncompressed_bytes > MAX_JAR_UNCOMPRESSED_BYTES or ratio > MAX_JAR_COMPRESSION_RATIO:
                    result.add(id="jar-scan-limit", category="bytecode", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation=f"JAR exceeds safe scan limits ({len(entries)} entries, {uncompressed_bytes} uncompressed bytes, {ratio:.1f}:1 compression ratio).", file=_relative(root, jar))
                    result.jars.append(entry)
                    continue
                if jar.stat().st_size > LARGE_BUNDLED_JAR_BYTES:
                    result.add(id="large-bundled-archive", category="dependencies", severity="medium", classification="REVIEW", confidence="DETERMINISTIC", explanation=f"Archive is {jar.stat().st_size} bytes. Attribute its ownership and dependency role before changing or redistributing it.", file=_relative(root, jar))
                majors: set[int] = set()
                bad_entries: list[str] = []
                for item in entries:
                    member = PurePosixPath(item.filename.replace("\\", "/"))
                    if member.is_absolute() or ".." in member.parts:
                        result.add(id="jar-path-traversal", category="bytecode", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation="JAR contains an absolute or parent-directory member name; it was not opened.", file=_relative(root, jar))
                        continue
                    if item.is_dir():
                        continue
                    # Every entry is read so its CRC is checked: the Chinese Nightcross jar had entries
                    # whose CRC failed, which used to abort this jar's whole scan as "unreadable".
                    try:
                        entry_bytes = archive.read(item)
                    except (zipfile.BadZipFile, OSError, NotImplementedError) as exc:
                        bad_entries.append(f"{item.filename}: {exc}")
                        continue
                    if item.filename.endswith(".class"):
                        class_bytes = entry_bytes
                        header = class_bytes[:8]
                        if header[:4] == b"\xca\xfe\xba\xbe" and len(header) == 8:
                            majors.add(int.from_bytes(header[6:8], "big"))
                            result.compiled_class_names.add(item.filename[:-6].replace("/", ".").replace("\\", "."))
                            for library, prefixes in LIBRARY_PACKAGES.items():
                                if any(prefix.replace(".", "/").encode() in class_bytes for prefix in prefixes):
                                    result.bytecode_library_references.add(library)
                            if b"java/lang/UnsupportedOperationException" in class_bytes:
                                result.add(
                                    id="bytecode-runtime-placeholder-reference",
                                    category="bytecode",
                                    severity="high",
                                    classification="REVIEW",
                                    confidence="HIGH",
                                    explanation="This compiled class references UnsupportedOperationException. It may be an unfinished callback implementation; inspect the class control flow before runtime testing.",
                                    file=_relative(root, jar),
                                    evidence=[item.filename[:-6].replace("/", ".").replace("\\", ".")],
                                )
                if bad_entries:
                    result.add(
                        id="jar-entry-unreadable",
                        category="bytecode",
                        severity="high",
                        classification="MANUAL",
                        confidence="DETERMINISTIC",
                        explanation="JAR entries fail their CRC check or cannot be decompressed. Java's class loader rejects a corrupt class the first time it is needed (a crash mid-game, not at boot); rebuild or re-download the jar. The rest of the jar was scanned.",
                        file=_relative(root, jar),
                        evidence=bad_entries[:25] + ([f"... {len(bad_entries) - 25} more"] if len(bad_entries) > 25 else []),
                    )
                entry["class_file_majors"] = sorted(majors)
                entry["java_levels"] = sorted({_java_for_major(major) for major in majors})
        except (OSError, zipfile.BadZipFile) as exc:
            result.add(id="unreadable-jar", category="bytecode", severity="high", classification="REVIEW", confidence="DETERMINISTIC", explanation=f"JAR could not be inspected: {exc}", file=_relative(root, jar))
        result.jars.append(entry)
        for library, pattern in LIBRARY_PATTERNS.items():
            if pattern.search(jar.name):
                bundled[library] += 1
                severity = "high" if library == "Kotlin runtime" else "info"
                result.add(id=f"bundled-{library.lower().replace(' ', '-')}", category="dependencies", severity=severity, classification="REVIEW", confidence="HIGH", explanation=f"Bundled {library} archive detected. Confirm it does not conflict with the target dependency strategy.", file=_relative(root, jar))
    for library, count in bundled.items():
        if count > 1:
            result.add(id=f"duplicate-{library.lower().replace(' ', '-')}", category="dependencies", severity="high", classification="REVIEW", confidence="DETERMINISTIC", explanation=f"{count} bundled archives match {library}; duplicate classes or versions are possible.")
    return jars


def _scan_sources(root: Path, result: ScanResult) -> None:
    try:
        result.source_facts = analyze_sources(root)
    except AstUnavailable as exc:
        result.add(id="source-ast-unavailable", category="source", severity="medium", classification="UNKNOWN", confidence="DETERMINISTIC", explanation=f"Structured Java parsing was unavailable; import collection used a limited fallback: {exc}")
    imports: set[str] = set()
    import_locations: dict[str, tuple[str, int | None]] = {}
    content_owners: dict[str, list[str]] = {}
    for source in root.rglob("*.java"):
        relative = _relative(root, source)
        try:
            raw_bytes = source.read_bytes()
        except OSError as exc:
            result.add(id="unreadable-source", category="source", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation=str(exc), file=relative)
            continue
        text = raw_bytes.decode("utf-8", errors="replace")
        content_owners.setdefault(hashlib.sha256(raw_bytes).hexdigest(), []).append(relative)
        active_source = "disabled_files" not in source.relative_to(root).parts
        if result.source_facts:
            file_import_facts = [fact for fact in result.source_facts if fact["kind"] == "import" and fact["file"] == relative]
            imports.update(fact["value"] for fact in file_import_facts)
            for fact in file_import_facts:
                import_locations.setdefault(fact["value"], (relative, fact.get("line")))
        else:
            found_imports = re.findall(r"^\s*import\s+([\w.]+(?:\.\*)?)\s*;", text, re.M)
            imports.update(found_imports)
            for name in found_imports:
                import_locations.setdefault(name, (relative, None))
        for needle, (rule_id, explanation) in LEGACY_API_RULES.items():
            if needle in text:
                result.add(id=rule_id, category="source-api", severity="high", classification="REVIEW", confidence="HIGH", explanation=explanation, file=relative, evidence=[needle])
        if active_source and RUNTIME_PLACEHOLDER_PATTERN.search(text):
            result.add(
                id="runtime-placeholder-unsupported-operation",
                category="source",
                severity="high",
                classification="REVIEW",
                confidence="DETERMINISTIC",
                explanation="Active Java source explicitly throws UnsupportedOperationException. This commonly indicates an IDE-generated placeholder that will crash when the callback is invoked.",
                file=relative,
                evidence=["throw new UnsupportedOperationException"],
            )
        if active_source:
            for contract_id, contract in TARGET_INTERFACE_CONTRACTS.items():
                if contract["implements"].search(text) and not contract["method"].search(text):
                    interface = contract.get("interface", contract_id)
                    result.add(
                        id="target-interface-method-missing",
                        category="source-api",
                        severity="critical",
                        classification="MANUAL",
                        confidence="DETERMINISTIC",
                        explanation=f"This source implements Starsector's {interface} but lacks the 0.98a-required {contract['signature']}. It will fail Janino/Javac loading before the mod can start. {contract['suggestion']}",
                        file=relative,
                        evidence=[interface, contract["signature"]],
                    )
        if active_source:
            missing_callbacks = _custom_ui_plugins_missing_button_callback(text)
            if missing_callbacks:
                result.add(
                    id="missing-custom-ui-button-pressed-callback",
                    category="source-api",
                    severity="high",
                    classification="REVIEW",
                    confidence="HIGH",
                    explanation="CustomUIPanelPlugin implementations in 0.98a require buttonPressed(Object). Add a no-op callback when the panel has no button handling, then runtime-test the UI.",
                    file=relative,
                    evidence=[f"{missing_callbacks} plugin block(s) missing buttonPressed(Object)"],
                )
        if active_source and CUSTOM_DIALOG_DELEGATE_PATTERN.search(text) and re.search(r"\bcreateCustomDialog\s*\(\s*CustomPanelAPI\s+\w+\s*\)", text):
            result.add(
                id="legacy-custom-dialog-delegate-signature",
                category="source-api",
                severity="high",
                classification="REVIEW",
                confidence="HIGH",
                explanation="CustomDialogDelegate#createCustomDialog now receives CustomDialogCallback in 0.98a. Update the signature and preserve any required callback behavior before runtime-testing the dialog.",
                file=relative,
                evidence=["createCustomDialog(CustomPanelAPI)"],
            )
        if active_source and RELEASE_BLOCKING_TODO_PATTERN.search(text):
            result.add(
                id="release-blocking-source-todo",
                category="source",
                severity="high",
                classification="REVIEW",
                confidence="HIGH",
                explanation="Active source contains a TODO/FIXME explicitly saying behavior must be removed, deleted, or disabled before release. Inspect it as a possible development-only gameplay or save-state leak.",
                file=relative,
                evidence=["TODO/FIXME release-removal marker"],
            )
        if active_source and ROBOT_INPUT_INJECTION_PATTERN.search(text):
            result.add(
                id="campaign-ui-robot-input-injection",
                category="campaign-ui",
                severity="medium",
                classification="REVIEW",
                confidence="DETERMINISTIC",
                explanation="Campaign UI code creates java.awt.Robot to synthesize operating-system input. This can fail under restricted desktops, overlays, focus changes, or platform-specific input handling; prefer an in-game UI transition when possible and runtime-test every affected dialog.",
                file=relative,
                evidence=["new Robot()"],
            )
        if active_source and MEMORY_SELF_STORE_PATTERN.search(text):
            result.add(
                id="campaign-memory-live-object",
                category="save-risk",
                severity="medium",
                classification="REVIEW",
                confidence="HIGH",
                explanation="Campaign memory stores `this`, a live Java object. Persistent campaign memory should normally use primitive values, IDs, or serializable data; inspect save/load behavior and replace UI/runtime objects where practical.",
                file=relative,
                evidence=["MemoryAPI.set(..., this)"],
            )
        if active_source and PERCENT_MULTIPLIER_PATTERN.search(text):
            result.add(
                id="suspicious-percent-multiplier",
                category="combat-stats",
                severity="medium",
                classification="REVIEW",
                confidence="HIGH",
                explanation="modifyPercent() received a multiplier-shaped expression (for example, 1f - penalty * 0.01f). It will apply approximately +1 percent rather than the intended multiplier or negative percentage in Starsector's mutable-stat API.",
                file=relative,
                evidence=["modifyPercent(..., 1f - value * 0.01f)"],
            )
        if active_source:
            for system_name in HARDCODED_SYSTEM_LOOKUP_PATTERN.findall(text):
                # Zorg18's spawner and Flu-X's plugin both null-check the lookup (2026-09-14): a guarded
                # lookup already survives a missing system, so it isn't a review item.
                guarded = _system_lookup_null_guarded(_blank_java_comments(text), system_name)
                result.add(
                    id="hard-coded-campaign-system-reference",
                    category="campaign",
                    severity="low" if guarded else "medium",
                    classification="SAFE" if guarded else "REVIEW",
                    confidence="DETERMINISTIC",
                    explanation=("Campaign code looks up a star system using a literal string, and null-checks the result, so a missing system is handled. Confirm the ID is the stable system ID." if guarded else "Campaign code looks up a star system using a literal string. Verify that it is the stable system ID, that the target is guaranteed to exist, and that optional/total-conversion environments are guarded."),
                    file=relative,
                    evidence=[system_name] + (["null-guarded"] if guarded else []),
                )
            for entity_id in HARDCODED_ENTITY_LOOKUP_PATTERN.findall(text):
                result.add(
                    id="hard-coded-campaign-entity-reference",
                    category="campaign",
                    severity="medium",
                    classification="REVIEW",
                    confidence="DETERMINISTIC",
                    explanation="Campaign code looks up an entity by a fixed ID. Verify that the entity is created before this code runs and null-check optional or save-dependent entities before dereferencing them.",
                    file=relative,
                    evidence=[entity_id],
                )
            for integration, prefix in EXTERNAL_CAMPAIGN_MEMORY_PREFIXES.items():
                keys = sorted(set(re.findall(rf'"({re.escape(prefix)}[A-Za-z0-9_]+)"', text)))
                if keys:
                    result.add(
                        id="external-campaign-memory-key",
                        category="campaign",
                        severity="medium",
                        classification="REVIEW",
                        confidence="DETERMINISTIC",
                        explanation=f"Campaign code reads {integration}-namespaced memory state directly. Verify the integration is optional, null-safe, and tested with {integration} disabled.",
                        file=relative,
                        evidence=[integration, *keys],
                    )
        commented_spawns = re.findall(r"//[^\r\n]*\b(?:addSpawnPoint|spawnFleet)\s*\(", text)
        uncommented_text = re.sub(r"//[^\r\n]*", "", text)
        active_spawns = re.findall(r"\b(?:addSpawnPoint|spawnFleet)\s*\(", uncommented_text)
        if active_source and commented_spawns and not active_spawns:
            result.add(
                id="campaign-spawn-registration-disabled",
                category="campaign",
                severity="high",
                classification="REVIEW",
                confidence="HIGH",
                explanation="Campaign fleet-spawn calls are present only in comments. The mod may generate its system but will not create those fleets until the spawning code is ported and enabled.",
                file=relative,
                evidence=[f"{len(commented_spawns)} commented spawn call(s)"],
            )
    result.imports = sorted(imports)
    for paths in content_owners.values():
        if len(paths) > 1:
            result.add(id="duplicate-source-layout", category="source", severity="medium", classification="REVIEW", confidence="DETERMINISTIC", explanation="Identical Java source appears at multiple paths. Establish the authoritative source/JAR layout before compiling or modifying it.", evidence=sorted(paths))
    _scan_mission_local_fleet_references(root, result)
    _scan_campaign_fleet_references(root, result)
    _scan_core_campaign_plugin_reregistered(root, result)
    _scan_system_generation_unguarded(root, result)
    _scan_mission_required_files(root, result)
    _scan_loose_script_janino_risk(root, result)
    _scan_weapon_effect_static_state(root, result)
    _scan_rules_firebest_populate_options(root, result)
    _scan_hullmod_instance_state(root, result)
    _scan_personality_ids(root, result)
    _scan_bare_market_fleet_source(root, result)
    _scan_legacy_event_report(root, result)
    _scan_non_english_text(root, result)
    _scan_shippable_work_files(root, result)
    _scan_non_ascii_names(root, result)
    _scan_data_encoding(root, result)
    _scan_fullwidth_numbers(root, result)
    _scan_source_build_dependencies(root, result, import_locations)
    _scan_removed_api_calls(root, result)

    scan_lazylib_compat(root, result)
    scan_magiclib_compat(result)
    scan_ashlib_compat(root, result)
    scan_graphicslib_compat(root, result)


# API calls the target no longer has, matched only on receivers whose type is certain. Each entry needs
# javap evidence from the target's starfarer.api.jar.
REMOVED_API_CALLS = (
    (
        re.compile(r"\b(?:Global\s*\.\s*)?getSector\s*\(\s*\)\s*\.\s*createFleet\s*\("),
        "SectorAPI.createFleet(factionId, fleetTypeId)",
        # javap of RC8 starfarer.api.jar: SectorAPI has no createFleet (2026-09-14). The 0.6 BaseSpawnPoint
        # spawners (Gekelonians, Cobalt-Arms, Batavia, ...) built fleets from faction fleet types with it.
        "0.6-era fleet creation from a faction's fleet types; RC8's SectorAPI has no createFleet. Build the fleet "
        "with FleetFactoryV3.createFleet(FleetParamsV3) (see Zorg18 r1's ZorgFleetSpawner) and keep the spawn point.",
    ),
)


def _scan_removed_api_calls(root: Path, result: ScanResult) -> None:
    """Calls to API methods the target removed, in loose scripts and bundled sources."""
    for pattern, signature, explanation in REMOVED_API_CALLS:
        hits: list[str] = []
        for source in sorted(root.rglob("*.java")):
            if "disabled_files" in source.relative_to(root).parts:
                continue  # never loaded by the game
            try:
                text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            for match in pattern.finditer(text):
                hits.append(f"{_relative(root, source)}:{text.count(chr(10), 0, match.start()) + 1}")
        if hits:
            result.add(
                id="removed-api-call",
                category="source-api",
                severity="critical",
                classification="MANUAL",
                confidence="DETERMINISTIC",
                explanation=f"Source calls {signature}, which the target API no longer has: {explanation} A loose script with this call fails to compile at load, so the game doesn't start.",
                evidence=[f"{signature}: {len(hits)} call(s)"] + hits[:12] + (["..."] if len(hits) > 12 else []),
            )


def _scan_source_build_dependencies(root: Path, result: ScanResult, import_locations: dict[str, tuple[str, int | None]] | None = None) -> None:
    lombok_imports = sorted(item for item in result.imports if item == "lombok" or item.startswith("lombok."))
    if lombok_imports:
        build_files = [name for name in ("pom.xml", "build.gradle", "build.gradle.kts") if (root / name).is_file()]
        detail = " Build metadata was not found." if not build_files else f" Build metadata found: {', '.join(build_files)}."
        result.add(
            id="source-lombok-annotation-processing",
            category="build",
            severity="high",
            classification="MANUAL",
            confidence="DETERMINISTIC",
            explanation="Source imports Lombok, which generates methods and constructors during compilation. A plain javac rebuild will fail or produce missing members unless Lombok is supplied as an annotation processor." + detail,
            evidence=lombok_imports,
        )
    # An import of one of the mod's own classes needs no library, even inside a library-named package:
    # Blackrock ships its own data.scripts.util.AnamorphicFlare / BRDYMulti / I18nUtil, which is
    # MagicLib's legacy package prefix.
    local_classes = set(_source_class_index(root))
    for _jar, _member, data in _iter_jar_class_files(root):
        info = _parse_class_file(data)
        if info is not None and info.this_class:
            local_classes.add(info.this_class.replace("/", "."))
    # Imports of mod-style classes (data.*) that this mod defines nowhere and no known library provides:
    # another mod's classes. FX Example imports FX Core's data.scripts.fx_Particle / fx_SharedLib /
    # fx_Trail but declared no dependency on it (2026-09-14).
    # MagicLib's legacy packages (data.scripts.util.Magic*, data.scripts.plugins.Magic*) count as a library.
    known_prefixes = tuple(prefix for prefixes in (*LIBRARY_PACKAGES.values(), *EXTERNAL_MOD_API_PACKAGES.values()) for prefix in prefixes) + ("data.scripts.plugins.Magic",)
    active_imports: dict[str, set[str]] = {}
    # A script in the removed class's own package uses it without an import: Antediluvians'
    # data.scripts.world.AntediluvianSpawnPoint extends BaseSpawnPoint directly (2026-09-14).
    same_package_uses: dict[str, set[str]] = {}
    for source in sorted(root.rglob("*.java")):
        if "disabled_files" in source.relative_to(root).parts:
            continue  # never loaded by the game (Zorg18 keeps its 0.6 spawn points there)
        try:
            text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        for imported in re.findall(r"(?m)^\s*import\s+([\w.]+)\s*;", text):
            active_imports.setdefault(imported, set()).add(_relative(root, source))
        package = re.search(r"(?m)^\s*package\s+([\w.]+)\s*;", text)
        if package:
            for name in LEGACY_VANILLA_CLASSES:
                owner, simple = name.rsplit(".", 1)
                if owner == package.group(1) and re.search(rf"\b{re.escape(simple)}\b", text):
                    same_package_uses.setdefault(name, set()).add(_relative(root, source))
    # A mod that ships its own copy of the class (Vacuum's earlier BaseSpawnPoint shim) is not affected.
    legacy = {name: set(files) for name, files in active_imports.items() if name in LEGACY_VANILLA_CLASSES and name not in local_classes}
    for name, files in same_package_uses.items():
        if name not in local_classes:
            legacy.setdefault(name, set()).update(files)
    if legacy:
        result.add(
            id="legacy-vanilla-class-import",
            category="source-api",
            severity="critical",
            classification="MANUAL",
            confidence="DETERMINISTIC",
            explanation="Source uses a vanilla class that no longer exists in 0.98a, by import or by simple name from the same package. A loose script using it fails to compile at load; a jar class fails when it loads. Port the code to the current API (e.g. BaseSpawnPoint fleets to an EveryFrameScript that builds fleets, as Zorg18 did).",
            evidence=[f"{name}: {LEGACY_VANILLA_CLASSES[name]} ({len(files)} file(s): {', '.join(sorted(files)[:6])}{' ...' if len(files) > 6 else ''})" for name, files in sorted(legacy.items())],
        )
    foreign = sorted(
        item for item in active_imports
        if item.startswith("data.") and item not in LEGACY_VANILLA_CLASSES and item not in VANILLA_LOOSE_SCRIPT_CLASSES
        and item not in local_classes and item.rsplit(".", 1)[0] not in local_classes
        and not item.startswith(known_prefixes)
    )
    if foreign:
        declared = bool(result.metadata.get("dependencies") or result.metadata.get("requiredDependencies"))
        result.add(
            id="source-import-unresolved",
            category="dependencies",
            severity="high",
            classification="REVIEW",
            confidence="HIGH",
            explanation="Source imports mod classes that this mod defines nowhere (no source, no jar class) and no known library provides. They belong to another mod, which must be installed and declared in mod_info.json, or the importing class fails when it loads." + (" The mod declares dependencies that may provide them; confirm." if declared else " The mod declares no dependency."),
            evidence=foreign[:20] + ([f"... {len(foreign) - 20} more"] if len(foreign) > 20 else []),
        )
    console_commands = _console_command_classes(root)
    for dependency, prefixes in EXTERNAL_MOD_API_PACKAGES.items():
        imports = sorted(item for item in result.imports if item not in local_classes and any(item == prefix.rstrip(".") or item.startswith(prefix) for prefix in prefixes))
        if imports and dependency == "Console Commands" and console_commands:
            # Console Commands loads command classes only from data/console/commands.csv, so without it
            # they are never loaded (Bionic Alteration's four commands, 2026-09-14).
            importing = _sources_mentioning(root, [prefix.rstrip(".") for prefix in prefixes])
            if importing and all(name in console_commands for name in importing.values()):
                result.add(
                    id="console-command-optional",
                    category="dependencies",
                    severity="info",
                    classification="SAFE",
                    confidence="HIGH",
                    explanation="Every class that uses Console Commands' API is registered in data/console/commands.csv, which only Console Commands reads, so the classes load only when it is installed. An optional integration; no dependency needed.",
                    evidence=sorted(importing)[:10],
                )
                continue
        if imports:
            first_file: str | None = None
            first_line: int | None = None
            if import_locations:
                locations = [import_locations[name] for name in imports if name in import_locations]
                if locations:
                    first_file, first_line = min(locations, key=lambda loc: (loc[0], loc[1] if loc[1] is not None else -1))
            evidence = [dependency, *imports]
            if first_line is not None:
                evidence.append(f"line:{first_line}")
            result.add(
                id="external-mod-api-import",
                category="dependencies",
                severity="high",
                classification="MANUAL",
                confidence="DETERMINISTIC",
                explanation=f"Source imports {dependency}'s API directly. Compile and runtime compatibility require that optional mod, or an explicit source-level compatibility shim/removal.",
                file=first_file,
                evidence=evidence,
            )


def _custom_ui_plugins_missing_button_callback(text: str) -> int:
    """Return plugin blocks that lack the 0.98a button callback.

    This is deliberately brace-aware rather than file-wide: an anonymous
    plugin can be missing the callback even when another implementation in the
    same source file defines one. Java parsing is not required for this narrow
    structural check, and an unmatched brace simply leaves that block for
    manual review.
    """
    missing = 0
    for match in CUSTOM_UI_PLUGIN_PATTERN.finditer(text):
        opening = match.end() - 1 if text[match.end() - 1] == "{" else text.find("{", match.end())
        if opening < 0:
            missing += 1
            continue
        depth = 0
        closing = -1
        for index in range(opening, len(text)):
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
                if depth == 0:
                    closing = index
                    break
        block = text[opening: closing + 1] if closing >= 0 else text[opening:]
        if not re.search(r"\bbuttonPressed\s*\(", block):
            missing += 1
    return missing


MISSION_REQUIRED_FILES = ("descriptor.json", "MissionDefinition.java", "mission_text.txt")


def _scan_mission_required_files(root: Path, result: ScanResult) -> None:
    """Every mission in mission_list.csv needs the files vanilla missions all ship (live bug PRB-MISSION-01).

    The game loads them when the Missions screen opens, so a missing one is a `Fatal: Error loading
    [data/missions/<id>/mission_text.txt]` dialog at startup, never a log line. An `icon` declared in
    descriptor.json must exist too.
    """
    mission_list = root / "data" / "missions" / "mission_list.csv"
    if not mission_list.is_file():
        return
    try:
        with mission_list.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle))
    except (OSError, csv.Error, UnicodeDecodeError):
        return
    mission_ids = [row[0].strip() for row in rows[1:] if row and row[0].strip() and not row[0].strip().startswith("#")]
    # Many mods compile MissionDefinition into their jar instead of shipping the loose .java (SEEKER's
    # missions ran live that way), so a compiled data/missions/<id>/MissionDefinition.class counts.
    compiled_entries: set[str] = set()
    for jar in _loaded_mod_jars(root):
        try:
            with zipfile.ZipFile(jar) as archive:
                compiled_entries.update(name for name in archive.namelist() if name.startswith("data/missions/"))
        except (OSError, zipfile.BadZipFile):
            continue
    for mission_id in mission_ids:
        mission_dir = root / "data" / "missions" / mission_id
        if not mission_dir.is_dir():
            result.add(
                id="mission-required-file-missing",
                category="missions",
                severity="high",
                classification="MANUAL",
                confidence="DETERMINISTIC",
                explanation="mission_list.csv lists this mission but the mod has no data/missions/<id>/ folder. Unless the id is a vanilla mission, the game shows a Fatal dialog when it loads the mission list.",
                file=_relative(root, mission_list),
                evidence=[f"mission:{mission_id}", "missing: folder"],
            )
            continue
        missing = [name for name in MISSION_REQUIRED_FILES if not (mission_dir / name).is_file()]
        if "MissionDefinition.java" in missing and f"data/missions/{mission_id}/MissionDefinition.class" in compiled_entries:
            missing.remove("MissionDefinition.java")
        descriptor = _load_lenient_json_file(mission_dir / "descriptor.json") if (mission_dir / "descriptor.json").is_file() else None
        icon = descriptor.get("icon") if isinstance(descriptor, dict) else None
        if isinstance(icon, str) and icon.strip() and not (mission_dir / icon.strip()).is_file():
            missing.append(f"{icon.strip()} (descriptor icon)")
        if missing:
            result.add(
                id="mission-required-file-missing",
                category="missions",
                severity="high",
                classification="MANUAL",
                confidence="DETERMINISTIC",
                explanation="A listed mission is missing a file that every vanilla mission ships. The game raises a Fatal dialog (\"Error loading [data/missions/<id>/...] resource, not found\") when it loads the mission list, so the game never reaches the main menu.",
                file=_relative(root, mission_dir),
                evidence=[f"mission:{mission_id}"] + [f"missing:{name}" for name in missing],
            )


LOOSE_SCRIPT_JANINO_PATTERNS = (
    ("typed-for-each", re.compile(r"\bfor\s*\(\s*(?:final\s+)?(?!Object\b)([A-Za-z_][\w.]*(?:\s*<[^>;]*>)?(?:\s*\[\s*\])*)\s+\w+\s*:(?!:)")),
    ("diamond", re.compile(r"\bnew\s+[A-Za-z_][\w.]*\s*<\s*>")),
    ("lambda", re.compile(r"(?:\)|\b[A-Za-z_]\w*)\s*->")),
)


def _scan_loose_script_janino_risk(root: Path, result: ScanResult) -> None:
    """Loose .java under data/ is compiled at runtime by Janino, which ignores generics (live bug PRB-MISSION-02).

    A for-each over a generic collection (element typed as Object -> String), a diamond or a lambda is a
    Fatal dialog before the main menu. Vanilla's 116 loose scripts use none of these; they iterate with
    raw iterators and explicit casts. REVIEW, not MANUAL: a for-each over an array does compile.

    A loose script whose class is also in a loaded jar is never compiled: the game loads the jar class
    and logs "already loaded (perhaps from jar file) ... skipping compilation". Mirfak Parcel Service
    ships both, so those are reported once as shadowed instead of as Janino risks.
    """
    jar_classes = set()
    for _jar, _member, data in _iter_jar_class_files(root):
        info = _parse_class_file(data)
        if info is not None and info.this_class:
            jar_classes.add(info.this_class.replace("/", "."))
    shadowed: list[str] = []
    for source in sorted((root / "data").rglob("*.java")) if (root / "data").is_dir() else []:
        if ".".join(source.relative_to(root).with_suffix("").parts) in jar_classes:
            shadowed.append(_relative(root, source))
            continue
        try:
            text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        evidence: list[str] = []
        for kind, pattern in LOOSE_SCRIPT_JANINO_PATTERNS:
            for match in pattern.finditer(text):
                evidence.append(f"line:{text.count(chr(10), 0, match.start()) + 1}:{kind}")
        if evidence:
            result.add(
                id="loose-script-janino-risk",
                category="scripts",
                severity="high",
                classification="REVIEW",
                confidence="HEURISTIC",
                explanation="This loose script is compiled at runtime by the game's Janino compiler, which ignores generics and predates lambdas. A for-each over a generic collection (the element reads as Object), a diamond <> or a lambda fails to compile, and the game shows a Fatal dialog before the main menu. Rewrite it the way vanilla loose scripts are written: a raw Iterator with explicit casts. A for-each over an array is fine.",
                file=_relative(root, source),
                evidence=sorted(set(evidence), key=lambda item: int(item.split(":")[1]))[:20],
            )
    if shadowed:
        result.add(
            id="loose-script-shadowed-by-jar",
            category="scripts",
            severity="info",
            classification="SAFE",
            confidence="HIGH",
            explanation="These loose scripts have the same class name as a class in the mod's loaded jar. The game loads the jar class and skips compiling the loose copy (starsector.log: 'already loaded (perhaps from jar file) ... skipping compilation'), so their Janino risks don't apply and edits to them have no effect. Change the jar (or its source) instead.",
            evidence=[f"count:{len(shadowed)}", *shadowed[:10]],
        )


def _declared_spec_ids(folder: Path, pattern: str, key: str) -> dict[str, Path]:
    """Spec id -> file, keyed by the id declared inside each file, which is what Starsector registers.

    Filenames often differ from ids (Nightcross's naai_mare_center.wpn declares naai_mare_deco). The
    filename is only a fallback when a file can't be parsed or declares no id.
    """
    specs: dict[str, Path] = {}
    for path in sorted(folder.glob(pattern)):
        declared = None
        try:
            data, _ = _parse_json(path.read_text(encoding="utf-8-sig"))
            declared = data.get(key) if isinstance(data, dict) else None
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            pass
        specs[declared.strip() if isinstance(declared, str) and declared.strip() else path.stem] = path
    return specs


def _scan_core_campaign_plugin_reregistered(root: Path, result: ScanResult) -> None:
    """A mod that registers vanilla's CoreCampaignPluginImpl again (Zorg18's ZorgGen, 2026-09-14).

    Vanilla's own SectorGen already calls sector.registerPlugin(new CoreCampaignPluginImpl()) (RC8
    data/scripts/world/SectorGen.java:168). 0.6-era system templates copied that line into mod
    generators, so every new game gains a second core plugin that is kept in the save. A total
    conversion that replaces SectorGen (Vacuum) legitimately registers it and is skipped.
    """
    if result.metadata.get("totalConversion") in (True, "true", "TRUE"):
        return
    hits: list[str] = []
    for source in sorted(root.rglob("*.java")):
        if "disabled_files" in source.relative_to(root).parts:
            continue
        try:
            text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if "SectorGeneratorPlugin" in text:
            continue
        for match in re.finditer(r"\bregisterPlugin\s*\(\s*new\s+(?:[\w.]+\.)?CoreCampaignPluginImpl\s*\(", text):
            hits.append(f"{_relative(root, source)}:{text.count(chr(10), 0, match.start()) + 1}")
    if hits:
        result.add(
            id="core-campaign-plugin-reregistered",
            category="campaign",
            severity="low",
            classification="REVIEW",
            confidence="HIGH",
            explanation="The mod registers vanilla's CoreCampaignPluginImpl, which vanilla's SectorGen already registers (RC8 SectorGen.java:168). Each new game then carries a duplicate core plugin in its save. It is a leftover from 0.6-era system templates; remove the line unless the mod replaces vanilla sector generation.",
            evidence=hits,
        )


_MEMORY_FLAG_CHECK = re.compile(r"getMemory(?:WithoutUpdate)?\s*\(\s*\)\s*\.\s*(?:getBoolean|contains|is)\s*\(")


def _method_body(text: str, name: str) -> str:
    """Body of the first method called `name` (brace-matched on comment-blanked text), or ''."""
    match = re.search(rf"\b{re.escape(name)}\s*\([^)]*\)\s*(?:throws[^{{]*)?\{{", text)
    if not match:
        return ""
    depth, index = 1, match.end()
    while index < len(text) and depth:
        depth += {"{": 1, "}": -1}.get(text[index], 0)
        index += 1
    return text[match.end(): index - 1]


def _method_body_with_helpers(text: str, name: str) -> str:
    """A method's body plus the bodies of same-class methods it calls (one level), e.g. onNewGame -> initExigency."""
    body = _method_body(text, name)
    extra = []
    for called in sorted(set(re.findall(r"\b([a-z_$][\w$]*)\s*\(", body))):
        if called not in {"if", "for", "while", "switch", "return", "new", "catch", name}:
            extra.append(_method_body(text, called))
    return body + "\n" + "\n".join(extra)


def _scan_system_generation_unguarded(root: Path, result: ScanResult) -> None:
    """Star systems created with no "already generated?" guard (Zorg18, 2026-09-14).

    createStarSystem("X") is safe when some code null-checks getStarSystem("X") or checks a memory flag
    around the generator (Flu-X's plugin does the first; Zorg18 r2 both). Unguarded generation reached
    from onGameLoad creates the system again on every load; from onNewGame it relies on being called
    once per sector. Total conversions and SectorGeneratorPlugin replacements build the whole sector and
    are skipped.
    """
    if result.metadata.get("totalConversion") in (True, "true", "TRUE"):
        return
    texts: dict[Path, str] = {}
    for source in sorted(root.rglob("*.java")):
        if "disabled_files" in source.relative_to(root).parts:
            continue
        try:
            texts[source] = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    plugins = {path: text for path, text in texts.items() if re.search(r"\bextends\s+BaseModPlugin\b", text)}
    hits: list[str] = []
    worst = "low"
    for source, text in texts.items():
        if "SectorGeneratorPlugin" in text:
            continue
        for match in re.finditer(r'\bcreateStarSystem\s*\(\s*"([^"]+)"', text):
            name = match.group(1)
            names = {name, name.lower(), name.replace(" ", "_").lower()}
            guarded = any(_system_lookup_null_guarded(other, candidate) for other in texts.values() for candidate in names)
            class_name = source.stem
            callers = [path for path, body in plugins.items() if re.search(rf"\b{re.escape(class_name)}\b", body)] or ([source] if source in plugins else [])
            if not guarded:
                guarded = bool(_MEMORY_FLAG_CHECK.search(text)) or any(_MEMORY_FLAG_CHECK.search(plugins[path]) for path in callers if path in plugins)
            if guarded:
                continue
            reached = "unknown"
            # Only a generation call counts: Exigency's onGameLoad calls the static Tasserus.getExiHome(),
            # while `new Tasserus().generate(...)` sits in initExigency(), called from onNewGame.
            generates = re.compile(rf"\bnew\s+{re.escape(class_name)}\s*\(|\b{re.escape(class_name)}\s*\.\s*generate\s*\(")
            for path in callers:
                plugin_text = plugins.get(path, "")
                if generates.search(_method_body_with_helpers(plugin_text, "onGameLoad")):
                    reached = "onGameLoad"
                    worst = "medium"
                    break
                if generates.search(_method_body_with_helpers(plugin_text, "onNewGame")):
                    reached = "onNewGame"
            line = text.count("\n", 0, match.start()) + 1
            hits.append(f"{_relative(root, source)}:{line}: {name} (called from {reached})")
    if hits:
        result.add(
            id="system-generation-unguarded",
            category="campaign",
            severity=worst,
            classification="REVIEW",
            confidence="MEDIUM",
            explanation="A star system is created with no check that it already exists (no null check on getStarSystem for it, no memory flag). Called from onGameLoad this duplicates the system on every load; from onNewGame it relies on running exactly once per sector. Add a memory-flag or getStarSystem guard.",
            evidence=hits,
        )


def _system_lookup_null_guarded(text: str, system_name: str) -> bool:
    """True when getStarSystem("<name>") is compared with null, inline or through the variable it's assigned to."""
    call = r'getStarSystem\s*\(\s*"' + re.escape(system_name) + r'"\s*\)'
    if re.search(call + r"\s*[!=]=\s*null|null\s*[!=]=\s*[^;]*" + call, text):
        return True
    for variable in re.findall(r"\b([A-Za-z_$][\w$]*)\s*=\s*[^;=]*" + call, text):
        if re.search(rf"\b{re.escape(variable)}\s*[!=]=\s*null\b|\bnull\s*[!=]=\s*{re.escape(variable)}\b", text):
            return True
    return False


def _scan_campaign_fleet_references(root: Path, result: ScanResult) -> None:
    """Variant and wing ids that campaign code builds fleets from must exist (Zorg18 spawner, 2026-09-14).

    Missions are covered by mission-local-fleet-reference-missing. Campaign spawners often keep ids in
    arrays and pick one at run time, so every string literal with this mod's prefix is checked in any
    source that uses FleetMemberType: "<prefix>..._wing" must be a wing, and a literal that starts with
    one of the mod's hull ids plus "_" must be a variant. A missing one fails only when that fleet spawns.
    """
    mod_id = str(result.metadata.get("id") or "").strip()
    if not mod_id:
        return
    prefix = f"{mod_id}_"
    variants = set(_declared_spec_ids(root / "data" / "variants", "*.variant", "variantId"))
    hulls = set(_declared_spec_ids(root / "data" / "hulls", "*.ship", "hullId"))
    wings = _wing_ids_set(root / "data" / "hulls" / "wing_data.csv")
    if not hulls and not wings:
        return
    missing: list[str] = []
    for source in sorted(root.rglob("*.java")):
        parts = source.relative_to(root).parts
        if "disabled_files" in parts or "missions" in parts:
            continue
        try:
            text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if "FleetMemberType" not in text:
            continue
        for literal in sorted(set(re.findall(r'"(' + re.escape(prefix) + r'[A-Za-z0-9_]+)"', text))):
            if literal in variants or literal in hulls or literal in wings:
                continue
            if literal.endswith("_wing") or any(literal.startswith(hull + "_") for hull in hulls):
                missing.append(f"{_relative(root, source)}: {literal}")
    if missing:
        result.add(
            id="campaign-fleet-reference-missing",
            category="campaign",
            severity="high",
            classification="MANUAL",
            confidence="HIGH",
            explanation="Campaign code builds fleets from a variant or wing id that this mod doesn't define. createFleetMember fails (or the member is skipped) only when that fleet spawns, which can be hours into a game.",
            evidence=missing,
        )


def _scan_mission_local_fleet_references(root: Path, result: ScanResult) -> None:
    mod_id = str(result.metadata.get("id") or "").strip()
    if not mod_id:
        return
    prefix = f"{mod_id}_"
    variants = set(_declared_spec_ids(root / "data" / "variants", "*.variant", "variantId"))
    hulls = set(_declared_spec_ids(root / "data" / "hulls", "*.ship", "hullId"))
    weapons = set(_declared_spec_ids(root / "data" / "weapons", "*.wpn", "id"))
    wing_data = root / "data" / "hulls" / "wing_data.csv"
    wings: set[str] = set()
    if wing_data.is_file():
        try:
            with wing_data.open("r", encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    wing_id = row.get("id")
                    if wing_id:
                        wings.add(wing_id)
        except (OSError, csv.Error, UnicodeDecodeError):
            return
    mission_sources = {
        * (root / "src").glob("data/missions/*/MissionDefinition.java"),
        * (root / "data").glob("missions/*/MissionDefinition.java"),
    }
    references: list[dict[str, str]] = []
    inspected_variants: set[str] = set()
    for source in sorted(mission_sources):
        try:
            text = source.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for fleet_id, member_type in MISSION_FLEET_REFERENCE_PATTERN.findall(text):
            resolution = "external-or-core"
            if fleet_id.startswith(prefix):
                resolution = "resolved-local" if fleet_id in (variants if member_type == "SHIP" else wings) else "missing-local"
            references.append({"file": _relative(root, source), "kind": member_type, "id": fleet_id, "resolution": resolution})
            if not fleet_id.startswith(prefix):
                continue
            expected = variants if member_type == "SHIP" else wings
            if fleet_id not in expected:
                result.add(
                    id="mission-local-fleet-reference-missing",
                    category="missions",
                    severity="high",
                    classification="MANUAL",
                    confidence="DETERMINISTIC",
                    explanation="A mission references a fleet member with this mod's ID prefix, but the corresponding local variant or fighter wing was not found.",
                    file=_relative(root, source),
                    evidence=[f"{member_type}:{fleet_id}", "resolution: missing-local"],
                )
            elif member_type == "SHIP" and fleet_id not in inspected_variants:
                inspected_variants.add(fleet_id)
                _scan_mission_variant_assets(root, result, fleet_id, prefix, hulls, weapons)
    result.migration_context["mission_fleet_references"] = references


def _scan_mission_variant_assets(root: Path, result: ScanResult, variant_id: str, prefix: str, hulls: set[str], weapons: set[str]) -> None:
    path = root / "data" / "variants" / f"{variant_id}.variant"
    try:
        data, _ = _parse_json(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return
    if not isinstance(data, dict):
        return
    hull_id = data.get("hullId")
    if isinstance(hull_id, str) and hull_id.startswith(prefix) and hull_id not in hulls:
        result.add(
            id="mission-local-variant-hull-missing",
            category="missions",
            severity="high",
            classification="MANUAL",
            confidence="DETERMINISTIC",
            explanation="A locally referenced mission variant uses a hull with this mod's ID prefix, but no matching local .ship definition was found.",
            file=_relative(root, path),
            evidence=[f"variant:{variant_id}", f"hull:{hull_id}", "resolution: missing-local"],
        )
    weapon_ids: set[str] = set()
    for group in data.get("weaponGroups", []):
        if not isinstance(group, dict):
            continue
        assigned = group.get("weapons", {})
        if isinstance(assigned, dict):
            weapon_ids.update(value for value in assigned.values() if isinstance(value, str))
    missing_weapons = sorted(weapon_id for weapon_id in weapon_ids if weapon_id.startswith(prefix) and weapon_id not in weapons)
    if missing_weapons:
        result.add(
            id="mission-local-variant-weapon-missing",
            category="missions",
            severity="high",
            classification="MANUAL",
            confidence="DETERMINISTIC",
            explanation="A locally referenced mission variant uses weapon IDs with this mod's prefix, but matching local .wpn definitions were not found.",
            file=_relative(root, path),
            evidence=[f"variant:{variant_id}", *[f"weapon:{weapon_id}" for weapon_id in missing_weapons], "resolution: missing-local"],
        )


def _scan_assets(root: Path, result: ScanResult) -> None:
    for path in root.rglob("*.json"):
        if path.name == "mod_info.json":
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as exc:
            _json_encoding_finding(result, "assets", _relative(root, path), exc)
            continue
        except OSError as exc:
            result.add(id="unreadable-json", category="assets", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation=f"JSON could not be read: {exc}", file=_relative(root, path))
            continue
        try:
            _, tolerances = _parse_json(text)
        except json.JSONDecodeError as exc:
            _unverified_json_syntax_finding(result, "assets", _relative(root, path), exc)
        else:
            _emit_json_tolerance_findings(result, "assets", _relative(root, path), tolerances)
    # Starsector's other JSON-like files: only the trailing-data result is reported here (content
    # after the root never loads); their other tolerances are routine and checked elsewhere.
    for suffix in ("*.faction", "*.ship", "*.skin", "*.variant", "*.wpn", "*.proj", "*.system"):
        for path in root.rglob(suffix):
            try:
                _, tolerances = _parse_json(path.read_text(encoding="utf-8-sig"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            if "trailing-data" in tolerances:
                _json_trailing_data_finding(result, "assets", _relative(root, path), tolerances)
    for path in root.rglob("*.csv"):
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = csv.reader(handle)
                header = next(rows, [])
                if not header or not any(cell.strip() for cell in header):
                    raise ValueError("CSV has no header row")
                for line_number, row in enumerate(rows, start=2):
                    if len(row) <= len(header) or not any(cell.strip() for cell in row):
                        continue
                    # Content beyond the header is a spilled row (loads into the wrong columns). Only
                    # empty trailing cells (spreadsheet padding; Mirfak's hull_mods rows reach 14,726
                    # cells) are ignored by Starsector but rejected by strict tools; that is SAFE to trim.
                    spilled = any(cell.strip() for cell in row[len(header):])
                    result.add(
                        id="csv-row-extra-columns",
                        category="assets",
                        severity="high" if spilled else "low",
                        classification="MANUAL" if spilled else "SAFE",
                        confidence="DETERMINISTIC",
                        explanation=(
                            "A CSV row has more fields than its header. Live revival testing showed that spilled description and hullmod rows can pass superficial parsing but load into the wrong columns; restore the intended row structure from authoritative data."
                            if spilled else
                            "A CSV row has empty cells beyond its header (spreadsheet padding). Starsector ignores them, but strict tools such as Project Go reject the file. `fix csv-row-extra-columns` trims them without changing any value."
                        ),
                        file=_relative(root, path),
                        evidence=[f"line:{line_number}", f"header-columns:{len(header)}", f"row-columns:{len(row)}", *[f"extra:{value}" for value in row[len(header):len(header) + 3]]],
                    )
        except UnicodeDecodeError as exc:
            result.add(id="csv-encoding-unverified", category="assets", severity="medium", classification="REVIEW", confidence="DETERMINISTIC", explanation=f"CSV could not be decoded as UTF-8 ({exc}). Encoding is separate from CSV structure; verify the target loader before conversion.", file=_relative(root, path))
        except (OSError, csv.Error, ValueError) as exc:
            result.add(id="invalid-csv", category="assets", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation=f"CSV could not be read: {exc}", file=_relative(root, path))
    _scan_wing_roles(root, result)
    _scan_content_graph(root, result)


def _scan_wing_roles(root: Path, result: ScanResult) -> None:
    """Validate the role field that makes a fighter wing loadable by the combat layer."""
    path = root / "data" / "hulls" / "wing_data.csv"
    if not path.is_file():
        return
    relative = _relative(root, path)
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        return
    # RC8's com.fs.starfarer.api.loading.WingRole enum (javap, 2026-09-14): BOMBER, FIGHTER, INTERCEPTOR,
    # ASSAULT, SUPPORT. ASSAULT was wrongly treated as removed; Vacuum's ASSAULT wings load live (VAC-R003).
    allowed = {"FIGHTER", "INTERCEPTOR", "BOMBER", "ASSAULT", "SUPPORT"}
    evidence: list[dict[str, str | int]] = []
    for index, row in enumerate(rows, start=2):
        wing_id = (row.get("id") or "").strip()
        if not wing_id or wing_id.startswith("#"):
            continue
        role = (row.get("role") or "").strip().upper()
        evidence.append({"line": index, "id": wing_id, "role": role})
        if not role:
            result.add(id="fighter-wing-role-missing", category="fighters", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation="A fighter wing has no role in data/hulls/wing_data.csv. Starsector requires a recognized role before the wing can load; choose the intended fighter, interceptor, bomber, or support behavior and runtime-test the wing.", file=relative, evidence=[f"line:{index}", f"wing:{wing_id}"])
        elif role not in allowed:
            result.add(id="fighter-wing-role-invalid", category="fighters", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation="A fighter wing role is not recognized by the target profile. Use a documented role and verify combat behavior; BridgeForge will not guess the intended tactical role.", file=relative, evidence=[f"line:{index}", f"wing:{wing_id}", f"role:{role}", f"allowed:{','.join(sorted(allowed))}"])
    result.migration_context["fighter_wing_roles"] = evidence


def _registered_csv_ids(path: Path) -> set[str] | None:
    if not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = csv.reader(handle)
            header = next(rows, [])
            normalized = [cell.strip().lower() for cell in header]
            if "id" not in normalized:
                return None
            id_index = normalized.index("id")
            registered: set[str] = set()
            for row in rows:
                first_value = next((cell.strip() for cell in row if cell.strip()), "")
                if first_value.startswith("#") or id_index >= len(row):
                    continue
                identifier = row[id_index].strip()
                if identifier:
                    registered.add(identifier)
            return registered
    except (OSError, UnicodeDecodeError, csv.Error):
        return None


def _scan_content_graph(root: Path, result: ScanResult) -> None:
    """Check local spec registrations and value kinds without inferring repairs."""
    weapons_root = root / "data" / "weapons"
    weapon_specs = _declared_spec_ids(weapons_root, "*.wpn", "id")
    registered_weapons = _registered_csv_ids(weapons_root / "weapon_data.csv")
    if registered_weapons is not None:
        for identifier, path in sorted(weapon_specs.items()):
            if identifier in registered_weapons:
                continue
            result.add(
                id="local-weapon-spec-unregistered",
                category="assets",
                severity="high",
                classification="REVIEW",
                confidence="DETERMINISTIC",
                explanation="A local .wpn file has no matching id row in this mod's weapon_data.csv. It may be an intentional override registered by another provider, unused content, or a load error; inspect the merged target registry and boot log before adding data or deleting the spec.",
                file=_relative(root, path),
                evidence=[f"weapon:{identifier}", "local-registration:missing"],
            )

    variants_root = root / "data" / "variants"
    variant_ids = set(_declared_spec_ids(variants_root, "*.variant", "variantId"))
    misplaced: list[dict[str, str]] = []
    for path in sorted(variants_root.glob("*.variant")):
        try:
            data, _ = _parse_json(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        weapon_groups = data.get("weaponGroups", [])
        if not isinstance(weapon_groups, list):
            continue
        for group_index, group in enumerate(weapon_groups):
            if not isinstance(group, dict) or not isinstance(group.get("weapons"), dict):
                continue
            for slot, assigned in sorted(group["weapons"].items()):
                if not isinstance(assigned, str) or assigned not in variant_ids or assigned in weapon_specs:
                    continue
                evidence = {
                    "file": _relative(root, path),
                    "slot": str(slot),
                    "variant": assigned,
                    "group": str(group_index),
                }
                misplaced.append(evidence)
                result.add(
                    id="variant-id-in-weapon-slot",
                    category="assets",
                    severity="critical",
                    classification="MANUAL",
                    confidence="DETERMINISTIC",
                    explanation="A weaponGroups assignment names a local ship variant rather than a local weapon spec. This caused a boot-fatal module-loading error in a real revival; verify that the hull slot is a station module and move the assignment to the target version's modules structure only when the hull evidence confirms it.",
                    file=evidence["file"],
                    evidence=[f"group:{group_index}", f"slot:{slot}", f"variant:{assigned}"],
                )

    result.migration_context["content_graph"] = {
        "local_weapon_specs": sorted(weapon_specs),
        "locally_registered_weapons": sorted(registered_weapons) if registered_weapons is not None else None,
        "local_variants": sorted(variant_ids),
        "variant_ids_in_weapon_slots": misplaced,
        "limitation": "Local registration and value-kind evidence does not establish merged target/provider ownership or intended balance.",
    }


def _source_class_index(root: Path) -> dict[str, str]:
    names: dict[str, str] = {}
    for path in root.rglob("*.java"):
        if "disabled_files" in path.relative_to(root).parts:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        package = re.search(r"^\s*package\s+([\w.]+)\s*;", text, re.M)
        # Comments blanked: "// Only class allowed to import ..." came before Flu-X NexCompat's declaration.
        declared = re.search(r"\b(?:public\s+)?(?:class|interface|enum)\s+(\w+)", _blank_java_comments(text, strings=True))
        if package and declared:
            names[f"{package.group(1)}.{declared.group(1)}"] = _relative(root, path)
    return names


def _scan_configured_class_integrity(root: Path, result: ScanResult) -> None:
    local_classes = _source_class_index(root)
    references: set[str] = set()
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".csv", ".json", ".faction", ".ship", ".variant", ".system"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        references.update(re.findall(r"\bdata(?:\.[A-Za-z_$][\w$]*)+", text))
    # Loose .java under data/ is compiled by the game at load (Janino), so it needs no jar: old mods such
    # as Gekelonians (0.53) ship only loose scripts and were all reported MANUAL (2026-09-14 batch).
    loose = {name for name, relative in local_classes.items() if str(relative).replace("\\", "/").startswith("data/")}
    source_only = sorted(set(local_classes) & references - result.compiled_class_names - loose)
    packaged = sorted(references & result.compiled_class_names)
    unresolved = sorted(references - set(local_classes) - result.compiled_class_names)
    entrypoint_sources = sorted(local_classes[name] for name in set(local_classes) & references)
    result.migration_context["configured_class_integrity"] = {
        "source_class_names": sorted(local_classes),
        "configured_references": sorted(references),
        "source_only": source_only,
        "loose_scripts": sorted(loose & references - result.compiled_class_names),
        "packaged": packaged,
        "unresolved": unresolved,
        "configured_entrypoint_sources": entrypoint_sources,
    }
    for finding in result.findings:
        if finding.file in entrypoint_sources and finding.id in {"runtime-placeholder-unsupported-operation", "campaign-spawn-registration-disabled", "missing-custom-ui-button-pressed-callback", "legacy-custom-dialog-delegate-signature"}:
            finding.evidence.append("reachability: configured-entrypoint")
        elif finding.id == "runtime-placeholder-unsupported-operation":
            finding.evidence.append("reachability: active-source-unconfigured")
    if source_only:
        result.add(id="configured-source-class-missing-from-jar", category="bytecode", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation="Mod data references active local source classes that are absent from every scanned JAR. Compile/package the active sources before runtime testing; this finding does not claim that every unresolved configured class belongs to this mod.", evidence=source_only)


def _scan_campaign_identifier_context(root: Path, result: ScanResult) -> None:
    """Attribute literal campaign lookups without assuming a global ID registry.

    A local definition is deterministic evidence. A mod-ID prefix is only a
    useful hint, so it remains explicitly labeled as such instead of becoming a
    compatibility claim.
    """
    mod_id = str(result.metadata.get("id") or "").strip()
    local_systems: set[str] = set()
    local_entities: set[str] = set()
    for source in root.rglob("*.java"):
        if "disabled_files" in source.relative_to(root).parts:
            continue
        try:
            text = source.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        local_systems.update(CAMPAIGN_SYSTEM_CREATION_PATTERN.findall(text))
        local_entities.update(CAMPAIGN_ENTITY_CREATION_PATTERN.findall(text))

    def ownership(identifier: str, defined: set[str]) -> str:
        if identifier in defined:
            return "defined-locally"
        if mod_id and identifier.startswith(f"{mod_id}_"):
            return "likely-mod-local-prefix"
        return "external-or-core-unresolved"

    lookups: list[dict[str, str]] = []
    for finding in result.findings:
        if finding.id == "hard-coded-campaign-system-reference" and finding.evidence:
            identifier = finding.evidence[0]
            state = ownership(identifier, local_systems)
            finding.evidence.append(f"ownership: {state}")
            lookups.append({"kind": "system", "id": identifier, "ownership": state})
        elif finding.id == "hard-coded-campaign-entity-reference" and finding.evidence:
            identifier = finding.evidence[0]
            state = ownership(identifier, local_entities)
            finding.evidence.append(f"ownership: {state}")
            lookups.append({"kind": "entity", "id": identifier, "ownership": state})
    result.migration_context["campaign_identifier_context"] = {
        "defined_system_ids": sorted(local_systems),
        "defined_entity_ids": sorted(local_entities),
        "lookups": lookups,
    }


def _annotate_source_reachability(root: Path, result: ScanResult) -> None:
    """Resolve only unambiguous local class-qualified calls from configured roots."""
    integrity = result.migration_context.get("configured_class_integrity", {})
    entrypoints = set(integrity.get("configured_entrypoint_sources", []))
    source_index = _source_class_index(root)
    by_simple_name: dict[str, set[str]] = {}
    for class_name, file in source_index.items():
        by_simple_name.setdefault(class_name.rsplit(".", 1)[-1], set()).add(file)
    calls: dict[str, list[str]] = {}
    for fact in result.source_facts:
        if fact.get("kind") == "call_edge":
            calls.setdefault(str(fact["file"]), []).append(str(fact["value"]))
    reachable = set(entrypoints)
    pending = list(sorted(entrypoints))
    resolved_edges: list[dict[str, str]] = []
    uncertain_edges = 0
    while pending:
        source = pending.pop()
        for edge in calls.get(source, []):
            _, _, select = edge.partition("->")
            receiver, separator, _ = select.partition(".")
            candidates = by_simple_name.get(receiver, set()) if separator else set()
            if len(candidates) != 1:
                uncertain_edges += 1
                continue
            target = next(iter(candidates))
            resolved_edges.append({"from": source, "to": target, "call": select})
            if target not in reachable:
                reachable.add(target)
                pending.append(target)
    result.migration_context["source_reachability"] = {
        "configured_entrypoint_sources": sorted(entrypoints),
        "reachable_local_sources": sorted(reachable),
        "resolved_local_edges": sorted(resolved_edges, key=lambda item: (item["from"], item["to"], item["call"])),
        "uncertain_call_edge_count": uncertain_edges,
        "limitation": "Only unambiguous local class-qualified calls are followed; unqualified, instance, inherited, reflective, and dependency calls remain unresolved.",
    }
    tracked = {"runtime-placeholder-unsupported-operation", "campaign-spawn-registration-disabled", "missing-custom-ui-button-pressed-callback", "legacy-custom-dialog-delegate-signature"}
    for finding in result.findings:
        if finding.id not in tracked or not finding.file:
            continue
        if finding.file in entrypoints and "reachability: configured-entrypoint" not in finding.evidence:
            finding.evidence.append("reachability: configured-entrypoint")
        elif finding.file in reachable and "reachability: reachable-local-call" not in finding.evidence:
            finding.evidence.append("reachability: reachable-local-call")


def _attribute_library_usage(result: ScanResult) -> None:
    dependencies = " ".join(map(str, result.metadata.get("dependencies") or result.metadata.get("requiredDependencies") or [])).lower()
    calls = [fact.get("value", "") for fact in result.source_facts if fact.get("kind") == "method_invocation"]
    for library, prefixes in LIBRARY_PACKAGES.items():
        imports = [item for item in result.imports if any(item.startswith(prefix) for prefix in prefixes)]
        simple_names = {item.rsplit(".", 1)[-1] for item in imports if not item.endswith(".*")}
        source_calls = [call for call in calls if call.split(".", 1)[0] in simple_names]
        bundled = any(LIBRARY_PATTERNS[library].search(str(item.get("path", ""))) for item in result.jars)
        declared = library.lower() in dependencies or library.replace("Lib", "").lower() in dependencies
        bytecode_referenced = library in result.bytecode_library_references
        if declared or bundled or imports:
            result.library_usage.append({"library": library, "declared": declared, "bundled": bundled, "imported": bool(imports), "source_called": bool(source_calls), "bytecode_referenced": bytecode_referenced, "evidence": {"imports": imports, "source_calls": source_calls}})
            if declared and not bundled and not imports:
                result.add(id="declared-library-unreferenced", category="dependencies", severity="medium", classification="REVIEW", confidence="DETERMINISTIC", explanation="A declared library has no bundled, import, or source-call evidence. Confirm whether it is required before removing or changing it.", evidence=[library])
            if imports and not declared and not bundled and not bytecode_referenced and _library_import_only(Path(result.input_path), result, [prefix.replace(".", "/") for prefix in prefixes]):
                pass  # an unused import compiled away; reported once as library-import-unused-in-jar
            elif imports and not declared and not bundled:
                result.add(
                    id="source-library-dependency-undeclared",
                    category="dependencies",
                    severity="high",
                    classification="REVIEW",
                    confidence="DETERMINISTIC",
                    explanation=f"Source imports {library}, but mod_info.json does not declare it and no bundled {library} JAR was found. Determine whether the library is mandatory or an optional integration before changing metadata or source.",
                    file="mod_info.json",
                    evidence=[library, *imports],
                )


def _dependency_compatibility_context(result: ScanResult) -> None:
    """Record dependency evidence without guessing API replacements or versions."""
    raw_declared = result.metadata.get("dependencies") or result.metadata.get("requiredDependencies") or []
    declared: list[dict[str, str | None]] = []
    normalized: set[str] = set()
    for item in raw_declared:
        if isinstance(item, dict):
            dependency_id = str(item.get("id") or "").strip() or None
            dependency_name = str(item.get("name") or "").strip() or None
        else:
            dependency_id = str(item).strip() or None
            dependency_name = None
        declared.append({"id": dependency_id, "name": dependency_name})
        normalized.update(re.sub(r"[^a-z0-9]", "", value.lower()) for value in (dependency_id, dependency_name) if value)
    direct_apis: list[dict[str, object]] = []
    for finding in result.findings:
        if finding.id != "external-mod-api-import" or not finding.evidence:
            continue
        dependency = finding.evidence[0]
        key = re.sub(r"[^a-z0-9]", "", dependency.lower())
        finding_imports = [item for item in finding.evidence[1:] if not item.startswith("line:")]
        direct_apis.append({"dependency": dependency, "declared": key in normalized, "imports": finding_imports})
    result.migration_context["dependency_compatibility"] = {
        "declared_dependencies": declared,
        "direct_api_dependencies": direct_apis,
        "library_usage": result.library_usage,
        "limitation": "Static evidence does not establish an installed dependency version or API-symbol compatibility.",
    }


def _infer_environment(result: ScanResult) -> None:
    majors = [major for jar in result.jars for major in jar.get("class_file_majors", [])]
    if majors:
        result.estimated_java = _java_for_major(max(majors))
        if max(majors) > 61:
            result.add(id="target-bytecode-exceeds-profile", category="java", severity="high", classification="REVIEW", confidence="DETERMINISTIC", explanation=f"Detected {_java_for_major(max(majors))} bytecode exceeds target Java {result.target.java}.")
    if result.estimated_starsector == "UNKNOWN":
        result.add(id="version-inference-blocked", category="environment", severity="medium", classification="UNKNOWN", confidence="DETERMINISTIC", explanation="No trustworthy declared Starsector version was available. Do not make confident compatibility or migration claims until metadata or independent target evidence is supplied.")


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


def _is_mission_source(root: Path, path: Path) -> bool:
    parts = path.relative_to(root).parts
    if "data" in parts:
        index = parts.index("data")
        if index + 1 < len(parts) and parts[index + 1] == "missions":
            return True
    return False


def _scan_procgen_rows(root: Path, result: ScanResult, vanilla_core: Path | None) -> None:
    """Every campaign-placed planets.json type needs a procgen CSV row (crash if absent)."""
    planets_path = root / "data" / "config" / "planets.json"
    data = _load_lenient_json_file(planets_path)
    if not isinstance(data, dict):
        return

    campaign_ids_used: dict[str, list[str]] = {}
    mission_ids_used: set[str] = set()
    jar_present = bool(list(root.rglob("*.jar")))
    for source in root.rglob("*.java"):
        try:
            text = source.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        literals = set(re.findall(r'"([A-Za-z0-9_]+)"', text))
        matched = literals & data.keys()
        if not matched:
            continue
        if _is_mission_source(root, source):
            mission_ids_used.update(matched)
        else:
            relative = _relative(root, source)
            for type_id in matched:
                campaign_ids_used.setdefault(type_id, []).append(relative)

    star_csv = root / "data" / "campaign" / "procgen" / "star_gen_data.csv"
    planet_csv = root / "data" / "campaign" / "procgen" / "planet_gen_data.csv"
    mod_star_ids = _csv_first_column_ids(star_csv)
    mod_planet_ids = _csv_first_column_ids(planet_csv)
    vanilla_star_ids: set[str] = set()
    vanilla_planet_ids: set[str] = set()
    vanilla_note: str | None = None
    if vanilla_core is not None:
        vanilla_star_ids = _csv_first_column_ids(vanilla_core / "data" / "campaign" / "procgen" / "star_gen_data.csv")
        vanilla_planet_ids = _csv_first_column_ids(vanilla_core / "data" / "campaign" / "procgen" / "planet_gen_data.csv")
    else:
        vanilla_note = "vanilla-core:unavailable; vanilla-row exemption could not be checked"

    for type_id in sorted(campaign_ids_used):
        spec = data.get(type_id)
        is_star = bool(isinstance(spec, dict) and spec.get("isStar"))
        registered = mod_star_ids if is_star else mod_planet_ids
        vanilla_registered = vanilla_star_ids if is_star else vanilla_planet_ids
        if type_id in registered or type_id in vanilla_registered:
            continue
        csv_relative = "data/campaign/procgen/star_gen_data.csv" if is_star else "data/campaign/procgen/planet_gen_data.csv"
        spec_class = "StarGenDataSpec" if is_star else "PlanetGenDataSpec"
        used_files = sorted(set(campaign_ids_used[type_id]))
        evidence = [f"type:{type_id}", f"isStar:{is_star}", f"missing-row-in:{csv_relative}", *[f"used-in:{f}" for f in used_files[:5]]]
        if jar_present:
            evidence.append("class-file-constant-strings:not-scanned (java sources only)")
        if vanilla_note:
            evidence.append(vanilla_note)
        result.add(
            id="procgen-star-row-missing" if is_star else "procgen-planet-row-missing",
            category="campaign",
            severity="critical",
            classification="REVIEW",
            confidence="HIGH",
            explanation=(
                f"data/config/planets.json defines '{type_id}' and it is used from campaign code, but no row "
                f"with that id exists in {csv_relative} (locally or in vanilla). StarSystem."
                "autogenerateHyperspaceJumpPoints -> PlanetConditionGenerator throws a fatal "
                f"'Spec of class [...{spec_class}] with id [{type_id}] not found' during new-game generation. "
                "Clone the closest vanilla row, rename its id, and set the frequency columns "
                "(frequency for planets; freqYOUNG/freqAVERAGE/freqOLD for stars) to 0 if it should not be "
                "randomly generated."
            ),
            file=_relative(root, planets_path),
            evidence=evidence,
        )


def _vanilla_faction_ids(vanilla_core: Path) -> set[str]:
    ids: set[str] = set()
    faction_dir = vanilla_core / "data" / "world" / "factions"
    if not faction_dir.is_dir():
        return ids
    for path in faction_dir.glob("*.faction"):
        data = _load_lenient_json_file(path)
        if isinstance(data, dict):
            faction_id = data.get("id")
            if isinstance(faction_id, str) and faction_id:
                ids.add(faction_id)
    return ids


_RULES_MERGED_CONDITION = re.compile(r"[A-Za-z0-9_)]\$[A-Za-z_]")
_RULES_FACTION_ID_CONDITION = re.compile(r"\$faction\.id\s*==\s*([A-Za-z0-9_]+)")


def _scan_rules_condition_defects(root: Path, result: ScanResult, vanilla_core: Path | None) -> None:
    """rules.csv conditions that can never match as written (Flu-X greetings, found 2026-09-13).

    Each condition is its own line in the cell. "$faction.id == infected$faction.hostileToPlayer" lost its
    line break, so it compares the id with that whole string and the rule never fires (vanilla RC8: 0 of
    11107 rules have a variable glued to a preceding word). A `$faction.id ==` naming a faction neither
    vanilla nor the mod defines is usually copy-paste (Flu-X's "greetinginfectedTOffWeaker" tests
    templars); it can also be a deliberate cross-mod integration, hence REVIEW.
    """
    rules = root / "data" / "campaign" / "rules.csv"
    try:
        with rules.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
            rows = [row for row in csv.DictReader(handle) if not (row.get("id") or "").lstrip().startswith("#")]
    except OSError:
        return
    merged: list[str] = []
    faction_refs: list[tuple[str, str]] = []
    for row in rows:
        rule_id = (row.get("id") or "").strip() or "<no id>"
        conditions = row.get("conditions") or ""
        for line in conditions.splitlines():
            if _RULES_MERGED_CONDITION.search(line):
                merged.append(f"rule:{rule_id}: {line.strip()}")
        faction_refs.extend((rule_id, faction) for faction in _RULES_FACTION_ID_CONDITION.findall(conditions))
    relative = _relative(root, rules)
    if merged:
        result.add(
            id="rules-condition-merged-lines",
            category="rules",
            severity="medium",
            classification="REVIEW",
            confidence="DETERMINISTIC",
            explanation="A rules.csv condition has a variable glued to the previous word, so two conditions lost their line break and the rule compares against the joined string: it never fires as written. Fixing it changes live behaviour (the rule starts firing), so treat it as a decision, not a cleanup.",
            file=relative,
            evidence=merged,
        )
    if vanilla_core is None or not faction_refs:
        return
    known = _vanilla_faction_ids(vanilla_core)
    for path in (root / "data" / "world" / "factions").glob("*.faction"):
        data = _load_lenient_json_file(path)
        known.add(data["id"] if isinstance(data, dict) and isinstance(data.get("id"), str) else path.stem)
    unknown = sorted({f"rule:{rule_id} -> {faction}" for rule_id, faction in faction_refs if faction not in known})
    if unknown:
        result.add(
            id="rules-condition-unknown-faction",
            category="rules",
            severity="medium",
            classification="REVIEW",
            confidence="HIGH",
            explanation="A rules.csv condition tests $faction.id against a faction that neither vanilla nor this mod defines. Usually a copy-paste from another mod (the rule never fires for the intended faction and shows its text to the other one); confirm it is not a deliberate integration before changing it.",
            file=relative,
            evidence=unknown,
        )


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
        result.add(id="player-text-non-english", category="localization", severity="low", classification="REVIEW", confidence="DETERMINISTIC", explanation=f"{len(counts)} data file(s) hold CJK text outside comments ({sum(counts.values())} characters). Translate with translate-export / translate-apply before English live tests; translate-check also covers jar strings.", evidence=[f"{path}: {count}" for path, count in counts.most_common(15)] + ([f"... {len(counts) - 15} more file(s)"] if len(counts) > 15 else []))


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


def _scan_faction_known_lists(root: Path, result: ScanResult, vanilla_core: Path | None) -> None:
    """A new faction missing known* lists gets silently empty markets/fleets since 0.8a."""
    faction_dir = root / "data" / "world" / "factions"
    if not faction_dir.is_dir():
        return
    vanilla_ids: set[str] | None = _vanilla_faction_ids(vanilla_core) if vanilla_core is not None else None
    for path in sorted(faction_dir.glob("*.faction")):
        data = _load_lenient_json_file(path)
        if not isinstance(data, dict):
            # Never skip silently: an unchecked faction file must not read as a clean one.
            result.add(
                id="faction-file-unparsed",
                category="factions",
                severity="medium",
                classification="UNKNOWN",
                confidence="DETERMINISTIC",
                explanation="BridgeForge's legacy-JSON parser could not read this faction file, so the known-lists check did not run on it. This is not proof the game rejects the file; inspect it manually.",
                file=_relative(root, path),
            )
            continue
        faction_id = data.get("id")
        if not isinstance(faction_id, str) or not faction_id:
            continue
        if vanilla_ids is not None and faction_id in vanilla_ids:
            continue
        missing = [key for key in ("knownShips", "knownWeapons", "knownFighters") if not data.get(key)]
        if not missing:
            continue
        ship_roles = data.get("shipRoles")
        role_variant_count = 0
        if isinstance(ship_roles, dict):
            for block in ship_roles.values():
                if isinstance(block, dict):
                    role_variant_count += sum(1 for key in block if key not in FACTION_SPECIAL_ROLE_KEYS)
        evidence = [f"missing:{','.join(missing)}", f"shipRoles-present:{isinstance(ship_roles, dict)}", f"role-variant-keys:{role_variant_count}"]
        if vanilla_ids is None:
            evidence.append("vanilla-faction-list:unavailable; merge-fragment exemption could not be checked")
        # Zorg18 (2026-09-14): no markets, no shipRoles, fleets assembled member by member. Nothing reads
        # its known lists, so HIGH overstated it. Keep HIGH whenever market use can't be ruled out.
        market_use = _faction_market_evidence(root, faction_id)
        unused = role_variant_count == 0 and market_use == "none"
        evidence.append(f"market-evidence:{market_use}")
        result.add(
            id="faction-known-lists-missing",
            category="factions",
            severity="low" if unused else "high",
            classification="REVIEW",
            confidence="HIGH",
            explanation=(
                "This faction is missing one or more of knownShips/knownWeapons/knownFighters. Since 0.8a, "
                "market stocking (BaseSubmarketPlugin.addWeapons/addFighters/addShips) and fleet generation "
                "(FleetFactoryV3) only draw from a faction's known lists, so a missing list silently produces "
                "empty market stock or empty fleets instead of an error."
                + (" This faction has no shipRoles and no market was found in its data or sources, so nothing obvious reads the lists; add them if it gains markets, FleetFactoryV3 fleets or a Nexerelin config." if unused else "")
            ),
            file=_relative(root, path),
            evidence=evidence,
        )


def _faction_market_evidence(root: Path, faction_id: str) -> str:
    """'found' when the faction owns or configures a market, 'none' when sources rule it out, else 'unknown'."""
    quoted = f'"{faction_id}"'
    econ = root / "data" / "campaign" / "econ"
    for path in econ.rglob("*.json") if econ.is_dir() else []:
        data = _load_lenient_json_file(path)
        if isinstance(data, dict) and data.get("faction") == faction_id:
            return "found"
    if (root / "data" / "config" / "exerelinFactionConfig" / f"{faction_id}.json").is_file():
        return "found"
    sources = [path for path in root.rglob("*.java") if "disabled_files" not in path.relative_to(root).parts]
    for path in sources:
        try:
            text = _blank_java_comments(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if quoted in text and re.search(r"\b(?:setFactionId|createMarket|addMarket|createEmptyFleet|createFleet)\s*\(", text):
            if re.search(r"\b(?:setFactionId|createMarket|addMarket)\s*\(", text):
                return "found"
    # Shipped jars often differ from bundled sources, so the bytecode is checked too: a class holding the
    # faction id as a string constant and calling a market-ownership method.
    has_classes = False
    for _jar, _member, data in _iter_jar_class_files(root):
        has_classes = True
        info = _parse_class_file(data)
        if info is None or faction_id not in (info.string_constants or set()):
            continue
        if {"setFactionId", "createMarket", "addMarket"} & set(info.utf8_values or ()):
            return "found"
    # Compiled code without any sources could still build markets in ways we can't read.
    return "unknown" if has_classes and not sources else "none"


def _scan_shiproles(root: Path, result: ScanResult, vanilla_core: Path | None) -> None:
    """0.8a carrier rework: shipRoles keys must be variant ids, not wing ids or fighter-role names."""
    faction_dir = root / "data" / "world" / "factions"
    if not faction_dir.is_dir():
        return
    wing_ids = _wing_ids_set(root / "data" / "hulls" / "wing_data.csv")
    if vanilla_core is not None:
        wing_ids |= _wing_ids_set(vanilla_core / "data" / "hulls" / "wing_data.csv")
    for path in sorted(faction_dir.glob("*.faction")):
        data = _load_lenient_json_file(path)
        if not isinstance(data, dict):
            continue
        ship_roles = data.get("shipRoles")
        if not isinstance(ship_roles, dict):
            continue
        relative = _relative(root, path)
        for role_name, block in sorted(ship_roles.items()):
            if role_name.lower() in OBSOLETE_FIGHTER_ROLE_NAMES:
                result.add(
                    id="shiproles-obsolete-fighter-role",
                    category="factions",
                    severity="medium",
                    classification="REVIEW",
                    confidence="HIGH",
                    explanation="This shipRoles block name (interceptor/fighter/bomber) was removed in the 0.8a carrier rework; its entries are not used by 0.98a fleet generation.",
                    file=relative,
                    evidence=[f"role:{role_name}"],
                )
            if not isinstance(block, dict):
                continue
            for key in sorted(block):
                if key in FACTION_SPECIAL_ROLE_KEYS:
                    continue
                if key.endswith("_wing") or key in wing_ids:
                    result.add(
                        id="shiproles-wing-id",
                        category="factions",
                        severity="critical",
                        classification="MANUAL",
                        confidence="HIGH",
                        explanation="0.98a resolves every shipRoles entry through a variant-only lookup. This key looks like a fighter wing id (the pre-0.8a convention), which is fatal at load rather than being ignored.",
                        file=relative,
                        evidence=[f"role:{role_name}", f"key:{key}"],
                    )


def _scan_carrier_rework_gap(root: Path, result: ScanResult) -> None:
    """ship_data/wing_data structural symptoms of the 0.8a carrier rework."""
    ship_data_path = root / "data" / "hulls" / "ship_data.csv"
    wing_data_path = root / "data" / "hulls" / "wing_data.csv"
    ship_rows: list[dict[str, str]] = []
    if ship_data_path.is_file():
        header = _csv_header(ship_data_path)
        if header is not None:
            normalized = [cell.strip().lower() for cell in header]
            if "fighter bays" not in normalized:
                result.add(
                    id="ship-data-missing-fighter-bays-column",
                    category="hulls",
                    severity="high",
                    classification="REVIEW",
                    confidence="DETERMINISTIC",
                    explanation="data/hulls/ship_data.csv has no 'fighter bays' column. This mod predates the 0.8a carrier rework; every carrier hull will silently load with 0 fighter bays.",
                    file=_relative(root, ship_data_path),
                    evidence=[f"columns:{len(header)}"],
                )
        ship_rows = _read_csv_rows(ship_data_path) or []

    variant_wings_by_hull: dict[str, bool] = {}
    variants_root = root / "data" / "variants"
    if variants_root.is_dir():
        for path in variants_root.rglob("*.variant"):
            data = _load_lenient_json_file(path)
            if not isinstance(data, dict):
                continue
            hull_id = data.get("hullId")
            if not isinstance(hull_id, str) or not hull_id:
                continue
            wings = data.get("wings")
            has_wings = isinstance(wings, list) and len(wings) > 0
            variant_wings_by_hull[hull_id] = variant_wings_by_hull.get(hull_id, False) or has_wings

    if wing_data_path.is_file():
        header = _csv_header(wing_data_path)
        if header is not None:
            normalized = [cell.strip().lower() for cell in header]
            if "role desc" not in normalized:
                result.add(
                    id="wing-data-missing-role-desc-column",
                    category="hulls",
                    severity="critical",
                    classification="MANUAL",
                    confidence="DETERMINISTIC",
                    explanation="data/hulls/wing_data.csv has no 'role desc' column, which the 0.98a loader requires; the file fails to load.",
                    file=_relative(root, wing_data_path),
                    evidence=[f"columns:{len(header)}"],
                )
        for index, row in enumerate(_read_csv_rows(wing_data_path) or [], start=2):
            wing_id = (row.get("id") or "").strip()
            if not wing_id or wing_id.startswith("#"):
                continue
            # `wing-role-assault-removed` retired 2026-09-14: ASSAULT is still a valid RC8 WingRole, and
            # rewriting it to FIGHTER silently changed the wing's AI behaviour.
            op_cost = (row.get("op cost") or "").strip()
            if not op_cost:
                result.add(
                    id="wing-op-cost-blank",
                    category="hulls",
                    severity="medium",
                    classification="REVIEW",
                    confidence="DETERMINISTIC",
                    explanation="This wing_data.csv row has a blank 'op cost' value.",
                    file=_relative(root, wing_data_path),
                    evidence=[f"line:{index}", f"wing:{wing_id}"],
                )

    for row in ship_rows:
        hull_id = (row.get("id") or "").strip()
        if not hull_id or hull_id.startswith("#"):
            continue
        hints = (row.get("hints") or "").upper()
        if "CARRIER" not in hints:
            continue
        bays_raw = (row.get("fighter bays") or "").strip()
        try:
            bays = int(float(bays_raw)) if bays_raw else 0
        except ValueError:
            bays = 0
        has_wings = variant_wings_by_hull.get(hull_id, False)
        if bays <= 0 and not has_wings:
            result.add(
                id="carrier-without-bays-or-wings",
                category="hulls",
                severity="high",
                classification="REVIEW",
                confidence="HIGH",
                explanation="This hull is tagged CARRIER in ship_data.csv hints but has 0/absent fighter bays and none of its variants declare a non-empty wings array, so it cannot deploy fighters.",
                file=_relative(root, ship_data_path),
                evidence=[f"hull:{hull_id}", f"fighter-bays:{bays_raw or '0'}", f"variants-with-wings:{has_wings}"],
            )


def _scan_black_hole_flag(root: Path, result: ScanResult) -> None:
    planets_path = root / "data" / "config" / "planets.json"
    data = _load_lenient_json_file(planets_path)
    if not isinstance(data, dict):
        return
    for type_id, spec in sorted(data.items()):
        if not isinstance(spec, dict) or not spec.get("isStar") or spec.get("isBlackHole"):
            continue
        name = str(spec.get("name") or "")
        texture = str(spec.get("texture") or "")
        if not (BLACK_HOLE_HINT_PATTERN.search(type_id) or BLACK_HOLE_HINT_PATTERN.search(name) or BLACK_HOLE_HINT_PATTERN.search(texture)):
            continue
        result.add(
            id="black-hole-type-missing-flag",
            category="campaign",
            severity="low",
            classification="REVIEW",
            confidence="HIGH",
            explanation="This star type's id/name/texture indicates a black hole, but isBlackHole:true is not set, so 0.98a renders it as a plain star instead of a black hole.",
            file=_relative(root, planets_path),
            evidence=[f"type:{type_id}", f"name:{name}", f"texture:{texture}"],
        )


def _base_game_version(version: str) -> str:
    """'0.98a-RC8' -> '0.98a'. The launcher accepts any RC of the same base version."""
    return re.sub(r"-RC\d+$", "", version.strip(), flags=re.I).lower()


def _version_series(version: str) -> str:
    """'0.98a-RC8' -> '0.98', '0.9.1a' -> '0.9.1', '0.98.x' -> '0.98'."""
    base = _base_game_version(version)
    return re.sub(r"(?:\.x|[a-z]+)$", "", base)


def _scan_mod_info_game_version(result: ScanResult) -> None:
    target_version = result.target.starsector
    declared = result.declared_starsector
    if not target_version or not declared or declared == target_version:
        return
    # A generic target ('0.98.x', the default) used to skip this check entirely, so the 2026-09-14 batch
    # of 0.53a-0.9.1a mods never heard that the launcher would untick every one of them.
    if not GAME_VERSION_RC_PATTERN.match(target_version):
        if not re.fullmatch(r"\d+(?:\.\d+)*\.x", target_version.strip()) or _version_series(declared) == _version_series(target_version):
            return
        target_version = f"{_version_series(target_version)}a"
    # The launcher matches on the BASE version: mods declaring 0.98a-RC5 / 0.98a-RC7 loaded and ran
    # all week in an RC8 rig (LazyLib, LunaLib, Console Commands, MagicLib), so an older RC is fine.
    if _base_game_version(declared) == _base_game_version(target_version):
        return
    result.add(
        id="mod-info-game-version-inexact",
        category="metadata",
        severity="high",
        classification="REVIEW",
        confidence="DETERMINISTIC",
        explanation=f"mod_info.json gameVersion ('{declared}') targets a different base game version than the configured target ({target_version}). The Starsector launcher unchecks a mod whose base version differs. An older release candidate of the same version (e.g. 0.98a-RC5 on RC8) is accepted, so only the base version matters.",
        file="mod_info.json",
        evidence=[f"declared:{declared}", f"target:{target_version}"],
    )


VANILLA_SHADOW_GROUP_THRESHOLD = 5


def _scan_vanilla_path_shadowing(root: Path, result: ScanResult, vanilla_core: Path | None) -> None:
    if vanilla_core is None:
        return
    data_root = root / "data"
    if not data_root.is_dir():
        return
    mod_info = _load_lenient_json_file(root / "mod_info.json")
    total_conversion = isinstance(mod_info, dict) and mod_info.get("totalConversion") is True
    shadowed: dict[str, list[tuple[Path, Path]]] = {}
    for path in data_root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SHADOW_PATH_EXTENSIONS:
            continue
        relative = path.relative_to(root)
        vanilla_path = vanilla_core / relative
        if not vanilla_path.is_file():
            continue
        try:
            mod_bytes = path.read_bytes()
            vanilla_bytes = vanilla_path.read_bytes()
        except OSError:
            continue
        if mod_bytes == vanilla_bytes:
            continue
        shadowed.setdefault(_relative(root, path.parent), []).append((path, vanilla_path))
    severity = "low" if total_conversion else "critical"
    classification = "REVIEW" if total_conversion else "MANUAL"
    for folder, files in sorted(shadowed.items()):
        # A rebalance that replaces a whole vanilla folder (Xenoargh's Rebal: 498 hullmod/weapon scripts)
        # reads as one decision, not hundreds of findings burying the rest of the report.
        if len(files) > VANILLA_SHADOW_GROUP_THRESHOLD:
            listed = sorted(_relative(root, path) for path, _vanilla in files)
            result.add(
                id="vanilla-path-shadowing",
                category="assets",
                severity=severity,
                classification=classification,
                confidence="DETERMINISTIC",
                explanation=f"{len(files)} files in this folder shadow vanilla files at the same data-relative paths with different bytes. Confirm the override is intentional (a rebalance mod does this on purpose); every shadow replaces core game content, and old copies of vanilla scripts can break against the current API.",
                file=folder,
                evidence=[f"count:{len(files)}", *(["mod_info:totalConversion=true"] if total_conversion else []), *listed[:25]],
            )
            continue
        for path, vanilla_path in files:
            evidence = [f"vanilla-path:{vanilla_path.as_posix()}"]
            if total_conversion:
                evidence.append("mod_info:totalConversion=true")
            result.add(
                id="vanilla-path-shadowing",
                category="assets",
                severity=severity,
                classification=classification,
                confidence="DETERMINISTIC",
                explanation=(
                    "This total-conversion mod replaces a vanilla file at the same data-relative path; overrides are expected for a total conversion, so spot-check rather than treat as a defect."
                    if total_conversion
                    else "This mod file shadows a vanilla file at the same data-relative path with different bytes. Confirm the override is intentional; an unintended shadow silently replaces core game content."
                ),
                file=_relative(root, path),
                evidence=evidence,
            )


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

    __slots__ = ("this_class", "referenced_classes", "methods", "super_class", "interfaces", "fields", "string_constants", "utf8_values")

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
        for _ in range(fields_count):
            field_flags, pos = _class_pool_u2(data, pos)
            field_name_index, pos = _class_pool_u2(data, pos)
            field_descriptor_index, pos = _class_pool_u2(data, pos)
            attr_count, pos = _class_pool_u2(data, pos)
            pos = _skip_attributes(data, pos, attr_count)
            fields.append((utf8.get(field_name_index, ""), utf8.get(field_descriptor_index, ""), bool(field_flags & 0x0008), bool(field_flags & 0x0010)))
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
        return _ClassFileInfo(this_class, referenced_classes, methods, super_class, interfaces, fields, string_constants, frozenset(utf8.values()))
    except (IndexError, KeyError, UnicodeDecodeError):
        return None


# Plugins Starsector instantiates once PER WEAPON (or per projectile); a static field is shared by
# every copy in the battle. Live run SK13-1: SEEKER's ART_thrusterRotation kept `static ShipAPI ship`,
# so Vector-cruiser debris spawned mid-battle overwrote it and a living cruiser's flame weapon read a
# ship with no system -> NPE -> Fatal dialog.
PER_WEAPON_PLUGIN_INTERFACES = {
    "com/fs/starfarer/api/combat/EveryFrameWeaponEffectPlugin",
    "com/fs/starfarer/api/combat/EveryFrameWeaponEffectPluginWithAdvanceAfter",
    "com/fs/starfarer/api/combat/OnFireEffectPlugin",
    "com/fs/starfarer/api/combat/OnHitEffectPlugin",
    "com/fs/starfarer/api/combat/WeaponEffectPluginWithInit",
}
COMBAT_STATE_TYPES = ("ShipAPI", "WeaponAPI", "ShipEngineControllerAPI", "ShipSystemAPI", "MissileAPI", "DamagingProjectileAPI", "BeamAPI")
_COMBAT_STATE_DESCRIPTORS = {f"Lcom/fs/starfarer/api/combat/{name};" for name in COMBAT_STATE_TYPES}
_SOURCE_STATIC_STATE = re.compile(r"\bstatic\s+(?!final\b)(?:(?:private|protected|public|volatile|transient)\s+)*(" + "|".join(COMBAT_STATE_TYPES) + r")\s+(\w+)\s*[;=]")


_HULLMOD_BASES = {"com/fs/starfarer/api/combat/BaseHullMod"}
_SOURCE_HULLMOD_FIELD = re.compile(r"^\s*(?:private|protected|public)?\s*(?!static\b)(?!final\b)(?:transient\s+|volatile\s+)*([A-Za-z_][\w.<>\[\], ]*?)\s+(\w+)\s*(?:=[^;]*)?;", re.MULTILINE)


def _looks_like_constant(name: str) -> bool:
    """UPPER_SNAKE fields are constants by convention even when not declared final (never mutated)."""
    return bool(re.fullmatch(r"[A-Z][A-Z0-9_]*", name))


def _scan_hullmod_instance_state(root: Path, result: ScanResult) -> None:
    """Hull mods are single shared instances: mutable instance fields leak state between ships (SEEKER-DEATH-01).

    Starsector creates ONE object per hull mod spec and calls advanceInCombat(ship, ...) for every
    ship that has it, so a non-static, non-final field is shared across all of those ships. SEEKER's
    ART_organicHull kept runOnce/RADIUS/timers that way, and re-ran its death effect every frame
    on a wreck. REVIEW: constants stored in non-final fields are harmless; per-ship state belongs in
    ship.getCustomData().
    """
    explanation = (
        "This hull mod keeps changeable instance fields. Starsector shares ONE hull mod object across every "
        "ship with it, so per-ship state (timers, 'runOnce' flags, cached radius) leaks between ships and is "
        "never reset per ship. SEEKER's ART_organicHull did this and also re-ran its death effect every frame "
        "on a wreck, spawning debris until the game crawled. Keep per-ship state in ship.getCustomData()."
    )
    for jar, member, data in _iter_jar_class_files(root):
        info = _parse_class_file(data)
        if info is None or info.super_class not in _HULLMOD_BASES:
            continue
        mutable = sorted(
            name for name, descriptor, is_static, is_final in info.fields
            if not is_static and not is_final and not _looks_like_constant(name) and not descriptor.startswith("Ljava/util/")
        )
        if mutable:
            result.add(id="hullmod-instance-state", category="scripts", severity="medium", classification="REVIEW", confidence="DETERMINISTIC", explanation=explanation, file=f"{_relative(root, jar)}!{member}", evidence=[f"field:{name}" for name in mutable[:12]])
    for source in sorted(root.rglob("*.java")):
        if any(part in NON_MOD_JAR_DIRS or part.startswith("src-decompiled") for part in source.relative_to(root).parts):
            continue
        try:
            text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        class_match = re.search(r"\bclass\s+\w+\s+extends\s+BaseHullMod\b[^{]*\{", text)
        if not class_match:
            continue
        # Only fields declared at class-body depth 1 (not locals inside methods).
        body = text[class_match.end():]
        depth, top_level = 1, []
        for line in body.splitlines():
            if depth == 1:
                top_level.append(line)
            depth += line.count("{") - line.count("}")
            if depth <= 0:
                break
        mutable = sorted({
            match.group(2) for match in _SOURCE_HULLMOD_FIELD.finditer("\n".join(top_level))
            if "(" not in match.group(0)
            and not re.search(r"\b(static|final|return|package|import)\b", match.group(0))
            and not _looks_like_constant(match.group(2))
            and not re.search(r"\b(Map|HashMap|List|ArrayList|Set|HashSet|Collection|WeakHashMap)\b", match.group(1))
        })
        if mutable:
            result.add(id="hullmod-instance-state", category="scripts", severity="medium", classification="REVIEW", confidence="HEURISTIC", explanation=explanation, file=_relative(root, source), evidence=[f"field:{name}" for name in mutable[:12]])


def _scan_rules_firebest_populate_options(root: Path, result: ScanResult) -> None:
    """`FireBest PopulateOptions` rebuilds a menu from ONE rule, dropping vanilla's options (live bug VAC-DIALOG-01).

    PopulateOptions is fired by many rules that each add options (trade, comm directory, Leave...).
    Vanilla's rules.csv uses `FireAll PopulateOptions` 462 times and `FireBest` never. Vacuum's
    recreated station options used FireBest after "take bounty", so only one rule ran and the player
    was left in the dialog with no Leave option.
    """
    rules = root / "data" / "campaign" / "rules.csv"
    if not rules.is_file():
        return
    try:
        text = rules.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return
    lines = [text.count("\n", 0, match.start()) + 1 for match in re.finditer(r"\bFireBest\s+PopulateOptions\b", text)]
    if lines:
        result.add(
            id="rules-firebest-populate-options",
            category="rules",
            severity="high",
            classification="MANUAL",
            confidence="DETERMINISTIC",
            explanation="rules.csv fires PopulateOptions with FireBest, which runs only the single best-scoring rule. Menus are built by many PopulateOptions rules together (trade, comm directory, Leave...), so the player can be left in a dialog with no way out. Vanilla uses FireAll PopulateOptions everywhere (462 times, FireBest never); use FireAll.",
            file=_relative(root, rules),
            evidence=[f"line:{line}" for line in lines],
        )


# Personality ids RC8 defines (starsector-core data/characters/personalities.csv; 0.7.2 already lacked
# the legacy ones). 0.6.x also had cowardly/suicidal/fearless: setPersonality() with one of those now
# leaves the officer's personality null, and the ship AI built on deploy NPEs in Ship.getPersonality ->
# Fatal dialog (live run SK13-1d, SEEKER's missions).
VANILLA_PERSONALITY_IDS = frozenset({"timid", "cautious", "steady", "aggressive", "reckless"})
LEGACY_PERSONALITY_IDS = {"cowardly": "timid", "suicidal": "reckless", "fearless": "reckless"}
_SOURCE_SET_PERSONALITY = re.compile(r'\bsetPersonality\s*\(\s*"([^"\\]+)"\s*\)')


def _mod_personality_ids(root: Path) -> set[str]:
    """Ids the mod adds itself: data/characters/personalities.csv merges into vanilla's by id (Vacuum does this)."""
    path = root / "data" / "characters" / "personalities.csv"
    try:
        with path.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
            return {(row.get("id") or "").strip() for row in csv.DictReader(handle) if (row.get("id") or "").strip()}
    except OSError:
        return set()


def _scan_personality_ids(root: Path, result: ScanResult) -> None:
    valid = VANILLA_PERSONALITY_IDS | _mod_personality_ids(root)
    explanation = (
        "This code gives an officer a personality id that Starsector 0.98a does not define (only timid, cautious, "
        "steady, aggressive and reckless exist, plus any this mod adds in data/characters/personalities.csv). The "
        "officer's personality is left empty, and the game crashes with a Fatal dialog when that ship deploys. "
        "SEEKER's missions used 0.6-era 'suicidal'/'fearless'. Use a valid id (suggested: "
        + ", ".join(f"{old}->{new}" for old, new in LEGACY_PERSONALITY_IDS.items()) + ")."
    )
    for jar, member, data in _iter_jar_class_files(root):
        info = _parse_class_file(data)
        if info is None or "setPersonality" not in info.utf8_values:
            continue
        # Bytecode can't tie a literal to its call, so only exact legacy ids count (not briefing text).
        unknown = sorted(value for value in info.string_constants if value in LEGACY_PERSONALITY_IDS and value not in valid)
        if unknown:
            result.add(id="personality-id-unknown", category="scripts", severity="high", classification="MANUAL", confidence="HIGH", explanation=explanation, file=f"{_relative(root, jar)}!{member}", evidence=[f"personality:{value}" for value in unknown])
    for source in sorted(root.rglob("*.java")):
        if any(part in NON_MOD_JAR_DIRS or part.startswith("src-decompiled") for part in source.relative_to(root).parts):
            continue
        try:
            text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        unknown = sorted({match.group(1) for match in _SOURCE_SET_PERSONALITY.finditer(text) if match.group(1) not in valid})
        if unknown:
            result.add(id="personality-id-unknown", category="scripts", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation=explanation, file=_relative(root, source), evidence=[f"personality:{value}" for value in unknown])


# RC8's FleetFactoryV3 multiplies fleet size by the source market's Stats.COMBAT_FLEET_SIZE_MULT.
# A bare Global.getFactory().createMarket(...) has no industries, so the multiplier is 0 and every
# fleet comes out empty and vanishes (live run EX-7: no Exigency fleets in Tasserus, no error).
_FLEET_FACTORY_V3 = "com/fs/starfarer/api/impl/campaign/fleets/FleetFactoryV3"
_FLEET_SIZE_MULT_KEY = "combat_fleet_size_mult"  # value of Stats.COMBAT_FLEET_SIZE_MULT


_SECTOR_API = "com/fs/starfarer/api/campaign/SectorAPI"


def _scan_legacy_event_report(root: Path, result: ScanResult) -> None:
    """SectorAPI.reportEventStage is a documented no-op in 0.98a (live run EX-7b, EXI-EVENT-01).

    Old event plugins put their real effect (reputation changes, rewards) in the
    OnMessageDeliveryScript passed to reportEventStage. RC8 still accepts the call but does nothing,
    so that script never runs: no message, no penalty, no error.
    """
    explanation = (
        "This code calls Global.getSector().reportEventStage(...). In 0.98a that method is deprecated and does "
        "nothing (the old comm-message system was replaced by intel), so any effect placed in its delivery "
        "script never happens, with no error. Exigency's illegal-tech event caught the player but never applied "
        "its reputation penalty this way. Apply the effect directly (e.g. adjustPlayerReputation) and notify via "
        "getCampaignUI().addMessage(...) or an intel item."
    )
    for jar, member, data in _iter_jar_class_files(root):
        info = _parse_class_file(data)
        if info is None or "reportEventStage" not in info.utf8_values or _SECTOR_API not in info.referenced_classes:
            continue
        result.add(id="legacy-event-report-noop", category="campaign", severity="high", classification="MANUAL", confidence="HIGH", explanation=explanation, file=f"{_relative(root, jar)}!{member}", evidence=["call:SectorAPI.reportEventStage"])
    for source in sorted(root.rglob("*.java")):
        if any(part in NON_MOD_JAR_DIRS or part.startswith("src-decompiled") for part in source.relative_to(root).parts):
            continue
        try:
            text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        lines = [text.count("\n", 0, match.start()) + 1 for match in re.finditer(r"\.reportEventStage\s*\(", text)]
        if lines:
            result.add(id="legacy-event-report-noop", category="campaign", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation=explanation, file=_relative(root, source), evidence=[f"line:{line}" for line in lines])


def _scan_bare_market_fleet_source(root: Path, result: ScanResult) -> None:
    """Flag fleets built from a bare createMarket() source, unless the same tier sets the fleet-size multiplier.

    Jars and source are judged separately: a fix in the source tree does not help a jar that was never
    rebuilt (the game runs the jar), and a fix in the jar does not cover loose scripts.
    """
    jar_callers: list[str] = []
    jar_mitigated = False
    for jar, member, data in _iter_jar_class_files(root):
        info = _parse_class_file(data)
        if info is None:
            continue
        if _FLEET_SIZE_MULT_KEY in info.string_constants:
            jar_mitigated = True
        if _FLEET_FACTORY_V3 in info.referenced_classes and {"createMarket", "createFleet"} <= info.utf8_values:
            jar_callers.append(f"{_relative(root, jar)}!{member}")
    source_callers: list[str] = []
    source_mitigated = False
    for source in sorted(root.rglob("*.java")):
        if any(part in NON_MOD_JAR_DIRS or part.startswith("src-decompiled") for part in source.relative_to(root).parts):
            continue
        try:
            text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if "COMBAT_FLEET_SIZE_MULT" in text or f'"{_FLEET_SIZE_MULT_KEY}"' in text:
            source_mitigated = True
        if re.search(r"\bcreateMarket\s*\(", text) and re.search(r"\bFleetFactoryV3\s*\.\s*createFleet\s*\(", text):
            source_callers.append(_relative(root, source))
    callers = (jar_callers if not jar_mitigated else []) + (source_callers if not source_mitigated else [])
    if callers:
        result.add(
            id="fleet-source-bare-market",
            category="campaign",
            severity="high",
            classification="REVIEW",
            confidence="HEURISTIC",
            explanation=(
                "This code builds fleets with FleetFactoryV3 from a market made by Global.getFactory().createMarket(...). "
                "In 0.98a, fleet size is multiplied by the source market's combat fleet size stat, which is 0 on a bare "
                "market with no industries, so every fleet comes out empty and silently vanishes. Exigency's fleets never "
                "appeared this way. Give the market what vanilla's own fallback gets (Stats.COMBAT_FLEET_SIZE_MULT flat 1, "
                "Stats.FLEET_QUALITY_MOD flat FleetFactoryV3.BASE_QUALITY_WHEN_NO_MARKET), or pass a null source with a "
                "hyperspace location."
            ),
            evidence=sorted(set(callers))[:12],
        )


def _scan_weapon_effect_static_state(root: Path, result: ScanResult) -> None:
    explanation = (
        "This weapon-effect plugin keeps combat state (a ship, weapon, engine controller, system or "
        "projectile) in a static field. Starsector creates one plugin per weapon, so a static field is "
        "shared by every copy in the battle: the last one to initialise overwrites it for all of them. "
        "SEEKER's ART_thrusterRotation did this, and a ship spawned mid-battle made another ship's weapon "
        "read a ship with no system, which crashed the game with a Fatal dialog. Make the field an instance "
        "field, and null-check getSystem()."
    )
    for jar, member, data in _iter_jar_class_files(root):
        info = _parse_class_file(data)
        if info is None or not PER_WEAPON_PLUGIN_INTERFACES.intersection(info.interfaces):
            continue
        shared = sorted(f"{name}:{descriptor.rsplit('/', 1)[-1].rstrip(';')}" for name, descriptor, is_static, is_final in info.fields if is_static and not is_final and descriptor in _COMBAT_STATE_DESCRIPTORS)
        if shared:
            result.add(id="weapon-effect-static-combat-state", category="scripts", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation=explanation, file=f"{_relative(root, jar)}!{member}", evidence=[f"static:{item}" for item in shared])
    for source in sorted(root.rglob("*.java")):
        if any(part in NON_MOD_JAR_DIRS or part.startswith("src-decompiled") for part in source.relative_to(root).parts):
            continue
        try:
            text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if not re.search(r"\bimplements\b[^{]*\b(EveryFrameWeaponEffectPlugin|OnFireEffectPlugin|OnHitEffectPlugin|WeaponEffectPluginWithInit)\b", text):
            continue
        shared = sorted(f"{match.group(2)}:{match.group(1)}" for match in _SOURCE_STATIC_STATE.finditer(text))
        if shared:
            result.add(id="weapon-effect-static-combat-state", category="scripts", severity="high", classification="MANUAL", confidence="HEURISTIC", explanation=explanation, file=_relative(root, source), evidence=[f"static:{item}" for item in shared])


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
    for jar in _loaded_mod_jars(root):
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


def _scan_script_sandbox_forbidden_api(root: Path, result: ScanResult) -> None:
    """RC8's script classloader crashes at runtime the first time a scripted class touches reflection/file I/O."""
    explanation = (
        "RC8's script sandbox classloader throws SecurityException(\"File access and reflection are not allowed "
        "to scripts\") the first time this class is loaded at runtime, because it references java.lang.reflect, "
        "java.nio.file, or a java.io.File-family type. This is lazy (it only surfaces when the class is actually "
        "loaded, which can be mid-combat), so a clean boot does not prove it is safe. Remove the reflection/file-I/O "
        "usage, or move it out of the scripted class, before runtime testing."
    )
    for jar, member, data in _iter_jar_class_files(root):
        info = _parse_class_file(data)
        if info is None:
            continue
        forbidden = sorted(
            name for name in info.referenced_classes
            if name.startswith(FORBIDDEN_REFLECT_PREFIX) or name.startswith(FORBIDDEN_NIO_FILE_PREFIX) or name in FORBIDDEN_IO_CLASSES
        )
        if not forbidden:
            continue
        class_name = (info.this_class or member[:-6]).replace("/", ".")
        result.add(
            id="script-sandbox-forbidden-api",
            category="bytecode",
            severity="critical",
            classification="MANUAL",
            confidence="HIGH",
            explanation=explanation,
            file=_relative(root, jar),
            evidence=[f"class:{class_name}", *[f"forbidden:{name.replace('/', '.')}" for name in forbidden]],
        )

    source_dirs = [root / "data" / "scripts", root / "src"]
    seen_sources: set[Path] = set()
    for source_dir in source_dirs:
        if not source_dir.is_dir():
            continue
        for source in sorted(source_dir.rglob("*.java")):
            if source in seen_sources:
                continue
            seen_sources.add(source)
            if "disabled_files" in source.relative_to(root).parts:
                continue
            try:
                text = source.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            matches = sorted(set(FORBIDDEN_SANDBOX_SOURCE_PATTERN.findall(text)))
            if not matches:
                continue
            result.add(
                id="script-sandbox-forbidden-api",
                category="bytecode",
                severity="critical",
                classification="MANUAL",
                confidence="HIGH",
                explanation=explanation,
                file=_relative(root, source),
                evidence=[f"forbidden:{name}" for name in matches[:10]],
            )


def _scan_bundled_library_classes(root: Path, result: ScanResult) -> None:
    """A mod jar can silently absorb another mod/library's compiled classes during a rebuild."""
    for jar in _loaded_mod_jars(root):
        try:
            with zipfile.ZipFile(jar) as archive:
                entries = archive.infolist()
                if len(entries) > MAX_JAR_ENTRIES:
                    continue
                names = [item.filename.replace("\\", "/") for item in entries if item.filename.endswith(".class")]
        except (OSError, zipfile.BadZipFile):
            continue
        counts: Counter[str] = Counter()
        for name in names:
            internal = name[:-6]
            for library, prefixes in BUNDLED_LIBRARY_PACKAGE_PREFIXES.items():
                if any(internal.startswith(prefix) for prefix in prefixes):
                    counts[library] += 1
        for library, count in sorted(counts.items()):
            prefixes = ", ".join(BUNDLED_LIBRARY_PACKAGE_PREFIXES[library])
            result.add(
                id="bundled-library-classes",
                category="dependencies",
                severity="high",
                classification="MANUAL",
                confidence="DETERMINISTIC",
                explanation=(
                    f"This jar contains {count} compiled class(es) under {library}'s package(s) ({prefixes}). "
                    f"A rebuild that compiles against {library}'s sources found on the classpath can silently "
                    "bundle its classes into this mod's own jar, duplicating them for every player who also has "
                    f"the real {library} installed. Rebuild against {library} as a provided/compile-only "
                    "dependency instead of packaging its classes."
                ),
                file=_relative(root, jar),
                evidence=[f"library:{library}", f"class-count:{count}"],
            )


def _vanilla_api_jar_class_info(vanilla_core: Path) -> dict[str, _ClassFileInfo]:
    classes: dict[str, _ClassFileInfo] = {}
    for jar_name in ("starfarer.api.jar", "starfarer_obf.jar"):
        jar_path = vanilla_core / jar_name
        if not jar_path.is_file():
            continue
        try:
            with zipfile.ZipFile(jar_path) as archive:
                for item in archive.infolist():
                    if not item.filename.endswith(".class"):
                        continue
                    fqn = item.filename.replace("\\", "/")[:-6].replace("/", ".")
                    if fqn in classes:
                        continue
                    try:
                        data = archive.read(item)
                    except (OSError, zipfile.BadZipFile, KeyError):
                        continue
                    info = _parse_class_file(data)
                    if info is not None:
                        classes[fqn] = info
        except (OSError, zipfile.BadZipFile):
            continue
    return classes


def _vanilla_loose_script_fqns(vanilla_core: Path) -> set[str]:
    """Every loose vanilla .java source under data/** (not just data/scripts), by path-derived FQN.

    Starsector loads loose scripts from many data/ subdirectories, not only data/scripts (e.g.
    data/shipsystems/scripts/SensorDroneStats.java, referenced by vanilla ship systems). The FQN is
    the path relative to starsector-core with '/' -> '.', minus the .java suffix; when the file
    declares a 'package' line, that is used instead so a mismatched directory layout does not
    produce a false FQN.
    """
    data_root = vanilla_core / "data"
    if not data_root.is_dir():
        return set()
    fqns: set[str] = set()
    for path in data_root.rglob("*.java"):
        relative = path.relative_to(vanilla_core)
        path_fqn = ".".join(relative.with_suffix("").parts)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            fqns.add(path_fqn)
            continue
        package_match = re.search(r"^\s*package\s+([\w.]+)\s*;", text, re.M)
        if package_match:
            fqns.add(f"{package_match.group(1)}.{path.stem}")
        else:
            fqns.add(path_fqn)
    return fqns


def _scan_vanilla_duplicated_classes(root: Path, result: ScanResult, vanilla_core: Path | None) -> None:
    """A mod jar's own copy of a vanilla class replaces the target release's class for every mod loaded after it."""
    if vanilla_core is None:
        return
    vanilla_jar_classes = _vanilla_api_jar_class_info(vanilla_core)
    vanilla_loose_fqns = _vanilla_loose_script_fqns(vanilla_core)
    if not vanilla_jar_classes and not vanilla_loose_fqns:
        return
    for jar, member, data in _iter_jar_class_files(root):
        fqn = member[:-6].replace("/", ".")
        # A mod's own new rulecmd command classes are how rules.csv registers commands; only classes
        # that also exist in vanilla are duplicates, so a brand-new rulecmd class is never flagged here.
        if fqn.startswith("com.fs.starfarer.api.impl.campaign.rulecmd.") and fqn not in vanilla_jar_classes and fqn not in vanilla_loose_fqns:
            continue
        if fqn in vanilla_jar_classes:
            info = _parse_class_file(data)
            if info is None:
                continue
            vanilla_info = vanilla_jar_classes[fqn]
            vanilla_public = {(name, descriptor) for name, descriptor, is_public in vanilla_info.methods if is_public}
            mod_public = {(name, descriptor) for name, descriptor, is_public in info.methods if is_public}
            missing = sorted(f"{name}{descriptor}" for name, descriptor in (vanilla_public - mod_public))
            classification = "MANUAL" if missing else "REVIEW"
            severity = "critical" if missing else "high"
            result.add(
                id="vanilla-class-duplicated-in-jar",
                category="bytecode",
                severity=severity,
                classification=classification,
                confidence="HIGH",
                explanation=(
                    "This mod jar contains its own compiled copy of a vanilla API class, replacing the target "
                    "release's class on the classpath for every mod loaded after it."
                    + (
                        f" The mod's copy is missing {len(missing)} public method(s) the current release's class "
                        "has, so code compiled against the real class fails with NoSuchMethodError at runtime."
                        if missing
                        else " Its public method signatures currently match the target release; confirm this is an "
                        "intentional override rather than a stale copy."
                    )
                ),
                file=_relative(root, jar),
                evidence=[f"class:{fqn}", "vanilla-source:api-jar", *[f"missing-public-method:{m}" for m in missing[:10]]],
            )
        elif fqn in vanilla_loose_fqns:
            result.add(
                id="vanilla-class-duplicated-in-jar",
                category="bytecode",
                severity="high",
                classification="REVIEW",
                confidence="HIGH",
                explanation=(
                    "This mod jar contains a compiled class at the same fully-qualified name as a vanilla loose "
                    "script (data/scripts/**/*.java). A compiled class on the classpath takes priority over the "
                    "game's loose script, silently replacing that vanilla script's behavior game-wide, not just "
                    "for this mod."
                ),
                file=_relative(root, jar),
                evidence=[f"class:{fqn}", "vanilla-source:loose-script"],
            )


def _scan_obfuscated_internal_api_use(root: Path, result: ScanResult) -> None:
    """com.fs.starfarer classes outside the api package are obfuscated internals renamed each release."""
    for jar, member, data in _iter_jar_class_files(root):
        info = _parse_class_file(data)
        if info is None:
            continue
        internal_refs = sorted(
            name.replace("/", ".") for name in info.referenced_classes
            if name.startswith("com/fs/starfarer/") and not name.startswith("com/fs/starfarer/api/")
        )
        if not internal_refs:
            continue
        class_name = (info.this_class or member[:-6]).replace("/", ".")
        result.add(
            id="obfuscated-internal-api-use",
            category="bytecode",
            severity="medium",
            classification="REVIEW",
            confidence="HIGH",
            explanation=(
                "This compiled class references com.fs.starfarer internal (non-api) classes. Names outside "
                "com.fs.starfarer.api are obfuscated implementation details that get renamed between releases "
                "without notice; verify each reference still resolves against the target release before runtime "
                "testing."
            ),
            file=_relative(root, jar),
            evidence=[f"class:{class_name}", *[f"internal:{name}" for name in internal_refs[:15]]],
        )


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


ORBIT_CALL_ARG_INDICES: dict[str, list[int]] = {
    "addRingBand": [8],
    "addAsteroidBelt": [4, 5],
    "setCircularOrbit": [3],
    "setCircularOrbitPointingDown": [3],
    "setCircularOrbitWithSpin": [3],
}
_ORBIT_CALL_NAME_PATTERN = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_ZERO_LITERAL_PATTERN = re.compile(r"^-?0+(\.0+)?[fFdD]?$")
_ORBIT_GUARD_PATTERN = re.compile(r"Math\.max\s*\(|isNaN\s*\(|>\s*0\b")
_METHOD_SIGNATURE_PATTERN = re.compile(
    r"(?:public|private|protected|static)[^;{}]*?\b[\w$]+\s*\([^()]*\)\s*(?:throws\s+[\w.,\s]+)?\s*\{"
)


def _extract_call_arguments_text(text: str, open_paren_index: int) -> str | None:
    """Return the text between a call's matching parens, respecting nesting and quoted strings."""
    depth = 0
    in_string: str | None = None
    index = open_paren_index
    length = len(text)
    while index < length:
        character = text[index]
        if in_string:
            if character == "\\" and index + 1 < length:
                index += 2
                continue
            if character == in_string:
                in_string = None
            index += 1
            continue
        if character in "\"'":
            in_string = character
            index += 1
            continue
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return text[open_paren_index + 1:index]
        index += 1
    return None


def _split_call_arguments(args_text: str) -> list[str]:
    """Split a call's argument text on top-level commas only (quote/paren/bracket-aware)."""
    args: list[str] = []
    current: list[str] = []
    depth = 0
    in_string: str | None = None
    index = 0
    length = len(args_text)
    while index < length:
        character = args_text[index]
        if in_string:
            current.append(character)
            if character == "\\" and index + 1 < length:
                current.append(args_text[index + 1])
                index += 2
                continue
            if character == in_string:
                in_string = None
            index += 1
            continue
        if character in "\"'":
            in_string = character
            current.append(character)
            index += 1
            continue
        if character in "([{":
            depth += 1
            current.append(character)
            index += 1
            continue
        if character in ")]}":
            depth -= 1
            current.append(character)
            index += 1
            continue
        if character == "," and depth == 0:
            args.append("".join(current).strip())
            current = []
            index += 1
            continue
        current.append(character)
        index += 1
    if current or args:
        args.append("".join(current).strip())
    return args


def _enclosing_method_span(text: str, position: int) -> tuple[int, int]:
    """Return the (start, end) offsets of the innermost method body enclosing `position`.

    Uses a simple signature regex plus brace counting; falls back to the whole file when no
    enclosing method is recognized (still safe: guard detection then just looks file-wide).
    """
    best: tuple[int, int] | None = None
    for match in _METHOD_SIGNATURE_PATTERN.finditer(text):
        body_start = match.end() - 1
        if body_start > position:
            continue
        depth = 0
        end = None
        for index in range(body_start, len(text)):
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
        if end is None or not (body_start <= position < end):
            continue
        if best is None or match.start() > best[0]:
            best = (match.start(), end)
    if best is None:
        return 0, len(text)
    return best


def _looks_like_division(expr: str) -> bool:
    cleaned = re.sub(r'"(?:\\.|[^"\\])*"', '""', expr)
    return bool(re.search(r"(?<!/)/(?!/)", cleaned))


def _classify_orbit_argument(arg_text: str, method_text: str) -> str | None:
    """Classify one orbit-period call argument: 'zero', 'computed-unguarded', or None (no finding)."""
    arg = arg_text.strip()
    if not arg:
        return None
    if _ZERO_LITERAL_PATTERN.match(arg):
        return "zero"
    is_computed = _looks_like_division(arg)
    if not is_computed and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", arg):
        is_computed = bool(re.search(rf"\b{re.escape(arg)}\s*=(?!=)\s*[^;]*?/[^;]*?;", method_text))
    if not is_computed:
        return None
    if _ORBIT_GUARD_PATTERN.search(method_text):
        return None
    return "computed-unguarded"


def _blank_java_comments(text: str, strings: bool = False) -> str:
    """Blank out // and /* */ comment text with spaces, keeping newlines so offsets and line numbers hold.

    String and char literals are skipped, so "http://..." survives. Without this, source checks flagged
    commented-out code (a disabled setCircularOrbit block in Legacy of Arkgneisis's procgen generator).
    With strings=True the literals' contents are blanked too (quotes kept): declaration matchers need it,
    since Xenoargh's AI Overhaul logs "couldn't find the class for a System" and archaeology read a class
    named `for` out of it (2026-09-14).
    """
    out = list(text)
    index, length = 0, len(text)
    while index < length:
        char = text[index]
        if char in "\"'":
            index += 1
            while index < length and text[index] != char and text[index] != "\n":
                step = 2 if text[index] == "\\" else 1
                if strings:
                    for position in range(index, min(index + step, length)):
                        if out[position] != "\n":
                            out[position] = " "
                index += step
            index += 1
            continue
        if text.startswith("//", index):
            while index < length and text[index] != "\n":
                out[index] = " "
                index += 1
            continue
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            end = length if end < 0 else end + 2
            for position in range(index, end):
                if out[position] != "\n":
                    out[position] = " "
            index = end
            continue
        index += 1
    return "".join(out)


def _scan_orbit_period_hazards(root: Path, result: ScanResult) -> None:
    """RC8 crashes at the next save when a ring/belt/orbit is given a zero (or unguarded-computed) period.

    A zero orbit period is infinite angular speed; RingBand and similar orbit objects cannot
    serialize a non-finite number, so the next autosave/save throws
    "RingBand.writeReplace: JSON does not allow non-finite numbers" (or an equivalent crash).
    Real case: Legacy of Arkgneisis's SpawnChampionRing computed `float orbitTime = orbitRadius / 20f;`
    where orbitRadius can be -1 (no jump points) or <= 0 (a cramped system).
    """
    for source in sorted(root.rglob("*.java")):
        if "disabled_files" in source.relative_to(root).parts:
            continue
        try:
            text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        relative = _relative(root, source)
        for match in _ORBIT_CALL_NAME_PATTERN.finditer(text):
            call_name = match.group(1)
            indices = ORBIT_CALL_ARG_INDICES.get(call_name)
            if indices is None:
                continue
            open_paren = match.end() - 1
            args_text = _extract_call_arguments_text(text, open_paren)
            if args_text is None:
                continue
            args = _split_call_arguments(args_text)
            line_number = text.count("\n", 0, match.start()) + 1
            method_text: str | None = None
            for index in indices:
                if index >= len(args):
                    continue
                arg_text = args[index]
                if method_text is None:
                    start, end = _enclosing_method_span(text, match.start())
                    method_text = text[start:end]
                classification = _classify_orbit_argument(arg_text, method_text)
                if classification == "zero":
                    result.add(
                        id="orbit-period-zero",
                        category="source",
                        severity="critical",
                        classification="MANUAL",
                        confidence="DETERMINISTIC",
                        explanation=(
                            f"This call to {call_name}(...) passes a literal 0 orbit-period. A zero orbit period "
                            "is infinite angular speed; the next save throws "
                            "'RingBand.writeReplace: JSON does not allow non-finite numbers' (or an equivalent "
                            "non-finite-orbit crash) the first time this object is serialized."
                        ),
                        file=relative,
                        evidence=[f"line:{line_number}", f"call:{call_name}", f"arg-index:{index}", f"arg:{arg_text}"],
                    )
                elif classification == "computed-unguarded":
                    result.add(
                        id="orbit-period-computed-unguarded",
                        category="source",
                        severity="medium",
                        classification="REVIEW",
                        confidence="MEDIUM",
                        explanation=(
                            f"This call to {call_name}(...) passes a computed orbit-period with no visible "
                            "Math.max/'> 0'/isNaN guard in the enclosing method. If the underlying value can be "
                            "zero, negative, or NaN, the next save throws a non-finite-number crash "
                            "(RingBand.writeReplace or equivalent). Real case: Legacy of Arkgneisis's "
                            "SpawnChampionRing computed `float orbitTime = orbitRadius / 20f;` where orbitRadius "
                            "can be -1 or <= 0."
                        ),
                        file=relative,
                        evidence=[f"line:{line_number}", f"call:{call_name}", f"arg-index:{index}", f"arg:{arg_text}"],
                    )


def _scan_module_captain_personality_risk(root: Path, result: ScanResult) -> None:
    """RC8's Ship.getPersonality() NPEs for a module/spawned ship whose captain has no personality."""
    ship_data_path = root / "data" / "hulls" / "ship_data.csv"
    for row in _read_csv_rows(ship_data_path) or []:
        hull_id = (row.get("id") or "").strip()
        if not hull_id or hull_id.startswith("#"):
            continue
        hints = (row.get("hints") or "").upper()
        if "SHIP_WITH_MODULES" not in hints:
            continue
        result.add(
            id="module-captain-personality-risk",
            category="hulls",
            severity="medium",
            classification="REVIEW",
            confidence="MEDIUM",
            explanation=(
                "This hull is tagged SHIP_WITH_MODULES. Reported live, pending confirmation: RC8's "
                "Ship.getPersonality() NPEs if a module's captain has no personality, and AI-replacement mods "
                "(e.g. AI Tweaks) construct BasicShipAI for modules without a personality override, crashing in "
                "CombatFleetManager.deployAll. Ensure module/spawned-ship captains get a personality."
            ),
            file=_relative(root, ship_data_path),
            evidence=[f"hull:{hull_id}", "hint:SHIP_WITH_MODULES"],
        )


_SPAWN_SHIP_CALL_PATTERN = re.compile(r"\b(spawnShipOrWing|spawnFleetMember)\s*\(\s*\"([^\"]+)\"")


def _scan_spawned_ship_captain_personality_risk(root: Path, result: ScanResult) -> None:
    """A ship (not wing) spawned directly via spawnShipOrWing/spawnFleetMember gets an AI captain with no personality."""
    wing_ids = _wing_ids_set(root / "data" / "hulls" / "wing_data.csv")
    for source in sorted(root.rglob("*.java")):
        if "disabled_files" in source.relative_to(root).parts:
            continue
        try:
            text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        relative = _relative(root, source)
        for match in _SPAWN_SHIP_CALL_PATTERN.finditer(text):
            call_name, spawned_id = match.group(1), match.group(2)
            if spawned_id.endswith("_wing") or spawned_id in wing_ids:
                continue
            line_number = text.count("\n", 0, match.start()) + 1
            result.add(
                id="spawned-ship-captain-personality-risk",
                category="source",
                severity="low",
                classification="REVIEW",
                confidence="MEDIUM",
                explanation=(
                    f"This {call_name}(...) call spawns '{spawned_id}', which resolves as a ship variant rather "
                    "than a fighter wing (it is not in wing_data.csv and does not end in '_wing'). RC8's "
                    "Ship.getPersonality() NPEs if the spawned ship's captain has no personality; real case: "
                    "SEEKER hullmods spawn ART_*_hulk* debris ships on death this way."
                ),
                file=relative,
                evidence=[f"line:{line_number}", f"call:{call_name}", f"spawned:{spawned_id}"],
            )


# Banner forms only. A bare, case-insensitive "broken" also matched the real mod name "Broken Star"
# after its "(BROEKN MAYBE)" banner was removed, so "BROKEN" must be all-caps or parenthesised.
MOD_INFO_TRIAGE_BANNER_PATTERN = re.compile(
    r"\bBROKEN\b|(?i:\(\s*broken|BROEKN|UNREVIVED|NEEDS TO BE UPDATED|fetch an old game version)"
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


_EXTERNAL_DEPENDENCY_PREFIXES = ("org.lazywizard", "org.magiclib", "org.dark", "lunalib", "exerelin")
_RULE_COMMAND_PATTERN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)")


def _is_external_dependency_class(fqn: str) -> bool:
    """True when a FQN matches a known third-party library/mod API package we cannot see the jar for."""
    lower = fqn.lower()
    if lower.startswith(_EXTERNAL_DEPENDENCY_PREFIXES):
        return True
    if lower.startswith("data.scripts.util."):
        simple_name = fqn.rsplit(".", 1)[-1]
        if simple_name.lower().startswith("magic"):
            return True
    return False


def _collect_csv_column_class_refs(path: Path, column: str, root: Path, references: list[tuple[str, str, str]]) -> None:
    header = _csv_header(path)
    if not header or column not in header:
        return
    rows = _read_csv_rows(path)
    if not rows:
        return
    relative = _relative(root, path)
    for row in rows:
        values = list(row.values())
        if values and str(values[0] or "").strip().startswith("#"):
            continue
        value = (row.get(column) or "").strip()
        if not value or value.startswith("#"):
            continue
        references.append((relative, column, value))


def _scan_data_class_references_missing(root: Path, result: ScanResult, vanilla_core: Path | None) -> None:
    """Every fully qualified class named in mod data must resolve to a class Starsector can actually load.

    Checked against: this mod's loaded jars (result.compiled_class_names), a loose data/scripts .java source
    (FQN via package+class name), vanilla (when vanilla_core is supplied), or a known third-party library
    package (classified UNKNOWN/external, since that dependency's jar is not visible to BridgeForge). A row
    or line commented out with '#' is skipped, so it never fires for a deliberately disabled reference (e.g.
    Exigency's commented-out exigency_RepulsorRenderer combat_radar_plugins.csv row).
    """
    references: list[tuple[str, str, str]] = []

    _collect_csv_column_class_refs(root / "data" / "hullmods" / "hull_mods.csv", "script", root, references)
    _collect_csv_column_class_refs(root / "data" / "shipsystems" / "ship_systems.csv", "script", root, references)
    _collect_csv_column_class_refs(root / "data" / "campaign" / "submarkets.csv", "script", root, references)
    _collect_csv_column_class_refs(root / "data" / "campaign" / "industries.csv", "plugin", root, references)

    weapon_data_path = root / "data" / "weapons" / "weapon_data.csv"
    weapon_header = _csv_header(weapon_data_path) or []
    for column in weapon_header:
        if column and "script" in column.lower():
            _collect_csv_column_class_refs(weapon_data_path, column, root, references)

    for suffix in ("*.system",):
        for path in (root / "data" / "shipsystems").rglob(suffix) if (root / "data" / "shipsystems").is_dir() else []:
            data = _load_lenient_json_file(path)
            if not isinstance(data, dict):
                continue
            for field in ("statsScript", "aiScript"):
                value = data.get(field)
                if isinstance(value, str) and value.strip() and not value.strip().startswith("#"):
                    references.append((_relative(root, path), field, value.strip()))

    for suffix in ("*.wpn", "*.proj"):
        for path in root.rglob(suffix):
            data = _load_lenient_json_file(path)
            if not isinstance(data, dict):
                continue
            for field in ("onHitEffect", "everyFrameEffect", "onFireEffect"):
                value = data.get(field)
                if isinstance(value, str) and value.strip() and not value.strip().startswith("#"):
                    references.append((_relative(root, path), field, value.strip()))

    rules_path = root / "data" / "campaign" / "rules.csv"
    rules_header = _csv_header(rules_path) or []
    if "script" in rules_header and vanilla_core is not None:
        rules_rows = _read_csv_rows(rules_path) or []
        relative = _relative(root, rules_path)
        for row in rules_rows:
            values = list(row.values())
            if values and str(values[0] or "").strip().startswith("#"):
                continue
            script_text = row.get("script") or ""
            for line in script_text.splitlines():
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("$"):
                    continue
                match = _RULE_COMMAND_PATTERN.match(line)
                if not match:
                    continue
                command = match.group(1)
                references.append((relative, "script(rule-command)", f"com.fs.starfarer.api.impl.campaign.rulecmd.{command}"))

    settings_path = root / "data" / "config" / "settings.json"
    settings = _load_lenient_json_file(settings_path)
    if isinstance(settings, dict):
        plugins = settings.get("plugins")
        relative = _relative(root, settings_path)
        if isinstance(plugins, dict):
            for key, value in plugins.items():
                if isinstance(value, str) and value.strip():
                    references.append((relative, f"plugins.{key}", value.strip()))
        elif isinstance(plugins, list):
            for value in plugins:
                if isinstance(value, str) and value.strip():
                    references.append((relative, "plugins", value.strip()))

    mod_info_path = root / "mod_info.json"
    mod_info = _load_lenient_json_file(mod_info_path)
    if isinstance(mod_info, dict):
        mod_plugin = mod_info.get("modPlugin")
        if isinstance(mod_plugin, str) and mod_plugin.strip():
            references.append((_relative(root, mod_info_path), "modPlugin", mod_plugin.strip()))

    local_source_fqns = set(_source_class_index(root))
    vanilla_jar_classes = _vanilla_api_jar_class_info(vanilla_core) if vanilla_core is not None else {}
    vanilla_loose_fqns = _vanilla_loose_script_fqns(vanilla_core) if vanilla_core is not None else set()
    local_simple_names = {name.rsplit(".", 1)[-1] for name in result.compiled_class_names} | {
        name.rsplit(".", 1)[-1] for name in local_source_fqns
    }
    # Vanilla rule commands also live in rulecmd sub-packages (e.g. rulecmd.salvage.AddBarEvent), so a bare
    # rules.csv command resolves by simple name against any vanilla class under a ".rulecmd." package.
    vanilla_rulecmd_simple_names = {
        name.rsplit(".", 1)[-1] for name in (set(vanilla_jar_classes) | vanilla_loose_fqns) if ".rulecmd." in name
    }

    def resolve(fqn: str, is_rule_command: bool) -> str:
        if fqn in result.compiled_class_names or fqn in local_source_fqns:
            return "resolved"
        if vanilla_core is not None and (fqn in vanilla_jar_classes or fqn in vanilla_loose_fqns):
            return "resolved"
        if is_rule_command and fqn.rsplit(".", 1)[-1] in local_simple_names:
            return "resolved"
        if is_rule_command and fqn.rsplit(".", 1)[-1] in vanilla_rulecmd_simple_names:
            return "resolved"
        if _is_external_dependency_class(fqn):
            return "external"
        if vanilla_core is None and (fqn.startswith("com.fs.starfarer.") or fqn.startswith("com.fs.")):
            # This is plausibly a vanilla engine class; without vanilla_core we cannot tell a genuine
            # vanilla reference (normal) from a removed/renamed API (a real bug) apart.
            return "vanilla-unverified"
        return "missing"

    seen: set[tuple[str, str, str]] = set()
    for file, field, class_name in references:
        key = (file, field, class_name)
        if key in seen:
            continue
        seen.add(key)
        status = resolve(class_name, field == "script(rule-command)")
        if status == "resolved":
            continue
        if status == "external":
            result.add(
                id="data-class-reference-missing",
                category="content",
                severity="low",
                classification="UNKNOWN",
                confidence="LOW",
                explanation="This class reference matches a known third-party library/mod API package (LazyLib, MagicLib, org.dark, LunaLib, Nexerelin). BridgeForge cannot see that dependency's jar, so this cannot be verified as present; treat it as an external dependency reference, unverified, not a defect.",
                file=file,
                evidence=[f"field:{field}", f"class:{class_name}", "external dependency, unverified"],
            )
            continue
        if status == "vanilla-unverified":
            result.add(
                id="data-class-reference-missing",
                category="content",
                severity="low",
                classification="UNKNOWN",
                confidence="LOW",
                explanation="This class reference is under com.fs.* (Starsector's own package namespace) and could not be checked against the mod's jars or sources. No --vanilla-core was supplied, so BridgeForge cannot distinguish an ordinary vanilla-engine class reference from a genuinely removed/renamed API; supply --vanilla-core to verify.",
                file=file,
                evidence=[f"field:{field}", f"class:{class_name}", "vanilla class, unverified (no vanilla core supplied)"],
            )
            continue
        result.add(
            id="data-class-reference-missing",
            category="content",
            severity="critical",
            classification="MANUAL",
            confidence="HIGH" if vanilla_core is not None else "MEDIUM",
            explanation="A fully qualified class named in mod data does not resolve to any class in this mod's loaded jars, a loose data/scripts source file, or (when supplied) the vanilla core. Loading this row/field at runtime throws a class-not-found-class crash. Confirm whether the class was removed, renamed, or simply not rebuilt into the jar, then restore it or remove the reference.",
            file=file,
            evidence=[f"field:{field}", f"class:{class_name}"],
        )


_COORDINATE_NUMBER = r"-?\d+(?:\.\d+)?f?"
_VECTOR_LITERAL_PATTERN = re.compile(
    rf"(?:new\s+Vector2f\s*\(\s*({_COORDINATE_NUMBER})\s*,\s*({_COORDINATE_NUMBER})\s*\))"
    rf"|(?:getLocation\(\)\.set\s*\(\s*({_COORDINATE_NUMBER})\s*,\s*({_COORDINATE_NUMBER})\s*\))"
)
_HYPERSPACE_TOUCH_PATTERN = re.compile(r"getHyperspace\(\)|getLocationInHyperspace|\bwaypoints?\b", re.I)
_TERRAIN_GRID_LITERAL_PATTERN = re.compile(r"(?:[/%]\s*(\d{2,4})\b)|(?:\[\s*(\d{2,4})\s*\])")


def _scan_hardcoded_hyperspace_coordinates(root: Path, result: ScanResult) -> None:
    """A hyperspace-touching class hard-coding >=3 literal coordinate pairs (e.g. a stale pre-rework layout)."""
    for path in root.rglob("*.java"):
        if "disabled_files" in path.relative_to(root).parts:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        blanked = _blank_java_comments(text)
        if not _HYPERSPACE_TOUCH_PATTERN.search(blanked):
            continue
        pairs: list[tuple[int, str, str]] = []
        for match in _VECTOR_LITERAL_PATTERN.finditer(blanked):
            groups = match.groups()
            x = groups[0] if groups[0] is not None else groups[2]
            y = groups[1] if groups[1] is not None else groups[3]
            line = blanked.count("\n", 0, match.start()) + 1
            pairs.append((line, x, y))
        if len(pairs) < 3:
            continue
        evidence = [f"line:{line}:({x},{y})" for line, x, y in pairs[:5]]
        evidence.append(f"total_coordinate_pairs:{len(pairs)}")
        result.add(
            id="hardcoded-hyperspace-coordinates",
            category="content",
            severity="low",
            classification="REVIEW",
            confidence="MEDIUM",
            explanation="This class touches hyperspace (getHyperspace()/getLocationInHyperspace/a waypoint-like list) and hard-codes 3 or more literal Vector2f coordinate pairs. A stale pre-rework layout (e.g. old hyperspace-terrain-era coordinates) can land in the wrong place after a hyperspace rework; verify these coordinates are still sane for the target game version.",
            file=_relative(root, path),
            evidence=evidence,
        )


def _scan_hardcoded_terrain_grid_size(root: Path, result: ScanResult) -> None:
    """Code that indexes/divides a getTiles() terrain grid by a hard-coded literal grid size or mask."""
    for path in root.rglob("*.java"):
        if "disabled_files" in path.relative_to(root).parts:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        blanked = _blank_java_comments(text)
        if "getTileCenter" in blanked:
            continue  # already fixed to use the grid's own accessor; must not fire
        for match in re.finditer(r"getTiles\(\)", blanked):
            start = max(0, match.start() - 200)
            end = min(len(blanked), match.end() + 200)
            grid_match = _TERRAIN_GRID_LITERAL_PATTERN.search(blanked[start:end])
            if not grid_match:
                continue
            value = grid_match.group(1) or grid_match.group(2)
            line = blanked.count("\n", 0, match.start()) + 1
            result.add(
                id="hardcoded-terrain-grid-size",
                category="content",
                severity="low",
                classification="REVIEW",
                confidence="MEDIUM",
                explanation="Code indexes or divides a getTiles() terrain grid by a hard-coded literal grid size/mask near this call. This breaks if the grid's actual dimensions ever differ from the constant; use the grid's own reported size/center accessor (e.g. getTileCenter) instead of a fixed literal.",
                file=_relative(root, path),
                evidence=[f"line:{line}", f"literal:{value}"],
            )
            break


def _mod_info_declares_dependency(result: ScanResult, dependency_id: str) -> bool:
    dependencies = result.metadata.get("dependencies") or result.metadata.get("requiredDependencies") or []
    target = dependency_id.strip().lower()
    for item in dependencies:
        if isinstance(item, dict):
            candidates = (str(item.get("id") or ""), str(item.get("name") or ""))
        else:
            candidates = (str(item),)
        if any(candidate.strip().lower() == target for candidate in candidates):
            return True
    return False


# Vanilla classes that 0.53-0.65 mods import and that 0.98a no longer ships (2026-09-14 batch: Batavia,
# Cobalt Arms, Gekelonians, Independant Mining Faction, Qualljom).
# Vanilla classes that old mods use but the target no longer has. Add an entry only with evidence from
# the target's own starsector-core: its jars AND its loose data/scripts.
# Correction, 2026-09-14: BaseSpawnPoint and corvus.Corvus were listed here as removed, but RC8 still
# ships both as loose scripts (starsector-core/data/scripts/world/BaseSpawnPoint.java, with the same
# constructor and abstract spawnFleet(), and .../corvus/Corvus.java). The earlier evidence had checked
# only the jars.
LEGACY_VANILLA_CLASSES: dict[str, str] = {}
def _load_rc8_vanilla_loose_script_classes() -> frozenset[str]:
    """RC8's loose vanilla scripts (all 116: hull mods, ship systems, missions, world generation).

    The game compiles them at startup, so mods may import them like API classes: Adjusted Sector imports
    data.hullmods.HeavyArmor. The list is read from vanilla_loose_scripts_rc8.json, which was generated
    from RC8's starsector-core, because the import check runs without a vanilla core path.
    """
    try:
        data = json.loads(Path(__file__).with_name("vanilla_loose_scripts_rc8.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return frozenset()
    return frozenset(str(name) for name in data.get("classes", []))


VANILLA_LOOSE_SCRIPT_CLASSES = _load_rc8_vanilla_loose_script_classes()


def _console_command_classes(root: Path) -> set[str]:
    """Classes registered in data/console/commands.csv (loaded only by Console Commands)."""
    rows = _read_csv_rows_lenient(root / "data" / "console" / "commands.csv") or []
    return {(row.get("class") or "").strip() for row in rows if (row.get("class") or "").strip()}


def _sources_mentioning(root: Path, dotted: list[str]) -> dict[str, str]:
    """{relative source path: class name} for .java files that mention any dotted package."""
    found: dict[str, str] = {}
    for source in sorted(root.rglob("*.java")):
        if "disabled_files" in source.relative_to(root).parts:
            continue
        try:
            text = source.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if any(needle in text for needle in dotted):
            package = re.search(r"(?m)^\s*package\s+([\w.]+)\s*;", text)
            found[_relative(root, source)] = f"{package.group(1)}.{source.stem}" if package else source.stem
    return found


def _library_import_only(root: Path, result: ScanResult, slash_prefixes: tuple[str, ...] | list[str]) -> list[str]:
    """Source files that mention a library although the shipped jar never references it.

    Returns the mentioning sources when every one of them compiles into a loaded jar class and no loaded
    jar class references the library's packages; otherwise []. Bionic Alteration imports Nexerelin's
    StringHelper but never calls it, so its jar has no exerelin/ reference and it runs without
    Nexerelin: an unused import is not a dependency (2026-09-14).
    """
    if not result.compiled_class_names:
        return []
    dotted = [prefix.replace("/", ".").rstrip(".") for prefix in slash_prefixes]
    mentioning: list[str] = []
    for source in sorted(root.rglob("*.java")):
        if "disabled_files" in source.relative_to(root).parts:
            continue
        try:
            text = source.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not any(needle in text for needle in dotted):
            continue
        package = re.search(r"(?m)^\s*package\s+([\w.]+)\s*;", text)
        class_name = f"{package.group(1)}.{source.stem}" if package else source.stem
        if class_name not in result.compiled_class_names:
            return []  # a loose or uncompiled source: its import may be live
        mentioning.append(_relative(root, source))
    if not mentioning:
        return []
    for _jar, _member, data in _iter_jar_class_files(root):
        info = _parse_class_file(data)
        if info is not None and any(ref.startswith(prefix) for ref in info.referenced_classes for prefix in slash_prefixes):
            return []
    return mentioning


def _scan_undeclared_library_dependency(root: Path, result: ScanResult) -> None:
    """Code that reaches a known library's package without mod_info.json declaring that dependency."""
    for library, dependency_id in LIBRARY_DEPENDENCY_IDS.items():
        if _mod_info_declares_dependency(result, dependency_id):
            continue
        prefixes = BUNDLED_LIBRARY_PACKAGE_PREFIXES[library]
        import_only = _library_import_only(root, result, prefixes)
        if import_only:
            result.add(
                id="library-import-unused-in-jar",
                category="dependencies",
                severity="info",
                classification="SAFE",
                confidence="HIGH",
                explanation=f"Source files mention {library}, but they all compile into the shipped jar and no jar class references {library}'s packages (an unused import). The mod runs without {library}; no dependency is needed.",
                file="mod_info.json",
                evidence=[f"library:{library}", *import_only[:5]],
            )
            continue
        dotted_needles = [prefix.replace("/", ".").rstrip(".") for prefix in prefixes]
        source_hits: list[str] = []
        guarded = False
        for source in sorted(root.rglob("*.java")):
            if "disabled_files" in source.relative_to(root).parts:
                continue
            try:
                text = source.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if not any(needle in text for needle in dotted_needles):
                continue
            source_hits.append(_relative(root, source))
            if re.search(r"\bisModEnabled\s*\(", text):
                guarded = True
        bytecode_hits: list[str] = []
        if not source_hits:
            for jar, member, data in _iter_jar_class_files(root):
                info = _parse_class_file(data)
                if info is None:
                    continue
                if any(ref.startswith(prefix) for ref in info.referenced_classes for prefix in prefixes):
                    relative_jar = _relative(root, jar)
                    if relative_jar not in bytecode_hits:
                        bytecode_hits.append(relative_jar)
                # Bytecode-only mods (no source, e.g. Nightcross): a loaded class that calls
                # isModEnabled and carries this mod id as a string literal is the same guard.
                if "isModEnabled" in info.utf8_values and any(value.strip().lower() == dependency_id.lower() for value in info.string_constants):
                    guarded = True
        if not source_hits and not bytecode_hits:
            continue
        classification = "REVIEW" if guarded else "MANUAL"
        result.add(
            id="undeclared-library-dependency",
            category="dependencies",
            severity="high",
            classification=classification,
            confidence="HIGH",
            explanation=(
                f"Code references {library}'s package(s) ({', '.join(prefixes)}), but mod_info.json does not "
                f"declare a matching '{dependency_id}' dependency. An undeclared mandatory dependency lets the "
                f"mod load and crash later, the first time it calls {library}."
                + (
                    " An isModEnabled(...) guard was found (in a referencing source file, or in a loaded class "
                    "that checks this mod id), suggesting an optional integration rather than a hard dependency. "
                    "A plugin may also use that check to fail fast when a required library is missing, so confirm."
                    if guarded
                    else ""
                )
            ),
            file="mod_info.json",
            evidence=[f"library:{library}", f"dependency-id:{dependency_id}", *source_hits[:5], *bytecode_hits[:5]],
        )


WEAPON_SLOT_SKIP_TYPES = {"BUILT_IN", "DECORATIVE", "SYSTEM", "LAUNCH_BAY", "STATION_MODULE"}
WEAPON_SLOT_SIZE_RANK = {"SMALL": 1, "MEDIUM": 2, "LARGE": 3}
HULL_MOD_COST_COLUMN_BY_SIZE = {
    "FRIGATE": "cost_frigate",
    "DESTROYER": "cost_dest",
    "CRUISER": "cost_cruiser",
    "CAPITAL": "cost_capital",
}


def _csv_id_index(mod_path: Path, vanilla_path: Path | None) -> dict[str, dict[str, str]]:
    """Merge a mod CSV's 'id'-keyed rows over the matching vanilla CSV (vanilla first, mod wins)."""
    index: dict[str, dict[str, str]] = {}
    for path in (vanilla_path, mod_path):
        if path is None or not path.is_file():
            continue
        for row in _read_csv_rows(path) or []:
            row_id = (row.get("id") or "").strip()
            if row_id and not row_id.startswith("#"):
                index[row_id] = row
    return index


def _float_or(value: object, default: float = 0.0) -> float:
    try:
        text = str(value).strip()
        if not text:
            return default
        return float(text)
    except (TypeError, ValueError):
        return default


def _ship_file_index(root: Path, vanilla_core: Path | None) -> dict[str, dict]:
    """hullId -> parsed .ship data, vanilla first so a mod's own hull of the same id wins."""
    index: dict[str, dict] = {}
    for base in (vanilla_core, root):
        if base is None or not base.is_dir():
            continue
        for path in base.rglob("*.ship"):
            data = _load_lenient_json_file(path)
            if not isinstance(data, dict):
                continue
            hull_id = data.get("hullId")
            if isinstance(hull_id, str) and hull_id.strip():
                index[hull_id.strip()] = data
            else:
                index[path.stem] = data
    return index


def _skin_index(root: Path, vanilla_core: Path | None) -> dict[str, str]:
    """skinHullId -> baseHullId, from .skin files in the mod and vanilla."""
    index: dict[str, str] = {}
    for base in (vanilla_core, root):
        if base is None or not base.is_dir():
            continue
        for path in base.rglob("*.skin"):
            data = _load_lenient_json_file(path)
            if not isinstance(data, dict):
                continue
            skin_id = data.get("skinHullId")
            base_id = data.get("baseHullId")
            if isinstance(skin_id, str) and skin_id.strip() and isinstance(base_id, str) and base_id.strip():
                index[skin_id.strip()] = base_id.strip()
    return index


def _resolve_hull_id(hull_id: str, skins: dict[str, str]) -> str:
    """Chase a skin's baseHullId chain to the underlying hull id (cycle-safe)."""
    seen: set[str] = set()
    current = hull_id
    while current in skins and current not in seen:
        seen.add(current)
        current = skins[current]
    return current


def _wpn_type_size_index(root: Path, vanilla_core: Path | None) -> dict[str, dict[str, str]]:
    """weapon id -> {'type':..., 'size':...} parsed from the actual .wpn spec files."""
    index: dict[str, dict[str, str]] = {}
    for base in (vanilla_core, root):
        if base is None or not base.is_dir():
            continue
        for path in base.rglob("*.wpn"):
            data = _load_lenient_json_file(path)
            if not isinstance(data, dict):
                continue
            weapon_id = data.get("id")
            if isinstance(weapon_id, str) and weapon_id.strip():
                index[weapon_id.strip()] = {
                    "type": str(data.get("type") or "").strip().upper(),
                    "size": str(data.get("size") or "").strip().upper(),
                    # mountTypeOverride lets a weapon fit other slot types (e.g. an ENERGY weapon with
                    # HYBRID fits BALLISTIC slots); ignoring it produced false slot mismatches.
                    "mount_override": str(data.get("mountTypeOverride") or "").strip().upper(),
                }
    return index


# Slot types a weapon's mountTypeOverride lets it occupy, on top of its base type.
MOUNT_OVERRIDE_FITS = {
    "HYBRID": {"BALLISTIC", "ENERGY", "HYBRID", "UNIVERSAL"},
    "COMPOSITE": {"BALLISTIC", "MISSILE", "COMPOSITE", "UNIVERSAL"},
    "SYNERGY": {"ENERGY", "MISSILE", "SYNERGY", "UNIVERSAL"},
    "UNIVERSAL": {"BALLISTIC", "ENERGY", "MISSILE", "HYBRID", "COMPOSITE", "SYNERGY", "UNIVERSAL"},
}

# Hull mods that add fighter bays when present (built-in or installed), e.g. vanilla converted_hangar.
BAY_ADDING_HULL_MODS = {"converted_hangar": 1}


def _override_fits(slot_type: str, mount_override: str) -> bool:
    return bool(mount_override) and slot_type in MOUNT_OVERRIDE_FITS.get(mount_override, {mount_override})


def _weapon_slot_type_compatible(slot_type: str, weapon_type: str) -> bool:
    if slot_type == "UNIVERSAL":
        return True
    if slot_type == "HYBRID":
        return weapon_type in {"BALLISTIC", "ENERGY"}
    if slot_type == "COMPOSITE":
        return weapon_type in {"BALLISTIC", "MISSILE"}
    if slot_type == "SYNERGY":
        return weapon_type in {"ENERGY", "MISSILE"}
    if slot_type in {"BALLISTIC", "ENERGY", "MISSILE"}:
        return weapon_type == slot_type
    # Unrecognized slot type (e.g. a modded enum BridgeForge does not know): do not guess.
    return True


def _system_type_index(root: Path, vanilla_core: Path | None) -> dict[str, str]:
    """ship system id -> .system "type" (e.g. DRONE_LAUNCHER), vanilla first so the mod wins."""
    index: dict[str, str] = {}
    for base in ([vanilla_core] if vanilla_core else []) + [root]:
        folder = base / "data" / "shipsystems"
        for path in sorted(folder.glob("*.system")) if folder.is_dir() else []:
            spec = _load_lenient_json_file(path)
            if isinstance(spec, dict) and isinstance(spec.get("id"), str):
                index[spec["id"]] = str(spec.get("type") or "")
    return index


def _scan_carrier_bays_proposal(root: Path, result: ScanResult, vanilla_core: Path | None) -> None:
    """Pre-0.8 mods: propose fighter bays per hull from the evidence the old data still carries.

    The owner asked whether a description saying "carrier" is enough (2026-09-14). Across 25 mods it is
    not: descriptions mention carriers on non-carriers, and modern hulls use LAUNCH_BAY slots for drone
    launchers. The pre-0.8 `hangar` column (the author's own carrier record) and variant wings are what
    make a carrier; the LAUNCH_BAY slot count gives the number. Only runs on pre-0.8 ship_data.
    """
    path = root / "data" / "hulls" / "ship_data.csv"
    header = _csv_header(path) if path.is_file() else None
    if not header:
        return
    columns = [cell.strip().lower() for cell in header]
    if "fighter bays" in columns and "hangar" not in columns:
        return  # 0.8+ schema: a blank bay count there is the author's choice
    rows = _read_csv_rows_lenient(path) or []
    ships = _ship_file_index(root, None)
    systems = _system_type_index(root, vanilla_core)
    wings_by_hull: Counter[str] = Counter()
    variants_root = root / "data" / "variants"
    for variant in sorted(variants_root.rglob("*.variant")) if variants_root.is_dir() else []:
        spec = _load_lenient_json_file(variant)
        if isinstance(spec, dict) and isinstance(spec.get("hullId"), str) and isinstance(spec.get("wings"), list):
            wings_by_hull[spec["hullId"]] = max(wings_by_hull[spec["hullId"]], len(spec["wings"]))
    proposals: list[str] = []
    hints_only: list[str] = []
    for row in rows:
        normalized = {str(key).strip().lower(): (value or "").strip() for key, value in row.items() if key}
        hull_id = normalized.get("id", "")
        if not hull_id or hull_id.startswith("#"):
            continue
        spec = ships.get(hull_id) or {}
        if str(spec.get("hullSize") or "").upper() == "FIGHTER":
            continue
        hangar = _float_or(normalized.get("hangar"))
        wings = wings_by_hull.get(hull_id, 0)
        slots = sum(1 for slot in spec.get("weaponSlots") or [] if isinstance(slot, dict) and slot.get("type") == "LAUNCH_BAY")
        drones = systems.get(normalized.get("system id", ""), "") == "DRONE_LAUNCHER"
        evidence = [f"hangar:{int(hangar)}" if hangar else "", f"variant-wings:{wings}" if wings else "", f"launch-bays:{slots}" if slots else "", "system:DRONE_LAUNCHER (slots may be for drones)" if drones else ""]
        evidence = [item for item in evidence if item]
        if hangar or wings:
            proposed = slots or wings
            proposals.append(f"{hull_id}: {f'{proposed} bay(s)' if proposed else 'choose a number (no launch-bay slots)'} [{', '.join(evidence)}]")
        elif "CARRIER" in normalized.get("hints", "").upper() or "carrier" in normalized.get("designation", "").lower():
            hints_only.append(f"{hull_id}: hint only ({', '.join(evidence + ['CARRIER hint/designation'])})")
    if proposals or hints_only:
        result.add(
            id="carrier-bays-proposal",
            category="hulls",
            severity="medium",
            classification="REVIEW",
            confidence="MEDIUM",
            explanation="Pre-0.8a data: these hulls carried fighters under the old system (a `hangar` value or wings in the mod's variants), but 0.8a+ needs a `fighter bays` count. Proposed counts come from each hull's LAUNCH_BAY slots, or its variants' wings. A description mentioning carriers is not treated as evidence, and hint-only hulls get no number. Approve per hull before applying.",
            file=_relative(root, path),
            evidence=proposals + hints_only,
        )


def _scan_unresolved_content_references(root: Path, result: ScanResult, vanilla_core: Path | None) -> None:
    """Hull mods, wings, weapons and hulls used by the mod's data but defined by neither it nor vanilla.

    Communist Clouds builds `vayra_red_army` into its hulls and fields `vayra_*` wings and weapons: it
    is a Vayra's Sector add-on, which its mod_info didn't declare and no check noticed (2026-09-14).
    """
    if vanilla_core is None:
        return
    weapons = set(_csv_id_index(root / "data" / "weapons" / "weapon_data.csv", vanilla_core / "data" / "weapons" / "weapon_data.csv")) | set(_wpn_type_size_index(root, vanilla_core))
    hull_mods = set(_csv_id_index(root / "data" / "hullmods" / "hull_mods.csv", vanilla_core / "data" / "hullmods" / "hull_mods.csv"))
    wings = set(_csv_id_index(root / "data" / "hulls" / "wing_data.csv", vanilla_core / "data" / "hulls" / "wing_data.csv"))
    skins = _skin_index(root, vanilla_core)
    hulls = set(_ship_file_index(root, vanilla_core)) | set(skins)
    if not (weapons and hull_mods and wings and hulls):
        return
    missing: dict[str, dict[str, set[str]]] = {"hullmod": {}, "wing": {}, "weapon": {}, "hull": {}}

    def check(kind: str, ident: object, known: set[str], where: str) -> None:
        if isinstance(ident, str) and ident.strip() and ident not in known:
            missing[kind].setdefault(ident, set()).add(where)

    data = root / "data"
    for path in sorted(data.rglob("*")) if data.is_dir() else []:
        if path.suffix.lower() not in (".variant", ".ship", ".skin"):
            continue
        spec = _load_lenient_json_file(path)
        if not isinstance(spec, dict):
            continue
        where = _relative(root, path)
        for key in ("hullMods", "permaMods", "sMods", "builtInMods", "removeBuiltInMods"):
            for ident in spec.get(key) or []:
                check("hullmod", ident, hull_mods, where)
        for key in ("wings", "builtInWings"):
            for ident in spec.get(key) or []:
                check("wing", ident, wings, where)
        for group in spec.get("weaponGroups") or []:
            if isinstance(group, dict) and isinstance(group.get("weapons"), dict):
                for ident in group["weapons"].values():
                    check("weapon", ident, weapons, where)
        if isinstance(spec.get("builtInWeapons"), dict):
            for ident in spec["builtInWeapons"].values():
                check("weapon", ident, weapons, where)
        if path.suffix.lower() == ".variant":
            check("hull", spec.get("hullId"), hulls, where)
        if path.suffix.lower() == ".skin":
            check("hull", spec.get("baseHullId"), hulls, where)
    unresolved = [(kind, ident, files) for kind, table in missing.items() for ident, files in sorted(table.items())]
    if not unresolved:
        return
    prefixes = Counter(ident.split("_", 1)[0] + "_" for _kind, ident, _files in unresolved if "_" in ident)
    prefix_note = [f"common prefix: {prefix} ({count} ids)" for prefix, count in prefixes.most_common(3) if count > 1]
    declares = bool(result.metadata.get("dependencies") or result.metadata.get("requiredDependencies"))
    result.add(
        id="content-reference-unresolved",
        category="dependencies",
        severity="high",
        classification="REVIEW" if declares else "MANUAL",
        confidence="HIGH",
        explanation="The mod's hulls, skins or variants use hull mods, wings, weapons or hulls that neither the mod nor vanilla defines. They must come from another mod, which then has to be installed (and declared in mod_info.json), or the specs fail to load." + (" The mod declares dependencies that may provide them; confirm." if declares else " The mod declares no dependency."),
        evidence=prefix_note + [f"{kind}:{ident} ({len(files)} file(s))" for kind, ident, files in unresolved[:25]] + ([f"... {len(unresolved) - 25} more"] if len(unresolved) > 25 else []),
    )


def _scan_variant_validity(root: Path, result: ScanResult, vanilla_core: Path | None) -> None:
    """Cross-check .variant files against their resolved hull's bays, OP budget, and slot rules.

    hullId is resolved through .skin baseHullId chains first (a variant commonly targets a skin's
    id, not the underlying hull's). A hull that cannot be resolved to both a .ship file and a
    ship_data.csv row (mod or vanilla) is left alone entirely: BridgeForge does not have enough
    evidence to compute a bay/OP budget or slot compatibility for it, and reports UNKNOWN, not a
    finding, for such gaps elsewhere; it stays silent here rather than guessing.
    """
    variants_root = root / "data" / "variants"
    if not variants_root.is_dir():
        return

    ship_files = _ship_file_index(root, vanilla_core)
    skins = _skin_index(root, vanilla_core)
    ship_data = _csv_id_index(
        root / "data" / "hulls" / "ship_data.csv",
        (vanilla_core / "data" / "hulls" / "ship_data.csv") if vanilla_core else None,
    )
    weapon_data = _csv_id_index(
        root / "data" / "weapons" / "weapon_data.csv",
        (vanilla_core / "data" / "weapons" / "weapon_data.csv") if vanilla_core else None,
    )
    weapon_specs = _wpn_type_size_index(root, vanilla_core)
    hull_mod_costs = _csv_id_index(
        root / "data" / "hullmods" / "hull_mods.csv",
        (vanilla_core / "data" / "hullmods" / "hull_mods.csv") if vanilla_core else None,
    )
    wing_data = _csv_id_index(
        root / "data" / "hulls" / "wing_data.csv",
        (vanilla_core / "data" / "hulls" / "wing_data.csv") if vanilla_core else None,
    )

    for path in sorted(variants_root.rglob("*.variant")):
        data = _load_lenient_json_file(path)
        if not isinstance(data, dict):
            continue
        relative = _relative(root, path)
        variant_id = data.get("variantId") or path.stem
        raw_hull_id = data.get("hullId")
        if not isinstance(raw_hull_id, str) or not raw_hull_id.strip():
            continue
        resolved_hull_id = _resolve_hull_id(raw_hull_id.strip(), skins)
        ship_json = ship_files.get(resolved_hull_id)
        row = ship_data.get(resolved_hull_id)
        if ship_json is None or row is None:
            continue  # Unresolvable hull: UNKNOWN, handled elsewhere; no finding fabricated here.
        if str(ship_json.get("hullSize") or "").strip().upper() == "FIGHTER":
            # Fighter-size hulls are not refit through the OP-budget/bays system: their ship_data.csv
            # "ordnance points" is almost always 0 (verified against vanilla: 30/32 fighter hulls), and
            # any hullMods/wings on a fighter variant are baked into its fixed design, not player-fitted.
            # Checking them against a budget/bay count that does not apply produces false positives.
            continue

        wings = data.get("wings")
        wing_list = [w for w in wings if isinstance(w, str)] if isinstance(wings, list) else []
        built_in_wings = ship_json.get("builtInWings")
        built_in_wing_count = len(built_in_wings) if isinstance(built_in_wings, list) else 0
        fighter_bays = int(_float_or(row.get("fighter bays")))
        # Bays can also come from hull mods (e.g. converted_hangar), built in or installed by the variant.
        bay_mods = set(ship_json.get("builtInMods") or []) | {
            mod for key in ("hullMods", "permaMods") for mod in (data.get(key) or []) if isinstance(mod, str)
        }
        fighter_bays += sum(BAY_ADDING_HULL_MODS.get(mod, 0) for mod in bay_mods)
        total_wings = len(wing_list) + built_in_wing_count
        if total_wings > fighter_bays:
            result.add(
                id="variant-wings-exceed-bays",
                category="variants",
                severity="high",
                classification="REVIEW",
                confidence="DETERMINISTIC",
                explanation=(
                    f"Variant '{variant_id}' equips {len(wing_list)} wing(s) plus {built_in_wing_count} "
                    f"built-in wing(s) ({total_wings} total) but hull '{resolved_hull_id}' has only "
                    f"{fighter_bays} fighter bay(s) in ship_data.csv. Extra wings will not deploy."
                ),
                file=relative,
                evidence=[f"variant:{variant_id}", f"hull:{resolved_hull_id}", f"wings:{len(wing_list)}", f"built-in-wings:{built_in_wing_count}", f"fighter-bays:{fighter_bays}"],
            )

        built_in_weapon_slots = ship_json.get("builtInWeapons")
        built_in_weapon_slot_ids = set(built_in_weapon_slots.keys()) if isinstance(built_in_weapon_slots, dict) else set()
        slot_by_id: dict[str, dict] = {}
        for slot in ship_json.get("weaponSlots") or []:
            if isinstance(slot, dict) and isinstance(slot.get("id"), str):
                slot_by_id[slot["id"]] = slot

        weapon_op_total = 0.0
        weapon_groups = data.get("weaponGroups") if isinstance(data.get("weaponGroups"), list) else []
        for group in weapon_groups:
            if not isinstance(group, dict):
                continue
            weapons = group.get("weapons")
            if not isinstance(weapons, dict):
                continue
            for slot_id, weapon_id in weapons.items():
                if slot_id in built_in_weapon_slot_ids or not isinstance(weapon_id, str):
                    continue
                w_row = weapon_data.get(weapon_id)
                if w_row is None:
                    continue
                weapon_op_total += _float_or(w_row.get("OPs"))

        built_in_mods = set(ship_json.get("builtInMods") or [])
        hull_size = str(ship_json.get("hullSize") or "").strip().upper()
        cost_column = HULL_MOD_COST_COLUMN_BY_SIZE.get(hull_size, "cost_cruiser")
        hull_mod_total = 0.0
        hull_mods = data.get("hullMods") if isinstance(data.get("hullMods"), list) else []
        for mod_id in hull_mods:
            if not isinstance(mod_id, str) or mod_id in built_in_mods:
                continue
            hm_row = hull_mod_costs.get(mod_id)
            if hm_row is None:
                continue
            hull_mod_total += _float_or(hm_row.get(cost_column))

        flux_vents = _float_or(data.get("fluxVents"))
        flux_caps = _float_or(data.get("fluxCapacitors"))

        wing_op_total = 0.0
        for wing_id in wing_list:
            w_row = wing_data.get(wing_id)
            if w_row is None:
                continue
            wing_op_total += _float_or(w_row.get("op cost"))

        ordnance_points = _float_or(row.get("ordnance points"))
        total_op = weapon_op_total + hull_mod_total + flux_vents + flux_caps + wing_op_total
        # Skill/hullmod OP-cost modifiers (e.g. Ordnance Expert, Weapon/Field Modulation) legitimately
        # let a live loadout exceed the *raw* budget in-game; a small tolerance keeps this check from
        # flagging those borderline, still-in-game-valid loadouts instead of genuine authoring bugs.
        tolerance = max(3.0, ordnance_points * 0.05)
        if total_op > ordnance_points + tolerance:
            result.add(
                id="variant-op-over-budget",
                category="variants",
                severity="high",
                classification="REVIEW",
                confidence="DETERMINISTIC",
                explanation=(
                    f"Variant '{variant_id}' costs {total_op:.1f} raw OP (weapons {weapon_op_total:.1f} + "
                    f"hullmods {hull_mod_total:.1f} + flux vents {flux_vents:.1f} + flux capacitors "
                    f"{flux_caps:.1f} + wings {wing_op_total:.1f}) against hull '{resolved_hull_id}''s "
                    f"{ordnance_points:.1f} ordnance points, beyond a {tolerance:.1f} OP tolerance for "
                    "skill/hullmod OP modifiers. Non-built-in costs only; verify in the refit screen."
                ),
                file=relative,
                evidence=[
                    f"variant:{variant_id}",
                    f"hull:{resolved_hull_id}",
                    f"weapons-op:{weapon_op_total:.1f}",
                    f"hullmods-op:{hull_mod_total:.1f}",
                    f"flux-vents:{flux_vents:.1f}",
                    f"flux-capacitors:{flux_caps:.1f}",
                    f"wings-op:{wing_op_total:.1f}",
                    f"total-op:{total_op:.1f}",
                    f"budget:{ordnance_points:.1f}",
                ],
            )

        for group in weapon_groups:
            if not isinstance(group, dict):
                continue
            weapons = group.get("weapons")
            if not isinstance(weapons, dict):
                continue
            for slot_id, weapon_id in weapons.items():
                if not isinstance(weapon_id, str):
                    continue
                slot = slot_by_id.get(slot_id)
                if slot is None:
                    continue
                slot_type = str(slot.get("type") or "").strip().upper()
                if slot_type in WEAPON_SLOT_SKIP_TYPES:
                    continue
                spec = weapon_specs.get(weapon_id)
                if spec is None:
                    continue
                slot_size = str(slot.get("size") or "").strip().upper()
                weapon_size = spec.get("size", "")
                weapon_type = spec.get("type", "")
                size_mismatch = WEAPON_SLOT_SIZE_RANK.get(weapon_size, 0) > WEAPON_SLOT_SIZE_RANK.get(slot_size, 0)
                type_mismatch = weapon_type and not (
                    _weapon_slot_type_compatible(slot_type, weapon_type)
                    or _override_fits(slot_type, spec.get("mount_override", ""))
                )
                if size_mismatch or type_mismatch:
                    reasons = []
                    if size_mismatch:
                        reasons.append(f"weapon size {weapon_size} exceeds slot size {slot_size}")
                    if type_mismatch:
                        reasons.append(f"weapon type {weapon_type} incompatible with slot type {slot_type}")
                    result.add(
                        id="variant-weapon-slot-mismatch",
                        category="variants",
                        severity="high",
                        classification="REVIEW",
                        confidence="DETERMINISTIC",
                        explanation=(
                            f"Variant '{variant_id}' puts weapon '{weapon_id}' in slot '{slot_id}' on hull "
                            f"'{resolved_hull_id}': {'; '.join(reasons)}."
                        ),
                        file=relative,
                        evidence=[f"variant:{variant_id}", f"hull:{resolved_hull_id}", f"slot:{slot_id}", f"slot-type:{slot_type}", f"slot-size:{slot_size}", f"weapon:{weapon_id}", f"weapon-type:{weapon_type}", f"weapon-size:{weapon_size}"],
                    )


def _hull_hints(row: dict[str, str]) -> set[str]:
    return {token.strip().upper() for token in (row.get("hints") or "").split(",") if token.strip()}


def _scan_description_missing(root: Path, result: ScanResult, vanilla_core: Path | None = None) -> None:
    """A mod hull/weapon/ship-system id with no matching descriptions.csv row of the right type.

    descriptions.csv rows are keyed by id, and Starsector does not require a mod to redeclare a row
    for an id it did not otherwise remove: a mod that reuses/rebalances a vanilla id (in weapon_data,
    ship_data, or ship_systems) inherits vanilla's description for that id unless it overrides it. So
    an id is "described" if it has a row in the mod's OWN descriptions.csv OR (when vanilla_core is
    given) vanilla's.
    """
    descriptions_path = root / "data" / "strings" / "descriptions.csv"
    described: dict[str, set[str]] = {}
    vanilla_descriptions_path = (vanilla_core / "data" / "strings" / "descriptions.csv") if vanilla_core else None
    if vanilla_descriptions_path is not None:
        for row in _read_csv_rows_lenient(vanilla_descriptions_path) or []:
            row_id = (row.get("id") or "").strip()
            row_type = (row.get("type") or "").strip().upper()
            if row_id and not row_id.startswith("#"):
                described.setdefault(row_id, set()).add(row_type)
    for row in _read_csv_rows(descriptions_path) or []:
        row_id = (row.get("id") or "").strip()
        row_type = (row.get("type") or "").strip().upper()
        if row_id and not row_id.startswith("#"):
            described.setdefault(row_id, set()).add(row_type)

    ship_files = _ship_file_index(root, None)

    ship_data_path = root / "data" / "hulls" / "ship_data.csv"
    for row in _read_csv_rows(ship_data_path) or []:
        hull_id = (row.get("id") or "").strip()
        if not hull_id or hull_id.startswith("#"):
            continue
        hints = _hull_hints(row)
        if "HIDE_IN_CODEX" in hints or "MODULE" in hints:
            continue
        ship_json = ship_files.get(hull_id)
        if isinstance(ship_json, dict) and str(ship_json.get("hullSize") or "").strip().upper() == "FIGHTER":
            continue
        if "SHIP" in described.get(hull_id, set()):
            continue
        result.add(
            id="description-missing",
            category="content",
            severity="low",
            classification="REVIEW",
            confidence="DETERMINISTIC",
            explanation=f"Hull '{hull_id}' has no SHIP-type row in data/strings/descriptions.csv; the codex/refit screen will show a blank description.",
            file=_relative(root, ship_data_path),
            evidence=[f"hull:{hull_id}"],
        )

    weapon_data_path = root / "data" / "weapons" / "weapon_data.csv"
    for row in _read_csv_rows(weapon_data_path) or []:
        weapon_id = (row.get("id") or "").strip()
        if not weapon_id or weapon_id.startswith("#"):
            continue
        hints = {token.strip().upper() for token in (row.get("hints") or "").split(",") if token.strip()}
        if "SYSTEM" in hints:
            continue
        if not (row.get("OPs") or "").strip():
            continue
        if "WEAPON" in described.get(weapon_id, set()):
            continue
        result.add(
            id="description-missing",
            category="content",
            severity="low",
            classification="REVIEW",
            confidence="DETERMINISTIC",
            explanation=f"Weapon '{weapon_id}' has no WEAPON-type row in data/strings/descriptions.csv; the codex/refit screen will show a blank description.",
            file=_relative(root, weapon_data_path),
            evidence=[f"weapon:{weapon_id}"],
        )

    ship_systems_path = root / "data" / "shipsystems" / "ship_systems.csv"
    for row in _read_csv_rows(ship_systems_path) or []:
        system_id = (row.get("id") or "").strip()
        if not system_id or system_id.startswith("#"):
            continue
        if "SHIP_SYSTEM" in described.get(system_id, set()):
            continue
        result.add(
            id="description-missing",
            category="content",
            severity="low",
            classification="REVIEW",
            confidence="DETERMINISTIC",
            explanation=f"Ship system '{system_id}' has no SHIP_SYSTEM-type row in data/strings/descriptions.csv; the codex will show a blank description.",
            file=_relative(root, ship_systems_path),
            evidence=[f"ship-system:{system_id}"],
        )


def _asset_exists(candidate: str, root: Path, vanilla_core: Path | None) -> bool:
    normalized = candidate.strip().lstrip("/\\").replace("\\", "/")
    if not normalized:
        return True
    if (root / normalized).is_file():
        return True
    if vanilla_core is not None and (vanilla_core / normalized).is_file():
        return True
    return False


def _report_asset_reference_missing(result: ScanResult, root: Path, vanilla_core: Path | None, file: str, field: str, candidate: str) -> None:
    if _asset_exists(candidate, root, vanilla_core):
        return
    if vanilla_core is None:
        result.add(
            id="asset-reference-missing",
            category="assets",
            severity="low",
            classification="UNKNOWN",
            confidence="LOW",
            explanation=f"'{field}' references '{candidate}', which is not present in this mod. No --vanilla-core was supplied, so BridgeForge cannot tell this apart from a legitimate vanilla asset path.",
            file=file,
            evidence=[f"field:{field}", f"path:{candidate}", "no vanilla core supplied"],
        )
        return
    result.add(
        id="asset-reference-missing",
        category="assets",
        severity="medium",
        classification="REVIEW",
        confidence="DETERMINISTIC",
        explanation=f"'{field}' references '{candidate}', which exists in neither this mod nor the supplied vanilla core. The asset will fail to load.",
        file=file,
        evidence=[f"field:{field}", f"path:{candidate}"],
    )


def _walk_sounds_json_files(node: object) -> list[tuple[str, str | None]]:
    """Every ('file', 'source'-or-None) pair found anywhere in a sounds.json structure."""
    found: list[tuple[str, str | None]] = []
    if isinstance(node, dict):
        file_value = node.get("file")
        if isinstance(file_value, str) and file_value.strip():
            source_value = node.get("source")
            found.append((file_value.strip(), source_value.strip() if isinstance(source_value, str) and source_value.strip() else None))
        for value in node.values():
            found.extend(_walk_sounds_json_files(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_walk_sounds_json_files(item))
    return found


def _scan_asset_reference_missing(root: Path, result: ScanResult, vanilla_core: Path | None) -> None:
    """A sprite/sound path named in mod data that resolves to no file in the mod or vanilla."""
    for path in sorted(root.rglob("*.ship")):
        data = _load_lenient_json_file(path)
        if not isinstance(data, dict):
            continue
        sprite = data.get("spriteName")
        if isinstance(sprite, str) and sprite.strip():
            _report_asset_reference_missing(result, root, vanilla_core, _relative(root, path), "spriteName", sprite)

    wpn_fields = ("turretSprite", "hardpointSprite", "turretUnderSprite", "hardpointUnderSprite", "turretGunSprite", "hardpointGunSprite")
    for path in sorted(root.rglob("*.wpn")):
        data = _load_lenient_json_file(path)
        if not isinstance(data, dict):
            continue
        for field in wpn_fields:
            value = data.get(field)
            if isinstance(value, str) and value.strip():
                _report_asset_reference_missing(result, root, vanilla_core, _relative(root, path), field, value)

    for path in sorted(root.rglob("*.proj")):
        data = _load_lenient_json_file(path)
        if not isinstance(data, dict):
            continue
        for field in ("sprite", "bulletSprite"):
            value = data.get(field)
            if isinstance(value, str) and value.strip():
                _report_asset_reference_missing(result, root, vanilla_core, _relative(root, path), field, value)

    sounds_path = root / "data" / "config" / "sounds.json"
    if sounds_path.is_file():
        data = _load_lenient_json_file(sounds_path)
        if isinstance(data, dict):
            relative = _relative(root, sounds_path)
            for file_value, source_value in _walk_sounds_json_files(data):
                if source_value and not source_value.lower().endswith((".bin", ".zip", ".jar")):
                    candidate = f"{source_value.rstrip('/')}/{file_value.lstrip('/')}"
                elif source_value:
                    continue  # Packed inside a binary/archive container; not independently verifiable.
                else:
                    candidate = file_value
                _report_asset_reference_missing(result, root, vanilla_core, relative, "sounds.json:file", candidate)


def _drop_vanilla_registered_weapon_specs(result: ScanResult, vanilla_core: Path | None) -> None:
    """A local .wpn whose id vanilla's weapon_data.csv registers is an override, not unregistered.

    Blackrock's blinker_green.wpn replaces vanilla's own; vanilla-path-shadowing already reports the
    override (critical), so also calling it 'unregistered' is noise.
    """
    if vanilla_core is None:
        return
    vanilla_ids = _registered_csv_ids(vanilla_core / "data" / "weapons" / "weapon_data.csv") or set()
    if not vanilla_ids:
        return

    def overrides_vanilla(finding) -> bool:
        return finding.id == "local-weapon-spec-unregistered" and any(
            str(item).startswith("weapon:") and str(item)[len("weapon:"):] in vanilla_ids for item in finding.evidence
        )

    result.findings[:] = [finding for finding in result.findings if not overrides_vanilla(finding)]


def scan_mod(input_path: Path, target: TargetProfile | None = None, vanilla_core: Path | None = None) -> ScanResult:
    root = input_path.expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Input mod directory does not exist: {root}")
    vanilla_root = vanilla_core.expanduser().resolve() if vanilla_core is not None else None
    if vanilla_root is not None and not vanilla_root.is_dir():
        vanilla_root = None
    result = ScanResult(input_path=root, target=target or TargetProfile())
    for path in sorted(root.rglob("*")):
        if path.is_file():
            result.files.append({"path": _relative(root, path), "size_bytes": path.stat().st_size})
    _scan_metadata(root, result)
    _scan_jars(root, result)
    _scan_sources(root, result)
    _scan_assets(root, result)
    _scan_configured_class_integrity(root, result)
    _annotate_source_reachability(root, result)
    _scan_campaign_identifier_context(root, result)
    _attribute_library_usage(result)
    _dependency_compatibility_context(result)
    _infer_environment(result)
    _scan_procgen_rows(root, result, vanilla_root)
    _scan_faction_known_lists(root, result, vanilla_root)
    _scan_rules_condition_defects(root, result, vanilla_root)
    _scan_design_type_colors(root, result, vanilla_root)
    _scan_shiproles(root, result, vanilla_root)
    _scan_carrier_rework_gap(root, result)
    _scan_black_hole_flag(root, result)
    _scan_mod_info_game_version(result)
    _scan_vanilla_path_shadowing(root, result, vanilla_root)
    _drop_vanilla_registered_weapon_specs(result, vanilla_root)
    _scan_script_sandbox_forbidden_api(root, result)
    _scan_bundled_library_classes(root, result)
    _scan_vanilla_duplicated_classes(root, result, vanilla_root)
    _scan_obfuscated_internal_api_use(root, result)
    _scan_csv_design_type_column(root, result)
    _scan_undeclared_library_dependency(root, result)
    _scan_orbit_period_hazards(root, result)
    _scan_module_captain_personality_risk(root, result)
    _scan_spawned_ship_captain_personality_risk(root, result)
    _scan_mod_info_triage_banner(root, result)
    _scan_data_class_references_missing(root, result, vanilla_root)
    _scan_hardcoded_hyperspace_coordinates(root, result)
    _scan_hardcoded_terrain_grid_size(root, result)
    _scan_variant_validity(root, result, vanilla_root)
    _scan_unresolved_content_references(root, result, vanilla_root)
    _scan_carrier_bays_proposal(root, result, vanilla_root)
    _scan_description_missing(root, result, vanilla_root)
    _scan_asset_reference_missing(root, result, vanilla_root)
    return result
