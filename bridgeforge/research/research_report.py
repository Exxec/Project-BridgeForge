"""`research report FEATURE --case WORKSPACE --question TEXT` (ROADMAP-3 82.1, 82.2): the comparative research report, read-only.

Collects, for one case workspace, what its trees contain for the feature terms, what Atlas and the D-series each detect (and where
they agree), what REMOVALS/dropped-features/live records/gates say, and turns it into claims (STATIC/OBSERVED/VALIDATED with evidence
locations), hypotheses and unknowns with the test that would settle each. Never edits a workspace, never runs the game.
"""
from __future__ import annotations

from pathlib import Path

from ..lookup import default_discovery_dir
from .research_atlas import ATLAS_BUILD, case_migrations, database_implementers, database_status, tree_concepts
from .research_case import content_parity_for, dropped, gates_for, live_records, locate_peer, locate_trees, removals
from .research_changelog import tree_changelog_quotes
from .research_decompile import DEFAULT_MAX_CLASSES, HOW_TO_GET, decompile_report_classes, jar_class_rows
from .research_claims import Ledger, change_hypotheses, changelog_claims, decompiled_claims, feature_claims, gate_claims, live_claims, parity_claims, removal_claims
from .research_compare import compare, merge
from .research_dseries import baselines_and_diffs, behavior_model, graph_concepts, load_graph, scoped_behaviors
from .research_reconcile import CATEGORIES, reconcile
from .research_search import search_tree, summarize
from .research_terms import AUTHOR_CLAIM, STATIC, Matcher, parse_terms

SCHEMA_VERSION = 2
TOOL = "bridgeforge research report"


class ResearchError(ValueError):
    pass


def _tree_ids(trees: list[dict]) -> dict[str, dict]:
    """Stable ids for trees: `working`, `original`, `old-tree` (a second original gets `original-2`); a peer keeps its `peer:NAME` id."""
    seen: dict[str, int] = {}
    out = {}
    for tree in trees:
        if tree.get("id"):
            out[tree["id"]] = tree
            continue
        seen[tree["label"]] = seen.get(tree["label"], 0) + 1
        tree_id = tree["label"] if seen[tree["label"]] == 1 else f"{tree['label']}-{seen[tree['label']]}"
        out[tree_id] = {**tree, "id": tree_id}
    return out


def _analyze_tree(tree: dict, matcher: Matcher, build: bool) -> dict:
    """Search, Atlas extraction and archaeology for one tree; D-series failures become a missing side, not an error."""
    path = tree["path"]
    hits = search_tree(path, matcher)
    atlas = tree_concepts(path, matcher)
    graph, graph_input = load_graph(path, build)
    dseries = graph_concepts(graph, matcher) if graph is not None else None
    return {"hits": hits, "term_summary": summarize(hits), "atlas": atlas, "dseries": dseries, "graph": graph, "graph_input": graph_input}


def _reconciliation(analysis: dict[str, dict]) -> dict:
    per_tree = {}
    totals = {name: 0 for name in CATEGORIES}
    missing: set[str] = set()
    for tree_id, item in sorted(analysis.items()):
        result = reconcile(item["atlas"], item["dseries"])
        per_tree[tree_id] = result
        missing.update(f"dseries ({tree_id})" if m == "dseries" else m for m in result["missing"])
        for name in CATEGORIES:
            totals[name] += result["counts"][name]
    return {"label": STATIC, "counts": totals, "missing": sorted(missing), "trees": per_tree,
            "note": "same code read twice: agreement corroborates, it does not validate; disagreements are kept as rows"}


def _find_repo(start: Path) -> Path:
    for folder in [start.resolve(), *start.resolve().parents]:
        if (folder / "gates.json").is_file():
            return folder
    return start.resolve()


def _check_request(feature: str, case: Path, question: str) -> tuple[tuple[str, ...], Path]:
    terms = parse_terms(feature)
    if not terms:
        raise ResearchError("give at least one search term in FEATURE")
    if not question.strip():
        raise ResearchError("--question must not be empty: the report answers a stated question")
    workspace = Path(case).expanduser().resolve()
    if not workspace.is_dir() or not ((workspace / "working").is_dir() or (workspace / "original").is_dir()):
        raise ResearchError(f"{workspace} is not a case workspace (no working/ or original/ folder)")
    return terms, workspace


