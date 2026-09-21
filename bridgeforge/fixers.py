from __future__ import annotations

import csv
import difflib
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .build_tag import _NAME_PATTERN, _find_top_level_key, _string_literal_to_text, _structural_depths, _text_to_string_literal
from .scanner import (
    DESIGN_TYPE_CSV_TARGETS,
    FACTION_SPECIAL_ROLE_KEYS,
    MOD_INFO_TRIAGE_BANNER_PATTERN,
    REMOVED_API_CALLS,
    _blank_java_comments,
    _load_lenient_json_file,
    _parse_json,
    _read_csv_rows,
    _relative,
    _removed_api_call_spans,
    _wing_ids_set,
)

SUPPORTED_FINDINGS = (
    "mod-info-game-version-inexact",
    "csv-row-extra-columns",
    "csv-missing-design-type-column",
    "procgen-planet-row-missing",
    "procgen-star-row-missing",
    "faction-known-lists-missing",
    "mod-info-triage-banner",
    "wing-data-missing-role-desc-column",
    "target-interface-method-missing",
    "removed-api-call",
    "carrier-bays-proposal",
    "revenantlib-fold-conflict",
    "undeclared-library-dependency",
)


class FixerError(ValueError):
    """Raised for an unsupported finding id, a missing required option, or a refusal to guess."""


@dataclass
class FileChange:
    path: Path
    before: bytes
    after: bytes
    existed_before: bool = True

    @property
    def changed(self) -> bool:
        return self.before != self.after


@dataclass
class FixPlan:
    finding_id: str
    mod_root: Path
    changes: list[FileChange] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Text/byte helpers shared by every fixer. All edits are surgical: only the
# located span(s) are rewritten, so unrelated bytes (line endings, comments,
# key order, BOM) survive untouched.
# ---------------------------------------------------------------------------


def _decode(raw: bytes) -> tuple[str, bool]:
    had_bom = raw.startswith(b"\xef\xbb\xbf")
    return raw.decode("utf-8-sig"), had_bom


def _encode(text: str, had_bom: bool) -> bytes:
    return (b"\xef\xbb\xbf" if had_bom else b"") + text.encode("utf-8")


_LINE_SPLIT_RE = re.compile(r"(.*?)(\r\n|\r|\n)?\Z", re.S)


def _split_terminator(line_with_ending: str) -> tuple[str, str]:
    match = _LINE_SPLIT_RE.match(line_with_ending)
    assert match is not None
    return match.group(1), match.group(2) or ""


def _line_field_spans(line: str, delimiter: str = ",") -> list[tuple[int, int, str]]:
    """(start, end, raw_text_incl_quotes) for each field of one CSV line (no embedded newlines)."""
    spans: list[tuple[int, int, str]] = []
    i = 0
    n = len(line)
    while True:
        start = i
        if i < n and line[i] == '"':
            j = i + 1
            while j < n:
                if line[j] == '"':
                    if j + 1 < n and line[j + 1] == '"':
                        j += 2
                        continue
                    j += 1
                    break
                j += 1
            end = j
        else:
            found = line.find(delimiter, i)
            end = found if found != -1 else n
        spans.append((start, end, line[start:end]))
        if end >= n or (end < n and line[end] != delimiter):
            break
        i = end + 1
    return spans


def _field_value(raw: str) -> str:
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        return raw[1:-1].replace('""', '"')
    return raw


def _quote_like(raw: str, value: str) -> str:
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        return '"' + value.replace('"', '""') + '"'
    return value


def _csv_escape(value: str) -> str:
    if any(ch in value for ch in ',"\n\r'):
        return '"' + value.replace('"', '""') + '"'
    return value


def _format_csv_row(fields: list[str]) -> str:
    return ",".join(_csv_escape(field_value) for field_value in fields)


def _csv_records(text: str) -> list[tuple[int, int]]:
    """(start, end) char spans for each logical CSV record, quote-aware across embedded newlines."""
    records: list[tuple[int, int]] = []
    start = 0
    in_quotes = False
    n = len(text)
    for index, char in enumerate(text):
        if char == '"':
            in_quotes = not in_quotes
        elif char == "\n" and not in_quotes:
            records.append((start, index + 1))
            start = index + 1
    if start < n:
        records.append((start, n))
    return records


def _parse_rgb(text: str) -> list[int]:
    parts = text.split(",")
    if len(parts) != 3:
        raise FixerError("--design-color must be R,G,B.")
    try:
        values = [int(part.strip()) for part in parts]
    except ValueError as exc:
        raise FixerError(f"--design-color must be three integers: {exc}") from exc
    if any(not 0 <= value <= 255 for value in values):
        raise FixerError("--design-color values must each be 0-255.")
    return values


# ---------------------------------------------------------------------------
# Fixer: wing-role-assault-removed
# ---------------------------------------------------------------------------


# Retired 2026-09-14 and no longer registered: ASSAULT is still a valid RC8 WingRole (javap on
# com.fs.starfarer.api.loading.WingRole), so rewriting it to FIGHTER changed behaviour for nothing.
def _fix_wing_role_assault_removed(root: Path, options: dict) -> list[FileChange]:
    path = root / "data" / "hulls" / "wing_data.csv"
    if not path.is_file():
        raise FixerError(f"No wing_data.csv found at {path}.")
    raw = path.read_bytes()
    text, had_bom = _decode(raw)
    lines = text.splitlines(keepends=True)
    if not lines:
        raise FixerError(f"{path} is empty.")
    header_content, header_term = _split_terminator(lines[0])
    header_fields = [_field_value(item[2]) for item in _line_field_spans(header_content)]
    normalized = [cell.strip().lower() for cell in header_fields]
    if "role" not in normalized:
        raise FixerError(f"{path} has no 'role' column.")
    role_index = normalized.index("role")

    edited_lines = [lines[0]]
    changed_count = 0
    for line in lines[1:]:
        content, term = _split_terminator(line)
        if not content.strip():
            edited_lines.append(line)
            continue
        spans = _line_field_spans(content)
        first_value = _field_value(spans[0][2]) if spans else ""
        if first_value.strip().startswith("#") or role_index >= len(spans):
            edited_lines.append(line)
            continue
        start, end, raw_field = spans[role_index]
        value = _field_value(raw_field)
        if value.strip().upper() == "ASSAULT":
            new_raw = _quote_like(raw_field, "FIGHTER")
            content = content[:start] + new_raw + content[end:]
            changed_count += 1
        edited_lines.append(content + term)

    if changed_count == 0:
        raise FixerError(f"No wing_data.csv row has role ASSAULT; nothing to fix in {path}.")
    new_text = "".join(edited_lines)
    return [FileChange(path=path, before=raw, after=_encode(new_text, had_bom))]


# ---------------------------------------------------------------------------
# Fixer: target-interface-method-missing (loose scripts only)
# ---------------------------------------------------------------------------

# RC8 defaults, read from starfarer.api.jar with javap (2026-09-14): BaseShipSystemScript returns -1f /
# -1 / null ("no override", i.e. what a pre-0.95 script did implicitly). Fully qualified types avoid
# touching imports.
_SHIP_SYSTEM_DEFAULTS = (
    ("getActiveOverride", "public float getActiveOverride(com.fs.starfarer.api.combat.ShipAPI ship) { return -1f; }"),
    ("getInOverride", "public float getInOverride(com.fs.starfarer.api.combat.ShipAPI ship) { return -1f; }"),
    ("getOutOverride", "public float getOutOverride(com.fs.starfarer.api.combat.ShipAPI ship) { return -1f; }"),
    ("getRegenOverride", "public float getRegenOverride(com.fs.starfarer.api.combat.ShipAPI ship) { return -1f; }"),
    ("getUsesOverride", "public int getUsesOverride(com.fs.starfarer.api.combat.ShipAPI ship) { return -1; }"),
    ("getDisplayNameOverride", "public String getDisplayNameOverride(com.fs.starfarer.api.plugins.ShipSystemStatsScript.State state, float effectLevel) { return null; }"),
)
_REFIT_PICKER_DEFAULT = "public boolean showInRefitScreenModPickerFor(com.fs.starfarer.api.combat.ShipAPI ship) { return true; }"


def _insert_before_class_end(text: str, members: list[str], note: str) -> str:
    end = text.rstrip().rfind("}")
    if end < 0 or not members:
        return text
    newline = "\r\n" if "\r\n" in text else "\n"
    block = newline + f"    // BridgeForge: {note}" + newline + newline.join(f"    {member}" for member in members) + newline
    return text[:end] + block + text[end:]


