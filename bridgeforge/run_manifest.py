"""Pre-launch run manifests and the one evidence evaluator for live acceptance (ROADMAP item 75 R1).

A log plus today's hash of the working files does not prove the run used those bytes. Before a run starts, `prepare_run` records
a versioned manifest in `<rig>/logs/<run id>.manifest.json`: the rig identity, the exact enabled mods with versions and hashes of the
files STAGED in the rig (dependencies included), the candidate hashes they must equal, runtime configuration hashes (enabled list,
probe config, launcher files) kept apart from shipped-file hashes, the log path, and the milestones the scenario must show. The rig
is owned by the run until `release_run`, which re-hashes the staged files and writes `<run id>.completed.json`; BridgeForge's own
staging commands (`rig-up`, `probe-group install`) refuse while a run owns the rig.

`evaluate_run` is the evaluator both `probe-group record --accept` and `accept` use. It compares the manifest with the rig and the
working copies now (a pre/post comparison: it detects drift, it does not claim tamper-proof execution) and with the log, and
checks the scenario's expected milestones per target. It never invents a manifest: a run without one stays provenance UNKNOWN.

File-set algorithm: `copy_drift._collect` (every root file and top-level folder except tool/build folders) with
`live_trust.shipped_hash`; the algorithm name is pinned in the manifest and a different one is refused.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .boot_test import _is_link
from .safeio import atomic_write_json

MANIFEST_VERSION = 1
FILESET_ALGORITHM = "copy_drift.collect+sha256/1"
MANIFEST_SUFFIX = ".manifest.json"
COMPLETED_SUFFIX = ".completed.json"
OWNER_FILE = "run_owner.json"
RIG_STATE_FILE = "rig_up_state.json"
CONFIG_RELATIVE = Path("saves") / "common" / "bf_probe_config.data"
MILESTONES = ("main_menu", "campaign_load", "save", "content_ids", "combat")
# What a kind of run can show at all: a smoke boot passes its boot scenario but never a campaign, combat or save requirement.
KIND_CAPABILITY = {
    "boot": {"main_menu"},
    "campaign": {"main_menu", "campaign_load", "save", "content_ids"},
    "live": set(MILESTONES),
}
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
_CONTENT_IDS = re.compile(r"BF-PROBE\|[^|]*\|content-ids\|[^|]*\|all-content\|")
_COMBAT = re.compile(r"BF-PROBE\|[^|]*\|combat-round\|")
_JAVA_EXE = re.compile(r'"([^"\r\n]*java\w*\.exe)"|(?<!\S)([^\s"\']*java\w*\.exe)(?=\s|$)', re.IGNORECASE)
_JAVA_VERSION = re.compile(r'\bJAVA_VERSION\s*=\s*"([^"]+)"')
_JAVA_VERSION_OUTPUT = re.compile(r'\bversion\s+"([^"]+)"', re.IGNORECASE)
EPOCH_SLACK_SECONDS = 2.0


class ManifestError(ValueError):
    """A manifest cannot be prepared, read or trusted."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_hash(folder: Path) -> str:
    from .live_trust import shipped_hash

    try:
        return shipped_hash(folder)
    except OSError as exc:
        raise ManifestError(f"cannot read {folder}: {exc}") from exc


def _canonical(data: object) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def manifest_path(rig: Path, run_id: str) -> Path:
    return Path(rig) / "logs" / f"{run_id}{MANIFEST_SUFFIX}"


def check_run_id(run_id: str) -> str:
    if not _RUN_ID.match(run_id or ""):
        raise ManifestError(f"{run_id!r} is not a usable run id (letters, digits, dot, dash and underscore; at most 81 characters)")
    return run_id


# ---- rig ownership ----------------------------------------------------------------------------------------------

