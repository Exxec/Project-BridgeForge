from __future__ import annotations

import json
import re
from pathlib import Path

from .working_tree import analyze_working_tree


def build_input_manifest(mod_directory: Path, source_root: str | None = None) -> dict:
    root = mod_directory.expanduser().resolve()
    layout = analyze_working_tree(root)
    candidates = layout["candidate_source_roots"]
    if source_root is not None and source_root not in candidates:
        raise ValueError("Selected source root is not a non-generated Java source candidate.")
    selected = source_root or (candidates[0] if len(candidates) == 1 else None)
    source_paths = list((root / selected).rglob("*.java")) if selected else []
    lombok_imports = sorted({match.group(0) for path in source_paths for match in re.finditer(r"(?m)^\s*import\s+(lombok\.[\w.]+)\s*;", path.read_text(encoding="utf-8", errors="replace"))})
    build_files = sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file() and path.name in {"pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"})
    processor_jars = sorted(path.relative_to(root).as_posix() for path in root.rglob("*.jar") if "lombok" in path.name.casefold())
    return {
        "schema_version": 1,
        "mode": "READ_ONLY_BUILD_INPUT_MANIFEST",
        "mod": root.name,
        "source_authority": {"selected_root": selected, "selection_required": selected is None, "candidates": candidates},
        "annotation_processing": {"status": "REQUIRED" if lombok_imports else "NOT_OBSERVED", "imports": lombok_imports, "local_processor_jars": processor_jars, "build_metadata": build_files, "limitation": "Observed imports do not identify a safe processor version or prove a successful rebuild."},
    }


def write_build_input_manifest(manifest: dict, output: Path, mod_directory: Path) -> Path:
    output = output.expanduser().resolve()
    if output.is_relative_to(mod_directory.expanduser().resolve()):
        raise ValueError("Build-input manifest must not be written inside the input mod directory.")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output