def _fix_target_interface_method_missing(root: Path, options: dict) -> list[FileChange]:
    """Bring loose scripts up to RC8's callback signatures (they fail to compile at load otherwise).

    - ShipSystemStatsScript: add the six *Override methods with BaseShipSystemScript's defaults.
    - OnHitEffectPlugin.onHit: insert the ApplyDamageResultAPI parameter before CombatEngineAPI.
    - HullModEffect: add showInRefitScreenModPickerFor returning BaseHullMod's default.
    Bodies are untouched. Classes compiled into a jar need the jar rebuilt, so those are refused.
    """
    from .scanner import scan_mod

    files = sorted({f.file for f in scan_mod(root).findings if f.id == "target-interface-method-missing" and f.file})
    loose = [rel for rel in files if rel.startswith("data/")]
    if not loose:
        detail = f" (jar sources need a rebuild: {', '.join(files[:5])})" if files else ""
        raise FixerError(f"No loose data/ script has a missing RC8 interface method{detail}.")
    changes: list[FileChange] = []
    for rel in loose:
        path = root / rel
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        new = text
        if re.search(r"\bimplements\s+(?:[^{]*?\b)?ShipSystemStatsScript\b", new):
            missing = [stub for name, stub in _SHIP_SYSTEM_DEFAULTS if not re.search(rf"\b{name}\s*\(", new)]
            new = _insert_before_class_end(new, missing, "RC8 ShipSystemStatsScript overrides, BaseShipSystemScript defaults (no override)")
        if re.search(r"\bimplements\s+(?:[^{]*?\b)?OnHitEffectPlugin\b", new) and not re.search(r"\bonHit\s*\([^)]*\bApplyDamageResultAPI\b", new):
            new = re.sub(
                r"(\bonHit\s*\([^)]*?,)(\s*)((?:final\s+)?(?:[\w.]+\.)?CombatEngineAPI\s+\w+\s*\))",
                r"\1\2com.fs.starfarer.api.combat.listeners.ApplyDamageResultAPI damageResult,\2\3",
                new,
                count=1,
            )
        if re.search(r"\bimplements\s+(?:[^{]*?\b)?HullModEffect\b", new) and not re.search(r"\bshowInRefitScreenModPickerFor\s*\(", new):
            new = _insert_before_class_end(new, [_REFIT_PICKER_DEFAULT], "RC8 HullModEffect method, BaseHullMod default")
        if new != text:
            changes.append(FileChange(path=path, before=raw, after=_encode(new, had_bom)))
    if not changes:
        raise FixerError("The flagged loose scripts could not be rewritten mechanically; fix them by hand.")
    return changes


# ---------------------------------------------------------------------------
# Fixer: removed-api-call (loose scripts only)
# ---------------------------------------------------------------------------
#
# Each bridgeforge.scanner.REMOVED_API_CALLS entry can have its own mechanical rewrite here, keyed by
# that entry's `signature` string. An entry with no key in _REMOVED_API_CALL_REWRITES is detected by the
# scanner but never rewritten by this fixer; it is left for the owner to fix by hand (every entry as of
# 2026-09-15 has a rewrite; the mechanism stays generic for a future entry that doesn't).

_LEGACY_FLEETS_CALL = "bf.legacyfleets.LegacyFleets.createFleet("
_REVENANTLIB_DEPENDENCY_ENTRY = '{"id":"revenantlib","name":"RevenantLib"}'
_DEPENDENCIES_ARRAY_PATTERN = re.compile(r"['\"]dependencies['\"]\s*:\s*\[")

# REMOVED_API_CALLS[0]: SectorAPI.createFleet(...) -> bf.legacyfleets.LegacyFleets.createFleet(...). The
# whole matched receiver+method-name span is replaced. This and the two LegacyWorld rewrites below each
# introduce a `bf.` call, so each adds RevenantLib as a dependency (once) when it actually rewrote
# something in this run - see _BF_CALL_SIGNATURES below.
_CREATE_FLEET_SIGNATURE = REMOVED_API_CALLS[0][1]


def _rewrite_create_fleet_span(_matched_text: str) -> str:
    return _LEGACY_FLEETS_CALL


# REMOVED_API_CALLS[1]: SectorAPI.addMessage(String) -> insert .getCampaignUI() before .addMessage(,
# keeping the original receiver (Global.getSector()/Global.getSectorAPI()/getSector()/getSectorAPI())
# untouched, since CampaignUIAPI.addMessage is what RC8 kept (javap, 2026-09-14).
_ADD_MESSAGE_TAIL_PATTERN = re.compile(r"\.\s*addMessage\s*\(\Z")


def _rewrite_add_message_span(matched_text: str) -> str:
    return _ADD_MESSAGE_TAIL_PATTERN.sub(lambda m: ".getCampaignUI()" + m.group(0), matched_text, count=1)


# REMOVED_API_CALLS[2]: CargoAPI.CrewXPLevel -> deleted outright (owner decision 2026-09-15: crew quality
# no longer exists in RC8; crew counts are kept). The scanner's combined pattern matches exactly the text
# that needs to disappear in each of its three shapes (the now-unresolvable import line; CrewXPLevel.X as
# addCrew's leading argument, including its trailing comma; and a trailing `, CrewXPLevel.X` argument to
# addToFleet), so every matched span is simply removed - no `bf.` call is introduced, so this rule never
# adds a dependency.
_CREW_XP_LEVEL_MATCHER = REMOVED_API_CALLS[2][0]
_CREW_XP_LEVEL_SIGNATURE = REMOVED_API_CALLS[2][1]


def _rewrite_crew_xp_level_span(_matched_text: str) -> str:
    return ""


# A CrewXPLevel-typed variable or parameter declaration (e.g. `CrewXPLevel level` or
# `CargoAPI.CrewXPLevel x`) means some local helper carries the level through its own signature and
# body, not just call-site arguments. Real case (AI-War, 2026-09-15):
# data/missions/aiw_midnight/MissionDefinition.java declared
# `addToFleetAndAddSkills(..., CrewXPLevel level, boolean isFlagship)`, with a body line
# `if (level == null) level = CrewXPLevel.REGULAR;`. The call-site-only rewrite above (matching
# `CrewXPLevel.X` member access, never a bare type name) would drop the argument at every call site
# while leaving the parameter's own type (now unresolvable, since the import line is also removed)
# and the body's default-value line untouched - some call sites keep 6 arguments, some now pass 5,
# against a signature still declaring 6 params of a type that no longer resolves. The owner's task
# A10 hand-ported this file instead (see its `.pre-bf-fix` era working copy). Matched on the type
# name followed by whitespace, so it never fires on `CrewXPLevel.ELITE` (a dot, not whitespace).
_CREW_XP_LEVEL_DECLARATION_PATTERN = re.compile(r"\bCrewXPLevel\s+[A-Za-z_$][\w$]*\s*[,);=]")


# REMOVED_API_CALLS[3]/[4]: the 0.6 7-argument LocationAPI.addPlanet(...) and the 6-argument
# LocationAPI.addOrbitalStation(...) both become a call to bf.legacyworld.LegacyWorld (RevenantLib),
# with the old receiver forwarded as this static method's new first argument and every other argument
# unchanged. The scanner's finder functions (bridgeforge.scanner._find_legacy_add_planet_calls /
# _find_legacy_add_orbital_station_calls) already return the *whole* call span (receiver through the
# matching close paren), so the rewrite only needs to re-split that same text at the same "receiver .
# methodName (" boundary - it never re-parses arguments, since the call's own argument text (already
# validated exactly once, when the scanner counted it) is carried through untouched.
_ADD_PLANET_SIGNATURE = REMOVED_API_CALLS[3][1]
_ADD_ORBITAL_STATION_SIGNATURE = REMOVED_API_CALLS[4][1]
_CALL_PREFIX_ADD_PLANET = re.compile(r"\A([A-Za-z_]\w*)\s*\.\s*addPlanet\s*\(", re.S)
_CALL_PREFIX_ADD_ORBITAL_STATION = re.compile(r"\A([A-Za-z_]\w*)\s*\.\s*addOrbitalStation\s*\(", re.S)


def _rewrite_add_planet_span(matched_text: str) -> str:
    match = _CALL_PREFIX_ADD_PLANET.match(matched_text)
    assert match is not None, f"addPlanet rewrite span did not start with a receiver.addPlanet( prefix: {matched_text!r}"
    receiver = match.group(1)
    args_text = matched_text[match.end():-1]  # drop the call's own trailing ')'
    return f"bf.legacyworld.LegacyWorld.addPlanet({receiver}, {args_text})"


