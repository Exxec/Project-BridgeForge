from __future__ import annotations

import csv
import hashlib
import json
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from . import __version__
from .scanner import _blank_java_comments, _load_lenient_json_file, scan_mod
from .models import TargetProfile
from .jar_audit import ClassFileError, parse_constant_pool, referenced_class_names, referenced_members
from .save_inspect import inspect_save
from .scanner import _parse_class_file


SCHEMA_VERSION = 1
DISCOVERY_SUFFIXES = {
    ".java", ".class", ".csv", ".json", ".faction", ".variant", ".ship",
    ".wpn", ".skin", ".system", ".jar",
}
LIFECYCLE_HOOKS = (
    "onApplicationLoad", "onNewGame", "onNewGameAfterProcGen",
    "onNewGameAfterEconomyLoad", "onNewGameAfterTimePass", "onGameLoad",
)
REGISTRATION_CALLS = (
    "addScript", "addTransientScript", "addListener", "addPlugin",
    "addLayeredRenderingPlugin", "addTransientListener",
)
CHECKED_DOMAINS = [
    "source", "bytecode", "csv", "json", "faction-data", "variants",
    "rules.csv", "reflection-shaped-strings",
]
UNVERIFIED_DOMAINS = [
    "runtime-registration", "generated-references", "external-mod-integration",
]


class DiscoveryError(ValueError):
    pass


_JAVA_KEYWORDS = frozenset(
    "abstract assert boolean break byte case catch char class const continue default do double else enum extends final "
    "finally float for goto if implements import instanceof int interface long native new package private protected public "
    "return short static strictfp super switch synchronized this throw throws transient try void volatile while var record".split()
)


def _resolved_directory(path: Path, label: str) -> Path:
    result = path.expanduser().resolve()
    if not result.is_dir():
        raise DiscoveryError(f"{label} is not a directory: {result}")
    return result


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _stable_id(prefix: str, *parts: object) -> str:
    material = "\0".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(material).hexdigest()[:10].upper()}"


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _walk_scalars(value: object, prefix: str = "") -> Iterable[tuple[str, str]]:
    if isinstance(value, dict):
        for key in sorted(value, key=str):
            child = f"{prefix}.{key}" if prefix else str(key)
            yield from _walk_scalars(value[key], child)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_scalars(item, f"{prefix}[{index}]")
    elif isinstance(value, (str, int, float, bool)):
        yield prefix, str(value)


def _looks_reference(value: str) -> bool:
    return bool(
        re.fullmatch(r"[A-Za-z_$][\w$]*(?:[./][A-Za-z_$][\w$]*)+", value)
        or re.fullmatch(r"[A-Za-z_$][\w$-]{2,}", value)
    )


def _symbol_key(value: str) -> str:
    return value.replace("/", ".").removesuffix(".class")


def _read_text(path: Path) -> str | None:
    for encoding in ("utf-8-sig", "windows-1252"):
        try:
            return path.read_text(encoding=encoding)
        except (UnicodeDecodeError, OSError):
            continue
    return None


def _load_save_aliases(path: Path | None) -> set[str]:
    if path is None:
        return set()
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise DiscoveryError(f"save-alias evidence does not exist: {resolved}")
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    aliases: set[str] = set()
    for key in ("aliases", "class_aliases", "classes", "tracked_classes"):
        value = payload.get(key) if isinstance(payload, dict) else None
        if isinstance(value, dict):
            aliases.update(map(str, value.keys()))
            aliases.update(str(item) for item in value.values() if isinstance(item, str))
        elif isinstance(value, list):
            aliases.update(str(item) for item in value)
    return aliases


