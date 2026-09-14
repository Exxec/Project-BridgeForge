"""`bridgeforge novelty`: how a mod compares with the mods BridgeForge has already seen.

A mod's fingerprint is drawn from its archaeology graph (the same one `lookup` queries):
- api: core API classes it references (bytecode references and imports into com.fs.starfarer.api);
- lifecycle: plugin hooks it implements and runtime registration calls it makes;
- structure: edge patterns (`relation|source-kind|target-kind`, with data files reduced to their
  folder and type, e.g. `data-reference|data:data/hullmods/*.csv|symbol`);
- finding: scanner finding ids;
- weak: ids/classes with weak ownership or reference evidence (no known reference, ownership
  unresolved, missing campaign fleet references).

Fingerprints are kept per mod in bridgeforge-state/corpus-fingerprints/ (gitignored: some come from
local-only mods). `--record` adds or refreshes the mod's own entry.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .lookup import default_discovery_dir, load_graph

SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CORPUS = REPO_ROOT / "bridgeforge-state" / "corpus-fingerprints"
CATEGORIES = ("api", "lifecycle", "structure", "finding")


def _kind(node: dict | None) -> str:
    if not node:
        return "unknown"
    kind = node.get("kind", "unknown")
    path = str(node.get("path") or "")
    if kind in ("data", "source", "resource") and path:
        parts = path.split("/")
        # Data/source keep two folder levels (data/hullmods); jar resources only their top folder, so one
        # bundled Kotlin runtime is one structure, not one per package.
        depth = 1 if kind == "resource" else 2
        folder = "/".join(parts[:depth]) if len(parts) > depth else "/".join(parts[:-1])
        suffix = Path(path).suffix.lower() or "(none)"
        return f"{kind}:{folder}/*{suffix}" if folder else f"{kind}:*{suffix}"
    return kind


def api_class(symbol: str) -> str:
    """The class a core-API reference points at: packages, then CamelCase classes and inner classes.

    `com.fs.starfarer.api.Global.getSector` -> `com.fs.starfarer.api.Global`;
    `...WeaponAPI.WeaponType.MISSILE` -> `...WeaponAPI.WeaponType` (methods and constants dropped).
    """
    parts = re.sub(r"[#(].*$", "", symbol).split(".")
    kept: list[str] = []
    seen_class = False
    for part in parts:
        is_class = part[:1].isupper() and not part.isupper()
        if seen_class and not is_class:
            break
        seen_class = seen_class or is_class
        kept.append(part)
    return ".".join(kept)


def _loaded(node: dict | None) -> bool:
    """disabled_files/ is never loaded by the game; its structures aren't the mod's."""
    return not str((node or {}).get("path") or (node or {}).get("source") or "").startswith("disabled_files/")


def fingerprint(graph: dict) -> dict:
    nodes = {node["id"]: node for node in graph.get("nodes", [])}
    own_classes = {str(node.get("name")) for node in nodes.values() if node.get("kind") == "class"}
    api, structure = set(), set()
    for edge in graph.get("edges", []):
        source, target_node = nodes.get(edge["source"]), nodes.get(edge["target"])
        if not (_loaded(source) and _loaded(target_node)):
            continue
        target = edge["target"].split(":", 1)[-1]
        if edge["relation"] in ("bytecode-reference", "imports") and target.startswith("com.fs.starfarer.api."):
            name = api_class(target)
            # Some mods put their own classes in vanilla's packages (Mirfak's ...campaign.items.LTHS_CARD_*).
            if name not in own_classes:
                api.add(name)
        structure.add(f"{edge['relation']}|{_kind(source)}|{_kind(target_node)}")
    lifecycle = graph.get("lifecycle") or {}
    lifecycle_features = {f"hook:{hook['hook']}" for hook in lifecycle.get("hooks", [])}
    lifecycle_features |= {f"register:{reg['call']}" for reg in lifecycle.get("registrations", [])}
    findings = {f"finding:{item['id']}" for item in graph.get("scanner_findings", []) if item.get("id")}
    weak = {f"no-known-reference: {entry.get('class') or entry.get('id') or entry.get('name')} ({entry.get('file')})" if isinstance(entry, dict) else f"no-known-reference: {entry}"
            for entry in graph.get("no_known_reference") or []}
    weak |= {f"{item.get('id')}: {(item.get('evidence') or ['?'])[0]}" for item in graph.get("scanner_findings", [])
             if any("external-or-core-unresolved" in str(ev) for ev in item.get("evidence") or []) or item.get("id") == "campaign-fleet-reference-missing"}
    weak = sorted(weak)
    return {
        "schema_version": SCHEMA_VERSION, "mod_id": graph.get("mod_id"), "input_mod": graph.get("input_mod"),
        "features": {"api": sorted(api), "lifecycle": sorted(lifecycle_features), "structure": sorted(structure), "finding": sorted(findings)},
        "weak": weak,
    }


def load_corpus(corpus_dir: Path) -> list[dict]:
    items = []
    for path in sorted(Path(corpus_dir).glob("*.json")) if Path(corpus_dir).is_dir() else []:
        try:
            items.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return items


def compare(fp: dict, corpus: list[dict], examples: int = 8) -> dict:
    others = [item for item in corpus if item.get("mod_id") != fp.get("mod_id")]
    counts = {category: {} for category in CATEGORIES}
    for other in others:
        for category in CATEGORIES:
            for feature in set(other.get("features", {}).get(category, [])):
                counts[category][feature] = counts[category].get(feature, 0) + 1
    mine = fp["features"]
    seen = sum(1 for category in CATEGORIES for feature in mine[category] if counts[category].get(feature))
    total = sum(len(mine[category]) for category in CATEGORIES)
    unusual = [feature for feature in mine["structure"] if counts["structure"].get(feature, 0) < 2]
    new_api = [feature for feature in mine["api"] if not counts["api"].get(feature)]
    new_lifecycle = [feature for feature in mine["lifecycle"] if not counts["lifecycle"].get(feature)]
    new_findings = [feature for feature in mine["finding"] if not counts["finding"].get(feature)]
    return {
        "schema_version": SCHEMA_VERSION, "mode": "NOVELTY", "mod_id": fp.get("mod_id"),
        "corpus_size": len(others), "small_corpus": len(others) < 3,
        "patterns_total": total, "patterns_seen": seen,
        "unusual_structures": len(unusual), "new_api_usages": len(new_api),
        "new_lifecycle_patterns": len(new_lifecycle), "new_finding_kinds": len(new_findings),
        "weak_ownership": len(fp["weak"]),
        "examples": {"unusual_structures": unusual[:examples], "new_api_usages": new_api[:examples], "new_lifecycle_patterns": new_lifecycle[:examples], "new_finding_kinds": new_findings[:examples], "weak_ownership": fp["weak"][:examples]},
    }


def novelty(mod_dir: Path, *, discovery_dir: Path | None = None, corpus_dir: Path | None = None, record: bool = False, vanilla_core: Path | None = None) -> dict:
    mod_dir = Path(mod_dir).expanduser().resolve()
    graph, source = load_graph(mod_dir, discovery_dir or default_discovery_dir(mod_dir), vanilla_core=vanilla_core)
    fp = fingerprint(graph)
    corpus_path = Path(corpus_dir) if corpus_dir else DEFAULT_CORPUS
    result = compare(fp, load_corpus(corpus_path))
    result["graph"] = source
    if record:
        corpus_path.mkdir(parents=True, exist_ok=True)
        name = re.sub(r"[^A-Za-z0-9_.-]", "_", str(fp.get("mod_id") or mod_dir.name))
        (corpus_path / f"{name}.json").write_text(json.dumps(fp, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        result["recorded"] = str(corpus_path / f"{name}.json")
    return result
