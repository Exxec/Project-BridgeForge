"""`bridgeforge lookup`: a query surface over a mod's existing archaeology graph (no second database).

For a class, id, file or symbol it joins what BridgeForge already records:
- definitions and references (graph nodes and edges);
- related classes, lifecycle hooks and registrations;
- save evidence (persistent-state candidates, save/probe baseline observations);
- source/bytecode status (source_package_authority);
- scanner findings;
- runtime observations (behavior map, baselines).

A class is looked up through its aliases: its source-file node (imports hang off the file), the
same-named `symbol:` node (how mod_info and data files reference it) and its lifecycle-hook nodes.

Each item gets an *inspection priority*: an archaeology priority, not an error score. It rises with
source/bytecode divergence, persistence, runtime registration, no known caller, external-mod
references, scanner findings and missing runtime coverage, and every point carries its reason.
`--top N` ranks the mod's classes that way.

The graph is read from <discovery>/archaeology/architecture.json while its file hashes still match the
mod; otherwise it is rebuilt in memory with the same builder (build_archaeology).
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path

from .behavior_discovery import build_archaeology

SCHEMA_VERSION = 1
ITEM_KINDS = ("class", "symbol", "data", "source", "jar", "resource", "registration", "lifecycle-hook")
EXTERNAL_PREFIXES = {
    "Nexerelin": ("exerelin.",),
    "LazyLib": ("org.lazywizard.lazylib.",),
    "Console Commands": ("org.lazywizard.console.",),
    "MagicLib": ("org.magiclib.", "data.scripts.util.Magic"),
    "GraphicsLib": ("org.dark.shaders.",),
    "LunaLib": ("lunalib.",),
}
WEIGHTS = {"divergence": 3, "persistence": 1, "persistence-evidence": 3, "registration": 3, "no-known-caller": 2, "external": 2, "manual-finding": 3, "review-finding": 1, "uncovered": 1}


def default_discovery_dir(mod_dir: Path) -> Path | None:
    """<Mod>/reports/discovery/<working folder name> for the In operation layout."""
    mod_dir = Path(mod_dir).resolve()
    candidate = mod_dir.parent / "reports" / "discovery" / mod_dir.name
    return candidate if candidate.is_dir() else None


def _sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def load_graph(mod_dir: Path, discovery_dir: Path | None = None, *, vanilla_core: Path | None = None) -> tuple[dict, str]:
    """(architecture graph, where it came from). A saved graph whose file hashes changed is rebuilt."""
    mod_dir = Path(mod_dir).expanduser().resolve()
    discovery = Path(discovery_dir).expanduser().resolve() if discovery_dir else default_discovery_dir(mod_dir)
    saved = discovery / "archaeology" / "architecture.json" if discovery else None
    if saved and saved.is_file():
        graph = json.loads(saved.read_text(encoding="utf-8"))
        files = [node for node in graph.get("nodes", []) if node.get("path") and node.get("sha256")]
        if files and all(_sha256(mod_dir / node["path"]) == node["sha256"] for node in files):
            return graph, str(saved)
        source = f"rebuilt in memory ({saved} is stale)"
    else:
        source = "built in memory (no saved archaeology)"
    return build_archaeology(mod_dir, vanilla_core=vanilla_core), source


def _load_json_list(folder: Path | None, pattern: str) -> list[dict]:
    items = []
    for path in sorted(folder.glob(pattern)) if folder and folder.is_dir() else []:
        try:
            items.append({"file": path.name, **json.loads(path.read_text(encoding="utf-8"))})
        except (OSError, json.JSONDecodeError):
            continue
    return items


class Index:
    """Query helpers over one graph plus the discovery artifacts beside it."""

    def __init__(self, graph: dict, discovery_dir: Path | None = None) -> None:
        self.graph = graph
        self.nodes = {node["id"]: node for node in graph.get("nodes", [])}
        self.outgoing: dict[str, list[dict]] = defaultdict(list)
        self.incoming: dict[str, list[dict]] = defaultdict(list)
        for edge in graph.get("edges", []):
            self.outgoing[edge["source"]].append(edge)
            self.incoming[edge["target"]].append(edge)
        summary = graph.get("summary") or {}
        authority = graph.get("source_package_authority") or {}
        # Divergence only means something when a mod has both sources and compiled classes.
        both = bool(summary.get("source_class_count")) and bool(summary.get("package_class_count"))
        self.divergent: set[str] = set()
        if both:
            self.divergent = {str(name) for key in ("source_only_classes", "package_only_classes") for name in authority.get(key) or []}
            self.divergent |= {str(item.get("class") if isinstance(item, dict) else item) for item in authority.get("method_inventory_divergence") or [] if item}
        self.no_reference = [json.dumps(entry, sort_keys=True) for entry in graph.get("no_known_reference") or []]
        self.hooks_by_class: dict[str, list[str]] = defaultdict(list)
        for node_id, node in self.nodes.items():
            if node.get("kind") == "lifecycle-hook" and node.get("class"):
                self.hooks_by_class[node["class"]].append(node_id)
        discovery = Path(discovery_dir) if discovery_dir else None
        behavior_path = discovery / "behavior.json" if discovery else None
        self.behaviors = json.loads(behavior_path.read_text(encoding="utf-8")).get("behaviors", []) if behavior_path and behavior_path.is_file() else None
        self.baselines = _load_json_list(discovery.parent / "baselines" if discovery else None, "*.json") + _load_json_list(discovery, "*baseline*.json")

    @staticmethod
    def display(node: dict) -> str:
        return str(node.get("name") or node.get("value") or node.get("path") or node.get("class") or node.get("owner") or node["id"].split(":", 1)[-1])

    def match(self, query: str, limit: int = 10) -> list[dict]:
        needle = query.strip().lower()
        tiers: list[list[dict]] = [[], [], []]
        for node in self.nodes.values():
            if node.get("kind") not in ITEM_KINDS:
                continue
            name = self.display(node).lower()
            ident = node["id"].lower()
            if needle in (name, ident, ident.split(":", 1)[-1]):
                tiers[0].append(node)
            elif name.rsplit(".", 1)[-1] == needle or name.rsplit("/", 1)[-1] == needle:
                tiers[1].append(node)
            elif needle in name or needle in ident:
                tiers[2].append(node)
        for tier in tiers:
            if tier:
                classes = {self.display(node) for node in tier if node["kind"] == "class"}
                # A class's symbol, hook and registration nodes are folded into the class item.
                kept = [node for node in tier if node["kind"] == "class" or self.display(node) not in classes]
                return sorted(kept, key=lambda node: (ITEM_KINDS.index(node["kind"]), node["id"]))[:limit]
        return []

    def _aliases(self, node: dict) -> tuple[set[str], set[str]]:
        """(ids whose incoming edges count as references, ids whose outgoing edges count as uses)."""
        node_id, name = node["id"], self.display(node)
        into, out = {node_id}, {node_id}
        if node.get("kind") == "class":
            into |= {f"symbol:{name}", *self.hooks_by_class.get(name, [])}
            out |= set(self.hooks_by_class.get(name, []))
            if node.get("source"):
                out.add(f"file:{node['source']}")
        return into, out

    def _mentions(self, text: str, node: dict) -> bool:
        name = self.display(node)
        simple = name.rsplit(".", 1)[-1]
        return name in text or (node.get("kind") == "class" and len(simple) > 3 and simple in text)

    def facts(self, node: dict) -> dict:
        node_id, name, kind = node["id"], self.display(node), node.get("kind")
        into, out = self._aliases(node)
        own = into | out
        definitions = ([f"source:{node['source']}"] if node.get("source") else []) + [f"jar:{provider}" for provider in node.get("providers") or []]
        if not definitions:
            definitions = sorted({edge["source"] for alias in into for edge in self.incoming[alias] if edge["relation"] in ("defines", "provides", "contains")})
        refs_in: dict[str, set[str]] = defaultdict(set)
        for alias in into:
            for edge in self.incoming[alias]:
                if edge["source"] not in own and edge["relation"] not in ("defines", "provides", "contains"):
                    refs_in[edge["relation"]].add(edge["source"])
        refs_out: dict[str, set[str]] = defaultdict(set)
        for alias in out:
            for edge in self.outgoing[alias]:
                if edge["target"] not in own and edge["relation"] not in ("defines", "provides", "contains"):
                    refs_out[edge["relation"]].add(edge["target"])
        neighbours = {src for targets in refs_in.values() for src in targets} | {tgt for targets in refs_out.values() for tgt in targets}
        related = sorted(other for other in neighbours if self.nodes.get(other, {}).get("kind") == "class")
        lifecycle = self.graph.get("lifecycle") or {}
        hooks = sorted({f"{hook['hook']} ({hook.get('evidence_kind') or 'source'}: {hook.get('file')})" for hook in lifecycle.get("hooks", []) if hook.get("class") == name})
        registrations = sorted({f"{reg['call']} -> {reg.get('target')} ({reg.get('file')})" for reg in lifecycle.get("registrations", []) if reg.get("owner") == name})
        if kind == "registration":
            registrations.append(f"{node.get('call')} -> {node.get('target')} (owner {node.get('owner')})")
        candidates = [item for item in self.graph.get("persistent_state", []) if item.get("class") == name and "static final" not in str(item.get("type", ""))]
        persistence = [f"{item.get('field')}: {item.get('type')} [{item.get('status')}]" for item in candidates]
        observations = []
        for baseline in self.baselines:
            for obs in baseline.get("observations", []):
                subject = str(obs.get("subject", ""))
                if name and (name == subject or self._mentions(subject, node) or (kind != "class" and f"[{name}]" in subject)):
                    observations.append(f"{baseline['file']}: {obs.get('observation')} {subject} {json.dumps(obs.get('fields', {}), sort_keys=True)}")
        behaviors = [{"id": b.get("id"), "entry_point": b.get("entry_point"), "lifecycle": b.get("lifecycle"), "runtime_verified": b.get("runtime_verified")}
                     for b in self.behaviors or [] if name in (b.get("java_classes") or []) or name in str(b.get("entry_point", ""))]
        source_files = {node.get("source"), node.get("path")} - {None}
        findings = sorted({f"{item.get('classification')} {item.get('id')} ({item.get('file')})" for item in self.graph.get("scanner_findings", [])
                           if (item.get("file") and item.get("file") in source_files) or any(self._mentions(str(ev), node) for ev in item.get("evidence") or [])})
        external = sorted({library for targets in refs_out.values() for target in targets for library, prefixes in EXTERNAL_PREFIXES.items()
                           if any(target.split(":", 1)[-1].startswith(prefix) for prefix in prefixes)})
        if kind == "class":
            status = "source+bytecode" if node.get("source") and node.get("providers") else ("source only" if node.get("source") else ("bytecode only" if node.get("providers") else "unknown"))
            if name in self.divergent:
                status += "; divergent (source_package_authority)"
        else:
            status = "-"
        no_caller = any(f'"{name}"' in entry or f'"{node_id}"' in entry for entry in self.no_reference)
        return {
            "id": node_id, "kind": kind, "name": name, "definitions": definitions,
            "references_in": {key: sorted(value) for key, value in sorted(refs_in.items())},
            "references_out": {key: sorted(value) for key, value in sorted(refs_out.items())},
            "related": related, "lifecycle_hooks": hooks, "registrations": registrations,
            "persistent_state": persistence, "save_and_probe_observations": observations,
            "source_bytecode_status": status, "findings": findings, "behaviors": behaviors,
            "external_mods": external, "no_known_caller": no_caller,
        }

    def priority(self, facts: dict) -> tuple[int, list[str]]:
        score, reasons = 0, []

        def bump(key: str, reason: str, times: int = 1) -> None:
            nonlocal score
            score += WEIGHTS[key] * times
            reasons.append(f"+{WEIGHTS[key] * times} {reason}")

        if "divergent" in facts["source_bytecode_status"]:
            bump("divergence", "source and bytecode disagree")
        if facts["persistent_state"]:
            if facts["save_and_probe_observations"]:
                bump("persistence-evidence", f"persistent state with save/probe evidence ({len(facts['persistent_state'])} fields)")
            else:
                bump("persistence", f"persistence candidates, unconfirmed ({len(facts['persistent_state'])} fields)")
        if facts["lifecycle_hooks"] or facts["registrations"]:
            bump("registration", "lifecycle hook / runtime registration")
        if facts["no_known_caller"]:
            bump("no-known-caller", "no known reference (every checked domain)")
        if facts["external_mods"]:
            bump("external", "references " + ", ".join(facts["external_mods"]))
        manual = sum(1 for item in facts["findings"] if item.startswith("MANUAL"))
        review = sum(1 for item in facts["findings"] if item.startswith("REVIEW"))
        if manual:
            bump("manual-finding", f"{manual} MANUAL finding(s)", min(manual, 2))
        if review:
            bump("review-finding", f"{review} REVIEW finding(s)", min(review, 3))
        if facts["behaviors"] and not any(item.get("runtime_verified") for item in facts["behaviors"]) and not facts["save_and_probe_observations"]:
            bump("uncovered", "behaviour without runtime coverage")
        return score, reasons


def lookup(mod_dir: Path, query: str | None = None, *, discovery_dir: Path | None = None, top: int = 0, limit: int = 3, vanilla_core: Path | None = None) -> dict:
    mod_dir = Path(mod_dir).expanduser().resolve()
    discovery = Path(discovery_dir).expanduser().resolve() if discovery_dir else default_discovery_dir(mod_dir)
    graph, source = load_graph(mod_dir, discovery, vanilla_core=vanilla_core)
    index = Index(graph, discovery)
    result: dict = {"schema_version": SCHEMA_VERSION, "mode": "LOOKUP", "mod": str(mod_dir), "graph": source, "behavior_map": bool(index.behaviors), "baselines": len(index.baselines)}
    if query:
        matches = index.match(query)
        result["query"] = query
        result["matches"] = [{"id": node["id"], "kind": node["kind"], "name": index.display(node)} for node in matches]
        detailed = []
        for node in matches[:limit]:
            facts = index.facts(node)
            facts["priority"], facts["priority_reasons"] = index.priority(facts)
            detailed.append(facts)
        result["items"] = detailed
        result["status"] = "OK" if matches else "NOT_FOUND"
    if top:
        ranked = []
        for node in index.nodes.values():
            if node.get("kind") != "class":
                continue
            facts = index.facts(node)
            score, reasons = index.priority(facts)
            if score:
                ranked.append({"id": node["id"], "name": facts["name"], "priority": score, "reasons": reasons})
        result["treasure_map"] = sorted(ranked, key=lambda item: (-item["priority"], item["id"]))[:top]
        result.setdefault("status", "OK")
    return result