def _rewrite_add_orbital_station_span(matched_text: str) -> str:
    match = _CALL_PREFIX_ADD_ORBITAL_STATION.match(matched_text)
    assert match is not None, f"addOrbitalStation rewrite span did not start with a receiver.addOrbitalStation( prefix: {matched_text!r}"
    receiver = match.group(1)
    args_text = matched_text[match.end():-1]
    return f"bf.legacyworld.LegacyWorld.addOrbitalStation({receiver}, {args_text})"


# Signatures whose rewrite introduces a `bf.` call: each adds the revenantlib dependency, once, when it
# actually rewrote something in this run (CrewXPLevel and addMessage never do - neither introduces a new
# call to RevenantLib code).
_BF_CALL_SIGNATURES = frozenset({_CREATE_FLEET_SIGNATURE, _ADD_PLANET_SIGNATURE, _ADD_ORBITAL_STATION_SIGNATURE})

_REMOVED_API_CALL_REWRITES: dict[str, Callable[[str], str]] = {
    _CREATE_FLEET_SIGNATURE: _rewrite_create_fleet_span,
    "SectorAPI.addMessage(String)": _rewrite_add_message_span,
    _CREW_XP_LEVEL_SIGNATURE: _rewrite_crew_xp_level_span,
    _ADD_PLANET_SIGNATURE: _rewrite_add_planet_span,
    _ADD_ORBITAL_STATION_SIGNATURE: _rewrite_add_orbital_station_span,
}


def _fix_removed_api_call(root: Path, options: dict) -> list[FileChange]:
    """Rewrite every `bridgeforge.scanner.REMOVED_API_CALLS` rule that has a mechanical rewrite.

    Most rules match (comments and disabled_files ignored, same as the scanner) on the receiver+method-
    name text only, leaving the call's own arguments untouched; the addPlanet/addOrbitalStation rules
    match the *whole* call (receiver through the closing paren), since their rewrite has to move the
    receiver into the argument list. A loose script with an unrewritten removed API call fails to compile
    at load, so this only ever touches `data/` scripts - a match found only in a compiled jar's bundled
    source is refused, same as target-interface-method-missing. A rule with no key in
    _REMOVED_API_CALL_REWRITES is never touched; if it is the only thing found, this refuses rather than
    guess. RevenantLib (`revenantlib`) is added to mod_info.json's `dependencies` only when a rule that
    introduces a `bf.` call (createFleet, addPlanet, addOrbitalStation - see _BF_CALL_SIGNATURES) actually
    rewrote something in this run (not, for example, when only addMessage or CrewXPLevel did).
    """
    # (matcher, rewrite, signature) for every rule this fixer knows how to rewrite. `matcher` is whatever
    # bridgeforge.scanner._removed_api_call_spans accepts (a compiled regex or a text -> spans function).
    rewrite_rules: list[tuple[object, Callable[[str], str], str]] = [
        (matcher, _REMOVED_API_CALL_REWRITES[signature], signature)
        for matcher, signature, _explanation in REMOVED_API_CALLS
        if signature in _REMOVED_API_CALL_REWRITES
    ]
    unrewritable_matchers: list[object] = [
        matcher for matcher, signature, _explanation in REMOVED_API_CALLS if signature not in _REMOVED_API_CALL_REWRITES
    ]

    matched_files: list[Path] = []  # any REMOVED_API_CALLS rule, any location
    rewrites_by_file: dict[Path, list[tuple[object, Callable[[str], str], str]]] = {}
    rewritable_hit = False
    crew_xp_level_refusals: list[Path] = []  # matched CrewXPLevel, but the file also declares the type
    for source in sorted(root.rglob("*.java")):
        if "disabled_files" in source.relative_to(root).parts:
            continue
        try:
            text = source.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        blanked = _blank_java_comments(text)
        # A file that declares a CrewXPLevel-typed variable/parameter is refused for that one rule
        # (see _CREW_XP_LEVEL_DECLARATION_PATTERN above); other rules in the same file are untouched
        # by this and still get their mechanical rewrite.
        declares_crew_xp_level_type = bool(_CREW_XP_LEVEL_DECLARATION_PATTERN.search(blanked))
        file_rewrite_rules = (
            [(matcher, rewrite, signature) for matcher, rewrite, signature in rewrite_rules if signature != _CREW_XP_LEVEL_SIGNATURE]
            if declares_crew_xp_level_type else rewrite_rules
        )
        file_rewrites = [(matcher, rewrite, signature) for matcher, rewrite, signature in file_rewrite_rules if _removed_api_call_spans(matcher, blanked)]
        has_unrewritable = any(_removed_api_call_spans(matcher, blanked) for matcher in unrewritable_matchers)
        refused_crew_xp_level = declares_crew_xp_level_type and bool(_removed_api_call_spans(_CREW_XP_LEVEL_MATCHER, blanked))
        if refused_crew_xp_level:
            crew_xp_level_refusals.append(source)
        if file_rewrites or has_unrewritable or refused_crew_xp_level:
            matched_files.append(source)
        if file_rewrites:
            rewrites_by_file[source] = file_rewrites
            rewritable_hit = True

    loose_files = [source for source in rewrites_by_file if source.relative_to(root).as_posix().startswith("data/")]
    if not loose_files:
        if crew_xp_level_refusals and not rewritable_hit:
            names = ", ".join(_relative(root, source) for source in crew_xp_level_refusals[:5])
            raise FixerError(
                f"{names}: declares a CrewXPLevel-typed variable or parameter (e.g. a helper method's own "
                "signature), so rewriting only the literal call-site arguments would desync it from the "
                "helper's own calls and its default-value logic. Hand-port this file instead."
            )
        if matched_files:
            names = ", ".join(_relative(root, source) for source in matched_files[:5])
            if not rewritable_hit:
                raise FixerError(
                    f"Every removed-api-call match found has no safe mechanical rewrite: {names}. Fix by hand."
                )
            raise FixerError(f"No loose data/ script has a rewritable removed API call (jar sources need a rebuild: {names}).")
        raise FixerError(
            "No loose data/ script calls getSector().createFleet(...)/Global.getSector().createFleet(...) or a similar removed API this fixer knows how to rewrite."
        )

    changes: list[FileChange] = []
    rewritten_signatures: set[str] = set()
    for source in sorted(loose_files, key=lambda path: path.as_posix()):
        raw = source.read_bytes()
        text, had_bom = _decode(raw)
        blanked = _blank_java_comments(text)
        spans: list[tuple[int, int, Callable[[str], str], str]] = []
        for matcher, rewrite, signature in rewrites_by_file[source]:
            for start, end in _removed_api_call_spans(matcher, blanked):
                spans.append((start, end, rewrite, signature))
        if not spans:
            continue
        new_text = text
        for start, end, rewrite, signature in sorted(spans, key=lambda item: item[0], reverse=True):
            new_text = new_text[:start] + rewrite(new_text[start:end]) + new_text[end:]
            rewritten_signatures.add(signature)
        changes.append(FileChange(path=source, before=raw, after=_encode(new_text, had_bom)))

    if not changes:
        raise FixerError("The flagged loose scripts could not be rewritten mechanically; fix them by hand.")

    if rewritten_signatures & _BF_CALL_SIGNATURES:
        dependency_change = _add_revenantlib_dependency(root / "mod_info.json")
        if dependency_change is not None:
            changes.append(dependency_change)
    return changes


