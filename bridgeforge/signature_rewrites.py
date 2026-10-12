"""Calls whose signature RC8 changed, with an exact RC8 equivalent (ROADMAP 41; Ironclads, javap 2026-10-04).

Each rule names a call and the argument count of its pre-RC8 form; the RC8 form is mechanical:

- `EconomyAPI.addMarket(m)` -> `addMarket(m, true)`: RC8 has only addMarket(MarketAPI, boolean withJunkAndChatter);
  vanilla passes true (starfarer.api.zip, Misc/SectorGen).
- `new TileParams(tiles, w, h, cat, key, wide, high)` -> `..., null)`: RC8 added a trailing String name; vanilla
  passes null.
- `Misc.addNebulaFromPNG(png, x, y, location, cat, key, wide, high, terrain)` -> `..., null)`: same added name.
- `MarketAPI.addCondition(id, true|false, param)` -> `addCondition(id, param)`: RC8 has (String) and
  (String, Object) only; 0.7's boolean flag is gone.

`RepActionEnvelope(action, param, message, boolean)` is not here: RC8 also has a 4-argument form
(action, param, TextPanelAPI, boolean), so the rewrite depends on the third argument's type.
"""
from __future__ import annotations

import re

from .procgen_args import _arguments

_BOOLEAN = re.compile(r"^\s*(true|false)\s*$")
RULES = [
    # (name, call pattern ending at '(', old argument count, test on args, rewrite of args)
    ("addMarket", re.compile(r"\.\s*addMarket\s*\("), 1, lambda a: True, lambda a: a + [" true"]),
    ("TileParams", re.compile(r"\bnew\s+(?:[\w.]+\.)?TileParams\s*\("), 7, lambda a: True, lambda a: a + [" null"]),
    ("addNebulaFromPNG", re.compile(r"\baddNebulaFromPNG\s*\("), 9, lambda a: True, lambda a: a + [" null"]),
    ("addCondition", re.compile(r"\.\s*addCondition\s*\("), 3, lambda a: bool(_BOOLEAN.match(a[1])), lambda a: [a[0], a[2]]),
]


def suspects(text: str) -> list[tuple[int, str, int, int]]:
    """(line, rule, start of the argument list '(', end ')') for each old-form call in comment-blanked source."""
    found = []
    for name, pattern, count, test, _ in RULES:
        for match in pattern.finditer(text):
            open_index = match.end() - 1
            args = _arguments(text, open_index)
            if args is None or len(args) != count or (count == 1 and not args[0].strip()) or not test(args):
                continue
            close = _close(text, open_index)
            found.append((text.count("\n", 0, match.start()) + 1, name, open_index, close))
    return sorted(found, key=lambda f: f[2])


def _close(text: str, open_index: int) -> int:
    depth = 0
    for i in range(open_index, len(text)):
        if text[i] in "([{":
            depth += 1
        elif text[i] in ")]}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def rewrite(text: str, blank: str) -> tuple[str, int]:
    """Apply every rule to `text`, locating calls in `blank` (same offsets, comments and strings blanked)."""
    rules = {name: fix for name, _, _, _, fix in RULES}
    out, last, count = [], 0, 0
    for _, name, open_index, close in suspects(blank):
        if open_index < last or close < 0:
            continue
        # Argument boundaries from the blanked text (a comma inside a string literal is not one), text from the source.
        args, start, depth = [], open_index + 1, 0
        for i in range(open_index, close + 1):
            if blank[i] in "([{":
                depth += 1
            elif blank[i] in ")]}":
                depth -= 1
            if (blank[i] == "," and depth == 1) or i == close:
                args.append(text[start:i])
                start = i + 1
        out.append(text[last:open_index + 1] + ",".join(rules[name](args)) + ")")
        last = close + 1
        count += 1
    out.append(text[last:])
    return "".join(out), count
