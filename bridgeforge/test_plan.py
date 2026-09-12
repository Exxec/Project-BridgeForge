from __future__ import annotations

import fnmatch
import json
import re
from pathlib import Path

from .build_tag import compute_working_copy_hashes, default_manifests_dir
from .copy_drift import _find_mod_root
from .scanner import _load_lenient_json_file

"""Change-impact test selection (roadmap P5).

`plan_tests` diffs a mod's current working copy against the file hashes recorded at a prior
`build-tag` bump (`build_tag.record_build_manifest`), maps the changed files to features with a
small data-driven rules table, and returns the minimal probe assertions plus the
`In operation/LIVE_TEST_INSTRUCTIONS.md` test IDs that matter for what actually changed.

Nothing here launches Starsector or edits any file; it only reads the manifest, the working copy
and (optionally) the live-test instructions document.
"""

DEFAULT_LIVE_TEST_INSTRUCTIONS = "LIVE_TEST_INSTRUCTIONS.md"

# Ordered so a file can be matched by more than one rule (e.g. a faction file is also under
# data/campaign in some mods) -- every matching rule's features are unioned, never short-circuited.
FEATURE_RULES: list[dict[str, object]] = [
    {
        "name": "faction-file",
        "patterns": ["data/world/factions/*.faction", "data/world/factions/**/*.faction"],
        "features": ["markets", "fleets"],
    },
    {
        "name": "ship-system",
        "patterns": ["*.system", "data/shipsystems/ship_systems.csv", "data/shipsystems/**/*.system"],
        "features": ["ship_systems"],
    },
    {
        "name": "worldgen-or-campaign",
        "patterns": ["data/campaign/*", "data/campaign/**/*", "data/config/*worldgen*", "*worldgen*"],
        "features": ["new_game"],
    },
    {
        "name": "hullmod",
        "patterns": ["data/hullmods/*", "data/hullmods/**/*"],
        "features": ["refit"],
    },
    {
        "name": "variant",
        "patterns": ["*.variant", "**/*.variant"],
        "features": ["combat", "refit"],
    },
    {
        "name": "jar",
        "patterns": ["jars/*.jar", "jars/**/*.jar"],
        "features": ["scripted"],
    },
    {
        "name": "description",
        "patterns": ["data/strings/descriptions.csv", "**/descriptions*.csv"],
        "features": ["text"],
    },
    {
        "name": "mod-info",
        "patterns": ["mod_info.json"],
        "features": ["launcher"],
    },
]

# What each feature means for evidence-tier-T2 probe re-runs (roadmap P3's probe checks).
FEATURE_PROBE_ASSERTIONS: dict[str, list[str]] = {
    "markets": [
        "campaign probe: faction known-list check (BF-PROBE faction-known-lists)",
        "campaign probe: submarket stock check (BF-PROBE market-stock)",
    ],
    "fleets": ["campaign probe: fleet presence per faction (BF-PROBE fleet-presence)"],
    "ship_systems": ["combat probe: ship-system activation and captain-personality check"],
    "new_game": [
        "campaign probe: ring/orbit finiteness (BF-PROBE ring-orbit)",
        "campaign probe: planet/star spec resolution (BF-PROBE planet-spec)",
    ],
    "refit": ["manual: hullmod applies/removes correctly in the refit screen"],
    "combat": ["combat probe: hull deployment under AI, weapon/system firing (BF-PROBE combat)"],
    "scripted": ["full re-run: campaign probe + combat probe (a jar change can affect anything scripted)"],
    "text": ["manual: description/asset text renders without truncation or stray quoting"],
    "launcher": ["boot-test: rig reaches the main menu with the mod enabled"],
}

# Keywords used to narrow LIVE_TEST_INSTRUCTIONS.md rows to the ones a feature actually concerns.
# "scripted" (a jar change) matches every row for the mod, since a jar can touch any behaviour.
FEATURE_KEYWORDS: dict[str, list[str]] = {
    "markets": ["market", "stock", "dock", "trade"],
    "fleets": ["fleet", "patrol", "spawn"],
    "ship_systems": ["system"],
    "new_game": ["new game", "generat", "system"],
    "refit": ["refit", "hullmod", "install"],
    "combat": ["combat", "weapon", "missile", "fire", "hit", "simulat"],
    "scripted": [],
    "text": ["description", "render"],
    "launcher": ["baseline", "launch", "menu"],
}

_LIVE_TEST_SECTION_RE = re.compile(r"^#{1,3}\s*\d+[a-z]?\.\s*(.+?)\s*$")
_LIVE_TEST_ROW_RE = re.compile(r"^\|\s*([A-Za-z]{2,6}-\d+[a-z]?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*$")


class TestPlanError(ValueError):
    """Raised when a manifest tag or the mod directory cannot be resolved."""


def _normalize_tag(since_tag: str | int) -> str:
    text = str(since_tag).strip()
    if text.lower().startswith("r"):
        text = text[1:]
    if not text.isdigit():
        raise TestPlanError(f"since_tag must look like a build number or 'rN' (got {since_tag!r}).")
    return f"r{int(text)}"


def _mod_id(root: Path) -> str | None:
    mod_info = root / "mod_info.json"
    if not mod_info.is_file():
        return None
    data = _load_lenient_json_file(mod_info)
    if isinstance(data, dict):
        value = data.get("id")
        if isinstance(value, str) and value:
            return value
    return None


def _mod_name(root: Path) -> str | None:
    mod_info = root / "mod_info.json"
    if not mod_info.is_file():
        return None
    data = _load_lenient_json_file(mod_info)
    if isinstance(data, dict):
        value = data.get("name")
        if isinstance(value, str) and value:
            return value
    return None


