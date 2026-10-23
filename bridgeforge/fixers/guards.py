"""Guard fixers for campaign generators (ROADMAP item 73, B1). REVIEW tier: each edit is a proposal a person reads.

Revised 2026-10-18 to ROADMAP item 75 R4 (semantic conditions are part of the fix, not the finding id).

- `system-generation-unguarded`: a void method that calls `createStarSystem("X")` once gets
  `if (<sector>.getStarSystem("X") != null) return;` as its first statement. Supported shape: the method only creates
  and fills that one system. Refused: more than one createStarSystem, any other sector/economy/faction/memory/script
  setup in the method (the early return would skip it), a non-void method, an existing lookup of the name.
  Real case: zzz-Bingus-Sustem's `atheos_custom_system` (2026-10-14 fixture from its `original/`).
- `orbit-period-computed-unguarded`: the flagged argument `E` becomes `Math.max(1f, (float) E)` only when
  `orbit_bounds.prove` shows `E` finite with a finite lower bound below 1 (a clamp repairs zero and negatives, not NaN
  or infinity: Math.max(1f, NaN) is NaN). Unknown calls, fields, float parameters, side effects (`++`, `=`), a divisor
  that may be zero and unbounded integers are refused and stay escalated. Both real cases (Vacuum's `orbitDays` from
  LazyLib `getRandomNumberInRange`, Bingus's `orbitRadius / (10f + random * 5f)` with a float parameter) are
  therefore refused: their ranges are not evidenced in the source.

Both edit only the located span (line endings, BOM and comments survive) and are idempotent: the scanner reads
`getStarSystem("X") != null` and `Math.max(` as guards, so a second run finds nothing. A source under `src/`
belongs to a jar: the edit has no effect until the jar is rebuilt.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

from ..orbit_bounds import Unproven, prove
from ..procgen_args import _arguments
from ..scan_javatext import _METHOD_SIGNATURE_PATTERN, _blank_java_comments, _enclosing_method_span

_EVIDENCE_LINE = re.compile(r"^(?P<file>.+?):(?P<line>\d+): (?P<name>.+) \(called from [^)]*\)$")
_IDENTIFIER = re.compile(r"^[A-Za-z_$][\w$]*$")
_GLOBAL_SECTOR = "com.fs.starfarer.api.Global.getSector()"
_MIN_ORBIT_DAYS = "1f"


def _fixers():
    from .. import fixers as _f

    return _f


def _not_running_source(relative: str) -> str | None:
    """Why an edit to this path would change nothing in the game, or None. Sources under src/, jars/ or jar/ belong to a
    jar (the game runs the jar until it is rebuilt: use patch-jar-class), and a '#'-prefixed folder such as
    '#Under construction' is never loaded. Sampling 2026-10-18 found both shapes among the applied edits."""
    parts = relative.replace("\\", "/").split("/")
    if "src" in parts or "jars" in parts or "jar" in parts:
        return "a jar's source tree: the edit changes nothing until the jar is rebuilt (patch-jar-class)"
    if any(part.startswith("#") for part in parts):
        return "under a '#' folder the game does not load"
    return None


def _java_text(path: Path):
    """(raw bytes, text, had_bom, comments-blanked text, comments-and-strings-blanked text), or None if unusable."""
    _f = _fixers()
    raw = path.read_bytes()
    text, had_bom = _f._decode(raw)
    blank, blank_strings = _blank_java_comments(text), _blank_java_comments(text, strings=True)
    if len(blank) != len(text) or len(blank_strings) != len(text):
        return None
    return raw, text, had_bom, blank, blank_strings


def _fix_system_generation_unguarded(root: Path, options: dict) -> list:
    """Insert an 'already exists' return at the top of each method that creates a named star system."""
    _f = _fixers()
    names_by_file: dict[str, list[tuple[int, str]]] = {}
    for finding in _f._findings_of(root, options, "system-generation-unguarded"):
        for item in finding.evidence or []:
            match = _EVIDENCE_LINE.match(str(item))
            if match:
                names_by_file.setdefault(match["file"], []).append((int(match["line"]), match["name"]))
    changes, refused = [], []
    for relative, wanted in sorted(names_by_file.items()):
        path = root / relative
        if not path.is_file() or path.suffix != ".java":
            refused.append(f"{relative} (not a loose java file)")
            continue
        if (reason := _not_running_source(relative)) is not None:
            refused.append(f"{relative}: {reason}")
            continue
        loaded = _java_text(path)
        if loaded is None:
            refused.append(f"{relative} (text could not be aligned)")
            continue
        raw, text, had_bom, blank, blank_strings = loaded
        newline = "\r\n" if "\r\n" in text else "\n"
        edits: dict[int, list[str]] = {}
        for line, name in sorted(set(wanted)):
            outcome = _guard_for(text, blank, blank_strings, line, name, newline)
            if isinstance(outcome, str):
                refused.append(f"{relative}:{line} ({name}): {outcome}")
                continue
            position, guard = outcome
            edits.setdefault(position, [])
            if guard not in edits[position]:
                edits[position].append(guard)
        if not edits:
            continue
        for position in sorted(edits, reverse=True):
            text = text[:position] + "".join(edits[position]) + text[position:]
        changes.append(_f.FileChange(path=path, before=raw, after=_f._encode(text, had_bom)))
    if refused and not changes:
        raise _f.FixerError("system-generation-unguarded: left for an agent: " + "; ".join(refused))
    return changes


def _guard_for(text: str, blank: str, blank_strings: str, line: int, name: str, newline: str):
    """(insert position, guard text) for the createStarSystem(name) call on `line`, or a refusal reason."""
    call = re.compile(r'\bcreateStarSystem\s*\(\s*"' + re.escape(name) + r'"\s*\)')
    hits = [m for m in call.finditer(blank) if text.count("\n", 0, m.start()) + 1 == line]
    if not hits:
        return "createStarSystem is not called with this one string literal on that line"
    start, end = _enclosing_method_span(blank_strings, hits[0].start())
    signature = _METHOD_SIGNATURE_PATTERN.match(blank_strings, start)
    if (start, end) == (0, len(text)) or signature is None:
        return "the enclosing method was not recognised"
    brace = signature.end() - 1
    header = blank_strings[start:brace]
    if not re.search(r"\bvoid\s+[\w$]+\s*\(", header):
        return "the enclosing method does not return void, so an early return would change its result"
    if re.search(r'\bgetStarSystem\s*\(\s*"' + re.escape(name) + r'"', blank[start:end]):
        return "the method already looks the system up by that name"
    unrelated = _unrelated_initialization(blank_strings[brace:end], header)
    if unrelated:
        return unrelated
    body_start = brace + 1
    first = re.match(r"[ \t]*\r?\n", text[body_start:])
    if first is None:
        return "the method body does not start on a new line"
    after = text[body_start + first.end():]
    following = re.search(r"^([ \t]*)\S", after, re.M)  # the first statement's indent, past any blank lines
    indent = following.group(1) if following and following.group(1) else "    "
    parameter = re.search(r"\bSectorAPI\s+([A-Za-z_$][\w$]*)", header)
    sector = parameter.group(1) if parameter else _GLOBAL_SECTOR
    guard = f'{indent}if ({sector}.getStarSystem("{name}") != null) return; // BridgeForge: do not create the system twice{newline}'
    return body_start + first.end(), guard


def _fix_orbit_period_computed_unguarded(root: Path, options: dict) -> list:
    """Wrap each flagged orbit-period argument as Math.max(1f, (float) E); multi-line arguments are refused."""
    _f = _fixers()
    edits_by_file: dict[str, set[tuple[int, str, int]]] = {}
    for finding in _f._findings_of(root, options, "orbit-period-computed-unguarded"):
        if not finding.file:
            continue
        facts = {}
        for item in finding.evidence or []:
            key, _, value = str(item).partition(":")
            facts[key] = value
        try:
            edits_by_file.setdefault(finding.file, set()).add((int(facts["line"]), facts["call"], int(facts["arg-index"])))
        except (KeyError, ValueError):
            continue
    changes, refused = [], []
    for relative, wanted in sorted(edits_by_file.items()):
        path = root / relative
        loaded = _java_text(path) if path.is_file() and path.suffix == ".java" else None
        if loaded is None:
            refused.append(f"{relative} (not a loose java file that can be edited)")
            continue
        if (reason := _not_running_source(relative)) is not None:
            refused.append(f"{relative}: {reason}")
            continue
        raw, text, had_bom, blank, blank_strings = loaded
        spans = set()
        for line, call, index in sorted(wanted):
            outcome = _orbit_span(blank, blank_strings, line, call, index)
            if isinstance(outcome, str):
                refused.append(f"{relative}:{line} ({call}): {outcome}")
            else:
                spans.add(outcome)
        for start, end in sorted(spans, reverse=True):
            argument = text[start:end]
            lead = argument[: len(argument) - len(argument.lstrip())]
            core = argument.strip()
            operand = f"(float) {core}" if _IDENTIFIER.match(core) else f"(float) ({core})"
            text = text[:start] + f"{lead}Math.max({_MIN_ORBIT_DAYS}, {operand})" + text[start + len(lead) + len(core):end] + text[end:]
        if spans:
            changes.append(_f.FileChange(path=path, before=raw, after=_f._encode(text, had_bom)))
    if refused and not changes:
        raise _f.FixerError("orbit-period-computed-unguarded: left for an agent: " + "; ".join(refused))
    return changes


def _orbit_span(blank: str, blank_strings: str, line: int, call: str, index: int):
    """(start, end) of the argument, or a refusal reason (including the interval proof's)."""
    for match in re.finditer(r"\b" + re.escape(call) + r"\s*\(", blank):
        if blank.count("\n", 0, match.start()) + 1 != line:
            continue
        open_index = match.end() - 1
        args = _arguments(blank, open_index)
        if args is None or index >= len(args):
            return "the call's arguments could not be read"
        start = open_index + 1 + sum(len(a) + 1 for a in args[:index])
        end = start + len(args[index])
        argument = blank[start:end]
        if "\n" in argument:
            return "the period expression spans several lines"
        if re.match(r"\s*Math\s*\.\s*max\s*\(", argument):
            return "the period is already wrapped in Math.max"
        method = blank[slice(*_enclosing_method_span(blank_strings, start))]
        try:
            low, _high = prove(argument, method)
        except Unproven as exc:
            return f"not provably finite with a lower bound ({exc}); a clamp alone does not repair NaN or infinity"
        if not math.isfinite(low) or low >= 1:
            return f"the proven lower bound {low:g} does not justify a one-day minimum"
        return start, end
    return "the call was not found on that line"


# Calls that set up something other than the one star system. Skipping the method when the system exists would skip these too.
_UNRELATED_CALL = re.compile(
    r"\b(registerPlugin|addScript|addTransientScript|addListener|addTransientListener|getFaction|getFactionById|getAllFactions|"
    r"getEconomy|getMemory\w*|getPersistentData|getPlayerFleet|getPlayerPerson|getImportantPeople|getIntelManager|"
    r"getCharacterData|addMessage|addPing)\s*\("
)
_SECTOR_MEMBERS_OK = {"createStarSystem", "getStarSystem", "getHyperspace"}
_SECTOR_ALIAS = r"\b([A-Za-z_$][\w$]*)\s*=\s*(?:com\.fs\.starfarer\.api\.)?Global\s*\.\s*getSector\s*\(\s*\)\s*;"


def _unrelated_initialization(body: str, header: str) -> str | None:
    """A refusal reason when the method does more than create this one system (an early return would skip it)."""
    if len(re.findall(r"\bcreateStarSystem\s*\(", body)) != 1:
        return "the method creates more than one star system, so one guard cannot cover them"
    found = _UNRELATED_CALL.search(body)
    if found:
        return f"the method also calls {found.group(1)}(...), initialization an early return would skip"
    names = {m.group(1) for m in re.finditer(r"\bSectorAPI\s+([A-Za-z_$][\w$]*)", header + body)}
    names |= {m.group(1) for m in re.finditer(_SECTOR_ALIAS, body)}
    receivers = [rf"\b{re.escape(n)}\s*\.\s*(\w+)" for n in sorted(names)] + [r"\bGlobal\s*\.\s*getSector\s*\(\s*\)\s*\.\s*(\w+)"]
    for pattern in receivers:
        for member in re.findall(pattern, body):
            if member not in _SECTOR_MEMBERS_OK:
                return f"the method also uses the sector ({member}), initialization an early return would skip"
    return None

