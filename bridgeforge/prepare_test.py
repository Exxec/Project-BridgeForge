from __future__ import annotations

from pathlib import Path

from .build_tag import DEFAULT_LABEL, BuildTagError, apply_build_tag
from .copy_drift import compare_copies


class PrepareTestError(ValueError):
    """Raised when prepare-test cannot resolve mod roots, sync files, or reach a synced state."""


def _mod_root_for_sync(path: Path) -> Path:
    """Resolve the same working/deployed mod-root convention `compare_copies` uses, for copy operations."""
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        raise PrepareTestError(f"{root} is not an existing directory.")
    if (root / "mod_info.json").is_file():
        return root
    candidates = sorted(child for child in root.iterdir() if child.is_dir() and (child / "mod_info.json").is_file())
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise PrepareTestError(f"No mod_info.json found at {root} or one directory below it.")
    raise PrepareTestError(f"Multiple mod_info.json candidates below {root}; ambiguous mod root.")


def prepare_test(
    working_dir: Path,
    rig_mod_dir: Path,
    sync: bool = False,
    bump: bool = False,
    label: str = DEFAULT_LABEL,
    boot: Path | None = None,
    mods: list[str] | None = None,
    timeout: int = 240,
    log_name: str | None = None,
    keep_mods: bool = False,
    record_manifest: bool = False,
) -> dict[str, object]:
    """Bump/sync a rig test copy from its working copy, then optionally run a boot test.

    Never copies rig -> working, never deletes files at the rig, and never launches Starsector
    itself -- that is delegated entirely to `boot_test.run_boot_test`, imported lazily so this
    module has no hard dependency on it.
    """
    working_resolved = Path(working_dir).expanduser().resolve()
    rig_resolved = Path(rig_mod_dir).expanduser().resolve()
    if not working_resolved.is_dir():
        raise PrepareTestError(f"{working_resolved} is not an existing directory.")
    if not rig_resolved.is_dir():
        raise PrepareTestError(f"{rig_resolved} is not an existing directory.")

    result: dict[str, object] = {
        "schema_version": 1,
        "mode": "PREPARE_TEST",
        "working_dir": str(working_resolved),
        "rig_mod_dir": str(rig_resolved),
    }

    if working_resolved == rig_resolved:
        result["status"] = "SAME_FOLDER"
        result["message"] = "same folder (junction), nothing to sync"
        return result

    if bump:
        try:
            result["bump"] = apply_build_tag(working_resolved, label=label, record_manifest=record_manifest)
        except BuildTagError as exc:
            raise PrepareTestError(f"--bump failed: {exc}") from exc

    drift = compare_copies(working_resolved, rig_resolved)
    result["drift_before_sync"] = drift

    if drift["status"] == "PASS":
        result["status"] = "PASS"
        result["synced"] = False
    elif not sync:
        result["status"] = "DRIFT"
        result["synced"] = False
    else:
        working_root = _mod_root_for_sync(working_resolved)
        rig_root = _mod_root_for_sync(rig_resolved)
        copied: list[str] = []
        for relative in [*drift["missing_in_deployed"], *[item["path"] for item in drift["different"]]]:
            source = working_root / relative
            destination = rig_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(source.read_bytes())
            copied.append(relative)
        result["synced"] = True
        result["synced_files"] = copied
        result["extra_in_deployed"] = drift["extra_in_deployed"]
        post_drift = compare_copies(working_resolved, rig_resolved)
        result["drift_after_sync"] = post_drift
        if post_drift["status"] != "PASS":
            raise PrepareTestError(
                f"After --sync, {post_drift['drift_count']} drift item(s) remain (never deleted extras, "
                f"never synced rig -> working): {post_drift}"
            )
        result["status"] = "PASS"

    if boot is not None:
        if result["status"] != "PASS":
            result["boot_test"] = {"status": "SKIPPED", "reason": "working and rig copies are not in sync"}
        else:
            try:
                from . import boot_test as boot_test_module
            except ImportError:
                result["boot_test"] = {"status": "UNAVAILABLE", "reason": "boot-test module unavailable"}
            else:
                result["boot_test"] = boot_test_module.run_boot_test(
                    Path(boot), mods or [], timeout=timeout, log_name=log_name, keep_mods=keep_mods
                )

    return result
