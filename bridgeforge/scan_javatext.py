"""Text helpers for scanning Java source: comment blanking, method bodies, call arguments, brace bodies."""
from __future__ import annotations

import re


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


def _brace_body(text: str, open_brace: int) -> str:
    depth = 0
    for index in range(open_brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[open_brace:index + 1]
    return text[open_brace:]


def _call_argument_count(text: str, index: int) -> int:
    """Top-level arguments of the call whose argument list starts at or after `index` (the first '(' from
    there); string literals are expected blanked or quote-free. 0 when the list does not close."""
    open_index = text.find("(", index)
    if open_index < 0:
        return 0
    depth, count, seen = 0, 1, False
    for i in range(open_index, len(text)):
        char = text[i]
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
            if depth == 0:
                return count if seen else 0
        elif char == "," and depth == 1:
            count += 1
        elif depth >= 1 and not char.isspace():
            seen = True
    return 0


_MOD_GUARD_VARIABLE = re.compile(r"\bboolean\s+(\w+)\s*=[^;]*isModEnabled\s*\(")
_IF_BLOCK = re.compile(r"\bif\s*\(([^{};]*)\)\s*\{")


def _blank_mod_guarded_blocks(text: str) -> str:
    """`text` with the body of every `if (...) { }` whose condition tests that another mod is enabled replaced by spaces (newlines kept).

    A mission that names `swp_gryphon_xiv_eli` inside `if (swp) { }`, `swp` being `boolean swp = ...isModEnabled("swp")`, never
    reaches the game without that mod, so its variants are not this mod's missing references (Vayra's Ship Pack and Kadur Remnant,
    REG-20261012). A negated test (`!swp`) guards nothing and an `else` branch is left as it is. Call on comment-blanked text."""
    guard_variables = set(_MOD_GUARD_VARIABLE.findall(text))
    blanked = list(text)
    for match in _IF_BLOCK.finditer(text):
        condition = match.group(1)
        positive_variable = any(re.search(rf"(?<![!\w]){re.escape(name)}\b", condition) for name in guard_variables)
        if "isModEnabled" not in condition.replace("!isModEnabled", "") and not positive_variable:
            continue
        end = match.end() - 1 + len(_brace_body(text, match.end() - 1)) - 1
        for index in range(match.end(), end):
            if blanked[index] != "\n":
                blanked[index] = " "
    return "".join(blanked)

