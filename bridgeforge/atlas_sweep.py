"""Mod Atlas sweeps (ROADMAP item 67, phases 4 and 6): a modpack as one load set, and every indexed mod against a family.

- `read_pack`: an enabled_mods.json (or a list of ids) becomes the load set to forecast; ids the index does not hold are reported,
  never guessed. Run it before anyone loads a save with that pack (the friend's 6.3 pack: 577 ids).
- `sweep`: forecast every indexed mod against a family (`aotd`) one by one and tabulate verdicts, so a mod's compatibility with
  the whole family is known before it is tested. One progress line per mod and a checkpoint, as every long-running command.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from .atlas import VANILLA_ID, AtlasError, group_mods, latest_mods
from .atlas_rules import forecast
from .progress import Checkpoint, report


def read_pack(conn: sqlite3.Connection, path: Path) -> tuple[list[dict], list[str]]:
    """(indexed mods the pack enables, ids the index does not hold). Matches by exact mod id, case-insensitively."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AtlasError(f"cannot read the pack file {path}: {exc}") from exc
    ids = data.get("enabledMods") if isinstance(data, dict) else data
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        raise AtlasError(f"{path} is not an enabled_mods.json (expected {{\"enabledMods\": [ids]}} or a list of ids)")
    by_id = {m["id"].lower(): m for m in latest_mods(conn)}
    found: list[dict] = []
    missing: list[str] = []
    for mod_id in dict.fromkeys(i.strip() for i in ids):
        mod = by_id.get(mod_id.lower())
        if mod is None:
            missing.append(mod_id)
        elif mod["id"] != VANILLA_ID and mod not in found:
            found.append(mod)
    return found, missing


def sweep(conn: sqlite3.Connection, group: str, checkpoint_path: Path | None = None, quiet: bool = False,
          limit: int | None = None) -> dict:
    """Forecast each indexed mod outside `group` against the group; {"group": [...], "rows": [{mod, status, findings, rules}]}."""
    family = group_mods(conn, group)
    if not family:
        raise AtlasError(f"no indexed mod belongs to group {group!r}")
    family_ids = {m["id"] for m in family}
    subjects = [m for m in latest_mods(conn) if m["id"] != VANILLA_ID and m["id"] not in family_ids]
    subjects = subjects[: limit or None]
    header = {"command": "atlas sweep", "group": group, "family": sorted(family_ids), "subjects": [m["id"] for m in subjects]}
    rows: list[dict] = []
    with Checkpoint(checkpoint_path, header) as saved:
        for index, mod in enumerate(subjects, 1):
            row = saved.get(mod["id"])
            started = time.monotonic()
            if row is None:
                result = forecast(conn, [mod], family)
                verdict = result["verdicts"][mod["id"]]
                row = {"mod": mod["id"], "name": mod["name"], "status": verdict["status"], "findings": verdict["findings"],
                       "rules": sorted({f.rule for f in result["findings"]}),
                       "ids": sorted({i for f in result["findings"] for i in f.ids})[:12]}
                saved.add(mod["id"], row)
                seconds = time.monotonic() - started
            else:
                seconds = None
            rows.append(row)
            if not quiet:
                report(index, len(subjects), mod["id"], f"{row['status']} ({row['findings']})", seconds)
        saved.finish()
    return {"group": group, "family": sorted(family_ids), "rows": rows,
            "summary": _summary(rows)}


def _summary(rows: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for row in rows:
        key = "REVIEW or worse" if row["findings"] else row["status"].split(" (")[0]
        counts[key] = counts.get(key, 0) + 1
    return counts


def sweep_text(data: dict) -> str:
    flagged = [r for r in data["rows"] if r["findings"]]
    lines = [f"Sweep against {data['group']} ({len(data['family'])} mod(s)): {len(data['rows'])} mod(s) checked; "
             + ", ".join(f"{n} {k}" for k, n in sorted(data["summary"].items()))]
    for row in sorted(flagged, key=lambda r: (-r["findings"], r["mod"])):
        lines.append(f"  {row['mod']}: {row['findings']} finding(s) [{', '.join(row['rules'])}] ids: {', '.join(row['ids'])}")
    if not flagged:
        lines.append("  no mod has a static conflict with the family")
    return "\n".join(lines)
