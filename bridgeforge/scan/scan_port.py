"""`port-dropped-feature`: what an older version had that the version it was ported onto lacks (ROADMAP item 73 E4, item 72b).

Templars 0.9.8f was ported onto 0.9.9e's RC8 code (2026-10-13): its Holy Crusade ran on the removed 0.8 event system, so
the Crusade's event class, `events.json` entry, `reports.csv` rows and console command were replaced by 0.9.9e's code,
which has no Crusade. Nothing in the workspace said so apart from free text in `SHIPPED_CHANGES.json`, and nothing listed
what was lost. This check lists it. A dropped feature is reported, never restored: a person decides whether it is
re-created (docs/TEMPLAR_CRUSADE_PLAN.md is the worked example; the packet kind `recreation` writes a plan skeleton).

How a port is recorded: `working/reports/PORT_SOURCE.json` (docs/PORT_SOURCE_FORMAT.md):

    {"schema_version": 1, "old_version": "0.9.8f", "onto": "0.9.9e (Kind Stranger)", "date": "2026-10-13",
     "old_tree": "scratch/port-0.9.9e-code/before", "reason": "..."}

`old_tree` is a folder of the OLD version's files (the whole old version, e.g. `original/extracted/Templars`, or just the
files the port replaced, e.g. `scratch/port-0.9.9e-code/before`), relative to the workspace folder (the parent of
`working/`). An absolute path or one that leaves the workspace is refused: the record sits inside a mod and must not
point the scanner at arbitrary folders.

Compared old against current, by category: classes (source files and jar entries, by package), `events.json` ids,
`reports.csv` event type and stage, `settings.json` keys two levels deep (asset maps `graphics` and `sounds` excluded:
`asset-reference-missing` covers those) and `rules.csv` triggers. One finding per category with items present.
"""
from __future__ import annotations

import csv
import re
import zipfile
from pathlib import Path

from ..models import ScanResult
from .scan_classfile import NON_MOD_JAR_DIRS
from .scan_common import MAX_JAR_ENTRIES
from .scan_json import _load_lenient_json_file

PORT_SOURCE_FILE = "reports/PORT_SOURCE.json"
MAX_ITEMS_SHOWN = 60
SETTINGS_SKIPPED_ROOTS = {"graphics", "sounds"}
_PACKAGE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.M)

CATEGORIES = {
    "classes": "classes (by package)",
    "events.json": "`events.json` event ids",
    "reports.csv": "`reports.csv` event type and stage",
    "settings": "`settings.json` keys",
    "rules.csv": "`rules.csv` triggers",
}


def load_port_source(root: Path) -> dict | None:
    """The mod's port record, or None when it has none or it is unreadable."""
    data = _load_lenient_json_file(Path(root) / PORT_SOURCE_FILE)
    return data if isinstance(data, dict) and isinstance(data.get("old_tree"), str) else None


def resolve_old_tree(root: Path, record: dict) -> Path | None:
    """The record's `old_tree` inside the workspace, or None (absolute, outside the workspace, or not a folder).
    A folder holding one mod below it (an `original/` extract) is descended to the folder with `mod_info.json`."""
    value = record["old_tree"].strip()
    if not value or Path(value).is_absolute():
        return None
    workspace = Path(root).resolve().parent
    tree = (workspace / value).resolve()
    if not tree.is_dir() or workspace not in tree.parents:
        return None
    if (tree / "mod_info.json").is_file():
        return tree
    found = sorted(tree.glob("mod_info.json")) or sorted(tree.glob("*/mod_info.json")) or sorted(tree.glob("*/*/mod_info.json"))
    return found[0].parent if found else tree


def _skipped(relative: Path) -> bool:
    return any(part in NON_MOD_JAR_DIRS or part.startswith("src-decompiled") for part in relative.parts)


