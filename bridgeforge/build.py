from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
import tempfile
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from .library_registry import LibraryRegistryEntry
from .models import TargetProfile
from .scanner import scan_mod
from .workspace import resolve_inside, workspace_paths


@dataclass(frozen=True)
class JdkDescriptor:
    home: str
    metadata: dict[str, str]
    javac: str | None


@dataclass(frozen=True)
class BuildProfile:
    schema_version: int
    target: TargetProfile
    jdk: JdkDescriptor | None
    source_roots: list[str]
    api_jars: list[str]
    dependency_jars: list[str]
    classes_directory: str
    command_preview: list[str]
    compile_validation: dict


def read_jdk(home: Path | None) -> JdkDescriptor | None:
    if home is None:
        return None
    home = home.expanduser().resolve()
    release = home / "release"
    if not release.is_file():
        raise ValueError(f"JDK release metadata not found: {release}")
    metadata: dict[str, str] = {}
    for line in release.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            metadata[key] = value.strip().strip('"')
    javac = home / "bin" / ("javac.exe" if __import__("os").name == "nt" else "javac")
    return JdkDescriptor(home=str(home), metadata=metadata, javac=str(javac) if javac.is_file() else None)


def resolve_registered_dependency_jars(working: Path, target: TargetProfile, registry: dict[str, LibraryRegistryEntry] | None) -> tuple[list[Path], list[dict[str, object]]]:
    """Auto-resolve a mod's declared dependency ids to local jars via a library registry.

    Reuses scan_mod's own tolerant mod_info.json parsing rather than
    reimplementing it, so this degrades exactly the same way scanning
    already does when metadata can't be trusted. A declared dependency
    with no supplied registry, no matching id, or a registered path that
    no longer exists on disk produces a REVIEW finding explaining exactly
    why -- never a guess, and never silently skipped. Bridgeforge does not
    bundle, fetch, or assume the presence of third-party library jars.
    """
    scan = scan_mod(working, target)
    dependencies = scan.metadata.get("dependencies") or scan.metadata.get("requiredDependencies") or []
    resolved: list[Path] = []
    findings: list[dict[str, object]] = []
    for dependency in dependencies:
        library_id = dependency.get("id") if isinstance(dependency, dict) else None
        if not library_id:
            continue
        entry = registry.get(str(library_id)) if registry is not None else None
        if entry is None:
            reason = "no --library-registry was supplied" if registry is None else "the supplied library registry has no entry for it"
            findings.append({
                "id": "declared-dependency-unregistered",
                "classification": "REVIEW",
                "confidence": "DETERMINISTIC",
                "jar_kind": "dependency",
                "library_id": str(library_id),
                "explanation": f"mod_info.json declares a dependency on {library_id!r}, but {reason}. Compile validation involving it is unverified, not confirmed unnecessary.",
            })
            continue
        candidate = Path(entry.path).expanduser()
        if not candidate.is_file():
            findings.append({
                "id": "declared-dependency-unregistered",
                "classification": "REVIEW",
                "confidence": "DETERMINISTIC",
                "jar_kind": "dependency",
                "library_id": str(library_id),
                "explanation": f"The library registry names a path for {library_id!r} that no longer exists on disk: {candidate}. Compile validation involving it is unverified, not confirmed unnecessary.",
            })
            continue
        resolved.append(candidate)
    return resolved, findings


