from __future__ import annotations

import hashlib
import re
import zipfile
from pathlib import Path

from .models import TargetProfile
from .scanner import scan_mod


def _manifest_value(archive: zipfile.ZipFile) -> str | None:
    try:
        text = archive.read("META-INF/MANIFEST.MF").decode("utf-8", errors="replace")
    except KeyError:
        return None
    for key in ("Implementation-Version", "Specification-Version", "Bundle-Version"):
        match = re.search(rf"(?im)^{re.escape(key)}:\s*(.+)$", text)
        if match:
            return match.group(1).strip()
    return None


def inventory_library_api(jar: Path, library_id: str | None = None, library_version: str | None = None) -> dict:
    jar = jar.expanduser().resolve()
    try:
        with zipfile.ZipFile(jar) as archive:
            classes = sorted(entry[:-6].replace("/", ".") for entry in archive.namelist() if entry.endswith(".class") and "$" not in entry)
            manifest_version = _manifest_value(archive)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError(f"Library API JAR is unreadable: {jar}") from exc
    digest = hashlib.sha256()
    with jar.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    version = library_version or manifest_version
    return {"schema_version": 1, "mode": "READ_ONLY_LIBRARY_CLASS_INVENTORY", "jar": jar.name, "sha256": digest.hexdigest(), "identity": {"library_id": library_id or "UNKNOWN", "version": version or "UNKNOWN", "version_source": "EXPLICIT" if library_version else "MANIFEST_UNVERIFIED" if manifest_version else "UNKNOWN"}, "class_count": len(classes), "classes": classes}


def match_library_imports(mod_directory: Path, inventory: dict, target: TargetProfile) -> dict:
    result = scan_mod(mod_directory, target)
    classes = inventory.get("classes")
    if not isinstance(classes, list) or not all(isinstance(item, str) for item in classes):
        raise ValueError("Library API inventory must contain a classes array of strings.")
    available = set(classes)
    class_parts = [item.split(".") for item in classes]
    shared = class_parts[0][:-1] if class_parts else []
    for parts in class_parts[1:]:
        next_shared = []
        for part, other in zip(shared, parts[:-1]):
            if part != other:
                break
            next_shared.append(part)
        shared = next_shared
    namespace = ".".join(shared)
    packages = sorted({".".join(parts[:-1]) for parts in class_parts if len(parts) > 1})
    imports = [item for item in result.imports if not item.endswith(".*") and any(item.startswith(package + ".") for package in packages)]
    missing = sorted(item for item in imports if item not in available)
    uncertainty = []
    wildcard_imports = []
    reflective_files = []
    for source in mod_directory.expanduser().resolve().rglob("*.java"):
        text = source.read_text(encoding="utf-8", errors="replace")
        wildcard_imports.extend(item for item in re.findall(r"(?m)^\s*import\s+(?:static\s+)?([\w.]+\.\*)\s*;", text) if any(item.startswith(package + ".") for package in packages))
        if any(package in text for package in packages) and any(marker in text for marker in ("Class.forName", "getMethod(", "Method.invoke")):
            reflective_files.append(source.relative_to(mod_directory.expanduser().resolve()).as_posix())
    if wildcard_imports:
        uncertainty.append({"id": "library-api-wildcard-import", "classification": "REVIEW", "evidence": sorted(set(wildcard_imports)), "explanation": "Wildcard imports are not resolved to exact symbols by this inventory comparison."})
    if reflective_files:
        uncertainty.append({"id": "library-api-reflection-uncertain", "classification": "REVIEW", "evidence": sorted(reflective_files), "explanation": "Reflective library access cannot be checked against a class-name inventory."})
    bytecode_only = sorted(item["library"] for item in result.library_usage if item["bytecode_referenced"] and not item["imported"])
    if bytecode_only:
        uncertainty.append({"id": "library-api-bytecode-only-reference", "classification": "REVIEW", "evidence": bytecode_only, "explanation": "Bytecode-only library references are observed, but this source-import comparison cannot determine exact API compatibility."})
    candidates = []
    for usage in result.library_usage:
        if usage["imported"] or usage["bytecode_referenced"]:
            candidates.append({"library": usage["library"], "classification": "REVIEW", "mode": "RESEARCH_CANDIDATE_ONLY", "reason": "Observed library use can be compared with a supplied local API inventory, but no transformation is proposed or applied."})
    identity = inventory.get("identity", {})
    if identity.get("library_id", "UNKNOWN") == "UNKNOWN":
        uncertainty.append({"id": "library-api-identity-unknown", "classification": "UNKNOWN", "explanation": "The supplied API inventory has no explicit library identity; no library-specific compatibility conclusion is justified."})
    if identity.get("version", "UNKNOWN") == "UNKNOWN":
        uncertainty.append({"id": "library-api-version-unknown", "classification": "UNKNOWN", "explanation": "The supplied API inventory has no explicit or manifest version; version compatibility is unverified."})
    return {"schema_version": 1, "mode": "READ_ONLY_LIBRARY_API_MATCH", "mod": mod_directory.expanduser().resolve().name, "inventory_sha256": inventory.get("sha256"), "inventory_identity": identity, "inventory_namespace": namespace or None, "inventory_packages": packages, "matched_import_count": len(imports) - len(missing), "unmatched_imports": missing, "uncertainty_findings": uncertainty, "migration_candidates": candidates}