def _load_manifest(manifests_dir: Path, mod_id: str | None, root: Path, tag: str) -> dict[str, object]:
    candidates = []
    if mod_id:
        candidates.append(manifests_dir / mod_id / f"{tag}.json")
    candidates.append(manifests_dir / root.name / f"{tag}.json")
    for candidate in candidates:
        if candidate.is_file():
            return json.loads(candidate.read_text(encoding="utf-8"))
    raise TestPlanError(f"No build manifest found for tag {tag} under {manifests_dir} (tried {[str(c) for c in candidates]}).")


def _diff_files(old_hashes: dict[str, str], new_hashes: dict[str, str]) -> dict[str, list[str]]:
    old_names, new_names = set(old_hashes), set(new_hashes)
    added = sorted(new_names - old_names)
    removed = sorted(old_names - new_names)
    modified = sorted(name for name in old_names & new_names if old_hashes[name] != new_hashes[name])
    return {"added": added, "removed": removed, "modified": modified}


def _features_for_file(relative_path: str) -> set[str]:
    features: set[str] = set()
    for rule in FEATURE_RULES:
        if any(fnmatch.fnmatch(relative_path, pattern) for pattern in rule["patterns"]):
            features.update(rule["features"])
    return features


def _parse_live_test_instructions(path: Path) -> dict[str, list[dict[str, str]]]:
    """Section heading (mod name) -> list of {"id", "step", "expected"} rows, best-effort.

    Missing file, or a mod with no matching section, is not an error: `plan_tests` degrades to
    probe assertions alone (this document does not cover every mod, e.g. a mod not yet on the
    live-test board).
    """
    if not path.is_file():
        return {}
    sections: dict[str, list[dict[str, str]]] = {}
    current: str | None = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        heading = _LIVE_TEST_SECTION_RE.match(line)
        if heading:
            current = heading.group(1).strip()
            sections.setdefault(current, [])
            continue
        row = _LIVE_TEST_ROW_RE.match(line)
        if row and current is not None:
            test_id, step, expected = row.groups()
            if test_id.lower() in ("id", "---"):
                continue
            sections[current].append({"id": test_id, "step": step, "expected": expected})
    return sections


def _matching_section(sections: dict[str, list[dict[str, str]]], mod_id: str | None, mod_name: str | None) -> str | None:
    needles = [n for n in (mod_id, mod_name) if n]
    for heading in sections:
        lowered = heading.lower()
        for needle in needles:
            if needle.lower() in lowered or lowered in needle.lower():
                return heading
    return None


def _live_test_ids_for_features(rows: list[dict[str, str]], features: set[str]) -> list[str]:
    if "scripted" in features:
        return [row["id"] for row in rows]
    ids: list[str] = []
    for row in rows:
        haystack = f"{row['step']} {row['expected']}".lower()
        for feature in features:
            keywords = FEATURE_KEYWORDS.get(feature, [])
            if any(keyword in haystack for keyword in keywords):
                if row["id"] not in ids:
                    ids.append(row["id"])
                break
    return ids


def plan_tests(
    mod_dir: Path,
    since_tag: str | int,
    *,
    manifests_dir: Path | None = None,
    live_test_instructions: Path | None = None,
) -> dict[str, object]:
    """Map changed files since `since_tag` to the minimal tests worth re-running.

    `manifests_dir` defaults to `build_tag.default_manifests_dir()`. `live_test_instructions`
    defaults to `In operation/LIVE_TEST_INSTRUCTIONS.md` relative to the repo root when it exists;
    pass an explicit path (e.g. a temp fixture) to override, or a nonexistent path to skip it.
    """
    root = _find_mod_root(mod_dir)
    tag = _normalize_tag(since_tag)
    mod_id = _mod_id(root)
    mod_name = _mod_name(root)
    manifests_root = Path(manifests_dir).expanduser().resolve() if manifests_dir is not None else default_manifests_dir()
    manifest = _load_manifest(manifests_root, mod_id, root, tag)
    old_hashes = manifest.get("files") or {}
    new_hashes = compute_working_copy_hashes(root)
    diff = _diff_files(old_hashes, new_hashes)
    changed_files = sorted({*diff["added"], *diff["removed"], *diff["modified"]})

    features: set[str] = set()
    unmatched_files: list[str] = []
    file_features: dict[str, list[str]] = {}
    for relative_path in changed_files:
        matched = _features_for_file(relative_path)
        file_features[relative_path] = sorted(matched)
        if matched:
            features.update(matched)
        else:
            unmatched_files.append(relative_path)

    probe_assertions: list[str] = []
    for feature in sorted(features):
        for assertion in FEATURE_PROBE_ASSERTIONS.get(feature, []):
            if assertion not in probe_assertions:
                probe_assertions.append(assertion)

    if live_test_instructions is not None:
        instructions_path = Path(live_test_instructions).expanduser().resolve()
    else:
        default_path = Path(__file__).resolve().parent.parent / "In operation" / DEFAULT_LIVE_TEST_INSTRUCTIONS
        instructions_path = default_path if default_path.is_file() else default_path
    sections = _parse_live_test_instructions(instructions_path)
    section = _matching_section(sections, mod_id, mod_name)
    live_test_ids = _live_test_ids_for_features(sections.get(section, []), features) if section else []

    return {
        "schema_version": 1,
        "mode": "READ_ONLY_TEST_PLAN",
        "mod_dir": str(root),
        "mod_id": mod_id,
        "mod_name": mod_name,
        "since_tag": tag,
        "manifest_build": manifest.get("build"),
        "changed_files": diff,
        "changed_file_count": len(changed_files),
        "file_features": file_features,
        "features": sorted(features),
        "unmatched_files": unmatched_files,
        "probe_assertions": probe_assertions,
        "live_test_section": section,
        "live_test_ids": live_test_ids,
    }
