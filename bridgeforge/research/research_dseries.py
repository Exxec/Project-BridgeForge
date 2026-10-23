"""D-series side of `research report` (82.1, 82.2): archaeology graph, behaviour map, hypotheses, baselines and behaviour-diff.

Reuses `lookup.load_graph` (a saved architecture.json whose file hashes still match, else built in memory), `behavior_discovery.
build_behavior_model` and the saved artifacts beside a working copy (`<workspace>/reports/discovery/<tree name>/`). Nothing is
written into the workspace. A building step is the only expensive part (about 25 s for a 2,600-node mod); `build=False` skips it
and reports the input as missing with the command that produces it.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from ..behavior_discovery import DiscoveryError, build_archaeology, build_behavior_model
from ..lookup import _sha256, default_discovery_dir
from .research_reconcile import Concept
from ..safeio import atomic_write_json
from .research_terms import FILE_EXTENSIONS, STATIC, Matcher, concept_key

MAX_ITEMS = 40
ARTIFACTS = ("behavior.json", "hypotheses.json", "unknowns.json", "risks.json")


def _saved_graph(tree: Path, discovery: Path | None) -> dict | None:
    saved = discovery / "archaeology" / "architecture.json" if discovery else None
    if not saved or not saved.is_file():
        return None
    try:
        graph = json.loads(saved.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    files = [n for n in graph.get("nodes", []) if n.get("path") and n.get("sha256")]
    return graph if files and all(_sha256(tree / n["path"]) == n["sha256"] for n in files) else None


def load_graph(tree: Path, build: bool) -> tuple[dict | None, dict]:
    """(graph or None, input record). A fresh saved graph is used; otherwise it is built in memory when `build`."""
    discovery = default_discovery_dir(tree)
    command = f'python -m bridgeforge archaeology "{tree}" --output <discovery>/archaeology'
    record = {"name": "archaeology", "tree": tree.name, "command": command}
    graph = _saved_graph(tree, discovery)
    if graph is not None:
        return graph, {**record, "status": "PRESENT", "path": str(discovery / "archaeology" / "architecture.json"), "note": "saved graph, file hashes match"}
    if not build:
        return None, {**record, "status": "MISSING", "path": "", "note": "no fresh saved graph; --no-build chosen, so nothing was built"}
    try:
        return build_archaeology(tree), {**record, "status": "BUILT_IN_MEMORY", "path": "", "note": "built read-only in memory (cheap, no write): no fresh saved graph"}
    except (DiscoveryError, OSError) as exc:
        return None, {**record, "status": "MISSING", "path": "", "note": f"archaeology failed: {exc}"}


def _node_files(graph: dict) -> dict[str, set[str]]:
    """symbol/class node id -> the files whose edges reference it."""
    refs: dict[str, set[str]] = {}
    for edge in graph.get("edges", []):
        source = str(edge.get("source", ""))
        if source.startswith("file:") and edge.get("relation") in {"data-reference", "string-reference", "defines", "provides", "imports"}:
            refs.setdefault(str(edge.get("target", "")), set()).add(source[5:])
    return refs


def graph_concepts(graph: dict, matcher: Matcher) -> dict[str, Concept]:
    """Concepts the archaeology graph holds for the feature terms (class nodes, symbols, lifecycle hooks, file-term references)."""
    refs = _node_files(graph)
    out: dict[str, Concept] = {}
    for node in graph.get("nodes", []):
        kind, ident = node.get("kind"), str(node.get("id", ""))
        if kind == "class":
            name = str(node.get("name", ""))
            terms = matcher.name_hits(name)
            if terms:
                asset = name.rsplit(".", 1)[-1].lower() in FILE_EXTENSIONS  # a path string the graph resolved like a class name
                where = [node.get("source")] + list(node.get("providers", [])) + sorted(refs.get(ident, ()))
                for place in [w for w in where if w]:
                    out.setdefault(concept_key(name), Concept()).add(name, "data-or-string" if asset else "code-class", "class-node (file path)" if asset else "class", str(place), terms)
        elif kind == "lifecycle-hook":
            name = f"{node.get('class')}#{node.get('hook')}"
            terms = matcher.name_hits(name)
            if terms:
                out.setdefault(concept_key(str(node.get("class", ""))), Concept()).add(name, "registration", "lifecycle-hook", str(node.get("file", "")), terms)
        elif kind == "symbol":
            name = str(node.get("value", ""))
            files = sorted(refs.get(ident, ()))
            terms = matcher.name_hits(name)
            terms += [t for f in files for t in matcher.file_hits(f) if t not in terms]
            for place in files if terms else ():
                out.setdefault(concept_key(name), Concept()).add(name, "data-or-string", "symbol", place, terms)
    return {key: concept for key, concept in out.items() if concept.names}


def behavior_model(graph: dict, discovery: Path | None) -> tuple[dict | None, dict]:
    """(behaviors/risks/hypotheses/unknowns, input record): the saved files when all exist, else derived in memory from `graph`."""
    command = "python -m bridgeforge behavior-map <architecture.json> --output <discovery>"
    saved = {name: discovery / name for name in ARTIFACTS if discovery and (discovery / name).is_file()}
    record = {"name": "behavior-map+hypotheses", "command": command}
    if len(saved) == len(ARTIFACTS):
        try:
            loaded = {n.removesuffix(".json"): json.loads(p.read_text(encoding="utf-8")) for n, p in saved.items()}
        except (OSError, ValueError):
            loaded = None
        if loaded:
            model = {"behaviors": loaded["behavior"].get("behaviors", []), "risks": loaded["risks"].get("risks", []),
                     "hypotheses": loaded["hypotheses"].get("hypotheses", []), "unknowns": loaded["unknowns"].get("unknowns", [])}
            return model, {**record, "status": "PRESENT", "path": str(discovery), "note": "saved files"}
    try:
        with tempfile.TemporaryDirectory(prefix="bf-research-") as scratch:
            path = Path(scratch) / "architecture.json"
            atomic_write_json(path, graph)
            built = build_behavior_model(path)
    except (DiscoveryError, OSError) as exc:
        return None, {**record, "status": "MISSING", "path": "", "note": f"could not derive: {exc}"}
    model = {k: built[k] for k in ("behaviors", "risks", "hypotheses", "unknowns")}
    return model, {**record, "status": "BUILT_IN_MEMORY", "path": "", "note": "derived in memory from the graph (deterministic, no write)"}


def scoped_behaviors(model: dict, matcher: Matcher) -> dict:
    """Behaviours that mention a feature term, with their hypotheses, unknowns and risks (all STATIC, all open until a run)."""
    picked = []
    for item in model["behaviors"]:
        pool = [str(item.get("entry_point", "")), *map(str, item.get("java_classes", [])), *map(str, item.get("data_files", [])), *map(str, item.get("ids_consumed", []))]
        terms = matcher.any_name(*pool)
        if terms:
            picked.append({"id": item["id"], "entry_point": item.get("entry_point"), "terms": terms, "evidence": item.get("evidence", []),
                           "runtime_verified": bool(item.get("runtime_verified")), "label": STATIC})
    ids = {p["id"] for p in picked}
    pick = lambda key: [x for x in model[key] if x.get("behavior_id") in ids]  # noqa: E731
    return {"behaviors": picked[:MAX_ITEMS], "behaviors_total": len(picked), "hypotheses": pick("hypotheses")[:MAX_ITEMS],
            "unknowns": pick("unknowns")[:MAX_ITEMS], "risks": pick("risks")[:MAX_ITEMS]}


def _json_files(discovery: Path | None) -> list[Path]:
    folders = [discovery, discovery.parent / "baselines" if discovery else None]
    return sorted({p for f in folders if f and f.is_dir() for p in f.glob("*.json") if p.name not in ARTIFACTS and p.name != "coverage_seed.json"})


def baselines_and_diffs(discovery: Path | None, matcher: Matcher) -> tuple[dict, list[dict]]:
    """Captured baselines (probe-baseline, save-baseline) and behaviour-diff results beside the discovery folder, scoped to the terms."""
    baselines, diffs, inputs = [], [], []
    for path in _json_files(discovery):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        if data.get("mode") == "NO_VERDICT_BASELINE":
            kind = (data.get("reference") or {}).get("kind")
            rows = [o for o in data.get("observations", []) if matcher.any_name(str(o.get("subject", "")), json.dumps(o.get("fields", {})))]
            baselines.append({"file": path.name, "scenario": data.get("scenario"), "reference_kind": kind, "observations_total": data.get("observation_count", 0),
                              "matching": [{"observation": o.get("observation"), "subject": o.get("subject"), "fields": o.get("fields")} for o in rows[:MAX_ITEMS]],
                              "label": STATIC if kind == "static-floor" else "OBSERVED"})
        elif isinstance(data.get("deltas"), list):
            rows = [d for d in data["deltas"] if matcher.any_name(str(d.get("subject", "")), str(d.get("observation", "")))]
            diffs.append({"file": path.name, "status": data.get("status"), "counts": data.get("counts", {}), "matching": rows[:MAX_ITEMS], "matching_total": len(rows),
                          "label": "OBSERVED"})
    missing = [("probe-baseline", baselines, 'python -m bridgeforge probe-baseline <observations.json> --build <id> --scenario <name> --output <discovery>'),
               ("behavior-diff", diffs, "python -m bridgeforge behavior-diff <before-baseline> <after-baseline> --output <diff.json>")]
    for name, found, command in missing:
        inputs.append({"name": name, "status": "PRESENT" if found else "MISSING", "path": str(discovery) if found else "", "command": command,
                       "note": f"{len(found)} file(s)" if found else "none beside the discovery folder: no captured runtime observations are compared"})
    return {"baselines": baselines, "diffs": diffs}, inputs
