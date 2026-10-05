from __future__ import annotations

import csv
import difflib
import fnmatch
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .build_tag import _NAME_PATTERN, _STRING_LITERAL, _find_top_level_key, _string_literal_to_text, _structural_depths, _text_to_string_literal
from .scanner import (
    DESIGN_TYPE_CSV_TARGETS,
    FACTION_SPECIAL_ROLE_KEYS,
    LEGACY_PERSONALITY_IDS,
    CUSTOM_UI_PLUGIN_PATTERN,
    MOD_INFO_TRIAGE_BANNER_PATTERN,
    _FULLWIDTH_NUMBER_CHARS,
    _NUMBER_CELL,
    REMOVED_API_CALLS,
    _blank_java_comments,
    _load_lenient_json_file,
    _parse_json,
    _read_csv_rows,
    _read_csv_rows_lenient,
    _relative,
    _removed_api_call_spans,
    _SOURCE_SET_PERSONALITY,
    _wing_id_variant_map,
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
    "rules-firebest-populate-options",
    "personality-id-unknown",
    "hullmod-instance-state",
    "nexerelin-corvus-mode-import",
    "spawned-ship-captain-personality-risk",
    "json-missing-comma",
    "builtin-wing-is-hullmod",
    "wing-op-cost-blank",
    "campaign-lookup-dereferenced-unguarded",
    "temporary-market-fleet-source",
    "faction-trait-weight-legacy-personality-id",
    "shiproles-wing-id",
    "csv-fullwidth-number",
    "ship-data-missing-fighter-bays-column",
    "missing-custom-ui-button-pressed-callback",
    "shippable-work-file",
    "data-file-not-utf8",
    "fleet-type-name-missing",
    "variant-op-over-budget",
    "procgen-mod-body-leak",
    "csv-slash-quote-escape",
    "variant-wings-exceed-bays",
    "variant-weapon-slot-mismatch",
    "variant-weapon-slot-missing",
    "hard-coded-campaign-system-reference",
    "hard-coded-campaign-entity-reference",
)


class FixerError(ValueError):
    """Raised for an unsupported finding id, a missing required option, or a refusal to guess."""


@dataclass
class FileChange:
    path: Path
    before: bytes
    after: bytes
    existed_before: bool = True
    removed: bool = False  # delete `path`; a plan that also writes the same bytes elsewhere is a move

    @property
    def changed(self) -> bool:
        return self.removed or self.before != self.after


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
# RC8 defaults for HullModEffect, read from starfarer.api.jar/BaseHullMod with javap (2026-09-14,
# 2026-09-22): showInRefitScreenModPickerFor defaults to visible; isSModEffectAPenalty defaults to
# false (an S-mod of this hullmod is a bonus, not a penalty).
_HULL_MOD_EFFECT_DEFAULTS = (
    ("showInRefitScreenModPickerFor", "public boolean showInRefitScreenModPickerFor(com.fs.starfarer.api.combat.ShipAPI ship) { return true; }"),
    ("isSModEffectAPenalty", "public boolean isSModEffectAPenalty() { return false; }"),
)


def _insert_before_class_end(text: str, members: list[str], note: str) -> str:
    end = text.rstrip().rfind("}")
    if end < 0 or not members:
        return text
    newline = "\r\n" if "\r\n" in text else "\n"
    block = newline + f"    // BridgeForge: {note}" + newline + newline.join(f"    {member}" for member in members) + newline
    return text[:end] + block + text[end:]


def _findings_of(root: Path, options: dict, finding_id: str) -> list:
    """This finding id's findings: the caller's own scan when it passes one (`options["scan_findings"]`,
    Finding objects or their dicts, as `revive` does, so a fixer run doesn't rescan the whole mod),
    else a fresh scan. Only the files and evidence are read, so either source gives the same edit.
    """
    supplied = options.get("scan_findings")
    if supplied is None:
        from .scanner import scan_mod

        return [f for f in scan_mod(root, vanilla_core=options.get("vanilla_core")).findings if f.id == finding_id]
    from types import SimpleNamespace

    found = [SimpleNamespace(**f) if isinstance(f, dict) else f for f in supplied]
    return [f for f in found if f.id == finding_id]


def _fix_target_interface_method_missing(root: Path, options: dict) -> list[FileChange]:
    """Bring loose scripts up to RC8's callback signatures (they fail to compile at load otherwise).

    - ShipSystemStatsScript: add the six *Override methods with BaseShipSystemScript's defaults.
    - OnHitEffectPlugin.onHit: insert the ApplyDamageResultAPI parameter before CombatEngineAPI.
    - HullModEffect: add showInRefitScreenModPickerFor/isSModEffectAPenalty, BaseHullMod's defaults.
    Bodies are untouched. Classes compiled into a jar need the jar rebuilt, so those are refused.
    """

    files = sorted({f.file for f in _findings_of(root, options, "target-interface-method-missing") if f.file})
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
        if re.search(r"\bimplements\s+(?:[^{]*?\b)?HullModEffect\b", new):
            missing = [stub for name, stub in _HULL_MOD_EFFECT_DEFAULTS if not re.search(rf"\b{name}\s*\(", new)]
            new = _insert_before_class_end(new, missing, "RC8 HullModEffect method(s), BaseHullMod defaults")
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

    findings = _findings_of(root, options, "revenantlib-fold-conflict")
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
    exact id `scanner.LIBRARY_DEPENDENCY_IDS` maps to. Only an UNGUARDED use is declared. A guarded one
    (`guard:present` in the evidence: an isModEnabled check or a loadClass/Class.forName probe) is an
    optional integration and is left alone: declaring it makes the library mandatory and changes what the
    mod does. Exigency 0.8.01a (2026-09-28) probes for Nexerelin and runs its illegal-tech event only
    without it; this fixer declared Nexerelin, which switched the event off and forced a Nexerelin random
    sector on every test (the old note here called declaring "safe regardless" of a guard; it was not).

    Hand-verified this session, twice: `scanner.LIBRARY_DEPENDENCY_IDS` had the wrong case for two
    libraries (`magiclib`/`shaderlib` instead of the real `MagicLib`/`shaderLib`, found by reading
    those libraries' own installed `mod_info.json`, corroborated by `revival_audit.py`'s already-
    correct copy of the same table) - fixed there before this fixer was built on top of it, so a
    written dependency actually matches what the game expects, not just what the scanner's own
    case-insensitive comparison would have accepted.
    """
    from .scanner import LIBRARY_DEPENDENCY_IDS

    findings = _findings_of(root, options, "undeclared-library-dependency")
    if not findings:
        raise FixerError("No undeclared-library-dependency finding for this mod.")

    to_add: dict[str, str] = {}  # dependency_id -> library display name
    findings = [f for f in findings if "guard:present" not in (f.evidence or [])]
    if not findings:
        raise FixerError("Every undeclared-library-dependency finding here is guarded (an optional integration); nothing is declared.")
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
    return _carrier_bays_edit(root, _parse_hull_bay_assignments(options.get("hulls") or []))


def _fix_ship_data_missing_fighter_bays_column(root: Path, options: dict) -> list[FileChange]:
    """Add RC8's 'fighter bays' column to a pre-0.8a ship_data.csv, blank for every hull (P15, 2026-09-26).

    Behaviour-neutral: a hull without the column already loads with 0 bays, and a blank cell reads the
    same, so this only makes the schema current. Carriers still need their counts from
    `carrier-bays-proposal` (--hull ID=N), which is an owner decision.
    """
    path = root / "data" / "hulls" / "ship_data.csv"
    header = next(csv.reader(io.StringIO(_decode(path.read_bytes())[0])), []) if path.is_file() else []
    if "fighter bays" in [cell.strip().lower() for cell in header]:
        raise FixerError(f"{path} already has a 'fighter bays' column.")
    return _carrier_bays_edit(root, {})


def _carrier_bays_edit(root: Path, assignments: dict[str, int]) -> list[FileChange]:
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

        # A space before an opening quote (`SHIP, "text, with commas"`) stops the field being read as quoted: its
        # commas split it and its line breaks end the record early (SWP Triumphant's descriptions.csv, 2026-10-01).
        # Dropping that space everywhere, and only when every row then fits the header, restores the rows as authored.
        try:
            widths = [len(row) for row in csv.reader(io.StringIO(text))]
        except csv.Error:
            widths = []
        if any(width > header_len for width in widths[1:]):
            unspaced = re.sub(r'(^|,)[ \t]+"', r'\1"', text, flags=re.M)
            try:
                rewidths = [len(row) for row in csv.reader(io.StringIO(unspaced))]
            except csv.Error:
                rewidths = []
            if unspaced != text and rewidths and all(width <= header_len for width in rewidths[1:]):
                changes.append(FileChange(path=path, before=raw, after=_encode(unspaced, had_bom)))
                continue

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
            # A space before an opening quote (`SHIP, "text, with commas"`) stops the field being read as quoted, so
            # its commas split it (SWP Triumphant's descriptions.csv, 2026-10-01). Dropping that space, and only
            # when the row then has exactly the header's width, restores the field as authored.
            unspaced = re.sub(r'(^|,)[ \t]+"', r'\1"', content)
            if unspaced != content:
                try:
                    respaced = next(csv.reader(io.StringIO(unspaced)))
                except (csv.Error, StopIteration):
                    respaced = []
                if len(respaced) == header_len:
                    edits.append((rec_start, rec_end, unspaced + term))
                    continue
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
    # Unattended (owner ruling 2026-09-30): add the column with every cell blank, as some vanilla rows are, so the
    # loader finds it; no design type is invented, so no settings.json colour is needed.
    blank = bool(options.get("blank_design_type"))
    if blank:
        design_type, prefixes = "", []
    elif not design_type:
        raise FixerError("--design-type is required for csv-missing-design-type-column.")
    if not blank and not prefixes:
        raise FixerError("At least one --id-prefix is required for csv-missing-design-type-column.")
    if not blank and not design_color:
        raise FixerError("--design-color R,G,B is required for csv-missing-design-type-column.")
    rgb = _parse_rgb(design_color) if not blank else None

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

    settings_change = None if blank else _add_design_type_color(root / "data" / "config" / "settings.json", design_type, rgb)
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


_GEN_ROW_KEYWORDS = (  # first keyword found in the type's id or name picks the vanilla row to copy
    ("black_hole", "black_hole"), ("blackhole", "black_hole"), ("neutron", "star_neutron"), ("pulsar", "star_neutron"),
    ("dwarf", "star_browndwarf"), ("blue", "star_blue_giant"), ("red", "star_red_dwarf"), ("orange", "star_orange"),
    ("white", "star_white"), ("yellow", "star_yellow"),
    ("ice_giant", "ice_giant"), ("gas", "gas_giant"), ("giant", "gas_giant"), ("lava", "lava"), ("volcan", "lava"),
    ("toxic", "toxic"), ("acid", "toxic"), ("irradiated", "irradiated"), ("radiat", "irradiated"),
    ("cryo", "cryovolcanic"), ("frozen", "frozen"), ("ice", "frozen"), ("snow", "frozen"), ("tundra", "tundra"),
    ("jungle", "jungle"), ("water", "water"), ("ocean", "water"), ("terran", "terran"), ("earth", "terran"),
    ("desert", "desert"), ("arid", "arid"), ("rock", "rocky_metallic"), ("metal", "rocky_metallic"), ("barren", "barren"),
)


def nearest_vanilla_gen_row(type_id: str, name: str, vanilla_ids: set[str], is_star: bool) -> str | None:
    """The vanilla procgen row to copy for a mod planet or star type with none: the first keyword of its id or name,
    else barren / star_yellow. Frequency is zeroed after the copy, so only scripted placement uses it; the category
    picks the conditions a scripted planet rolls, and the choice is in the reviewed diff."""
    text = f"{type_id} {name}".lower()
    for keyword, row in _GEN_ROW_KEYWORDS:
        if keyword in text and row in vanilla_ids and row.startswith(("star_", "black_hole")) == is_star:
            return row
    fallback = "star_yellow" if is_star else "barren"
    return fallback if fallback in vanilla_ids else None


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
    variant_ids: set[str] = set()
    if isinstance(ship_roles, dict):
        for block in ship_roles.values():
            if not isinstance(block, dict):
                continue
            for key in block:
                if key in FACTION_SPECIAL_ROLE_KEYS:
                    continue
                variant_ids.add(key)
    else:
        # A 0.6-era faction lists its fleets in fleetCompositions[*].ships ({"atol_Wayfarer":[1, 1], ...}) instead
        # of shipRoles (Antediluvians, Batavia, Qualljom and six more, 2026-09-30): the same variant and wing ids.
        for composition in (data.get("fleetCompositions") or {}).values():
            if isinstance(composition, dict) and isinstance(composition.get("ships"), dict):
                variant_ids.update(key for key in composition["ships"] if isinstance(key, str) and key)
    if not variant_ids:
        raise FixerError(f"{faction_path} has no shipRoles or fleetCompositions ships to derive known lists from.")

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
        if variant_id in valid_wing_ids and _load_variant(search_roots, variant_id) is None:
            # Pre-0.65 role and fleet lists named wings directly ("broadsword_wing"): a known fighter, not a variant.
            known_fighters.add(variant_id)
            continue
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

    depths = _structural_depths(text)
    match = None
    # Before the top-level key the lists were derived from: shipRoles, or a 0.6-era fleetCompositions.
    for key in ("shipRoles", "fleetCompositions"):
        match = _find_top_level_key(text, re.compile(r"(?P<key>['\"]?" + key + r"['\"]?)\s*:"), depths)
        if match is not None:
            break
    if match is None:
        raise FixerError(f"{faction_path} has no top-level 'shipRoles' or 'fleetCompositions' key to insert before.")
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


def _fullwidth_cells(path: Path) -> dict[str, str]:
    """{raw cell: ASCII number} for every cell the scanner's csv-fullwidth-number check reports."""
    import unicodedata

    cells: dict[str, str] = {}
    for row in _read_csv_rows_lenient(path) or []:
        for value in row.values():
            if isinstance(value, str) and _FULLWIDTH_NUMBER_CHARS.search(value):
                normalised = unicodedata.normalize("NFKC", value.replace("。", ".")).strip()
                if _NUMBER_CELL.fullmatch(normalised):
                    cells[value] = normalised
    return cells


