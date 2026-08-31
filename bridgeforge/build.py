from __future__ import annotations

import json
import os
import shlex
import subprocess
import tempfile
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from .models import TargetProfile
from .workspace import workspace_paths


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


def create_build_profile(workspace: Path, target: TargetProfile, jdk_home: Path | None, api_jars: list[Path], dependency_jars: list[Path]) -> BuildProfile:
    workspace = workspace.expanduser().resolve()
    _, working, _ = workspace_paths(workspace)
    jdk = read_jdk(jdk_home)
    excluded_source_directories = {".git", ".idea", "build", "disabled_files", "jar", "out"}
    source_files = [
        path for path in sorted(working.rglob("*.java"))
        if not any(part in excluded_source_directories for part in path.relative_to(working).parts)
    ]
    source_roots = sorted({path.parent for path in source_files})
    api = [str(path.expanduser().resolve()) for path in api_jars]
    dependencies = [str(path.expanduser().resolve()) for path in dependency_jars]
    missing = [path for path in [*api_jars, *dependency_jars] if not path.expanduser().is_file()]
    if missing:
        raise ValueError("Selected API/dependency JAR does not exist: " + ", ".join(map(str, missing)))
    classes = workspace / "build" / "classes"
    command = [jdk.javac if jdk and jdk.javac else "<javac-not-configured>", "--release", str(target.java), "-d", str(classes)]
    classpath = [*api, *dependencies]
    if classpath:
        command.extend(["-classpath", __import__("os").pathsep.join(classpath)])
    command.extend(str(source) for source in source_files)
    profile = BuildProfile(1, target, jdk, [str(path.relative_to(working)).replace("\\", "/") for path in source_roots], api, dependencies, str(classes), command)
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
    artifact = {"schema_version": 1, "compile_success": result["success"], "findings": feedback, "classification_counts": dict(summary)}
    (workspace / "compile-feedback.json").write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = ["# Bridgeforge compile feedback", "", f"- Compile result: {'PASS' if result['success'] else 'FAILED'}", f"- Feedback findings: {len(feedback)}", ""]
    for item in feedback:
        diagnostic = item["diagnostic"]
        lines.extend([f"## [{diagnostic['classification']}] {diagnostic['kind']}", "", f"- Evidence: `{diagnostic['raw']}`", f"- Planned rule candidates: {', '.join(item['planned_rule_candidates']) or 'none'}", "- Automatic modification: not performed", ""])
    (workspace / "COMPILE_FEEDBACK.md").write_text("\n".join(lines), encoding="utf-8")
    return artifact
