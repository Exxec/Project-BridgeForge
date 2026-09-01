from __future__ import annotations

import csv
import hashlib
import json
import re
import zipfile
from collections import Counter
from pathlib import Path
from pathlib import PurePosixPath

from .models import ScanResult, TargetProfile
from .java_ast import AstUnavailable, analyze_sources

CLASS_MAJOR_TO_JAVA = {51: 7, 52: 8, 55: 11, 61: 17, 65: 21, 69: 25}
MAX_JAR_ENTRIES = 10_000
MAX_JAR_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
MAX_JAR_COMPRESSION_RATIO = 100
LARGE_BUNDLED_JAR_BYTES = 25 * 1024 * 1024
LIBRARY_PATTERNS = {
    "LazyLib": re.compile(r"lazylib", re.I),
    "MagicLib": re.compile(r"magiclib", re.I),
    "GraphicsLib": re.compile(r"graphicslib", re.I),
    "LunaLib": re.compile(r"lunalib", re.I),
    "Nexerelin": re.compile(r"nexerelin", re.I),
    "Kotlin runtime": re.compile(r"kotlin-(stdlib|reflect)|kotlinx-coroutines", re.I),
    "Gson": re.compile(r"gson", re.I),
}
LIBRARY_PACKAGES = {"LazyLib": "org.lazywizard.lazylib", "MagicLib": "org.magiclib"}
LEGACY_API_RULES = {
    "com.fs.starfarer.api.util.Misc.getHyperspaceTerrain": (
        "legacy-api-hyperspace-terrain",
        "A legacy Starsector utility reference was found. Confirm its replacement against the target API before changing it.",
    ),
    "sun.misc": (
        "internal-jvm-api",
        "An internal JVM API import was found; it may not be supported by the selected Java runtime.",
    ),
    "java.security.SecurityManager": (
        "security-manager",
        "SecurityManager APIs are obsolete on modern Java runtimes and require manual review.",
    ),
}


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _java_for_major(major: int) -> str:
    if major in CLASS_MAJOR_TO_JAVA:
        return str(CLASS_MAJOR_TO_JAVA[major])
    return f"class-file major {major}"


def _without_trailing_commas(text: str) -> str:
    result: list[str] = []
    in_string = False
    escaped = False
    index = 0
    while index < len(text):
        character = text[index]
        if in_string:
            result.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            index += 1
            continue
        if character == '"':
            in_string = True
        if character == ",":
            next_index = index + 1
            while next_index < len(text) and text[next_index].isspace():
                next_index += 1
            if next_index < len(text) and text[next_index] in "}]":
                index += 1
                continue
        result.append(character)
        index += 1
    return "".join(result)


def _without_hash_comments(text: str) -> str:
    result: list[str] = []
    in_string = False
    escaped = False
    index = 0
    while index < len(text):
        character = text[index]
        if in_string:
            result.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            index += 1
            continue
        if character == '"':
            in_string = True
            result.append(character)
        elif character == "#":
            while index < len(text) and text[index] not in "\r\n":
                index += 1
            continue
        else:
            result.append(character)
        index += 1
    return "".join(result)


def _parse_json(text: str) -> tuple[object, set[str]]:
    try:
        return json.loads(text), set()
    except json.JSONDecodeError as original_error:
        normalized = _without_hash_comments(text)
        tolerances: set[str] = set()
        if normalized != text:
            tolerances.add("hash-comments")
        without_commas = _without_trailing_commas(normalized)
        if without_commas != normalized:
            tolerances.add("trailing-commas")
        if not tolerances:
            raise original_error
        try:
            return json.loads(without_commas), tolerances
        except json.JSONDecodeError:
            raise original_error


def _non_strict_json_finding(result: ScanResult, category: str, file: str) -> None:
    result.add(id="non-strict-json-trailing-comma", category=category, severity="medium", classification="REVIEW", confidence="DETERMINISTIC", explanation="Trailing-comma JSON was accepted by the verified target parser compatibility path; retain it unchanged and recheck the selected game parser before modifying this file.", file=file)


def _hash_comment_json_finding(result: ScanResult, category: str, file: str) -> None:
    result.add(id="historical-json-hash-comment", category=category, severity="high", classification="REVIEW", confidence="DETERMINISTIC", explanation="Bridgeforge parsed # comments outside JSON strings only to inspect historical structure. This syntax is not accepted by the verified 0.98a org.json parser, so it must not support confident target-version inference or automatic rewriting.", file=file)


def _unverified_json_syntax_finding(result: ScanResult, category: str, file: str, exc: Exception) -> None:
    result.add(id="unverified-json-syntax", category=category, severity="medium", classification="UNKNOWN", confidence="DETERMINISTIC", explanation=f"A strict JSON parser rejected this file ({exc}). This is not proof that the target game parser rejects it; no matching parser-tolerance evidence is available.", file=file)