def _dseries_section(trees: dict[str, dict], analysis: dict[str, dict], matcher: Matcher) -> tuple[list[dict], dict | None, dict]:
    """(inputs, scoped behaviours or None, captured baselines and diffs) for the working copy's D-series files."""
    inputs = [{**a["graph_input"], "name": f"archaeology ({tid})"} for tid, a in analysis.items()]
    missing = {"name": "behavior-map+hypotheses", "status": "MISSING", "path": ""}
    if "working" not in trees:
        inputs.append({**missing, "command": "python -m bridgeforge archaeology <working> --output <discovery>", "note": "the case has no working/ copy"})
        return inputs, None, {"baselines": [], "diffs": []}
    discovery = default_discovery_dir(trees["working"]["path"])
    graph = analysis["working"]["graph"]
    model, model_input = behavior_model(graph, discovery) if graph is not None else (None, {**missing, "command": "python -m bridgeforge behavior-map <architecture.json> --output <discovery>", "note": "no archaeology graph for working/"})
    runtime, runtime_inputs = baselines_and_diffs(discovery, matcher)
    return inputs + [model_input] + runtime_inputs, (scoped_behaviors(model, matcher) if model else None), runtime


def _atlas_section(trees: dict[str, dict], atlas_db: Path, matcher: Matcher) -> tuple[list[dict], dict, dict]:
    """(inputs, database peers, migration rules for baseline -> working)."""
    status = database_status(atlas_db)
    inputs = [status]
    peers = {"mods_with_any": 0, "shown": []}
    if status["status"] == "PRESENT":
        peers = database_implementers(atlas_db, matcher, tuple(str(t["path"]) for t in trees.values()))
        if not status["census"]:
            inputs.append({"name": "atlas-census", "status": "MISSING", "path": status["path"], "command": ATLAS_BUILD, "note": "the database has no census table, so API usage of other mods is not compared"})
    baseline = next((t for t in ("old-tree", "original") if t in trees), None)
    migrations = {"label": STATIC, "rules": [], "rules_total": 0, "pairs": [], "api_diff": False}
    command = "python -m bridgeforge atlas migrations OLD_DIR NEW_DIR --write DIR"
    if baseline and "working" in trees:
        migrations = case_migrations(trees[baseline]["path"], trees["working"]["path"], matcher)
        inputs.append({"name": "atlas-migrations", "status": "BUILT_IN_MEMORY", "path": "", "command": command,
                       "note": f"mined in memory from {baseline} -> working (read-only); {len(migrations['rules'])} of {migrations['rules_total']} rule(s) name the feature; no api-diff given"})
    else:
        inputs.append({"name": "atlas-migrations", "status": "MISSING", "path": "", "command": command, "note": "needs a baseline tree and a working copy"})
    return inputs, peers, migrations


def _fill_ledger(ledger: Ledger, parts: dict) -> None:
    feature_claims(ledger, parts["tree_rows"])
    ids = removal_claims(ledger, parts["removal"], parts["drop"])
    parity_claims(ledger, parts["parity"])
    live_claims(ledger, parts["live"])
    gate_claims(ledger, parts["gate"]["gates"])
    changelog_claims(ledger, parts["changelogs"])
    decompiled_claims(ledger, parts["decompiled"])
    _reconciliation_claims(ledger, parts["reconciliation"])
    behaviors = parts["behaviors"]
    if behaviors and behaviors["behaviors_total"]:
        ledger.claim("dseries", f"{behaviors['behaviors_total']} behaviour(s) in the working copy's behaviour map mention the feature; none is runtime verified", STATIC,
                     [f"behavior {b['id']} {', '.join(b['evidence'][:1])}" for b in behaviors["behaviors"][:5]], "behavior-map")
    for rule in parts["migrations"]["rules"]:
        ledger.claim("migrations", f"Atlas migration pair: {rule['old']} -> {rule['new']} ({rule['kind']}, {rule['reason']}); proposal only, never applied", STATIC, rule["old_examples"][:1] + rule["new_examples"][:1], "atlas-migrations")
    change_hypotheses(ledger, parts["matrix"], ids, parts["gate"]["gates"])
    for item in parts["inputs"]:
        if item["status"] == "MISSING":
            ledger.unknown(f"{item['name']} is missing for this case: {item['note']}", {"kind": "command", "gates": [], "commands": [item["command"]], "proposed": None}, [])


