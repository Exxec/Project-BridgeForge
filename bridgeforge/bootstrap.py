from __future__ import annotations

import json
from pathlib import Path

from .baseline import finding_baseline_key
from .build_tag import record_current_manifest
from .scanner import scan_mod


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def default_baselines_dir() -> Path:
    """Default location for scan baselines -- always outside any mod folder, mirroring
    `build_tag.default_manifests_dir`'s `bridgeforge-state/build-manifests/` convention."""
    return _repo_root() / "bridgeforge-state" / "baselines"


def _write_baseline_file(path: Path, keys: list[str]) -> None:
    # Same format `scan --write-baseline` writes in cli.py: {"findings": [...]}, sorted, indented.
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"findings": keys}, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def bootstrap_mods(
    mod_dirs: list[Path],
    *,
    vanilla_core: Path,
    baselines_dir: Path | None = None,
    manifests_dir: Path | None = None,
    overwrite: bool = False,
) -> dict[str, object]:
    """Give each of `mod_dirs` a starting baseline and an `r0` manifest, without touching the mod itself.

    For every mod dir: run `scan_mod` against `vanilla_core` and write its finding keys to
    `baselines_dir/<mod-id>.json` in exactly the format `scan --write-baseline` uses (see cli.py) --
    unless a baseline already exists there and `overwrite` is False, in which case it is left alone
    and reported as kept. Then call `build_tag.record_current_manifest` to record an `r0` (or
    whatever build the mod is already tagged at) hash manifest, so `test_plan.plan_tests` has
    something to diff against immediately.

    Nothing is ever written inside a mod's own directory: baselines and manifests both live under
    `baselines_dir`/`manifests_dir`, which default to locations under `<repo>/bridgeforge-state/`
    but should be pointed at a temp dir for validation runs that must not touch the real repo state.
    """
    vanilla_root = Path(vanilla_core).expanduser().resolve()
    baselines_root = Path(baselines_dir).expanduser().resolve() if baselines_dir is not None else default_baselines_dir()

    summary: dict[str, object] = {}
    for mod_dir in mod_dirs:
        scan_result = scan_mod(Path(mod_dir), vanilla_core=vanilla_root)
        mod_id = None
        metadata = scan_result.metadata if isinstance(scan_result.metadata, dict) else {}
        raw_id = metadata.get("id")
        if isinstance(raw_id, str) and raw_id:
            mod_id = raw_id
        label = mod_id or Path(mod_dir).name

        baseline_path = baselines_root / f"{label}.json"
        keys = sorted({finding_baseline_key(finding) for finding in scan_result.findings})
        manual_count = sum(1 for finding in scan_result.findings if finding.classification == "MANUAL")

        baseline_written = True
        if baseline_path.is_file() and not overwrite:
            baseline_written = False
        else:
            _write_baseline_file(baseline_path, keys)

        manifest_info = record_current_manifest(mod_dir, manifests_dir=manifests_dir)

        summary[label] = {
            "mod_dir": str(Path(mod_dir).expanduser().resolve()),
            "mod_id": mod_id,
            "baseline_path": str(baseline_path),
            "baseline_written": baseline_written,
            "baseline_kept_existing": not baseline_written,
            "finding_count": len(scan_result.findings),
            "manual_finding_count": manual_count,
            "manifest_path": str(manifest_info["path"]),
            "manifest_build": manifest_info["build"],
            "manifest_file_count": manifest_info["file_count"],
        }
    return summary
