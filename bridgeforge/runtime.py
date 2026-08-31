from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .workspace import workspace_paths


def create_runtime_profile(workspace: Path, executable: Path, arguments: list[str], working_directory: Path, timeout_seconds: int) -> dict:
    workspace = workspace.expanduser().resolve()
    workspace_paths(workspace)
    executable = executable.expanduser().resolve()
    working_directory = working_directory.expanduser().resolve()
    if not executable.is_file() or not working_directory.is_dir():
        raise ValueError("Runtime executable or working directory does not exist.")
    if timeout_seconds <= 0:
        raise ValueError("Runtime timeout must be positive.")
    profile = {"schema_version": 1, "executable": str(executable), "arguments": arguments, "working_directory": str(working_directory), "timeout_seconds": timeout_seconds, "execution_requires_explicit_flag": True}
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
        result = {"status": "PASS" if completed.returncode == 0 else "FAILED", "exit_code": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}
    except subprocess.TimeoutExpired as exc:
        result = {"status": "TIMED_OUT", "stdout": exc.stdout or "", "stderr": exc.stderr or ""}
    (workspace / "runtime-result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result
