"""Synthetic staged runs for the R1 tests: a rig with a junction, staged mods, a pre-launch manifest, a log and a release. No game."""
from __future__ import annotations

import json
from pathlib import Path

from bridgeforge.probe.probe_group import sync_working_copy
from bridgeforge.run_manifest import prepare_run, record_candidates, release_run
from tests.support import link_dir

MENU = "100 [Thread-8] INFO  sound.H  - Playing music with id [miscallenous_main_menu.ogg]"
LOAD = "150 [Thread-2] INFO  com.fs.starfarer.campaign.save.CampaignGameManager  - Loading C:\\rig\\saves\\save_Test_1..."
SAVED = "160 [Thread-2] INFO  com.fs.starfarer.campaign.save.CampaignGameManager  - Finished saving"
PROBE = "9 [Thread-2] INFO  com.bridgeforge.probe.ProbeLog  - "
CONTENT_IDS = PROBE + "BF-PROBE|0.2.9|content-ids|OK|all-content|checked=2 failed=0"
COMBAT = PROBE + "BF-PROBE|0.2.9|combat-round|INFO|round-1|frames=900"
BASIC_LOG = [MENU, LOAD]


def make_rig(root: Path, providers: dict[str, list[str]] | None = None) -> Path:
    """A rig whose starsector-core is a junction, with provider mods {id: [their own dependencies]} installed."""
    rig = root / "rig"
    (rig / "mods").mkdir(parents=True)
    core = root / "core_real"
    core.mkdir(exist_ok=True)
    link_dir(core, rig / "starsector-core")
    for mod_id, deps in (providers or {}).items():
        folder = rig / "mods" / mod_id
        folder.mkdir()
        (folder / "mod_info.json").write_text(json.dumps({"id": mod_id, "version": "1.0", "dependencies": [{"id": d} for d in deps]}), encoding="utf-8")
        (folder / "payload.txt").write_text(f"{mod_id} payload", encoding="utf-8")
    return rig


def stage(rig: Path, workspaces: dict[str, Path], extra_enabled: list[str] | None = None) -> None:
    """Copy each {mod id: workspace} working copy into the rig, enable it after `extra_enabled`, and record the candidates."""
    for mod_id, workspace in workspaces.items():
        sync_working_copy(workspace / "working", rig / "mods" / workspace.name)
    enabled = [*(extra_enabled or []), *workspaces]
    (rig / "mods" / "enabled_mods.json").write_text(json.dumps({"enabledMods": enabled}), encoding="utf-8")
    record_candidates(rig, {mod_id: ws / "working" for mod_id, ws in workspaces.items()})


def bound_run(root: Path, workspaces: dict[str, Path], test_id: str, log_lines: list[str] | None = None, *,
              expected: tuple[str, ...] = ("main_menu", "campaign_load"), kind: str = "campaign",
              providers: dict[str, list[str]] | None = None, rig: Path | None = None, release: bool = True) -> tuple[Path, Path]:
    """Stage, prepare the manifest, write the log (after it, so it is newer), release. Returns (rig, log path)."""
    rig = rig or make_rig(root, providers)
    stage(rig, workspaces, list(providers or {}))
    prepare_run(rig, test_id, kind, targets=list(workspaces), expected=list(expected))
    log = rig / "logs" / f"{test_id}.stdout.log"
    log.write_text("\n".join(log_lines if log_lines is not None else BASIC_LOG) + "\n", encoding="utf-8")
    if release:
        release_run(rig, test_id)
    return rig, log
