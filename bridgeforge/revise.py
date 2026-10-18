"""`revise prepare` / `revise finalize`: a revised mod is tested as the bytes it is archived as (ROADMAP item 75 R5, replaces 73 H2).

The earlier idea, bump the version and archive in one command, needed a live run of a version it had just created. The flow is now

1. `revise prepare WORKSPACE "reason"`: bump `+bf.N` ONCE, record the previous archive, the authorized scope (a local archive; never a
   push or a publication) and the candidate's file hash in a journal `reports/revisions/<revision id>.json`. Repeating it for the same
   candidate returns the pending revision; a changed candidate needs `--refresh-candidate`, which invalidates the old evidence
   instead of bumping again.
2. the existing rig and scenario commands (`rig-up`, `run-manifest`, the live run, `accept`) test exactly those bytes (item 75 R1).
3. `revise finalize WORKSPACE --revision ID --test-id ID`: re-check from the run records (not from the journal's word) that the test
   was a PASS, bound by a manifest to this candidate and version, that the candidate is unchanged, the archive gate and the migration
   evidence of H3 hold; then changelog, archive (an existing Done/<Mod> is moved to Done/_replaced-<date>/, never deleted), verify the
   archived bytes equal the tested bytes, readme copies, snapshot. Finalize never edits shipped files or the version.

Journal states: PREPARED -> LIVE_ACCEPTED -> ARCHIVED -> SNAPSHOTTED -> COMPLETE. A step that fails records FAILED_STEP with its error
and leaves the state at the last good step; running finalize again resumes the incomplete work only (no duplicated changelog line,
no second archive when the first one's recorded hash still matches). State writes are atomic and the workspace is locked.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from .safeio import atomic_write_json, atomic_write_text

SCHEMA_VERSION = 1
STATES = ("PREPARED", "LIVE_ACCEPTED", "ARCHIVED", "SNAPSHOTTED", "COMPLETE")
SCOPE = ["local-archive"]
LOCK_NAME = ".lock"


class ReviseError(ValueError):
    """The revision cannot be prepared or finalized; nothing was changed (or only what the journal says)."""


class StepFailed(ReviseError):
    """A finalize step failed after earlier ones succeeded; the journal records the exact partial state."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def revisions_dir(workspace: Path) -> Path:
    return Path(workspace) / "reports" / "revisions"


def _journal_path(workspace: Path, revision_id: str) -> Path:
    if not re.fullmatch(r"[\w.-]+", revision_id or ""):
        raise ReviseError(f"{revision_id!r} is not a revision id")
    return revisions_dir(workspace) / f"{revision_id}.json"


