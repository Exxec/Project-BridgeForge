"""`working/reports/REMOVALS.json`: features a person or tool removed on purpose (ROADMAP item 77.19).

`dropped-features` lists what an older tree had and `working/` lacks. A removal that was decided (a strip plan, a RevenantLib
fold, an upstream deletion, an owner decision, a rename) is recorded here with its reason, so the sweep can tell an explained
drop from a silent one:

    {"schema": 1, "removals": [
      {"category": "rules.csv", "item": "TEMCrusadeNews", "reason": "Crusade removed upstream", "source": "upstream", "date": "2026-10-13"},
      {"category": "classes", "pattern": "data.scripts.old.*", "reason": "...", "source": "strip-plan", "date": "2026-10-13"}]}

`item` is the exact string `scan_port.dropped_features` returns for the category (class name `pkg.Name`, events.json id,
`type/stage`, `section.key`, trigger); `pattern` is a shell glob over the same strings. Exactly one of the two is required, as
are a non-empty `reason`. The file is only ever read by the sweep; the helpers here are for tools that record a removal.

The `files` category (item = path below `working/`, e.g. `data/hulls/raa_dragline.ship`, or a glob over such paths) explains
file-level drops: a file under `data/` the older tree had and `working/` lacks. `remove` (77.27) writes these entries.
"""
from __future__ import annotations

import fnmatch
import json
import re
from datetime import date
from pathlib import Path

from .safeio import atomic_write_json
from bridgeforge.scan.scan_port import CATEGORIES as FEATURE_CATEGORIES

FILES_CATEGORY = "files"
CATEGORIES = {**FEATURE_CATEGORIES, FILES_CATEGORY: "files under `data/`"}

REMOVALS_FILE = "reports/REMOVALS.json"
SCHEMA = 1
SOURCES = ("strip-plan", "revenantlib-fold", "upstream", "owner", "renamed")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class RemovalsError(ValueError):
    """REMOVALS.json is unreadable or an entry is invalid."""


def validate_entry(entry: object, where: str = "entry") -> dict:
    """A normalised copy of `entry`, or RemovalsError naming what is wrong."""
    if not isinstance(entry, dict):
        raise RemovalsError(f"{where}: not an object")
    category = entry.get("category")
    if category not in CATEGORIES:
        raise RemovalsError(f"{where}: unknown category {category!r} (one of {', '.join(CATEGORIES)})")
    item, pattern = entry.get("item"), entry.get("pattern")
    if (item is None) == (pattern is None):
        raise RemovalsError(f"{where}: give exactly one of `item` and `pattern`")
    target = item if item is not None else pattern
    if not isinstance(target, str) or not target.strip():
        raise RemovalsError(f"{where}: `item`/`pattern` must be a non-empty string")
    reason = entry.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise RemovalsError(f"{where}: `reason` is required")
    source = entry.get("source")
    if source not in SOURCES:
        raise RemovalsError(f"{where}: `source` must be one of {', '.join(SOURCES)}, got {source!r}")
    when = entry.get("date")
    if not isinstance(when, str) or not _DATE.match(when):
        raise RemovalsError(f"{where}: `date` must be YYYY-MM-DD")
    key = "item" if item is not None else "pattern"
    return {"category": category, key: target.strip(), "reason": reason.strip(), "source": source, "date": when}


def load_removals(working: Path) -> list[dict]:
    """The workspace's validated removals (empty when it has no file). Raises RemovalsError when the file is invalid."""
    path = Path(working) / REMOVALS_FILE
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise RemovalsError(f"{REMOVALS_FILE}: unreadable ({exc})") from exc
    if not isinstance(data, dict) or data.get("schema") != SCHEMA or not isinstance(data.get("removals"), list):
        raise RemovalsError(f'{REMOVALS_FILE}: expected {{"schema": {SCHEMA}, "removals": [...]}}')
    return [validate_entry(entry, f"{REMOVALS_FILE} removals[{index}]") for index, entry in enumerate(data["removals"])]


def covers(removal: dict, category: str, item: str) -> bool:
    if removal["category"] != category:
        return False
    if "item" in removal:
        return removal["item"] == item
    return fnmatch.fnmatchcase(item, removal["pattern"])


def split_explained(dropped: dict[str, list[str]], removals: list[dict]) -> dict[str, dict[str, list[str]]]:
    """Per category `{"unexplained": [...], "explained": [...]}` for the items `dropped_features` returned."""
    result: dict[str, dict[str, list[str]]] = {}
    for category, items in dropped.items():
        explained = [i for i in items if any(covers(r, category, i) for r in removals)]
        result[category] = {"unexplained": [i for i in items if i not in set(explained)], "explained": explained}
    return result


def add_removals(working: Path, entries: list[dict]) -> Path:
    """Record `entries` (validated; duplicates of an existing entry skipped) in the workspace's REMOVALS.json."""
    existing = load_removals(working)
    merged = list(existing)
    for entry in entries:
        clean = validate_entry(entry)
        if clean not in merged:
            merged.append(clean)
    return atomic_write_json(Path(working) / REMOVALS_FILE, {"schema": SCHEMA, "removals": merged}, indent=2, ensure_ascii=False)


def make_entry(category: str, *, reason: str, source: str, item: str | None = None, pattern: str | None = None,
               when: str | None = None) -> dict:
    entry = {"category": category, "reason": reason, "source": source, "date": when or date.today().isoformat()}
    if item is not None:
        entry["item"] = item
    if pattern is not None:
        entry["pattern"] = pattern
    return validate_entry(entry)
