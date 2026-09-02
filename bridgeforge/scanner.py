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
from .ashlib_compat import scan_ashlib_compat
from .graphicslib_compat import scan_graphicslib_compat
from .lazylib_compat import scan_lazylib_compat
from .magiclib_compat import scan_magiclib_compat

CLASS_MAJOR_TO_JAVA = {51: 7, 52: 8, 55: 11, 61: 17, 65: 21, 69: 25}
MAX_JAR_ENTRIES = 10_000
MAX_JAR_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
MAX_JAR_COMPRESSION_RATIO = 100
LARGE_BUNDLED_JAR_BYTES = 25 * 1024 * 1024
LIBRARY_PATTERNS = {
    "LazyLib": re.compile(r"lazylib", re.I),
    "MagicLib": re.compile(r"magiclib", re.I),
    "AshLib": re.compile(r"ashlib", re.I),
    "GraphicsLib": re.compile(r"graphicslib", re.I),
    "LunaLib": re.compile(r"lunalib", re.I),
    "Nexerelin": re.compile(r"nexerelin", re.I),
    "Kotlin runtime": re.compile(r"kotlin-(stdlib|reflect)|kotlinx-coroutines", re.I),
    "Gson": re.compile(r"gson", re.I),
}
LIBRARY_PACKAGES = {
    "LazyLib": ("org.lazywizard.lazylib",),
    "MagicLib": ("org.magiclib", "data.scripts.util"),
}
EXTERNAL_MOD_API_PACKAGES = {
    "Console Commands": ("org.lazywizard.console.",),
    "Industrial Evolution": ("com.fs.starfarer.api.impl.campaign.ids.IndEvo_ids", "indevo.ids."),
    "MagicLib": ("data.scripts.util.",),
}
EXTERNAL_CAMPAIGN_MEMORY_PREFIXES = {
    "Nexerelin": "$nex_",
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
RUNTIME_PLACEHOLDER_PATTERN = re.compile(
    r"\bthrow\s+new\s+(?:java\.lang\.)?UnsupportedOperationException\s*\(", re.M
)
PERCENT_MULTIPLIER_PATTERN = re.compile(
    r"\.modifyPercent\s*\(\s*[^,]+,\s*1f\s*-\s*[A-Za-z_$][\w$]*\s*\*\s*0\.01f\s*\)"
)
HARDCODED_SYSTEM_LOOKUP_PATTERN = re.compile(r"\bgetStarSystem\s*\(\s*\"([^\"]+)\"\s*\)")
HARDCODED_ENTITY_LOOKUP_PATTERN = re.compile(r"\bgetEntityById\s*\(\s*\"([^\"]+)\"\s*\)")
CAMPAIGN_SYSTEM_CREATION_PATTERN = re.compile(r"\b(?:createStarSystem|addStarSystem)\s*\(\s*\"([^\"]+)\"")
CAMPAIGN_ENTITY_CREATION_PATTERN = re.compile(r"\b(?:addCustomEntity|addEntity)\s*\(\s*\"([^\"]+)\"")
MISSION_FLEET_REFERENCE_PATTERN = re.compile(
    r"\baddToFleet\s*\(\s*FleetSide\.(?:PLAYER|ENEMY)\s*,\s*\"([^\"]+)\"\s*,\s*FleetMemberType\.(SHIP|FIGHTER_WING)"
)
CUSTOM_UI_PLUGIN_PATTERN = re.compile(r"\b(?:implements\s+CustomUIPanelPlugin|new\s+CustomUIPanelPlugin\s*\(\s*\)\s*\{)")
CUSTOM_DIALOG_DELEGATE_PATTERN = re.compile(r"\bimplements\s+CustomDialogDelegate\b")
RELEASE_BLOCKING_TODO_PATTERN = re.compile(
    r"//[^\r\n]*\b(?:TODO|FIXME)\b[^\r\n]*\b(?:remove|delete|disable)\b[^\r\n]*\b(?:final|release)\b",
    re.I,
)
ROBOT_INPUT_INJECTION_PATTERN = re.compile(r"\bnew\s+(?:java\.awt\.)?Robot\s*\(")
TARGET_INTERFACE_CONTRACTS = {
    "LevelupPlugin": {
        "implements": re.compile(r"\bimplements\s+(?:[\w.]+\.)?LevelupPlugin\b"),
        "method": re.compile(r"\bpublic\s+int\s+getBonusXPUseMultAtMaxLevel\s*\(\s*\)"),
        "signature": "int getBonusXPUseMultAtMaxLevel()",
        "suggestion": "For a settings-driven level-up curve, return (int) Global.getSettings().getFloat(\"bonusXPUseMultAtMaxLevel\").",
    },
}
MEMORY_SELF_STORE_PATTERN = re.compile(
    r"(?:\b\w*(?:memory|mem)\w*\s*|\.getMemoryWithoutUpdate\(\)\s*)\.set\s*\(\s*[^,]+\s*,\s*this\b",
    re.I,
)


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
                            for library, prefixes in LIBRARY_PACKAGES.items():
                                if any(prefix.replace(".", "/").encode() in class_bytes for prefix in prefixes):
                                    result.bytecode_library_references.add(library)
                            if b"java/lang/UnsupportedOperationException" in class_bytes:
                                result.add(
                                    id="bytecode-runtime-placeholder-reference",
                                    category="bytecode",
                                    severity="high",
                                    classification="REVIEW",
                                    confidence="HIGH",
                                    explanation="This compiled class references UnsupportedOperationException. It may be an unfinished callback implementation; inspect the class control flow before runtime testing.",
                                    file=_relative(root, jar),
                                    evidence=[item.filename[:-6].replace("/", ".").replace("\\", ".")],
                                )
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
        active_source = "disabled_files" not in source.relative_to(root).parts
        if result.source_facts:
            imports.update(fact["value"] for fact in result.source_facts if fact["kind"] == "import" and fact["file"] == relative)
        else:
            imports.update(re.findall(r"^\s*import\s+([\w.]+(?:\.\*)?)\s*;", text, re.M))
        for needle, (rule_id, explanation) in LEGACY_API_RULES.items():
            if needle in text:
                result.add(id=rule_id, category="source-api", severity="high", classification="REVIEW", confidence="HIGH", explanation=explanation, file=relative, evidence=[needle])
        if active_source and RUNTIME_PLACEHOLDER_PATTERN.search(text):
            result.add(
                id="runtime-placeholder-unsupported-operation",
                category="source",
                severity="high",
                classification="REVIEW",
                confidence="DETERMINISTIC",
                explanation="Active Java source explicitly throws UnsupportedOperationException. This commonly indicates an IDE-generated placeholder that will crash when the callback is invoked.",
                file=relative,
                evidence=["throw new UnsupportedOperationException"],
            )
        if active_source:
            for interface, contract in TARGET_INTERFACE_CONTRACTS.items():
                if contract["implements"].search(text) and not contract["method"].search(text):
                    result.add(
                        id="target-interface-method-missing",
                        category="source-api",
                        severity="critical",
                        classification="MANUAL",
                        confidence="DETERMINISTIC",
                        explanation=f"This source implements Starsector's {interface} but lacks the 0.98a-required {contract['signature']}. It will fail Janino/Javac loading before the mod can start. {contract['suggestion']}",
                        file=relative,
                        evidence=[interface, contract["signature"]],
                    )
        if active_source:
            missing_callbacks = _custom_ui_plugins_missing_button_callback(text)
            if missing_callbacks:
                result.add(
                    id="missing-custom-ui-button-pressed-callback",
                    category="source-api",
                    severity="high",
                    classification="REVIEW",
                    confidence="HIGH",
                    explanation="CustomUIPanelPlugin implementations in 0.98a require buttonPressed(Object). Add a no-op callback when the panel has no button handling, then runtime-test the UI.",
                    file=relative,
                    evidence=[f"{missing_callbacks} plugin block(s) missing buttonPressed(Object)"],
                )
        if active_source and CUSTOM_DIALOG_DELEGATE_PATTERN.search(text) and re.search(r"\bcreateCustomDialog\s*\(\s*CustomPanelAPI\s+\w+\s*\)", text):
            result.add(
                id="legacy-custom-dialog-delegate-signature",
                category="source-api",
                severity="high",
                classification="REVIEW",
                confidence="HIGH",
                explanation="CustomDialogDelegate#createCustomDialog now receives CustomDialogCallback in 0.98a. Update the signature and preserve any required callback behavior before runtime-testing the dialog.",
                file=relative,
                evidence=["createCustomDialog(CustomPanelAPI)"],
            )
        if active_source and RELEASE_BLOCKING_TODO_PATTERN.search(text):
            result.add(
                id="release-blocking-source-todo",
                category="source",
                severity="high",
                classification="REVIEW",
                confidence="HIGH",
                explanation="Active source contains a TODO/FIXME explicitly saying behavior must be removed, deleted, or disabled before release. Inspect it as a possible development-only gameplay or save-state leak.",
                file=relative,
                evidence=["TODO/FIXME release-removal marker"],
            )
        if active_source and ROBOT_INPUT_INJECTION_PATTERN.search(text):
            result.add(
                id="campaign-ui-robot-input-injection",
                category="campaign-ui",
                severity="medium",
                classification="REVIEW",
                confidence="DETERMINISTIC",
                explanation="Campaign UI code creates java.awt.Robot to synthesize operating-system input. This can fail under restricted desktops, overlays, focus changes, or platform-specific input handling; prefer an in-game UI transition when possible and runtime-test every affected dialog.",
                file=relative,
                evidence=["new Robot()"],
            )
        if active_source and MEMORY_SELF_STORE_PATTERN.search(text):
            result.add(
                id="campaign-memory-live-object",
                category="save-risk",
                severity="medium",
                classification="REVIEW",
                confidence="HIGH",
                explanation="Campaign memory stores `this`, a live Java object. Persistent campaign memory should normally use primitive values, IDs, or serializable data; inspect save/load behavior and replace UI/runtime objects where practical.",
                file=relative,
                evidence=["MemoryAPI.set(..., this)"],
            )
        if active_source and PERCENT_MULTIPLIER_PATTERN.search(text):
            result.add(
                id="suspicious-percent-multiplier",
                category="combat-stats",
                severity="medium",
                classification="REVIEW",
                confidence="HIGH",
                explanation="modifyPercent() received a multiplier-shaped expression (for example, 1f - penalty * 0.01f). It will apply approximately +1 percent rather than the intended multiplier or negative percentage in Starsector's mutable-stat API.",
                file=relative,
                evidence=["modifyPercent(..., 1f - value * 0.01f)"],
            )
        if active_source:
            for system_name in HARDCODED_SYSTEM_LOOKUP_PATTERN.findall(text):
                result.add(
                    id="hard-coded-campaign-system-reference",
                    category="campaign",
                    severity="medium",
                    classification="REVIEW",
                    confidence="DETERMINISTIC",
                    explanation="Campaign code looks up a star system using a literal string. Verify that it is the stable system ID, that the target is guaranteed to exist, and that optional/total-conversion environments are guarded.",
                    file=relative,
                    evidence=[system_name],
                )
            for entity_id in HARDCODED_ENTITY_LOOKUP_PATTERN.findall(text):
                result.add(
                    id="hard-coded-campaign-entity-reference",
                    category="campaign",
                    severity="medium",
                    classification="REVIEW",
                    confidence="DETERMINISTIC",
                    explanation="Campaign code looks up an entity by a fixed ID. Verify that the entity is created before this code runs and null-check optional or save-dependent entities before dereferencing them.",
                    file=relative,
                    evidence=[entity_id],
                )
            for integration, prefix in EXTERNAL_CAMPAIGN_MEMORY_PREFIXES.items():
                keys = sorted(set(re.findall(rf'"({re.escape(prefix)}[A-Za-z0-9_]+)"', text)))
                if keys:
                    result.add(
                        id="external-campaign-memory-key",
                        category="campaign",
                        severity="medium",
                        classification="REVIEW",
                        confidence="DETERMINISTIC",
                        explanation=f"Campaign code reads {integration}-namespaced memory state directly. Verify the integration is optional, null-safe, and tested with {integration} disabled.",
                        file=relative,
                        evidence=[integration, *keys],
                    )
        commented_spawns = re.findall(r"//[^\r\n]*\b(?:addSpawnPoint|spawnFleet)\s*\(", text)
        uncommented_text = re.sub(r"//[^\r\n]*", "", text)
        active_spawns = re.findall(r"\b(?:addSpawnPoint|spawnFleet)\s*\(", uncommented_text)
        if active_source and commented_spawns and not active_spawns:
            result.add(
                id="campaign-spawn-registration-disabled",
                category="campaign",
                severity="high",
                classification="REVIEW",
                confidence="HIGH",
                explanation="Campaign fleet-spawn calls are present only in comments. The mod may generate its system but will not create those fleets until the spawning code is ported and enabled.",
                file=relative,
                evidence=[f"{len(commented_spawns)} commented spawn call(s)"],
            )
    result.imports = sorted(imports)
    for paths in content_owners.values():
        if len(paths) > 1:
            result.add(id="duplicate-source-layout", category="source", severity="medium", classification="REVIEW", confidence="DETERMINISTIC", explanation="Identical Java source appears at multiple paths. Establish the authoritative source/JAR layout before compiling or modifying it.", evidence=sorted(paths))
    _scan_mission_local_fleet_references(root, result)
    _scan_source_build_dependencies(root, result)

    scan_lazylib_compat(root, result)
    scan_magiclib_compat(result)
    scan_ashlib_compat(root, result)
    scan_graphicslib_compat(root, result)


def _scan_source_build_dependencies(root: Path, result: ScanResult) -> None:
    lombok_imports = sorted(item for item in result.imports if item == "lombok" or item.startswith("lombok."))
    if lombok_imports:
        build_files = [name for name in ("pom.xml", "build.gradle", "build.gradle.kts") if (root / name).is_file()]
        detail = " Build metadata was not found." if not build_files else f" Build metadata found: {', '.join(build_files)}."
        result.add(
            id="source-lombok-annotation-processing",
            category="build",
            severity="high",
            classification="MANUAL",
            confidence="DETERMINISTIC",
            explanation="Source imports Lombok, which generates methods and constructors during compilation. A plain javac rebuild will fail or produce missing members unless Lombok is supplied as an annotation processor." + detail,
            evidence=lombok_imports,
        )
    for dependency, prefixes in EXTERNAL_MOD_API_PACKAGES.items():
        imports = sorted(item for item in result.imports if any(item == prefix.rstrip(".") or item.startswith(prefix) for prefix in prefixes))
        if imports:
            result.add(
                id="external-mod-api-import",
                category="dependencies",
                severity="high",
                classification="MANUAL",
                confidence="DETERMINISTIC",
                explanation=f"Source imports {dependency}'s API directly. Compile and runtime compatibility require that optional mod, or an explicit source-level compatibility shim/removal.",
                evidence=[dependency, *imports],
            )


def _custom_ui_plugins_missing_button_callback(text: str) -> int:
    """Return plugin blocks that lack the 0.98a button callback.

    This is deliberately brace-aware rather than file-wide: an anonymous
    plugin can be missing the callback even when another implementation in the
    same source file defines one. Java parsing is not required for this narrow
    structural check, and an unmatched brace simply leaves that block for
    manual review.
    """
    missing = 0
    for match in CUSTOM_UI_PLUGIN_PATTERN.finditer(text):
        opening = match.end() - 1 if text[match.end() - 1] == "{" else text.find("{", match.end())
        if opening < 0:
            missing += 1
            continue
        depth = 0
        closing = -1
        for index in range(opening, len(text)):
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
                if depth == 0:
                    closing = index
                    break
        block = text[opening: closing + 1] if closing >= 0 else text[opening:]
        if not re.search(r"\bbuttonPressed\s*\(", block):
            missing += 1
    return missing


def _scan_mission_local_fleet_references(root: Path, result: ScanResult) -> None:
    mod_id = str(result.metadata.get("id") or "").strip()
    if not mod_id:
        return
    prefix = f"{mod_id}_"
    variants = {path.stem for path in (root / "data" / "variants").glob("*.variant")}
    hulls = {path.stem for path in (root / "data" / "hulls").glob("*.ship")}
    weapons = {path.stem for path in (root / "data" / "weapons").glob("*.wpn")}
    wing_data = root / "data" / "hulls" / "wing_data.csv"
    wings: set[str] = set()
    if wing_data.is_file():
        try:
            with wing_data.open("r", encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    wing_id = row.get("id")
                    if wing_id:
                        wings.add(wing_id)
        except (OSError, csv.Error, UnicodeDecodeError):
            return
    mission_sources = {
        * (root / "src").glob("data/missions/*/MissionDefinition.java"),
        * (root / "data").glob("missions/*/MissionDefinition.java"),
    }
    references: list[dict[str, str]] = []
    inspected_variants: set[str] = set()
    for source in sorted(mission_sources):
        try:
            text = source.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for fleet_id, member_type in MISSION_FLEET_REFERENCE_PATTERN.findall(text):
            resolution = "external-or-core"
            if fleet_id.startswith(prefix):
                resolution = "resolved-local" if fleet_id in (variants if member_type == "SHIP" else wings) else "missing-local"
            references.append({"file": _relative(root, source), "kind": member_type, "id": fleet_id, "resolution": resolution})
            if not fleet_id.startswith(prefix):
                continue
            expected = variants if member_type == "SHIP" else wings
            if fleet_id not in expected:
                result.add(
                    id="mission-local-fleet-reference-missing",
                    category="missions",
                    severity="high",
                    classification="MANUAL",
                    confidence="DETERMINISTIC",
                    explanation="A mission references a fleet member with this mod's ID prefix, but the corresponding local variant or fighter wing was not found.",
                    file=_relative(root, source),
                    evidence=[f"{member_type}:{fleet_id}", "resolution: missing-local"],
                )
            elif member_type == "SHIP" and fleet_id not in inspected_variants:
                inspected_variants.add(fleet_id)
                _scan_mission_variant_assets(root, result, fleet_id, prefix, hulls, weapons)
    result.migration_context["mission_fleet_references"] = references


def _scan_mission_variant_assets(root: Path, result: ScanResult, variant_id: str, prefix: str, hulls: set[str], weapons: set[str]) -> None:
    path = root / "data" / "variants" / f"{variant_id}.variant"
    try:
        data, _ = _parse_json(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return
    if not isinstance(data, dict):
        return
    hull_id = data.get("hullId")
    if isinstance(hull_id, str) and hull_id.startswith(prefix) and hull_id not in hulls:
        result.add(
            id="mission-local-variant-hull-missing",
            category="missions",
            severity="high",
            classification="MANUAL",
            confidence="DETERMINISTIC",
            explanation="A locally referenced mission variant uses a hull with this mod's ID prefix, but no matching local .ship definition was found.",
            file=_relative(root, path),
            evidence=[f"variant:{variant_id}", f"hull:{hull_id}", "resolution: missing-local"],
        )
    weapon_ids: set[str] = set()
    for group in data.get("weaponGroups", []):
        if not isinstance(group, dict):
            continue
        assigned = group.get("weapons", {})
        if isinstance(assigned, dict):
            weapon_ids.update(value for value in assigned.values() if isinstance(value, str))
    missing_weapons = sorted(weapon_id for weapon_id in weapon_ids if weapon_id.startswith(prefix) and weapon_id not in weapons)
    if missing_weapons:
        result.add(
            id="mission-local-variant-weapon-missing",
            category="missions",
            severity="high",
            classification="MANUAL",
            confidence="DETERMINISTIC",
            explanation="A locally referenced mission variant uses weapon IDs with this mod's prefix, but matching local .wpn definitions were not found.",
            file=_relative(root, path),
            evidence=[f"variant:{variant_id}", *[f"weapon:{weapon_id}" for weapon_id in missing_weapons], "resolution: missing-local"],
        )


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


def _source_class_index(root: Path) -> dict[str, str]:
    names: dict[str, str] = {}
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
            names[f"{package.group(1)}.{declared.group(1)}"] = _relative(root, path)
    return names


def _scan_configured_class_integrity(root: Path, result: ScanResult) -> None:
    local_classes = _source_class_index(root)
    references: set[str] = set()
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".csv", ".json", ".faction", ".ship", ".variant", ".system"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        references.update(re.findall(r"\bdata(?:\.[A-Za-z_$][\w$]*)+", text))
    source_only = sorted(set(local_classes) & references - result.compiled_class_names)
    packaged = sorted(references & result.compiled_class_names)
    unresolved = sorted(references - set(local_classes) - result.compiled_class_names)
    entrypoint_sources = sorted(local_classes[name] for name in set(local_classes) & references)
    result.migration_context["configured_class_integrity"] = {
        "source_class_names": sorted(local_classes),
        "configured_references": sorted(references),
        "source_only": source_only,
        "packaged": packaged,
        "unresolved": unresolved,
        "configured_entrypoint_sources": entrypoint_sources,
    }
    for finding in result.findings:
        if finding.file in entrypoint_sources and finding.id in {"runtime-placeholder-unsupported-operation", "campaign-spawn-registration-disabled", "missing-custom-ui-button-pressed-callback", "legacy-custom-dialog-delegate-signature"}:
            finding.evidence.append("reachability: configured-entrypoint")
        elif finding.id == "runtime-placeholder-unsupported-operation":
            finding.evidence.append("reachability: active-source-unconfigured")
    if source_only:
        result.add(id="configured-source-class-missing-from-jar", category="bytecode", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation="Mod data references active local source classes that are absent from every scanned JAR. Compile/package the active sources before runtime testing; this finding does not claim that every unresolved configured class belongs to this mod.", evidence=source_only)


def _scan_campaign_identifier_context(root: Path, result: ScanResult) -> None:
    """Attribute literal campaign lookups without assuming a global ID registry.

    A local definition is deterministic evidence. A mod-ID prefix is only a
    useful hint, so it remains explicitly labeled as such instead of becoming a
    compatibility claim.
    """
    mod_id = str(result.metadata.get("id") or "").strip()
    local_systems: set[str] = set()
    local_entities: set[str] = set()
    for source in root.rglob("*.java"):
        if "disabled_files" in source.relative_to(root).parts:
            continue
        try:
            text = source.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        local_systems.update(CAMPAIGN_SYSTEM_CREATION_PATTERN.findall(text))
        local_entities.update(CAMPAIGN_ENTITY_CREATION_PATTERN.findall(text))

    def ownership(identifier: str, defined: set[str]) -> str:
        if identifier in defined:
            return "defined-locally"
        if mod_id and identifier.startswith(f"{mod_id}_"):
            return "likely-mod-local-prefix"
        return "external-or-core-unresolved"

    lookups: list[dict[str, str]] = []
    for finding in result.findings:
        if finding.id == "hard-coded-campaign-system-reference" and finding.evidence:
            identifier = finding.evidence[0]
            state = ownership(identifier, local_systems)
            finding.evidence.append(f"ownership: {state}")
            lookups.append({"kind": "system", "id": identifier, "ownership": state})
        elif finding.id == "hard-coded-campaign-entity-reference" and finding.evidence:
            identifier = finding.evidence[0]
            state = ownership(identifier, local_entities)
            finding.evidence.append(f"ownership: {state}")
            lookups.append({"kind": "entity", "id": identifier, "ownership": state})
    result.migration_context["campaign_identifier_context"] = {
        "defined_system_ids": sorted(local_systems),
        "defined_entity_ids": sorted(local_entities),
        "lookups": lookups,
    }


def _annotate_source_reachability(root: Path, result: ScanResult) -> None:
    """Resolve only unambiguous local class-qualified calls from configured roots."""
    integrity = result.migration_context.get("configured_class_integrity", {})
    entrypoints = set(integrity.get("configured_entrypoint_sources", []))
    source_index = _source_class_index(root)
    by_simple_name: dict[str, set[str]] = {}
    for class_name, file in source_index.items():
        by_simple_name.setdefault(class_name.rsplit(".", 1)[-1], set()).add(file)
    calls: dict[str, list[str]] = {}
    for fact in result.source_facts:
        if fact.get("kind") == "call_edge":
            calls.setdefault(str(fact["file"]), []).append(str(fact["value"]))
    reachable = set(entrypoints)
    pending = list(sorted(entrypoints))
    resolved_edges: list[dict[str, str]] = []
    uncertain_edges = 0
    while pending:
        source = pending.pop()
        for edge in calls.get(source, []):
            _, _, select = edge.partition("->")
            receiver, separator, _ = select.partition(".")
            candidates = by_simple_name.get(receiver, set()) if separator else set()
            if len(candidates) != 1:
                uncertain_edges += 1
                continue
            target = next(iter(candidates))
            resolved_edges.append({"from": source, "to": target, "call": select})
            if target not in reachable:
                reachable.add(target)
                pending.append(target)
    result.migration_context["source_reachability"] = {
        "configured_entrypoint_sources": sorted(entrypoints),
        "reachable_local_sources": sorted(reachable),
        "resolved_local_edges": sorted(resolved_edges, key=lambda item: (item["from"], item["to"], item["call"])),
        "uncertain_call_edge_count": uncertain_edges,
        "limitation": "Only unambiguous local class-qualified calls are followed; unqualified, instance, inherited, reflective, and dependency calls remain unresolved.",
    }
    tracked = {"runtime-placeholder-unsupported-operation", "campaign-spawn-registration-disabled", "missing-custom-ui-button-pressed-callback", "legacy-custom-dialog-delegate-signature"}
    for finding in result.findings:
        if finding.id not in tracked or not finding.file:
            continue
        if finding.file in entrypoints and "reachability: configured-entrypoint" not in finding.evidence:
            finding.evidence.append("reachability: configured-entrypoint")
        elif finding.file in reachable and "reachability: reachable-local-call" not in finding.evidence:
            finding.evidence.append("reachability: reachable-local-call")


def _attribute_library_usage(result: ScanResult) -> None:
    dependencies = " ".join(map(str, result.metadata.get("dependencies") or result.metadata.get("requiredDependencies") or [])).lower()
    calls = [fact.get("value", "") for fact in result.source_facts if fact.get("kind") == "method_invocation"]
    for library, prefixes in LIBRARY_PACKAGES.items():
        imports = [item for item in result.imports if any(item.startswith(prefix) for prefix in prefixes)]
        simple_names = {item.rsplit(".", 1)[-1] for item in imports if not item.endswith(".*")}
        source_calls = [call for call in calls if call.split(".", 1)[0] in simple_names]
        bundled = any(LIBRARY_PATTERNS[library].search(str(item.get("path", ""))) for item in result.jars)
        declared = library.lower() in dependencies or library.replace("Lib", "").lower() in dependencies
        bytecode_referenced = library in result.bytecode_library_references
        if declared or bundled or imports:
            result.library_usage.append({"library": library, "declared": declared, "bundled": bundled, "imported": bool(imports), "source_called": bool(source_calls), "bytecode_referenced": bytecode_referenced, "evidence": {"imports": imports, "source_calls": source_calls}})
            if declared and not bundled and not imports:
                result.add(id="declared-library-unreferenced", category="dependencies", severity="medium", classification="REVIEW", confidence="DETERMINISTIC", explanation="A declared library has no bundled, import, or source-call evidence. Confirm whether it is required before removing or changing it.", evidence=[library])


def _dependency_compatibility_context(result: ScanResult) -> None:
    """Record dependency evidence without guessing API replacements or versions."""
    raw_declared = result.metadata.get("dependencies") or result.metadata.get("requiredDependencies") or []
    declared: list[dict[str, str | None]] = []
    normalized: set[str] = set()
    for item in raw_declared:
        if isinstance(item, dict):
            dependency_id = str(item.get("id") or "").strip() or None
            dependency_name = str(item.get("name") or "").strip() or None
        else:
            dependency_id = str(item).strip() or None
            dependency_name = None
        declared.append({"id": dependency_id, "name": dependency_name})
        normalized.update(re.sub(r"[^a-z0-9]", "", value.lower()) for value in (dependency_id, dependency_name) if value)
    direct_apis: list[dict[str, object]] = []
    for finding in result.findings:
        if finding.id != "external-mod-api-import" or not finding.evidence:
            continue
        dependency = finding.evidence[0]
        key = re.sub(r"[^a-z0-9]", "", dependency.lower())
        direct_apis.append({"dependency": dependency, "declared": key in normalized, "imports": finding.evidence[1:]})
    result.migration_context["dependency_compatibility"] = {
        "declared_dependencies": declared,
        "direct_api_dependencies": direct_apis,
        "library_usage": result.library_usage,
        "limitation": "Static evidence does not establish an installed dependency version or API-symbol compatibility.",
    }


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
    _annotate_source_reachability(root, result)
    _scan_campaign_identifier_context(root, result)
    _attribute_library_usage(result)
    _dependency_compatibility_context(result)
    _infer_environment(result)
    return result