def build_archaeology(mod_directory: Path, *, save_aliases: Path | None = None, vanilla_core: Path | None = None) -> dict[str, object]:
    root = _resolved_directory(mod_directory, "mod directory")
    aliases = _load_save_aliases(save_aliases)
    mod_info = _load_lenient_json_file(root / "mod_info.json") if (root / "mod_info.json").is_file() else None
    mod_id = str(mod_info.get("id")) if isinstance(mod_info, dict) and mod_info.get("id") else root.name
    files = sorted(
        (path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in DISCOVERY_SUFFIXES),
        key=lambda path: _relative(root, path).lower(),
    )
    nodes: dict[str, dict[str, object]] = {}
    edges: set[tuple[str, str, str, str]] = set()
    source_classes: dict[str, str] = {}
    package_classes: dict[str, set[str]] = defaultdict(set)
    bytecode_methods: dict[str, set[str]] = defaultdict(set)
    source_methods: dict[str, set[str]] = defaultdict(set)
    lifecycle: list[dict[str, object]] = []
    registrations: list[dict[str, object]] = []
    persistent_candidates: list[dict[str, object]] = []
    # With vanilla_core, assets a mod borrows from vanilla resolve instead of reading as missing
    # (Flu-X: 9 false HIGH "asset-reference-missing" risks without it).
    scan_result = scan_mod(root, TargetProfile(), vanilla_core)

    def add_node(node_id: str, kind: str, **extra: object) -> None:
        existing = nodes.setdefault(node_id, {"id": node_id, "kind": kind})
        existing.update(extra)

    def add_reference(source: str, value: str, relation: str, evidence: str) -> None:
        normalized = _symbol_key(value.strip())
        if not normalized or not _looks_reference(normalized):
            return
        target = f"symbol:{normalized}"
        add_node(target, "symbol", value=normalized)
        edges.add((source, target, relation, evidence))

    for path in files:
        rel = _relative(root, path)
        file_id = f"file:{rel}"
        suffix = path.suffix.lower()
        kind = "jar" if suffix == ".jar" else "bytecode" if suffix == ".class" else "source" if suffix == ".java" else "data"
        try:
            file_bytes = path.read_bytes()
            add_node(file_id, kind, path=rel, size=len(file_bytes), sha256=hashlib.sha256(file_bytes).hexdigest())
        except OSError:
            file_bytes = b""
            add_node(file_id, kind, path=rel, unreadable=True)
        if suffix == ".jar":
            try:
                with zipfile.ZipFile(path) as archive:
                    for member in sorted(archive.namelist()):
                        if member.endswith(".class") and not member.endswith("module-info.class"):
                            class_name = _symbol_key(member)
                            package_classes[class_name].add(rel)
                            class_id = f"class:{class_name}"
                            add_node(class_id, "class", name=class_name, providers=sorted(package_classes[class_name]))
                            edges.add((file_id, class_id, "provides", member))
                            try:
                                class_bytes = archive.read(member)
                                pool = parse_constant_pool(class_bytes)
                                references = referenced_class_names(pool)
                            except (ClassFileError, KeyError, OSError):
                                add_node(class_id, "class", bytecode_references_unreadable=True)
                            else:
                                for reference in sorted(references):
                                    add_reference(class_id, reference, "bytecode-reference", member)
                                class_info = _parse_class_file(class_bytes)
                                if class_info is not None:
                                    bytecode_methods[class_name].update(name for name, _descriptor, _public in class_info.methods if name not in {"<init>", "<clinit>"})
                                    for method_name, _descriptor, _public in class_info.methods:
                                        if method_name in LIFECYCLE_HOOKS:
                                            entry = {"class": class_name, "hook": method_name, "file": rel, "offset": -1, "evidence_kind": "bytecode-method"}
                                            lifecycle.append(entry)
                                            hook_id = f"lifecycle:{class_name}#{method_name}"
                                            add_node(hook_id, "lifecycle-hook", **entry)
                                            edges.add((class_id, hook_id, "declares-hook", f"{member} method table"))
                                for owner_name, method_name, descriptor in sorted(referenced_members(pool)):
                                    if method_name in REGISTRATION_CALLS:
                                        entry = {"owner": class_name, "call": method_name, "target": "<argument-unresolved-from-bytecode>", "file": rel, "offset": -1, "evidence": f"{member}: {owner_name}.{method_name}{descriptor}"}
                                        registrations.append(entry)
                                        reg_id = _stable_id("REG", class_name, method_name, member)
                                        add_node(f"registration:{reg_id}", "registration", **entry)
                                        edges.add((class_id, f"registration:{reg_id}", "registers", entry["evidence"]))
                        elif not member.endswith("/"):
                            resource_id = f"resource:{member}"
                            add_node(resource_id, "resource", path=member)
                            edges.add((file_id, resource_id, "contains", member))
            except (OSError, zipfile.BadZipFile):
                add_node(file_id, kind, unreadable=True)
            continue
        if suffix == ".class":
            class_name = _symbol_key(rel)
            package_classes[class_name].add(rel)
            add_node(f"class:{class_name}", "class", name=class_name, providers=sorted(package_classes[class_name]))
            edges.add((file_id, f"class:{class_name}", "provides", rel))
            try:
                class_bytes = path.read_bytes()
                pool = parse_constant_pool(class_bytes)
                references = referenced_class_names(pool)
            except (ClassFileError, OSError):
                add_node(f"class:{class_name}", "class", bytecode_references_unreadable=True)
            else:
                for reference in sorted(references):
                    add_reference(f"class:{class_name}", reference, "bytecode-reference", rel)
                class_info = _parse_class_file(class_bytes)
                if class_info is not None:
                    bytecode_methods[class_name].update(name for name, _descriptor, _public in class_info.methods if name not in {"<init>", "<clinit>"})
                    for method_name, _descriptor, _public in class_info.methods:
                        if method_name in LIFECYCLE_HOOKS:
                            entry = {"class": class_name, "hook": method_name, "file": rel, "offset": -1, "evidence_kind": "bytecode-method"}
                            lifecycle.append(entry)
                            hook_id = f"lifecycle:{class_name}#{method_name}"
                            add_node(hook_id, "lifecycle-hook", **entry)
                            edges.add((f"class:{class_name}", hook_id, "declares-hook", f"{rel} method table"))
                for owner_name, method_name, descriptor in sorted(referenced_members(pool)):
                    if method_name in REGISTRATION_CALLS:
                        entry = {"owner": class_name, "call": method_name, "target": "<argument-unresolved-from-bytecode>", "file": rel, "offset": -1, "evidence": f"{owner_name}.{method_name}{descriptor}"}
                        registrations.append(entry)
                        reg_id = _stable_id("REG", class_name, method_name, rel)
                        add_node(f"registration:{reg_id}", "registration", **entry)
                        edges.add((f"class:{class_name}", f"registration:{reg_id}", "registers", entry["evidence"]))
            continue
        text = _read_text(path)
        if text is None:
            add_node(file_id, kind, unreadable=True)
            continue
        if suffix == ".java":
            package_match = re.search(r"(?m)^\s*package\s+([\w.]+)\s*;", text)
            package = package_match.group(1) if package_match else ""
            # Comments blanked first: "// Only class allowed to import" (Flu-X NexCompat) was read as a
            # declaration of a class named "allowed".
            # Strings blanked as well: a log message "the class for a System" produced a class `for`.
            for match in re.finditer(r"\b(?:class|interface|enum)\s+([A-Za-z_$][\w$]*)", _blank_java_comments(text, strings=True)):
                simple = match.group(1)
                if simple in _JAVA_KEYWORDS:
                    continue
                class_name = f"{package}.{simple}" if package else simple
                source_classes[class_name] = rel
                class_id = f"class:{class_name}"
                add_node(class_id, "class", name=class_name, source=rel)
                edges.add((file_id, class_id, "defines", simple))
            for imported in re.findall(r"(?m)^\s*import\s+(?:static\s+)?([\w.$*]+)\s*;", text):
                add_reference(file_id, imported, "imports", imported)
            for literal in re.findall(r'"((?:\\.|[^"\\])*)"', text):
                add_reference(file_id, literal, "string-reference", literal)
            owner = next((name for name, source in source_classes.items() if source == rel), rel)
            for method_match in re.finditer(r"(?m)^\s*(?:public|protected|private)\s+(?:static\s+|final\s+|synchronized\s+)*[\w.$<>?,\[\] ]+\s+([A-Za-z_$][\w$]*)\s*\(", text):
                source_methods[owner].add(method_match.group(1))
            for hook in LIFECYCLE_HOOKS:
                for match in re.finditer(rf"\b{re.escape(hook)}\s*\(", text):
                    entry = {"class": owner, "hook": hook, "file": rel, "offset": match.start()}
                    lifecycle.append(entry)
                    hook_id = f"lifecycle:{owner}#{hook}"
                    add_node(hook_id, "lifecycle-hook", **entry)
                    edges.add((f"class:{owner}", hook_id, "declares-hook", hook))
            for call in REGISTRATION_CALLS:
                for match in re.finditer(rf"\b{re.escape(call)}\s*\(([^;\n]*)", text):
                    expression = match.group(1).strip()[:240]
                    target_match = re.search(r"new\s+([\w.$]+)", expression)
                    target = target_match.group(1) if target_match else expression
                    entry = {"owner": owner, "call": call, "target": target, "file": rel, "offset": match.start()}
                    registrations.append(entry)
                    reg_id = _stable_id("REG", owner, call, target, rel, match.start())
                    add_node(f"registration:{reg_id}", "registration", **entry)
                    edges.add((f"class:{owner}", f"registration:{reg_id}", "registers", call))
                    add_reference(f"registration:{reg_id}", target, "targets", expression)
            class_names = [name for name, source in source_classes.items() if source == rel]
            for field in re.finditer(r"(?m)^\s*(?!static\b)(?:public|protected|private)?\s*(?:final\s+|transient\s+|volatile\s+)*([\w.$<>?, ]+)\s+([A-Za-z_$][\w$]*)\s*(?:=|;)", text):
                for class_name in class_names or [rel]:
                    confirmed = class_name in aliases or class_name.rsplit(".", 1)[-1] in aliases
                    persistent_candidates.append({
                        "class": class_name, "field": field.group(2), "type": " ".join(field.group(1).split()),
                        "file": rel, "status": "CONFIRMED_SAVE_ALIAS" if confirmed else "CANDIDATE_NOT_RUNTIME_CONFIRMED",
                    })
            continue
        if suffix == ".csv":
            try:
                rows = list(csv.DictReader(text.splitlines()))
            except csv.Error:
                rows = []
            for row_index, row in enumerate(rows, start=2):
                for column, value in sorted(row.items(), key=lambda item: str(item[0])):
                    if isinstance(value, str):
                        add_reference(file_id, value, "data-reference", f"row {row_index}, {column if column is not None else '(extra-column)'}")
            continue
        data = _load_lenient_json_file(path)
        if data is not None:
            for location, value in _walk_scalars(data):
                add_reference(file_id, value, "data-reference", location)

    # Resolve generic symbol nodes onto class providers without erasing the evidence edge.
    by_simple: dict[str, list[str]] = defaultdict(list)
    for class_name in sorted(set(source_classes) | set(package_classes)):
        by_simple[class_name.rsplit(".", 1)[-1]].append(class_name)
    for source, target, relation, evidence in list(edges):
        if not target.startswith("symbol:"):
            continue
        value = target[7:]
        matches = ([value] if value in source_classes or value in package_classes else by_simple.get(value.rsplit(".", 1)[-1], []))
        for class_name in matches:
            edges.add((source, f"class:{class_name}", f"resolves-{relation}", evidence))

    scanner_findings = []
    for finding in scan_result.findings:
        entry = {
            "id": finding.id, "category": finding.category, "severity": finding.severity,
            "classification": finding.classification, "confidence": finding.confidence,
            "explanation": finding.explanation, "file": finding.file, "evidence": finding.evidence,
        }
        scanner_findings.append(entry)
        finding_node = f"finding:{_stable_id('FIND', finding.id, finding.file, finding.evidence)}"
        add_node(finding_node, "scanner-finding", finding=entry)
        if finding.file:
            source = f"file:{finding.file}"
            add_node(source, "data", path=finding.file)
            edges.add((source, finding_node, "has-finding", finding.id))

    incoming = Counter(target for source, target, relation, _ in edges if relation not in {"defines", "provides"})
    no_known_reference = []
    for class_name, rel in sorted(source_classes.items()):
        if incoming[f"class:{class_name}"] == 0:
            no_known_reference.append({
                "class": class_name,
                "file": rel,
                "finding": "NO_KNOWN_REFERENCE",
                "confidence": 0.72,
                "checked": CHECKED_DOMAINS,
                "not_verified": UNVERIFIED_DOMAINS,
                "note": "This is not a dead-code verdict.",
            })
    routes: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for entry in registrations:
        routes[(str(entry["call"]), str(entry["target"]))].append(entry)
    duplicate_risks = [
        {"call": key[0], "target": key[1], "routes": sorted(value, key=lambda item: (str(item["file"]), int(item["offset"]))), "status": "POSSIBLE_DUPLICATE_REGISTRATION"}
        for key, value in sorted(routes.items()) if len(value) > 1
    ]
    source_names, package_names = set(source_classes), set(package_classes)
    method_divergence = []
    for class_name in sorted(source_names & package_names):
        source_set, bytecode_set = source_methods.get(class_name, set()), bytecode_methods.get(class_name, set())
        if source_set != bytecode_set:
            method_divergence.append({"class": class_name, "source_only_methods": sorted(source_set - bytecode_set), "bytecode_only_methods": sorted(bytecode_set - source_set), "status": "REVIEW_SOURCE_BYTECODE_DIVERGENCE"})
    result: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "bridgeforge_version": __version__,
        "input_mod": str(root),
        "mod_id": mod_id,
        "scope": {"mode": "READ_ONLY_STATIC", "runtime_claim": False, "dead_code_claims": False},
        "input_manifest_sha256": hashlib.sha256("\n".join(f"{node.get('path')}\0{node.get('sha256')}" for node in sorted(nodes.values(), key=lambda item: str(item.get("path", ""))) if node.get("path") and node.get("sha256")).encode("utf-8")).hexdigest(),
        "summary": {
            "file_count": len(files), "node_count": len(nodes), "edge_count": len(edges),
            "source_class_count": len(source_names), "package_class_count": len(package_names),
            "no_known_reference_count": len(no_known_reference), "duplicate_registration_risk_count": len(duplicate_risks),
            "scanner_finding_count": len(scanner_findings),
        },
        "nodes": sorted(nodes.values(), key=lambda item: str(item["id"])),
        "edges": [
            {"source": source, "target": target, "relation": relation, "evidence": evidence}
            for source, target, relation, evidence in sorted(edges)
        ],
        "lifecycle": {"hooks": sorted(lifecycle, key=lambda item: (str(item["hook"]), str(item["class"]), int(item["offset"]))), "registrations": sorted(registrations, key=lambda item: (str(item["file"]), int(item["offset"]))), "possible_duplicates": duplicate_risks},
        "persistent_state": sorted(persistent_candidates, key=lambda item: (str(item["class"]), str(item["field"]))),
        "source_package_authority": {
            "source_only_classes": sorted(source_names - package_names),
            "package_only_classes": sorted(package_names - source_names),
            "class_name_overlap": sorted(source_names & package_names),
            "method_inventory_divergence": method_divergence,
            "claim_limit": "Class-name overlap does not prove source and bytecode equivalence.",
        },
        "no_known_reference": no_known_reference,
        "scanner_findings": sorted(scanner_findings, key=lambda item: (str(item["id"]), str(item.get("file") or ""), json.dumps(item.get("evidence", [])))),
    }
    return result