def read_journal(workspace: Path, revision_id: str) -> dict:
    try:
        data = json.loads(_journal_path(workspace, revision_id).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ReviseError(f"no readable revision {revision_id} in {revisions_dir(workspace)}: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise ReviseError(f"revision {revision_id} has an unsupported journal")
    return data


def _save(workspace: Path, journal: dict) -> None:
    atomic_write_json(_journal_path(workspace, journal["revision_id"]), journal)


def _set_state(workspace: Path, journal: dict, state: str) -> None:
    journal["state"] = state
    journal["failed_step"] = None
    journal["history"].append({"state": state, "at": _now()})
    _save(workspace, journal)


def pending_journals(workspace: Path) -> list[dict]:
    found = []
    for path in sorted(revisions_dir(workspace).glob("*.json")) if revisions_dir(workspace).is_dir() else []:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get("state") in STATES and data.get("state") != "COMPLETE":
            found.append(data)
    return found


class _Lock:
    """One revise operation per workspace: an exclusively created lock file."""

    def __init__(self, workspace: Path) -> None:
        self.path = revisions_dir(workspace) / LOCK_NAME

    def __enter__(self) -> "_Lock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            handle = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise ReviseError(f"another revise operation holds {self.path}; wait for it, or delete the file if none is running") from exc
        os.write(handle, f"pid {os.getpid()} {_now()}\n".encode("utf-8"))
        os.close(handle)
        return self

    def __exit__(self, *exc: object) -> None:
        self.path.unlink(missing_ok=True)


def _info(working: Path) -> dict:
    from .scanner import _load_lenient_json_file

    info = _load_lenient_json_file(working / "mod_info.json") if (working / "mod_info.json").is_file() else None
    if not isinstance(info, dict):
        raise ReviseError(f"{working / 'mod_info.json'} is missing or unreadable")
    return info


def _write_version(working: Path, old: str, new: str) -> None:
    path = working / "mod_info.json"
    text = path.read_text(encoding="utf-8")
    needle = json.dumps(old)
    if text.count(needle) != 1:
        raise ReviseError(f"{path}: the version string appears {text.count(needle)} times; set it by hand and use --keep-version")
    atomic_write_text(path, text.replace(needle, json.dumps(new), 1), newline="")


def _previous(done_dir: Path, workspace: Path) -> dict | None:
    from .archive import _previous_version
    from .live_trust import shipped_hash

    root = Path(done_dir) / workspace.name / workspace.name
    if not root.is_dir():
        return None
    return {"archive": str(Path(done_dir) / workspace.name), "root": str(root), "version": _previous_version(root), "shipped_sha256": shipped_hash(root)}


def prepare(workspace: Path, reason: str, *, done_dir: Path, refresh_candidate: bool = False, keep_version: bool = False,
            today: str | None = None) -> dict:
    from .live_trust import live_status, shipped_hash
    from .workspace_tools import next_version

    workspace = Path(workspace).expanduser().resolve()
    working = workspace / "working"
    if not reason.strip():
        raise ReviseError("say what changed: the reason goes into the journal and the mod changelog")
    info = _info(working)
    with _Lock(workspace):
        pending = pending_journals(workspace)
        if len(pending) > 1:
            raise ReviseError(f"{len(pending)} revisions are pending in {revisions_dir(workspace)}; finish or remove all but one")
        candidate = shipped_hash(working)
        if pending:
            journal = pending[0]
            if journal["candidate"]["shipped_sha256"] == candidate:
                return {**journal, "mode": "REVISE_PREPARE", "reused": True}
            if journal["state"] != "PREPARED":
                raise ReviseError(f"revision {journal['revision_id']} is {journal['state']} and its candidate changed: recover it, do not prepare another")
            if not refresh_candidate:
                raise ReviseError(f"the working copy changed since revision {journal['revision_id']} was prepared; "
                                  "`revise prepare ... --refresh-candidate` keeps the version, records the new candidate and invalidates the old test evidence")
            journal["superseded"] = [*journal.get("superseded", []), {"candidate_sha256": journal["candidate"]["shipped_sha256"], "at": _now(),
                                                                     "live_status_then": live_status(workspace).get("test_id")}]
            journal["candidate"] = {"shipped_sha256": candidate, "version": journal["new_version"]}
            journal["migration"] = _migration_summary(workspace, journal.get("previous"), working)
            _set_state(workspace, journal, "PREPARED")
            return {**journal, "mode": "REVISE_PREPARE", "reused": False, "refreshed": True}
        old = info.get("version")
        if not isinstance(old, str) or not old:
            raise ReviseError(f"mod_info version is not a plain string ({old!r}); set it by hand and use --keep-version")
        new = old if keep_version else next_version(old)
        previous = _previous(done_dir, workspace)
        if previous and previous["version"] == new:
            raise ReviseError(f"version {new} is the one already archived; a revision needs a new version")
        if not keep_version:
            _write_version(working, old, new)
        mod_id = str(info.get("id") or workspace.name)
        revision_id = re.sub(r"[^\w.-]", "_", f"{mod_id}-{new}")
        if _journal_path(workspace, revision_id).is_file():
            raise ReviseError(f"revision {revision_id} was already used (completed); the working copy must carry a newer version")
        journal = {"schema_version": SCHEMA_VERSION, "revision_id": revision_id, "mod_id": mod_id, "mod_name": str(info.get("name") or workspace.name),
                   "workspace": workspace.name, "reason": reason.strip(), "day": today or date.today().isoformat(), "previous_version_in_work": old,
                   "new_version": new, "previous": previous, "scope": list(SCOPE),
                   "publication": "not authorized: this revision is archived locally; a push or publication needs its own authorization",
                   "candidate": {"shipped_sha256": shipped_hash(working), "version": new},
                   "migration": _migration_summary(workspace, previous, working), "steps": {}, "superseded": [], "state": "PREPARED",
                   "failed_step": None, "history": [{"state": "PREPARED", "at": _now()}]}
        _save(workspace, journal)
        return {**journal, "mode": "REVISE_PREPARE", "reused": False}


def _migration_summary(workspace: Path, previous: dict | None, working: Path) -> dict:
    from .revision_renames import migration_requirement

    result = migration_requirement(workspace, Path(previous["root"]) if previous else None, working)
    return {"required": result["required"], "satisfied": result["satisfied"], "how": result["how"], "removed_sha256": result["removed_sha256"],
            "problems": result["problems"]}


def _bound_run(workspace: Path, journal: dict, test_id: str) -> dict:
    """The run record line proving `test_id` was a PASS bound to this candidate and version (read from the records, not the journal)."""
    from .live_trust import RUN_LOG, live_status

    log = workspace / "reports" / RUN_LOG
    try:
        lines = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, ValueError) as exc:
        raise ReviseError(f"no readable run log {log}: {exc}") from exc
    mine = [r for r in lines if r.get("test_id") == test_id]
    if not mine:
        raise ReviseError(f"no run {test_id} is recorded for {workspace.name}; accept the run first (`probe-group record --accept` or `accept`)")
    line = mine[-1]
    candidate = journal["candidate"]["shipped_sha256"]
    wrong = []
    if line.get("verdict") != "PASS":
        wrong.append(f"verdict {line.get('verdict')}")
    if line.get("provenance") != "BOUND":
        wrong.append(f"provenance {line.get('provenance', 'UNKNOWN (legacy)')}: not bound to staged inputs by a manifest")
    if line.get("shipped_sha256") != candidate:
        wrong.append("it tested other bytes than the prepared candidate")
    if str(line.get("version")) != journal["new_version"]:
        wrong.append(f"it tested version {line.get('version')}, not {journal['new_version']}")
    if wrong:
        raise ReviseError(f"run {test_id} does not qualify: " + "; ".join(wrong))
    status = live_status(workspace)
    if status["status"] != "CURRENT" or status.get("test_id") != test_id:
        raise ReviseError(f"the live status is {status['status']} (test {status.get('test_id')}), not CURRENT for {test_id}")
    return line


def finalize(workspace: Path, revision_id: str, test_id: str, *, done_dir: Path, policy_path: Path | None = None,
             changelog: Path | None = None) -> dict:
    from .live_trust import archive_gate, shipped_hash
    from .revision_renames import migration_requirement

    workspace = Path(workspace).expanduser().resolve()
    working = workspace / "working"
    done_dir = Path(done_dir).expanduser().resolve()
    with _Lock(workspace):
        journal = read_journal(workspace, revision_id)
        if journal["scope"] != SCOPE:
            raise ReviseError("the journal's scope does not authorize a local archive")
        if journal["state"] == "COMPLETE":
            return {**journal, "mode": "REVISE_FINALIZE", "already_complete": True, "reconciled": _verify_archive(done_dir, workspace, journal)}
        if shipped_hash(working) != journal["candidate"]["shipped_sha256"]:
            raise ReviseError("the working copy changed after the candidate was prepared; `revise prepare --refresh-candidate` and test again")
        line = _bound_run(workspace, journal, test_id)
        if journal["state"] == "PREPARED":
            gate = archive_gate(workspace)
            problems = list(gate["problems"])
            previous = journal.get("previous")
            requirement = migration_requirement(workspace, Path(previous["root"]) if previous else None, working)
            problems += requirement["problems"]
            if problems:
                raise ReviseError("the release gates are not met: " + "; ".join(problems))
            journal["live"] = {"test_id": test_id, "manifest_id": line.get("manifest_id"), "date": line.get("date")}
            journal["migration"] = _migration_summary(workspace, previous, working)
            _set_state(workspace, journal, "LIVE_ACCEPTED")
        elif journal.get("live", {}).get("test_id") != test_id:
            raise ReviseError(f"revision {revision_id} was accepted with run {journal.get('live', {}).get('test_id')}, not {test_id}")
        for name, step in (("changelog", _step_changelog), ("archive", _step_archive), ("snapshot", _step_snapshot)):
            try:
                step(workspace, journal, done_dir, policy_path, changelog)
            except StepFailed:
                raise
            except Exception as exc:  # report the exact partial state, never swallow it
                journal["failed_step"] = {"step": name, "error": f"{type(exc).__name__}: {exc}", "at": _now()}
                _save(workspace, journal)
                raise StepFailed(f"{name} failed after {journal['state']}: {exc}; run finalize again to resume") from exc
        _set_state(workspace, journal, "COMPLETE")
        return {**journal, "mode": "REVISE_FINALIZE", "already_complete": False}


def _step_changelog(workspace: Path, journal: dict, done_dir: Path, policy_path: Path | None, changelog: Path | None) -> None:
    from .mod_changelog import add_entry

    if journal["steps"].get("changelog"):
        return
    path = changelog or done_dir.parent / "MOD_CHANGELOG.md"
    line = add_entry(journal["mod_name"], journal["reason"].split("\n")[0], version=journal["new_version"], day=journal["day"], path=path)
    journal["steps"]["changelog"] = {"line": line, "path": str(path)}
    _save(workspace, journal)


def _archived_folder_matches(done_dir: Path, workspace: Path, journal: dict) -> bool:
    from .live_trust import shipped_hash

    folder = done_dir / workspace.name / workspace.name
    note = done_dir / workspace.name / "ARCHIVE_NOTE.md"
    return folder.is_dir() and note.is_file() and shipped_hash(folder) == journal["candidate"]["shipped_sha256"]


def _step_archive(workspace: Path, journal: dict, done_dir: Path, policy_path: Path | None, changelog: Path | None) -> None:
    from .archive import archive_mod, write_readme_copies

    if journal["state"] in ("ARCHIVED", "SNAPSHOTTED"):
        if not _archived_folder_matches(done_dir, workspace, journal):
            raise ReviseError("the journal says ARCHIVED but the archive no longer holds the tested bytes; recover by hand (the old archive is in Done/_replaced-*)")
        return
    if _archived_folder_matches(done_dir, workspace, journal) and (done_dir / workspace.name).is_dir():
        result = {"zip": next(iter(sorted((done_dir / workspace.name).glob("*.zip"))), None), "replaced": None, "reconciled": True}
    else:
        result = archive_mod(workspace, done_dir, policy_path=policy_path, today=journal["day"], refresh=False, move_aside=True)
        zip_path = Path(result["zip"])
        shutil.copy2(zip_path, done_dir / zip_path.name)
        write_readme_copies(Path(result["archive"]))
        if not _archived_folder_matches(done_dir, workspace, journal):
            raise ReviseError("the archived files differ from the tested candidate; the archive was written but not accepted")
        result["reconciled"] = False
    zip_path = result.get("zip")
    journal["steps"]["archive"] = {"folder": str(done_dir / workspace.name), "zip": str(zip_path) if zip_path else None,
                                   "zip_sha256": _file_sha(Path(zip_path)) if zip_path else None, "replaced": result.get("replaced"),
                                   "reconciled": result["reconciled"]}
    _set_state(workspace, journal, "ARCHIVED")


def _file_sha(path: Path) -> str:
    import hashlib

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _step_snapshot(workspace: Path, journal: dict, done_dir: Path, policy_path: Path | None, changelog: Path | None) -> None:
    from .state_snapshot import snapshot_after_archive

    if journal["state"] == "SNAPSHOTTED":
        return
    note = snapshot_after_archive(done_dir)
    if note and note.startswith("snapshot after archive FAILED"):
        raise ReviseError(note)
    journal["steps"]["snapshot"] = note or "not configured (no bridgeforge-state/snapshot.json)"
    _set_state(workspace, journal, "SNAPSHOTTED")


def _verify_archive(done_dir: Path, workspace: Path, journal: dict) -> bool:
    return _archived_folder_matches(Path(done_dir), workspace, journal)


# ---- command ----------------------------------------------------------------------------------------------------

def add_parser(subcommands) -> None:
    cmd = subcommands.add_parser("revise", help="a revised mod is tested as the bytes it is archived as (ROADMAP item 75 R5): prepare bumps +bf.N once and journals the candidate; after the live test, finalize archives exactly those bytes; local only, never pushes")
    sub = cmd.add_subparsers(dest="revise_command", required=True)
    prepare_cmd = sub.add_parser("prepare", help="bump the version once, journal the previous archive and the candidate's hash (repeating it for the same candidate returns the pending revision)")
    prepare_cmd.add_argument("workspace", type=Path)
    prepare_cmd.add_argument("reason", help="what changed (the first line goes to the mod changelog)")
    prepare_cmd.add_argument("--refresh-candidate", action="store_true", help="the working copy changed since prepare: keep the version, record the new candidate, invalidate the old test evidence")
    prepare_cmd.add_argument("--keep-version", action="store_true", help="the version in mod_info is already the new one (do not bump)")
    prepare_cmd.add_argument("--done", type=Path, help="default: <repo>/Done")
    prepare_cmd.add_argument("--json", action="store_true")
    finalize_cmd = sub.add_parser("finalize", help="after the accepted live run: changelog, archive (old archive kept in Done/_replaced-*), tested-bytes check, readme copies, snapshot; resumes after a failed step")
    finalize_cmd.add_argument("workspace", type=Path)
    finalize_cmd.add_argument("--revision", required=True, metavar="ID")
    finalize_cmd.add_argument("--test-id", required=True, metavar="ID")
    finalize_cmd.add_argument("--done", type=Path)
    finalize_cmd.add_argument("--json", action="store_true")
    status_cmd = sub.add_parser("status", help="list the workspace's revision journals (read-only)")
    status_cmd.add_argument("workspace", type=Path)
    status_cmd.add_argument("--json", action="store_true")
    migration_cmd = sub.add_parser("migration", help="record the answer to 'this revision drops ids or classes of the archived build': a written reason, or a migration pack file (docs/MIGRATION_PACK_CONTRACT.md fields plus save_compat.save)")
    migration_cmd.add_argument("workspace", type=Path)
    migration_cmd.add_argument("--reason", help="why no migration is needed (at least 20 characters)")
    migration_cmd.add_argument("--pack", type=Path, help="JSON file with the pack")
    migration_cmd.add_argument("--done", type=Path)
    migration_cmd.add_argument("--json", action="store_true")


def run_cli(args: argparse.Namespace) -> int:
    from .substitutes import REPO_ROOT

    workspace = Path(args.workspace).expanduser().resolve()
    done = (args.done or REPO_ROOT / "Done") if args.revise_command != "status" else None
    try:
        if args.revise_command == "prepare":
            result = prepare(workspace, args.reason, done_dir=done, refresh_candidate=args.refresh_candidate, keep_version=args.keep_version)
            text = (f"Revision {result['revision_id']} {'pending (unchanged)' if result.get('reused') else 'prepared'}: {result['previous_version_in_work']} -> "
                    f"{result['new_version']}, candidate {result['candidate']['shipped_sha256'][:12]}. Test exactly these bytes, then `revise finalize`.")
        elif args.revise_command == "finalize":
            result = finalize(workspace, args.revision, args.test_id, done_dir=done)
            text = (f"Revision {result['revision_id']} was already complete." if result.get("already_complete")
                    else f"Revision {result['revision_id']} COMPLETE: archived {result['steps']['archive']['folder']}; snapshot: {result['steps']['snapshot']}")
        elif args.revise_command == "migration":
            from .revision_renames import migration_requirement, write_evidence

            previous = _previous(done, workspace)
            requirement = migration_requirement(workspace, Path(previous["root"]) if previous else None, workspace / "working")
            pack = json.loads(args.pack.read_text(encoding="utf-8")) if args.pack else None
            path = write_evidence(workspace, requirement, reason=args.reason, pack=pack)
            result = migration_requirement(workspace, Path(previous["root"]) if previous else None, workspace / "working")
            text = f"Wrote {path}: " + ("satisfied" if result["satisfied"] else "NOT satisfied: " + "; ".join(result["problems"]))
        else:
            result = {"revisions": [json.loads(p.read_text(encoding="utf-8")) for p in sorted(revisions_dir(workspace).glob("*.json"))]}
            text = "\n".join(f"{r['revision_id']}: {r['state']}" + (f" (FAILED_STEP {r['failed_step']['step']}: {r['failed_step']['error']})" if r.get("failed_step") else "")
                             for r in result["revisions"]) or "no revisions"
    except StepFailed as exc:
        print(f"bridgeforge: {exc}", file=sys.stderr)
        return 1
    except (ReviseError, OSError, ValueError) as exc:
        print(f"bridgeforge: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False) if args.json else text)
    return 0
