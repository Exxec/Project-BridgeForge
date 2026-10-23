from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Callable
from ..scanner import REMOVED_API_CALLS, _blank_java_comments, _load_lenient_json_file, _parse_json, _relative, _removed_api_call_spans
from .common import FileChange, FixerError, _decode, _encode


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


def _rewrite_crew_xp_level_span(matched_text: str) -> str:
    # getCrew(CrewXPLevel.X): REGULAR reads all crew, other tiers 0 (owner decision "one crew", Ironclads 2026-10-05).
    read = re.match(r"getCrew\s*\(.*CrewXPLevel\s*\.\s*(\w+)\s*\)$", matched_text, re.S)
    if read:
        return "getCrew()" if read.group(1) == "REGULAR" else "getCrew() * 0 /* 0.7 non-REGULAR crew tier */"
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
