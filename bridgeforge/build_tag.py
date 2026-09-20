from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .scanner import _parse_json

DEFAULT_LABEL = "BF"


class BuildTagError(ValueError):
    """Raised when mod_info.json cannot be located, read, edited, or is not a well-formed object."""


def _find_mod_info(mod_dir: Path) -> Path:
    """Locate mod_info.json at `mod_dir` itself or a child/grandchild directory (depth <= 2)."""
    root = Path(mod_dir).expanduser().resolve()
    if not root.is_dir():
        raise BuildTagError(f"{root} is not an existing directory.")
    direct = root / "mod_info.json"
    if direct.is_file():
        return direct
    frontier = [root]
    for _ in range(2):
        next_frontier: list[Path] = []
        for parent in frontier:
            try:
                children = sorted(child for child in parent.iterdir() if child.is_dir())
            except OSError:
                continue
            for child in children:
                candidate = child / "mod_info.json"
                if candidate.is_file():
                    return candidate
                next_frontier.append(child)
        frontier = next_frontier
    raise BuildTagError(f"No mod_info.json found under {root} (searched to depth 2).")


_STRING_LITERAL = r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\''
_OBJECT_LITERAL = r"\{[^{}]*\}"


def _key_value_pattern(key: str, *, allow_object: bool) -> re.Pattern[str]:
    value_pattern = f"{_STRING_LITERAL}|{_OBJECT_LITERAL}" if allow_object else _STRING_LITERAL
    return re.compile(rf'(?P<key>[\'"]{re.escape(key)}[\'"])(?P<sep>\s*:\s*)(?P<value>{value_pattern})')


_NAME_PATTERN = _key_value_pattern("name", allow_object=False)
_VERSION_PATTERN = _key_value_pattern("version", allow_object=True)
_VERSION_BF_SUFFIX_PATTERN = re.compile(r"\+bf\.(\d+)\s*$")


def _structural_depths(text: str) -> list[int]:
    """Brace/bracket nesting depth "at" each character offset (the depth enclosing that character).

    Batavia, Qualljom and Antediluvians all list `"dependencies":[{"id":"revenantlib",
    "name":"RevenantLib"}]` before the mod's own top-level "name" (read 2026-09-15); a plain
    `_NAME_PATTERN.search(text)` finds that dependency's "name" first and tags it instead. This
    walks the raw text once, skipping string contents (both `"`/`'` quoting, backslash-escaped) and
    `#`/`//` line comments (the leniences build_tag's caller-facing JSON already tolerates) so only
    real structural `{[`/`}]` characters change the count. A key whose opening quote sits at depth 1
    is a direct property of the root object; anything deeper (inside "dependencies", say) is not.
    """
    n = len(text)
    depths = [0] * n
    depth = 0
    in_string = False
    quote = ""
    escaped = False
    in_comment = False
    i = 0
    while i < n:
        char = text[i]
        if in_comment:
            depths[i] = depth
            if char in "\r\n":
                in_comment = False
            i += 1
            continue
        if in_string:
            depths[i] = depth
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                in_string = False
            i += 1
            continue
        depths[i] = depth
        if char in "\"'":
            in_string = True
            quote = char
        elif char == "#" or (char == "/" and i + 1 < n and text[i + 1] == "/"):
            in_comment = True
        elif char in "{[":
            depth += 1
        elif char in "}]":
            depth = max(0, depth - 1)
        i += 1
    return depths


def _find_top_level_key(text: str, pattern: re.Pattern[str], depths: list[int]) -> re.Match[str] | None:
    """The first match of `pattern` whose key sits directly inside the root object (depth 1)."""
    for match in pattern.finditer(text):
        start = match.start("key")
        if start < len(depths) and depths[start] == 1:
            return match
    return None


def _string_literal_to_text(literal: str) -> str:
    quote = literal[0]
    body = literal[1:-1]
    if quote == '"':
        try:
            return json.loads(literal)
        except json.JSONDecodeError:
            return body
    return body.replace("\\'", "'").replace('\\"', '"').replace("\\\\", "\\")


def _text_to_string_literal(text: str, quote: str) -> str:
    if quote == '"':
        return json.dumps(text)
    escaped = text.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def _bump_name(name: str, label: str, set_value: int | None) -> tuple[str, int]:
    suffix_pattern = re.compile(rf"\s*\[{re.escape(label)}\s+r(\d+)\]\s*$")
    match = suffix_pattern.search(name)
    if match:
        base = name[:match.start()]
        current = int(match.group(1))
    else:
        base = name
        current = 0
    build = set_value if set_value is not None else current + 1
    return f"{base.rstrip()} [{label} r{build}]", build


