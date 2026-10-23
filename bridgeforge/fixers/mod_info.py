from __future__ import annotations
import json
import re
from pathlib import Path
from ..build_tag import _NAME_PATTERN, _find_top_level_key, _string_literal_to_text, _structural_depths, _text_to_string_literal
from ..scanner import MOD_INFO_TRIAGE_BANNER_PATTERN, _parse_json
from .common import FileChange, FixerError, _decode, _encode


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