def _architecture_markdown(result: dict[str, object]) -> str:
    summary = result["summary"]
    lifecycle = result["lifecycle"]
    authority = result["source_package_authority"]
    lines = [
        "# Architecture map", "",
        "Static, read-only evidence. This report makes no runtime or dead-code claim.", "",
        "## Summary", "",
        f"- Files: {summary['file_count']}", f"- Nodes: {summary['node_count']}", f"- Edges: {summary['edge_count']}",
        f"- Lifecycle hooks: {len(lifecycle['hooks'])}", f"- Registrations: {len(lifecycle['registrations'])}",
        f"- Possible duplicate registrations: {len(lifecycle['possible_duplicates'])}", "",
        "## Lifecycle", "",
    ]
    for hook in lifecycle["hooks"]:
        lines.append(f"- `{hook['hook']}`: `{hook['class']}` (`{hook['file']}`)")
    if not lifecycle["hooks"]:
        lines.append("- No known lifecycle hooks found by the static crawl.")
    lines.extend(["", "## No known reference", ""])
    for item in result["no_known_reference"]:
        lines.append(f"- `NO KNOWN REFERENCE (confidence {item['confidence']:.2f})`: `{item['class']}`. Checked: {', '.join(item['checked'])}. Not verified: {', '.join(item['not_verified'])}. This is not a dead-code verdict.")
    if not result["no_known_reference"]:
        lines.append("- None reported.")
    lines.extend(["", "## Source and package authority", "", f"- Source-only class names: {len(authority['source_only_classes'])}", f"- Package-only class names: {len(authority['package_only_classes'])}", f"- Overlapping class names: {len(authority['class_name_overlap'])}", f"- Method-inventory divergences requiring review: {len(authority['method_inventory_divergence'])}", f"- Limit: {authority['claim_limit']}", ""])
    return "\n".join(lines)


def write_archaeology(mod_directory: Path, output: Path, *, save_aliases: Path | None = None, vanilla_core: Path | None = None) -> dict[str, str]:
    root = _resolved_directory(mod_directory, "mod directory")
    out = output.expanduser().resolve()
    try:
        out.relative_to(root)
    except ValueError:
        pass
    else:
        raise DiscoveryError("archaeology output must be outside the selected mod directory")
    # --output names the discovery folder; the files go in its archaeology/ subfolder. Passing the
    # archaeology folder itself used to nest a second one and leave the old maps stale (Flu-X, 2026-09-13).
    if out.name.lower() == "archaeology":
        out = out.parent
    result = build_archaeology(root, save_aliases=save_aliases, vanilla_core=vanilla_core)
    archaeology_dir = out / "archaeology"
    architecture = _write_json(archaeology_dir / "architecture.json", result)
    cross_reference = _write_json(archaeology_dir / "cross_reference.json", {
        "schema_version": SCHEMA_VERSION, "input_mod": result["input_mod"],
        "nodes": result["nodes"], "edges": result["edges"], "no_known_reference": result["no_known_reference"],
    })
    markdown = out / "ARCHITECTURE_MAP.md"
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(_architecture_markdown(result), encoding="utf-8")
    return {"architecture": str(architecture), "cross_reference": str(cross_reference), "markdown": str(markdown)}


def _load_object(path: Path, label: str) -> dict[str, object]:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise DiscoveryError(f"{label} does not exist: {resolved}")
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise DiscoveryError(f"{label} must contain a JSON object")
    return payload