def _add_revenantlib_dependency(path: Path) -> FileChange | None:
    """Add RevenantLib (id `revenantlib`) as a dependency, unless already declared.

    RevenantLib 1.1.0+bf.1 folded in the retired BF Legacy Fleets library (`bf.legacyfleets.LegacyFleets`,
    id `bf_legacy_fleets`, owner decision 2026-09-15) and added `bf.legacyworld.LegacyWorld`; both are
    what the createFleet/addPlanet/addOrbitalStation rewrites above now point at, so this replaces the
    older `_add_legacy_fleets_dependency` (which added `bf_legacy_fleets` instead). "Already declared"
    checks both a `{"id": "revenantlib", ...}` object entry and a bare `"revenantlib"` string entry --
    Starsector accepts either shape (`_mod_info_declares_dependency` in scanner.py already does the same
    both-shapes check); recognizing only the object shape here let `revenantlib-fold-conflict`'s fixer
    double-add a second, redundant `{"id": "revenantlib", ...}` entry onto a mod_info.json that already
    declared it as a bare string (found by that fixer's own test, 2026-09-20).
    """
    if not path.is_file():
        raise FixerError(f"No mod_info.json found at {path}.")
    raw = path.read_bytes()
    text, had_bom = _decode(raw)
    data = _load_lenient_json_file(path)
    if not isinstance(data, dict):
        raise FixerError(f"{path} could not be parsed as JSON.")
    dependencies = data.get("dependencies")
    if dependencies is not None and not isinstance(dependencies, list):
        raise FixerError(f"{path} 'dependencies' is not a JSON array; add the revenantlib dependency by hand.")
    if isinstance(dependencies, list) and any(
        (isinstance(item, dict) and item.get("id") == "revenantlib") or item == "revenantlib" for item in dependencies
    ):
        return None

    match = _DEPENDENCIES_ARRAY_PATTERN.search(text)
    if match is not None:
        insert_at = match.end()  # just after the array's '['
        needs_comma = not text[insert_at:].lstrip().startswith("]")
        new_text = text[:insert_at] + _REVENANTLIB_DEPENDENCY_ENTRY + ("," if needs_comma else "") + text[insert_at:]
    else:
        brace_index = text.find("{")
        if brace_index == -1:
            raise FixerError(f"{path} has no '{{' to insert dependencies after.")
        insertion = '"dependencies":[' + _REVENANTLIB_DEPENDENCY_ENTRY + "],"
        new_text = text[: brace_index + 1] + insertion + text[brace_index + 1 :]

    try:
        parsed, _tolerances = _parse_json(new_text)
    except json.JSONDecodeError as exc:
        raise FixerError(f"Edited {path} failed to re-parse: {exc}") from exc
    new_dependencies = parsed.get("dependencies") if isinstance(parsed, dict) else None
    if not isinstance(new_dependencies, list) or not any(
        isinstance(item, dict) and item.get("id") == "revenantlib" for item in new_dependencies
    ):
        raise FixerError(f"Edited {path} did not round-trip the revenantlib dependency as expected.")
    return FileChange(path=path, before=raw, after=_encode(new_text, had_bom))


# ---------------------------------------------------------------------------
# Fixer: revenantlib-fold-conflict (roadmap P14 item 10, fold-in workflow)
# ---------------------------------------------------------------------------

# One dependencies-array entry: a bare id string (either quote style) or a flat {"id":...} object
# (no nested braces expected in a real dependency entry -- same assumption _OBJECT_LITERAL in
# build_tag.py already makes for "version").
_DEPENDENCY_ENTRY_PATTERN = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|\{[^{}]*\}')
_DEPENDENCY_ENTRY_ID_PATTERN = re.compile(r"""['"]id['"]\s*:\s*("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')""")


def _remove_dependency_entries(text: str, remove_ids: list[str]) -> tuple[str, list[str]]:
    """Drop each `dependencies` array entry (a bare id string or an {"id": ...} object) whose id
    case-insensitively matches one of `remove_ids` -- `revenantlib` itself is never a candidate.
    Everything else in the file (comments, formatting, other keys) is left untouched. Returns
    (new_text, ids actually removed); an id with no matching array entry is silently not removed --
    the caller decides whether that's an error.
    """
    targets = {item.strip().lower() for item in remove_ids if item.strip() and item.strip().lower() != "revenantlib"}
    match = _DEPENDENCIES_ARRAY_PATTERN.search(text)
    if match is None or not targets:
        return text, []
    depths = _structural_depths(text)
    open_pos = match.end() - 1  # the '[' itself
    inner_depth = depths[open_pos] + 1
    close_pos = None
    for i in range(open_pos + 1, len(text)):
        if text[i] == "]" and depths[i] == inner_depth:
            close_pos = i
            break
    if close_pos is None:
        return text, []

    body = text[open_pos + 1 : close_pos]
    remove_spans: list[tuple[int, int]] = []
    removed: list[str] = []
    for entry_match in _DEPENDENCY_ENTRY_PATTERN.finditer(body):
        raw_entry = entry_match.group(0)
        if raw_entry.startswith("{"):
            id_match = _DEPENDENCY_ENTRY_ID_PATTERN.search(raw_entry)
            entry_id = _string_literal_to_text(id_match.group(1)) if id_match else None
        else:
            entry_id = _string_literal_to_text(raw_entry)
        if entry_id and entry_id.strip().lower() in targets:
            remove_spans.append((entry_match.start(), entry_match.end()))
            removed.append(entry_id)
    if not remove_spans:
        return text, []

    new_body = body
    for start, end in sorted(remove_spans, reverse=True):
        seg_start, seg_end = start, end
        after_match = re.match(r"[ \t]*,", new_body[seg_end:])
        if after_match:
            seg_end += after_match.end()
        else:
            before_match = re.search(r",\s*\Z", new_body[:seg_start])
            if before_match:
                seg_start = before_match.start()
        new_body = new_body[:seg_start] + new_body[seg_end:]
    new_text = text[: open_pos + 1] + new_body + text[close_pos:]
    return new_text, removed


def _fix_revenantlib_fold_conflict(root: Path, options: dict) -> list[FileChange]:
    """Resolve `revenantlib-fold-conflict`: drop the redundant original dependency entry/entries a
    mod_info.json also declares alongside revenantlib (per dependency_successors.json's
    "folded-into-revenantlib" entries, written by `bridgeforge fold` -- see bridgeforge/fold.py).
    revenantlib's own entry is left exactly as it is; `_add_revenantlib_dependency` is still called
    first (as every other dependency-touching fixer above does) so a mod_info.json that somehow lost
    its revenantlib entry between scan and fix gets it back, and so the removal below always edits
    the same in-memory text that ends up written (never a second, independently-read FileChange for
    the same path, which could otherwise clobber this one).
    """
    from .scanner import scan_mod

    findings = [f for f in scan_mod(root).findings if f.id == "revenantlib-fold-conflict"]
    if not findings:
        raise FixerError(
            "No revenantlib-fold-conflict finding for this mod: mod_info.json does not declare both "
            "revenantlib and an original mod RevenantLib has folded in."
        )
    conflicting_ids = sorted({item for finding in findings for item in finding.evidence})

    path = root / "mod_info.json"
    if not path.is_file():
        raise FixerError(f"No mod_info.json found at {path}.")

    dependency_change = _add_revenantlib_dependency(path)
    if dependency_change is not None:
        raw = dependency_change.before
        text, had_bom = _decode(dependency_change.after)
    else:
        raw = path.read_bytes()
        text, had_bom = _decode(raw)

    new_text, removed = _remove_dependency_entries(text, conflicting_ids)
    if not removed:
        raise FixerError(f"{path}: could not locate a removable dependency entry among {', '.join(conflicting_ids)}.")

    try:
        parsed, _tolerances = _parse_json(new_text)
    except json.JSONDecodeError as exc:
        raise FixerError(f"Edited {path} failed to re-parse: {exc}") from exc
    remaining_ids = {
        (str(item.get("id") or "").strip().lower() if isinstance(item, dict) else str(item).strip().lower())
        for item in ((parsed.get("dependencies") or []) if isinstance(parsed, dict) else [])
    }
    if any(removed_id.lower() in remaining_ids for removed_id in removed):
        raise FixerError(f"Edited {path} still declares {', '.join(removed)} after removal; refusing to write a partial edit.")
    if "revenantlib" not in remaining_ids:
        raise FixerError(f"Edited {path} no longer declares revenantlib; refusing to write an edit that would leave dependents unable to resolve either id.")

    return [FileChange(path=path, before=raw, after=_encode(new_text, had_bom))]


# ---------------------------------------------------------------------------
# Fixer: undeclared-library-dependency (roadmap P14 item 16)
# ---------------------------------------------------------------------------


def _add_dependency_entry(text: str, dependency_id: str, name: str) -> str:
    """Insert `{"id":"<id>","name":"<name>"}` into `dependencies`, creating the array if absent.

    Generalizes `_add_revenantlib_dependency`'s insertion logic (kept separate above since it also
    carries revenantlib-specific "already declared" checks and round-trip verification); this one
    assumes the caller has already confirmed the id isn't declared and just needs the array edit.
    """
    entry = '{"id":' + json.dumps(dependency_id) + ',"name":' + json.dumps(name) + "}"
    match = _DEPENDENCIES_ARRAY_PATTERN.search(text)
    if match is not None:
        insert_at = match.end()  # just after the array's '['
        needs_comma = not text[insert_at:].lstrip().startswith("]")
        return text[:insert_at] + entry + ("," if needs_comma else "") + text[insert_at:]
    brace_index = text.find("{")
    if brace_index == -1:
        raise FixerError("mod_info.json has no '{' to insert dependencies after.")
    insertion = '"dependencies":[' + entry + "],"
    return text[: brace_index + 1] + insertion + text[brace_index + 1 :]


