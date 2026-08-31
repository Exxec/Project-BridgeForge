from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .bytecode import inspect_bytecode


@dataclass(frozen=True)
class BytecodeRule:
    id: str
    action: str
    classification: str
    description: str
    owner: str
    replacement_owner: str
    expected_matches: int
    target_sha256: str | None = None


def load_bytecode_rules(path: Path) -> list[BytecodeRule]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload["schema_version"] != 1 or payload["kind"] != "bridgeforge-bytecode-rules":
            raise ValueError("unsupported bytecode rule schema")
        rules = [BytecodeRule(**entry) for entry in payload["rules"]]
    except (OSError, KeyError, TypeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"Invalid bytecode rule pack {path}: {exc}") from exc
    for rule in rules:
        if rule.action != "remap-class-reference" or rule.classification != "REVIEW":
            raise ValueError(f"Bytecode rule {rule.id} is not an allowed review-only class remap.")
        if not rule.owner or not rule.replacement_owner or rule.owner == rule.replacement_owner or rule.expected_matches < 1:
            raise ValueError(f"Bytecode rule {rule.id} has invalid exact-match constraints.")
        if rule.target_sha256 and len(rule.target_sha256) != 64:
            raise ValueError(f"Bytecode rule {rule.id} has an invalid target SHA-256.")
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
        matches = [
            {"class_name": item["class_name"], "input": item["input"], "reference_index": index, "reference": reference}
            for item in inventory["classes"]
            for index, reference in enumerate(item["references"])
            if reference.get("kind") == "type" and reference.get("owner") == rule.owner
        ]
        source_inputs = {match["input"].split("!", 1)[0] for match in matches}
        fingerprint_ok = not rule.target_sha256 or all(hashes.get(source) == rule.target_sha256 for source in source_inputs)
        if len(matches) != rule.expected_matches or not fingerprint_ok:
            rejected.append({"rule_id": rule.id, "classification": "MANUAL", "found_matches": len(matches), "expected_matches": rule.expected_matches, "fingerprint_ok": fingerprint_ok, "reason": "Exact occurrence count or target fingerprint did not match; no rewrite is planned."})
            continue
        planned.append({"rule_id": rule.id, "classification": "REVIEW", "action": rule.action, "replacement_owner": rule.replacement_owner, "matches": matches, "constraints": {"same_descriptor": True, "application": "NOT_IMPLEMENTED"}})
    return {"schema_version": 1, "mode": "PLAN_ONLY", "rules": [asdict(rule) for rule in rules], "planned": planned, "rejected": rejected}