def _bump_version(version: str, set_value: int | None) -> tuple[str, int]:
    match = _VERSION_BF_SUFFIX_PATTERN.search(version)
    if match:
        base = version[:match.start()]
        current = int(match.group(1))
    else:
        base = version
        current = 0
    build = set_value if set_value is not None else current + 1
    return f"{base}+bf.{build}", build


def build_tag(mod_dir: Path, label: str = DEFAULT_LABEL, set_value: int | None = None) -> dict[str, object]:
    """Compute an iterated build tag for a revived mod's mod_info.json name/version.

    Edits the file text surgically: only the "name" and "version" string values are replaced
    in place (regex-anchored on the key, honoring both `"` and `'` quoting). The JSON is never
    re-serialized, so comments, trailing commas, key order, BOM, and line endings outside those
    two values survive untouched. "id" is never touched, and this never opens a .version
    (version-checker) file -- only mod_info.json.
    """
    mod_info_path = _find_mod_info(mod_dir)
    try:
        raw = mod_info_path.read_bytes()
    except OSError as exc:
        raise BuildTagError(f"{mod_info_path} could not be read: {exc}") from exc
    had_bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise BuildTagError(f"{mod_info_path} is not valid UTF-8: {exc}") from exc

    depths = _structural_depths(text)
    name_match = _find_top_level_key(text, _NAME_PATTERN, depths)
    if name_match is None:
        raise BuildTagError(f'{mod_info_path} has no top-level "name" string to tag.')
    old_name_literal = name_match.group("value")
    old_name = _string_literal_to_text(old_name_literal)
    new_name, build = _bump_name(old_name, label, set_value)
    new_name_literal = _text_to_string_literal(new_name, old_name_literal[0])

    version_match = _find_top_level_key(text, _VERSION_PATTERN, depths)
    version_is_object = False
    old_version: str | None = None
    new_version: str | None = None
    new_version_literal: str | None = None
    if version_match is not None:
        raw_value = version_match.group("value")
        if raw_value.lstrip().startswith("{"):
            version_is_object = True
            old_version = raw_value
            new_version = raw_value
        else:
            old_version = _string_literal_to_text(raw_value)
            new_version, _version_build = _bump_version(old_version, set_value)
            new_version_literal = _text_to_string_literal(new_version, raw_value[0])

    edits: list[tuple[int, int, str]] = [(name_match.start("value"), name_match.end("value"), new_name_literal)]
    if version_match is not None and not version_is_object:
        edits.append((version_match.start("value"), version_match.end("value"), new_version_literal))
    edits.sort(key=lambda item: item[0], reverse=True)
    new_text = text
    for start, end, replacement in edits:
        new_text = new_text[:start] + replacement + new_text[end:]

    try:
        parsed, _tolerances = _parse_json(new_text)
    except json.JSONDecodeError as exc:
        raise BuildTagError(f"Edited mod_info.json failed to re-parse: {exc}") from exc
    if not isinstance(parsed, dict):
        raise BuildTagError("Edited mod_info.json did not parse back to a JSON object.")
    if parsed.get("name") != new_name:
        raise BuildTagError("Edited mod_info.json's name did not round-trip to the expected value.")
    if not version_is_object and parsed.get("version") != new_version:
        raise BuildTagError("Edited mod_info.json's version did not round-trip to the expected value.")

    new_bytes = (b"\xef\xbb\xbf" if had_bom else b"") + new_text.encode("utf-8")
    return {
        "mod_info": str(mod_info_path),
        "old_name": old_name,
        "new_name": new_name,
        "old_version": old_version,
        "new_version": new_version,
        "version_is_object": version_is_object,
        "build": build,
        "_new_bytes": new_bytes,
    }


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def default_manifests_dir() -> Path:
    """Default location for per-tag hash manifests -- always outside any mod folder (roadmap P5)."""
    return _repo_root() / "bridgeforge-state" / "build-manifests"


def compute_working_copy_hashes(mod_dir: Path) -> dict[str, str]:
    """sha256 per relative POSIX path, over the same data/jars/graphics/sounds/mod_info.json set
    that `copy_drift` compares and that gets packaged -- backups and src excluded, since a manifest
    exists to drive test selection on shippable content, not on working-tree scratch files."""
    # Imported lazily (not at module import time) to avoid a hard import cycle: copy_drift does not
    # import build_tag, so this direction is safe, but keeping it local documents the dependency.
    from .copy_drift import _collect, _find_mod_root

    root = _find_mod_root(mod_dir)
    files = _collect(root)
    return {rel: hashlib.sha256(path.read_bytes()).hexdigest() for rel, path in files.items()}