def _fix_undeclared_library_dependency(root: Path, options: dict) -> list[FileChange]:
    """Resolve `undeclared-library-dependency`: declare the library findings already identified
    the mod actually reaches by package (LazyLib/MagicLib/GraphicsLib/LunaLib/Nexerelin), using the
    exact id `scanner.LIBRARY_DEPENDENCY_IDS` maps to. Declaring a library the mod already imports
    is safe regardless of whether the finding is MANUAL (unguarded) or REVIEW (an isModEnabled guard
    found, suggesting an optional integration) - Starsector's dependency mechanism has no separate
    "optional" shape, so a real integration wants the dependency present either way, and it never
    makes the undeclared-crash failure mode worse.

    Hand-verified this session, twice: `scanner.LIBRARY_DEPENDENCY_IDS` had the wrong case for two
    libraries (`magiclib`/`shaderlib` instead of the real `MagicLib`/`shaderLib`, found by reading
    those libraries' own installed `mod_info.json`, corroborated by `revival_audit.py`'s already-
    correct copy of the same table) - fixed there before this fixer was built on top of it, so a
    written dependency actually matches what the game expects, not just what the scanner's own
    case-insensitive comparison would have accepted.
    """
    from .scanner import LIBRARY_DEPENDENCY_IDS, scan_mod

    findings = [f for f in scan_mod(root).findings if f.id == "undeclared-library-dependency"]
    if not findings:
        raise FixerError("No undeclared-library-dependency finding for this mod.")

    to_add: dict[str, str] = {}  # dependency_id -> library display name
    for finding in findings:
        library = next((item.split(":", 1)[1] for item in finding.evidence if item.startswith("library:")), None)
        dependency_id = next((item.split(":", 1)[1] for item in finding.evidence if item.startswith("dependency-id:")), None)
        if not library or not dependency_id:
            continue
        # Trust LIBRARY_DEPENDENCY_IDS as the source of truth for the id to write, not the
        # finding's own copy of it, so a corrected table takes effect without needing a fresh scan.
        to_add[LIBRARY_DEPENDENCY_IDS.get(library, dependency_id)] = library

    path = root / "mod_info.json"
    if not path.is_file():
        raise FixerError(f"No mod_info.json found at {path}.")
    raw = path.read_bytes()
    text, had_bom = _decode(raw)
    data = _load_lenient_json_file(path)
    if not isinstance(data, dict):
        raise FixerError(f"{path} could not be parsed as JSON.")
    dependencies = data.get("dependencies")
    if dependencies is not None and not isinstance(dependencies, list):
        raise FixerError(f"{path} 'dependencies' is not a JSON array; add the dependency by hand.")
    already_declared = {
        str((item.get("id") if isinstance(item, dict) else item) or "").strip().lower()
        for item in (dependencies or [])
    }

    added: list[str] = []
    for dependency_id, library in sorted(to_add.items()):
        if dependency_id.strip().lower() in already_declared:
            continue
        text = _add_dependency_entry(text, dependency_id, library)
        already_declared.add(dependency_id.strip().lower())
        added.append(dependency_id)
    if not added:
        raise FixerError(f"{path} already declares every library this mod's undeclared-library-dependency findings name.")

    try:
        parsed, _tolerances = _parse_json(text)
    except json.JSONDecodeError as exc:
        raise FixerError(f"Edited {path} failed to re-parse: {exc}") from exc
    new_ids = {
        str((item.get("id") if isinstance(item, dict) else item) or "").strip().lower()
        for item in ((parsed.get("dependencies") or []) if isinstance(parsed, dict) else [])
    }
    missing = [dep_id for dep_id in added if dep_id.strip().lower() not in new_ids]
    if missing:
        raise FixerError(f"Edited {path} did not round-trip {', '.join(missing)} as expected.")

    return [FileChange(path=path, before=raw, after=_encode(text, had_bom))]


# ---------------------------------------------------------------------------
# Fixer: wing-data-missing-role-desc-column
# ---------------------------------------------------------------------------


def _fix_wing_data_missing_role_desc_column(root: Path, options: dict) -> list[FileChange]:
    """Append a blank `role desc` column: without it RC8's FighterWingSpreadsheetLoader throws a
    JSONException and content loading dies before the main menu (live bug VAC-R002, Vacuum). Vacuum's
    live runs showed a blank value is accepted. Pre-0.8 faction mods (0.53-0.65) all lack it.
    """
    path = root / "data" / "hulls" / "wing_data.csv"
    if not path.is_file():
        raise FixerError(f"No wing_data.csv found at {path}.")
    raw = path.read_bytes()
    text, had_bom = _decode(raw)
    lines = text.splitlines(keepends=True)
    if not lines:
        raise FixerError(f"{path} is empty.")
    # Count every record the reader returns (a padding row of bare commas is a record too; Cobalt Arms has
    # 44 of them), against every non-blank line: they differ only when a quoted field spans lines.
    records = [row for row in csv.reader(io.StringIO(text)) if row]
    if len(records) != sum(1 for line in lines if line.strip()):
        raise FixerError(f"{path} has a quoted field spanning several lines; add the column by hand rather than guess the row boundaries.")
    header_content, header_term = _split_terminator(lines[0])
    header_fields = [_field_value(item[2]) for item in _line_field_spans(header_content)]
    if "role desc" in [cell.strip().lower() for cell in header_fields]:
        raise FixerError(f"{path} already has a 'role desc' column.")
    width = len(header_fields)
    edited_lines = [header_content + ",role desc" + (header_term or "\n")]
    for line in lines[1:]:
        content, term = _split_terminator(line)
        if not content.strip():
            edited_lines.append(line)
            continue
        present = len(_line_field_spans(content))
        # Pad a short row first so the blank lands in the new column, not an earlier one.
        edited_lines.append(content + "," * max(0, width - present) + "," + term)
    return [FileChange(path=path, before=raw, after=_encode("".join(edited_lines), had_bom))]


# ---------------------------------------------------------------------------
# Fixer: carrier-bays-proposal
# ---------------------------------------------------------------------------

# RC8's own ship_data.csv (starsector-core/data/hulls/ship_data.csv, read 2026-09-15): the highest
# "fighter bays" value any vanilla hull carries is 6 (the Astral, RC8's dedicated fleet carrier;
# the Legion and both carrier hull-mod modules are 4). Nothing in vanilla goes higher, so a --hull
# value above this is refused rather than guessed at.
_MAX_FIGHTER_BAYS = 6


def _parse_hull_bay_assignments(raw: list[str]) -> dict[str, int]:
    if not raw:
        raise FixerError("--hull ID=N is required (repeatable) for carrier-bays-proposal.")
    assignments: dict[str, int] = {}
    for item in raw:
        hull_id, sep, value = item.strip().rpartition("=")
        if not sep:
            raise FixerError(f"--hull must be ID=N (got '{item}').")
        hull_id = hull_id.strip()
        value = value.strip()
        if not hull_id:
            raise FixerError(f"--hull '{item}' has no hull id.")
        if not re.fullmatch(r"-?\d+", value):
            raise FixerError(f"--hull {hull_id}=... value must be an integer (got '{value}').")
        count = int(value)
        if not 0 <= count <= _MAX_FIGHTER_BAYS:
            raise FixerError(f"--hull {hull_id}={count}: fighter bays must be 0-{_MAX_FIGHTER_BAYS} (vanilla's own maximum, the Astral, RC8 ship_data.csv).")
        if hull_id in assignments and assignments[hull_id] != count:
            raise FixerError(f"--hull {hull_id} was given more than once with different values.")
        assignments[hull_id] = count
    return assignments


