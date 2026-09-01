from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .workspace import resolve_inside, workspace_paths


def create_runtime_profile(workspace: Path, executable: Path, arguments: list[str], working_directory: Path, timeout_seconds: int, log_file: str | None = None, required_markers: list[str] | None = None) -> dict:
    workspace = workspace.expanduser().resolve()
    workspace_paths(workspace)
    executable = executable.expanduser().resolve()
    working_directory = working_directory.expanduser().resolve()
    if not executable.is_file() or not working_directory.is_dir():
        raise ValueError("Runtime executable or working directory does not exist.")
    if timeout_seconds <= 0:
        raise ValueError("Runtime timeout must be positive.")
    if log_file is not None:
        resolve_inside(working_directory, log_file)
    profile = {"schema_version": 1, "executable": str(executable), "arguments": arguments, "working_directory": str(working_directory), "timeout_seconds": timeout_seconds, "log_file": log_file, "required_markers": required_markers or [], "execution_requires_explicit_flag": True}
    (workspace / "runtime-profile.json").write_text(json.dumps(profile, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return profile


def run_runtime_smoke(workspace: Path, execute: bool = False) -> dict:
    workspace = workspace.expanduser().resolve()
    workspace_paths(workspace)
    profile_path = workspace / "runtime-profile.json"
    if not profile_path.is_file():
        raise ValueError("No runtime profile found. Create one first.")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    if not execute:
        return {"status": "NOT_EXECUTED", "reason": "Pass --execute to explicitly launch the configured runtime profile."}
    command = [profile["executable"], *profile["arguments"]]
    try:
        completed = subprocess.run(command, cwd=profile["working_directory"], capture_output=True, text=True, timeout=profile["timeout_seconds"], check=False)
        markers = profile.get("required_markers") or []
        log_validation = {"status": "NOT_CONFIGURED"}
        if profile.get("log_file"):
            log_path = resolve_inside(Path(profile["working_directory"]), profile["log_file"])
            text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
            missing = [marker for marker in markers if marker not in text]
            log_validation = {"status": "PASS" if log_path.is_file() and not missing else "FAILED", "log_file": profile["log_file"], "missing_markers": missing}
        result = {"status": "PASS" if completed.returncode == 0 and log_validation["status"] != "FAILED" else "FAILED", "exit_code": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr, "log_validation": log_validation}
    except subprocess.TimeoutExpired as exc:
        result = {"status": "TIMED_OUT", "stdout": exc.stdout or "", "stderr": exc.stderr or ""}
    (workspace / "runtime-result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result