def _fix_csv_fullwidth_number(root: Path, options: dict) -> list[FileChange]:
    """Rewrite full-width numeric CSV cells ('１５００', '0。5') as the ASCII number they spell (P15, 2026-09-26).

    Only whole cells the scanner reports are touched, keeping their quoting; prose with Chinese
    punctuation is left alone because it doesn't normalise to a plain number. The value is the one
    the author wrote, so this is behaviour-neutral: the loader couldn't parse the original.
    """
    data = root / "data"
    changes: list[FileChange] = []
    for path in sorted(data.rglob("*.csv")) if data.is_dir() else []:
        cells = _fullwidth_cells(path)
        if not cells:
            continue
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        new = text
        for value, number in cells.items():
            cell = re.compile(rf'(^|,)(")?{re.escape(value)}(?(2)")(?=,|\r|\n|$)', re.M)
            new = cell.sub(lambda m, number=number: m.group(1) + (m.group(2) or "") + number + (m.group(2) or ""), new)
            if cell.search(new) or new.count("\n") != text.count("\n"):
                raise FixerError(f"{path}: the full-width cell {value!r} could not be rewritten in place; fix it by hand.")
        if new == text:
            raise FixerError(f"{path}: the full-width cells sit inside multi-line or unusual quoting; fix them by hand.")
        changes.append(FileChange(path=path, before=raw, after=_encode(new, had_bom)))
    if not changes:
        raise FixerError("No CSV under data/ has a full-width numeric cell.")
    return changes


def _fix_missing_custom_ui_button_pressed_callback(root: Path, options: dict) -> list[FileChange]:
    """Add a no-op `buttonPressed(Object)` to CustomUIPanelPlugin blocks that lack it (P15, 2026-09-26).

    RC8's CustomUIPanelPlugin declares buttonPressed(Object) (the scanner's evidence), so an
    implementation without it fails to compile and the panel never opens. A panel with no buttons
    never receives the call, so an empty body keeps behaviour; a panel that has buttons needed a
    handler the old API didn't have, and the live test says whether it matters. Each block is found
    with the scanner's own brace-aware walk; an unbalanced block is refused. Loose data/ scripts
    only: jar sources need the jar rebuilt.
    """

    files = sorted({f.file for f in _findings_of(root, options, "missing-custom-ui-button-pressed-callback") if f.file})
    loose = [rel for rel in files if rel.startswith("data/")]
    if not loose:
        raise FixerError("No loose data/ script lacks buttonPressed(Object)" + (f" (jar sources need a rebuild: {', '.join(files[:5])})" if files else "") + ".")
    changes = []
    for rel in loose:
        path = root / rel
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        inserts = []
        for match in CUSTOM_UI_PLUGIN_PATTERN.finditer(text):
            opening = match.end() - 1 if text[match.end() - 1] == "{" else text.find("{", match.end())
            depth, closing = 0, -1
            for index in range(max(opening, 0), len(text)) if opening >= 0 else ():
                depth += {"{": 1, "}": -1}.get(text[index], 0)
                if depth == 0 and text[index] == "}":
                    closing = index
                    break
            if closing < 0:
                raise FixerError(f"{path}: a CustomUIPanelPlugin block has unbalanced braces; add buttonPressed(Object) by hand.")
            if not re.search(r"\bbuttonPressed\s*\(", text[opening:closing]):
                line_start = text.rfind("\n", 0, closing) + 1
                indent = re.match(r"[ \t]*", text[line_start:]).group(0)
                inserts.append((closing, f"{indent}    // Required by the 0.98a CustomUIPanelPlugin interface; added by BridgeForge as a no-op (the old API had no button callback).\n"
                                         f"{indent}    public void buttonPressed(Object buttonId) {{}}\n{indent}"))
        new = text
        for position, snippet in sorted(inserts, reverse=True):
            before = new[:position].rstrip(" \t")
            new = before + ("" if before.endswith("\n") else "\n") + snippet + new[position:]
        changes.append(FileChange(path=path, before=raw, after=_encode(new, had_bom)))
    return changes


# ---------------------------------------------------------------------------
# Fixer: rules-firebest-populate-options
# ---------------------------------------------------------------------------

_FIREBEST_POPULATE_OPTIONS_PATTERN = re.compile(r"\bFireBest(\s+)PopulateOptions\b")


def _fix_rules_firebest_populate_options(root: Path, options: dict) -> list[FileChange]:
    """FireBest PopulateOptions -> FireAll PopulateOptions in rules.csv (live bug VAC-DIALOG-01).

    FireBest runs only the single best-scoring rule; PopulateOptions menus are built by many rules
    together (trade, comm directory, Leave...), so FireBest leaves the player in a dialog with no way
    out. Vanilla's own rules.csv uses FireAll PopulateOptions everywhere (462 times) and FireBest never,
    so the rewrite is a literal keyword swap - same column, same surrounding whitespace.
    """
    path = root / "data" / "campaign" / "rules.csv"
    if not path.is_file():
        raise FixerError(f"No rules.csv found at {path}.")
    raw = path.read_bytes()
    text, had_bom = _decode(raw)
    new_text, count = _FIREBEST_POPULATE_OPTIONS_PATTERN.subn(r"FireAll\1PopulateOptions", text)
    if count == 0:
        raise FixerError(f"{path} has no 'FireBest PopulateOptions' to fix.")
    return [FileChange(path=path, before=raw, after=_encode(new_text, had_bom))]


# ---------------------------------------------------------------------------
# Fixer: personality-id-unknown (loose scripts only)
# ---------------------------------------------------------------------------


def _fix_personality_id_unknown(root: Path, options: dict) -> list[FileChange]:
    """cowardly/suicidal/fearless -> timid/reckless/reckless in setPersonality(...) (loose scripts only).

    RC8 dropped these 0.6-era personality ids (bridgeforge.scanner.LEGACY_PERSONALITY_IDS); an unknown
    id leaves the officer's personality null and Ship.getPersonality() NPEs on deploy - a Fatal dialog on
    the first affected ship (live run SK13-1d, SEEKER's missions). The mapping is the same one-to-one
    table the scanner's own finding explanation already suggests. A jar's bundled source needs the jar
    rebuilt, so a match found only there is refused rather than silently skipped.
    """

    files = sorted({f.file for f in _findings_of(root, options, "personality-id-unknown") if f.file})
    loose = [rel for rel in files if "!" not in rel]
    if not loose:
        detail = f" (jar sources need a rebuild: {', '.join(files[:5])})" if files else ""
        raise FixerError(f"No loose script has an unknown legacy personality id{detail}.")

    def _rewrite(match: re.Match) -> str:
        new = LEGACY_PERSONALITY_IDS.get(match.group(1))
        return f'setPersonality("{new}")' if new else match.group(0)

    changes: list[FileChange] = []
    for rel in loose:
        path = root / rel
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        new_text = _SOURCE_SET_PERSONALITY.sub(_rewrite, text)
        if new_text != text:
            changes.append(FileChange(path=path, before=raw, after=_encode(new_text, had_bom)))
    if not changes:
        raise FixerError("The flagged loose scripts could not be rewritten mechanically; fix them by hand.")
    return changes


# ---------------------------------------------------------------------------
# Fixer: nexerelin-corvus-mode-import (ROADMAP 34.13)
# ---------------------------------------------------------------------------


def _fix_nexerelin_corvus_mode_import(root: Path, options: dict) -> list[FileChange]:
    """SectorManager[.getManager()].getCorvusMode() -> (!Global.getSector().getMemoryWithoutUpdate()
    .getBoolean("$nex_randomSector")) and the Nexerelin import dropped (done by hand for Hiver Swarm, 2026-10-04;
    evidence in scanner._scan_nexerelin_corvus_mode_import). Without Nexerelin the key is absent and getBoolean
    returns false, i.e. "Corvus mode", which is the vanilla sector."""
    from .scanner import _NEX_CORVUS_CALL, _NEX_SECTOR_MANAGER_IMPORT

    replacement = '(!Global.getSector().getMemoryWithoutUpdate().getBoolean("$nex_randomSector"))'
    changes: list[FileChange] = []
    for rel in sorted({f.file for f in _findings_of(root, options, "nexerelin-corvus-mode-import") if f.file}):
        path = root / rel
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        new_text = _NEX_CORVUS_CALL.sub(lambda _m: replacement, _NEX_SECTOR_MANAGER_IMPORT.sub("", text, count=1))
        if "import com.fs.starfarer.api.Global;" not in new_text and "import com.fs.starfarer.api.*;" not in new_text:
            package = re.search(r"^package [\w.]+;\s*\n", new_text, re.M)
            at = package.end() if package else 0
            new_text = new_text[:at] + "import com.fs.starfarer.api.Global;\n" + new_text[at:]
        if new_text != text:
            changes.append(FileChange(path=path, before=raw, after=_encode(new_text, had_bom)))
    if not changes:
        raise FixerError("No loose script imports Nexerelin's SectorManager only for getCorvusMode().")
    return changes


