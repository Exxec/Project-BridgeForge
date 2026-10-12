"""Industry ids a mod's code asks for that no installed table defines, but one close to them does (ROADMAP 60d).

Found when Tritachyon asked for BOGGLED_AI_STATION and Terraforming & Station Construction 10.0.9 calls it
BOGGLED_REMNANT_STATION: New Game stopped in onNewGame. Scope is industry ids only, read from string constants in
classes and loose scripts that call an industry API method; hull mod, commodity and condition ids are not covered.
"""
from __future__ import annotations

import csv
import difflib
import re
import zipfile
from pathlib import Path

from .jar_audit import ClassFileError, parse_constant_pool

INDUSTRY_API_NAMES = frozenset({"addIndustry", "hasIndustry", "getIndustry", "removeIndustry", "isIndustry", "getIndustrySpec"})
_ID_SHAPE = re.compile(r"^[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+$")
_LITERAL = re.compile(r'"([A-Za-z][A-Za-z0-9_]{5,})"')
MIN_RATIO = 0.75


def industry_ids_in_csv(path: Path) -> set[str]:
    try:
        with path.open(encoding="utf-8", errors="replace", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except OSError:
        return set()
    return {(row.get("id") or "").strip() for row in rows if (row.get("id") or "").strip() and not (row.get("id") or "").startswith("#")}


def _ids_from(table: str, vanilla_core: Path | None, own_root: Path, provider_dirs: list[Path]) -> set[str]:
    ids: set[str] = set()
    for folder in ([vanilla_core] if vanilla_core else []) + [own_root] + list(provider_dirs):
        ids |= industry_ids_in_csv(Path(folder) / "data" / "campaign" / table)
    return ids


def known_industry_ids(vanilla_core: Path | None, own_root: Path, provider_dirs: list[Path]) -> set[str]:
    return _ids_from("industries.csv", vanilla_core, own_root, provider_dirs)


def used_industry_ids(root: Path) -> dict[str, list[str]]:
    """Candidate id -> where it was found, from industry-API classes in jars and loose .java files."""
    used: dict[str, list[str]] = {}
    for source in root.rglob("*.java"):
        try:
            text = source.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not any(name in text for name in INDUSTRY_API_NAMES):
            continue
        for literal in set(_LITERAL.findall(text)):
            if _ID_SHAPE.match(literal):
                used.setdefault(literal, []).append(str(source.relative_to(root)).replace("\\", "/"))
    for jar in root.rglob("*.jar"):
        try:
            with zipfile.ZipFile(jar) as archive:
                for item in archive.infolist():
                    if not item.filename.endswith(".class"):
                        continue
                    try:
                        pool = parse_constant_pool(archive.read(item))
                    except (ClassFileError, OSError, zipfile.BadZipFile):
                        continue
                    utf8 = {i: e[1] for i, e in enumerate(pool) if e is not None and e[0] == 1}
                    if not INDUSTRY_API_NAMES.intersection(utf8.values()):
                        continue
                    for entry in pool:
                        if entry is not None and entry[0] == 8 and entry[1] in utf8:
                            literal = utf8[entry[1]]
                            if len(literal) > 5 and _ID_SHAPE.match(literal):
                                used.setdefault(literal, []).append(f"{jar.name}!{item.filename}")
        except (OSError, zipfile.BadZipFile):
            continue
    return used


def closest_known(candidate: str, known: set[str]) -> tuple[str, float] | None:
    """The known id most like the candidate that shares its first token (BOGGLED_...), if close enough."""
    head = candidate.split("_", 1)[0].lower()
    best: tuple[str, float] | None = None
    for other in known:
        if other.split("_", 1)[0].lower() != head:
            continue
        ratio = difflib.SequenceMatcher(None, candidate, other).ratio()
        if ratio >= MIN_RATIO and (best is None or ratio > best[1]):
            best = (other, ratio)
    return best


def renamed_industry_ids(root: Path, vanilla_core: Path | None, provider_dirs: list[Path]) -> list[dict]:
    """[{used, suggestion, ratio, where}] for each used id absent from every table that has a close sibling."""
    known = known_industry_ids(vanilla_core, root, provider_dirs)
    # Suggestions come only from a declared provider's own table: a vanilla-only match was pure noise in a sweep of 312
    # workspaces (station_side05 -> station_base, an entity id beside an industry call).
    provider_only = _ids_from("industries.csv", None, Path(root) / "_none_", provider_dirs) - known_industry_ids(vanilla_core, root, [])
    if not provider_only:
        return []
    # Market conditions share the add* call sites in these classes (population_5 beside population): not industries.
    conditions = _ids_from("market_conditions.csv", vanilla_core, root, provider_dirs)
    out = []
    for candidate, where in sorted(used_industry_ids(root).items()):
        if candidate in known or candidate in conditions or re.search(r"_\d+$", candidate):
            continue
        near = closest_known(candidate, provider_only)
        if near:
            out.append({"used": candidate, "suggestion": near[0], "ratio": round(near[1], 2), "where": sorted(set(where))[:3]})
    return out
