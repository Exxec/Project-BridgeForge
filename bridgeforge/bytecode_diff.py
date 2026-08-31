from __future__ import annotations

from .bytecode import inspect_bytecode


def _shape(reference: dict[str, object]) -> tuple[object, object]:
    return reference.get("kind"), reference.get("opcode")


def _method_shape(method: dict[str, object], key: str) -> list[object]:
    return [item.get(key) for item in method]


def diff_bytecode(before_inputs: list, after_inputs: list) -> dict[str, object]:
    """Compare normalized symbolic inventories; never compare raw class bytes."""
    before = inspect_bytecode(before_inputs)
    after = inspect_bytecode(after_inputs)
    old = {item["class_name"]: item for item in before["classes"]}
    new = {item["class_name"]: item for item in after["classes"]}
    changed: list[dict[str, object]] = []
    for name in sorted(set(old) & set(new)):
        previous, current = old[name], new[name]
        old_refs, new_refs = previous["references"], current["references"]
        reference_changes = [
            {"index": index, "before": left, "after": right}
            for index, (left, right) in enumerate(zip(old_refs, new_refs)) if left != right
        ]
        if len(old_refs) != len(new_refs): reference_changes.append({"kind": "reference-count", "before": len(old_refs), "after": len(new_refs)})
        invariants = {
            "same_class_name": previous["class_name"] == current["class_name"],
            "same_class_file_version": previous["class_file_version"] == current["class_file_version"],
            "same_fields": previous["fields"] == current["fields"],
            "same_methods": previous["methods"] == current["methods"],
            "same_reference_shape": len(old_refs) == len(new_refs) and all(_shape(left) == _shape(right) for left, right in zip(old_refs, new_refs)),
            "same_instruction_counts": _method_shape(previous["methods"], "instruction_count") == _method_shape(current["methods"], "instruction_count"),
            "same_opcode_sequence": _method_shape(previous["methods"], "opcode_sequence") == _method_shape(current["methods"], "opcode_sequence"),
            "same_branch_counts": _method_shape(previous["methods"], "branch_count") == _method_shape(current["methods"], "branch_count"),
            "same_exception_tables": _method_shape(previous["methods"], "exception_table_count") == _method_shape(current["methods"], "exception_table_count"),
        }
        if reference_changes or any(value is False for value in invariants.values()): changed.append({"class_name": name, "reference_changes": reference_changes, "invariants": invariants})
    return {"schema_version": 1, "mode": "SEMANTIC_DIFF_ONLY", "added_classes": sorted(set(new) - set(old)), "removed_classes": sorted(set(old) - set(new)), "changed_classes": changed}