def _fix_carrier_bays_proposal(root: Path, options: dict) -> list[FileChange]:
    """Write approved `--hull ID=N` fighter-bay counts into ship_data.csv (roadmap P14 item 6).

    "fighter bays" is RC8's own ship_data.csv header name for the column (read from the core, see
    _MAX_FIGHTER_BAYS above). If the mod's file predates it (the pre-0.8 `hangar` schema), the
    column is appended the same way `wing-data-missing-role-desc-column` adds `role desc`: blank for
    every hull not named on the command line, so untouched rows keep their author's silence rather
    than an invented 0. Every --hull id must already exist as a ship_data.csv row (comment/blank-id
    rows don't count); an id this file has no row for is refused rather than silently skipped.
    """
    assignments = _parse_hull_bay_assignments(options.get("hulls") or [])
    path = root / "data" / "hulls" / "ship_data.csv"
    if not path.is_file():
        raise FixerError(f"No ship_data.csv found at {path}.")
    raw = path.read_bytes()
    text, had_bom = _decode(raw)
    lines = text.splitlines(keepends=True)
    if not lines:
        raise FixerError(f"{path} is empty.")
    # Same quoted-multiline-field guard as wing-data-missing-role-desc-column: refuse rather than
    # guess row boundaries if a quoted field spans lines.
    records = [row for row in csv.reader(io.StringIO(text)) if row]
    if len(records) != sum(1 for line in lines if line.strip()):
        raise FixerError(f"{path} has a quoted field spanning several lines; add fighter bays by hand rather than guess the row boundaries.")

    header_content, header_term = _split_terminator(lines[0])
    header_fields = [_field_value(item[2]) for item in _line_field_spans(header_content)]
    normalized_header = [cell.strip().lower() for cell in header_fields]
    if "id" not in normalized_header:
        raise FixerError(f"{path} has no 'id' column.")
    id_index = normalized_header.index("id")
    width = len(header_fields)
    add_column = "fighter bays" not in normalized_header
    bay_index = width if add_column else normalized_header.index("fighter bays")

    def row_hull_id(content: str) -> str:
        spans = _line_field_spans(content)
        return _field_value(spans[id_index][2]).strip() if id_index < len(spans) else ""

    existing_ids = {
        row_hull_id(_split_terminator(line)[0])
        for line in lines[1:] if _split_terminator(line)[0].strip()
    }
    existing_ids = {hull_id for hull_id in existing_ids if hull_id and not hull_id.startswith("#")}
    unknown = sorted(set(assignments) - existing_ids)
    if unknown:
        raise FixerError(f"{path} has no row for hull id(s): {', '.join(unknown)}.")

    edited_lines = [header_content + (",fighter bays" if add_column else "") + (header_term or "\n")]
    touched: set[str] = set()
    for line in lines[1:]:
        content, term = _split_terminator(line)
        if not content.strip():
            edited_lines.append(line)
            continue
        spans = _line_field_spans(content)
        hull_id = row_hull_id(content)
        present = len(spans)
        if hull_id in assignments and not hull_id.startswith("#"):
            count = assignments[hull_id]
            touched.add(hull_id)
            if add_column:
                padded = content + ("," * max(0, width - present))
                edited_lines.append(padded + "," + str(count) + term)
            elif present <= bay_index:
                padded = content + ("," * (bay_index - present + 1))
                pad_start, pad_end, _pad_raw = _line_field_spans(padded)[bay_index]
                edited_lines.append(padded[:pad_start] + str(count) + padded[pad_end:] + term)
            else:
                start, end, raw_field = spans[bay_index]
                edited_lines.append(content[:start] + _quote_like(raw_field, str(count)) + content[end:] + term)
        elif add_column:
            # Not an approved hull: pad so the new blank column still lands at the same position.
            edited_lines.append(content + ("," * max(0, width - present)) + "," + term)
        else:
            edited_lines.append(line)

    missed = sorted(set(assignments) - touched)
    if missed:
        raise FixerError(f"{path}: could not locate row(s) for hull id(s): {', '.join(missed)}.")
    return [FileChange(path=path, before=raw, after=_encode("".join(edited_lines), had_bom))]


# ---------------------------------------------------------------------------
# Fixer: mod-info-game-version-inexact
# ---------------------------------------------------------------------------

_GAME_VERSION_PATTERN = re.compile(
    r"(?P<key>[\'\"]gameVersion[\'\"])(?P<sep>\s*:\s*)(?P<value>\"(?:\\.|[^\"\\])*\"|\'(?:\\.|[^\'\\])*\')"
)


def _fix_mod_info_game_version_inexact(root: Path, options: dict) -> list[FileChange]:
    target_version = options.get("target_game_version")
    if not target_version:
        raise FixerError("--target-game-version is required for mod-info-game-version-inexact.")
    path = root / "mod_info.json"
    if not path.is_file():
        raise FixerError(f"No mod_info.json found at {path}.")
    raw = path.read_bytes()
    text, had_bom = _decode(raw)
    match = _GAME_VERSION_PATTERN.search(text)
    if match is None:
        raise FixerError(f"{path} has no 'gameVersion' string to fix.")
    old_literal = match.group("value")
    quote = old_literal[0]
    old_value = _string_literal_to_text(old_literal)
    if old_value == target_version:
        raise FixerError(f"{path} gameVersion is already '{target_version}'; nothing to fix.")
    new_literal = _text_to_string_literal(target_version, quote)
    new_text = text[: match.start("value")] + new_literal + text[match.end("value") :]
    try:
        parsed, _tolerances = _parse_json(new_text)
    except json.JSONDecodeError as exc:
        raise FixerError(f"Edited {path} failed to re-parse: {exc}") from exc
    if not isinstance(parsed, dict) or parsed.get("gameVersion") != target_version:
        raise FixerError(f"Edited {path} did not round-trip gameVersion as expected.")
    return [FileChange(path=path, before=raw, after=_encode(new_text, had_bom))]


# ---------------------------------------------------------------------------
# Fixer: csv-row-extra-columns
# ---------------------------------------------------------------------------


def _fix_csv_row_extra_columns(root: Path, options: dict) -> list[FileChange]:
    changes: list[FileChange] = []
    for path in sorted(root.rglob("*.csv")):
        try:
            raw = path.read_bytes()
            text, had_bom = _decode(raw)
        except (OSError, UnicodeDecodeError):
            continue
        records = _csv_records(text)
        if not records:
            continue
        header_start, header_end = records[0]
        header_content, _header_term = _split_terminator(text[header_start:header_end])
        try:
            header = next(csv.reader(io.StringIO(header_content)))
        except (csv.Error, StopIteration):
            continue
        if not header or not any(cell.strip() for cell in header):
            continue
        header_len = len(header)

        edits: list[tuple[int, int, str]] = []
        for rec_start, rec_end in records[1:]:
            record_text = text[rec_start:rec_end]
            content, term = _split_terminator(record_text)
            if not content.strip():
                continue
            try:
                fields = next(csv.reader(io.StringIO(content)))
            except (csv.Error, StopIteration):
                continue
            if len(fields) <= header_len:
                continue
            extras = fields[header_len:]
            if any(value.strip() for value in extras):
                raise FixerError(
                    f"{_relative(root, path)}: a csv-row-extra-columns row has non-empty extra "
                    f"field(s) ({extras!r}); refusing to drop data."
                )
            spans = _line_field_spans(content)
            if header_len == 0 or header_len - 1 >= len(spans):
                continue
            cut_at = spans[header_len - 1][1]
            edits.append((rec_start, rec_end, content[:cut_at] + term))

        if not edits:
            continue
        new_text = text
        for rec_start, rec_end, replacement in sorted(edits, key=lambda item: item[0], reverse=True):
            new_text = new_text[:rec_start] + replacement + new_text[rec_end:]
        changes.append(FileChange(path=path, before=raw, after=_encode(new_text, had_bom)))

    if not changes:
        raise FixerError("No csv-row-extra-columns rows with only empty extra fields were found to fix.")
    return changes


# ---------------------------------------------------------------------------
# Fixer: csv-missing-design-type-column
# ---------------------------------------------------------------------------


def _fix_csv_missing_design_type_column(root: Path, options: dict) -> list[FileChange]:
    design_type = options.get("design_type")
    prefixes = options.get("id_prefixes") or []
    design_color = options.get("design_color")
    if not design_type:
        raise FixerError("--design-type is required for csv-missing-design-type-column.")
    if not prefixes:
        raise FixerError("At least one --id-prefix is required for csv-missing-design-type-column.")
    if not design_color:
        raise FixerError("--design-color R,G,B is required for csv-missing-design-type-column.")
    rgb = _parse_rgb(design_color)

    changes: list[FileChange] = []
    any_csv_fixed = False
    for parts in DESIGN_TYPE_CSV_TARGETS:
        path = root.joinpath(*parts)
        if not path.is_file():
            continue
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        lines = text.splitlines(keepends=True)
        if not lines:
            continue
        header_content, header_term = _split_terminator(lines[0])
        try:
            header_fields = next(csv.reader(io.StringIO(header_content)))
        except (csv.Error, StopIteration):
            continue
        normalized = [cell.strip().lower() for cell in header_fields]
        if any("tech" in cell or "manufacturer" in cell for cell in normalized):
            continue
        header_width = len(header_fields)

        new_lines = [header_content + "," + _csv_escape("tech/manufacturer") + header_term]
        for line in lines[1:]:
            content, term = _split_terminator(line)
            if not content.strip():
                new_lines.append(line)
                continue
            try:
                fields = next(csv.reader(io.StringIO(content)))
            except (csv.Error, StopIteration):
                new_lines.append(line)
                continue
            row_id = fields[0].strip() if fields else ""
            missing = header_width - len(fields)
            padded_content = content + ("," * missing if missing > 0 else "")
            value = design_type if any(row_id.startswith(prefix) for prefix in prefixes) else ""
            new_lines.append(padded_content + "," + _csv_escape(value) + term)

        new_text = "".join(new_lines)
        changes.append(FileChange(path=path, before=raw, after=_encode(new_text, had_bom)))
        any_csv_fixed = True

    if not any_csv_fixed:
        raise FixerError("Neither ship_data.csv nor weapon_data.csv is missing a tech/manufacturer column.")

    settings_change = _add_design_type_color(root / "data" / "config" / "settings.json", design_type, rgb)
    if settings_change is not None:
        changes.append(settings_change)
    return changes