def _json_encoding_finding(result: ScanResult, category: str, file: str, exc: UnicodeDecodeError) -> None:
    result.add(id="json-encoding-unverified", category=category, severity="medium", classification="REVIEW", confidence="DETERMINISTIC", explanation=f"JSON could not be decoded as UTF-8 ({exc}). Encoding is separate from JSON structure; verify the target loader before conversion.", file=file)


def _scan_metadata(root: Path, result: ScanResult) -> None:
    path = root / "mod_info.json"
    if not path.exists():
        result.add(id="missing-mod-info", category="metadata", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation="mod_info.json was not found at the mod root.")
        nested_roots = [child.name for child in root.iterdir() if child.is_dir() and (child / "mod_info.json").is_file()]
        if len(nested_roots) == 1:
            result.add(id="wrapper-directory-layout", category="metadata", severity="medium", classification="REVIEW", confidence="DETERMINISTIC", explanation="A single nested directory contains mod_info.json. Select that directory after extracting the release archive; Bridgeforge will not implicitly change the input root.", evidence=nested_roots)
        return
    try:
        metadata_text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        _json_encoding_finding(result, "metadata", "mod_info.json", exc)
        return
    except OSError as exc:
        result.add(id="unreadable-mod-info", category="metadata", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation=f"mod_info.json could not be read: {exc}", file="mod_info.json")
        return
    try:
        metadata, tolerances = _parse_json(metadata_text)
    except json.JSONDecodeError as exc:
        result.add(id="unverified-mod-info-syntax", category="metadata", severity="high", classification="UNKNOWN", confidence="DETERMINISTIC", explanation=f"A strict JSON parser rejected mod_info.json ({exc}). Metadata could not be trusted for environment inference.", file="mod_info.json")
        return
    if not isinstance(metadata, dict):
        result.add(id="invalid-mod-info", category="metadata", severity="critical", classification="MANUAL", confidence="DETERMINISTIC", explanation="mod_info.json must contain a JSON object.", file="mod_info.json")
        return
    result.metadata = metadata
    result.metadata_parse_mode = "STRICT" if not tolerances else "+".join(sorted(tolerances)).upper()
    if "trailing-commas" in tolerances:
        _non_strict_json_finding(result, "metadata", "mod_info.json")
    if "hash-comments" in tolerances:
        _hash_comment_json_finding(result, "metadata", "mod_info.json")
    game_version = metadata.get("gameVersion") or metadata.get("game_version")
    if game_version:
        result.declared_starsector = str(game_version)
        if "hash-comments" not in tolerances:
            result.estimated_starsector = str(game_version)
    dependencies = metadata.get("dependencies") or metadata.get("requiredDependencies") or []
    if dependencies:
        result.add(id="declared-dependencies", category="dependencies", severity="info", classification="SAFE", confidence="DETERMINISTIC", explanation="Dependency declarations were found.", file="mod_info.json", evidence=[str(item) for item in dependencies])


