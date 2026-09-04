from __future__ import annotations

import hashlib
import re
import zipfile
from pathlib import Path

from .models import TargetProfile
from .scanner import scan_mod
from .bytecode import BytecodeUnavailable, inspect_bytecode


DEPENDENCY_ID_ALIASES = {
    "industrialevolution": {"indevo", "industrialevolution"},
    "consolecommands": {"consolecommands", "console"},
}


def _normalized_identity(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _inventory_classes(inventory: dict) -> set[str]:
    validate_library_api_inventory(inventory)
    classes = inventory.get("classes")
    if not isinstance(classes, list) or not all(isinstance(item, str) for item in classes):
        raise ValueError("Library API inventory must contain a classes array of strings.")
    return set(classes)


def validate_library_api_inventory(inventory: object) -> None:
    """Reject malformed or incompatible inventory reports before compatibility matching."""
    if not isinstance(inventory, dict):
        raise ValueError("Library API inventory must be a JSON object.")
    schema_version = inventory.get("schema_version")
    if schema_version not in (None, 1, 2):
        raise ValueError("Library API inventory has an unsupported schema.")
    if schema_version in (1, 2) and inventory.get("mode") != "READ_ONLY_LIBRARY_CLASS_INVENTORY":
        raise ValueError("Library API inventory has an unsupported mode.")
    classes = inventory.get("classes")
    if not isinstance(classes, list) or not all(isinstance(item, str) for item in classes):
        raise ValueError("Library API inventory must contain a classes array of strings.")
    if schema_version == 2 and inventory.get("class_count") != len(classes):
        raise ValueError("Library API inventory class_count does not match its classes array.")
    digest = inventory.get("sha256")
    if not isinstance(digest, str) or (schema_version == 2 and not re.fullmatch(r"[0-9a-f]{64}", digest)):
        raise ValueError("Library API inventory must contain a SHA-256 digest.")
    identity = inventory.get("identity")
    identity_keys = ("library_id", "version", "version_source") if schema_version == 2 else ("library_id", "version")
    if not isinstance(identity, dict) or not all(isinstance(identity.get(key), str) for key in identity_keys):
        raise ValueError("Library API inventory must contain string identity fields.")


def _inventory_matches_dependency(inventory: dict, dependency: str) -> bool:
    supplied = _normalized_identity(inventory.get("identity", {}).get("library_id", ""))
    expected = _normalized_identity(dependency)
    aliases = DEPENDENCY_ID_ALIASES.get(expected, {expected})
    return supplied in aliases


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
    method_symbols: list[str] = []
    method_symbol_status = "UNAVAILABLE"
    try:
        inspected = inspect_bytecode([jar])
        method_symbols = sorted(
            f"{str(entry['class_name']).replace('/', '.')}#{method['name']}"
            for entry in inspected["classes"]
            for method in entry.get("methods", [])
            if method.get("name") not in {"<init>", "<clinit>"}
        )
        method_symbol_status = "AVAILABLE"
    except (BytecodeUnavailable, ValueError, KeyError, TypeError):
        pass
    return {"schema_version": 2, "mode": "READ_ONLY_LIBRARY_CLASS_INVENTORY", "jar": jar.name, "sha256": digest.hexdigest(), "identity": {"library_id": library_id or "UNKNOWN", "version": version or "UNKNOWN", "version_source": "EXPLICIT" if library_version else "MANIFEST_UNVERIFIED" if manifest_version else "UNKNOWN"}, "class_count": len(classes), "classes": classes, "method_symbol_status": method_symbol_status, "method_symbols": method_symbols}


def match_library_imports(mod_directory: Path, inventory: dict, target: TargetProfile) -> dict:
    result = scan_mod(mod_directory, target)
    classes = inventory.get("classes")
    available = _inventory_classes(inventory)
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


def check_dependency_apis(mod_directory: Path, inventories: list[dict], target: TargetProfile) -> dict:
    """Compare direct optional-mod imports to explicit local API inventories.

    This checks imported class names only. It never fetches a dependency,
    infers its installed version, checks method signatures, or proposes code
    changes.
    """
    for inventory in inventories:
        validate_library_api_inventory(inventory)
    result = scan_mod(mod_directory, target)
    direct = result.migration_context.get("dependency_compatibility", {}).get("direct_api_dependencies", [])
    checks: list[dict[str, object]] = []
    for item in direct:
        dependency = str(item["dependency"])
        imports = list(item.get("imports", []))
        matching = [inventory for inventory in inventories if _inventory_matches_dependency(inventory, dependency)]
        if not matching:
            checks.append({"dependency": dependency, "declared": bool(item.get("declared")), "imports": imports, "status": "NO_MATCHING_LOCAL_INVENTORY", "missing_imports": imports})
            continue
        if len(matching) > 1:
            checks.append({"dependency": dependency, "declared": bool(item.get("declared")), "imports": imports, "status": "AMBIGUOUS_LOCAL_INVENTORY", "inventory_identities": [inventory.get("identity", {}) for inventory in matching], "missing_imports": imports})
            continue
        inventory = matching[0]
        available = _inventory_classes(inventory)
        missing = sorted(import_name for import_name in imports if import_name not in available)
        method_checks = _check_imported_method_names(result, imports, inventory)
        checks.append({"dependency": dependency, "declared": bool(item.get("declared")), "imports": imports, "status": "IMPORT_CLASSES_PRESENT" if not missing else "MISSING_IMPORTED_CLASSES", "inventory_identity": inventory.get("identity", {}), "inventory_sha256": inventory.get("sha256"), "missing_imports": missing, "method_checks": method_checks})
    configured = result.migration_context.get("configured_class_integrity", {})
    configured_checks: list[dict[str, object]] = []
    for class_name in configured.get("unresolved", []):
        matching = [inventory for inventory in inventories if class_name in _inventory_classes(inventory)]
        if not matching:
            configured_checks.append({"class": class_name, "status": "NOT_FOUND_IN_EXPLICIT_INVENTORIES"})
        elif len(matching) == 1:
            inventory = matching[0]
            configured_checks.append({"class": class_name, "status": "PRESENT_IN_EXPLICIT_INVENTORY", "inventory_identity": inventory.get("identity", {}), "inventory_sha256": inventory.get("sha256")})
        else:
            configured_checks.append({"class": class_name, "status": "AMBIGUOUS_EXPLICIT_INVENTORY_OWNERSHIP", "inventory_identities": [inventory.get("identity", {}) for inventory in matching]})
    return {
        "schema_version": 1,
        "mode": "READ_ONLY_DEPENDENCY_API_CHECK",
        "mod": mod_directory.expanduser().resolve().name,
        "checks": checks,
        "configured_class_checks": configured_checks,
        "limitations": [
            "Only explicit local inventories are considered; Bridgeforge does not detect installed mods automatically.",
            "Matching imported or configured classes does not prove method-signature, runtime, load-order, or behavioral compatibility.",
        ],
    }


def _check_imported_method_names(result, imports: list[str], inventory: dict) -> list[dict[str, str]]:
    if inventory.get("method_symbol_status") != "AVAILABLE":
        return [{"status": "METHOD_SYMBOLS_UNAVAILABLE"}] if imports else []
    symbols = set(inventory.get("method_symbols", []))
    by_simple_name = {item.rsplit(".", 1)[-1]: item for item in imports}
    checks: set[tuple[str, str, str]] = set()
    for fact in result.source_facts:
        if fact.get("kind") != "method_invocation":
            continue
        receiver, separator, method = str(fact.get("value", "")).partition(".")
        class_name = by_simple_name.get(receiver)
        if not separator or not class_name or method == "":
            continue
        status = "METHOD_NAME_PRESENT" if f"{class_name}#{method}" in symbols else "METHOD_NAME_MISSING"
        checks.add((class_name, method, status))
    return [{"class": class_name, "method": method, "status": status} for class_name, method, status in sorted(checks)]
