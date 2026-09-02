from __future__ import annotations

import json
import hashlib
import subprocess
from pathlib import Path

from .workspace import resolve_inside, workspace_paths


RUNTIME_SCENARIOS = {"campaign-load", "mission-launch", "custom-ui"}


def _tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(root).as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def create_runtime_profile(workspace: Path, executable: Path, arguments: list[str], working_directory: Path, timeout_seconds: int, log_file: str | None = None, required_markers: list[str] | None = None, scenarios: list[str] | None = None, scenario_markers: dict[str, list[str]] | None = None) -> dict:
    workspace = workspace.expanduser().resolve()
    _, staged_mod, _ = workspace_paths(workspace)
    executable = executable.expanduser().resolve()
    working_directory = working_directory.expanduser().resolve()
    if not executable.is_file() or not working_directory.is_dir():
        raise ValueError("Runtime executable or working directory does not exist.")
    if timeout_seconds <= 0:
        raise ValueError("Runtime timeout must be positive.")
    scenarios = scenarios or []
    unsupported = sorted(set(scenarios) - RUNTIME_SCENARIOS)
    if unsupported:
        raise ValueError(f"Unsupported runtime scenario(s): {', '.join(unsupported)}")
    scenario_markers = scenario_markers or {}
    if set(scenario_markers) - set(scenarios):
        raise ValueError("Scenario marker assertions require the corresponding scenario to be selected.")
    if any(not marker for markers in scenario_markers.values() for marker in markers):
        raise ValueError("Scenario marker assertions may not be empty.")
    if log_file is not None:
        resolve_inside(working_directory, log_file)
    profile = {"schema_version": 3, "executable": str(executable), "arguments": arguments, "working_directory": str(working_directory), "staged_mod_directory": str(staged_mod), "staged_mod_tree_sha256": _tree_sha256(staged_mod), "timeout_seconds": timeout_seconds, "log_file": log_file, "required_markers": required_markers or [], "scenarios": scenarios, "scenario_markers": {scenario: list(markers) for scenario, markers in sorted(scenario_markers.items())}, "execution_requires_explicit_flag": True, "limitation": "Scenario labels and log markers are user-authored evidence. Bridgeforge does not prove that the game loaded the staged mod or exercised the labeled scenario."}
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
        return {"status": "NOT_EXECUTED", "scenarios": profile.get("scenarios", []), "reason": "Pass --execute to explicitly launch the configured runtime profile."}
    staged_mod = Path(profile["staged_mod_directory"])
    if not staged_mod.is_dir() or _tree_sha256(staged_mod) != profile.get("staged_mod_tree_sha256"):
        result = {"status": "STALE_STAGED_MOD", "scenarios": profile.get("scenarios", []), "reason": "The staged working copy changed after this runtime profile was recorded; create a new profile before executing."}
        (workspace / "runtime-result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return result
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
        scenario_validation = {}
        for scenario in profile.get("scenarios", []):
            expected = profile.get("scenario_markers", {}).get(scenario, [])
            missing = [marker for marker in expected if marker not in text] if profile.get("log_file") else expected
            scenario_validation[scenario] = {"status": "NOT_CONFIGURED" if not expected else "PASS" if not missing else "FAILED", "missing_markers": missing}
        scenarios_failed = any(item["status"] == "FAILED" for item in scenario_validation.values())
        result = {"status": "PASS" if completed.returncode == 0 and log_validation["status"] != "FAILED" and not scenarios_failed else "FAILED", "scenarios": profile.get("scenarios", []), "scenario_validation": scenario_validation, "exit_code": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr, "log_validation": log_validation}
    except subprocess.TimeoutExpired as exc:
        result = {"status": "TIMED_OUT", "stdout": exc.stdout or "", "stderr": exc.stderr or ""}
    (workspace / "runtime-result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result
