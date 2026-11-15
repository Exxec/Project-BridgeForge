"""Same signature, other meaning: parameter renames between two game API source bundles (ROADMAP-3 item 89, 2026-11-15).

`api-diff` compares class files, so a method whose descriptor survived is "unchanged" to it. 0.98.5a-RC3 kept
`Misc.getOfficerSalary(PersonAPI, boolean)` but its boolean went from `mercenary` to `checkIfInPopulatedSystem`: an RC8
call compiles, links and silently computes something else. It was found by comparing parameter names in the two
`starfarer.api.zip` source bundles the game ships beside `starfarer.api.jar`; this does that for every public or protected
method. A renamed parameter is a lead, not proof (a rename can be cosmetic), so findings built on it are REVIEW.
"""
from __future__ import annotations

import re
import zipfile
from functools import lru_cache
from pathlib import Path

from .zipsafe import read_limited

SOURCE_ZIP = "starfarer.api.zip"
_DECL = re.compile(r"(?:public|protected)\s+(?:static\s+|final\s+|abstract\s+|synchronized\s+|default\s+)*"
                   r"(?:<[^>]+>\s+)?[\w.<>\[\], ?]+?\s+(\w+)\s*\(([^)]*)\)\s*(?:throws [\w., ]+)?\s*[{;]")


def _params(text: str) -> list[tuple[str, str]]:
    parts, depth, current = [], 0, ""
    for char in text:
        depth += char == "<"
        depth -= char == ">"
        if char == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += char
    if current.strip():
        parts.append(current)
    result = []
    for part in parts:
        part = re.sub(r"@\w+\s*", "", part).replace("final ", "").strip()
        bits = part.rsplit(None, 1)
        if len(bits) == 2:
            result.append((re.sub(r"<.*>", "", re.sub(r"\s+", "", bits[0])), bits[1]))
    return result


def _declarations(zip_path: Path) -> dict[tuple[str, str, tuple[str, ...]], tuple[str, ...]]:
    """{(dotted class, method, parameter types): parameter names} for every public/protected method in a source zip."""
    found: dict[tuple[str, str, tuple[str, ...]], tuple[str, ...]] = {}
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            if not info.filename.endswith(".java"):
                continue
            text = read_limited(archive, info).decode("utf-8", "replace")
            text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
            text = re.sub(r"//[^\n]*", "", text)
            owner = info.filename[:-5].replace("/", ".")
            for match in _DECL.finditer(text):
                params = _params(match.group(2))
                if params:
                    found.setdefault((owner, match.group(1), tuple(t for t, _ in params)), tuple(n for _, n in params))
    return found


@lru_cache(maxsize=4)
def parameter_renames(old_zip: str, new_zip: str) -> tuple[dict, ...]:
    """One record per method present in both bundles with the same parameter types and at least one renamed parameter."""
    old, new = _declarations(Path(old_zip)), _declarations(Path(new_zip))
    records = []
    for key in sorted(old.keys() & new.keys()):
        if old[key] == new[key]:
            continue
        owner, method, types = key
        records.append({"class": owner, "method": method, "types": list(types),
                        "renamed": [{"type": t, "old": a, "new": b} for t, a, b in zip(types, old[key], new[key]) if a != b]})
    return tuple(records)


def source_zip_beside(api_jar_or_core: Path) -> Path | None:
    path = Path(api_jar_or_core)
    folder = path if path.is_dir() else path.parent
    candidate = folder / SOURCE_ZIP
    return candidate if candidate.is_file() else None


def render_rename(record: dict) -> str:
    changes = "; ".join(f"{r['type']} {r['old']} -> {r['new']}" for r in record["renamed"])
    return f"{record['class']}.{record['method']}({', '.join(record['types'])}): {changes}"