def _scan_jars(root: Path, result: ScanResult) -> list[Path]:
    jars = list(root.rglob("*.jar"))
    bundled: Counter[str] = Counter()
    for jar in jars:
        entry: dict[str, object] = {"path": _relative(root, jar), "class_file_majors": [], "java_levels": []}
        try:
            with zipfile.ZipFile(jar) as archive:
                entries = archive.infolist()
                uncompressed_bytes = sum(item.file_size for item in entries)
                compressed_bytes = sum(item.compress_size for item in entries)
                ratio = uncompressed_bytes / max(compressed_bytes, 1)
                if len(entries) > MAX_JAR_ENTRIES or uncompressed_bytes > MAX_JAR_UNCOMPRESSED_BYTES or ratio > MAX_JAR_COMPRESSION_RATIO:
                    result.add(id="jar-scan-limit", category="bytecode", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation=f"JAR exceeds safe scan limits ({len(entries)} entries, {uncompressed_bytes} uncompressed bytes, {ratio:.1f}:1 compression ratio).", file=_relative(root, jar))
                    result.jars.append(entry)
                    continue
                if jar.stat().st_size > LARGE_BUNDLED_JAR_BYTES:
                    result.add(id="large-bundled-archive", category="dependencies", severity="medium", classification="REVIEW", confidence="DETERMINISTIC", explanation=f"Archive is {jar.stat().st_size} bytes. Attribute its ownership and dependency role before changing or redistributing it.", file=_relative(root, jar))
                majors: set[int] = set()
                for item in entries:
                    member = PurePosixPath(item.filename.replace("\\", "/"))
                    if member.is_absolute() or ".." in member.parts:
                        result.add(id="jar-path-traversal", category="bytecode", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation="JAR contains an absolute or parent-directory member name; it was not opened.", file=_relative(root, jar))
                        continue
                    if item.filename.endswith(".class"):
                        with archive.open(item) as class_file:
                            class_bytes = class_file.read()
                        header = class_bytes[:8]
                        if header[:4] == b"\xca\xfe\xba\xbe" and len(header) == 8:
                            majors.add(int.from_bytes(header[6:8], "big"))
                            result.compiled_class_names.add(item.filename[:-6].replace("/", ".").replace("\\", "."))
                            for library, prefix in LIBRARY_PACKAGES.items():
                                if prefix.replace(".", "/").encode() in class_bytes:
                                    result.bytecode_library_references.add(library)
                entry["class_file_majors"] = sorted(majors)
                entry["java_levels"] = sorted({_java_for_major(major) for major in majors})
        except (OSError, zipfile.BadZipFile) as exc:
            result.add(id="unreadable-jar", category="bytecode", severity="high", classification="REVIEW", confidence="DETERMINISTIC", explanation=f"JAR could not be inspected: {exc}", file=_relative(root, jar))
        result.jars.append(entry)
        for library, pattern in LIBRARY_PATTERNS.items():
            if pattern.search(jar.name):
                bundled[library] += 1
                severity = "high" if library == "Kotlin runtime" else "info"
                result.add(id=f"bundled-{library.lower().replace(' ', '-')}", category="dependencies", severity=severity, classification="REVIEW", confidence="HIGH", explanation=f"Bundled {library} archive detected. Confirm it does not conflict with the target dependency strategy.", file=_relative(root, jar))
    for library, count in bundled.items():
        if count > 1:
            result.add(id=f"duplicate-{library.lower().replace(' ', '-')}", category="dependencies", severity="high", classification="REVIEW", confidence="DETERMINISTIC", explanation=f"{count} bundled archives match {library}; duplicate classes or versions are possible.")
    return jars


def _scan_sources(root: Path, result: ScanResult) -> None:
    try:
        result.source_facts = analyze_sources(root)
    except AstUnavailable as exc:
        result.add(id="source-ast-unavailable", category="source", severity="medium", classification="UNKNOWN", confidence="DETERMINISTIC", explanation=f"Structured Java parsing was unavailable; import collection used a limited fallback: {exc}")
    imports: set[str] = set()
    content_owners: dict[str, list[str]] = {}
    for source in root.rglob("*.java"):
        relative = _relative(root, source)
        try:
            raw_bytes = source.read_bytes()
        except OSError as exc:
            result.add(id="unreadable-source", category="source", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation=str(exc), file=relative)
            continue
        text = raw_bytes.decode("utf-8", errors="replace")
        content_owners.setdefault(hashlib.sha256(raw_bytes).hexdigest(), []).append(relative)
        if result.source_facts:
            imports.update(fact["value"] for fact in result.source_facts if fact["kind"] == "import" and fact["file"] == relative)
        else:
            imports.update(re.findall(r"^\s*import\s+([\w.]+(?:\.\*)?)\s*;", text, re.M))
        for needle, (rule_id, explanation) in LEGACY_API_RULES.items():
            if needle in text:
                result.add(id=rule_id, category="source-api", severity="high", classification="REVIEW", confidence="HIGH", explanation=explanation, file=relative, evidence=[needle])
    result.imports = sorted(imports)
    for paths in content_owners.values():
        if len(paths) > 1:
            result.add(id="duplicate-source-layout", category="source", severity="medium", classification="REVIEW", confidence="DETERMINISTIC", explanation="Identical Java source appears at multiple paths. Establish the authoritative source/JAR layout before compiling or modifying it.", evidence=sorted(paths))


def _scan_assets(root: Path, result: ScanResult) -> None:
    for path in root.rglob("*.json"):
        if path.name == "mod_info.json":
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as exc:
            _json_encoding_finding(result, "assets", _relative(root, path), exc)
            continue
        except OSError as exc:
            result.add(id="unreadable-json", category="assets", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation=f"JSON could not be read: {exc}", file=_relative(root, path))
            continue
        try:
            _, tolerances = _parse_json(text)
        except json.JSONDecodeError as exc:
            _unverified_json_syntax_finding(result, "assets", _relative(root, path), exc)
        else:
            if "trailing-commas" in tolerances:
                _non_strict_json_finding(result, "assets", _relative(root, path))
            if "hash-comments" in tolerances:
                _hash_comment_json_finding(result, "assets", _relative(root, path))
    for path in root.rglob("*.csv"):
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                header = next(csv.reader(handle), [])
            if not header or not any(cell.strip() for cell in header):
                raise ValueError("CSV has no header row")
        except UnicodeDecodeError as exc:
            result.add(id="csv-encoding-unverified", category="assets", severity="medium", classification="REVIEW", confidence="DETERMINISTIC", explanation=f"CSV could not be decoded as UTF-8 ({exc}). Encoding is separate from CSV structure; verify the target loader before conversion.", file=_relative(root, path))
        except (OSError, csv.Error, ValueError) as exc:
            result.add(id="invalid-csv", category="assets", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation=f"CSV could not be read: {exc}", file=_relative(root, path))


