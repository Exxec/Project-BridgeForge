from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from .boot_test import _is_link
from .copy_drift import _collect, _find_mod_root, compare_copies
from .reference_rigs import ReferenceRigError, verify_reference_rig_manifest
from .scanner import _load_lenient_json_file

_RC_PATTERN = re.compile(r"^0\.98a-RC(\d+)$")


class CompatSetError(ValueError):
    """Raised when a named compat set can't be loaded, resolved, or installed."""


def bundled_compat_sets_path() -> Path:
    return Path(__file__).with_name("compat_sets") / "standard.json"


def load_compat_sets(path: Path | None = None) -> dict[str, object]:
    """Load the named compat-set definitions (own file, not Starsector-lenient JSON)."""
    data_path = Path(path) if path is not None else bundled_compat_sets_path()
    try:
        raw = json.loads(data_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CompatSetError(f"Could not read compat-set definitions at {data_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CompatSetError(f"Invalid JSON in compat-set definitions at {data_path}: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != 1 or not isinstance(raw.get("sets"), dict):
        raise CompatSetError(f"{data_path} is not a recognized compat-set definitions file (schema_version 1, 'sets' object).")
    return raw


def resolve_set(data: dict[str, object], name: str, _seen: frozenset[str] = frozenset()) -> dict[str, dict[str, object]]:
    """Resolve a named set to {mod_id: info}, merging any sets it 'extends' (its own entries win)."""
    sets = data.get("sets")
    if not isinstance(sets, dict) or name not in sets:
        raise CompatSetError(f"Unknown compat set '{name}'. Known sets: {sorted(sets) if isinstance(sets, dict) else []}")
    if name in _seen:
        raise CompatSetError(f"Compat set '{name}' has a circular 'extends' chain.")
    entry = sets[name]
    if not isinstance(entry, dict):
        raise CompatSetError(f"Compat set '{name}' is malformed.")
    merged: dict[str, dict[str, object]] = {}
    for parent in entry.get("extends", []) or []:
        merged.update(resolve_set(data, parent, _seen | {name}))
    mods = entry.get("mods")
    if not isinstance(mods, dict):
        raise CompatSetError(f"Compat set '{name}' has no 'mods' object.")
    merged.update(mods)
    return merged


def set_mod_ids(data: dict[str, object], name: str) -> list[str]:
    return sorted(resolve_set(data, name))


def lib_mod_ids(data: dict[str, object], name: str) -> list[str]:
    """Ids within the resolved set whose role is 'lib'."""
    return sorted(mod_id for mod_id, info in resolve_set(data, name).items() if isinstance(info, dict) and info.get("role") == "lib")


def _refuse_non_rig(runtime_dir: Path, reference_manifest: Path | None = None) -> None:
    core_path = runtime_dir / "starsector-core"
    if _is_link(core_path):
        return
    if reference_manifest is not None:
        try:
            verification = verify_reference_rig_manifest(reference_manifest)
        except ReferenceRigError as exc:
            raise CompatSetError(str(exc)) from exc
        if Path(str(verification["runtime_dir"])).resolve() != runtime_dir:
            raise CompatSetError("reference-rig manifest does not name this runtime directory")
        if verification["status"] != "FAIL":
            return
        raise CompatSetError("reference-rig manifest verification failed; run rig-doctor for details")
    raise CompatSetError(
        f"{core_path} is not a junction/symlink. compat-set install refuses to write into a "
        "non-isolated runtime unless a valid --reference-manifest identifies it."
    )


def _index_source_mods(source_mods_dir: Path) -> dict[str, Path]:
    """Map declared mod id -> its folder, for every direct child of source_mods_dir with a readable mod_info.json.

    Read-only: never writes into source_mods_dir. Uses the same lenient JSON reader as the scanner
    so '#' comments and trailing commas in a mod's mod_info.json don't hide it.
    """
    by_id: dict[str, Path] = {}
    if not source_mods_dir.is_dir():
        return by_id
    for child in sorted(p for p in source_mods_dir.iterdir() if p.is_dir()):
        info_path = child / "mod_info.json"
        if not info_path.is_file():
            continue
        info = _load_lenient_json_file(info_path)
        if not isinstance(info, dict):
            continue
        mod_id = info.get("id")
        if isinstance(mod_id, str) and mod_id and mod_id not in by_id:
            by_id[mod_id] = child
    return by_id


def _rig_game_version(runtime_dir: Path) -> str | None:
    """Best-effort RC version already installed in the rig's own mods/, from mod_info.json gameVersion fields.

    There is no single canonical version file in an isolated rig (starsector-core is a junction to a
    real install with no exposed version marker). This looks at what's already enabled/present and
    returns the most common '0.98a-RCn' string found, or None if none is found (in which case an
    exact-RC-match warning simply can't be produced).
    """
    mods_dir = runtime_dir / "mods"
    if not mods_dir.is_dir():
        return None
    counts: dict[str, int] = {}
    for child in mods_dir.iterdir():
        if not child.is_dir():
            continue
        info = _load_lenient_json_file(child / "mod_info.json")
        if not isinstance(info, dict):
            continue
        version = info.get("gameVersion")
        if isinstance(version, str) and _RC_PATTERN.match(version):
            counts[version] = counts.get(version, 0) + 1
    if not counts:
        return None
    return max(counts.items(), key=lambda item: (item[1], item[0]))[0]


def _copy_missing_mod(source_root: Path, dest: Path) -> list[str]:
    """Full first-time copy of a mod's tracked files (copy_drift.INCLUDED_DIRS + mod_info.json) into dest."""
    copied: list[str] = []
    for relative, source_path in _collect(source_root).items():
        dest_path = dest / relative
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, dest_path)
        copied.append(relative)
    return copied


def _copy_drifted_files(source_root: Path, dest: Path, drift: dict[str, object]) -> list[str]:
    """Copy only the files copy_drift reports missing/different from source_root -> dest. Never touches extras."""
    copied: list[str] = []
    relatives = list(drift.get("missing_in_deployed", [])) + [entry["path"] for entry in drift.get("different", [])]
    for relative in relatives:
        source_path = source_root / relative
        if not source_path.is_file():
            continue
        dest_path = dest / relative
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, dest_path)
        copied.append(relative)
    return copied


