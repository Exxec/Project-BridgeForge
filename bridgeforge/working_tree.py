from __future__ import annotations

import hashlib
import json
from pathlib import Path


GENERATED_ROOTS = {"build", "out", "target", "bin", "classes"}
BACKUP_PREFIXES = ("backup", "backup_", "backup-")


def classify_path(path: str) -> str:
    """Classify a relative path without excluding it from any analysis."""
    parts = Path(path).as_posix().split("/")
    lowered = [part.casefold() for part in parts]
    if any(part in GENERATED_ROOTS for part in lowered) or Path(path).suffix.casefold() in {".class", ".log"}:
        return "GENERATED_CANDIDATE"
    if any(part == "backup" or part.startswith(BACKUP_PREFIXES) or part.endswith(".bak") for part in lowered):
        return "BACKUP_CANDIDATE"
    return "SOURCE_OR_CONTENT_CANDIDATE"


def _tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda item: item.relative_to(root).as_posix()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def analyze_working_tree(mod_directory: Path) -> dict:
    root = mod_directory.expanduser().resolve()
    if not root.is_dir():
        raise ValueError("Working-tree layout requires an existing directory.")
    files = [path for path in root.rglob("*") if path.is_file()]
    classified = {"GENERATED_CANDIDATE": [], "BACKUP_CANDIDATE": [], "SOURCE_OR_CONTENT_CANDIDATE": []}
    for path in files:
        relative = path.relative_to(root).as_posix()
        classified[classify_path(relative)].append(relative)
    source_roots = sorted({path.relative_to(root).parts[0] for path in files if path.suffix.lower() == ".java" and classify_path(path.relative_to(root).as_posix()) != "GENERATED_CANDIDATE"})
    return {
        "schema_version": 1,
        "mode": "READ_ONLY_WORKING_TREE_LAYOUT",
        "mod": root.name,
        "file_counts": {key: len(value) for key, value in classified.items()},
        "candidate_source_roots": source_roots,
        "selection_required": len(source_roots) > 1,
        "classified_paths": {key: sorted(value) for key, value in classified.items() if value},
        "limitation": "Generated and backup candidates remain visible evidence; Bridgeforge does not implicitly exclude or delete them.",
    }


def write_source_authority_selection(mod_directory: Path, selected_root: str, output: Path) -> Path:
    root = mod_directory.expanduser().resolve()
    layout = analyze_working_tree(root)
    if selected_root not in layout["candidate_source_roots"]:
        raise ValueError("Selected source root is not a non-generated Java source candidate.")
    output = output.expanduser().resolve()
    if output.is_relative_to(root):
        raise ValueError("Source-authority manifest must not be written inside the input mod directory.")
    selected = root / selected_root
    payload = {
        "schema_version": 1,
        "mode": "EXPLICIT_SOURCE_AUTHORITY_SELECTION",
        "mod": root.name,
        "selected_root": selected_root,
        "selected_root_sha256": _tree_sha256(selected),
        "layout_summary": {"file_counts": layout["file_counts"], "candidate_source_roots": layout["candidate_source_roots"]},
        "limitation": "This records an operator selection for later review; it neither compiles nor changes any source.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output
