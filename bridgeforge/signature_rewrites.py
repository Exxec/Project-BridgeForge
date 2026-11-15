"""Calls whose signature RC8 changed, with an exact RC8 equivalent (ROADMAP 41; Ironclads, javap 2026-10-04).

Each rule names a call and the argument count of its pre-RC8 form; the RC8 form is mechanical:

- `EconomyAPI.addMarket(m)` -> `addMarket(m, true)`: RC8 has only addMarket(MarketAPI, boolean withJunkAndChatter);
  vanilla passes true (starfarer.api.zip, Misc/SectorGen).
- `new TileParams(tiles, w, h, cat, key, wide, high)` -> `..., null)`: RC8 added a trailing String name; vanilla
  passes null.
- `Misc.addNebulaFromPNG(png, x, y, location, cat, key, wide, high, terrain)` -> `..., null)`: same added name. A 9-argument call
  ending in a StarAge is RC8's own other overload and is left alone (Templars, 2026-10-13).
- `MarketAPI.addCondition(id, true|false, param)` -> `addCondition(id, param)`: RC8 has (String) and
  (String, Object) only; 0.7's boolean flag is gone.

Considered for item 73 B2 on 2026-10-18 and NOT added (no RC8 member is involved, so there is no javap line to cite): the three
verified agent fixes in Mountain-and-Sea and Smol-Shippack were (1) deleting a stray `@Override` on a private helper
(SHAGen.initFactionRelationships), (2) renaming a public class to its file name (smol_expansion_ModPlugin -> smol_ModPlugin),
(3) stripping an unresolvable GraphicsLib integration from SHModPlugin (a judgement about a missing dependency). (1) and (2) are
Java-language fixes that would need their own fixer with a javac-error trigger; (3) stays with an agent or the owner.

`RepActionEnvelope(action, param, message, boolean)` is not here: RC8 also has a 4-argument form
(action, param, TextPanelAPI, boolean), so the rewrite depends on the third argument's type.

`TARGET_RULES` (2026-11-15) are for a target newer than RC8 (0.98.5a-RC3, `C:\\Games\\Starsector-0.98.5a-RC3`). Their
new forms do not compile on RC8, so each is gated on the target core's own API jar (`linkage.core_index`): it applies
only when the target lacks the old member and has the new one. No target core given, no gated rule. Evidence, from
`api-diff` RC8 -> 0.98.5a-RC3 and both versions' `starfarer.api.zip` sources:

- `new ShipAIConfig()` -> `new ShipAIConfig(null)`: 0.98.5a has only `ShipAIConfig(ShipAPI shipIfAny)`, whose body runs
  only for a non-null ship; the field defaults are RC8's, so null keeps RC8's behaviour exactly. 30 mods use it.
- `x.isBeingIgnored()` -> `x.isBeingIgnored(false)`: RC8's javadoc "being mostly ignored by enemy ships"; 0.98.5a's
  `isBeingIgnored(boolean byAlly)` returns false when byAlly is true.
- `Misc.getOfficerSalary(p)` -> `(p, Misc.isMercenary(p), false, false)`: RC8's one-argument form was exactly that
  formula; 0.98.5a's four-argument form with both checks false applies no inactive or civilised-space multiplier.
  Only a plain variable or field is rewritten, so the argument is never evaluated twice.
- `OfficerManagerEvent.pickPortraitPreferNonDuplicate(f, g)` -> `(f, g, null)` (item 91): 0.98.5a's body is RC8's plus
  `if (random != null) return picker.pick(random);`, so null is RC8's `picker.pick()`; vanilla itself passes null in
  `PromoteOfficerIntel` (`vanilla-migration`, 2026-11-15). Kadur Remnant's hand port.
- `Misc.getOfficerSalary(p, b)` -> `(p, b, false, false)`: the descriptor survived but its boolean changed meaning from
  `mercenary` to `checkIfInPopulatedSystem` (the only same-signature parameter rename between the two source zips), so
  the call compiles and silently computes something else.
"""
from __future__ import annotations

import re
from pathlib import Path

from .procgen_args import _arguments

_BOOLEAN = re.compile(r"^\s*(true|false)\s*$")
_PLAIN_REFERENCE = re.compile(r"^\s*[A-Za-z_$][\w$]*(?:\s*\.\s*[A-Za-z_$][\w$]*)*\s*$")
RULES = [
    # (name, call pattern ending at '(', old argument count, test on args, rewrite of args)
    ("addMarket", re.compile(r"\.\s*addMarket\s*\("), 1, lambda a: True, lambda a: a + [" true"]),
    ("TileParams", re.compile(r"\bnew\s+(?:[\w.]+\.)?TileParams\s*\("), 7, lambda a: True, lambda a: a + [" null"]),
    # RC8 still has a 9-argument addNebulaFromPNG ending in a StarAge (javap 2026-10-13); only 0.7's form, ending in a terrain String, is gone.
    ("addNebulaFromPNG", re.compile(r"\baddNebulaFromPNG\s*\("), 9, lambda a: "StarAge" not in a[8], lambda a: a + [" null"]),
    ("addCondition", re.compile(r"\.\s*addCondition\s*\("), 3, lambda a: bool(_BOOLEAN.match(a[1])), lambda a: [a[0], a[2]]),
]

