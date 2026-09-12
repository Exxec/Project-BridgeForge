from __future__ import annotations

import json
from pathlib import Path

from .boot_test import _is_link, _running_java_under
from .copy_drift import compare_copies
from .probe_mod_build import RELEASE_RELATIVE
from .scanner import _base_game_version, _load_lenient_json_file

TARGET_BASE_GAME_VERSION = "0.98a"
DEFAULT_BASELINE_RELATIVE = Path("bridgeforge-state") / "real-saves-baseline.json"

# Working copies are found by the project layout (In operation/README.md), keyed by the mod id in
# each copy's mod_info.json -- never by a hand-kept list:
#   In operation/<Mod>/working/      the one copy BridgeForge edits (wins when a mod is in both places)
#   Done/<Mod>/<release folder>/     a finished mod's released copy
# Folders starting with "_" (the rigs, _attic) and the per-mod original/, scratch/, reports/,
# builds/ and workspace/ folders are never working copies.
NON_WORKING_FOLDER_NAMES = {"original", "scratch", "reports", "builds", "workspace"}


def _repo_root() -> Path:
    """The BridgeForge repo root (this file lives at <repo_root>/bridgeforge/rig_doctor.py).

    A separate function (rather than inlining this in rig_doctor()) so tests can monkeypatch it to
    point at a throwaway fixture tree instead of the real repo.
    """
    return Path(__file__).resolve().parent.parent


def _declared_id(folder: Path) -> str | None:
    info = _load_lenient_json_file(folder / "mod_info.json") if (folder / "mod_info.json").is_file() else None
    mod_id = info.get("id") if isinstance(info, dict) else None
    return mod_id if isinstance(mod_id, str) and mod_id else None


def default_working_copies(repo_root: Path) -> dict[str, Path]:
    """Discover working copies by the layout convention (see NON_WORKING_FOLDER_NAMES above)."""
    repo_root = Path(repo_root)
    found: dict[str, Path] = {}
    for area in ("In operation", "Done"):  # In operation first: a mod under re-test beats its release
        base = repo_root / area
        if not base.is_dir():
            continue
        for mod_folder in sorted(p for p in base.iterdir() if p.is_dir() and not p.name.startswith("_")):
            if area == "In operation":
                candidates = [mod_folder / "working"]
            else:
                candidates = sorted(p for p in mod_folder.iterdir() if p.is_dir() and p.name not in NON_WORKING_FOLDER_NAMES)
            for candidate in candidates:
                mod_id = _declared_id(candidate) if candidate.is_dir() else None
                if mod_id and mod_id not in found:
                    found[mod_id] = candidate
    return found


def _check(name: str, status: str, detail: str) -> dict[str, object]:
    return {"name": name, "status": status, "detail": detail}


def _mods_by_id(mods_dir: Path) -> dict[str, Path]:
    """Map declared mod id -> its folder under mods_dir, reading mod_info.json leniently.

    iterdir()/is_dir() follow NTFS junctions/symlinks the same as a plain directory, so a rig mod
    folder that is itself a link (e.g. Flu-X's rig folder) is included like any other.
    """
    by_id: dict[str, Path] = {}
    if not mods_dir.is_dir():
        return by_id
    for child in sorted(p for p in mods_dir.iterdir() if p.is_dir()):
        info = _load_lenient_json_file(child / "mod_info.json")
        if isinstance(info, dict):
            mod_id = info.get("id")
            if isinstance(mod_id, str) and mod_id:
                by_id.setdefault(mod_id, child)
    return by_id


def _check_isolation(runtime_dir: Path) -> dict[str, object]:
    core_path = runtime_dir / "starsector-core"
    if _is_link(core_path):
        return _check("isolation", "PASS", f"{core_path} is a junction/symlink.")
    return _check(
        "isolation",
        "FAIL",
        f"{core_path} is not a junction/symlink; this rig is not isolated from a real Starsector install.",
    )


def _check_game_not_running(runtime_dir: Path) -> dict[str, object]:
    running = _running_java_under(runtime_dir)
    if not running:
        return _check("game_not_running", "PASS", "No java.exe process is running under this rig.")
    pids = ", ".join(str(item.get("pid")) for item in running)
    return _check(
        "game_not_running",
        "WARN",
        f"java.exe already running under {runtime_dir} (pid {pids}). Stop it before launching a new test.",
    )