def _peer_trees(peers: tuple[Path, ...], workspace: Path) -> list[dict]:
    found = []
    for peer in peers:
        tree = locate_peer(peer)
        if tree is None:
            raise ResearchError(f"--peer {peer} holds no working/ or original/ folder and no mod_info.json")
        if Path(peer).expanduser().resolve() == workspace:
            raise ResearchError(f"--peer {peer} is the case itself")
        found.append(tree)
    return found


def _check_cache(cache_dir: Path | None, trees: dict[str, dict], workspace: Path) -> Path | None:
    if cache_dir is None:
        return None
    cache = Path(cache_dir).expanduser().resolve()
    roots = [workspace, *(t["path"].resolve() for t in trees.values())]
    if any(cache == root or root in cache.parents for root in roots):
        raise ResearchError(f"decompiled code is never written into a workspace or mod tree ({cache})")
    return cache


def _decompile_input(section: dict, requested: bool) -> dict:
    record = {"name": "decompiler", "path": "", "command": HOW_TO_GET}
    if not requested:
        return {**record, "status": "SKIPPED", "note": "--no-decompile: no jar class was decompiled"}
    if section["status"] == "MISSING":
        return {**record, "status": "MISSING", "note": f"{section['note']}: readable code was not produced; the bytecode findings above are unaffected"}
    if section["status"] == "NO_CLASSES":
        return {**record, "status": "PRESENT", "note": section["note"]}
    shown = sum(c["status"] in ("CACHED", "DECOMPILED") for c in section["classes"])
    return {**record, "status": "PRESENT", "note": f"Vineflower {section['vineflower']}, JDK {section['jdk']}; {shown} of {section['decompiled_classes']} class version(s) readable, {section['candidates']} class(es) found"}


def _changelog_section(trees: dict[str, dict], matcher: Matcher) -> tuple[dict, dict]:
    files, quotes = [], []
    for tree_id, tree in trees.items():
        found = tree_changelog_quotes(tree["path"], tree_id, matcher)
        files += found["files"]
        quotes += found["quotes"]
    note = f"{len(files)} changelog file(s)/section(s) in {len({f['tree'] for f in files})} tree(s); {len(quotes)} line(s) name the feature (AUTHOR CLAIM, a hint to confirm in code)" if files else "no changelog file or README changelog section in any tree"
    return {"label": AUTHOR_CLAIM, "files": files, "quotes": quotes}, {"name": "author-changelogs", "status": "PRESENT" if files else "NONE_FOUND", "path": "", "command": "", "note": note}


