from __future__ import annotations

import csv
import json
import re
import zipfile
from collections import Counter
from pathlib import Path

from .models import ScanResult, TargetProfile
from .java_ast import AstUnavailable, analyze_sources

CLASS_MAJOR_TO_JAVA = {51: 7, 52: 8, 55: 11, 61: 17, 65: 21, 69: 25}
MAX_JAR_ENTRIES = 10_000
MAX_JAR_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
LIBRARY_PATTERNS = {
    "LazyLib": re.compile(r"lazylib", re.I),
    "MagicLib": re.compile(r"magiclib", re.I),
    "GraphicsLib": re.compile(r"graphicslib", re.I),
    "LunaLib": re.compile(r"lunalib", re.I),
    "Nexerelin": re.compile(r"nexerelin", re.I),
    "Kotlin runtime": re.compile(r"kotlin-(stdlib|reflect)|kotlinx-coroutines", re.I),
    "Gson": re.compile(r"gson", re.I),
}
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


def _scan_metadata(root: Path, result: ScanResult) -> None:
    path = root / "mod_info.json"
    if not path.exists():
        result.add(id="missing-mod-info", category="metadata", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation="mod_info.json was not found at the mod root.")
        return
    try:
        metadata = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        result.add(id="invalid-mod-info", category="metadata", severity="critical", classification="MANUAL", confidence="DETERMINISTIC", explanation=f"mod_info.json could not be parsed: {exc}", file="mod_info.json")
        return
    result.metadata = metadata
    game_version = metadata.get("gameVersion") or metadata.get("game_version")
    if game_version:
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
                if len(entries) > MAX_JAR_ENTRIES or uncompressed_bytes > MAX_JAR_UNCOMPRESSED_BYTES:
                    result.add(id="jar-scan-limit", category="bytecode", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation=f"JAR exceeds safe scan limits ({len(entries)} entries, {uncompressed_bytes} uncompressed bytes).", file=_relative(root, jar))
                    result.jars.append(entry)
                    continue
                majors: set[int] = set()
                for item in entries:
                    if item.filename.endswith(".class"):
                        with archive.open(item) as class_file:
                            header = class_file.read(8)
                        if header[:4] == b"\xca\xfe\xba\xbe" and len(header) == 8:
                            majors.add(int.from_bytes(header[6:8], "big"))
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
    for source in root.rglob("*.java"):
        relative = _relative(root, source)
        try:
            text = source.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            result.add(id="unreadable-source", category="source", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation=str(exc), file=relative)
            continue
        if result.source_facts:
            imports.update(fact["value"] for fact in result.source_facts if fact["kind"] == "import" and fact["file"] == relative)
        else:
            imports.update(re.findall(r"^\s*import\s+([\w.]+(?:\.\*)?)\s*;", text, re.M))
        for needle, (rule_id, explanation) in LEGACY_API_RULES.items():
            if needle in text:
                result.add(id=rule_id, category="source-api", severity="high", classification="REVIEW", confidence="HIGH", explanation=explanation, file=relative, evidence=[needle])
    result.imports = sorted(imports)


def _scan_assets(root: Path, result: ScanResult) -> None:
    for path in root.rglob("*.json"):
        if path.name == "mod_info.json":
            continue
        try:
            json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            result.add(id="invalid-json", category="assets", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation=f"JSON could not be parsed: {exc}", file=_relative(root, path))
    for path in root.rglob("*.csv"):
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                header = next(csv.reader(handle), [])
            if not header or not any(cell.strip() for cell in header):
                raise ValueError("CSV has no header row")
        except (OSError, csv.Error, ValueError) as exc:
            result.add(id="invalid-csv", category="assets", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation=f"CSV could not be read: {exc}", file=_relative(root, path))


def _infer_environment(result: ScanResult) -> None:
    majors = [major for jar in result.jars for major in jar.get("class_file_majors", [])]
    if majors:
        result.estimated_java = _java_for_major(max(majors))
        if max(majors) > 61:
            result.add(id="target-bytecode-exceeds-profile", category="java", severity="high", classification="REVIEW", confidence="DETERMINISTIC", explanation=f"Detected {_java_for_major(max(majors))} bytecode exceeds target Java {result.target.java}.")
    if result.estimated_starsector == "UNKNOWN":
        result.add(id="starsector-version-unknown", category="environment", severity="medium", classification="UNKNOWN", confidence="LOW", explanation="No declared Starsector version was found; inspect metadata, dependencies, and API usage manually.")


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
    _infer_environment(result)
    return result
