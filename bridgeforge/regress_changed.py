"""`probe-group regress --changed-since COMMIT`: rerun only the archives that need it (ROADMAP item 73 G2).

A full regression pass plays every LIVE_VALIDATED workspace (about five minutes a group). Most of that is wasted when nothing
that could change a verdict has changed. A workspace is rerun when

- the probe or the harness changed since COMMIT (`git diff COMMIT`: `probe-mod/`, the live driver, launcher click, rig preferences,
  boot test, probe-group install/report code): then every verdict is suspect, so every validated workspace reruns; or
- its own shipped files changed since its last PASS run record (`live_trust.live_status` is not CURRENT; `In operation/` is
  gitignored, so the run record's hash is the only history of a workspace).

Owner decision 4 (2026-10-14): an overnight run on the dedicated rig is allowed, results are reported and never acted on, and a
run that finds a regression stops further runs until a person looks. The stop is a hold file in `<queue>/_regress/`; a
`--changed-since` run refuses to start while it exists (`--clear-hold` removes it). Nothing here schedules anything.
"""
from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path
from typing import Callable

from .safeio import atomic_write_json

# Paths (relative to the repository root, forward slashes) whose change can alter any archive's live verdict.
PROBE_HARNESS_PREFIXES = (
    "probe-mod/",
    "bridgeforge/live_run.py",
    "bridgeforge/screen_read.py",
    "bridgeforge/launcher_click.py",
    "bridgeforge/rig_prefs.py",
    "bridgeforge/boot_test.py",
    "bridgeforge/probe_config.py",
    "bridgeforge/probe_group.py",
    "bridgeforge/probe_mod_build.py",
    "bridgeforge/regress.py",
    "bridgeforge/log_triage.py",
    "tools/bf-test.ps1",
)
HOLD_FILE = "REGRESSION_HOLD.json"


class RegressChangedError(ValueError):
    """The commit is unknown, the rig is not isolated, or a regression hold is in place."""


def changed_paths(repo_root: Path, commit: str, git: Callable[[list[str], Path], str] | None = None) -> list[str]:
    """Paths changed between COMMIT and the working tree, forward slashes. Raises RegressChangedError for an unknown commit."""
    if not commit or commit.startswith("-"):
        raise RegressChangedError(f"not a commit: {commit!r}")
    run = git or _git
    try:
        run(["rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}"], repo_root)
        out = run(["diff", "--name-only", commit, "--"], repo_root)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RegressChangedError(f"cannot diff against {commit!r}: {exc}") from exc
    return sorted({line.strip().replace("\\", "/") for line in out.splitlines() if line.strip()})


def _git(args: list[str], cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True, timeout=120).stdout


def probe_or_harness_changes(paths: list[str]) -> list[str]:
    return [p for p in paths if any(p == prefix or (prefix.endswith("/") and p.startswith(prefix)) for prefix in PROBE_HARNESS_PREFIXES)]


def last_recorded_verdict(workspace: Path) -> str | None:
    """The verdict of the workspace's newest run in reports/live_runs.jsonl, or None."""
    log = Path(workspace) / "reports" / "live_runs.jsonl"
    last = None
    try:
        lines = log.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        try:
            last = json.loads(line).get("verdict") or last
        except ValueError:
            continue
    return last


