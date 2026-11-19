from __future__ import annotations

import csv
import hashlib
import json
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from . import __version__
from bridgeforge.scan.scanner import _blank_java_comments, _load_lenient_json_file, scan_mod
from .models import TargetProfile
from bridgeforge.bytecode.jar_audit import ClassFileError, parse_constant_pool, referenced_class_names, referenced_members
from bridgeforge.scan.scanner import _parse_class_file
from bridgeforge.zipsafe import MAX_CLASS_BYTES, read_limited


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


def build_archaeology(mod_directory: Path, *, save_aliases: Path | None = None, vanilla_core: Path | None = None, provider_roots: list[Path] | None = None) -> dict[str, object]:
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
    scan_result = (scan_mod(root, TargetProfile(), vanilla_core) if provider_roots is None
                   else scan_mod(root, TargetProfile(), vanilla_core, provider_roots=provider_roots))

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
                                class_bytes = read_limited(archive, member, MAX_CLASS_BYTES)
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


