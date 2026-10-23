from __future__ import annotations
import fnmatch
import json
import re
from pathlib import Path
from ..build_tag import _structural_depths
from bridgeforge.scan.scanner import FACTION_SPECIAL_ROLE_KEYS, LEGACY_PERSONALITY_IDS, _load_lenient_json_file, _parse_json, _wing_id_variant_map, _wing_ids_set
from .common import FileChange, FixerError, _decode, _encode
from .encoding import _referencing_bytes


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
    from ..copy_drift import _collect
    from bridgeforge.scan.scanner import _WORK_FILE_GLOBS

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