def last_manifest_summary(queue: Path, workspace: Path) -> dict | None:
    """The manifest summary of the workspace's newest bound run record in <queue>/_live, or None (legacy runs have none)."""
    newest = None
    for path in sorted((Path(queue) / "_live").glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(record, dict) or not record.get("manifest"):
            continue
        if any(m.get("workspace") == workspace.name and m.get("provenance") == "BOUND" for m in record.get("members") or []):
            if newest is None or str(record.get("recorded_at", "")) >= str(newest.get("recorded_at", "")):
                newest = record
    return newest["manifest"] if newest else None


def select_workspaces(queue: Path, changed: list[str], validated: list[Path] | None = None, rig: Path | None = None) -> dict[str, str]:
    """{workspace name: why it reruns} for the validated workspaces; the others are left out. Besides git and the shipped hash,
    a workspace reruns when the providers, probe config or launcher files of its last bound run differ from the rig now (R1)."""
    from .live_trust import live_status
    from .regress import validated_workspaces
    from .run_manifest import environment_drift

    harness = probe_or_harness_changes(changed)
    chosen: dict[str, str] = {}
    for workspace in validated if validated is not None else validated_workspaces(queue):
        if harness:
            chosen[workspace.name] = f"probe/harness changed ({harness[0]}" + (f" and {len(harness) - 1} more" if len(harness) > 1 else "") + ")"
            continue
        status = live_status(workspace)["status"]
        if status != "CURRENT":
            chosen[workspace.name] = f"shipped files changed since the last PASS run ({status})" if status == "STALE" else f"no recorded run hash ({status})"
            continue
        summary = last_manifest_summary(queue, workspace) if rig is not None else None
        if summary is None:
            continue  # a legacy run has no recorded environment to compare; git and the shipped hash are all there is
        drift = environment_drift(rig, summary)
        if drift:
            chosen[workspace.name] = "environment changed since the last bound run (" + "; ".join(drift[:3]) + ")"
    return chosen


def hold_path(queue: Path) -> Path:
    return Path(queue) / "_regress" / HOLD_FILE


def run_changed(queue: Path, rig: Path, out: Path, commit: str, *, repo_root: Path, bat: str | None = None, size: int = 8,
                limit: int | None = None, quiet: bool = False, test_prefix: str | None = None, clear_hold: bool = False,
                runner: Callable | None = None, git: Callable | None = None) -> dict:
    """Rerun the workspaces `select_workspaces` picks and write per-archive verdicts (all of them) to `out`. Never records."""
    from .boot_test import _is_link

    queue, rig = Path(queue).expanduser().resolve(), Path(rig).expanduser().resolve()
    if not _is_link(rig / "starsector-core"):
        raise RegressChangedError(f"{rig / 'starsector-core'} is not a junction/symlink; unattended runs are for the dedicated rig only")
    hold = hold_path(queue)
    if hold.is_file():
        if not clear_hold:
            raise RegressChangedError(f"a regression hold is in place ({hold}); look at it, then rerun with --clear-hold")
        hold.unlink()
    changed = changed_paths(repo_root, commit, git)
    chosen = select_workspaces(queue, changed, rig=rig)
    previous = {name: last_recorded_verdict(queue / name) for name in chosen}
    if runner is None:
        from .regress import run_regression as runner
    if chosen:
        result = runner(queue, rig, out, bat=bat, size=size, limit=limit, only=sorted(chosen), quiet=quiet, test_prefix=test_prefix)
    else:
        result = {"mode": "PROBE_GROUP_REGRESS", "date": f"{date.today():%Y-%m-%d}", "groups": [], "unplaced": [], "attention": []}
    archives = _archive_verdicts(queue, rig, result, chosen, previous)
    result = {**result, "mode": "PROBE_GROUP_REGRESS_CHANGED", "since": commit, "changed_paths": len(changed),
              "selected": chosen, "archives": archives,
              "changed_verdicts": {name: row for name, row in archives.items() if row["changed"]}}
    if any(row["regression"] for row in archives.values()):
        atomic_write_json(hold, {"since": commit, "date": result.get("date"), "regressions": sorted(n for n, r in archives.items() if r["regression"]),
                                 "summary": str(out)})
        result["hold"] = str(hold)
    atomic_write_json(Path(out), result)
    return result


def _archive_verdicts(queue: Path, rig: Path, result: dict, chosen: dict[str, str], previous: dict[str, str | None]) -> dict[str, dict]:
    """Per selected workspace: its verdict now, the one before, and whether it changed or regressed (was PASS, is not)."""
    from .probe_group import _workspaces_by_mod_id

    owners = {mod: ws.name for mod, ws in _workspaces_by_mod_id(queue, rig / "mods").items() if ws is not None}
    now: dict[str, str] = {}
    for row in result.get("groups", []):
        members = row.get("members")
        if isinstance(members, dict):
            for mod, verdict in members.items():
                if mod in owners:
                    now[owners[mod]] = str(verdict)
        else:  # the group never reached a verdict: every member is NOT_RUN
            for name in members or []:
                now.setdefault(name, "NOT_RUN")
    archives = {}
    for name, why in sorted(chosen.items()):
        verdict, before = now.get(name, "NOT_RUN"), previous.get(name)
        archives[name] = {"why": why, "previous": before, "verdict": verdict, "changed": verdict != before,
                          "regression": before == "PASS" and verdict != "PASS"}
    return archives