def build_report(feature: str, case: Path, question: str, *, atlas_db: Path, repo: Path | None = None, build: bool = True, peer_workspaces: tuple[Path, ...] = (),
                 decompile: bool = True, max_classes: int = DEFAULT_MAX_CLASSES, cache_dir: Path | None = None) -> dict:
    terms, workspace = _check_request(feature, case, question)
    if max_classes < 1:
        raise ResearchError("--max-classes must be at least 1")
    matcher = Matcher(terms)
    trees = _tree_ids(locate_trees(workspace) + _peer_trees(peer_workspaces, workspace))
    cache = _check_cache(cache_dir, trees, workspace)
    if not trees:
        raise ResearchError(f"{workspace} holds no mod tree to search")
    analysis = {tid: _analyze_tree(tree, matcher, build) for tid, tree in trees.items()}
    d_inputs, behaviors, runtime = _dseries_section(trees, analysis, matcher)
    a_inputs, peers, migrations = _atlas_section(trees, atlas_db, matcher)
    mod_ids = _mod_ids(trees)
    removal, drop, parity = removals(workspace, matcher), dropped(workspace, matcher), content_parity_for(workspace, matcher)
    live, gate = live_records(workspace, mod_ids, matcher), gates_for(repo or _find_repo(Path.cwd()), matcher, mod_ids)
    changelogs, changelog_input = _changelog_section(trees, matcher)
    jar_classes = jar_class_rows(trees, analysis)
    decompiled = decompile_report_classes(trees, jar_classes, matcher, cache, max_classes, workspace.parent.parent) if decompile else {"status": "SKIPPED", "classes": [], "label": STATIC}
    inputs = d_inputs + a_inputs + [changelog_input, _decompile_input(decompiled, decompile), removal["input"], drop["input"], parity["input"], live["input"], gate["input"]]
    concepts = {tid: merge(a["atlas"], a["dseries"]) for tid, a in analysis.items()}
    matrix = compare(concepts, {tid: t["label"] for tid, t in trees.items()}, peers["shown"], removal["entries"])
    tree_rows = [{"id": tid, "label": t["label"], "rel": t["rel"], "terms": list(terms), "term_summary": analysis[tid]["term_summary"]} for tid, t in trees.items()]
    reconciliation = _reconciliation(analysis)
    ledger = Ledger()
    _fill_ledger(ledger, {"tree_rows": tree_rows, "removal": removal, "drop": drop, "parity": parity, "live": live, "gate": gate, "reconciliation": reconciliation,
                          "behaviors": behaviors, "migrations": migrations, "matrix": matrix, "inputs": inputs, "changelogs": changelogs, "decompiled": decompiled})
    return {"schema_version": SCHEMA_VERSION, "tool": TOOL, "read_only": True, "feature": list(terms), "question": question.strip(), "case": {"workspace": workspace.name, "mod_ids": sorted(mod_ids)},
            "trees": [{k: v for k, v in t.items() if k != "path"} for t in tree_rows], "peer_workspaces": sorted(t["rel"] for t in trees.values() if t["label"] == "peer"), "inputs": sorted(inputs, key=lambda i: (i["name"], i["status"])),
            "search": {tid: {"hits": a["hits"][:200], "hits_total": len(a["hits"])} for tid, a in analysis.items()},
            "jar_classes": jar_classes, "decompiled": decompiled, "changelogs": changelogs, "reconciliation": reconciliation, "peers": peers, "comparison": matrix, "migrations": migrations,
            "dseries": {"behaviors": behaviors, **runtime}, "removals": removal["entries"], "dropped_features": {"verdict": drop["verdict"], "items": drop["items"]}, "content_parity": parity["row"],
            "live_records": live["runs"], "gates": gate["gates"], "claims": ledger.claims, "hypotheses": ledger.hypotheses, "unknowns": ledger.unknowns}



def _mod_ids(trees: dict[str, dict]) -> set[str]:
    from ..scanner import _load_lenient_json_file
    ids = set()
    for tree in (t for t in trees.values() if t["label"] != "peer"):
        info = _load_lenient_json_file(tree["path"] / "mod_info.json")
        if isinstance(info, dict) and info.get("id"):
            ids.add(str(info["id"]))
    return ids


def _reconciliation_claims(ledger: Ledger, reconciliation: dict) -> None:
    counts = reconciliation["counts"]
    text = "; ".join(f"{name} {counts[name]}" for name in CATEGORIES)
    missing = f" (incomplete: {', '.join(reconciliation['missing'])})" if reconciliation["missing"] else ""
    claim = ledger.claim("reconciliation", f"Atlas vs D-series on the feature concepts, summed over trees: {text}{missing}; agreement is corroboration of the same files, not validation", STATIC,
                         [f"reconciliation.trees.{tid}" for tid in reconciliation["trees"]], "atlas+dseries")
    if counts["both-different"]:
        ledger.unknown(f"which stack is right on the {counts['both-different']} concept(s) where Atlas and the D-series both detect it but differ (role or file)", {"kind": "command", "gates": [], "commands": ["python -m bridgeforge lookup <name> --mod <working>", "python -m bridgeforge atlas id <name>"],
                                                                                                                                              "proposed": "read the cited files and decide per concept; the counts decide authority later (82.2)"}, [claim])