_API = "com/fs/starfarer/api/"
_PERSON = "Lcom/fs/starfarer/api/characters/PersonAPI;"
_SALARY_GATE = (_API + "util/Misc", ("getOfficerSalary", f"({_PERSON})F"), ("getOfficerSalary", f"({_PERSON}ZZZ)F"))
_PORTRAIT_OLD = f"(L{_API}campaign/FactionAPI;L{_API}characters/FullName$Gender;)Ljava/lang/String;"
_PORTRAIT_GATE = (_API + "impl/campaign/events/OfficerManagerEvent", ("pickPortraitPreferNonDuplicate", _PORTRAIT_OLD),
                  ("pickPortraitPreferNonDuplicate", _PORTRAIT_OLD.replace(";)", ";Ljava/util/Random;)")))
# As RULES, plus a gate: (owner class, member the target must lack, member it must have), names as in the class file.
TARGET_RULES = [
    ("ShipAIConfig", re.compile(r"\bnew\s+(?:[\w.]+\.)?ShipAIConfig\s*\("), 0, lambda a: True, lambda a: ["null"],
     (_API + "combat/ShipAIConfig", ("<init>", "()V"), ("<init>", f"(L{_API}combat/ShipAPI;)V"))),
    ("isBeingIgnored", re.compile(r"\.\s*isBeingIgnored\s*\("), 0, lambda a: True, lambda a: ["false"],
     (_API + "combat/ShipAPI", ("isBeingIgnored", "()Z"), ("isBeingIgnored", "(Z)Z"))),
    ("getOfficerSalary", re.compile(r"\bMisc\s*\.\s*getOfficerSalary\s*\("), 1, lambda a: bool(_PLAIN_REFERENCE.match(a[0])),
     lambda a: [a[0], f" Misc.isMercenary({a[0].strip()})", " false", " false"], _SALARY_GATE),
    ("getOfficerSalary", re.compile(r"\bMisc\s*\.\s*getOfficerSalary\s*\("), 2, lambda a: True,
     lambda a: a + [" false", " false"], _SALARY_GATE),
    ("pickPortraitPreferNonDuplicate", re.compile(r"\bpickPortraitPreferNonDuplicate\s*\("), 2, lambda a: True, lambda a: a + [" null"],
     _PORTRAIT_GATE),
]
NOTES = {
    "addMarket": "RC8 has only addMarket(MarketAPI, boolean withJunkAndChatter)",
    "TileParams": "RC8 added a trailing String name",
    "addNebulaFromPNG": "RC8 added a trailing String name",
    "addCondition": "RC8 dropped 0.7's boolean flag",
    "ShipAIConfig": "the target has only ShipAIConfig(ShipAPI shipIfAny); null keeps RC8's defaults",
    "isBeingIgnored": "the target has only isBeingIgnored(boolean byAlly); false is RC8's meaning",
    "getOfficerSalary": "the target dropped the one-argument form and gave the two-argument form's boolean a new meaning "
                        "(mercenary -> checkIfInPopulatedSystem)",
    "pickPortraitPreferNonDuplicate": "the target added a trailing Random; null picks as RC8 did (vanilla passes null too)",
}


def _gate_open(gate: tuple, vanilla_core: Path | None) -> bool:
    if vanilla_core is None:
        return False
    from . import linkage

    info = linkage.core_index(str(Path(vanilla_core).expanduser().resolve())).get(gate[0])
    return info is not None and gate[1] not in info.methods and gate[2] in info.methods


def active_rules(vanilla_core: Path | None = None) -> list[tuple]:
    """RULES plus each TARGET_RULES entry whose gate the target core opens, as 5-tuples."""
    return list(RULES) + [rule[:5] for rule in TARGET_RULES if _gate_open(rule[5], vanilla_core)]


def suspects(text: str, vanilla_core: Path | None = None) -> list[tuple[int, str, int, int]]:
    """(line, rule, start of the argument list '(', end ')') for each old-form call in comment-blanked source."""
    found = []
    for name, pattern, count, test, _ in active_rules(vanilla_core):
        for match in pattern.finditer(text):
            open_index = match.end() - 1
            args = _arguments(text, open_index)
            if args is None:
                continue
            given = 0 if len(args) == 1 and not args[0].strip() else len(args)
            if given != count or not test(args):
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


def rewrite(text: str, blank: str, vanilla_core: Path | None = None) -> tuple[str, int]:
    """Apply every rule to `text`, locating calls in `blank` (same offsets, comments and strings blanked)."""
    rules = {(name, count): fix for name, _, count, _, fix in active_rules(vanilla_core)}
    out, last, count = [], 0, 0
    for _, name, open_index, close in suspects(blank, vanilla_core):
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
        given = 0 if len(args) == 1 and not args[0].strip() else len(args)
        out.append(text[last:open_index + 1] + ",".join(rules[(name, given)](args)) + ")")
        last = close + 1
        count += 1
    out.append(text[last:])
    return "".join(out), count