def build_behavior_model(architecture_path: Path) -> dict[str, object]:
    architecture = _load_object(architecture_path, "architecture map")
    if architecture.get("schema_version") != SCHEMA_VERSION:
        raise DiscoveryError("unsupported architecture schema_version")
    mod_id = re.sub(r"[^A-Za-z0-9]+", "", str(architecture.get("mod_id") or "MOD").upper())[:8] or "MOD"
    behavior_seeds: list[dict[str, object]] = []
    for hook in architecture.get("lifecycle", {}).get("hooks", []):
        behavior_seeds.append({"subsystem": "campaign-lifecycle", "entry_point": f"{hook['class']}#{hook['hook']}", "trigger": hook["hook"], "java_classes": [hook["class"]], "data_files": [], "lifecycle": hook["hook"], "evidence": [f"{hook['file']}@{hook['offset']}"]})
    for registration in architecture.get("lifecycle", {}).get("registrations", []):
        behavior_seeds.append({"subsystem": "runtime-registration", "entry_point": f"{registration['owner']}#{registration['call']}:{registration['target']}", "trigger": registration["call"], "registration_target": registration["target"], "java_classes": [registration["owner"]], "data_files": [], "lifecycle": "registered-runtime-object", "evidence": [f"{registration['file']}@{registration['offset']}: {registration['target']}"]})
    for node in architecture.get("nodes", []):
        if node.get("kind") == "data" and str(node.get("path", "")).lower().endswith((".faction", "rules.csv", ".system")):
            path = str(node["path"])
            behavior_seeds.append({"subsystem": "data-driven", "entry_point": path, "trigger": "loader", "java_classes": [], "data_files": [path], "lifecycle": "data-load", "evidence": [path]})
    local_class_names = {str(node.get("name")) for node in architecture.get("nodes", []) if isinstance(node, dict) and node.get("kind") == "class"}
    for edge in architecture.get("edges", []):
        if not isinstance(edge, dict) or edge.get("relation") != "resolves-data-reference" or not str(edge.get("source", "")).startswith("file:") or not str(edge.get("target", "")).startswith("class:"):
            continue
        path, class_name = str(edge["source"])[5:], str(edge["target"])[6:]
        if class_name not in local_class_names:
            continue
        behavior_seeds.append({"subsystem": "data-loaded-class", "entry_point": f"{path}:{class_name}", "trigger": "data-loader", "java_classes": [class_name], "data_files": [path], "lifecycle": "data-load", "evidence": [f"{path}: {edge.get('evidence')}"]})
    for finding in architecture.get("scanner_findings", []):
        if not isinstance(finding, dict):
            continue
        file = str(finding.get("file") or "(mod-wide)")
        behavior_seeds.append({
            "subsystem": "scanner-evidence", "entry_point": f"{finding.get('id')}:{file}",
            "trigger": "compatibility-check", "java_classes": [], "data_files": [] if file == "(mod-wide)" else [file],
            "lifecycle": "unknown", "evidence": [str(finding.get("explanation"))],
            "scanner_finding": {key: finding.get(key) for key in ("id", "severity", "classification", "confidence")},
        })
    merged_seeds: dict[tuple[str, str], dict[str, object]] = {}
    for seed in behavior_seeds:
        key = (str(seed["subsystem"]), str(seed["entry_point"]))
        if key not in merged_seeds:
            merged_seeds[key] = seed
        else:
            merged_seeds[key]["evidence"] = sorted(set(merged_seeds[key]["evidence"]) | set(seed["evidence"]))
    behaviors: list[dict[str, object]] = []
    graph_edges = [item for item in architecture.get("edges", []) if isinstance(item, dict)]
    known_classes = {str(node.get("name")) for node in architecture.get("nodes", []) if isinstance(node, dict) and node.get("kind") == "class"}
    for seed in sorted(merged_seeds.values(), key=lambda item: (str(item["subsystem"]), str(item["entry_point"]))):
        behavior_id = _stable_id("BEH", mod_id, seed["subsystem"], seed["entry_point"])
        sources = {f"class:{name}" for name in seed["java_classes"]} | {f"file:{name}" for name in seed["data_files"]}
        referenced = sorted({str(edge["target"]).split(":", 1)[-1] for edge in graph_edges if edge.get("source") in sources and str(edge.get("relation", "")).startswith(("imports", "string", "data", "bytecode", "resolves"))})
        external_apis = sorted(value for value in referenced if "." in value and value not in known_classes and value.startswith(("com.fs.starfarer.", "org.", "lunalib.", "exerelin.")))
        produced = sorted(set(seed["java_classes"] + ([str(seed["registration_target"])] if seed.get("registration_target") else [])))
        finding_fact = seed.get("scanner_finding") if isinstance(seed.get("scanner_finding"), dict) else None
        behaviors.append({
            "id": behavior_id, **seed, "ids_consumed": referenced, "ids_produced": produced,
            "persistent_state": [item for item in architecture.get("persistent_state", []) if item.get("class") in seed["java_classes"]],
            "external_apis": external_apis, "other_mods": [], "side_effects": [str(seed["evidence"][0])] if finding_fact else ["UNKNOWN_STATIC_ONLY"],
            "confidence": "STATIC_EVIDENCE", "runtime_verified": False,
        })
    duplicate_targets = {(entry["call"], entry["target"]) for entry in architecture.get("lifecycle", {}).get("possible_duplicates", [])}
    risks: list[dict[str, object]] = []
    hypotheses: list[dict[str, object]] = []
    unknowns: list[dict[str, object]] = []
    for behavior in behaviors:
        risk_items = ["runtime side effects are not established by static evidence"]
        scanner_finding = behavior.get("scanner_finding") if isinstance(behavior.get("scanner_finding"), dict) else None
        if scanner_finding:
            risk_items.append(f"scanner finding {scanner_finding.get('id')} is classified {scanner_finding.get('classification')}")
        has_persistent_candidate = any(item.get("status") == "CANDIDATE_NOT_RUNTIME_CONFIRMED" for item in behavior["persistent_state"])
        has_confirmed_persistence = any(item.get("status") == "CONFIRMED_SAVE_ALIAS" for item in behavior["persistent_state"])
        if has_persistent_candidate:
            risk_items.append("persistent fields are candidates but are not confirmed by a real save alias")
        possible_duplicate = (behavior["trigger"], behavior.get("registration_target")) in duplicate_targets
        if possible_duplicate:
            risk_items.append("registration may be reachable through multiple static routes")
        risk_id = _stable_id("RISK", behavior["id"], *risk_items)
        hyp_id = _stable_id("HYP", behavior["id"], "runtime-contract")
        unk_id = _stable_id("UNK", behavior["id"], "side-effects")
        high_risk = bool(scanner_finding and scanner_finding.get("classification") in {"MANUAL", "UNKNOWN"}) or has_confirmed_persistence or possible_duplicate
        risks.append({"id": risk_id, "behavior_id": behavior["id"], "level": "HIGH" if high_risk else "MEDIUM", "status": "OPEN", "narrative": "; ".join(risk_items), "evidence": behavior["evidence"]})
        observations = [
            {"kind": "instance-count", "when": "before-and-after-load"},
            {"kind": "state-snapshot", "when": "trigger-and-next-tick"},
        ]
        hypotheses.append({"id": hyp_id, "behavior_id": behavior["id"], "statement": f"{behavior['entry_point']} preserves its historical runtime contract", "unknowns": ["registered exactly once", "state survives save/load where applicable", "side effects remain continuous after load"], "required_observations": observations, "status": "PROPOSED"})
        unknowns.append({"id": unk_id, "behavior_id": behavior["id"], "subject": behavior["entry_point"], "status": "PRESERVE UNTIL EXPLAINED", "question": "What player-visible effects and invariants does this entry point establish?", "evidence": behavior["evidence"]})
    coverage_seed = [{"behavior_id": item["id"], "static": True, "runtime": False, "save_load": False, "compat": False, "human": False, "status": "OPEN"} for item in behaviors]
    return {"schema_version": SCHEMA_VERSION, "input_architecture": str(architecture_path.expanduser().resolve()), "mod_key": mod_id, "behaviors": behaviors, "risks": risks, "hypotheses": hypotheses, "unknowns": unknowns, "coverage_seed": coverage_seed}


def _behavior_markdown(title: str, entries: list[dict[str, object]], fields: tuple[str, ...]) -> str:
    lines = [f"# {title}", "", "Generated deterministically from static archaeology; runtime claims remain open.", ""]
    for entry in entries:
        lines.append(f"## {entry['id']}")
        lines.append("")
        for field in fields:
            value = entry.get(field)
            if value not in (None, [], ""):
                lines.append(f"- {field.replace('_', ' ').title()}: {json.dumps(value, sort_keys=True) if isinstance(value, (list, dict)) else value}")
        lines.append("")
    if not entries:
        lines.append("No entries were derived from the current static map.\n")
    return "\n".join(lines)


def write_behavior_model(architecture_path: Path, output: Path) -> dict[str, str]:
    result = build_behavior_model(architecture_path)
    out = output.expanduser().resolve()
    architecture = _load_object(architecture_path, "architecture map")
    input_mod = Path(str(architecture.get("input_mod", ""))).expanduser().resolve()
    if input_mod.is_dir():
        try:
            out.relative_to(input_mod)
        except ValueError:
            pass
        else:
            raise DiscoveryError("D1 output must be outside the selected mod directory")
    out.mkdir(parents=True, exist_ok=True)
    header = {"schema_version": SCHEMA_VERSION, "input_architecture": result["input_architecture"], "mod_key": result["mod_key"]}
    paths = {
        "behavior": _write_json(out / "behavior.json", {**header, "behaviors": result["behaviors"]}),
        "risks": _write_json(out / "risks.json", {**header, "risks": result["risks"]}),
        "hypotheses": _write_json(out / "hypotheses.json", {**header, "hypotheses": result["hypotheses"]}),
        "unknowns": _write_json(out / "unknowns.json", {**header, "unknowns": result["unknowns"]}),
        "coverage_seed": _write_json(out / "coverage_seed.json", {**header, "coverage": result["coverage_seed"]}),
    }
    markdown = {
        "behavior_markdown": (out / "BEHAVIOR_MAP.md", _behavior_markdown("Behaviour map", result["behaviors"], ("subsystem", "entry_point", "trigger", "lifecycle", "confidence", "evidence"))),
        "risk_markdown": (out / "RISK_REGISTER.md", _behavior_markdown("Risk register", result["risks"], ("behavior_id", "level", "status", "narrative", "evidence"))),
        "unknown_markdown": (out / "UNKNOWN_BEHAVIORS.md", _behavior_markdown("Unknown behaviours", result["unknowns"], ("behavior_id", "status", "subject", "question", "evidence"))),
    }
    for key, (path, text) in markdown.items():
        path.write_text(text, encoding="utf-8")
        paths[key] = path
    return {key: str(path) for key, path in paths.items()}


def _normalized_observations(payload: object) -> list[dict[str, object]]:
    raw = payload.get("observations") if isinstance(payload, dict) else payload
    if not isinstance(raw, list):
        raise DiscoveryError("observation input must be a list or an object with an observations list")
    normalized: list[dict[str, object]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise DiscoveryError(f"observation {index} must be an object")
        observation, subject = item.get("observation"), item.get("subject")
        if not isinstance(observation, str) or not observation or not isinstance(subject, str) or not subject:
            raise DiscoveryError(f"observation {index} requires non-empty observation and subject")
        fields = item.get("fields")
        if fields is None and "field" in item and "value" in item:
            fields = {str(item["field"]): item["value"]}
        if not isinstance(fields, dict) or not fields:
            raise DiscoveryError(f"observation {index} requires fields or field/value")
        normalized.append({
            "behavior_id": str(item["behavior_id"]) if item.get("behavior_id") else None,
            "observation": observation,
            "subject": subject,
            "fields": {str(key): fields[key] for key in sorted(fields, key=str)},
            "source": str(item.get("source", "captured")),
        })
    return sorted(normalized, key=lambda item: (str(item.get("behavior_id") or ""), str(item["observation"]), str(item["subject"]), json.dumps(item["fields"], sort_keys=True)))


def build_probe_baseline(observation_input: Path, *, build: str, scenario: str, reference_kind: str = "build") -> dict[str, object]:
    if not build.strip() or not scenario.strip():
        raise DiscoveryError("build and scenario must be non-empty")
    path = observation_input.expanduser().resolve()
    if not path.is_file():
        raise DiscoveryError(f"observation input does not exist: {path}")
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8-sig"))
    observations = _normalized_observations(payload)
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "NO_VERDICT_BASELINE",
        "reference": {"kind": reference_kind, "id": build},
        "scenario": scenario,
        "input": {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()},
        "observations": observations,
        "observation_count": len(observations),
        "verdict": None,
    }