# ---------------------------------------------------------------------------
# Fixer: campaign-lookup-dereferenced-unguarded (2026-10-04)
# ---------------------------------------------------------------------------

_VOID_METHOD_HEADER = re.compile(r"\bvoid\s+\w+\s*\([^)]*\)\s*(?:throws[^{]*)?\{\s*$")


def _fix_lookup_dereferenced_unguarded(root: Path, options: dict) -> list[FileChange]:
    """Guard `getStarSystem(name).x()` / `getEntityById(id).x()` with `if (lookup == null) { return; }` when the
    statement is the first one in a void method (DNEEP's setIndustryOnPlanet, fixed by hand 2026-10-04): the early
    return skips only what would have thrown. Any other shape (inside a loop, after other statements, in a method that
    returns a value) is refused and left for a person. Loose scripts only."""
    from .scanner import _blank_java_comments

    lines_by_file: dict[str, set[int]] = {}
    for finding in _findings_of(root, options, "campaign-lookup-dereferenced-unguarded"):
        if finding.file and not finding.file.replace("\\", "/").startswith(("jars/", "src/")) and "!" not in finding.file:
            lines_by_file.setdefault(finding.file, set()).update(int(e.split(":", 1)[1]) for e in finding.evidence if e.startswith("line:"))
    changes, refused = [], []
    for rel, wanted in sorted(lines_by_file.items()):
        path = root / rel
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        eol = "\r\n" if "\r\n" in text else "\n"
        # splitlines counts line breaks as the scanner's universal-newline read does (a lone CR included)
        lines = text.splitlines(keepends=True)
        blank = _blank_java_comments(text).splitlines(keepends=True)
        inserts = []
        for number in sorted(wanted):
            index = number - 1
            call = re.search(r"\b(getStarSystem|getEntityById)\s*\(\s*([A-Za-z_]\w*)\s*\)", blank[index])
            previous = index - 1
            while previous >= 0 and not blank[previous].strip():
                previous -= 1
            if not call or previous < 0 or not _VOID_METHOD_HEADER.search(blank[previous]):
                refused.append(f"{rel}:{number}")
                continue
            receiver = re.search(r"([\w.()]*?)\b" + call.group(1) + r"\s*\(", lines[index])
            prefix = receiver.group(1) if receiver else ""
            indent = re.match(r"[ \t]*", lines[index]).group(0)
            inserts.append((index, [f"{indent}// BridgeForge: a missing system or entity (random sector, total conversion) is skipped.{eol}",
                                    f"{indent}if ({prefix}{call.group(1)}({call.group(2)}) == null) {{{eol}",
                                    f"{indent}    return;{eol}", f"{indent}}}{eol}"]))
        for index, block in sorted(inserts, reverse=True):
            lines[index:index] = block
        if inserts:
            changes.append(FileChange(path=path, before=raw, after=_encode("".join(lines), had_bom)))
    if not changes:
        raise FixerError("No unguarded lookup is the first statement of a void method" + (f" (refused: {', '.join(refused[:5])})" if refused else "."))
    return changes


# ---------------------------------------------------------------------------
# Fixer: temporary-market-fleet-source (ROADMAP 34.38, 2026-10-04)
# ---------------------------------------------------------------------------

_TEMP_MARKET = re.compile(r"\b([A-Za-z_]\w*)\s*=\s*Global\s*\.\s*getFactory\s*\(\s*\)\s*\.\s*createMarket\s*\(")
_REMOVE_MARKET_LINE = re.compile(r"^([ \t]*)Global\s*\.\s*getSector\s*\(\s*\)\s*\.\s*getEconomy\s*\(\s*\)\s*\.\s*removeMarket\s*\(\s*([A-Za-z_]\w*)\s*\)\s*;[ \t]*(\r?\n?)$")


def _temporary_market_sources(root: Path, options: dict) -> list[Path]:
    """Source files for the findings: a loose script as is; a jar class through the mod's bundled source
    (jars/src/ or src/, matched by package path), which patch-jar-class then compiles into the jar."""
    paths: list[Path] = []
    for finding in _findings_of(root, options, "temporary-market-fleet-source"):
        file = (finding.file or "").replace("\\", "/")
        if "!" in file:
            class_path = file.split("!", 1)[1].split("$", 1)[0].removesuffix(".class") + ".java"
            candidates = [root / base / class_path for base in ("jars/src", "src")]
            found = next((c for c in candidates if c.is_file()), None)
            if found is None:
                raise FixerError(f"{file}: no bundled source for this class (jars/src/ or src/); decompile it first")
            paths.append(found)
        elif file:
            paths.append(root / file)
    return sorted(set(paths))


def _fix_temporary_market_fleet_source(root: Path, options: dict) -> list[FileChange]:
    """Drop `Global.getSector().getEconomy().removeMarket(m);` where `m` came from `createMarket(...)` in the same
    file and is never `addMarket`-ed: the market never entered the economy, so vanilla only removes it from a list it is
    not in and marks the location cache stale (ReachEconomy.removeMarket, javap 2026-10-04; RC8-22), and
    the fleet still builds from the same market (same quality and size). AoTD Theory of Toolbox's economy turns each
    such call into a structural refresh (AoTDEconomy.removeMarket, 2026-10-04). A market that is also added, or a
    removeMarket not alone on its line, is refused."""
    from .scanner import _blank_java_comments

    changes, refused = [], []
    for path in _temporary_market_sources(root, options):
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        blank = _blank_java_comments(text)
        created = set(_TEMP_MARKET.findall(blank))
        lines = text.splitlines(keepends=True)
        blank_lines = blank.splitlines(keepends=True)
        changed = False
        for index, line in enumerate(blank_lines):
            match = _REMOVE_MARKET_LINE.match(line)
            if not match:
                continue
            name = match.group(2)
            if name not in created or re.search(r"\baddMarket\s*\(\s*" + re.escape(name) + r"\b", blank):
                refused.append(f"{_relative_path(root, path)}:{index + 1}")
                continue
            eol = match.group(3) or ""
            lines[index] = (f"{match.group(1)}// BridgeForge: removeMarket({name}) dropped; {name} never entered the economy, "
                            f"so vanilla only removed it from a list it was not in and marked a cache stale (RC8-22).{eol}")
            changed = True
        if changed:
            changes.append(FileChange(path=path, before=raw, after=_encode("".join(lines), had_bom)))
    if not changes:
        raise FixerError("No removeMarket of a never-added temporary market found" + (f" (refused: {', '.join(refused[:5])})" if refused else "."))
    return changes


