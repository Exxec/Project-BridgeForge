from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


class ReferenceRigError(ValueError):
    """Raised when a historical Starsector install cannot be registered safely."""


DEFAULT_REGISTRY_RELATIVE = Path("bridgeforge-state") / "reference-rigs"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_version(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())


def _find_java(install: Path) -> Path | None:
    candidates = (
        install / "jre" / "bin" / "java.exe",
        install / "jre" / "bin" / "java",
        install / "starsector-core" / "jre" / "bin" / "java.exe",
        install / "starsector-core" / "jre" / "bin" / "java",
    )
    return next((path for path in candidates if path.is_file()), None)


def _java_release(java: Path | None) -> dict[str, object] | None:
    if java is None:
        return None
    release = java.parent.parent / "release"
    version = None
    if release.is_file():
        match = re.search(r'^JAVA_VERSION="([^"]+)"', release.read_text(encoding="utf-8", errors="replace"), re.M)
        version = match.group(1) if match else None
    return {"path": str(java), "sha256": _sha256(java), "version": version, "version_source": str(release) if version else None}


def _find_run_command(install: Path) -> Path | None:
    names = ("starsector.bat", "starsector.exe", "starsector.sh")
    return next((install / name for name in names if (install / name).is_file()), None)


def build_reference_rig_manifest(install: Path, *, game_version: str) -> dict[str, object]:
    """Inventory a dedicated historical install without changing or launching it."""
    install = Path(install).expanduser().resolve()
    if not game_version.strip():
        raise ReferenceRigError("game version must be non-empty")
    core = install / "starsector-core"
    api = core / "starfarer.api.jar"
    if not install.is_dir() or not core.is_dir() or not api.is_file():
        raise ReferenceRigError("reference install must contain starsector-core/starfarer.api.jar")
    run_command = _find_run_command(install)
    if run_command is None:
        raise ReferenceRigError("reference install has no starsector.bat, starsector.exe, or starsector.sh run command")
    java = _java_release(_find_java(install))
    return {
        "schema_version": 1,
        "mode": "REFERENCE_RIG",
        "game_version": game_version.strip(),
        "install": str(install),
        "isolation": {
            "kind": "dedicated-install",
            "asserted_by": "rig-create invocation",
            "verified": False,
            "limitation": "BridgeForge cannot prove that the selected folder is not the player's primary install.",
        },
        "core_api": {"path": str(api), "sha256": _sha256(api)},
        "bundled_java": java,
        "run_command": {"path": str(run_command), "working_directory": str(install)},
        "saves_directory": str(install / "saves"),
        "probe_support": "UNSUPPORTED_USE_SAVE_BASELINE",
    }


def write_reference_rig_manifest(
    install: Path,
    *,
    game_version: str,
    output: Path | None = None,
    repo_root: Path | None = None,
    replace: bool = False,
) -> Path:
    manifest = build_reference_rig_manifest(install, game_version=game_version)
    if output is None:
        root = Path(repo_root).resolve() if repo_root is not None else Path(__file__).resolve().parent.parent
        output = root / DEFAULT_REGISTRY_RELATIVE / f"{_safe_version(game_version)}.json"
    path = Path(output).expanduser().resolve()
    if path.exists() and not replace:
        raise ReferenceRigError(f"reference-rig manifest already exists: {path}; pass --replace to replace it")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def load_reference_rig_manifest(path: Path) -> dict[str, object]:
    path = Path(path).expanduser().resolve()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReferenceRigError(f"could not read reference-rig manifest at {path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1 or payload.get("mode") != "REFERENCE_RIG":
        raise ReferenceRigError(f"{path} is not a reference-rig schema version 1 manifest")
    return payload


def verify_reference_rig_manifest(path: Path) -> dict[str, object]:
    """Check that a registered install and its immutable identity inputs have not drifted."""
    manifest = load_reference_rig_manifest(path)
    install = Path(str(manifest.get("install", ""))).resolve()
    expected_api = manifest.get("core_api")
    api = install / "starsector-core" / "starfarer.api.jar"
    checks: list[dict[str, str]] = []
    checks.append({"name": "reference_install_exists", "status": "PASS" if api.is_file() else "FAIL", "detail": str(api)})
    if api.is_file() and isinstance(expected_api, dict):
        actual = _sha256(api)
        expected = expected_api.get("sha256")
        checks.append({"name": "reference_core_identity", "status": "PASS" if actual == expected else "FAIL", "detail": f"expected={expected} actual={actual}"})
    run = manifest.get("run_command")
    run_path = Path(str(run.get("path", ""))) if isinstance(run, dict) else Path()
    checks.append({"name": "reference_run_command", "status": "PASS" if run_path.is_file() else "FAIL", "detail": str(run_path)})
    java = manifest.get("bundled_java")
    if isinstance(java, dict):
        java_path = Path(str(java.get("path", "")))
        actual = _sha256(java_path) if java_path.is_file() else None
        checks.append({"name": "reference_bundled_java", "status": "PASS" if actual == java.get("sha256") else "FAIL", "detail": f"{java_path}; version={java.get('version') or 'UNKNOWN'}"})
    else:
        checks.append({"name": "reference_bundled_java", "status": "WARN", "detail": "No bundled Java executable was found at registration."})
    status = "FAIL" if any(item["status"] == "FAIL" for item in checks) else ("WARN" if any(item["status"] == "WARN" for item in checks) else "PASS")
    return {"schema_version": 1, "mode": "REFERENCE_RIG_VERIFY", "manifest": str(Path(path).resolve()), "runtime_dir": str(install), "game_version": manifest.get("game_version"), "status": status, "checks": checks}