def write_probe_baseline(observation_input: Path, output: Path, *, build: str, scenario: str, reference_kind: str = "build") -> Path:
    result = build_probe_baseline(observation_input, build=build, scenario=scenario, reference_kind=reference_kind)
    path = output.expanduser().resolve()
    if path.exists() and path.is_dir():
        safe_build = re.sub(r"[^A-Za-z0-9._-]+", "-", build)
        safe_scenario = re.sub(r"[^A-Za-z0-9._-]+", "-", scenario)
        path = path / f"baseline-{safe_build}-{safe_scenario}.json"
    return _write_json(path, result)


def build_save_baseline(
    save: Path,
    *,
    build: str,
    scenario: str,
    track_classes: Iterable[str] = (),
    track_ids: Iterable[str] = (),
    mod_dir: Path | None = None,
) -> dict[str, object]:
    """Convert read-only historical-save evidence into the same no-verdict D2 contract."""
    if not build.strip() or not scenario.strip():
        raise DiscoveryError("build and scenario must be non-empty")
    inspected = inspect_save(
        save,
        track_classes=list(track_classes),
        track_ids=list(track_ids),
        mod_dir=mod_dir,
    )
    observations: list[dict[str, object]] = []
    for item in inspected["tracked_objects"]:
        observations.append({
            "behavior_id": None,
            "observation": "save.object",
            "subject": f"{item['class']}@{item['path']}",
            "fields": item["fields"],
            "source": "save-inspect",
        })
    # XStream writes each faction in full wherever it is first referenced (inside some fleet or
    # route), so a known list's path changes from save to save. List tag + owning faction is the
    # stable subject; the path (plus an occurrence number) is only a fallback for owner-less lists.
    # behavior-diff refuses duplicate subjects, and unstable ones read as missing/new behaviour.
    seen_subjects: Counter = Counter()
    for item in inspected["known_lists"]:
        subject = f"{item['tag']}[{item['owner']}]" if item.get("owner") else f"{item['tag']}@{item['path']}"
        seen_subjects[subject] += 1
        if seen_subjects[subject] > 1:
            subject += f"#{seen_subjects[subject]}"
        observations.append({
            "behavior_id": None,
            "observation": "save.known-list",
            "subject": subject,
            "fields": {"size": item["size"]},
            "source": "save-inspect-heuristic",
        })
    hits: dict[str, list[str]] = defaultdict(list)
    for item in inspected["tracked_id_hits"]:
        hits[str(item["id"])].append(str(item["path"]))
    for tracked_id, paths in sorted(hits.items()):
        observations.append({
            "behavior_id": None,
            "observation": "save.id",
            "subject": tracked_id,
            "fields": {"occurrences": len(paths), "paths": sorted(paths)},
            "source": "save-inspect",
        })
    counts = inspected.get("mod_object_counts")
    if isinstance(counts, dict):
        for namespace, count in sorted(counts.get("by_namespace", {}).items()):
            observations.append({
                "behavior_id": None,
                "observation": "save.mod-object-count",
                "subject": namespace,
                "fields": {"count": count},
                "source": "save-inspect",
            })
        observations.append({
            "behavior_id": None,
            "observation": "save.mod-object-count",
            "subject": "TOTAL",
            "fields": {"count": counts["total"]},
            "source": "save-inspect",
        })
    observations = _normalized_observations({"observations": observations})
    campaign = Path(str(inspected["save"]))
    raw = campaign.read_bytes()
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "NO_VERDICT_BASELINE",
        "reference": {"kind": "old-game-rig", "id": build},
        "scenario": scenario,
        "input": {"kind": "starsector-save", "path": str(campaign), "sha256": hashlib.sha256(raw).hexdigest()},
        "observations": observations,
        "observation_count": len(observations),
        "verdict": None,
    }


def write_save_baseline(save: Path, output: Path, **kwargs: Any) -> Path:
    result = build_save_baseline(save, **kwargs)
    return _write_json(Path(output).expanduser().resolve(), result)


def synthesize_tests(hypotheses_path: Path) -> dict[str, object]:
    payload = _load_object(hypotheses_path, "hypotheses")
    hypotheses = payload.get("hypotheses")
    if payload.get("schema_version") != SCHEMA_VERSION or not isinstance(hypotheses, list):
        raise DiscoveryError("hypotheses file has an unsupported schema or no hypotheses list")
    tests: list[dict[str, object]] = []
    for hypothesis in sorted(hypotheses, key=lambda item: str(item.get("id", ""))):
        hyp_id = str(hypothesis.get("id", ""))
        behavior_id = str(hypothesis.get("behavior_id", ""))
        for index, observation in enumerate(hypothesis.get("required_observations", []), start=1):
            tests.append({
                "id": _stable_id("TEST", hyp_id, index, observation),
                "hypothesis_id": hyp_id,
                "behavior_id": behavior_id,
                "kind": observation.get("kind", "observation") if isinstance(observation, dict) else "observation",
                "setup": "Reproduce the named scenario from an immutable build and capture the precondition.",
                "action": observation.get("when", "trigger behavior") if isinstance(observation, dict) else str(observation),
                "adversarial_variants": ["repeat the trigger", "save and reload between trigger and observation", "run with the declared compatibility set"],
                "acceptance": "The captured observation remains explainable and consistent with the approved behavior contract.",
                "stop_conditions": ["unexpected save mutation", "unattributed fatal error", "evidence input hash changed"],
                "status": "PROPOSED",
            })
    return {"schema_version": SCHEMA_VERSION, "source": str(hypotheses_path.expanduser().resolve()), "tests": tests}


def write_synthesized_tests(hypotheses_path: Path, output: Path) -> Path:
    return _write_json(output.expanduser().resolve(), synthesize_tests(hypotheses_path))


def _artifact_ids(paths: Iterable[Path]) -> set[str]:
    result: set[str] = set()
    for path in paths:
        payload = _load_object(path, "linked artifact")
        for key in ("risks", "hypotheses", "tests", "behaviors"):
            entries = payload.get(key)
            if isinstance(entries, list):
                result.update(str(item.get("id")) for item in entries if isinstance(item, dict) and item.get("id"))
    return result


def check_expected_changes(expected_path: Path, *, linked_artifacts: Iterable[Path] = (), known_builds: Iterable[str] = ()) -> dict[str, object]:
    path = expected_path.expanduser().resolve()
    payload = _load_lenient_json_file(path)
    if not isinstance(payload, dict):
        raise DiscoveryError("expected-changes file must contain a JSON object")
    errors: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append({"code": "unsupported-schema", "value": payload.get("schema_version")})
    changes = payload.get("changes")
    if not isinstance(changes, list):
        errors.append({"code": "changes-not-list"})
        changes = []
    linked_ids = _artifact_ids(linked_artifacts)
    build_set = set(map(str, known_builds))
    seen: set[str] = set()
    required = {"id", "build", "layer", "summary", "why", "match", "status"}
    for index, change in enumerate(changes):
        if not isinstance(change, dict):
            errors.append({"code": "change-not-object", "index": index})
            continue
        change_id = str(change.get("id", ""))
        missing = sorted(required - set(change))
        if missing:
            errors.append({"code": "missing-fields", "id": change_id, "fields": missing})
        if change_id in seen:
            errors.append({"code": "duplicate-id", "id": change_id})
        seen.add(change_id)
        if not re.fullmatch(r"EXP-[A-Za-z0-9]+-\d{3,}", change_id):
            errors.append({"code": "invalid-id", "id": change_id})
        if change.get("status") not in {"PROPOSED", "APPROVED", "RETIRED"}:
            errors.append({"code": "invalid-status", "id": change_id, "value": change.get("status")})
        elif change.get("status") == "APPROVED" and not all(change.get(key) for key in ("approved_by", "approved_on")):
            errors.append({"code": "approval-provenance-missing", "id": change_id})
        elif change.get("status") == "RETIRED" and not all(change.get(key) for key in ("retired_by", "retired_why")):
            errors.append({"code": "retirement-provenance-missing", "id": change_id})
        if change.get("layer") not in {"runtime", "save", "static"}:
            errors.append({"code": "invalid-layer", "id": change_id, "value": change.get("layer")})
        if build_set and str(change.get("build")) not in build_set:
            errors.append({"code": "unknown-build", "id": change_id, "build": change.get("build")})
        match = change.get("match")
        if not isinstance(match, dict) or match.get("change") not in {"from_to", "count", "added", "removed", "renamed", "any"}:
            errors.append({"code": "invalid-matcher", "id": change_id})
        elif match.get("change") == "any":
            warnings.append({"code": "broad-any-matcher", "id": change_id})
        links = change.get("links", {})
        if links and not isinstance(links, dict):
            errors.append({"code": "links-not-object", "id": change_id})
        elif isinstance(links, dict):
            if not any(links.get(kind) for kind in ("risk", "hyp", "test")):
                errors.append({"code": "missing-modernization-breadcrumb", "id": change_id})
            for kind in ("risk", "hyp", "test"):
                for linked in links.get(kind, []):
                    if linked_ids and str(linked) not in linked_ids:
                        errors.append({"code": "unknown-link", "id": change_id, "kind": kind, "target": linked})
    return {"schema_version": SCHEMA_VERSION, "file": str(path), "status": "PASS" if not errors else "FAIL", "change_count": len(changes), "errors": errors, "warnings": warnings, "changes": changes}