def _relative_path(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


# ---------------------------------------------------------------------------
# Fixer: wing-op-cost-blank (ROADMAP 34.22; approval-gated: the value is a comparison, not a conversion)
# ---------------------------------------------------------------------------


def _raw_csv_spans(line: str) -> list[tuple[int, int]]:
    spans, start, quoted = [], 0, False
    for i, ch in enumerate(line):
        if ch == '"':
            quoted = not quoted
        elif ch == "," and not quoted:
            spans.append((start, i))
            start = i + 1
    spans.append((start, len(line.rstrip("\r\n"))))
    return spans


def _fix_wing_op_cost_blank(root: Path, options: dict) -> list[FileChange]:
    """Set a blank wing `op cost` to the nearest vanilla RC8 wing's (same role, nearest fleet pts, then fighter
    count), only for a wing a variant fits or a faction knows (autofit can fit it): built-in or unused wings are never
    charged and stay as they are. A pre-0.8 file without the column gets an `op cost` column appended, rows padded to
    the header first. Only the one cell changes. Done by hand for 36 wings in 7 mods on 2026-10-04 (owner ruling)."""
    import csv as _csv
    import io as _io

    from .scanner import _load_lenient_json_file

    core = options.get("vanilla_core")
    if not core:
        raise FixerError("wing-op-cost-blank needs --vanilla-core: the cost is read from the nearest vanilla wing.")
    vanilla = [r for r in _csv.DictReader(_io.StringIO((Path(core) / "data/hulls/wing_data.csv").read_text(encoding="utf-8-sig")))
               if r.get("id") and (r.get("op cost") or "").strip()]
    if not vanilla:
        raise FixerError("the vanilla core's wing_data.csv has no op costs to compare with.")

    def number(value) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    flagged = {e.split(":", 1)[1] for f in _findings_of(root, options, "wing-op-cost-blank") for e in f.evidence if e.startswith("wing:")}
    used: set[str] = set()
    for spec_path in (root / "data" / "variants").rglob("*.variant") if (root / "data" / "variants").is_dir() else []:
        spec = _load_lenient_json_file(spec_path)
        if isinstance(spec, dict):
            used |= {w for w in spec.get("wings") or [] if isinstance(w, str)}
    factions = " ".join(p.read_text(encoding="utf-8", errors="replace") for p in (root / "data/world/factions").glob("*.faction")) \
        if (root / "data/world/factions").is_dir() else ""
    targets = {w for w in flagged if w in used or f'"{w}"' in factions}
    if not targets:
        raise FixerError("No blank-cost wing is fitted by a variant or known to a faction: nothing is ever charged, accept as authored.")
    path = root / "data/hulls/wing_data.csv"
    raw = path.read_bytes()
    text, had_bom = _decode(raw)
    lines = text.splitlines(keepends=True)
    header = next(_csv.reader(_io.StringIO(lines[0])))
    if "op cost" not in header:
        width, eol = len(header), ("\r\n" if lines[0].endswith("\r\n") else "\n")
        lines[0] = lines[0].rstrip("\r\n") + ",op cost" + eol
        for n, line in enumerate(lines[1:], 1):
            if line.strip():
                body = line.rstrip("\r\n") + "," * max(0, width - len(_raw_csv_spans(line)))
                lines[n] = body + "," + (line[len(line.rstrip("\r\n")):] or eol)
        header = header + ["op cost"]
    column = header.index("op cost")
    changed = 0
    for n, line in enumerate(lines[1:], 1):
        row = next(_csv.reader(_io.StringIO(line)), [])
        if not row or row[0] not in targets or len(row) <= column or row[column].strip():
            continue
        fields = dict(zip(header, row))
        same = [v for v in vanilla if v["role"] == (fields.get("role") or "").strip()] or vanilla
        best = min(same, key=lambda v: (abs(number(v["fleet pts"]) - number(fields.get("fleet pts"))), abs(number(v["num"]) - number(fields.get("num")))))
        start, end = _raw_csv_spans(line)[column]
        lines[n] = line[:start] + best["op cost"].strip() + line[end:]
        changed += 1
    if not changed:
        raise FixerError("The flagged wings' rows could not be edited mechanically.")
    return [FileChange(path=path, before=raw, after=_encode("".join(lines), had_bom))]


# ---------------------------------------------------------------------------
# Fixer: builtin-wing-is-hullmod (2026-10-04)
# ---------------------------------------------------------------------------


def _fix_builtin_wing_is_hullmod(root: Path, options: dict) -> list[FileChange]:
    """Rename `builtInWings` to `builtInMods` when every entry under it is a hull mod and the spec has no
    `builtInMods` yet (The Nomads' nom_komodo_p.ship, fixed by hand 2026-10-04). Mixed lists, or a spec that already
    has builtInMods, are refused: moving single entries between arrays is left to a person."""
    from .scanner import _load_lenient_json_file

    files = sorted({f.file for f in _findings_of(root, options, "builtin-wing-is-hullmod") if f.file})
    flagged: dict[str, set[str]] = {}
    for finding in _findings_of(root, options, "builtin-wing-is-hullmod"):
        flagged.setdefault(finding.file, set()).update(e.split(":", 1)[1] for e in finding.evidence if e.startswith("hullmod:"))
    changes, refused = [], []
    for rel in files:
        path = root / rel
        spec = _load_lenient_json_file(path) or {}
        wings = [w for w in spec.get("builtInWings") or [] if isinstance(w, str)]
        if "builtInMods" in spec or set(wings) - flagged.get(rel, set()):
            refused.append(rel)
            continue
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        new_text, count = re.subn(r'(["\'])builtInWings\1(\s*:)', r'\1builtInMods\1\2', text, count=1)
        if count:
            changes.append(FileChange(path=path, before=raw, after=_encode(new_text, had_bom)))
    if not changes:
        raise FixerError("No builtInWings list can be renamed mechanically" + (f" (refused: {', '.join(refused[:5])})" if refused else "."))
    return changes


# ---------------------------------------------------------------------------
# Fixer: json-missing-comma (ROADMAP 34.16)
# ---------------------------------------------------------------------------


def _fix_json_missing_comma(root: Path, options: dict) -> list[FileChange]:
    """Apply scanner._repair_missing_commas, which only succeeds when the file then parses as RC8 reads it."""
    from .scanner import _repair_missing_commas

    changes: list[FileChange] = []
    for rel in sorted({f.file for f in _findings_of(root, options, "json-missing-comma") if f.file}):
        path = root / rel
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        repaired = _repair_missing_commas(text)
        if repaired:
            changes.append(FileChange(path=path, before=raw, after=_encode(repaired[0], had_bom)))
    if not changes:
        raise FixerError("No flagged JSON file parses after adding the missing commas.")
    return changes


# ---------------------------------------------------------------------------
# Fixer: spawned-ship-captain-personality-risk (loose scripts only; ROADMAP 34.14)
# ---------------------------------------------------------------------------

_SPAWN_THREE_ARGS = re.compile(r"\bspawnShipOrWing\s*\(")
_BF_SPAWN_CAPTAIN = (
    "\n    // BridgeForge: a ship spawned without a captain has no personality, and RC8's Ship.getPersonality() NPEs\n"
    "    // on it. RC8's ChiralFigmentStats spawns ships with createPerson() + setPersonality (ROADMAP 34.14).\n"
    "    private static com.fs.starfarer.api.characters.PersonAPI bfSpawnCaptain() {\n"
    "        com.fs.starfarer.api.characters.PersonAPI captain = com.fs.starfarer.api.Global.getSettings().createPerson();\n"
    "        captain.setPersonality(com.fs.starfarer.api.impl.campaign.ids.Personalities.STEADY);\n"
    "        return captain;\n"
    "    }\n"
)


def _fix_spawned_ship_captain(root: Path, options: dict) -> list[FileChange]:
    """spawnShipOrWing("ship", loc, facing) -> spawnShipOrWing("ship", loc, facing, 0f, bfSpawnCaptain()), the
    overload with a captain (done by hand for Traverser's turrets, 2026-10-04). The 3-argument form has no
    travel-drive burn, so 0f keeps it. A 4-argument call keeps its own burn. Only the flagged lines change;
    wings are never flagged. Jar sources need patch-jar-class and are refused."""
    from .scanner import _blank_java_comments, _call_argument_count

    lines_by_file: dict[str, set[int]] = {}
    for finding in _findings_of(root, options, "spawned-ship-captain-personality-risk"):
        if finding.file and "!" not in finding.file and not finding.file.replace("\\", "/").startswith(("jars/", "src/")):
            if any(e == "call:spawnShipOrWing" for e in finding.evidence):
                lines_by_file.setdefault(finding.file, set()).update(
                    int(e.split(":", 1)[1]) for e in finding.evidence if e.startswith("line:"))
    changes: list[FileChange] = []
    for rel, lines in sorted(lines_by_file.items()):
        path = root / rel
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        blank = _blank_java_comments(text, strings=True)
        edits = []
        for match in _SPAWN_THREE_ARGS.finditer(blank):
            if text.count("\n", 0, match.start()) + 1 not in lines:
                continue
            count = _call_argument_count(blank, match.start())
            if count not in (3, 4):
                continue
            depth, close = 0, None
            for i in range(match.end() - 1, len(blank)):
                depth += {"(": 1, ")": -1}.get(blank[i], 0)
                if depth == 0:
                    close = i
                    break
            if close is not None:
                edits.append((close, (", 0f" if count == 3 else "") + ", bfSpawnCaptain()"))
        if not edits:
            continue
        out = text
        for at, insert in sorted(edits, reverse=True):
            out = out[:at] + insert + out[at:]
        if "bfSpawnCaptain() {" not in out:
            last = _blank_java_comments(out, strings=True).rstrip().rfind("}")
            out = out[:last] + _BF_SPAWN_CAPTAIN + out[last:]
        changes.append(FileChange(path=path, before=raw, after=_encode(out, had_bom)))
    if not changes:
        raise FixerError("No flagged loose-script spawnShipOrWing call could be given a captain mechanically.")
    return changes


# ---------------------------------------------------------------------------
# Fixer: hullmod-instance-state (loose scripts only; ROADMAP 34.1)
# ---------------------------------------------------------------------------


def _fix_hullmod_instance_state(root: Path, options: dict) -> list[FileChange]:
    """Move a hull mod's flagged instance fields into a per-ship State in ship.getCustomData()
    (`hullmod_state.port_hullmod_state`, the rewrite done by hand for SEEKER and Sylphon on 2026-10-04). Jar
    classes and jar sources need patch-jar-class, so they are refused; so is any shape the port refuses."""
    from .hullmod_state import HullModStateError, port_hullmod_state

    fields_by_file: dict[str, list[str]] = {}
    for finding in _findings_of(root, options, "hullmod-instance-state"):
        if finding.file:
            fields_by_file.setdefault(finding.file, []).extend(
                e.split(":", 1)[1] for e in finding.evidence if e.startswith("field:"))
    loose = {rel: names for rel, names in fields_by_file.items()
             if "!" not in rel and rel.endswith(".java") and not rel.replace("\\", "/").startswith(("jars/", "src/"))}
    if not loose:
        raise FixerError("No loose hull mod script keeps per-ship instance fields (jar classes need patch-jar-class).")
    changes: list[FileChange] = []
    refused: list[str] = []
    for rel, names in sorted(loose.items()):
        path = root / rel
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        try:
            new_text = port_hullmod_state(text, sorted(set(names)), path.stem)
        except HullModStateError as exc:
            refused.append(f"{rel}: {exc}")
            continue
        changes.append(FileChange(path=path, before=raw, after=_encode(new_text, had_bom)))
    if not changes:
        raise FixerError("Not mechanical: " + "; ".join(refused[:5]))
    return changes


# ---------------------------------------------------------------------------
# Shared: surgically rename/merge keys inside one JSON sub-object's interior text (a `.faction`'s
# `traits.<role>` or `shipRoles.<role>` block - both are flat `"id": <number>` maps).
# ---------------------------------------------------------------------------

_TRAITS_KEY_PATTERN = re.compile(r"['\"]traits['\"]\s*:")
_SHIP_ROLES_KEY_PATTERN = re.compile(r"['\"]shipRoles['\"]\s*:")
_ID_WEIGHT_KEY_VALUE_PATTERN = re.compile(r"(?P<quote>['\"])(?P<key>[A-Za-z_][A-Za-z0-9_]*)(?P=quote)\s*:\s*(?P<value>-?\d+(?:\.\d+)?)\s*(?P<comma>,?)")


def _matching_close_brace(text: str, depths: list[int], open_index: int) -> int:
    """Index of the `}` that closes the `{` at `open_index` (see `build_tag._structural_depths`)."""
    target_depth = depths[open_index] + 1
    for i in range(open_index + 1, len(text)):
        if text[i] == "}" and depths[i] == target_depth:
            return i
    raise ValueError(f"no matching close brace for the '{{' at offset {open_index}")


def _format_weight_sum(values: list[str]) -> str:
    if all(re.fullmatch(r"-?\d+", value) for value in values):
        return str(sum(int(value) for value in values))
    return f"{sum(float(value) for value in values):g}"


def _rewrite_id_weight_object(block_text: str, rename: dict[str, str]) -> str:
    """One `"id": <number>` sub-object's interior text: keys in `rename` renamed/merged to their
    `rename[key]` target.

    Multiple old keys can map to the same target (e.g. `suicidal`/`fearless` both -> `reckless`);
    their weights are summed rather than left as a silently-colliding duplicate JSON key. Refuses
    (rather than guess a merge order) if the target key already has its own explicit entry in the
    block that `rename` doesn't itself account for.
    """
    by_key: dict[str, re.Match] = {}
    for match in _ID_WEIGHT_KEY_VALUE_PATTERN.finditer(block_text):
        by_key.setdefault(match.group("key"), match)
    renaming = {key: match for key, match in by_key.items() if key in rename}
    if not renaming:
        return block_text
    targets: dict[str, list[re.Match]] = {}
    for key, match in renaming.items():
        targets.setdefault(rename[key], []).append(match)
    for target in targets:
        if target in by_key and target not in rename:
            raise FixerError(f"block already has an explicit '{target}' entry alongside a key that renames to it; merge by hand.")

    first_start_target = {min(matches, key=lambda m: m.start()).start(): target for target, matches in targets.items()}
    removals = sorted((match for matches in targets.values() for match in matches), key=lambda m: m.start())

    pieces = []
    cursor = 0
    for match in removals:
        pieces.append(block_text[cursor:match.start()])
        if match.start() in first_start_target:
            target = first_start_target[match.start()]
            weight = _format_weight_sum([m.group("value") for m in targets[target]])
            quote = match.group("quote")
            pieces.append(f"{quote}{target}{quote}:{weight}{match.group('comma')}")
        cursor = match.end()
    pieces.append(block_text[cursor:])
    return "".join(pieces)


# ---------------------------------------------------------------------------
# Fixer: faction-trait-weight-legacy-personality-id
# ---------------------------------------------------------------------------


def _fix_faction_trait_weight_legacy_personality_id(root: Path, options: dict) -> list[FileChange]:
    """Rename/merge 0.6-era personality ids (`LEGACY_PERSONALITY_IDS`) in every `.faction`'s
    `traits.<role>` weight block, surgically - only the flagged key/value text is touched, the rest
    of the file (comments, trailing commas, key order) survives untouched.
    """
    faction_dir = root / "data" / "world" / "factions"
    if not faction_dir.is_dir():
        raise FixerError(f"No {faction_dir} directory.")
    changes: list[FileChange] = []
    for path in sorted(faction_dir.glob("*.faction")):
        data = _load_lenient_json_file(path)
        if not isinstance(data, dict):
            continue
        traits = data.get("traits")
        if not isinstance(traits, dict):
            continue
        legacy_roles = sorted(
            role for role, block in traits.items()
            if isinstance(block, dict) and any(key in LEGACY_PERSONALITY_IDS for key in block)
        )
        if not legacy_roles:
            continue
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        depths = _structural_depths(text)
        traits_match = _TRAITS_KEY_PATTERN.search(text)
        if traits_match is None:
            raise FixerError(f"{path}: could not locate a 'traits' key to anchor the edit.")
        traits_open = text.index("{", traits_match.end())
        traits_close = _matching_close_brace(text, depths, traits_open)

        spans: list[tuple[int, int, str]] = []
        for role in legacy_roles:
            role_match = re.search(rf"['\"]{re.escape(role)}['\"]\s*:\s*\{{", text[traits_open:traits_close])
            if role_match is None:
                raise FixerError(f"{path}: could not locate role '{role}' text inside 'traits'.")
            role_open = traits_open + role_match.end() - 1
            role_close = _matching_close_brace(text, depths, role_open)
            spans.append((role_open + 1, role_close, _rewrite_id_weight_object(text[role_open + 1:role_close], LEGACY_PERSONALITY_IDS)))

        pieces = []
        cursor = 0
        for start, end, new_block in sorted(spans):
            pieces.append(text[cursor:start])
            pieces.append(new_block)
            cursor = end
        pieces.append(text[cursor:])
        new_text = "".join(pieces)

        try:
            parsed, _tolerances = _parse_json(new_text)
        except json.JSONDecodeError as exc:
            raise FixerError(f"Edited {path} failed to re-parse: {exc}") from exc
        new_traits = parsed.get("traits") if isinstance(parsed, dict) else None
        if not isinstance(new_traits, dict) or any(
            isinstance(new_traits.get(role), dict) and any(key in LEGACY_PERSONALITY_IDS for key in new_traits[role])
            for role in legacy_roles
        ):
            raise FixerError(f"Edited {path} still has a legacy personality id in its traits block.")
        changes.append(FileChange(path=path, before=raw, after=_encode(new_text, had_bom)))
    if not changes:
        raise FixerError("No .faction file has a legacy personality id in its traits block.")
    return changes


# ---------------------------------------------------------------------------
# Fixer: shiproles-wing-id
# ---------------------------------------------------------------------------


def _fix_shiproles_wing_id(root: Path, options: dict) -> list[FileChange]:
    """Rename a `shipRoles.<role>` fighter-wing id to the variant id 0.98a actually resolves,
    surgically - only the flagged key/value text is touched.

    0.98a's `shipRoles` only resolves variant ids (the pre-0.8a convention read a wing id instead,
    which is fatal at load rather than ignored). The correct replacement is that wing's own
    `variant` column in `data/hulls/wing_data.csv` - the same file/column the scanner's own
    `shiproles-wing-id` check reads to decide a key "looks like a fighter wing id" in the first
    place, so the fixer and the check agree on what counts as a wing id.
    """
    faction_dir = root / "data" / "world" / "factions"
    if not faction_dir.is_dir():
        raise FixerError(f"No {faction_dir} directory.")
    wing_variants = _wing_id_variant_map(root / "data" / "hulls" / "wing_data.csv")
    vanilla_core = options.get("vanilla_core")
    if vanilla_core:
        wing_variants = {**_wing_id_variant_map(Path(vanilla_core) / "data" / "hulls" / "wing_data.csv"), **wing_variants}
    wing_ids = _wing_ids_set(root / "data" / "hulls" / "wing_data.csv")
    if vanilla_core:
        wing_ids |= _wing_ids_set(Path(vanilla_core) / "data" / "hulls" / "wing_data.csv")

    changes: list[FileChange] = []
    for path in sorted(faction_dir.glob("*.faction")):
        data = _load_lenient_json_file(path)
        if not isinstance(data, dict):
            continue
        ship_roles = data.get("shipRoles")
        if not isinstance(ship_roles, dict):
            continue

        def is_wing_key(key: str) -> bool:
            return key not in FACTION_SPECIAL_ROLE_KEYS and (key.endswith("_wing") or key in wing_ids)

        affected_roles = sorted(
            role for role, block in ship_roles.items()
            if isinstance(block, dict) and any(is_wing_key(key) for key in block)
        )
        if not affected_roles:
            continue
        unresolved = sorted({
            key for role in affected_roles for key in ship_roles[role]
            if is_wing_key(key) and key not in wing_variants
        })
        if unresolved:
            raise FixerError(f"{path}: no 'variant' column for wing id(s) {', '.join(unresolved)} in wing_data.csv; fix by hand.")

        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        depths = _structural_depths(text)
        ship_roles_match = _SHIP_ROLES_KEY_PATTERN.search(text)
        if ship_roles_match is None:
            raise FixerError(f"{path}: could not locate a 'shipRoles' key to anchor the edit.")
        ship_roles_open = text.index("{", ship_roles_match.end())
        ship_roles_close = _matching_close_brace(text, depths, ship_roles_open)

        spans: list[tuple[int, int, str]] = []
        for role in affected_roles:
            role_match = re.search(rf"['\"]{re.escape(role)}['\"]\s*:\s*\{{", text[ship_roles_open:ship_roles_close])
            if role_match is None:
                raise FixerError(f"{path}: could not locate role '{role}' text inside 'shipRoles'.")
            role_open = ship_roles_open + role_match.end() - 1
            role_close = _matching_close_brace(text, depths, role_open)
            rename = {key: wing_variants[key] for key in ship_roles[role] if is_wing_key(key)}
            spans.append((role_open + 1, role_close, _rewrite_id_weight_object(text[role_open + 1:role_close], rename)))

        pieces = []
        cursor = 0
        for start, end, new_block in sorted(spans):
            pieces.append(text[cursor:start])
            pieces.append(new_block)
            cursor = end
        pieces.append(text[cursor:])
        new_text = "".join(pieces)

        try:
            parsed, _tolerances = _parse_json(new_text)
        except json.JSONDecodeError as exc:
            raise FixerError(f"Edited {path} failed to re-parse: {exc}") from exc
        new_ship_roles = parsed.get("shipRoles") if isinstance(parsed, dict) else None
        if not isinstance(new_ship_roles, dict) or any(
            isinstance(new_ship_roles.get(role), dict) and any(is_wing_key(key) for key in new_ship_roles[role])
            for role in affected_roles
        ):
            raise FixerError(f"Edited {path} still has a wing id in its shipRoles block.")
        changes.append(FileChange(path=path, before=raw, after=_encode(new_text, had_bom)))
    if not changes:
        raise FixerError("No .faction file has a fighter-wing id in its shipRoles block.")
    return changes


# ---------------------------------------------------------------------------
# Dispatch, diffing, backup/apply
# ---------------------------------------------------------------------------

def _fix_shippable_work_file(root: Path, options: dict) -> list[FileChange]:
    """Move editor/work files out of the shipped tree (P15 item 14, 2026-09-27).

    Each file `shippable-work-file` lists moves to `<workspace>/scratch/work-files/<same path>` when
    `root` is a workspace's `working/` (else `<root>.work-files/` beside it), so nothing is lost and
    the release no longer carries it. A file whose name appears in the mod's own data, loose scripts,
    `mod_info.json` or jar entries is left in place: the scanner's own caveat is that a mod could,
    rarely, read one on purpose.
    """
    from .copy_drift import _collect
    from .scanner import _WORK_FILE_GLOBS

    found = sorted(relative for relative in _collect(root)
                   if any(fnmatch.fnmatch(relative.rsplit("/", 1)[-1].lower(), pattern) for pattern in _WORK_FILE_GLOBS))
    if not found:
        return []
    corpus = _referencing_bytes(root, set(found))
    destination = root.parent / "scratch" / "work-files" if root.name == "working" else root.parent / f"{root.name}.work-files"
    changes = []
    for relative in found:
        name = relative.rsplit("/", 1)[-1]
        if name.lower().encode("utf-8") in corpus:
            continue  # referenced by the mod itself: a person decides
        source = root / relative
        target = destination / relative
        if target.exists():
            raise FixerError(f"{target} already exists; move or remove it before rerunning this fixer.")
        data = source.read_bytes()
        changes.append(FileChange(path=target, before=b"", after=data, existed_before=False))
        changes.append(FileChange(path=source, before=data, after=b"", removed=True))
    return changes


_REFERENCE_SUFFIXES = {".json", ".csv", ".java", ".kt", ".faction", ".ship", ".skin", ".variant", ".wpn", ".proj",
                       ".system", ".wing", ".ini", ".txt", ".xml", ".properties"}


def _referencing_bytes(root: Path, skip: set[str]) -> bytes:
    """Lower-cased text of every file that could name another file at runtime, jar members included."""
    import zipfile

    parts = []
    from .copy_drift import _is_excluded

    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        # IDE/VCS folders (.idea, .git, src*...) never ship and the game never reads them; a mention there
        # is not a runtime reference (Jackundor's .idea/libraries/data.xml named its backup zips, 2026-09-27).
        if not path.is_file() or relative in skip or _is_excluded(relative):
            continue
        suffix = path.suffix.lower()
        # A root readme or changelog is for people, never read by the game (Hiver Swarm's README named its
        # "Replacement Ships.rar", which kept the archive shipping; ROADMAP 34.18, 2026-10-04).
        if "/" not in relative and suffix in {".txt", ".md"}:
            continue
        try:
            if suffix in _REFERENCE_SUFFIXES and path.stat().st_size <= 8 * 1024 * 1024:
                parts.append(path.read_bytes().lower())
            elif suffix == ".jar":
                with zipfile.ZipFile(path) as jar:
                    parts.extend(jar.read(info).lower() for info in jar.infolist() if not info.is_dir() and info.file_size <= 8 * 1024 * 1024)
        except (OSError, zipfile.BadZipFile):
            continue
    return b"\n".join(parts)


# CP-1252's typographic bytes: curly quotes, en/em dash, ellipsis, no-break space. Mac Roman reads the
# same bytes as accented letters (0x92 = í, 0x93 = ì) and Shift-JIS/GBK need two high bytes, so an
# isolated one of these between ASCII bytes has one plausible reading. Surveyed 2026-09-27 over the
# queue's 44 non-UTF-8 data files: 30 meet this; the rest carry Mac Roman (DME's 0xD5 for ’), Shift-JIS
# (Stinger-Shipyards' 0x81 0x66) or accented letters, whose encoding a person must name.
_CP1252_TYPOGRAPHY = frozenset({0x85, 0x91, 0x92, 0x93, 0x94, 0x96, 0x97, 0xA0})


def _invalid_utf8_offsets(raw: bytes) -> list[int]:
    offsets, start = [], 0
    while start < len(raw):
        try:
            raw[start:].decode("utf-8")
            break
        except UnicodeDecodeError as exc:
            offsets.append(start + exc.start)
            start += exc.start + 1
    return offsets


def _fix_data_file_not_utf8(root: Path, options: dict) -> list[FileChange]:
    """Re-encode data files whose only non-UTF-8 bytes are isolated CP-1252 punctuation (P15 item 15).

    Valid UTF-8 already in the file is kept byte for byte; each invalid byte becomes its CP-1252
    character in UTF-8. A file with any other invalid byte is refused with the bytes it holds, because
    its real encoding (Mac Roman, Shift-JIS, GBK, CP-1252 letters) cannot be told from the bytes alone.
    """
    from .scanner import _PLAYER_TEXT_SUFFIXES

    data = root / "data"
    paths = [root / "mod_info.json"] + ([p for p in data.rglob("*") if p.suffix.lower() in _PLAYER_TEXT_SUFFIXES] if data.is_dir() else [])
    changes, refused = [], []
    named_encodings = dict(options.get("encodings") or {})
    for relative, encoding in named_encodings.items():
        if encoding not in _NAMEABLE_ENCODINGS:
            raise FixerError(f"{relative}: encoding {encoding!r} is not one of {', '.join(sorted(_NAMEABLE_ENCODINGS))}.")
    for path in sorted(p for p in paths if p.is_file()):
        raw = path.read_bytes()
        offsets = _invalid_utf8_offsets(raw)
        if not offsets:
            continue
        invalid = set(offsets)

        def plain(index: int) -> bool:
            return index < 0 or index >= len(raw) or raw[index] < 0x80 or index in invalid

        relative = path.relative_to(root).as_posix()
        named = named_encodings.pop(relative, None)
        if named is not None:
            changes.append(FileChange(path=path, before=raw, after=_reencode_invalid(raw, offsets, named, relative)))
            continue
        if not all(raw[i] in _CP1252_TYPOGRAPHY and plain(i - 1) and plain(i + 1) for i in offsets):
            odd = sorted({f"0x{raw[i]:02x}" for i in offsets if raw[i] not in _CP1252_TYPOGRAPHY})
            refused.append(f"{path.relative_to(root).as_posix()} ({', '.join(odd) or 'adjacent high bytes'})")
            continue
        out, last = bytearray(), 0
        for i in offsets:
            out += raw[last:i] + bytes([raw[i]]).decode("cp1252").encode("utf-8")
            last = i + 1
        out += raw[last:]
        changes.append(FileChange(path=path, before=raw, after=bytes(out)))
    if named_encodings:
        raise FixerError(f"No invalid UTF-8 to re-encode in: {', '.join(sorted(named_encodings))}.")
    if not changes and refused:
        raise FixerError("No file has only CP-1252 punctuation outside UTF-8; name the real encoding by hand for: " + "; ".join(refused)
                         + " (fix --encoding FILE=ENCODING)")
    if refused:
        # Some files converted, others not: the caller (revive) reports these as still pending (ROADMAP P15 20.5).
        options.setdefault("partial_refusals", []).append("Not converted; name the real encoding by hand for: " + "; ".join(refused)
                                                          + " (fix --encoding FILE=ENCODING)")
    return changes


NAMED_ENCODINGS_FILE = "NAMED_ENCODINGS.json"


def _named_encodings_path(mod_dir: Path) -> Path | None:
    """<workspace>/NAMED_ENCODINGS.json when mod_dir is a workspace's working/ (ROADMAP P15 item 20.4)."""
    mod_dir = Path(mod_dir).resolve()
    return mod_dir.parent / NAMED_ENCODINGS_FILE if mod_dir.name == "working" else None


def record_named_encodings(mod_dir: Path, encodings: dict[str, str]) -> Path | None:
    """Keep a person's `fix --encoding FILE=ENC` decisions in the workspace, so a fresh copy from original/ (and revive) can reapply them."""
    path = _named_encodings_path(mod_dir)
    if path is None or not encodings:
        return None
    known = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    known.update({name.replace("\\", "/"): encoding for name, encoding in encodings.items()})
    path.write_text(json.dumps(dict(sorted(known.items())), indent=2) + "\n", encoding="utf-8")
    return path


def pending_named_encodings(mod_dir: Path) -> dict[str, str]:
    """Recorded encodings whose file is still not valid UTF-8 (already converted files are left out)."""
    path = _named_encodings_path(mod_dir)
    if path is None or not path.is_file():
        return {}
    pending = {}
    for name, encoding in json.loads(path.read_text(encoding="utf-8")).items():
        target = Path(mod_dir) / name
        try:
            target.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            pending[name] = encoding
        except OSError:
            continue
    return pending


# Encodings a person may name for data-file-not-utf8 (`fix --encoding FILE=ENC`), each seen in the queue
# 2026-09-27: CP-1252 letters (Thule-Legacy, Epta-Consortium), Mac Roman (DME), Shift-JIS (Stinger-Shipyards).
_NAMEABLE_ENCODINGS = frozenset({"cp1252", "mac_roman", "shift_jis", "gbk", "gb18030", "latin-1"})


def _reencode_invalid(raw: bytes, offsets: list[int], encoding: str, relative: str) -> bytes:
    """Decode only the invalid bytes (a lead byte takes its trail byte with it in a two-byte encoding)
    with the encoding a person named; bytes that are already valid UTF-8 stay as they are."""
    out, last = bytearray(), 0
    for i in offsets:
        if i < last:
            continue  # consumed as a trail byte
        for width in (1, 2):
            try:
                text = raw[i:i + width].decode(encoding)
            except UnicodeDecodeError:
                continue
            if len(text) == 1:
                break
        else:
            raise FixerError(f"{relative}: byte 0x{raw[i]:02x} at offset {i} does not decode as {encoding}.")
        out += raw[last:i] + text.encode("utf-8")
        last = i + width
    return bytes(out + raw[last:])


def _fleet_type_display_name(fleet_type: str) -> str:
    """"Zeta AI raid" -> "Zeta AI Raid"; camelCase ids split into words: "pathFleet" -> "Path Fleet"."""
    words = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", fleet_type).split(" ")
    return " ".join(w[:1].upper() + w[1:] for w in words if w)


def _fix_fleet_type_name_missing(root: Path, options: dict) -> list[FileChange]:
    """Add a `fleetTypeNames` entry per unnamed fleet type (P15 item 20.15), title-casing the type as Zorg18's
    hand fix did ("Zeta AI raid" -> "Zeta AI Raid"). Text insertion, so comments and formatting survive;
    `options["names"]` ({type: name}) overrides the proposed name. The check needs the vanilla core, so a
    fresh scan here passes `options["vanilla_core"]`."""
    if options.get("scan_findings") is None:
        from .scanner import scan_mod

        vanilla = options.get("vanilla_core")
        findings = [f for f in scan_mod(root, vanilla_core=Path(vanilla) if vanilla else None).findings if f.id == "fleet-type-name-missing"]
    else:
        findings = _findings_of(root, options, "fleet-type-name-missing")
    by_file: dict[str, list[str]] = {}
    for finding in findings:
        fleet_type = next((e.split(":", 1)[1] for e in finding.evidence if e.startswith("type:")), None)
        if fleet_type and finding.file:
            by_file.setdefault(finding.file, []).append(fleet_type)
    names = options.get("names") or {}
    # A vanilla faction's type (The Mayorate's "pathFleet" for luddic_path): the mod has no faction file to edit,
    # so the name goes in its own data/world/factions/default_fleet_type_names.json, which RC8 merges with
    # vanilla's. Evidence: Broken Star and Nexerelin ship that file with only their own entries (2026-09-27), and
    # vanilla fleets keep their names with them enabled.
    defaults_relative = "data/world/factions/default_fleet_type_names.json"
    for relative in [r for r in by_file if not (root / r).is_file() and r != defaults_relative]:
        by_file.setdefault(defaults_relative, []).extend(by_file.pop(relative))
    changes = []
    for relative, types in sorted(by_file.items()):
        path = root / relative
        if relative == defaults_relative:
            raw = path.read_bytes() if path.is_file() else b""
            text, had_bom = _decode(raw) if raw else ("{\n}\n", False)
            newline = "\r\n" if "\r\n" in text else "\n"
            entries = "".join(newline + "\t" + json.dumps(t) + ":" + json.dumps(names.get(t) or _fleet_type_display_name(t)) + ","
                              for t in sorted(set(types)))
            brace = text.index("{")
            text = text[:brace + 1] + entries + text[brace + 1:]
            changes.append(FileChange(path=path, before=raw, after=_encode(text, had_bom), existed_before=path.is_file()))
            continue
        if not path.is_file():
            continue
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        newline = "\r\n" if "\r\n" in text else "\n"
        entries = "".join(
            newline + "\t\t" + json.dumps(t) + ":" + json.dumps(names.get(t) or _fleet_type_display_name(t)) + ","
            for t in sorted(set(types)))
        match = re.search(r'"fleetTypeNames"\s*:\s*\{', text)
        if match:
            text = text[:match.end()] + entries + text[match.end():]
        else:
            brace = text.index("{")
            text = text[:brace + 1] + newline + '\t"fleetTypeNames":{' + entries + newline + "\t}," + text[brace + 1:]
        changes.append(FileChange(path=path, before=raw, after=_encode(text, had_bom)))
    return changes


# ---------------------------------------------------------------------------
# Bracket-span helpers for the variant-fit fixers below. `.variant` files are lenient JSON (# / //
# comments, trailing commas), so edits stay surgical text-span rewrites, never a json.dumps
# round-trip that would reformat the file (as `_fix_variant_op_over_budget` above already does for
# flux numbers and hullMods entries). These three locate/remove spans inside "wings" and
# "weaponGroups" the same way, using `_structural_depths` (build_tag.py) so a `{`/`[`/`}`/`]`
# inside a string or a comment never miscounts.
# ---------------------------------------------------------------------------

_STRING_PAIR_RE = re.compile(r"(?:" + _STRING_LITERAL + r")\s*:\s*(?:" + _STRING_LITERAL + r")")


def _matching_bracket(text: str, depths: list[int], open_pos: int) -> int | None:
    """Position of the `]`/`}` that closes the `[`/`{` at `open_pos`."""
    target = depths[open_pos] + 1
    close_char = "]" if text[open_pos] == "[" else "}"
    for i in range(open_pos + 1, len(text)):
        if text[i] == close_char and depths[i] == target:
            return i
    return None


def _enclosing_bracket(text: str, depths: list[int], pos: int, open_char: str) -> int | None:
    """Position of the `open_char` one depth level up that directly encloses `pos` (also works when
    `pos` is itself another bracket's open position, since an open bracket char is recorded at the
    depth of its own context, same as any other content character there)."""
    target = depths[pos] - 1
    for i in range(pos - 1, -1, -1):
        if text[i] == open_char and depths[i] == target:
            return i
    return None


def _remove_span_with_comma(text: str, start: int, end: int) -> str:
    """Remove text[start:end] plus the one adjacent list/object comma: the one after it (with any
    whitespace) if there is more after, else the one before it (it was last). Mirrors
    `_fix_variant_op_over_budget`'s hullMods removal so a trimmed array/object still closes exactly
    like lenient JSON expects, without reformatting anything else."""
    after = text[end:]
    after_match = re.match(r"\s*,\s*", after)
    if after_match:
        return text[:start] + text[end + after_match.end():]
    before = text[:start]
    before_match = re.search(r",\s*\Z", before)
    if before_match:
        return text[:before_match.start()] + text[end:]
    return text[:start] + text[end:]


def _fix_variant_wings_exceed_bays(root: Path, options: dict) -> list[FileChange]:
    """Drop wings from the END of the variant's own "wings" list until the total (plus the hull's
    built-in wings, which live on the .ship and can never be removed here) fits its fighter bays
    (owner ruling 2026-09-29: drop only what RC8's changed hulls can no longer fit; keep everything
    else exactly as the mod author wrote it). The kept wings stay in the author's order; nothing else
    in the file changes. A variant whose built-in wings alone already exceed the bays has nothing in
    its own wings list left to trim, and is refused."""
    string_re = re.compile(_STRING_LITERAL)
    changes: list[FileChange] = []
    refused: list[str] = []
    for finding in _findings_of(root, options, "variant-wings-exceed-bays"):
        if not finding.file:
            continue
        values = {e.split(":", 1)[0]: e.split(":", 1)[1] for e in finding.evidence if ":" in e}
        try:
            wings_count = int(values.get("wings", ""))
            built_in = int(values.get("built-in-wings", ""))
            bays = int(values.get("fighter-bays", ""))
        except ValueError:
            refused.append(f"{finding.file}: wings/built-in-wings/fighter-bays evidence is not numeric")
            continue
        excess = wings_count + built_in - bays
        if excess <= 0:
            continue
        path = root / finding.file
        if not path.is_file():
            refused.append(f"{finding.file}: file not found")
            continue
        if excess > wings_count:
            refused.append(
                f"{finding.file}: built-in wings alone ({built_in}) already exceed {bays} bay(s); "
                "nothing in the variant's own wings list can fix this"
            )
            continue
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        match = re.search(r'"wings"\s*:\s*\[', text)
        if match is None:
            refused.append(f"{finding.file}: no \"wings\" array found")
            continue
        open_pos = match.end() - 1
        depths = _structural_depths(text)
        close_pos = _matching_bracket(text, depths, open_pos)
        if close_pos is None:
            refused.append(f"{finding.file}: \"wings\" array has no matching ']'")
            continue
        literals = list(string_re.finditer(text, open_pos + 1, close_pos))
        if len(literals) != wings_count:
            refused.append(
                f"{finding.file}: {len(literals)} wing entries found in the file but the scan saw {wings_count}; ambiguous, skipped"
            )
            continue
        for literal in reversed(literals[wings_count - excess:]):
            text = _remove_span_with_comma(text, literal.start(), literal.end())
        changes.append(FileChange(path=path, before=raw, after=_encode(text, had_bom)))
    if refused:
        if not changes:
            raise FixerError("No variant-wings-exceed-bays finding could be trimmed: " + "; ".join(refused))
        options.setdefault("partial_refusals", []).append("Not trimmed (variant-wings-exceed-bays): " + "; ".join(refused))
    return changes


def _fix_variant_weapon_slot_removed(root: Path, options: dict, finding_id: str) -> list[FileChange]:
    """Shared by variant-weapon-slot-mismatch and variant-weapon-slot-missing (owner ruling
    2026-09-29): remove the one slot->weapon entry the finding names from its weapon group's
    "weapons"; if that empties the group's own weapons, remove the whole group object from
    "weaponGroups" too (rather than leave an empty group behind). Nothing else in the file changes.
    Several findings against the same file are applied in turn, each against the file as the
    previous one left it, so two bad weapons in the same group correctly empty (and remove) it.
    """
    by_file: dict[str, list] = {}
    for finding in _findings_of(root, options, finding_id):
        if finding.file:
            by_file.setdefault(finding.file, []).append(finding)
    changes: list[FileChange] = []
    refused: list[str] = []
    for relative in sorted(by_file):
        findings = by_file[relative]
        path = root / relative
        if not path.is_file():
            refused.append(f"{relative}: file not found")
            continue
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        for finding in findings:
            values = {e.split(":", 1)[0]: e.split(":", 1)[1] for e in finding.evidence if ":" in e}
            slot_id, weapon_id = values.get("slot"), values.get("weapon")
            if not slot_id or not weapon_id:
                refused.append(f"{relative}: {finding.id} evidence has no slot/weapon id")
                continue
            match = re.search(r'"' + re.escape(slot_id) + r'"\s*:\s*"' + re.escape(weapon_id) + r'"', text)
            if match is None:
                refused.append(f"{relative}: slot '{slot_id}' -> weapon '{weapon_id}' not found (already changed?)")
                continue
            depths = _structural_depths(text)
            weapons_open = _enclosing_bracket(text, depths, match.start(), "{")
            weapons_close = _matching_bracket(text, depths, weapons_open) if weapons_open is not None else None
            if weapons_open is None or weapons_close is None:
                refused.append(f"{relative}: could not locate the weapons object enclosing slot '{slot_id}'")
                continue
            remaining = len(_STRING_PAIR_RE.findall(text[weapons_open + 1:weapons_close]))
            if remaining <= 1:
                group_open = _enclosing_bracket(text, depths, weapons_open, "{")
                group_close = _matching_bracket(text, depths, group_open) if group_open is not None else None
                if group_open is None or group_close is None:
                    refused.append(f"{relative}: could not locate the weapon group enclosing slot '{slot_id}'")
                    continue
                text = _remove_span_with_comma(text, group_open, group_close + 1)
            else:
                text = _remove_span_with_comma(text, match.start(), match.end())
        changes.append(FileChange(path=path, before=raw, after=_encode(text, had_bom)))
    if refused:
        if not changes:
            raise FixerError(f"No {finding_id} finding could be fixed: " + "; ".join(refused))
        options.setdefault("partial_refusals", []).append(f"Not fixed ({finding_id}): " + "; ".join(refused))
    return changes


def _fix_variant_op_over_budget(root: Path, options: dict) -> list[FileChange]:
    """Trim an over-budget variant to its hull's ordnance points (owner ruling 2026-09-27: "trim to fit if
    possible, best estimate"). Order: flux capacitors, then flux vents (1 OP each, the least character-changing),
    then non-built-in hull mods, costliest first. If even that cannot fit the budget the variant is refused and left
    as it is, because the only step left would be removing weapons. Aims at the raw budget, no tolerance. Edits are
    surgical: only the two flux numbers and the removed hullMods entries change. Needs `options["vanilla_core"]`."""
    from .scanner import (HULL_MOD_COST_COLUMN_BY_SIZE, _csv_id_index, _float_or, _resolve_variant_hull_and_slots,
                          _ship_file_index, _skin_index, _skin_weapon_slot_changes, scan_mod)

    vanilla = options.get("vanilla_core")
    if not vanilla:
        raise FixerError("variant-op-over-budget needs --vanilla-core (vanilla weapon, hull mod and hull costs).")
    vanilla = Path(vanilla)
    if options.get("scan_findings") is None:
        findings = [f for f in scan_mod(root, vanilla_core=vanilla).findings if f.id == "variant-op-over-budget"]
    else:
        findings = _findings_of(root, options, "variant-op-over-budget")
    reference = options.get("reference_core")
    if reference:
        # Owner ruling 2026-09-27 (option 2): trim only variants that fit under the reference game's costs, i.e.
        # the ones RC8's cost changes pushed over; a variant over budget there too was authored that way (as RC8's
        # own 12 over-budget variants are) and is left alone.
        from .models import ScanResult, TargetProfile
        from .scanner import _scan_variant_validity

        ref_result = ScanResult(input_path=root, target=TargetProfile())
        _scan_variant_validity(root, ref_result, Path(reference))
        authored = {f.file for f in ref_result.findings if f.id == "variant-op-over-budget"}
        findings = [f for f in findings if f.file not in authored]
    ship_files, skins, skin_slots = _ship_file_index(root, vanilla), _skin_index(root, vanilla), _skin_weapon_slot_changes(root, vanilla)
    hull_mod_costs = _csv_id_index(root / "data" / "hullmods" / "hull_mods.csv", vanilla / "data" / "hullmods" / "hull_mods.csv")
    changes, refused = [], []
    for finding in findings:
        values = {e.split(":", 1)[0]: e.split(":", 1)[1] for e in finding.evidence if ":" in e}
        excess = _float_or(values.get("total-op")) - _float_or(values.get("budget"))
        path = root / finding.file
        if excess <= 0 or not path.is_file():
            continue
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        from .scanner import _load_lenient_json_file

        data = _load_lenient_json_file(path) or {}
        _hull, ship_json, _slots = _resolve_variant_hull_and_slots(str(data.get("hullId") or ""), ship_files, skins, skin_slots)
        cost_column = HULL_MOD_COST_COLUMN_BY_SIZE.get(str((ship_json or {}).get("hullSize") or "").upper(), "cost_cruiser")
        built_in = set((ship_json or {}).get("builtInMods") or []) | {m for key in ("sMods", "permaMods") for m in (data.get(key) or []) if isinstance(m, str)}
        caps, vents = int(_float_or(data.get("fluxCapacitors"))), int(_float_or(data.get("fluxVents")))
        cut_caps = min(caps, int(-(-excess // 1)))
        excess -= cut_caps
        cut_vents = min(vents, max(0, int(-(-excess // 1))))
        excess -= cut_vents
        removed_mods = []
        mods = [m for m in data.get("hullMods") or [] if isinstance(m, str) and m not in built_in and m in hull_mod_costs]
        for mod_id in sorted(mods, key=lambda m: -_float_or(hull_mod_costs[m].get(cost_column))):
            if excess <= 0:
                break
            cost = _float_or(hull_mod_costs[mod_id].get(cost_column))
            if cost > 0:
                removed_mods.append(mod_id)
                excess -= cost
        if excess > 0:
            refused.append(f"{finding.file} ({excess:.0f} OP over even without flux and hull mods; weapons would have to go)")
            continue
        for key, new in (("fluxCapacitors", caps - cut_caps), ("fluxVents", vents - cut_vents)):
            text = re.sub(r'("' + key + r'"\s*:\s*)-?\d+(\.\d+)?', lambda m, n=new: m.group(1) + str(n), text, count=1)
        for mod_id in removed_mods:
            text = re.sub(r'\s*"' + re.escape(mod_id) + r'"\s*,', "", text, count=1) if re.search(r'"' + re.escape(mod_id) + r'"\s*,', text) \
                else re.sub(r',?\s*"' + re.escape(mod_id) + r'"', "", text, count=1)
        changes.append(FileChange(path=path, before=raw, after=_encode(text, had_bom)))
    if refused:
        if not changes:
            raise FixerError("No over-budget variant can be trimmed to fit without removing weapons: " + "; ".join(refused))
        options.setdefault("partial_refusals", []).append("Not trimmed (weapons would have to go): " + "; ".join(refused))
    return changes


def _fix_procgen_mod_body_leak(root: Path, options: dict) -> list[FileChange]:
    """Zero the procgen weight of each type `procgen-mod-body-leak` names (P15 item 25): the Zorg18 r3 fix as a
    fixer. Only the frequency fields of that type's row change; the row stays so nothing else loses the type."""
    by_file: dict[str, set[str]] = {}
    for finding in _findings_of(root, options, "procgen-mod-body-leak"):
        type_id = next((e.split(":", 1)[1] for e in finding.evidence if e.startswith("type:")), None)
        if type_id and finding.file:
            by_file.setdefault(finding.file, set()).add(type_id)
    columns = {"star_gen_data.csv": ("freqYOUNG", "freqAVERAGE", "freqOLD"), "planet_gen_data.csv": ("frequency",)}
    changes = []
    for relative, types in sorted(by_file.items()):
        path = root / relative
        if not path.is_file():
            continue
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        newline = "\r\n" if "\r\n" in text else "\n"
        lines = text.split(newline)
        header = next(csv.reader([lines[0]]))
        wanted = [header.index(c) for c in columns.get(path.name, ()) if c in header]
        for number, line in enumerate(lines[1:], 1):
            fields = next(csv.reader([line]), [])
            if fields and fields[0].strip() in types:
                spans = _line_field_spans(line)
                for index in sorted(wanted, reverse=True):
                    if index < len(spans):
                        start, end, _raw = spans[index]
                        line = line[:start] + "0" + line[end:]
                lines[number] = line
        changes.append(FileChange(path=path, before=raw, after=_encode(newline.join(lines), had_bom)))
    return changes

def _fix_csv_slash_quote_escape(root: Path, options: dict) -> list[FileChange]:
    """Rewrite each /"phrase/" (or \\"phrase\\") that `csv-slash-quote-escape` names as ""phrase"", the CSV escape
    vanilla's descriptions.csv uses (SEEKER 0.6.6 special_items.csv, 2026-09-28). Nothing else in the file changes."""
    from .scanner import CSV_SLASH_QUOTE

    changes = []
    for relative in sorted({f.file for f in _findings_of(root, options, "csv-slash-quote-escape") if f.file}):
        path = root / relative
        if not path.is_file():
            continue
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        fixed = CSV_SLASH_QUOTE.sub(lambda m: '""' + m.group(1) + '""', text)
        if fixed != text:
            changes.append(FileChange(path=path, before=raw, after=_encode(fixed, had_bom)))
    return changes


def _fix_campaign_lookup_guard(root: Path, options: dict, finding_id: str) -> list[FileChange]:
    """Guard an unguarded `getStarSystem("X")` / `getEntityById("X")` in a void method: right after the declaration
    that takes the result, `if (v == null) { log a warning; return; }`. Done by hand for Pegasus Belt Council,
    Vayra's Sector and First Persean Empire (2026-09-29/30): a generator that assumes a vanilla system or entity
    exists NPEs at New Game in a total conversion or random sector.

    Applied only where the edit cannot change anything else: a one-line local declaration directly in a void
    method's body (not in a loop, lambda or inner block), so the early return skips only the rest of that method,
    which would have thrown on the null. Every other shape is refused and stays with an agent."""
    from .scanner import _blank_java_comments

    method = "getStarSystem" if finding_id == "hard-coded-campaign-system-reference" else "getEntityById"
    names_by_file: dict[str, set[str]] = {}
    for finding in _findings_of(root, options, finding_id):
        if finding.file and finding.evidence and "null-guarded" not in finding.evidence and "created-in-same-file" not in finding.evidence:
            names_by_file.setdefault(finding.file, set()).add(finding.evidence[0])
    changes, refused = [], []
    for relative, names in sorted(names_by_file.items()):
        path = root / relative
        # A jar's source tree is not what runs: an edit there changes nothing until the jar is rebuilt, so it is a jar
        # packet for patch-jar-class (21 of 33 first-run edits were jar sources, 2026-09-30).
        if not path.is_file() or path.suffix != ".java" or relative.replace("\\", "/").startswith(("src/", "jars/", "jar/")):  # any source under jars/ (Free Stars Union: jars/FSU_source_from_Procyon/)
            refused.append(relative)
            continue
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        newline = "\r\n" if "\r\n" in text else "\n"
        # Split the real and the comment-blanked text on the same boundaries: the blanker turns "\r" into a space, so
        # on a CRLF file split(newline) gave the blanked text ONE line and the guard went in at line 1, inside a doc
        # comment, once per revive round (Scy Nation's SCY_outposts, five times, 2026-09-30). Mixed endings: refuse.
        if newline == "\r\n" and text.count("\n") != text.count("\r\n"):
            refused.append(f"{relative} (mixed line endings)")
            continue
        lines = text.split(newline)
        blank = _blank_java_comments(text.replace("\r\n", "\n")).split("\n")
        if len(blank) != len(lines):
            refused.append(f"{relative} (line split mismatch)")
            continue
        cls = re.search(r"\bclass\s+(\w+)", _blank_java_comments(text))
        inserts: list[tuple[int, str]] = []
        for name in sorted(names):
            call = re.escape(method) + r'\s*\(\s*"' + re.escape(name) + r'"\s*\)'
            hits = [i for i, line in enumerate(blank) if re.search(call, line)]
            placed = False
            for i in hits:
                decl = re.match(r"^(\s*)(?:final\s+)?[\w.]+(?:<[\w.,\s<>?]*>)?\s+(\w+)\s*=\s*[^;]*" + call + r"\s*;\s*$", blank[i])
                if not decl or cls is None:
                    continue
                # Brace depth from the enclosing method's opening brace must be exactly 1.
                depth, start = 0, None
                for j in range(i - 1, -1, -1):
                    depth += blank[j].count("}") - blank[j].count("{")
                    if depth < 0:
                        start = j
                        break
                if start is None or depth != -1 or not re.search(r"\bvoid\s+\w+\s*\([^)]*\)\s*(?:throws[^{]*)?\{\s*$", blank[start]):
                    continue
                if "->" in blank[start]:
                    continue
                indent, variable = decl.group(1), decl.group(2)
                if i + 1 < len(lines) and f"if ({variable} == null)" in lines[i + 1]:
                    continue  # already guarded right here: never insert twice
                what = "star system" if method == "getStarSystem" else "entity"
                inserts.append((i + 1, newline.join([
                    f"{indent}if ({variable} == null) {{ // BridgeForge: guard a missing {what} (a total conversion or random sector)",
                    f'{indent}    com.fs.starfarer.api.Global.getLogger({cls.group(1)}.class).warn("{what} \\"{name}\\" not found, skipping the rest of this generator");',
                    f"{indent}    return;",
                    f"{indent}}}"])))
                placed = True
            if not placed:
                refused.append(f"{relative} ({name})")
        if inserts:
            for index, block in sorted(inserts, reverse=True):
                lines.insert(index, block)
            changes.append(FileChange(path=path, before=raw, after=_encode(newline.join(lines), had_bom)))
    if refused and not changes:
        raise FixerError(f"{finding_id}: no lookup is a one-line declaration directly in a void method; left for an agent: " + ", ".join(refused))
    return changes


_FIXER_FUNCS = {
    "hard-coded-campaign-system-reference": lambda root, options: _fix_campaign_lookup_guard(root, options, "hard-coded-campaign-system-reference"),
    "hard-coded-campaign-entity-reference": lambda root, options: _fix_campaign_lookup_guard(root, options, "hard-coded-campaign-entity-reference"),
    "csv-slash-quote-escape": _fix_csv_slash_quote_escape,
    "procgen-mod-body-leak": _fix_procgen_mod_body_leak,
    "fleet-type-name-missing": _fix_fleet_type_name_missing,
    "variant-op-over-budget": _fix_variant_op_over_budget,
    "variant-wings-exceed-bays": _fix_variant_wings_exceed_bays,
    "variant-weapon-slot-mismatch": lambda root, options: _fix_variant_weapon_slot_removed(root, options, "variant-weapon-slot-mismatch"),
    "variant-weapon-slot-missing": lambda root, options: _fix_variant_weapon_slot_removed(root, options, "variant-weapon-slot-missing"),
    "data-file-not-utf8": _fix_data_file_not_utf8,
    "shippable-work-file": _fix_shippable_work_file,
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
    "rules-firebest-populate-options": _fix_rules_firebest_populate_options,
    "personality-id-unknown": _fix_personality_id_unknown,
    "hullmod-instance-state": _fix_hullmod_instance_state,
    "nexerelin-corvus-mode-import": _fix_nexerelin_corvus_mode_import,
    "spawned-ship-captain-personality-risk": _fix_spawned_ship_captain,
    "json-missing-comma": _fix_json_missing_comma,
    "builtin-wing-is-hullmod": _fix_builtin_wing_is_hullmod,
    "wing-op-cost-blank": _fix_wing_op_cost_blank,
    "campaign-lookup-dereferenced-unguarded": _fix_lookup_dereferenced_unguarded,
    "temporary-market-fleet-source": _fix_temporary_market_fleet_source,
    "faction-trait-weight-legacy-personality-id": _fix_faction_trait_weight_legacy_personality_id,
    "shiproles-wing-id": _fix_shiproles_wing_id,
    "csv-fullwidth-number": _fix_csv_fullwidth_number,
    "ship-data-missing-fighter-bays-column": _fix_ship_data_missing_fighter_bays_column,
    "missing-custom-ui-button-pressed-callback": _fix_missing_custom_ui_button_pressed_callback,
}


def compute_fix(mod_dir: Path, finding_id: str, options: dict | None = None) -> FixPlan:
    """Compute (never write) the surgical edit(s) for one supported finding id."""
    if finding_id not in SUPPORTED_FINDINGS:
        raise FixerError(f"Unsupported finding id '{finding_id}'. Supported: {', '.join(SUPPORTED_FINDINGS)}")
    root = Path(mod_dir).expanduser().resolve()
    if not root.is_dir():
        raise FixerError(f"{root} is not an existing directory.")
    options = options or {}
    handler = _FIXER_FUNCS[finding_id]
    changes = [change for change in handler(root, options) if change.changed]
    if not changes:
        raise FixerError(f"No change was computed for finding '{finding_id}'.")
    if not options.get("allow_shadowed_edit"):
        _refuse_shadowed_edits(root, changes, options.get("provider_roots"))
    return FixPlan(finding_id=finding_id, mod_root=root, changes=changes)


def _refuse_shadowed_edits(root: Path, changes: list[FileChange], provider_roots: list[Path] | None = None) -> None:
    """Refuse a plan that edits a loose script one of this mod's own jars already shadows (ROADMAP
    P14 item 14). `loose-script-shadowed-by-jar` already says editing such a file has no effect - the
    game loads the jar class and never compiles the loose one - but nothing previously stopped a
    fixer writing the edit anyway. Found 2026-09-20: a task converted six `setPersonality(...)` calls
    in Thule-Legacy's `MissionDefinition.java` with a full evidence trail, and it changed nothing
    in-game, because `ThuleLegacy.jar` shipped that exact class. Pass `allow_shadowed_edit: True` in
    `compute_fix`'s `options` only when the jar is also being rebuilt from the patched source in the
    same pass (as this exact case was, once caught) - otherwise the edit is dead on arrival.

    ROADMAP P14 item 12 extends the same guard to a *declared dependency's* jar (Maelstrom
    Interstellar Imperium Unofficial Expansion, escalation E8) - all mod jars share one classloader,
    so the rule is identical either way. `options["provider_roots"]` (default: the same
    `<repo>/In operation` + rig mods default `compile-check`/`dependency-substitutes` use) can
    override which providers are searched.
    """
    from .scanner import _dependency_jar_class_names, loose_script_jar_shadowed_class

    dependency_classes = None  # computed lazily, once, only if a candidate script needs it
    for change in changes:
        if change.path.suffix.lower() != ".java":
            continue
        try:
            relative = change.path.relative_to(root)
        except ValueError:
            continue
        if "data" not in relative.parts:
            continue
        shadowing_class = loose_script_jar_shadowed_class(root, change.path)
        if shadowing_class is not None:
            raise FixerError(
                f"{change.path} is shadowed by a class already compiled into one of this mod's own jars "
                f"({shadowing_class}): the game loads the jar's class and never compiles this loose script, "
                "so editing it has no effect. Rebuild the jar from the patched source (or strip the class "
                "so the loose script compiles), or pass allow_shadowed_edit=True if that is already planned "
                "as part of this same fix."
            )
        if dependency_classes is None:
            dependency_classes = _dependency_jar_class_names(root, provider_roots)
        class_name = ".".join(relative.with_suffix("").parts)
        provider_name = dependency_classes.get(class_name)
        if provider_name is not None:
            raise FixerError(
                f"{change.path} is shadowed by a class already compiled into the declared dependency "
                f"{provider_name}'s own jar ({class_name}): the game loads {provider_name}'s class and never "
                "compiles this loose script, so editing it has no effect. Patch the dependency's jar (or its "
                "source, if you can rebuild it) instead, or pass allow_shadowed_edit=True if that is already "
                "planned as part of this same fix."
            )


def unified_diff_for_change(change: FileChange) -> str:
    """A unified diff for one FileChange, decoding best-effort for display only (never affects the write)."""
    if change.removed:
        return f"--- {change.path}\n+++ /dev/null\n@@ removed ({len(change.before)} bytes) @@\n"
    if not change.existed_before and b"\x00" in change.after[:8192]:
        return f"--- /dev/null\n+++ {change.path}\n@@ new binary file ({len(change.after)} bytes) @@\n"
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
    copies = {change.after for change in plan.changes if not change.existed_before and not change.removed}
    for change in plan.changes:
        backup: Path | None = None
        if change.removed:
            # A move's new copy is its backup; a bare removal keeps the usual .bak next to it.
            if change.before not in copies:
                backup = _backup_path(change.path, plan.finding_id)
                backup.write_bytes(change.before)
            change.path.unlink()
            applied.append({"path": str(change.path), "backup": str(backup) if backup is not None else None, "removed": True})
            continue
        if change.existed_before:
            backup = _backup_path(change.path, plan.finding_id)
            backup.write_bytes(change.before)
        change.path.parent.mkdir(parents=True, exist_ok=True)
        change.path.write_bytes(change.after)
        applied.append({"path": str(change.path), "backup": str(backup) if backup is not None else None})
    return applied