def _check_probe_installed(runtime_dir: Path, repo_root: Path) -> dict[str, object]:
    release_dir = repo_root / RELEASE_RELATIVE
    rig_probe_dir = runtime_dir / "mods" / "bridgeforge-probe"
    fix_hint = f"probe-config <probe mod_dir> --runtime {runtime_dir} --install"
    if not release_dir.is_dir():
        return _check(
            "probe_installed",
            "FAIL",
            f"Repo probe release copy not found at {release_dir}. Run build-probe-mod --install-release first.",
        )
    if not rig_probe_dir.is_dir():
        return _check(
            "probe_installed",
            "WARN",
            f"Probe is not installed in the rig at {rig_probe_dir}. Fix: {fix_hint}",
        )
    result = compare_copies(release_dir, rig_probe_dir)
    if result["status"] == "PASS":
        return _check("probe_installed", "PASS", "Rig probe copy matches the repo release copy.")
    return _check(
        "probe_installed",
        "WARN",
        f"Rig probe copy has drifted from the repo release copy (drift_count={result['drift_count']}). Fix: {fix_hint}",
    )


def _check_enabled_mods_resolve(runtime_dir: Path) -> dict[str, object]:
    mods_dir = runtime_dir / "mods"
    enabled_path = mods_dir / "enabled_mods.json"
    if not enabled_path.is_file():
        return _check("enabled_mods_resolve", "FAIL", f"{enabled_path} not found.")
    data = _load_lenient_json_file(enabled_path)
    enabled = data.get("enabledMods") if isinstance(data, dict) else None
    if not isinstance(enabled, list):
        return _check(
            "enabled_mods_resolve",
            "FAIL",
            f"{enabled_path} did not parse to an object with an 'enabledMods' list.",
        )
    enabled_ids = [str(item) for item in enabled]
    enabled_set = set(enabled_ids)
    by_id = _mods_by_id(mods_dir)

    unresolved: list[str] = []
    dep_warnings: list[str] = []
    version_warnings: list[str] = []
    for mod_id in enabled_ids:
        folder = by_id.get(mod_id)
        if folder is None:
            unresolved.append(mod_id)
            continue
        info = _load_lenient_json_file(folder / "mod_info.json")
        if not isinstance(info, dict):
            continue
        dependencies = info.get("dependencies")
        if isinstance(dependencies, list):
            for dependency in dependencies:
                dep_id = dependency.get("id") if isinstance(dependency, dict) else None
                if isinstance(dep_id, str) and dep_id and dep_id not in enabled_set:
                    dep_warnings.append(f"{mod_id} depends on {dep_id} (not enabled)")
        game_version = info.get("gameVersion") or info.get("game_version")
        if isinstance(game_version, str) and game_version.strip():
            if _base_game_version(game_version) != TARGET_BASE_GAME_VERSION:
                version_warnings.append(f"{mod_id} declares gameVersion {game_version}")

    if unresolved:
        status = "FAIL"
    elif dep_warnings or version_warnings:
        status = "WARN"
    else:
        status = "PASS"

    parts: list[str] = []
    if unresolved:
        parts.append("Unresolved enabled id(s) with no matching mods/ folder: " + ", ".join(sorted(unresolved)))
    if dep_warnings:
        parts.append("Dependencies not enabled: " + "; ".join(dep_warnings))
    if version_warnings:
        parts.append(f"gameVersion base differs from {TARGET_BASE_GAME_VERSION}: " + "; ".join(version_warnings))
    if not parts:
        parts.append(f"All {len(enabled_ids)} enabled mod id(s) resolve; dependencies enabled; gameVersion matches {TARGET_BASE_GAME_VERSION}.")
    return _check("enabled_mods_resolve", status, " | ".join(parts))


def _check_working_copy_drift(runtime_dir: Path, working_copies: dict[str, Path]) -> dict[str, object]:
    if not working_copies:
        return _check("working_copy_drift", "SKIPPED", "No working_copies provided.")
    mods_dir = runtime_dir / "mods"
    by_id = _mods_by_id(mods_dir)
    status = "PASS"
    lines: list[str] = []
    for mod_id, working_dir in sorted(working_copies.items()):
        working_dir = Path(working_dir)
        rig_folder = by_id.get(mod_id)
        if rig_folder is None:
            status = "FAIL"
            lines.append(f"{mod_id}: no rig mods/ folder declares this id")
            continue
        try:
            same_folder = rig_folder.resolve() == working_dir.expanduser().resolve()
        except OSError:
            same_folder = False
        if same_folder:
            lines.append(f"{mod_id}: PASS (rig folder is a link to the working copy, same folder)")
            continue
        result = compare_copies(working_dir, rig_folder)
        if result["status"] == "PASS":
            lines.append(f"{mod_id}: PASS (no drift)")
            continue
        if status == "PASS":
            status = "WARN"
        lines.append(
            f"{mod_id}: WARN drift_count={result['drift_count']}. "
            f"Fix: prepare-test {working_dir} {rig_folder} --sync"
        )
    return _check("working_copy_drift", status, "; ".join(lines))


