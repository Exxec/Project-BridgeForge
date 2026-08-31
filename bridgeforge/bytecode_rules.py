from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from .bytecode import inspect_bytecode, rewrite_class
from .bytecode_diff import diff_bytecode


@dataclass(frozen=True)
class BytecodeRule:
    id: str
    action: str
    classification: str
    description: str
    owner: str
    replacement_owner: str
    expected_matches: int
    name: str = ""
    descriptor: str = ""
    opcode: int | None = None
    replacement_name: str = ""
    replacement_descriptor: str = ""
    target_sha256: str | None = None
    evidence: dict[str, str] | None = None


def load_bytecode_rules(path: Path) -> list[BytecodeRule]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload["schema_version"] != 1 or payload["kind"] != "bridgeforge-bytecode-rules":
            raise ValueError("unsupported bytecode rule schema")
        rules = [BytecodeRule(**entry) for entry in payload["rules"]]
    except (OSError, KeyError, TypeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"Invalid bytecode rule pack {path}: {exc}") from exc
    for rule in rules:
        required_evidence = {"provenance", "before_fixture", "after_fixture", "semantic_diff_validation", "idempotence", "conflict_review", "save_risk_assessment"}
        if rule.action not in {"remap-class-reference", "remap-method-reference", "remap-field-reference"} or rule.classification != "REVIEW":
            raise ValueError(f"Bytecode rule {rule.id} is not an allowed review-only remap.")
        if not rule.owner or not rule.replacement_owner or rule.owner == rule.replacement_owner or rule.expected_matches < 1:
            raise ValueError(f"Bytecode rule {rule.id} has invalid exact-match constraints.")
        if rule.target_sha256 and len(rule.target_sha256) != 64:
            raise ValueError(f"Bytecode rule {rule.id} has an invalid target SHA-256.")
        if rule.action != "remap-class-reference":
            if not rule.name or not rule.descriptor or rule.opcode is None or not rule.replacement_name or rule.replacement_descriptor != rule.descriptor:
                raise ValueError(f"Bytecode rule {rule.id} must retain an exact descriptor and specify name, opcode, and replacement name.")
        if not isinstance(rule.evidence, dict) or any(not isinstance(rule.evidence.get(field), str) or not rule.evidence[field].strip() for field in required_evidence):
            raise ValueError(f"Bytecode rule {rule.id} requires verified evidence: " + ", ".join(sorted(required_evidence)))
    if len({rule.id for rule in rules}) != len(rules):
        raise ValueError("Duplicate bytecode rule IDs")
    return rules


def plan_bytecode(inputs: list[Path], rules_path: Path) -> dict[str, object]:
    selected = [path.expanduser().resolve() for path in inputs]
    rules = load_bytecode_rules(rules_path)
    inventory = inspect_bytecode(selected)
    planned: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []
    hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in selected}
    for rule in rules:
        kind = {"remap-class-reference": "type", "remap-method-reference": "method", "remap-field-reference": "field"}[rule.action]
        matches = [
            {"class_name": item["class_name"], "input": item["input"], "reference_index": index, "reference": reference}
            for item in inventory["classes"]
            for index, reference in enumerate(item["references"])
            if reference.get("kind") == kind and reference.get("owner") == rule.owner
            and (rule.action == "remap-class-reference" or (reference.get("name") == rule.name and reference.get("descriptor") == rule.descriptor and reference.get("opcode") == rule.opcode))
        ]
        source_inputs = {match["input"].split("!", 1)[0] for match in matches}
        fingerprint_ok = not rule.target_sha256 or all(hashes.get(source) == rule.target_sha256 for source in source_inputs)
        if len(matches) != rule.expected_matches or not fingerprint_ok:
            rejected.append({"rule_id": rule.id, "classification": "MANUAL", "found_matches": len(matches), "expected_matches": rule.expected_matches, "fingerprint_ok": fingerprint_ok, "reason": "Exact occurrence count or target fingerprint did not match; no rewrite is planned."})
            continue
        planned.append({"rule_id": rule.id, "classification": "REVIEW", "action": rule.action, "replacement": {"owner": rule.replacement_owner, "name": rule.replacement_name or None, "descriptor": rule.replacement_descriptor or None}, "matches": matches, "constraints": {"same_descriptor": True, "application": "NOT_IMPLEMENTED"}})
    return {"schema_version": 1, "mode": "PLAN_ONLY", "rules": [asdict(rule) for rule in rules], "planned": planned, "rejected": rejected}


def apply_bytecode_class(input_path: Path, output_path: Path, rules_path: Path, approved_rule_ids: set[str]) -> dict[str, object]:
    """Apply explicitly approved exact rules to an output copy, never in place."""
    source, output = input_path.expanduser().resolve(), output_path.expanduser().resolve()
    if source == output: raise ValueError("Bytecode output must differ from input; in-place replacement is forbidden.")
    plan = plan_bytecode([source], rules_path)
    rejected = {item["rule_id"] for item in plan["rejected"]}
    rules = {rule.id: rule for rule in load_bytecode_rules(rules_path)}
    selected = [rules[rule_id] for rule_id in approved_rule_ids if rule_id in rules and rule_id not in rejected]
    if not selected: raise ValueError("No approved bytecode rules matched this class exactly.")
    with tempfile.TemporaryDirectory() as directory:
        current = Path(directory) / "before.class"; shutil.copy2(source, current)
        for index, rule in enumerate(selected):
            next_path = Path(directory) / f"rewrite-{index}.class"
            rewrite_class(current, next_path, rule)
            current = next_path
        semantic = diff_bytecode([source], [current])
        if len(semantic["changed_classes"]) != 1:
            raise ValueError("Bytecode rewrite changed an unexpected class set.")
        invariants = semantic["changed_classes"][0]["invariants"]
        required = ("same_class_name", "same_class_file_version", "same_fields", "same_methods", "same_reference_shape")
        if not all(invariants[key] is True for key in required):
            raise ValueError("Bytecode rewrite violated a structural invariant; output was discarded.")
        output.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(current, output)
    return {"schema_version": 1, "mode": "REVIEW_APPLIED_TO_OUTPUT_COPY", "applied_rule_ids": [rule.id for rule in selected], "output": str(output), "semantic_diff": semantic}