def _add_design_type_color(path: Path, name: str, rgb: list[int]) -> FileChange | None:
    entry_text = f'"designTypeColors":{{"{name}":[{rgb[0]},{rgb[1]},{rgb[2]},255]}}'
    if not path.is_file():
        new_text = "{" + entry_text + "}\n"
        try:
            _parse_json(new_text)
        except json.JSONDecodeError as exc:
            raise FixerError(f"Generated {path} failed to parse: {exc}") from exc
        return FileChange(path=path, before=b"", after=new_text.encode("utf-8"), existed_before=False)

    raw = path.read_bytes()
    text, had_bom = _decode(raw)
    data = _load_lenient_json_file(path)
    if isinstance(data, dict) and "designTypeColors" in data:
        return None
    brace_index = text.find("{")
    if brace_index == -1:
        raise FixerError(f"{path} has no '{{' to insert designTypeColors after.")
    new_text = text[: brace_index + 1] + entry_text + "," + text[brace_index + 1 :]
    try:
        parsed, _tolerances = _parse_json(new_text)
    except json.JSONDecodeError as exc:
        raise FixerError(f"Edited {path} failed to re-parse: {exc}") from exc
    if not isinstance(parsed, dict) or "designTypeColors" not in parsed:
        raise FixerError(f"Edited {path} did not round-trip designTypeColors as expected.")
    return FileChange(path=path, before=raw, after=_encode(new_text, had_bom))


# ---------------------------------------------------------------------------
# Fixer: procgen-planet-row-missing / procgen-star-row-missing
# ---------------------------------------------------------------------------


def _fix_procgen_row_missing(root: Path, finding_id: str, options: dict) -> list[FileChange]:
    vanilla_core = options.get("vanilla_core")
    type_id = options.get("type_id")
    from_vanilla_id = options.get("from_vanilla_id")
    if not vanilla_core:
        raise FixerError(f"--vanilla-core is required for {finding_id}.")
    if not type_id:
        raise FixerError(f"--type-id is required for {finding_id}.")
    if not from_vanilla_id:
        raise FixerError(f"--from-vanilla-id is required for {finding_id}.")

    is_star = finding_id == "procgen-star-row-missing"
    csv_name = "star_gen_data.csv" if is_star else "planet_gen_data.csv"
    freq_columns = ["freqYOUNG", "freqAVERAGE", "freqOLD"] if is_star else ["frequency"]

    vanilla_path = Path(vanilla_core).expanduser().resolve() / "data" / "campaign" / "procgen" / csv_name
    if not vanilla_path.is_file():
        raise FixerError(f"Vanilla {csv_name} not found at {vanilla_path}.")
    vanilla_text, _vanilla_bom = _decode(vanilla_path.read_bytes())
    vanilla_rows = list(csv.reader(io.StringIO(vanilla_text)))
    if not vanilla_rows:
        raise FixerError(f"{vanilla_path} has no header row.")
    header = vanilla_rows[0]
    normalized_header = [cell.strip() for cell in header]
    match_row: list[str] | None = None
    for row in vanilla_rows[1:]:
        if row and row[0].strip() == from_vanilla_id:
            match_row = row
            break
    if match_row is None:
        raise FixerError(f"No row with id '{from_vanilla_id}' found in vanilla {csv_name}.")

    new_row = list(match_row)
    if len(new_row) < len(header):
        new_row += [""] * (len(header) - len(new_row))
    new_row[0] = type_id
    for freq_col in freq_columns:
        if freq_col in normalized_header:
            new_row[normalized_header.index(freq_col)] = "0"

    mod_path = root / "data" / "campaign" / "procgen" / csv_name
    if mod_path.is_file():
        raw = mod_path.read_bytes()
        text, had_bom = _decode(raw)
        existing_ids = set()
        for row in csv.reader(io.StringIO(text)):
            if row and row[0].strip() and not row[0].strip().startswith("#"):
                existing_ids.add(row[0].strip())
        if type_id in existing_ids:
            raise FixerError(f"{mod_path} already has a row with id '{type_id}'.")
        prefix = "" if (not text or text.endswith(("\n", "\r"))) else "\n"
        new_text = text + prefix + _format_csv_row(new_row) + "\n"
        existed_before = True
    else:
        raw = b""
        had_bom = False
        new_text = _format_csv_row(header) + "\n" + _format_csv_row(new_row) + "\n"
        existed_before = False

    return [FileChange(path=mod_path, before=raw, after=_encode(new_text, had_bom), existed_before=existed_before)]


# ---------------------------------------------------------------------------
# Fixer: faction-known-lists-missing
# ---------------------------------------------------------------------------


def _hull_ids(root: Path) -> set[str]:
    ids: set[str] = set()
    for row in _read_csv_rows(root / "data" / "hulls" / "ship_data.csv") or []:
        hull_id = (row.get("id") or "").strip()
        if hull_id and not hull_id.startswith("#"):
            ids.add(hull_id)
    skins_dir = root / "data" / "hulls" / "skins"
    if skins_dir.is_dir():
        for path in skins_dir.glob("*.skin"):
            data = _load_lenient_json_file(path)
            if isinstance(data, dict):
                skin_hull_id = data.get("skinHullId")
                if isinstance(skin_hull_id, str) and skin_hull_id:
                    ids.add(skin_hull_id)
    return ids


def _weapon_ids(root: Path) -> set[str]:
    ids: set[str] = set()
    for row in _read_csv_rows(root / "data" / "weapons" / "weapon_data.csv") or []:
        weapon_id = (row.get("id") or "").strip()
        if weapon_id and not weapon_id.startswith("#"):
            ids.add(weapon_id)
    return ids


def _load_variant(search_roots: list[Path], variant_id: str) -> dict | None:
    for search_root in search_roots:
        direct = search_root / "data" / "variants" / f"{variant_id}.variant"
        if direct.is_file():
            data = _load_lenient_json_file(direct)
            if isinstance(data, dict):
                return data
    for search_root in search_roots:
        variants_root = search_root / "data" / "variants"
        if not variants_root.is_dir():
            continue
        for path in variants_root.rglob(f"{variant_id}.variant"):
            data = _load_lenient_json_file(path)
            if isinstance(data, dict):
                return data
    return None