def _classes(tree: Path) -> set[str]:
    names: set[str] = set()
    for source in tree.rglob("*.java"):
        if _skipped(source.relative_to(tree)):
            continue
        try:
            text = source.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        match = _PACKAGE.search(text)
        names.add((match.group(1) + "." if match else "") + source.stem)
    for jar in tree.rglob("*.jar"):
        if _skipped(jar.relative_to(tree)):
            continue
        try:
            with zipfile.ZipFile(jar) as archive:
                entries = archive.namelist()
        except (OSError, zipfile.BadZipFile):
            continue
        if len(entries) > MAX_JAR_ENTRIES:
            continue
        names.update(e[:-6].replace("/", ".") for e in entries if e.endswith(".class") and "$" not in e and not e.endswith("module-info.class"))
    return names


def _events(tree: Path) -> set[str]:
    data = _load_lenient_json_file(tree / "data/campaign/events.json")
    return {str(key) for key in data} if isinstance(data, dict) else set()


def _rows(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            return list(csv.DictReader(handle))
    except (OSError, csv.Error):
        return []


def _reports(tree: Path) -> set[str]:
    return {f"{row.get('event_type', '').strip()}/{row.get('event_stage', '').strip()}"
            for row in _rows(tree / "data/campaign/reports.csv") if (row.get("event_type") or "").strip()}


def _triggers(tree: Path) -> set[str]:
    return {(row.get("trigger") or "").strip() for row in _rows(tree / "data/campaign/rules.csv") if (row.get("trigger") or "").strip()}


def _settings(tree: Path) -> set[str]:
    data = _load_lenient_json_file(tree / "data/config/settings.json")
    keys: set[str] = set()
    if not isinstance(data, dict):
        return keys
    for key, value in data.items():
        if key in SETTINGS_SKIPPED_ROOTS:
            continue
        if isinstance(value, dict) and value:
            keys.update(f"{key}.{inner}" for inner in value)
        else:
            keys.add(str(key))
    return keys


def describe_tree(tree: Path) -> dict[str, set[str]]:
    return {"classes": _classes(tree), "events.json": _events(tree), "reports.csv": _reports(tree),
            "settings": _settings(tree), "rules.csv": _triggers(tree)}


def dropped_features(old: Path, new: Path) -> dict[str, list[str]]:
    """Per category, what `old` has that `new` lacks (sorted); empty categories are left out."""
    before, after = describe_tree(old), describe_tree(new)
    return {name: sorted(before[name] - after[name]) for name in CATEGORIES if before[name] - after[name]}


def _class_lines(names: list[str]) -> list[str]:
    by_package: dict[str, list[str]] = {}
    for name in names:
        package, _, simple = name.rpartition(".")
        by_package.setdefault(package or "(default package)", []).append(simple)
    return [f"{package}: {', '.join(sorted(simple))}" for package, simple in sorted(by_package.items())]


def _scan_port_dropped_feature(root: Path, result: ScanResult) -> None:
    record = load_port_source(root)
    if record is None:
        return
    old = resolve_old_tree(root, record)
    if old is None or old.resolve() == Path(root).resolve():
        return
    old_version, onto = str(record.get("old_version") or "the older version"), str(record.get("onto") or "the newer code")
    for category, items in dropped_features(old, Path(root)).items():
        lines = _class_lines(items) if category == "classes" else items
        shown = [f"{category}: {line}" for line in lines[:MAX_ITEMS_SHOWN]]
        if len(lines) > MAX_ITEMS_SHOWN:
            shown.append(f"{category}: ... and {len(lines) - MAX_ITEMS_SHOWN} more")
        result.add(
            id="port-dropped-feature", category="campaign", severity="medium", classification="REVIEW", confidence="DETERMINISTIC",
            explanation=(f"This mod was ported: {old_version} was moved onto {onto} (reports/PORT_SOURCE.json). {len(items)} item(s) in "
                         f"{CATEGORIES[category]} exist in the older version and not in this one, so whatever they did is gone. A dropped "
                         "feature is reported, not restored: decide whether it was meant to go (accept it with the reason) or should be "
                         "re-created for RC8 (docs/TEMPLAR_CRUSADE_PLAN.md is a worked example; the packet writes a plan skeleton)."),
            file=PORT_SOURCE_FILE, evidence=shown)
