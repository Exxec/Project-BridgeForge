"""Checks for total conversions that replace RC8's hull list (found on Ironclads, GRP10B-GRP10F, 2026-10-05).

RC8 loads every vanilla faction next to the mod's. A faction file names variants in `shipRoles` and `variantOverrides`
(`"gremlin_Strike":10`), and the loader prices each one at startup: a variant whose hull the mod's replaced
`ship_data.csv` removed is a Fatal "Ship hull variant [gremlin_Strike] not found!" (Hegemony, Luddic Church, Remnants,
Derelict) or a NullPointerException on `getHullSpec()` (Lions Guard, Luddic Path, Persean League, Sindrian Diktat).
A mod file cannot remove entries from a vanilla faction, because faction files merge; the mod must *replace* the file
(`mod_info.json` `replace`) with a copy that lacks those lines. The fixer writes those copies from the vanilla core.
"""
from __future__ import annotations

import csv
import io
import re
from pathlib import Path

from .scanner import ScanResult, _load_lenient_json_file, _relative

REPLACED_HULLS = "data/hulls/ship_data.csv"
FACTION_DIR = Path("data") / "world" / "factions"
# What a hiding stub may hold and still be carried into the replaced copy (Ironclads' hegemony.faction).
_STUB_KEYS = {"showInIntelTab"}


def replace_list(root: Path) -> set[str]:
    info = _load_lenient_json_file(Path(root) / "mod_info.json")
    entries = info.get("replace") if isinstance(info, dict) else None
    return {str(item).replace("\\", "/").lower() for item in entries or [] if isinstance(item, str)}


def _csv_ids(path: Path) -> set[str]:
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return set()
    return {(row.get("id") or "").strip() for row in csv.DictReader(io.StringIO(text)) if (row.get("id") or "").strip()}