def _write_expected_decision(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        backup = path.with_suffix(path.suffix + ".before-last-edit")
        backup.write_bytes(path.read_bytes())
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def add_expected_change(
    expected_path: Path,
    *,
    mod_id: str,
    change_id: str,
    build: str,
    layer: str,
    summary: str,
    why: str,
    match: dict[str, object],
    links: dict[str, list[str]] | None = None,
    proposed_by: str = "agent",
) -> dict[str, object]:
    if not re.fullmatch(r"EXP-[A-Za-z0-9]+-\d{3,}", change_id):
        raise DiscoveryError("expected-change id must match EXP-<MOD>-nnn")
    if layer not in {"runtime", "save", "static"}:
        raise DiscoveryError(f"invalid expected-change layer: {layer}")
    matcher_kind = match.get("change")
    if matcher_kind in {"from_to", "count"} and not {"from", "to"}.issubset(match):
        raise DiscoveryError(f"{matcher_kind} matcher requires --from and --to")
    if matcher_kind == "renamed" and not {"old", "new"}.issubset(match):
        raise DiscoveryError("renamed matcher requires --old and --new")
    if matcher_kind not in {"from_to", "count", "added", "removed", "renamed", "any"}:
        raise DiscoveryError(f"invalid expected-change matcher: {matcher_kind}")
    path = expected_path.expanduser().resolve()
    if path.exists():
        payload = _load_lenient_json_file(path)
        if not isinstance(payload, dict):
            raise DiscoveryError("expected-changes file must contain a JSON object")
    else:
        payload = {"schema_version": SCHEMA_VERSION, "mod_id": mod_id, "changes": []}
    if payload.get("mod_id") != mod_id:
        raise DiscoveryError(f"mod id mismatch: file has {payload.get('mod_id')!r}, command supplied {mod_id!r}")
    changes = payload.setdefault("changes", [])
    if not isinstance(changes, list):
        raise DiscoveryError("expected-changes changes must be a list")
    if any(isinstance(item, dict) and item.get("id") == change_id for item in changes):
        raise DiscoveryError(f"expected-change id already exists: {change_id}")
    entry = {"id": change_id, "build": build, "layer": layer, "summary": summary, "why": why, "links": links or {}, "match": match, "status": "PROPOSED", "proposed_by": proposed_by}
    changes.append(entry)
    changes.sort(key=lambda item: str(item.get("id", "")) if isinstance(item, dict) else "")
    _write_expected_decision(path, payload)
    return {"status": "UPDATED", "action": "add", "id": change_id, "file": str(path), "backup": str(path.with_suffix(path.suffix + ".before-last-edit")) if path.with_suffix(path.suffix + ".before-last-edit").exists() else None}


def update_expected_change_status(expected_path: Path, change_id: str, *, status: str, actor: str, on: str | None = None, why: str | None = None) -> dict[str, object]:
    if status not in {"APPROVED", "RETIRED"}:
        raise DiscoveryError(f"unsupported expected-change transition: {status}")
    path = expected_path.expanduser().resolve()
    payload = _load_lenient_json_file(path)
    if not isinstance(payload, dict) or not isinstance(payload.get("changes"), list):
        raise DiscoveryError("expected-changes file must contain a changes list")
    matches = [item for item in payload["changes"] if isinstance(item, dict) and item.get("id") == change_id]
    if len(matches) != 1:
        raise DiscoveryError(f"expected exactly one entry for {change_id}; found {len(matches)}")
    entry = matches[0]
    if status == "APPROVED" and entry.get("status") != "PROPOSED":
        raise DiscoveryError(f"only a PROPOSED entry can be approved; {change_id} is {entry.get('status')}")
    if status == "APPROVED" and not on:
        raise DiscoveryError("approving an expected change requires an approval date")
    if status == "RETIRED" and not why:
        raise DiscoveryError("retiring an expected change requires --why")
    entry["status"] = status
    key = "approved" if status == "APPROVED" else "retired"
    entry[f"{key}_by"] = actor
    if on:
        entry[f"{key}_on"] = on
    if why:
        entry["retired_why"] = why
    _write_expected_decision(path, payload)
    return {"status": "UPDATED", "action": key, "id": change_id, "file": str(path), "backup": str(path.with_suffix(path.suffix + ".before-last-edit"))}


def _flat_observations(baseline: dict[str, object]) -> dict[tuple[str, str, str, str], object]:
    result: dict[tuple[str, str, str, str], object] = {}
    for item in baseline.get("observations", []):
        if not isinstance(item, dict) or not isinstance(item.get("fields"), dict):
            continue
        for field, value in item["fields"].items():
            key = (str(item.get("behavior_id") or ""), str(item.get("observation")), str(item.get("subject")), str(field))
            if key in result:
                raise DiscoveryError(f"duplicate observation field: {key}")
            result[key] = value
    return result


def _value_matches(pattern: object, value: object) -> bool:
    if pattern == "*":
        return True
    if isinstance(pattern, str):
        if re.fullmatch(r">-?\d+(?:\.\d+)?", pattern):
            return isinstance(value, (int, float)) and value > float(pattern[1:])
        if re.fullmatch(r"<-?\d+(?:\.\d+)?", pattern):
            return isinstance(value, (int, float)) and value < float(pattern[1:])
        range_match = re.fullmatch(r"(-?\d+(?:\.\d+)?)\.\.(-?\d+(?:\.\d+)?)", pattern)
        if range_match:
            return isinstance(value, (int, float)) and float(range_match.group(1)) <= value <= float(range_match.group(2))
    return pattern == value


def _glob_matches(pattern: object, value: str) -> bool:
    regex = "^" + re.escape(str(pattern)).replace(r"\*", ".*") + "$"
    return bool(re.match(regex, value))


def _change_matches(change: dict[str, object], delta: dict[str, object]) -> bool:
    match = change.get("match")
    if not isinstance(match, dict):
        return False
    if change.get("layer") and change.get("layer") != delta.get("layer"):
        return False
    if delta.get("before") == delta.get("after"):
        return False
    for field in ("observation", "subject", "field"):
        if field in match and not _glob_matches(match[field], str(delta.get(field, ""))):
            return False
    kind = match.get("change")
    before, after = delta.get("before"), delta.get("after")
    if kind in {"from_to", "count"}:
        return _value_matches(match.get("from", "*"), before) and _value_matches(match.get("to", "*"), after)
    if kind == "added":
        return before is None and after is not None
    if kind == "removed":
        return before is not None and after is None
    if kind == "renamed":
        return before == match.get("old") and after == match.get("new")
    return kind == "any"


def _flat_static_map(payload: dict[str, object]) -> dict[tuple[str, str, str], object]:
    result: dict[tuple[str, str, str], object] = {}
    for node in payload.get("nodes", []):
        if isinstance(node, dict) and node.get("kind") in {"class", "data", "resource"}:
            subject = str(node.get("name") or node.get("path") or node.get("id"))
            result[(f"static.{node['kind']}", subject, "present")] = True
    lifecycle = payload.get("lifecycle", {})
    if isinstance(lifecycle, dict):
        for hook in lifecycle.get("hooks", []):
            if isinstance(hook, dict):
                result[("static.lifecycle", str(hook.get("class")), str(hook.get("hook")))] = True
        for registration in lifecycle.get("registrations", []):
            if isinstance(registration, dict):
                result[("static.registration", str(registration.get("owner")), f"{registration.get('call')}:{registration.get('target')}")] = True
    for field in payload.get("persistent_state", []):
        if isinstance(field, dict):
            result[("static.persistent-field", str(field.get("class")), str(field.get("field")))] = field.get("status")
    return result


def behavior_diff(before_path: Path, after_path: Path, *, expected_path: Path | None = None, before_map_path: Path | None = None, after_map_path: Path | None = None) -> dict[str, object]:
    before = _load_object(before_path, "before baseline")
    after = _load_object(after_path, "after baseline")
    for label, payload in (("before", before), ("after", after)):
        if payload.get("schema_version") != SCHEMA_VERSION or payload.get("mode") != "NO_VERDICT_BASELINE":
            raise DiscoveryError(f"{label} baseline has an unsupported schema or mode")
    before_flat, after_flat = _flat_observations(before), _flat_observations(after)
    expected = check_expected_changes(expected_path)["changes"] if expected_path else []
    deltas: list[dict[str, object]] = []
    matched_expected: set[str] = set()
    for key in sorted(set(before_flat) | set(after_flat)):
        behavior_id, observation, subject, field = key
        old, new = before_flat.get(key), after_flat.get(key)
        delta = {"layer": "runtime", "behavior_id": behavior_id or None, "observation": observation, "subject": subject, "field": field, "before": old, "after": new}
        if key in before_flat and key in after_flat and old == new:
            category = "UNCHANGED"
        elif key not in before_flat:
            category = "NEW_BEHAVIOR"
        elif key not in after_flat:
            category = "MISSING_OBSERVATION"
        else:
            category = "UNEXPLAINED_CHANGE"
        matches = [item for item in expected if isinstance(item, dict) and item.get("status") != "RETIRED" and _change_matches(item, delta)]
        approved = [item for item in matches if item.get("status") == "APPROVED"]
        proposed = [item for item in matches if item.get("status") == "PROPOSED"]
        if approved:
            category = "EXPECTED_CHANGE"
            matched_expected.update(str(item["id"]) for item in approved)
        elif proposed:
            category = "PENDING_APPROVAL"
            matched_expected.update(str(item["id"]) for item in proposed)
        delta["category"] = category
        delta["expected_change_ids"] = [str(item["id"]) for item in approved + proposed]
        deltas.append(delta)
    if (before_map_path is None) != (after_map_path is None):
        raise DiscoveryError("static map diff requires both before_map_path and after_map_path")
    if before_map_path is not None and after_map_path is not None:
        before_map_payload = _load_object(before_map_path, "before architecture map")
        after_map_payload = _load_object(after_map_path, "after architecture map")
        if before_map_payload.get("schema_version") != SCHEMA_VERSION or after_map_payload.get("schema_version") != SCHEMA_VERSION:
            raise DiscoveryError("architecture map has an unsupported schema_version")
        before_map = _flat_static_map(before_map_payload)
        after_map = _flat_static_map(after_map_payload)
        for key in sorted(set(before_map) | set(after_map)):
            observation, subject, field = key
            old, new = before_map.get(key), after_map.get(key)
            delta = {"layer": "static", "behavior_id": None, "observation": observation, "subject": subject, "field": field, "before": old, "after": new}
            if key in before_map and key in after_map and old == new:
                category = "UNCHANGED"
            elif key not in before_map:
                category = "NEW_BEHAVIOR"
            elif key not in after_map:
                category = "MISSING_OBSERVATION"
            else:
                category = "UNEXPLAINED_CHANGE"
            matches = [item for item in expected if isinstance(item, dict) and item.get("status") != "RETIRED" and _change_matches(item, delta)]
            approved = [item for item in matches if item.get("status") == "APPROVED"]
            proposed = [item for item in matches if item.get("status") == "PROPOSED"]
            if approved:
                category = "EXPECTED_CHANGE"
                matched_expected.update(str(item["id"]) for item in approved)
            elif proposed:
                category = "PENDING_APPROVAL"
                matched_expected.update(str(item["id"]) for item in proposed)
            delta["category"] = category
            delta["expected_change_ids"] = [str(item["id"]) for item in approved + proposed]
            deltas.append(delta)
    for change in expected:
        if isinstance(change, dict) and change.get("status") == "APPROVED" and str(change.get("id")) not in matched_expected:
            match = change.get("match", {})
            deltas.append({"layer": change.get("layer"), "behavior_id": None, "observation": match.get("observation"), "subject": match.get("subject"), "field": match.get("field"), "before": None, "after": None, "category": "EXPECTED_BUT_ABSENT", "expected_change_ids": [str(change["id"])]})
    deltas.sort(key=lambda item: (str(item.get("layer")), str(item.get("behavior_id") or ""), str(item.get("observation")), str(item.get("subject")), str(item.get("field")), str(item.get("category"))))
    counts = Counter(str(item["category"]) for item in deltas)
    blocking = sum(counts[name] for name in ("UNEXPLAINED_CHANGE", "PENDING_APPROVAL", "EXPECTED_BUT_ABSENT", "MISSING_OBSERVATION", "NEW_BEHAVIOR"))
    return {"schema_version": SCHEMA_VERSION, "before": str(before_path.expanduser().resolve()), "after": str(after_path.expanduser().resolve()), "before_map": str(before_map_path.expanduser().resolve()) if before_map_path else None, "after_map": str(after_map_path.expanduser().resolve()) if after_map_path else None, "expected_changes": str(expected_path.expanduser().resolve()) if expected_path else None, "status": "PASS" if blocking == 0 else "REVIEW_REQUIRED", "counts": dict(sorted(counts.items())), "blocking_count": blocking, "deltas": deltas}


def evaluate_behavior_release(diff_path: Path, *, risks_path: Path | None = None, unknowns_path: Path | None = None) -> dict[str, object]:
    diff = _load_object(diff_path, "behavior diff")
    if diff.get("schema_version") != SCHEMA_VERSION:
        raise DiscoveryError("behavior diff has an unsupported schema_version")
    blocking_reasons = []
    if diff.get("status") != "PASS":
        blocking_reasons.append("behavior-diff-has-unresolved-deltas")
    high_open: list[str] = []
    if risks_path:
        risk_payload = _load_object(risks_path, "risks")
        if risk_payload.get("schema_version") != SCHEMA_VERSION or not isinstance(risk_payload.get("risks"), list):
            raise DiscoveryError("risks file has an unsupported schema or no risks list")
        risks = risk_payload["risks"]
        high_open = [str(item.get("id")) for item in risks if isinstance(item, dict) and item.get("level") == "HIGH" and item.get("status") in {"OPEN", "UNKNOWN", "PRESERVE UNTIL EXPLAINED"}]
    preserved_unknowns: list[str] = []
    if unknowns_path:
        unknown_payload = _load_object(unknowns_path, "unknowns")
        if unknown_payload.get("schema_version") != SCHEMA_VERSION or not isinstance(unknown_payload.get("unknowns"), list):
            raise DiscoveryError("unknowns file has an unsupported schema or no unknowns list")
        unknowns = unknown_payload["unknowns"]
        preserved_unknowns = [str(item.get("id")) for item in unknowns if isinstance(item, dict) and item.get("status") in {"UNKNOWN", "PRESERVE UNTIL EXPLAINED"}]
    if high_open:
        blocking_reasons.append("high-risk-behavior-remains-open")
    if preserved_unknowns:
        blocking_reasons.append("unknown-behavior-lacks-written-decision")
    return {"schema_version": SCHEMA_VERSION, "status": "PASS" if not blocking_reasons else "FAIL", "blocking_reasons": blocking_reasons, "high_risks_open": high_open, "unknowns_open": preserved_unknowns, "diff_status": diff.get("status")}


DECIDED_UNKNOWN_STATUSES = frozenset({"EXPLAINED", "LIKELY INTENTIONAL", "LIKELY DEFECT"})
DECIDED_RISK_STATUSES = frozenset({"MITIGATED", "ACCEPTED", "EXPLAINED"})
_DECISION_SELECTORS = frozenset({"ids", "lifecycle", "subsystem", "entry_point_prefix"})


def _decision_selects(select: dict, item: dict, behavior: dict) -> bool:
    ids = set(select.get("ids") or [])
    if "ids" in select and item.get("id") not in ids and item.get("behavior_id") not in ids:
        return False
    if "lifecycle" in select and behavior.get("lifecycle") != select["lifecycle"]:
        return False
    if "subsystem" in select and behavior.get("subsystem") != select["subsystem"]:
        return False
    if "entry_point_prefix" in select and not str(behavior.get("entry_point", "")).startswith(str(select["entry_point_prefix"])):
        return False
    return True


def apply_behavior_decisions(discovery_dir: Path, decisions_path: Path) -> dict[str, object]:
    """Apply written decisions to a D1 model's risks and unknowns, leaving the generated files untouched.

    Each decision selects items (by risk/unknown/behavior id, lifecycle, subsystem or entry-point
    prefix) and must carry a status, why, by and on (YYYY-MM-DD). A decision that selects nothing is
    refused as stale, so regenerated maps can't silently drop a decision.
    """
    base = _resolved_directory(discovery_dir, "discovery directory")
    behavior = _load_object(base / "behavior.json", "behavior map")
    risks = _load_object(base / "risks.json", "risks")
    unknowns = _load_object(base / "unknowns.json", "unknowns")
    decisions_file = Path(decisions_path).expanduser().resolve()
    decisions = _load_object(decisions_file, "decisions")
    if decisions.get("schema_version") != SCHEMA_VERSION or not isinstance(decisions.get("decisions"), list):
        raise DiscoveryError("decisions file needs schema_version 1 and a decisions list")
    by_behavior = {b["id"]: b for b in behavior.get("behaviors", []) if isinstance(b, dict)}
    items = {"risks": risks.get("risks", []), "unknowns": unknowns.get("unknowns", [])}
    applied: Counter = Counter()
    for index, decision in enumerate(decisions["decisions"], start=1):
        where = f"decision {index}"
        for field in ("status", "why", "by", "on"):
            if not str(decision.get(field) or "").strip():
                raise DiscoveryError(f"{where}: missing {field}")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(decision["on"])):
            raise DiscoveryError(f"{where}: 'on' must be YYYY-MM-DD")
        select = decision.get("select") or {}
        if not select or set(select) - _DECISION_SELECTORS:
            raise DiscoveryError(f"{where}: select needs only keys from {sorted(_DECISION_SELECTORS)}")
        matched = 0
        for kind in decision.get("applies_to") or ["unknowns", "risks"]:
            if kind not in items:
                raise DiscoveryError(f"{where}: applies_to must be unknowns and/or risks")
            allowed = DECIDED_UNKNOWN_STATUSES if kind == "unknowns" else DECIDED_RISK_STATUSES
            if decision["status"] not in allowed:
                raise DiscoveryError(f"{where}: status {decision['status']!r} is not valid for {kind} ({sorted(allowed)})")
            for item in items[kind]:
                if isinstance(item, dict) and _decision_selects(select, item, by_behavior.get(item.get("behavior_id"), {})):
                    item["status"] = decision["status"]
                    item["decision"] = {
                        "why": decision["why"],
                        "evidence": list(decision.get("evidence") or []),
                        "by": decision["by"],
                        "on": decision["on"],
                        "source": f"{decisions_file.name}#{index}",
                    }
                    matched += 1
                    applied[kind] += 1
        if not matched:
            raise DiscoveryError(f"{where}: selects nothing (stale after regenerating the maps?)")
    open_unknowns = [u["id"] for u in items["unknowns"] if isinstance(u, dict) and u.get("status") not in DECIDED_UNKNOWN_STATUSES]
    open_high = [r["id"] for r in items["risks"] if isinstance(r, dict) and r.get("level") == "HIGH" and r.get("status") in {"OPEN", "UNKNOWN", "PRESERVE UNTIL EXPLAINED"}]
    return {
        "risks": risks,
        "unknowns": unknowns,
        "summary": {"decisions": len(decisions["decisions"]), "applied": dict(applied), "unknowns_open": open_unknowns, "high_risks_open": open_high},
    }