def create_build_profile(workspace: Path, target: TargetProfile, jdk_home: Path | None, api_jars: list[Path], dependency_jars: list[Path], library_registry: dict[str, LibraryRegistryEntry] | None = None) -> BuildProfile:
    workspace = workspace.expanduser().resolve()
    _, working, _ = workspace_paths(workspace)
    jdk = read_jdk(jdk_home)
    excluded_source_directories = {".git", ".idea", "build", "disabled_files", "jar", "out"}
    source_files = [
        path for path in sorted(working.rglob("*.java"))
        if not any(part in excluded_source_directories for part in path.relative_to(working).parts)
    ]
    source_roots = sorted({path.parent for path in source_files})
    registered_jars, registry_findings = resolve_registered_dependency_jars(working, target, library_registry)
    explicit_resolved = {path.expanduser().resolve() for path in dependency_jars}
    dependency_jars = list(dependency_jars) + [jar for jar in registered_jars if jar.resolve() not in explicit_resolved]
    requested_jars = [("api", path) for path in api_jars] + [("dependency", path) for path in dependency_jars]
    available_jars = [(kind, path.expanduser().resolve()) for kind, path in requested_jars if path.expanduser().is_file()]
    missing_jars = [(kind, path.expanduser().resolve()) for kind, path in requested_jars if not path.expanduser().is_file()]
    api = [str(path) for kind, path in available_jars if kind == "api"]
    dependencies = [str(path) for kind, path in available_jars if kind == "dependency"]
    findings = [
        {
            "id": "compile-validation-unavailable",
            "classification": "REVIEW",
            "confidence": "DETERMINISTIC",
            "jar_kind": kind,
            "jar": str(path),
            "explanation": f"The requested {kind} JAR is unavailable, so compile validation cannot verify sources against it. The remaining modernization pipeline will continue without compilation.",
        }
        for kind, path in missing_jars
    ] + registry_findings
    compile_validation = {"status": "UNAVAILABLE" if findings else "AVAILABLE", "findings": findings}
    classes = workspace / "build" / "classes"
    command = [jdk.javac if jdk and jdk.javac else "<javac-not-configured>", "--release", str(target.java), "-d", str(classes)]
    classpath = [*api, *dependencies]
    if classpath:
        command.extend(["-classpath", __import__("os").pathsep.join(classpath)])
    command.extend(str(source) for source in source_files)
    profile = BuildProfile(1, target, jdk, [str(path.relative_to(working)).replace("\\", "/") for path in source_roots], api, dependencies, str(classes), command, compile_validation)
    (workspace / "build-profile.json").write_text(json.dumps(asdict(profile), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return profile


def preview_shell_command(profile: BuildProfile) -> str:
    return shlex.join(profile.command_preview)


def _classify_diagnostic(line: str) -> dict[str, str]:
    lower = line.lower()
    if "cannot find symbol" in lower:
        return {"kind": "missing-symbol", "classification": "REVIEW", "confidence": "DETERMINISTIC"}
    if "package " in lower and " does not exist" in lower:
        return {"kind": "missing-package", "classification": "REVIEW", "confidence": "DETERMINISTIC"}
    if "release version" in lower and "not supported" in lower:
        return {"kind": "unsupported-release", "classification": "MANUAL", "confidence": "DETERMINISTIC"}
    return {"kind": "compiler-error", "classification": "UNKNOWN", "confidence": "DETERMINISTIC"}


def run_compile(workspace: Path) -> dict:
    workspace = workspace.expanduser().resolve()
    _, _, _ = workspace_paths(workspace)
    profile_data = json.loads((workspace / "build-profile.json").read_text(encoding="utf-8"))
    validation = profile_data.get("compile_validation", {"status": "AVAILABLE", "findings": []})
    if validation.get("status") == "UNAVAILABLE":
        result = {"schema_version": 1, "status": "UNAVAILABLE", "success": None, "command": profile_data.get("command_preview", []), "diagnostics": [], "findings": validation.get("findings", []), "reason": "One or more requested compile-validation JARs are unavailable."}
        (workspace / "build-result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        report = ["# Bridgeforge compile report", "", "- Result: UNAVAILABLE", "- Reason: one or more requested API/dependency JARs are unavailable.", "", "## Unresolved compile-validation JARs", ""]
        for finding in result["findings"]:
            label = f"`{finding['jar']}`" if "jar" in finding else repr(finding.get("library_id", finding["id"]))
            report.extend([f"- [{finding['classification']}] {finding['jar_kind']} JAR: {label}", f"  - {finding['explanation']}"])
        report.extend(["", "## Scope boundary", "", "Compilation was skipped; this does not prove source, runtime, or behavioral compatibility.", ""])
        (workspace / "BUILD_REPORT.md").write_text("\n".join(report), encoding="utf-8")
        return result
    jdk = profile_data.get("jdk") or {}
    javac = jdk.get("javac")
    if not javac or not Path(javac).is_file():
        raise ValueError("Configured JDK compiler is unavailable. Create a build plan with a complete JDK.")
    classes = Path(profile_data["classes_directory"]).resolve()
    try:
        classes.relative_to(workspace)
    except ValueError as exc:
        raise ValueError("Build output must remain inside the workspace.") from exc
    command = list(profile_data["command_preview"])
    command[0] = javac
    if not any(argument.endswith(".java") for argument in command):
        raise ValueError("Build profile contains no Java source files.")
    classes.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".javac", delete=False) as handle:
        for argument in command[1:]:
            handle.write('"' + argument.replace('\\', '\\\\').replace('"', '\\"') + '"\n')
        argument_file = Path(handle.name)
    try:
        completed = subprocess.run([command[0], "@" + str(argument_file)], cwd=workspace, capture_output=True, text=True, check=False)
    finally:
        argument_file.unlink(missing_ok=True)
    diagnostics = [_classify_diagnostic(line) | {"raw": line} for line in completed.stderr.splitlines() if "error:" in line or "cannot find symbol" in line]
    result = {"schema_version": 1, "command": command, "exit_code": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr, "diagnostics": diagnostics, "success": completed.returncode == 0}
    (workspace / "build-result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = ["# Bridgeforge compile report", "", f"- Result: {'PASS' if result['success'] else 'FAILED'}", f"- Exit code: {completed.returncode}", f"- Diagnostics: {len(diagnostics)}", "", "## Scope boundary", "", "Compilation does not prove runtime or behavioral compatibility.", ""]
    (workspace / "BUILD_REPORT.md").write_text("\n".join(report), encoding="utf-8")
    return result


def package_compiled_jar(workspace: Path, input_jar: str, output_name: str | None = None) -> dict:
    """Package successful workspace classes into a new JAR, preserving the input JAR."""
    workspace = workspace.expanduser().resolve()
    _, working, _ = workspace_paths(workspace)
    result_path = workspace / "build-result.json"
    if not result_path.is_file() or not json.loads(result_path.read_text(encoding="utf-8")).get("success"):
        raise ValueError("Successful workspace compilation is required before packaging a JAR.")
    source = resolve_inside(working, input_jar)
    if source.suffix.lower() != ".jar" or not source.is_file():
        raise ValueError("Packaging requires an existing working-copy JAR.")
    classes = workspace / "build" / "classes"
    class_files = sorted(path for path in classes.rglob("*.class") if path.is_file())
    if not class_files:
        raise ValueError("Compilation produced no class files to package.")
    artifact_directory = workspace / "package-artifacts"
    output = resolve_inside(artifact_directory, output_name or source.name)
    if output.resolve() == source:
        raise ValueError("Packaged JAR output must differ from the working-copy input JAR.")
    output.parent.mkdir(parents=True, exist_ok=True)
    input_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    replacements = {path.relative_to(classes).as_posix(): path for path in class_files}
    try:
        with zipfile.ZipFile(source) as original:
            original_entries = {info.filename: original.read(info) for info in original.infolist()}
    except zipfile.BadZipFile as exc:
        raise ValueError("Packaging requires a readable JAR/ZIP archive.") from exc
    contents = {
        name: replacements[name].read_bytes() if name in replacements else data
        for name, data in original_entries.items()
    }
    contents.update({name: path.read_bytes() for name, path in replacements.items()})
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as packaged:
        for name in sorted(contents):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o40755 if name.endswith("/") else 0o100644) << 16
            packaged.writestr(info, contents[name], compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    manifest = {"schema_version": 1, "mode": "REVIEW_PACKAGED_JAR_OUTPUT_COPY", "input_jar": str(Path(input_jar).as_posix()), "output": str(output), "compiled_class_count": len(class_files), "input_sha256": input_sha256, "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "input_preserved": input_sha256 == hashlib.sha256(source.read_bytes()).hexdigest()}
    (artifact_directory / "package-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def compile_feedback(workspace: Path) -> dict:
    workspace = workspace.expanduser().resolve()
    _, working, _ = workspace_paths(workspace)
    result_path = workspace / "build-result.json"
    if not result_path.is_file():
        raise ValueError("No compile result found. Run `bridgeforge compile` first.")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    plan_path = workspace / "migration-plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8")) if plan_path.is_file() else {"migrations": []}
    feedback = []
    for diagnostic in result["diagnostics"]:
        raw = diagnostic["raw"]
        raw_path = raw.split(":", 1)[0] if ".java:" in raw else None
        try:
            file_hint = Path(raw_path).resolve().relative_to(working).as_posix() if raw_path else None
        except ValueError:
            file_hint = None
        candidates = [migration["rule_id"] for migration in plan["migrations"] if file_hint and migration["file"].endswith(file_hint)]
        feedback.append({"diagnostic": diagnostic, "planned_rule_candidates": candidates, "automatic_modification": "not performed"})
    summary = Counter(item["diagnostic"]["classification"] for item in feedback)
    artifact = {"schema_version": 1, "compile_status": result.get("status", "PASS" if result["success"] else "FAILED"), "compile_success": result["success"], "findings": feedback, "validation_findings": result.get("findings", []), "classification_counts": dict(summary)}
    (workspace / "compile-feedback.json").write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    compile_label = result.get("status", "PASS" if result["success"] else "FAILED")
    lines = ["# Bridgeforge compile feedback", "", f"- Compile result: {compile_label}", f"- Feedback findings: {len(feedback)}", ""]
    for finding in result.get("findings", []):
        label = f"`{finding['jar']}`" if "jar" in finding else repr(finding.get("library_id", finding["id"]))
        lines.extend([f"## [{finding['classification']}] {finding['id']}", "", f"- Requested {finding['jar_kind']} JAR: {label}", f"- {finding['explanation']}", ""])
    for item in feedback:
        diagnostic = item["diagnostic"]
        lines.extend([f"## [{diagnostic['classification']}] {diagnostic['kind']}", "", f"- Evidence: `{diagnostic['raw']}`", f"- Planned rule candidates: {', '.join(item['planned_rule_candidates']) or 'none'}", "- Automatic modification: not performed", ""])
    (workspace / "COMPILE_FEEDBACK.md").write_text("\n".join(lines), encoding="utf-8")
    return artifact
