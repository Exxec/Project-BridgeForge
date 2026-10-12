"""`bridgeforge renamed-ids`: was a missing id renamed in a newer copy of the mod that defined it? (ROADMAP 34.24)

Found by hand on 2026-10-04: Xhan Empire 3.0.1 renamed hull mod `XHAN_targeting_mast` to `XHAN_TargetingMast`
(same name "XhanTech Targeting Mast", same description), so an addon's reference could be remapped; Traverser's
`TDB_chuan_yue_xue_zhe` ("Traverser Scholar") has only `TDB_chuan_yue_XZ` ("Cold Sky Scholar", unmanned, another
system) as a near name, a redesign, so the hull was retired instead. Read-only: it reports candidates, a person or an
approved fixer decides. RENAMED means the same display name and the same description; SIMILAR means only a shared
name word, which is never enough to remap on its own.
"""
from __future__ import annotations

import csv
import io
import re
from pathlib import Path

TABLES = {
    "hull": ("data/hulls/ship_data.csv", ("name", "designation"), ()),
    "weapon": ("data/weapons/weapon_data.csv", ("name",), ()),
    "hullmod": ("data/hullmods/hull_mods.csv", ("name",), ("desc",)),
    "wing": ("data/hulls/wing_data.csv", ("variant",), ()),
}


def _rows(root: Path, kind: str, alternates: bool = False) -> dict[str, dict]:
    """Rows of the kind's table; with `alternates`, also of same-folder copies such as ship_data_old.csv (an author's
    retired rows: Traverser's Scholar survives only there)."""
    main = Path(root) / TABLES[kind][0]
    paths = [main] + (sorted(p for p in main.parent.glob(main.stem + "_*.csv")) if alternates else [])
    rows: dict[str, dict] = {}
    for path in paths:
        if path.is_file():
            text = path.read_text(encoding="utf-8-sig", errors="replace")
            for r in csv.DictReader(io.StringIO(text)):
                if (r.get("id") or "").strip() and not r["id"].startswith("#"):
                    rows.setdefault(r["id"].strip(), r)
    return rows


def _key(row: dict, fields) -> str:
    return " ".join((row.get(f) or "").strip().lower() for f in fields)


def find_renamed(old_root: Path, new_root: Path, ids: list[str]) -> list[dict]:
    """For each `kind:id` missing from `new_root` but defined in `old_root`, the new entries that look like it."""
    results = []
    for item in ids:
        kind, _, ident = item.partition(":")
        if kind not in TABLES:
            results.append({"id": item, "verdict": "UNSUPPORTED_KIND"})
            continue
        old, new = _rows(old_root, kind, alternates=True), _rows(new_root, kind)
        if ident in new:
            results.append({"id": item, "verdict": "STILL_DEFINED"})
            continue
        if ident not in old:
            results.append({"id": item, "verdict": "NOT_IN_OLD_COPY"})
            continue
        _, name_fields, text_fields = TABLES[kind]
        wanted_name, wanted_text = _key(old[ident], name_fields), _key(old[ident], text_fields)
        renamed = [i for i, r in new.items() if wanted_name and _key(r, name_fields) == wanted_name
                   and (not text_fields or _key(r, text_fields) == wanted_text)]
        words = {w for w in re.findall(r"[a-z]{4,}", wanted_name)}
        similar = [i for i, r in new.items() if i not in renamed and words & set(re.findall(r"[a-z]{4,}", _key(r, name_fields)))]
        results.append({"id": item, "old_name": wanted_name,
                        "verdict": "RENAMED" if len(renamed) == 1 else "AMBIGUOUS" if renamed else "SIMILAR" if similar else "NOT_FOUND",
                        "renamed_to": renamed, "similar": [{"id": i, "name": _key(new[i], name_fields)} for i in similar[:5]]})
    return results