def write_behavior_decisions(discovery_dir: Path, decisions_path: Path, output: Path | None = None) -> dict[str, object]:
    """Write risks.decided.json / unknowns.decided.json for the release gate."""
    result = apply_behavior_decisions(discovery_dir, decisions_path)
    out = Path(output or discovery_dir).expanduser().resolve()
    risks_path = _write_json(out / "risks.decided.json", result["risks"])
    unknowns_path = _write_json(out / "unknowns.decided.json", result["unknowns"])
    return {"schema_version": SCHEMA_VERSION, "risks": str(risks_path), "unknowns": str(unknowns_path), **result["summary"]}


def build_coverage(behavior_path: Path, *, baselines: Iterable[Path] = (), diff_path: Path | None = None, tests_path: Path | None = None, unknowns_path: Path | None = None) -> dict[str, object]:
    behavior_payload = _load_object(behavior_path, "behavior map")
    if behavior_payload.get("schema_version") != SCHEMA_VERSION or not isinstance(behavior_payload.get("behaviors"), list):
        raise DiscoveryError("behavior map has an unsupported schema or no behaviors list")
    behaviors = behavior_payload["behaviors"]
    runtime_ids: set[str] = set()
    save_ids: set[str] = set()
    compat_ids: set[str] = set()
    for path in baselines:
        baseline = _load_object(path, "baseline")
        if baseline.get("schema_version") != SCHEMA_VERSION or baseline.get("mode") != "NO_VERDICT_BASELINE":
            raise DiscoveryError("baseline has an unsupported schema or mode")
        scenario = str(baseline.get("scenario", "")).lower()
        for item in baseline.get("observations", []):
            if isinstance(item, dict) and item.get("behavior_id"):
                behavior_id = str(item["behavior_id"])
                runtime_ids.add(behavior_id)
                if "save" in scenario or "load" in scenario:
                    save_ids.add(behavior_id)
                if "compat" in scenario:
                    compat_ids.add(behavior_id)
    diff_ids: set[str] = set()
    if diff_path:
        diff = _load_object(diff_path, "behavior diff")
        if diff.get("schema_version") != SCHEMA_VERSION:
            raise DiscoveryError("behavior diff has an unsupported schema_version")
        diff_ids = {str(item["behavior_id"]) for item in diff.get("deltas", []) if isinstance(item, dict) and item.get("behavior_id") and item.get("category") in {"UNCHANGED", "EXPECTED_CHANGE"}}
    tested_ids: set[str] = set()
    if tests_path:
        test_payload = _load_object(tests_path, "tests")
        if test_payload.get("schema_version") != SCHEMA_VERSION or not isinstance(test_payload.get("tests"), list):
            raise DiscoveryError("tests file has an unsupported schema or no tests list")
        tests = test_payload["tests"]
        tested_ids = {str(item["behavior_id"]) for item in tests if isinstance(item, dict) and item.get("behavior_id") and item.get("status") in {"PASS", "COVERED"}}
    rows = []
    for behavior in sorted((item for item in behaviors if isinstance(item, dict)), key=lambda item: str(item.get("id", ""))):
        behavior_id = str(behavior.get("id"))
        runtime = behavior_id in runtime_ids
        differential = behavior_id in diff_ids
        save_load = behavior_id in save_ids
        compat = behavior_id in compat_ids
        human = behavior_id in tested_ids
        covered = runtime and differential and (not behavior.get("persistent_state") or save_load) and (not behavior.get("other_mods") or compat)
        rows.append({"behavior_id": behavior_id, "static": True, "runtime": runtime, "differential": differential, "save_load": save_load, "compat": compat, "human": human, "status": "COVERED" if covered else "OPEN"})
    unknown_open = 0
    if unknowns_path:
        unknown_payload = _load_object(unknowns_path, "unknowns")
        if unknown_payload.get("schema_version") != SCHEMA_VERSION or not isinstance(unknown_payload.get("unknowns"), list):
            raise DiscoveryError("unknowns file has an unsupported schema or no unknowns list")
        unknowns = unknown_payload["unknowns"]
        unknown_open = sum(1 for item in unknowns if isinstance(item, dict) and item.get("status") not in {"EXPLAINED", "LIKELY INTENTIONAL", "LIKELY DEFECT"})
    counts = Counter(row["status"] for row in rows)
    need_runtime = sum(1 for row in rows if not row["runtime"])
    need_human = sum(1 for row in rows if row["runtime"] and not row["human"])
    residual = []
    for row in rows:
        if row["status"] == "COVERED":
            continue
        reasons = []
        if not row["runtime"]:
            reasons.append("runtime evidence missing or unresolved")
        elif not row["differential"]:
            reasons.append("D5 differential evidence missing or unresolved")
        if not row["save_load"]:
            reasons.append("save/load evidence not supplied")
        if not row["compat"]:
            reasons.append("compat-set evidence not supplied")
        if not row["human"]:
            reasons.append("human/adversarial test not recorded as passed")
        residual.append({"behavior_id": row["behavior_id"], "reasons": reasons, "action": "Run only the missing evidence rows; do not repeat covered checks."})
    return {"schema_version": SCHEMA_VERSION, "coverage": rows, "residual_human_tests": residual, "counts": {"known_behaviors": len(rows), "covered": counts["COVERED"], "open": counts["OPEN"], "need_runtime_evidence": need_runtime, "need_human_judgment": need_human, "unknowns_open": unknown_open}, "percentage": None, "status": "PASS" if counts["OPEN"] == 0 and unknown_open == 0 else "OPEN"}


def write_coverage(behavior_path: Path, output: Path, **kwargs: object) -> Path:
    return _write_json(output.expanduser().resolve(), build_coverage(behavior_path, **kwargs))
