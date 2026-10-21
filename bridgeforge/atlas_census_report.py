"""Reports over the atlas census tables (ROADMAP-3 item 81): `atlas api-usage`, and the lookup behind `api how`.

All numbers are STATIC: they count classes/files that mention a symbol (constant-pool entries and loose-script regexes),
not how often it runs. A symbol seen in a mod's code may be dead code; a mod can also bundle a library under its own name.
"""
from __future__ import annotations

import sqlite3

from .atlas import ORIGINAL_SUFFIX, latest_mods

DEFAULT_EXAMPLES = 3


def _latest_filter(conn: sqlite3.Connection) -> set[tuple[str, str]]:
    return {(m["id"], m["version"]) for m in latest_mods(conn)}


def census_rows(conn: sqlite3.Connection, area: str, symbol_prefix: str = "", exact: bool = False) -> list[dict]:
    """Census rows of the latest version of every mod whose symbol starts with (or equals) `symbol_prefix`."""
    latest = _latest_filter(conn)
    if exact:
        cursor = conn.execute("SELECT * FROM census WHERE area = ? AND symbol = ?", (area, symbol_prefix))
    else:
        cursor = conn.execute("SELECT * FROM census WHERE area = ? AND symbol LIKE ? ESCAPE '\\'",
                              (area, symbol_prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"))
    return [dict(r) for r in cursor if (r["mod"], r["version"]) in latest and not r["version"].endswith(ORIGINAL_SUFFIX)]


def api_usage(conn: sqlite3.Connection, prefix: str, limit: int = 25) -> dict:
    """Which mods use every API symbol starting with `prefix` (a class, a member or a package), how widely, with an example."""
    by_symbol: dict[str, dict] = {}
    for row in census_rows(conn, "api", prefix):
        entry = by_symbol.setdefault(row["symbol"], {"symbol": row["symbol"], "kind": row["kind"], "mods": [], "total": 0})
        entry["mods"].append({"mod": row["mod"], "count": row["count"], "example": row["example"]})
        entry["total"] += row["count"]
    symbols = sorted(by_symbol.values(), key=lambda e: (-len(e["mods"]), -e["total"], e["symbol"]))
    for entry in symbols:
        entry["mods"].sort(key=lambda m: (-m["count"], m["mod"]))
        entry["mod_count"] = len(entry["mods"])
    return {"prefix": prefix, "symbols": len(symbols), "shown": symbols[:limit], "label": "STATIC"}


def api_usage_text(data: dict, examples: int = DEFAULT_EXAMPLES) -> str:
    lines = [f"API usage for {data['prefix']!r} (STATIC): {data['symbols']} symbol(s), showing {len(data['shown'])}"]
    for entry in data["shown"]:
        lines.append(f"  {entry['symbol']} [{entry['kind']}]: {entry['mod_count']} mod(s), {entry['total']} class/file ref(s)")
        for mod in entry["mods"][:examples]:
            lines.append(f"      {mod['mod']} x{mod['count']}  e.g. {mod['example']}")
        if len(entry["mods"]) > examples:
            lines.append(f"      ... and {len(entry['mods']) - examples} more mod(s)")
    if not data["shown"]:
        lines.append("  no mod uses a symbol with that prefix (use the full dotted name, e.g. com.fs.starfarer.api.campaign.SectorAPI)")
    return "\n".join(lines)


# ---------------------------------------------------------------- api how

def _split_symbol(old_symbol: str) -> tuple[str, str]:
    """`SectorAPI.addMessage` -> ('SectorAPI', 'addMessage'); a bare class name -> (name, '')."""
    parts = old_symbol.strip().rstrip("()").split(".")
    if len(parts) >= 2 and (parts[-1][:1].islower() or parts[-1].isupper()):
        return ".".join(parts[:-1]), parts[-1]
    return ".".join(parts), ""


def _matches_class(dotted: str, wanted: str) -> bool:
    return dotted == wanted or dotted.endswith("." + wanted)


def _owner_of(rendered: str) -> tuple[str, str]:
    """`pkg.Cls.name(args)` or `pkg.Cls.void name(..)` style entries -> (owner, member name)."""
    head = rendered.split("(", 1)[0]
    words = head.split(" ")
    qualified = words[0] if "." in words[0] and len(words) == 1 else head
    if len(words) > 1:  # "void name": no owner in the text
        return "", words[-1]
    owner, _, name = qualified.rpartition(".")
    return owner, name


def removed_entries(catalogue: dict, owner: str, member: str) -> list[dict]:
    """The api-diff entries for the removed class/method/field, plus candidate (owner, name) pairs that may replace it."""
    found = []
    for cls in catalogue.get("removed_classes", []):
        if not member and _matches_class(cls["class"], owner):
            found.append({"removed": cls["class"], "kind": "class",
                          "candidates": [(c, "") for c in cls.get("same_name_elsewhere", [])]})
    for dotted, entry in catalogue.get("changed_classes", {}).items():
        if not _matches_class(dotted, owner) or not member:
            continue
        for key, kind in (("methods_removed", "method"), ("fields_removed", "field")):
            for item in entry[key]:
                if item["name"] != member:
                    continue
                candidates = [(dotted, member)] if item.get("same_name_in_class") else []
                candidates += [_owner_of(text) for text in item.get("same_signature_elsewhere", [])]
                found.append({"removed": f"{dotted}.{item['signature']}", "kind": kind, "class": dotted, "candidates": candidates,
                              "in_class": item.get("same_name_in_class", []), "elsewhere": item.get("same_signature_elsewhere", [])})
    return found


def moved_by_name(catalogue: dict, member: str, exclude: set[tuple[str, str]]) -> list[tuple[str, str]]:
    """Other API classes whose newly added methods carry the same name (a move with a changed signature)."""
    out = []
    for dotted, entry in catalogue.get("changed_classes", {}).items():
        if any(text.split("(", 1)[0].split(" ")[-1] == member for text in entry.get("methods_added", [])) and (dotted, member) not in exclude:
            out.append((dotted, member))
    return out


def api_how(conn: sqlite3.Connection, catalogue: dict, old_symbol: str, limit_examples: int = DEFAULT_EXAMPLES) -> dict:
    owner, member = _split_symbol(old_symbol)
    entries = removed_entries(catalogue, owner, member)
    result = {"symbol": old_symbol, "label": "STATIC", "removed": [], "note": catalogue.get("note", "")}
    for entry in entries:
        seen = set(entry["candidates"])
        candidates = list(entry["candidates"])
        if member:
            candidates += moved_by_name(catalogue, member, seen)
        rows = []
        for cand_owner, cand_name in dict.fromkeys(c for c in candidates if c[0] or c[1]):
            symbol = f"{cand_owner}.{cand_name}" if cand_name and cand_owner else (cand_owner or cand_name)
            users = census_rows(conn, "api", symbol, exact=True)
            users.sort(key=lambda r: (-r["count"], r["mod"]))
            rows.append({"candidate": symbol, "mod_count": len(users),
                         "mods": [{"mod": u["mod"], "count": u["count"], "example": u["example"]} for u in users[:limit_examples]]})
        old_users = census_rows(conn, "api", f"{entry['class']}.{member}" if member else entry["removed"], exact=True) if member else []
        entry_out = {k: entry[k] for k in ("removed", "kind")}
        entry_out.update(candidates=rows, still_referenced_by=[u["mod"] for u in old_users])
        result["removed"].append(entry_out)
    return result


def api_how_text(data: dict) -> str:
    lines = [f"api how {data['symbol']} (STATIC)"]
    if not data["removed"]:
        lines.append("  api-diff lists no removed class/method/field by that name (check the spelling, or it is unchanged)")
    for entry in data["removed"]:
        lines.append(f"  removed: {entry['removed']}")
        if entry["still_referenced_by"]:
            lines.append(f"    still referenced by: {', '.join(entry['still_referenced_by'][:10])}")
        for cand in entry["candidates"]:
            lines.append(f"    candidate {cand['candidate']}: used by {cand['mod_count']} mod(s)")
            for mod in cand["mods"]:
                lines.append(f"        {mod['mod']} x{mod['count']}  e.g. {mod['example']}")
        if not entry["candidates"]:
            lines.append("    no same-name candidate in the new API")
    lines.append(f"  {data['note']}")
    return "\n".join(lines)


def run_census_cli(args, conn: sqlite3.Connection, emit) -> None:
    if args.atlas_command == "api-usage":
        data = api_usage(conn, args.symbol, args.limit)
        emit(args, data, api_usage_text(data, args.examples))