def install_compat_set(
    set_name: str,
    runtime_dir: Path,
    source_mods_dir: Path,
    data_path: Path | None = None,
    dry_run: bool = False,
    reference_manifest: Path | None = None,
) -> dict[str, object]:
    """Copy every mod in a named compat set from source_mods_dir into <runtime_dir>/mods/.

    Refuses unless runtime_dir/starsector-core is a junction/symlink (same rig-only guard as
    run_boot_test/probe-config). Only ever copies source -> rig, never the reverse. Skips a mod
    already byte-identical in the rig (via copy_drift.compare_copies); for a drifted mod, copies only
    the missing/different files, never touching rig-only extras. --dry-run performs no writes.
    """
    runtime_dir = Path(runtime_dir).expanduser().resolve()
    source_mods_dir = Path(source_mods_dir).expanduser().resolve()
    _refuse_non_rig(runtime_dir, reference_manifest)

    data = load_compat_sets(data_path)
    resolved = resolve_set(data, set_name)
    source_index = _index_source_mods(source_mods_dir)
    rig_version = _rig_game_version(runtime_dir)

    missing: list[str] = []
    warnings: list[str] = []
    plan: list[dict[str, object]] = []
    skipped_identical: list[str] = []

    for mod_id in sorted(resolved):
        info = resolved[mod_id]
        if isinstance(info, dict) and info.get("evidence_status") == "EXACT_VERSION_UNRESOLVED":
            warnings.append(
                f"{mod_id}: the era set identifies this dependency but not an authoritative exact library build; "
                "verify the supplied archive/version before treating the reference run as valid."
            )
        source_root = source_index.get(mod_id)
        if source_root is None:
            missing.append(mod_id)
            continue

        mod_info = _load_lenient_json_file(source_root / "mod_info.json")
        game_version = mod_info.get("gameVersion") if isinstance(mod_info, dict) else None
        # Only a different BASE version matters: the launcher accepts older RCs of the same version
        # (LazyLib/LunaLib 0.98a-RC5 and MagicLib 0.98a-RC7 ran in the RC8 rig).
        base = lambda value: re.sub(r"-RC\d+$", "", value.strip(), flags=re.I).lower()
        if rig_version and isinstance(game_version, str) and base(game_version) != base(rig_version):
            warnings.append(
                f"{mod_id}: source gameVersion '{game_version}' targets a different base version than the "
                f"rig's '{rig_version}'; the launcher will likely uncheck it."
            )

        dest = runtime_dir / "mods" / source_root.name
        if not dest.is_dir():
            plan.append({"id": mod_id, "source": str(source_root), "destination": str(dest), "reason": "missing_in_rig", "files": None})
            continue

        drift = compare_copies(source_root, dest)
        if drift["status"] == "PASS":
            skipped_identical.append(mod_id)
            continue
        files = drift["missing_in_deployed"] + [entry["path"] for entry in drift["different"]]
        plan.append({"id": mod_id, "source": str(source_root), "destination": str(dest), "reason": "drift", "files": files})

    result: dict[str, object] = {
        "schema_version": 1,
        "mode": "COMPAT_SET_INSTALL",
        "set": set_name,
        "runtime_dir": str(runtime_dir),
        "source_mods_dir": str(source_mods_dir),
        "reference_manifest": str(Path(reference_manifest).resolve()) if reference_manifest is not None else None,
        "resolved_mod_ids": sorted(resolved),
        "rig_game_version": rig_version,
        "missing": missing,
        "warnings": warnings,
        "skipped_identical": skipped_identical,
        "plan": plan,
        "dry_run": dry_run,
        "installed": [],
    }

    if dry_run:
        return result

    installed: list[dict[str, object]] = []
    for item in plan:
        source_root = Path(item["source"])
        dest = Path(item["destination"])
        if item["reason"] == "missing_in_rig":
            dest.mkdir(parents=True, exist_ok=True)
            copied = _copy_missing_mod(_find_mod_root(source_root), dest)
        else:
            copied = _copy_drifted_files(_find_mod_root(source_root), dest, {"missing_in_deployed": item["files"], "different": []})
        installed.append({"id": item["id"], "destination": str(dest), "files_copied": copied})
    result["installed"] = installed
    return result