def _variant_hulls(*roots: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    for base in roots:
        for path in (Path(base) / "data" / "variants").rglob("*.variant"):
            data = _load_lenient_json_file(path)
            if isinstance(data, dict) and isinstance(data.get("variantId"), str) and isinstance(data.get("hullId"), str):
                found[data["variantId"]] = data["hullId"]
    return found


def _referenced_ids(node) -> set[str]:
    out: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            out.add(key)
            out |= _referenced_ids(value)
    elif isinstance(node, list):
        for value in node:
            out |= _referenced_ids(value)
    elif isinstance(node, str):
        out.add(node)
    return out


def _faction_source(root: Path, vanilla_file: Path, replaced: set[str]) -> Path:
    relative = (FACTION_DIR / vanilla_file.name).as_posix()
    mine = Path(root) / FACTION_DIR / vanilla_file.name
    return mine if relative.lower() in replaced and mine.is_file() else vanilla_file


def factions_naming_removed_hulls(root: Path, vanilla_core: Path | None) -> dict[str, list[str]]:
    """{faction file name: variant ids it names whose hull the mod's replaced ship_data.csv removed}. Empty unless the
    mod replaces data/hulls/ship_data.csv."""
    root = Path(root)
    replaced = replace_list(root)
    if vanilla_core is None or REPLACED_HULLS not in replaced:
        return {}
    core_data = Path(vanilla_core) / "data"
    hulls = _csv_ids(root / REPLACED_HULLS)
    variant_hull = _variant_hulls(Path(vanilla_core), root)
    result: dict[str, list[str]] = {}
    for vanilla_file in sorted((core_data / "world" / "factions").glob("*.faction")):
        source = _faction_source(root, vanilla_file, replaced)
        data = _load_lenient_json_file(source)
        if not isinstance(data, dict):
            continue
        bad = sorted(v for v in _referenced_ids(data) if v in variant_hull and variant_hull[v] not in hulls)
        if bad:
            result[vanilla_file.name] = bad
    return result


def scan_factions_naming_removed_hulls(root: Path, result: ScanResult, vanilla_core: Path | None) -> None:
    hits = factions_naming_removed_hulls(root, vanilla_core)
    if not hits:
        return
    result.add(
        id="conversion-faction-names-removed-hull",
        category="content",
        severity="high",
        classification="REVIEW",
        confidence="DETERMINISTIC",
        explanation="This mod replaces data/hulls/ship_data.csv, but "
                    + ", ".join(sorted(hits)) + " name variants whose hulls it removed. RC8 prices every variant a faction names "
                    "at startup and stops (Fatal 'Ship hull variant ... not found' or a NullPointerException). Faction files merge, "
                    "so the mod must replace each file with a copy lacking those lines; `fix` writes them from --vanilla-core.",
        file="mod_info.json",
        evidence=[f"{name}:{','.join(variants[:6])}" for name, variants in sorted(hits.items())],
    )


def factions_csv_relists_neutral(root: Path, vanilla_core: Path | None) -> bool:
    """The mod's factions.csv lists vanilla's neutral.faction again. Ironclads GRP10D-20261005 (neutral, player, pirates and
    independent relisted) loaded hegemony first and died with a NullPointerException in the Faction class (its hard-coded
    `neutral` had no spec yet); GRP10E, with the four rows removed, loaded neutral and player first. It is not a rule: Vacuum
    relists neutral last and passed its live tests (2026-09-08, isolated runtime), so this is a REVIEW pointer, not a fault."""
    if vanilla_core is None:
        return False
    listing = Path(root) / FACTION_DIR / "factions.csv"
    vanilla_listing = Path(vanilla_core) / "data" / "world" / "factions" / "factions.csv"
    if not listing.is_file() or not vanilla_listing.is_file():
        return False
    wanted = (FACTION_DIR / "neutral.faction").as_posix().lower()

    def rows(path: Path) -> list[str]:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        return [line.split(",")[0].strip().strip('"').replace("\\", "/").lower() for line in text.splitlines()[1:] if line.strip()]

    return wanted in rows(listing) and wanted in rows(vanilla_listing)


def scan_factions_csv_relists_neutral(root: Path, result: ScanResult, vanilla_core: Path | None) -> None:
    if factions_csv_relists_neutral(root, vanilla_core):
        result.add(
            id="factions-csv-relists-neutral",
            category="content",
            severity="medium",
            classification="REVIEW",
            confidence="MEDIUM",
            explanation="factions.csv lists neutral.faction again, which vanilla's list already starts with. In Ironclads this moved neutral "
                        "behind other factions and RC8 stopped at startup (NullPointerException in the Faction class, GRP10D-20261005), and "
                        "removing the row fixed it. Vacuum lists it last and ran fine, so it is a pointer: if the log shows 'Faction' "
                        "initialisation failing before neutral loads, `fix` removes the row (a mod file at that path still replaces vanilla's).",
            file=_relative(Path(root), listing_path(root)),
            evidence=["row:data/world/factions/neutral.faction"],
        )


def listing_path(root: Path) -> Path:
    return Path(root) / FACTION_DIR / "factions.csv"


def remove_neutral_row(raw: bytes) -> bytes:
    newline = b"\r\n" if b"\r\n" in raw else b"\n"
    lines = raw.split(newline)
    kept = [line for line in lines if line.strip().strip(b'"').replace(b"\\", b"/").lower().split(b",")[0] != b"data/world/factions/neutral.faction"]
    return newline.join(kept)


def faction_copy_without(source: bytes, variants: list[str], header: list[str], hidden_stub_value: bool | None) -> bytes:
    """Vanilla's file with the lines naming `variants` removed (each must sit alone on its line, as vanilla writes
    them) and a comment header. `hidden_stub_value` carries a showInIntelTab stub's value; None adds nothing."""
    newline = b"\r\n" if b"\r\n" in source else b"\n"
    lines = source.split(newline)
    entry = re.compile(rb'^\s*"([^"]+)"\s*:\s*[-\d.]+\s*,?\s*(?:#.*)?$')
    drop = [i for i, line in enumerate(lines) if (m := entry.match(line)) and m.group(1).decode() in variants]
    if {entry.match(lines[i]).group(1).decode() for i in drop} != set(variants):
        raise ValueError("a variant is not on a line of its own")
    kept = [line for i, line in enumerate(lines) if i not in set(drop)]
    insert_at = next(i for i, line in enumerate(kept) if line.strip().startswith(b"{")) + 1
    added = [("# " + text).encode("utf-8") for text in header]
    flag = b"showInIntelTab"
    existing = [i for i, line in enumerate(kept) if re.match(rb'^\s*"showInIntelTab"\s*:', line)]
    if hidden_stub_value is not None:
        value = b"true" if hidden_stub_value else b"false"
        if existing:
            indent = re.match(rb"^\s*", kept[existing[0]]).group(0)
            kept[existing[0]] = indent + b'"' + flag + b'":' + value + b","
        else:
            added.append(b'\t"' + flag + b'":' + value + b",")
    kept[insert_at:insert_at] = added
    return newline.join(kept)


def stub_value(root: Path, name: str) -> tuple[bool, bool | None]:
    """(usable, showInIntelTab value) for the mod's own overlay of a vanilla faction file: absent -> (True, None);
    a stub holding only showInIntelTab -> (True, value); anything else -> (False, None) for the owner."""
    mine = Path(root) / FACTION_DIR / name
    if not mine.is_file():
        return True, None
    data = _load_lenient_json_file(mine)
    if isinstance(data, dict) and set(data) <= _STUB_KEYS:
        value = data.get("showInIntelTab")
        return True, value if isinstance(value, bool) else None
    return False, None


def add_replace_entries(text: str, entries: list[str]) -> str:
    """Append `entries` to mod_info.json's replace array, keeping the file's own text."""
    match = re.search(r'"replace"\s*:\s*\[', text)
    if match is None:
        raise ValueError("no replace array")
    depth, i, quote = 1, match.end(), ""
    while i < len(text) and depth:
        c = text[i]
        if quote:
            if c == "\\":
                i += 1
            elif c == quote:
                quote = ""
        elif c in "\"'":
            quote = c
        elif c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
        i += 1
    close = i - 1
    body = text[match.end():close]
    existing = {e.lower() for e in re.findall(r'"([^"]+)"', body)}
    new = [e for e in entries if e.lower() not in existing]
    if not new:
        return text
    separator = "" if not body.strip() or body.rstrip().endswith(",") else ","
    block = separator + "\n" + "\n".join(f'"{e}",' for e in new) + "\n"
    return text[:close].rstrip() + block + text[close:]