def _list_saves(saves_dir: Path) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for path in sorted(saves_dir.rglob("*")):
        if not path.is_file():
            continue
        stat = path.stat()
        entries.append({"path": path.relative_to(saves_dir).as_posix(), "size": stat.st_size, "mtime": stat.st_mtime})
    return entries


def _check_real_install_saves_untouched(
    repo_root: Path,
    real_install: Path | None,
    saves_baseline: Path | None,
    write_saves_baseline: bool,
) -> dict[str, object]:
    if real_install is None:
        return _check("real_install_saves_untouched", "SKIPPED", "No real_install provided.")
    real_install = Path(real_install)
    saves_dir = real_install / "saves"
    baseline_path = Path(saves_baseline) if saves_baseline is not None else repo_root / DEFAULT_BASELINE_RELATIVE
    if not saves_dir.is_dir():
        return _check("real_install_saves_untouched", "WARN", f"{saves_dir} does not exist (nothing to compare).")

    current = _list_saves(saves_dir)

    if write_saves_baseline:
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(
            json.dumps({"saves_dir": str(saves_dir), "entries": current}, indent=2),
            encoding="utf-8",
        )
        return _check(
            "real_install_saves_untouched",
            "PASS",
            f"Baseline written to {baseline_path} ({len(current)} file(s)).",
        )

    if not baseline_path.is_file():
        return _check(
            "real_install_saves_untouched",
            "SKIPPED",
            f"No baseline found at {baseline_path}. Run rig_doctor once with write_saves_baseline=True "
            "(the only write this module ever makes) to record the current real-install saves, then rerun to compare.",
        )

    try:
        baseline_data = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _check("real_install_saves_untouched", "FAIL", f"Baseline at {baseline_path} could not be read: {exc}")

    baseline_entries = {entry["path"]: entry for entry in baseline_data.get("entries", []) if isinstance(entry, dict) and "path" in entry}
    current_entries = {entry["path"]: entry for entry in current}

    added = sorted(set(current_entries) - set(baseline_entries))
    removed = sorted(set(baseline_entries) - set(current_entries))
    changed = sorted(
        path
        for path in (set(current_entries) & set(baseline_entries))
        if current_entries[path]["size"] != baseline_entries[path]["size"]
        or current_entries[path]["mtime"] != baseline_entries[path]["mtime"]
    )

    if added or changed:
        return _check(
            "real_install_saves_untouched",
            "FAIL",
            f"Real install saves changed since the baseline at {baseline_path} "
            f"(isolation may have broken): added={added}, changed={changed}, removed={removed}.",
        )

    detail = f"Real install saves match the baseline at {baseline_path} ({len(current_entries)} file(s)); nothing added or changed."
    if removed:
        detail += f" Note: {len(removed)} file(s) removed since baseline (not treated as a failure): {removed}."
    return _check("real_install_saves_untouched", "PASS", detail)


def rig_doctor(
    runtime_dir: Path,
    *,
    working_copies: dict[str, Path] | None = None,
    real_install: Path | None = None,
    saves_baseline: Path | None = None,
    write_saves_baseline: bool = False,
) -> dict[str, object]:
    """Read-only pre-flight checks for a Starsector test rig; the only write is the opt-in saves baseline.

    Never touches the real install except (optionally, read-only) to list <real_install>/saves, and
    never launches Starsector.
    """
    runtime_dir = Path(runtime_dir).expanduser().resolve()
    repo_root = _repo_root()

    checks = [
        _check_isolation(runtime_dir),
        _check_game_not_running(runtime_dir),
        _check_probe_installed(runtime_dir, repo_root),
        _check_enabled_mods_resolve(runtime_dir),
        _check_working_copy_drift(runtime_dir, working_copies or {}),
        _check_real_install_saves_untouched(repo_root, real_install, saves_baseline, write_saves_baseline),
    ]

    if any(item["status"] == "FAIL" for item in checks):
        overall = "FAIL"
    elif any(item["status"] == "WARN" for item in checks):
        overall = "WARN"
    else:
        overall = "PASS"

    return {
        "schema_version": 1,
        "mode": "RIG_DOCTOR",
        "runtime_dir": str(runtime_dir),
        "status": overall,
        "checks": checks,
    }
