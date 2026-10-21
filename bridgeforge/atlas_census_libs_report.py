"""`atlas libraries` report (ROADMAP-3 81.4): library calls from the census plus declared dependency versions."""
from __future__ import annotations

import sqlite3

from .atlas import latest_mods
from .atlas_census_libs import DECLARED_ID_LIBRARY

LIBRARY_TOP_FUNCTIONS = 10
SPREAD_TOP = 12
NO_VERSION = "(none)"


def _declared_library(dep_id: str, dep_name: str) -> str:
    return DECLARED_ID_LIBRARY.get(dep_id.lower()) or DECLARED_ID_LIBRARY.get(dep_name.lower().replace(" ", "")) or ""


def _collect_library_rows(conn: sqlite3.Connection, latest: set) -> dict[str, dict]:
    libs: dict[str, dict] = {}
    for row in conn.execute("SELECT * FROM census WHERE area = 'lib'"):
        if (row["mod"], row["version"]) not in latest:
            continue
        lib = libs.setdefault(row["kind"], {"library": row["kind"], "mods": {}, "functions": {}, "declared": {}})
        lib["mods"][row["mod"]] = lib["mods"].get(row["mod"], 0) + row["count"]
        fn = lib["functions"].setdefault(row["symbol"], {"symbol": row["symbol"], "mods": [], "example": row["example"]})
        fn["mods"].append(row["mod"])
    return libs


def _collect_dependencies(conn: sqlite3.Connection, latest: set, libs: dict[str, dict]) -> list[dict]:
    dependencies: dict[str, dict] = {}
    for dep in conn.execute("SELECT * FROM census_deps"):
        if (dep["mod"], dep["version"]) not in latest:
            continue
        version = dep["dep_version"] or NO_VERSION
        key = dep["dep_id"] or dep["dep_name"]
        dependencies.setdefault(key, {"dependency": key, "versions": {}})["versions"].setdefault(version, []).append(dep["mod"])
        library = _declared_library(dep["dep_id"], dep["dep_name"])
        if library in libs:
            libs[library]["declared"].setdefault(version, []).append(dep["mod"])
    spreads = list(dependencies.values())
    for spread in spreads:
        spread["mod_count"] = sum(len(mods) for mods in spread["versions"].values())
        spread["versions"] = {v: sorted(mods) for v, mods in sorted(spread["versions"].items())}
    return sorted(spreads, key=lambda d: (-d["mod_count"], d["dependency"]))


def libraries(conn: sqlite3.Connection, top: int = LIBRARY_TOP_FUNCTIONS) -> dict:
    """Per library: mods that call it, its most-used functions, and the dependency versions mods declare for it."""
    latest = {(m["id"], m["version"]) for m in latest_mods(conn)}
    libs = _collect_library_rows(conn, latest)
    spreads = _collect_dependencies(conn, latest, libs)
    out = []
    for lib in libs.values():
        functions = sorted(lib["functions"].values(), key=lambda f: (-len(f["mods"]), f["symbol"]))
        declaring = {m for mods in lib["declared"].values() for m in mods}
        out.append({"library": lib["library"], "mod_count": len(lib["mods"]), "mods": sorted(lib["mods"]),
                    "undeclared_users": sorted(set(lib["mods"]) - declaring) if lib["declared"] else [],
                    "functions": [{"symbol": f["symbol"], "mod_count": len(f["mods"]), "example": f["example"]} for f in functions[:top]],
                    "declared_versions": {v: sorted(m) for v, m in sorted(lib["declared"].items())}})
    out.sort(key=lambda e: (e["library"].startswith("pkg:"), -e["mod_count"], e["library"]))
    return {"label": "STATIC", "libraries": out, "dependencies": spreads,
            "note": "Function lists count classes/files that reference a symbol; a mod bundling a library under its own name is not counted."}


def libraries_text(data: dict, limit: int = SPREAD_TOP) -> str:
    lines = [f"Library census ({data['label']})"]
    for lib in data["libraries"][:limit]:
        lines.append(f"  {lib['library']}: {lib['mod_count']} mod(s) call it")
        for fn in lib["functions"][:5]:
            lines.append(f"      {fn['symbol']}  {fn['mod_count']} mod(s), e.g. {fn['example']}")
        if lib["declared_versions"]:
            lines.append("      declared versions: " + "; ".join(f"{v} x{len(m)}" for v, m in lib["declared_versions"].items()))
        if lib["undeclared_users"]:
            lines.append(f"      call it without declaring it: {', '.join(lib['undeclared_users'][:8])}")
    lines.append("  declared dependencies (mod_info.json):")
    for dep in data["dependencies"][:limit]:
        lines.append(f"      {dep['dependency']}: {dep['mod_count']} mod(s); " + "; ".join(f"{v} x{len(m)}" for v, m in dep["versions"].items()))
    lines.append(f"  {data['note']}")
    return "\n".join(lines)