def _source_class_names(root: Path) -> set[str]:
    names: set[str] = set()
    for path in root.rglob("*.java"):
        if "disabled_files" in path.relative_to(root).parts:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        package = re.search(r"^\s*package\s+([\w.]+)\s*;", text, re.M)
        declared = re.search(r"\b(?:public\s+)?(?:class|interface|enum)\s+(\w+)", text)
        if package and declared:
            names.add(f"{package.group(1)}.{declared.group(1)}")
    return names


def _scan_configured_class_integrity(root: Path, result: ScanResult) -> None:
    local_classes = _source_class_names(root)
    references: set[str] = set()
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".csv", ".json", ".faction", ".ship", ".variant", ".system"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        references.update(re.findall(r"\bdata(?:\.[A-Za-z_$][\w$]*)+", text))
    missing = sorted(local_classes & references - result.compiled_class_names)
    if missing:
        result.add(id="configured-source-class-missing-from-jar", category="bytecode", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation="Mod data references local source classes that are absent from every scanned JAR. Compile/package the active sources before runtime testing.", evidence=missing)


def _attribute_library_usage(result: ScanResult) -> None:
    dependencies = " ".join(map(str, result.metadata.get("dependencies") or result.metadata.get("requiredDependencies") or [])).lower()
    calls = [fact.get("value", "") for fact in result.source_facts if fact.get("kind") == "method_invocation"]
    for library, prefix in LIBRARY_PACKAGES.items():
        imports = [item for item in result.imports if item.startswith(prefix)]
        simple_names = {item.rsplit(".", 1)[-1] for item in imports if not item.endswith(".*")}
        source_calls = [call for call in calls if call.split(".", 1)[0] in simple_names]
        bundled = any(LIBRARY_PATTERNS[library].search(str(item.get("path", ""))) for item in result.jars)
        declared = library.lower() in dependencies or library.replace("Lib", "").lower() in dependencies
        bytecode_referenced = library in result.bytecode_library_references
        if declared or bundled or imports:
            result.library_usage.append({"library": library, "declared": declared, "bundled": bundled, "imported": bool(imports), "source_called": bool(source_calls), "bytecode_referenced": bytecode_referenced, "evidence": {"imports": imports, "source_calls": source_calls}})
            if declared and not bundled and not imports:
                result.add(id="declared-library-unreferenced", category="dependencies", severity="medium", classification="REVIEW", confidence="DETERMINISTIC", explanation="A declared library has no bundled, import, or source-call evidence. Confirm whether it is required before removing or changing it.", evidence=[library])


def _infer_environment(result: ScanResult) -> None:
    majors = [major for jar in result.jars for major in jar.get("class_file_majors", [])]
    if majors:
        result.estimated_java = _java_for_major(max(majors))
        if max(majors) > 61:
            result.add(id="target-bytecode-exceeds-profile", category="java", severity="high", classification="REVIEW", confidence="DETERMINISTIC", explanation=f"Detected {_java_for_major(max(majors))} bytecode exceeds target Java {result.target.java}.")
    if result.estimated_starsector == "UNKNOWN":
        result.add(id="version-inference-blocked", category="environment", severity="medium", classification="UNKNOWN", confidence="DETERMINISTIC", explanation="No trustworthy declared Starsector version was available. Do not make confident compatibility or migration claims until metadata or independent target evidence is supplied.")


def scan_mod(input_path: Path, target: TargetProfile | None = None) -> ScanResult:
    root = input_path.expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Input mod directory does not exist: {root}")
    result = ScanResult(input_path=root, target=target or TargetProfile())
    for path in sorted(root.rglob("*")):
        if path.is_file():
            result.files.append({"path": _relative(root, path), "size_bytes": path.stat().st_size})
    _scan_metadata(root, result)
    _scan_jars(root, result)
    _scan_sources(root, result)
    _scan_assets(root, result)
    _scan_configured_class_integrity(root, result)
    _attribute_library_usage(result)
    _infer_environment(result)
    return result