def _mod_id_for_manifest(mod_info_path: Path) -> str | None:
    try:
        data, _tolerances = _parse_json(mod_info_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(data, dict):
        value = data.get("id")
        if isinstance(value, str) and value:
            return value
    return None


def record_build_manifest(
    mod_dir: Path,
    build: int,
    *,
    manifests_dir: Path | None = None,
) -> dict[str, object]:
    """Write `<manifests_dir>/<mod-id>/r<build>.json`: a per-tag hash manifest for `test_plan`'s diff.

    Always written outside the mod folder (default `<repo>/bridgeforge-state/build-manifests/`, or a
    caller-given `manifests_dir`), so it is never packaged with the mod.
    """
    mod_info_path = _find_mod_info(mod_dir)
    mod_id = _mod_id_for_manifest(mod_info_path)
    target_dir = Path(manifests_dir).expanduser().resolve() if manifests_dir is not None else default_manifests_dir()
    target_dir = target_dir / (mod_id or "unknown-mod")
    target_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "mod_id": mod_id,
        "mod_dir": str(mod_info_path.parent),
        "build": build,
        "files": compute_working_copy_hashes(mod_info_path.parent),
    }
    manifest_path = target_dir / f"r{build}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"path": manifest_path, "mod_id": mod_id, "build": build, "file_count": len(manifest["files"])}


def _current_build(mod_info_path: Path, label: str = DEFAULT_LABEL) -> int:
    """The build number already encoded in mod_info.json's name suffix, or 0 if untagged."""
    try:
        text = mod_info_path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise BuildTagError(f"{mod_info_path} could not be read: {exc}") from exc
    match = _find_top_level_key(text, _NAME_PATTERN, _structural_depths(text))
    if match is None:
        return 0
    name = _string_literal_to_text(match.group("value"))
    suffix_pattern = re.compile(rf"\s*\[{re.escape(label)}\s+r(\d+)\]\s*$")
    suffix_match = suffix_pattern.search(name)
    return int(suffix_match.group(1)) if suffix_match else 0


def record_current_manifest(
    mod_dir: Path,
    *,
    manifests_dir: Path | None = None,
) -> dict[str, object]:
    """Record a hash manifest for the CURRENT build number, without bumping or writing mod_info.json.

    If the mod has no `[BF rN]` name suffix yet (never build-tagged), the current build is treated
    as `r0` -- `test_plan._normalize_tag("r0")` accepts that directly, so `test_plan.plan_tests(...,
    since_tag="r0")` (or `--since r0` on the CLI) can diff a working copy against this manifest even
    before the mod has ever been tagged.
    """
    mod_info_path = _find_mod_info(mod_dir)
    build = _current_build(mod_info_path)
    return record_build_manifest(mod_dir, build, manifests_dir=manifests_dir)


def apply_build_tag(
    mod_dir: Path,
    label: str = DEFAULT_LABEL,
    set_value: int | None = None,
    dry_run: bool = False,
    *,
    manifests_dir: Path | None = None,
    record_manifest: bool = False,
) -> dict[str, object]:
    """Compute the build tag and, unless `dry_run`, write it back to mod_info.json.

    Pass `record_manifest=True` (roadmap P5) to also record a per-tag working-copy hash manifest
    via `record_build_manifest`, stored outside the mod folder -- see `default_manifests_dir`. It
    defaults to `False` so every *existing* caller of `apply_build_tag` (the CLI's `build-tag` and
    `prepare-test --bump`, and every test that predates P5) keeps writing nothing beyond
    mod_info.json unless it explicitly opts in; wire `record_manifest=True` wherever a caller wants
    `test_plan.plan_tests` to have a manifest to diff against.
    """
    result = build_tag(mod_dir, label=label, set_value=set_value)
    new_bytes = result.pop("_new_bytes")
    if not dry_run:
        Path(result["mod_info"]).write_bytes(new_bytes)
        if record_manifest:
            manifest_info = record_build_manifest(mod_dir, result["build"], manifests_dir=manifests_dir)
            result["manifest_path"] = str(manifest_info["path"])
            result["manifest_file_count"] = manifest_info["file_count"]
    return result
