from __future__ import annotations
import json
import re
from pathlib import Path
from ..build_tag import _string_literal_to_text, _structural_depths
from ..scanner import _load_lenient_json_file, _parse_json
from .common import FileChange, FixerError, _decode, _encode, _findings_of
from .removed_api import _DEPENDENCIES_ARRAY_PATTERN, _add_revenantlib_dependency


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
    from ..scanner import LIBRARY_DEPENDENCY_IDS

    to_add: dict[str, str] = {}  # dependency_id -> library display name
    # Providers a person approved (item 73 B7: the one indexed mod that defines an unresolved import's class): declared by
    # id and name exactly as given. The provider's version is shown in the packet, never written (no evidence yet that the
    # game's dependency `version` is a minimum rather than an exact match).
    for provider in options.get("declare_providers") or []:
        if not isinstance(provider, dict) or not str(provider.get("id") or "").strip():
            raise FixerError(f"declare_providers entry {provider!r} needs an id.")
        to_add[str(provider["id"]).strip()] = str(provider.get("name") or provider["id"]).strip()
    findings = [] if to_add else _findings_of(root, options, "undeclared-library-dependency")
    if not findings and not to_add:
        raise FixerError("No undeclared-library-dependency finding for this mod.")
    # A guard whose absent branch throws is a required library, not an optional one (Hiigaran Descendants, shaderLib).
    findings = [f for f in findings if "guard:present" not in (f.evidence or []) or "required:throws-without" in (f.evidence or [])]
    if not findings and not to_add:
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