def _fix_faction_known_lists_missing(root: Path, options: dict) -> list[FileChange]:
    faction_file = options.get("faction_file")
    vanilla_core = options.get("vanilla_core")
    if not faction_file:
        raise FixerError("--faction-file is required for faction-known-lists-missing.")
    if not vanilla_core:
        raise FixerError("--vanilla-core is required for faction-known-lists-missing.")

    faction_path = Path(faction_file)
    if not faction_path.is_absolute():
        faction_path = root / faction_path
    faction_path = faction_path.resolve()
    if not faction_path.is_file():
        raise FixerError(f"{faction_path} does not exist.")
    vanilla_root = Path(vanilla_core).expanduser().resolve()

    raw = faction_path.read_bytes()
    text, had_bom = _decode(raw)
    data = _load_lenient_json_file(faction_path)
    if not isinstance(data, dict):
        raise FixerError(f"{faction_path} could not be parsed as JSON.")
    ship_roles = data.get("shipRoles")
    if not isinstance(ship_roles, dict):
        raise FixerError(f"{faction_path} has no 'shipRoles' object to derive known lists from.")

    variant_ids: set[str] = set()
    for block in ship_roles.values():
        if not isinstance(block, dict):
            continue
        for key in block:
            if key in FACTION_SPECIAL_ROLE_KEYS:
                continue
            variant_ids.add(key)

    search_roots = [root, vanilla_root]
    valid_hull_ids = _hull_ids(root) | _hull_ids(vanilla_root)
    valid_weapon_ids = _weapon_ids(root) | _weapon_ids(vanilla_root)
    valid_wing_ids = _wing_ids_set(root / "data" / "hulls" / "wing_data.csv") | _wing_ids_set(
        vanilla_root / "data" / "hulls" / "wing_data.csv"
    )

    known_hulls: set[str] = set()
    known_weapons: set[str] = set()
    known_fighters: set[str] = set()
    unresolved: list[str] = []

    for variant_id in sorted(variant_ids):
        variant_data = _load_variant(search_roots, variant_id)
        if variant_data is None:
            unresolved.append(f"variant:{variant_id} (not found)")
            continue
        hull_id = variant_data.get("hullId")
        if isinstance(hull_id, str) and hull_id:
            if hull_id not in valid_hull_ids:
                unresolved.append(f"hull:{hull_id} (from variant {variant_id})")
            else:
                known_hulls.add(hull_id)
        for group in variant_data.get("weaponGroups", []) or []:
            if not isinstance(group, dict):
                continue
            assigned = group.get("weapons", {})
            if isinstance(assigned, dict):
                for weapon_id in assigned.values():
                    if not isinstance(weapon_id, str) or not weapon_id:
                        continue
                    if weapon_id not in valid_weapon_ids:
                        unresolved.append(f"weapon:{weapon_id} (from variant {variant_id})")
                    else:
                        known_weapons.add(weapon_id)
        for wing_id in variant_data.get("wings", []) or []:
            if not isinstance(wing_id, str) or not wing_id:
                continue
            if wing_id not in valid_wing_ids:
                unresolved.append(f"wing:{wing_id} (from variant {variant_id})")
            else:
                known_fighters.add(wing_id)

    if unresolved:
        raise FixerError("Refusing to derive known-lists: unresolved id(s): " + "; ".join(sorted(set(unresolved))))

    insertion = (
        '"knownShips":{"hulls":[' + ",".join(json.dumps(item) for item in sorted(known_hulls)) + "]},"
        '"knownWeapons":{"weapons":[' + ",".join(json.dumps(item) for item in sorted(known_weapons)) + "]},"
        '"knownFighters":{"fighters":[' + ",".join(json.dumps(item) for item in sorted(known_fighters)) + "]},"
    )

    ship_roles_key_pattern = re.compile(r"['\"]shipRoles['\"]\s*:")
    match = ship_roles_key_pattern.search(text)
    if match is None:
        raise FixerError(f"{faction_path} has no 'shipRoles' key text to insert before.")
    insert_at = match.start()
    new_text = text[:insert_at] + insertion + text[insert_at:]
    try:
        parsed, _tolerances = _parse_json(new_text)
    except json.JSONDecodeError as exc:
        raise FixerError(f"Edited {faction_path} failed to re-parse: {exc}") from exc
    if not isinstance(parsed, dict) or "knownShips" not in parsed:
        raise FixerError(f"Edited {faction_path} did not round-trip knownShips as expected.")
    return [FileChange(path=faction_path, before=raw, after=_encode(new_text, had_bom))]


# ---------------------------------------------------------------------------
# Fixer: mod-info-triage-banner
# ---------------------------------------------------------------------------

_LEADING_BANNER_PATTERN = re.compile(r"^\(([^)]*)\)\s*")


def _fix_mod_info_triage_banner(root: Path, options: dict) -> list[FileChange]:
    path = root / "mod_info.json"
    if not path.is_file():
        raise FixerError(f"No mod_info.json found at {path}.")
    raw = path.read_bytes()
    text, had_bom = _decode(raw)
    # Top-level only (build_tag._structural_depths): a "dependencies" entry can carry its own
    # "name" (e.g. {"id":"revenantlib","name":"RevenantLib"}) before the mod's real one.
    match = _find_top_level_key(text, _NAME_PATTERN, _structural_depths(text))
    if match is None:
        raise FixerError(f"{path} has no top-level 'name' string.")
    old_literal = match.group("value")
    old_name = _string_literal_to_text(old_literal)
    leading_match = _LEADING_BANNER_PATTERN.match(old_name)
    if leading_match is None or not MOD_INFO_TRIAGE_BANNER_PATTERN.search(leading_match.group(0)):
        raise FixerError(f"{path}'s name has no leading parenthesized triage banner to remove ('{old_name}').")
    new_name = old_name[leading_match.end() :]
    new_literal = _text_to_string_literal(new_name, old_literal[0])
    new_text = text[: match.start("value")] + new_literal + text[match.end("value") :]
    try:
        parsed, _tolerances = _parse_json(new_text)
    except json.JSONDecodeError as exc:
        raise FixerError(f"Edited {path} failed to re-parse: {exc}") from exc
    if not isinstance(parsed, dict) or parsed.get("name") != new_name:
        raise FixerError(f"Edited {path} did not round-trip name as expected.")
    return [FileChange(path=path, before=raw, after=_encode(new_text, had_bom))]


# ---------------------------------------------------------------------------
# Dispatch, diffing, backup/apply
# ---------------------------------------------------------------------------

_FIXER_FUNCS = {
    "wing-role-assault-removed": _fix_wing_role_assault_removed,
    "mod-info-game-version-inexact": _fix_mod_info_game_version_inexact,
    "wing-data-missing-role-desc-column": _fix_wing_data_missing_role_desc_column,
    "target-interface-method-missing": _fix_target_interface_method_missing,
    "removed-api-call": _fix_removed_api_call,
    "csv-row-extra-columns": _fix_csv_row_extra_columns,
    "csv-missing-design-type-column": _fix_csv_missing_design_type_column,
    "procgen-planet-row-missing": lambda root, options: _fix_procgen_row_missing(root, "procgen-planet-row-missing", options),
    "procgen-star-row-missing": lambda root, options: _fix_procgen_row_missing(root, "procgen-star-row-missing", options),
    "faction-known-lists-missing": _fix_faction_known_lists_missing,
    "mod-info-triage-banner": _fix_mod_info_triage_banner,
    "carrier-bays-proposal": _fix_carrier_bays_proposal,
    "revenantlib-fold-conflict": _fix_revenantlib_fold_conflict,
    "undeclared-library-dependency": _fix_undeclared_library_dependency,
}


def compute_fix(mod_dir: Path, finding_id: str, options: dict | None = None) -> FixPlan:
    """Compute (never write) the surgical edit(s) for one supported finding id."""
    if finding_id not in SUPPORTED_FINDINGS:
        raise FixerError(f"Unsupported finding id '{finding_id}'. Supported: {', '.join(SUPPORTED_FINDINGS)}")
    root = Path(mod_dir).expanduser().resolve()
    if not root.is_dir():
        raise FixerError(f"{root} is not an existing directory.")
    handler = _FIXER_FUNCS[finding_id]
    changes = [change for change in handler(root, options or {}) if change.changed]
    if not changes:
        raise FixerError(f"No change was computed for finding '{finding_id}'.")
    return FixPlan(finding_id=finding_id, mod_root=root, changes=changes)


def unified_diff_for_change(change: FileChange) -> str:
    """A unified diff for one FileChange, decoding best-effort for display only (never affects the write)."""
    try:
        before_text = change.before.decode("utf-8-sig")
    except UnicodeDecodeError:
        before_text = repr(change.before)
    try:
        after_text = change.after.decode("utf-8-sig")
    except UnicodeDecodeError:
        after_text = repr(change.after)
    diff = difflib.unified_diff(
        before_text.splitlines(keepends=True),
        after_text.splitlines(keepends=True),
        fromfile=str(change.path) if change.existed_before else "/dev/null",
        tofile=str(change.path),
    )
    return "".join(diff)


def _backup_path(path: Path, finding_id: str) -> Path:
    base = path.with_name(f"{path.name}.pre-bf-fix-{finding_id}.bak")
    if not base.exists():
        return base
    counter = 2
    while True:
        candidate = path.with_name(f"{path.name}.pre-bf-fix-{finding_id}.bak.{counter}")
        if not candidate.exists():
            return candidate
        counter += 1


def apply_fix(plan: FixPlan) -> list[dict[str, object]]:
    """Write every planned change, keeping a `.pre-bf-fix-<id>.bak` backup per pre-existing file."""
    applied: list[dict[str, object]] = []
    for change in plan.changes:
        backup: Path | None = None
        if change.existed_before:
            backup = _backup_path(change.path, plan.finding_id)
            backup.write_bytes(change.before)
        change.path.parent.mkdir(parents=True, exist_ok=True)
        change.path.write_bytes(change.after)
        applied.append({"path": str(change.path), "backup": str(backup) if backup is not None else None})
    return applied
