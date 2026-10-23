"""Atlas side of `research report` (82.1, 82.2): reuses atlas.index_mod, the atlas database and atlas_migrations.mine; reads only.

Two uses, kept apart:
  * `tree_concepts`: the Atlas view of one mod tree of the case, extracted in memory with the Atlas's own extractor (nothing is
    written to the database), as concepts for reconciliation.
  * `database_implementers`: which indexed mods (other workspaces, Done/, the rig) carry the feature, from the stored database.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from ..atlas import index_mod
from ..atlas_migrations import Pair, mine
from .research_reconcile import Concept
from .research_terms import Matcher, concept_key

ATLAS_BUILD = "python -m bridgeforge atlas build"
MAX_MODS_LISTED = 25
MAX_EXAMPLES = 3
MAX_CONCEPTS_PER_MOD = 400
KIND_ROLE = {"class": "code-class", "hook": "registration"}


def _role(kind: str) -> str:
    return KIND_ROLE.get(kind, "data-or-string")


def tree_concepts(root: Path, matcher: Matcher) -> dict[str, Concept]:
    """Concepts the Atlas extractor finds in `root` for the feature terms (fact ids, file-term files, string literals)."""
    facts, literals = index_mod(root)
    out: dict[str, Concept] = {}
    for fact in facts:
        terms = matcher.name_hits(fact.id) + [t for t in matcher.file_hits(fact.file) if t not in matcher.name_hits(fact.id)]
        if terms:
            out.setdefault(concept_key(fact.id), Concept()).add(fact.id, _role(fact.kind), fact.kind, f"{fact.file}:{fact.line}" if fact.line else fact.file, terms)
    for file, line, value, _ctx in literals:
        terms = matcher.name_hits(value)
        if terms and len(value) <= 120:
            out.setdefault(concept_key(value), Concept()).add(value, "data-or-string", "literal", f"{file}:{line}" if line else file, terms)
    return {key: concept for key, concept in out.items() if concept.names}


def open_readonly(db: Path) -> sqlite3.Connection:
    """The atlas database opened read-only (`atlas.connect` would create missing tables in it)."""
    conn = sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def database_status(db: Path) -> dict:
    """Input record for the atlas database: PRESENT with the tables it has, or MISSING with the producing command."""
    if not db.is_file():
        return {"name": "atlas-database", "status": "MISSING", "path": str(db), "command": ATLAS_BUILD, "note": "no database: no indexed mod can be compared"}
    conn = open_readonly(db)
    try:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        mods = conn.execute("SELECT COUNT(*) FROM mods").fetchone()[0]
    finally:
        conn.close()
    return {"name": "atlas-database", "status": "PRESENT", "path": str(db), "mods": mods, "tables": sorted(tables),
            "census": "census" in tables,
            "note": "" if "census" in tables else f"no census table (API usage not indexed): rebuild with `{ATLAS_BUILD}`"}


def _like(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_").replace("*", "%")
    return f"%{escaped}%"


def database_implementers(db: Path, matcher: Matcher, exclude_paths: tuple[str, ...] = ()) -> dict:
    """Per indexed mod: facts, literals and API census rows matching the terms, with a few file:line examples."""
    conn = open_readonly(db)
    mods: dict[tuple[str, str], dict] = {}
    try:
        paths = {(r["id"], r["version"]): r["path"] for r in conn.execute("SELECT id, version, path FROM mods")}
        has_census = bool(conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'census'").fetchone())
        for term in matcher.terms:
            pat = _like(term)
            queries = [("fact", "SELECT mod, version, kind AS what, id AS name, file, line FROM facts WHERE lower(id) LIKE lower(?) ESCAPE '\\'", (pat,)),
                       ("literal", "SELECT mod, version, 'literal' AS what, value AS name, file, line FROM literals WHERE lower(value) LIKE lower(?) ESCAPE '\\'", (pat,))]
            if has_census:
                queries.append(("census", "SELECT mod, version, kind AS what, symbol AS name, example AS file, 0 AS line FROM census WHERE area = 'api' AND lower(symbol) LIKE lower(?) ESCAPE '\\'", (pat,)))
            for source, sql, params in queries:
                for row in conn.execute(sql, params):
                    entry = mods.setdefault((row["mod"], row["version"]), {"mod": row["mod"], "version": row["version"], "path": paths.get((row["mod"], row["version"]), ""), "rows": 0, "kinds": {}, "terms": set(), "examples": [], "keys": set()})
                    if len(row["name"]) > 120:
                        continue
                    entry["rows"] += 1
                    entry["keys"].add(concept_key(row["name"]))
                    entry["terms"].add(term)
                    kind = f"{source}:{row['what']}"
                    entry["kinds"][kind] = entry["kinds"].get(kind, 0) + 1
                    place = f"{row['file']}:{row['line']}" if row["line"] else str(row["file"])
                    example = f"{row['name']} @ {place}"
                    if len(entry["examples"]) < MAX_EXAMPLES and example not in entry["examples"]:
                        entry["examples"].append(example)
    finally:
        conn.close()
    skip = {p.lower() for p in exclude_paths}
    listed = [m for m in mods.values() if m["path"].lower() not in skip]
    listed.sort(key=lambda m: (-len(m["terms"]), -m["rows"], m["mod"], m["version"]))
    shown = [{**{k: v for k, v in m.items() if k != "keys"}, "concept_keys": sorted(m["keys"])[:MAX_CONCEPTS_PER_MOD], "terms": sorted(m["terms"]), "kinds": dict(sorted(m["kinds"].items())), "label": "STATIC"} for m in listed[:MAX_MODS_LISTED]]
    return {"mods_with_any": len(listed), "shown": shown}


def case_migrations(old_tree: Path, new_tree: Path, matcher: Matcher) -> dict:
    """atlas_migrations.mine on (old tree, new tree), kept to the rules that mention a feature term. STATIC proposals, never applied."""
    data = mine([Pair(f"{old_tree.name} -> {new_tree.name}", old_tree, new_tree)])
    rules = [r for r in data["rules"] if matcher.any_name(r["old"], r["new"], *r["old_examples"], *r["new_examples"])]
    return {"label": "STATIC", "pairs": data["pairs"], "rules_total": len(data["rules"]), "rules": rules, "api_diff": data["api_diff"]}
