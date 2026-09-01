from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

from .models import TargetProfile
from .scanner import scan_mod


def inventory_library_api(jar: Path) -> dict:
    jar = jar.expanduser().resolve()
    try:
        with zipfile.ZipFile(jar) as archive:
            classes = sorted(entry[:-6].replace("/", ".") for entry in archive.namelist() if entry.endswith(".class") and "$" not in entry)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError(f"Library API JAR is unreadable: {jar}") from exc
    return {"schema_version": 1, "mode": "READ_ONLY_LIBRARY_CLASS_INVENTORY", "jar": str(jar), "sha256": hashlib.sha256(jar.read_bytes()).hexdigest(), "class_count": len(classes), "classes": classes}


def match_library_imports(mod_directory: Path, inventory: dict, target: TargetProfile) -> dict:
    result = scan_mod(mod_directory, target)
    available = set(inventory["classes"])
    class_parts = [item.split(".") for item in inventory["classes"]]
    shared = class_parts[0][:-1] if class_parts else []
    for parts in class_parts[1:]:
        next_shared = []
        for part, other in zip(shared, parts[:-1]):
            if part != other:
                break
            next_shared.append(part)
        shared = next_shared
    namespace = ".".join(shared)
    imports = [item for item in result.imports if not item.endswith(".*") and (not namespace or item.startswith(namespace + "."))]
    missing = sorted(item for item in imports if item not in available)
    candidates = []
    for usage in result.library_usage:
        if usage["imported"] or usage["bytecode_referenced"]:
            candidates.append({"library": usage["library"], "classification": "REVIEW", "mode": "RESEARCH_CANDIDATE_ONLY", "reason": "Observed library use can be compared with a supplied local API inventory, but no transformation is proposed or applied."})
    return {"schema_version": 1, "mode": "READ_ONLY_LIBRARY_API_MATCH", "mod": mod_directory.expanduser().resolve().name, "inventory_sha256": inventory["sha256"], "inventory_namespace": namespace or None, "matched_import_count": len(imports) - len(missing), "unmatched_imports": missing, "migration_candidates": candidates}