def rig_owner(rig: Path) -> dict | None:
    try:
        data = json.loads((Path(rig) / "logs" / OWNER_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def refuse_if_owned(rig: Path, action: str) -> None:
    """BridgeForge staging commands call this: a run that has prepared its manifest owns the rig until it is released."""
    owner = rig_owner(rig)
    if owner:
        raise ManifestError(f"run {owner.get('run_id')} owns the rig (manifest {str(owner.get('manifest_id'))[:12]}); {action} refused. "
                            f"Finish it, or `bridgeforge run-manifest release {rig} {owner.get('run_id')}` if it died")


# ---- staging state shared by rig-up and probe-group install ------------------------------------------------------

def read_staging_state(rig: Path) -> dict:
    try:
        data = json.loads((Path(rig) / RIG_STATE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def record_candidates(rig: Path, candidates: dict[str, Path]) -> None:
    """Remember which working copy each staged mod id came from (merged into rig_up_state.json), so the manifest can bind them."""
    state = read_staging_state(rig)
    state["candidates"] = {mod_id: {"working": str(Path(working).resolve()), "workspace": Path(working).resolve().parent.name}
                           for mod_id, working in candidates.items()}
    state.setdefault("schema_version", 1)
    atomic_write_json(Path(rig) / RIG_STATE_FILE, state)


# ---- the manifest -----------------------------------------------------------------------------------------------

def _enabled_ids(rig: Path) -> list[str]:
    path = Path(rig) / "mods" / "enabled_mods.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ManifestError(f"cannot read {path}: {exc}") from exc
    ids = data.get("enabledMods") if isinstance(data, dict) else None
    if not isinstance(ids, list) or not all(isinstance(i, str) and i for i in ids):
        raise ManifestError(f"{path} has no usable enabledMods list")
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ManifestError(f"enabled_mods.json lists {', '.join(duplicates)} more than once")
    return ids


def _rig_folders(rig: Path) -> dict[str, list[Path]]:
    from .scanner import _load_lenient_json_file

    found: dict[str, list[Path]] = {}
    mods = Path(rig) / "mods"
    for child in sorted(p for p in mods.iterdir() if p.is_dir()) if mods.is_dir() else []:
        info = _load_lenient_json_file(child / "mod_info.json") if (child / "mod_info.json").is_file() else None
        mod_id = info.get("id") if isinstance(info, dict) else None
        if isinstance(mod_id, str) and mod_id:
            found.setdefault(mod_id, []).append(child)
    return found


def _staged_entries(rig: Path, enabled: list[str]) -> list[dict]:
    from .scanner import _load_lenient_json_file

    folders = _rig_folders(rig)
    entries = []
    for mod_id in enabled:
        candidates = folders.get(mod_id, [])
        if not candidates:
            raise ManifestError(f"enabled mod {mod_id} is not installed in the rig")
        if len(candidates) > 1:
            raise ManifestError(f"enabled mod {mod_id} is installed in {len(candidates)} rig folders: {', '.join(c.name for c in candidates)}")
        info = _load_lenient_json_file(candidates[0] / "mod_info.json")
        entries.append({"id": mod_id, "version": str((info or {}).get("version") or ""), "folder": candidates[0].name,
                        "staged_sha256": _tree_hash(candidates[0])})
    return entries


def _launcher_files(rig: Path, launcher: Path | None) -> tuple[dict[str, str], str | None]:
    files: dict[str, str] = {}
    java = None
    names = [Path(launcher)] if launcher else []
    names += sorted(Path(rig).glob("*.vmparams"))
    for path in names:
        if path.is_file():
            files[path.name] = _sha256_file(path)
    if launcher and Path(launcher).is_file():
        found = _JAVA_EXE.search(Path(launcher).read_text(encoding="utf-8", errors="replace"))
        java = next((part for part in found.groups() if part), None) if found else None
    return files, java


def _resolve_java_executable(rig: Path, launcher: Path | None, java: str | None) -> Path | None:
    """Resolve the Java command selected by the launcher without searching for an unrelated installed JDK."""
    if not java:
        return None
    # A batch file may SET these variables/PATH differently from this Python process. Do not substitute the host JDK.
    if "%" in java or "$" in java:
        return None
    candidate = Path(java.strip())
    if candidate.parent == Path("."):
        return None
    candidates = [candidate] if candidate.is_absolute() else [Path(rig) / candidate]
    if launcher and not candidate.is_absolute():
        candidates.insert(0, Path(launcher).parent / candidate)
    for path in candidates:
        if path.is_file():
            return path.resolve()
    return None


def _java_version(rig: Path, launcher: Path | None, java: str | None) -> str | None:
    """Observe the selected JDK version from its release file or bounded `java -version`; never launch mod code."""
    executable = _resolve_java_executable(rig, launcher, java)
    if executable is None:
        return None
    release = executable.parent.parent / "release"
    try:
        match = _JAVA_VERSION.search(release.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        match = None
    if match:
        return match.group(1)
    try:
        result = subprocess.run([str(executable), "-version"], capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    output = f"{result.stdout}\n{result.stderr}"
    match = _JAVA_VERSION_OUTPUT.search(output)
    return match.group(1) if match else None


def runtime_hashes(rig: Path, launcher: Path | None) -> dict:
    """Runtime configuration, hashed apart from the shipped files: the enabled list, the probe config and the launcher files."""
    rig = Path(rig)
    enabled = rig / "mods" / "enabled_mods.json"
    config = rig / CONFIG_RELATIVE
    files, java = _launcher_files(rig, launcher)
    return {"enabled_mods_sha256": _sha256_file(enabled) if enabled.is_file() else None,
            "probe_config_sha256": _sha256_file(config) if config.is_file() else None,
            "launcher_files": files, "java_executable": java, "java_version": _java_version(rig, launcher, java)}


def prepare_run(rig: Path, run_id: str, kind: str, *, targets: list[str], expected: list[str], scenario: str = "",
                candidates: dict[str, Path] | None = None, launcher: Path | None = None, core_baseline: Path | None = None) -> dict:
    """Write the pre-launch manifest and take ownership of the rig. Raises ManifestError (and writes nothing) when the rig is not an
    isolated one, another run owns it, an enabled id is duplicated, missing or unreadable, a target is not enabled, or the scenario
    expects a milestone this kind of run cannot show."""
    rig = Path(rig).expanduser().resolve()
    check_run_id(run_id)
    if kind not in KIND_CAPABILITY:
        raise ManifestError(f"unknown run kind {kind!r} (one of {', '.join(sorted(KIND_CAPABILITY))})")
    unknown = [m for m in expected if m not in MILESTONES]
    if unknown:
        raise ManifestError(f"unknown milestone(s) {', '.join(unknown)} (known: {', '.join(MILESTONES)})")
    beyond = [m for m in expected if m not in KIND_CAPABILITY[kind]]
    if beyond:
        raise ManifestError(f"a {kind} run cannot show {', '.join(beyond)}; use a campaign or live run for that requirement")
    if not _is_link(rig / "starsector-core"):
        raise ManifestError(f"{rig / 'starsector-core'} is not a junction/symlink: no manifest for a non-isolated rig")
    existing = manifest_path(rig, run_id)
    owner = rig_owner(rig)
    if owner and owner.get("run_id") != run_id:
        refuse_if_owned(rig, "a new run")
    enabled = _enabled_ids(rig)
    entries = _staged_entries(rig, enabled)
    by_id = {entry["id"]: entry for entry in entries}
    state_candidates = {k: Path(v["working"]) for k, v in (read_staging_state(rig).get("candidates") or {}).items() if isinstance(v, dict) and v.get("working")}
    bound = dict(candidates) if candidates is not None else state_candidates
    target_rows = {}
    for mod_id in targets:
        if mod_id not in by_id:
            raise ManifestError(f"target {mod_id} is not an enabled mod of the rig")
        if mod_id not in bound:
            raise ManifestError(f"target {mod_id} has no recorded candidate working copy (stage it with rig-up or probe-group install)")
        target_rows[mod_id] = {"candidate_sha256": _tree_hash(Path(bound[mod_id])), "working": str(Path(bound[mod_id]).resolve())}
    log = rig / "logs" / f"{run_id}.stdout.log"
    body = {"schema_version": MANIFEST_VERSION, "fileset_algorithm": FILESET_ALGORITHM, "run_id": run_id, "kind": kind,
            "scenario": scenario, "rig": str(rig), "rig_core": str((rig / "starsector-core").resolve()),
            "enabled": entries, "targets": target_rows, "runtime": runtime_hashes(rig, launcher),
            "core_baseline_sha256": _sha256_file(core_baseline) if core_baseline and Path(core_baseline).is_file() else None,
            "expected_milestones": sorted(set(expected)), "log": str(log)}
    body["java_version"] = body["runtime"].get("java_version")
    manifest_id = hashlib.sha256(_canonical(body)).hexdigest()
    manifest = {**body, "manifest_id": manifest_id, "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "created_epoch": time.time()}
    if existing.is_file():
        previous = read_manifest(rig, run_id)
        if previous["manifest_id"] != manifest_id:
            raise ManifestError(f"run id {run_id} already has a different manifest; use a new run id")
        return previous
    (rig / "logs").mkdir(parents=True, exist_ok=True)
    atomic_write_json(existing, manifest)
    atomic_write_json(rig / "logs" / OWNER_FILE, {"run_id": run_id, "manifest_id": manifest_id, "since": manifest["created_at"]})
    return manifest


def read_manifest(rig: Path, run_id: str) -> dict:
    """The manifest of a run. Raises ManifestError when it is missing, unreadable, of another version or algorithm."""
    path = manifest_path(rig, check_run_id(run_id))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ManifestError(f"no readable manifest for run {run_id} at {path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != MANIFEST_VERSION:
        raise ManifestError(f"{path} is not a version {MANIFEST_VERSION} manifest")
    if data.get("fileset_algorithm") != FILESET_ALGORITHM:
        raise ManifestError(f"{path} was hashed with {data.get('fileset_algorithm')!r}, not {FILESET_ALGORITHM!r}")
    body = {k: v for k, v in data.items() if k not in ("manifest_id", "created_at", "created_epoch")}
    if hashlib.sha256(_canonical(body)).hexdigest() != data.get("manifest_id"):
        raise ManifestError(f"{path} does not match its own manifest id (edited after it was written)")
    return data


def staged_drift(rig: Path, manifest: dict, launcher: Path | None = None) -> list[str]:
    """What differs between the manifest and the rig now: staged mod hashes, the enabled list, runtime configuration."""
    rig = Path(rig)
    problems: list[str] = []
    try:
        now = {entry["id"]: entry for entry in _staged_entries(rig, _enabled_ids(rig))}
    except ManifestError as exc:
        return [str(exc)]
    recorded = {entry["id"]: entry for entry in manifest["enabled"]}
    for mod_id in sorted(set(recorded) - set(now)):
        problems.append(f"{mod_id} was enabled at launch and is not now")
    for mod_id in sorted(set(now) - set(recorded)):
        problems.append(f"{mod_id} is enabled now and was not at launch")
    for mod_id in sorted(set(now) & set(recorded)):
        if now[mod_id]["staged_sha256"] != recorded[mod_id]["staged_sha256"]:
            problems.append(f"staged files of {mod_id} changed since launch")
    launcher_names = list((manifest["runtime"].get("launcher_files") or {}))
    chosen = launcher or (rig / launcher_names[0] if launcher_names else None)
    for key, value in runtime_hashes(rig, chosen).items():
        if key == "java_executable":
            continue
        if value != manifest["runtime"].get(key):
            problems.append(f"runtime configuration {key} changed since launch")
    return problems


def release_run(rig: Path, run_id: str, launcher: Path | None = None) -> dict:
    """Run ended: re-hash the staged files (completion check), write <run id>.completed.json, and give the rig back."""
    rig = Path(rig).expanduser().resolve()
    manifest = read_manifest(rig, run_id)
    drift = staged_drift(rig, manifest, launcher)
    completed = {"schema_version": 1, "run_id": run_id, "manifest_id": manifest["manifest_id"], "drift": drift,
                 "completed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "completed_epoch": time.time()}
    atomic_write_json(rig / "logs" / f"{run_id}{COMPLETED_SUFFIX}", completed)
    owner = rig_owner(rig)
    if owner and owner.get("run_id") == run_id:
        (rig / "logs" / OWNER_FILE).unlink(missing_ok=True)
    return completed


# ---- the evaluator ----------------------------------------------------------------------------------------------

def _milestones(log: Path, mods_dir: Path | None) -> dict[str, bool]:
    from .log_triage import triage_log

    triage = triage_log(log, mods_dir=mods_dir) if mods_dir is not None else triage_log(log)
    text = Path(log).read_text(encoding="utf-8", errors="replace")
    marks = triage["milestones"]
    return {"main_menu": bool(marks["main_menu_reached"]), "campaign_load": bool(marks["campaign_loads"]),
            "save": bool(marks["finished_saving_count"]), "content_ids": bool(_CONTENT_IDS.search(text)),
            "combat": bool(_COMBAT.search(text))}


def evaluate_run(rig: Path, manifest: dict | None, log: Path, *, member_verdicts: dict[str, str] | None = None,
                 mods_dir: Path | None = None, launcher: Path | None = None) -> dict:
    """The shared evidence evaluator. Status ACCEPTABLE only when, for the run as a whole, the manifest is intact, the log is this
    run's own and newer than the manifest, nothing staged or configured drifted (at completion and now), and the expected milestones
    show; and per target when its staged bytes equal its candidate, its candidate is unchanged now, and its verdict is PASS.
    A target failing alone is `ok: false` while the run's other targets keep theirs: an unrelated member's success is not enough."""
    rig = Path(rig).expanduser().resolve()
    if manifest is None:
        return {"schema_version": 1, "mode": "RUN_EVIDENCE", "status": "UNKNOWN_PROVENANCE", "run_id": None, "manifest_id": None,
                "problems": ["no pre-launch manifest: the run's inputs were not recorded before launch (provenance UNKNOWN)"], "members": {}}
    problems: list[str] = []
    log = Path(log).expanduser().resolve()
    if log != Path(manifest["log"]).resolve():
        problems.append(f"log {log} is not the manifest's run log {manifest['log']}")
    log_info: dict = {"path": str(log), "sha256": None, "size": 0}
    milestones: dict[str, bool] = {m: False for m in MILESTONES}
    if log.is_file():
        stat = log.stat()
        log_info.update(sha256=_sha256_file(log), size=stat.st_size)
        if stat.st_size == 0:
            problems.append("the run log is empty")
        if stat.st_mtime + EPOCH_SLACK_SECONDS < float(manifest.get("created_epoch") or 0):
            problems.append("the log is older than the manifest: not written by this run")
        milestones = _milestones(log, mods_dir)
    else:
        problems.append(f"the run log {log} does not exist")
    for name in manifest["expected_milestones"]:
        if not milestones.get(name):
            problems.append(f"expected milestone {name} not observed in the log")
    completed_path = rig / "logs" / f"{manifest['run_id']}{COMPLETED_SUFFIX}"
    try:
        completed = json.loads(completed_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        completed = None
    if not isinstance(completed, dict) or completed.get("manifest_id") != manifest["manifest_id"]:
        problems.append("no completion record for this manifest (the run was not released, or the record is for another manifest)")
    elif completed.get("drift"):
        problems.append("staged inputs drifted during the run: " + "; ".join(completed["drift"][:5]))
    problems.extend(f"now: {item}" for item in staged_drift(rig, manifest, launcher))
    staged = {entry["id"]: entry for entry in manifest["enabled"]}
    members: dict[str, dict] = {}
    for mod_id, target in sorted(manifest["targets"].items()):
        issues: list[str] = []
        if mod_id not in staged:
            issues.append("target absent from the enabled mods")
        elif staged[mod_id]["staged_sha256"] != target["candidate_sha256"]:
            issues.append("staged files differ from the candidate working copy")
        try:
            now = _tree_hash(Path(target["working"]))
        except ManifestError as exc:
            now = None
            issues.append(str(exc))
        if now is not None and now != target["candidate_sha256"]:
            issues.append("the working copy changed after the run was prepared")
        verdict = (member_verdicts or {}).get(mod_id, "PASS")
        if verdict != "PASS":
            issues.append(f"verdict {verdict}")
        members[mod_id] = {"verdict": verdict, "candidate_sha256": target["candidate_sha256"], "workspace_sha256_now": now,
                           "ok": not issues, "problems": issues}
    if not members:
        problems.append("the manifest names no target")
    status = "ACCEPTABLE" if not problems and any(m["ok"] for m in members.values()) else "REFUSED"
    return {"schema_version": 1, "mode": "RUN_EVIDENCE", "status": status, "run_id": manifest["run_id"], "manifest_id": manifest["manifest_id"],
            "kind": manifest["kind"], "log": log_info, "milestones": milestones, "expected_milestones": manifest["expected_milestones"],
            "problems": problems, "members": members}


def summary_for_record(manifest: dict) -> dict:
    """What a run record keeps of the manifest so later selection can notice dependency, probe and launcher drift (regress --changed-since)."""
    targets = set(manifest["targets"])
    return {"manifest_id": manifest["manifest_id"], "kind": manifest["kind"], "scenario": manifest["scenario"],
            "dependencies": {e["id"]: {"version": e["version"], "staged_sha256": e["staged_sha256"], "folder": e["folder"]}
                             for e in manifest["enabled"] if e["id"] not in targets},
            "launcher_files": manifest["runtime"].get("launcher_files"), "probe_config_sha256": manifest["runtime"].get("probe_config_sha256"),
            "java_executable": manifest["runtime"].get("java_executable"), "java_version": manifest.get("java_version"),
            "expected_milestones": manifest["expected_milestones"]}


def environment_drift(rig: Path, summary: dict | None) -> list[str]:
    """How the rig's providers, probe config and launcher files differ now from a recorded run's manifest summary."""
    if not summary:
        return ["no manifest summary recorded"]
    rig = Path(rig)
    problems: list[str] = []
    folders = _rig_folders(rig)
    for mod_id, dep in sorted((summary.get("dependencies") or {}).items()):
        found = folders.get(mod_id, [])
        if len(found) != 1:
            problems.append(f"dependency {mod_id} is not installed exactly once")
        elif _tree_hash(found[0]) != dep["staged_sha256"]:
            problems.append(f"dependency {mod_id} changed since the last run")
    config = rig / CONFIG_RELATIVE
    now_config = _sha256_file(config) if config.is_file() else None
    if summary.get("probe_config_sha256") and now_config != summary["probe_config_sha256"]:
        problems.append("probe config changed since the last run")
    for name, digest in sorted((summary.get("launcher_files") or {}).items()):
        path = rig / name
        if not path.is_file() or _sha256_file(path) != digest:
            problems.append(f"launcher file {name} changed since the last run")
    return problems


# ---- command ----------------------------------------------------------------------------------------------------

def add_parser(subcommands) -> None:
    cmd = subcommands.add_parser("run-manifest", help="pre-launch run manifests (ROADMAP item 75 R1): prepare one before a live run, release the rig after it, check a run against its manifest")
    sub = cmd.add_subparsers(dest="run_manifest_command", required=True)
    prepare = sub.add_parser("prepare", help="record the staged inputs of a run before launch and take ownership of the rig")
    prepare.add_argument("rig", type=Path)
    prepare.add_argument("run_id")
    prepare.add_argument("--kind", choices=sorted(KIND_CAPABILITY), default="live")
    prepare.add_argument("--target", action="append", default=[], metavar="MOD_ID", help="a mod under test (default: every candidate rig-up or install recorded); repeatable")
    prepare.add_argument("--expect", action="append", default=None, metavar="MILESTONE", help=f"milestone the log must show ({', '.join(MILESTONES)}); repeatable; default: main_menu")
    prepare.add_argument("--scenario", default="")
    prepare.add_argument("--launcher", type=Path, help="the launcher .bat (hashed with the rig's *.vmparams)")
    prepare.add_argument("--json", action="store_true")
    release = sub.add_parser("release", help="the run ended: re-hash the staged files, write the completion record, give the rig back")
    release.add_argument("rig", type=Path)
    release.add_argument("run_id")
    release.add_argument("--launcher", type=Path)
    release.add_argument("--json", action="store_true")
    check = sub.add_parser("check", help="evaluate a finished run against its manifest (read-only)")
    check.add_argument("rig", type=Path)
    check.add_argument("run_id")
    check.add_argument("--json", action="store_true")


def run_cli(args: argparse.Namespace) -> int:
    try:
        rig = Path(args.rig).expanduser().resolve()
        if args.run_manifest_command == "prepare":
            targets = args.target or sorted(read_staging_state(rig).get("candidates") or {})
            result = prepare_run(rig, args.run_id, args.kind, targets=targets, expected=args.expect or ["main_menu"],
                                 scenario=args.scenario, launcher=args.launcher)
            text = f"Manifest {result['manifest_id'][:12]} for run {args.run_id}: {len(result['enabled'])} enabled mod(s), targets {', '.join(result['targets']) or 'none'}; the rig is owned until release"
        elif args.run_manifest_command == "release":
            result = release_run(rig, args.run_id, args.launcher)
            text = f"Run {args.run_id} released; drift: {'; '.join(result['drift']) or 'none'}"
        else:
            manifest = read_manifest(rig, args.run_id)
            result = evaluate_run(rig, manifest, Path(manifest["log"]))
            text = f"{result['status']}: " + ("; ".join(result["problems"]) or "all identities and milestones match")
    except (ManifestError, OSError, ValueError) as exc:
        print(f"bridgeforge: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False) if args.json else text)
    return 1 if result.get("status") in ("REFUSED", "UNKNOWN_PROVENANCE") else 0
