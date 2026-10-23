"""Auto-acceptance as an explicit validation policy (ROADMAP item 73 E1/E2, refined by item 75 R3).

Report-only today: `evaluate_attempt` says whether an agent attempt would be ELIGIBLE for application without a person,
and which gate stops it otherwise. `escalation run --auto-accept` is REFUSED until `PREREQUISITES` (R1, R2, R4 of
docs/ROADMAP_IMPLEMENTATION_HANDOFF.md) are built and `ENABLED` is switched on; the application path
(`apply_attempt`: workspace lock, hash recheck, staged writes, journal, rollback) is implemented and unit-tested behind
that refusal so it can be enabled later.

Every check records a status (PASS, FAIL, INCOMPLETE, NOT_APPLICABLE), its reason, the tool identity, input and output
hashes and evidence. A check that could not run (no compiler or core, timeout, parser failure, no regression fixture)
is INCOMPLETE and cannot qualify. Only PASS and NOT_APPLICABLE (with a checked reason) qualify. Line counts and review
flags are extra signals, never proof; a finding tier of `none`, or silence from the flag regexes, bypasses nothing.

Scope. An approval covers a bounded kind of change, not any file in `allowed_files`: the queue folder's
`AUTO_ACCEPT_POLICY.json` names each finding id that may be applied unattended with the file suffixes it may change:

    {"schema_version": 1,
     "approved": {"json-empty-array-element": {"suffixes": [".json"], "max_files": 2,
                                               "regression": ["python", "check.py"]}},
     "maintained_third_party_mods": ["some_mod_id"]}

Never eligible: MANUAL/UNKNOWN findings, decision-tier findings (gameplay and owner decisions), save-migration and
lifecycle findings (`EXCLUDED_FINDING_PARTS`), and mods the policy lists as maintained third-party.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
from pathlib import Path

from bridgeforge import __version__
from bridgeforge.safeio import atomic_write_json

PASS, FAIL, INCOMPLETE, NOT_APPLICABLE = "PASS", "FAIL", "INCOMPLETE", "NOT_APPLICABLE"
QUALIFYING = (PASS, NOT_APPLICABLE)
POLICY_NAME = "AUTO_ACCEPT_POLICY.json"
DELETION_SLACK = 10
COMPILE_ERROR_IDS = ("loose-script-compile-error", "loose-script-janino-compile-error")
COMPILE_SKIPPED_IDS = ("loose-script-compile-unavailable",)
CODE_SUFFIXES = (".java", ".class", ".jar")
EXCLUDED_CLASSIFICATIONS = ("MANUAL", "UNKNOWN")
EXCLUDED_FINDING_PARTS = ("save", "migrat", "lifecycle", "live-object", "legacy-event")
REGRESSION_TIMEOUT = 300
JOURNAL_NAME = "APPLY_JOURNAL.json"
LOCK_NAME = "APPLY.lock"

# E2 stays off until the trust gates it depends on exist (item 75). Flip with the work, not before.
ENABLED = False
PREREQUISITES = (
    ("R1", "bind every accepted run to staged inputs"),
    ("R2", "register scans and compare content, not timestamps"),
    ("R4", "preserve semantic conditions in fixers and standing approvals"),
)


class AutoAcceptError(ValueError):
    """Raised when auto-acceptance is refused or an application is stopped (the working copy is left as it was)."""


def refusal_message() -> str:
    return ("--auto-accept is not enabled: its prerequisites in docs/ROADMAP_IMPLEMENTATION_HANDOFF.md are not built ("
            + "; ".join(f"{key} {title}" for key, title in PREREQUISITES)
            + "). Use `escalation review` (report-only ELIGIBLE / NOT ELIGIBLE) and `escalation apply` after a person has looked.")


def require_enabled() -> None:
    if not ENABLED:
        raise AutoAcceptError(refusal_message())


def _sha(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def tool_identity(vanilla_core: str | None = None) -> dict:
    return {"bridgeforge": __version__, "python": platform.python_version(), "vanilla_core": vanilla_core}


def _check(name: str, status: str, reason: str, *, tool: dict | None = None, inputs: str | None = None,
           outputs: str | None = None, evidence: list | None = None, signal: bool = False) -> dict:
    return {"check": name, "status": status, "reason": reason, "tool": tool, "input_sha256": inputs, "output_sha256": outputs,
            "evidence": evidence or [], "signal": signal}


def load_policy(workspace: Path) -> tuple[dict | None, str | None]:
    path = Path(workspace).parent / POLICY_NAME
    if not path.is_file():
        return None, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, _sha(path)
    return (data if isinstance(data, dict) and isinstance(data.get("approved"), dict) else None), _sha(path)


def _finding_keys(findings: list[dict]) -> set[tuple[str, str, str]]:
    from bridgeforge.revive import _informational

    return {(f["id"], f.get("file") or "", (f.get("evidence") or [""])[0]) for f in findings if not _informational(f)}


def _is_code(name: str) -> bool:
    return "!" in name or name.lower().endswith(CODE_SUFFIXES)


def _scope_check(packet: dict, workspace: Path, changed: list[str], policy: dict | None, policy_sha: str | None) -> dict:
    from bridgeforge.automation import tier_for

    finding = packet["finding"]
    ids = set(packet.get("merged") or [finding])
    classes = {f.get("classification") for f in packet.get("findings") or []}
    if packet.get("kind") != "agent":
        return _check("scope", FAIL, f"packet kind is {packet.get('kind')!r}, not an agent packet")
    if classes & set(EXCLUDED_CLASSIFICATIONS):
        return _check("scope", FAIL, f"{'/'.join(sorted(classes & set(EXCLUDED_CLASSIFICATIONS)))} findings are never applied unattended")
    for fid in sorted(ids):
        if tier_for(fid) == "decision":
            return _check("scope", FAIL, f"`{fid}` is a decision-tier finding (owner or gameplay decision)")
        part = next((p for p in EXCLUDED_FINDING_PARTS if p in fid), None)
        if part:
            return _check("scope", FAIL, f"`{fid}` is save-migration or lifecycle work (matches '{part}'); a person reviews it")
    if policy is None:
        return _check("scope", FAIL, f"no standing auto-accept policy ({POLICY_NAME} in the queue folder) approves `{finding}`", inputs=policy_sha)
    try:
        mod_id = json.loads((Path(workspace) / "working" / "mod_info.json").read_text(encoding="utf-8")).get("id")
    except (OSError, ValueError, AttributeError):
        return _check("scope", INCOMPLETE, "working/mod_info.json is unreadable, so maintained third-party status is unknown", inputs=policy_sha)
    if mod_id in (policy.get("maintained_third_party_mods") or []):
        return _check("scope", FAIL, f"mod `{mod_id}` is listed as maintained third-party: wrapper plugins only, never in-place edits", inputs=policy_sha)
    missing = sorted(i for i in ids if i not in policy["approved"])
    if missing:
        return _check("scope", FAIL, "no standing approval for " + ", ".join(f"`{i}`" for i in missing), inputs=policy_sha)
    bad = []
    for fid in sorted(ids):
        rule = policy["approved"][fid] if isinstance(policy["approved"][fid], dict) else {}
        suffixes = tuple(s.lower() for s in rule.get("suffixes") or [])
        bad += [f"{n} (not {', '.join(suffixes) or 'any approved suffix'})" for n in changed if not suffixes or not n.lower().endswith(suffixes)]
        if len(changed) > int(rule.get("max_files") or 1):
            bad.append(f"{len(changed)} files changed, approval allows {int(rule.get('max_files') or 1)}")
    if bad:
        return _check("scope", FAIL, "outside the approved kind of change: " + "; ".join(sorted(set(bad))), inputs=policy_sha)
    return _check("scope", PASS, "approved kind of change for " + ", ".join(sorted(ids)), inputs=policy_sha)


def _regression_check(packet: dict, sandbox: Path, changed: list[str], policy: dict | None) -> dict:
    code = [n for n in changed if _is_code(n)]
    if not code:
        return _check("regression", NOT_APPLICABLE, "only data files changed (" + ", ".join(sorted({Path(n).suffix or n for n in changed})) + "); the rescan of the candidate is the regression check")
    rule = ((policy or {}).get("approved") or {}).get(packet["finding"])
    command = rule.get("regression") if isinstance(rule, dict) else None
    if not command:
        return _check("regression", INCOMPLETE, "code changed and no regression fixture is registered for this finding in the policy", evidence=code)
    try:
        done = subprocess.run(command, cwd=sandbox, capture_output=True, text=True, timeout=REGRESSION_TIMEOUT, check=False)
    except subprocess.TimeoutExpired:
        return _check("regression", INCOMPLETE, f"regression command timed out after {REGRESSION_TIMEOUT}s", tool={"command": command})
    except OSError as exc:
        return _check("regression", INCOMPLETE, f"regression command could not start: {exc}", tool={"command": command})
    out = (done.stdout + done.stderr)[-2000:]
    return _check("regression", PASS if done.returncode == 0 else FAIL, f"exit {done.returncode}", tool={"command": command},
                  outputs=hashlib.sha256(out.encode("utf-8")).hexdigest(), evidence=out.splitlines()[-5:])


def _compile_check(changed: list[str], before: list[dict], after: list[dict], vanilla: Path | None, tool: dict) -> dict:
    code = [n for n in changed if _is_code(n)]
    if not code:
        return _check("compile", NOT_APPLICABLE, "no code file changed (" + ", ".join(sorted({Path(n).suffix or n for n in changed})) + "): nothing to compile", tool=tool)
    shadow = [n for n in code if n.replace("\\", "/").startswith(("src/", "jars/src/", "jar/src/")) or "!" in n]
    if shadow:
        return _check("compile", INCOMPLETE, "jar source or packaged class edited: the packaged bytes are not rebuilt and checked here", tool=tool, evidence=shadow)
    if vanilla is None:
        return _check("compile", INCOMPLETE, "code changed and the packet has no vanilla core, so the compile check did not run", tool=tool)
    if any(f["id"] in COMPILE_SKIPPED_IDS for f in after):
        return _check("compile", INCOMPLETE, "the compile check was skipped (a compiler or dependency was unavailable)", tool=tool)
    keys = lambda fs: {(f["id"], f.get("file") or "", (f.get("evidence") or [""])[0]) for f in fs if f["id"] in COMPILE_ERROR_IDS}  # noqa: E731
    b, a = keys(before), keys(after)
    if a - b:
        return _check("compile", FAIL, f"{len(a - b)} new compile error(s)", tool=tool, outputs=_digest(sorted(a)), evidence=sorted(f"{i}|{f}" for i, f, _ in a - b)[:5])
    if a:
        return _check("compile", INCOMPLETE, f"{len(a)} pre-existing compile error(s) remain; they need bounded handling, not a waiver", tool=tool, outputs=_digest(sorted(a)))
    return _check("compile", PASS, f"compile errors {len(b)} -> 0 under the same tool", tool=tool, inputs=_digest(sorted(b)), outputs=_digest([]))


def bindings(workspace: Path, packet_name: str, sandbox: Path, changed: list[str]) -> dict:
    workspace = Path(workspace)
    policy_path = workspace.parent / POLICY_NAME
    return {"packet_sha256": _sha(workspace / "reports" / "escalations" / f"{packet_name}.json"), "policy_sha256": _sha(policy_path),
            "attempt": {n: _sha(sandbox / n) for n in changed}, "working": {n: _sha(workspace / "working" / n) for n in changed}}


def evaluate_attempt(packet: dict | None, workspace: Path, sandbox: Path, changed: list[str], flags: list[str],
                     diffs: dict[str, list[str]], *, before: list[dict] | None = None) -> dict:
    """Every gate for one attempt. `before` is a `revive._scan` of working/ (pass it to scan once)."""
    if packet is None:
        c = _check("packet", FAIL, "the packet file is gone (revive regenerates packets)")
        return _result([c], None, None)
    if not sandbox.is_dir() or not changed:
        c = _check("attempt", FAIL, "the attempt changed nothing" if sandbox.is_dir() else "the attempt folder has no working copy")
        return _result([c], None, None)
    from bridgeforge.automation import tier_for
    from bridgeforge.escalation.escalation import verify
    from bridgeforge.revive import _informational, _scan

    workspace = Path(workspace)
    policy, policy_sha = load_policy(workspace)
    vanilla = Path(packet["vanilla_core"]) if packet.get("vanilla_core") else None
    tool = tool_identity(str(vanilla) if vanilla else None)
    start = sandbox.parent / "START_TREE.json"
    input_hash = _digest({n: _sha(workspace / "working" / n) for n in changed})
    output_hash = _digest({n: _sha(sandbox / n) for n in changed})
    checks = [_scope_check(packet, workspace, changed, policy, policy_sha)]
    outside = [n for n in changed if n not in packet["allowed_files"]]
    checks.append(_check("allowed-files", FAIL if outside else PASS, ("outside allowed_files: " + ", ".join(outside)) if outside else "all inside allowed_files",
                         inputs=input_hash, outputs=output_hash))
    try:
        after = _scan(sandbox, vanilla)
        before = before if before is not None else _scan(workspace / "working", vanilla)
        check = verify(packet, sandbox, scanned=after)
    except Exception as exc:  # noqa: BLE001 - a scanner or parser failure must read as INCOMPLETE, never as a pass
        checks.append(_check("scan", INCOMPLETE, f"the scan failed: {type(exc).__name__}: {exc}", tool=tool))
        return _result(checks, bindings(workspace, packet["id"], sandbox, changed), None)
    verifier_ok = check["status"] == "PASS"
    checks.append(_check("verifier", PASS if verifier_ok else FAIL, "PASS" if verifier_ok else "; ".join(check["reasons"]), tool=tool,
                         inputs=output_hash, outputs=_digest(sorted(_finding_keys(after)))))
    before_keys, after_keys = _finding_keys(before), _finding_keys(after)
    targets = set(packet.get("merged") or [packet["finding"]])
    remaining = [k for k in after_keys if k[0] in targets and (not packet.get("file") or k[1] == packet["file"])]
    checks.append(_check("finding-gone", FAIL if remaining else PASS, f"{len(remaining)} remain" if remaining else "gone", tool=tool))
    fresh = after_keys - before_keys
    by_id = {f["id"]: f for f in after if not _informational(f)}
    # A tier of `none`, or a SAFE classification, does not excuse a MANUAL/UNKNOWN finding that is new.
    blocking = [k for k in sorted(fresh) if tier_for(k[0]) != "none" or (by_id.get(k[0]) or {}).get("classification") in EXCLUDED_CLASSIFICATIONS]
    checks.append(_check("no-new-findings", FAIL if blocking else PASS, ("new: " + ", ".join(f"{i} ({tier_for(i)})" for i, _, _ in blocking[:5])) if blocking else "none",
                         tool=tool, inputs=_digest(sorted(before_keys)), outputs=_digest(sorted(after_keys))))
    checks.append(_compile_check(changed, before, after, vanilla, tool))
    checks.append(_regression_check(packet, sandbox, changed, policy))
    added = sum(1 for lines in diffs.values() for line in lines if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for lines in diffs.values() for line in lines if line.startswith("-") and not line.startswith("---"))
    checks.append(_check("review-flags", FAIL if flags else PASS, ("flags: " + ", ".join(flags)) if flags else "no flag fired (a regex signal, not proof)", signal=True))
    checks.append(_check("deletions", PASS if removed <= added + DELETION_SLACK else FAIL, f"{removed} deleted, {added} added (limit added + {DELETION_SLACK}; a signal, not proof)", signal=True))
    delta = {"removed": [list(k[:2]) for k in sorted(before_keys - after_keys)], "added": [list(k[:2]) for k in sorted(fresh)]}
    stats = {"checked": vanilla is not None, "errors_before": sum(1 for f in before if f["id"] in COMPILE_ERROR_IDS),
             "errors_after": sum(1 for f in after if f["id"] in COMPILE_ERROR_IDS)}
    result = _result(checks, bindings(workspace, packet["id"], sandbox, changed), delta)
    result["compile"] = stats
    result["verify"] = check
    result["start_tree_present"] = start.is_file()
    return result


def _result(checks: list[dict], bound: dict | None, delta: dict | None) -> dict:
    bad = next((c for c in checks if c["status"] not in QUALIFYING), None)
    return {"eligible": bad is None, "failed": None if bad is None else f"{bad['check']} {bad['status']}: {bad['reason']}",
            "checks": checks, "bindings": bound, "scan_delta": delta, "compile": None, "verify": None}


# ---- application: lock, recheck, stage, journal, commit, roll back -------------------------------------------------

class workspace_apply_lock:
    """One application per workspace at a time (O_EXCL lock file naming the PID; a dead owner's lock is taken over)."""

    def __init__(self, workspace: Path):
        self.path = Path(workspace) / "scratch" / "escalations" / LOCK_NAME

    def __enter__(self):
        from bridgeforge.escalation.escalation import _pid_alive

        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                try:
                    pid = int(self.path.read_text(encoding="utf-8").split()[0])
                except (OSError, ValueError, IndexError):
                    pid = 0
                if pid and pid != os.getpid() and _pid_alive(pid):
                    raise AutoAcceptError(f"another application (PID {pid}) holds {self.path}") from None
                self.path.unlink(missing_ok=True)
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(f"{os.getpid()}\n")
            return self
        raise AutoAcceptError(f"could not take {self.path}")

    def __exit__(self, *exc):
        self.path.unlink(missing_ok=True)
        return False


def _safe_target(base: Path, name: str) -> Path:
    if Path(name).is_absolute() or ".." in Path(name).parts:
        raise AutoAcceptError(f"path escape refused: {name}")
    target = (base / name).resolve()
    if base.resolve() not in target.parents:
        raise AutoAcceptError(f"path escape refused: {name}")
    return target


def _journal_path(workspace: Path, packet_name: str) -> Path:
    return Path(workspace) / "scratch" / "escalations" / packet_name / JOURNAL_NAME


def _was_committed(entry: dict) -> bool:
    """True when the journal entry's replacement happened, even if the crash came before the journal recorded it."""
    target = Path(entry["target"])
    if entry["committed"]:
        return True
    if entry["after_sha"] is None:
        return entry["before_sha"] is not None and not target.exists()
    return entry["before_sha"] != entry["after_sha"] and _sha(target) == entry["after_sha"]


def recover(workspace: Path, packet_name: str) -> dict:
    """Roll back an application that stopped part way (a crash or an error): restore every file the journal shows
    as committed from its backup, remove stage files, then mark the journal ROLLED_BACK. Idempotent."""
    path = _journal_path(workspace, packet_name)
    if not path.is_file():
        return {"state": "NO_JOURNAL", "restored": []}
    journal = json.loads(path.read_text(encoding="utf-8"))
    if journal.get("state") in ("DONE", "ROLLED_BACK"):
        return {"state": journal["state"], "restored": []}
    restored = []
    for entry in journal["entries"]:
        target = Path(entry["target"])
        stage = Path(entry["stage"]) if entry.get("stage") else None
        if stage is not None:
            stage.unlink(missing_ok=True)
        if _was_committed(entry):
            if entry["backup"]:
                shutil.copyfile(entry["backup"], target)
                restored.append(entry["path"])
            elif entry["before_sha"] is None:
                target.unlink(missing_ok=True)
                restored.append(entry["path"])
    atomic_write_json(path, {**journal, "state": "ROLLED_BACK"})
    return {"state": "ROLLED_BACK", "restored": restored}


def apply_attempt(workspace: Path, packet: dict, attempt: int, assessment: dict, *, now=None) -> dict:
    """Apply an ELIGIBLE attempt: under the workspace lock, recheck every bound hash, stage all new content, journal,
    then commit file by file; any failure rolls everything back. Never called while `ENABLED` is False."""
    from bridgeforge.escalation.escalation import _keep_line_endings
    from bridgeforge.revive import append_ledger

    workspace = Path(workspace).expanduser().resolve()
    if not assessment.get("eligible") or not assessment.get("bindings"):
        raise AutoAcceptError("the attempt is not ELIGIBLE: " + str(assessment.get("failed")))
    sandbox = workspace / "scratch" / "escalations" / packet["id"] / f"attempt-{attempt}" / "working"
    working = workspace / "working"
    bound = assessment["bindings"]
    changed = sorted(bound["attempt"])
    with workspace_apply_lock(workspace):
        recover(workspace, packet["id"])  # an earlier interrupted application is undone first
        now_bound = bindings(workspace, packet["id"], sandbox, changed)
        for key in ("packet_sha256", "policy_sha256", "attempt", "working"):
            if now_bound[key] != bound[key]:
                raise AutoAcceptError(f"{key.split('_')[0]} changed since the attempt was assessed; nothing was applied")
        entries, payload, journal = [], {}, _journal_path(workspace, packet["id"])
        for name in changed:
            source, target = _safe_target(sandbox, name), _safe_target(working, name)
            before = target.read_bytes() if target.is_file() else b""
            new = _keep_line_endings(before, source.read_bytes()) if source.is_file() else None
            backup = target.with_name(f"{target.name}.pre-bf-escalation-{packet['id']}.bak") if target.is_file() else None
            stage = target.with_name(target.name + ".bf-stage") if new is not None else None
            payload[name] = new
            entries.append({"path": name, "target": str(target), "backup": str(backup) if backup else None, "stage": str(stage) if stage else None,
                            "before_sha": _sha(target), "after_sha": hashlib.sha256(new).hexdigest() if new is not None else None, "committed": False})
        try:
            for entry in entries:  # prepare: every backup and every stage file exists before anything is replaced
                if entry["backup"]:
                    shutil.copyfile(entry["target"], entry["backup"])
                if entry["stage"]:
                    Path(entry["target"]).parent.mkdir(parents=True, exist_ok=True)
                    Path(entry["stage"]).write_bytes(payload[entry["path"]])
            atomic_write_json(journal, {"state": "COMMITTING", "packet": packet["id"], "attempt": attempt, "entries": entries})
            for entry in entries:
                if entry["stage"]:
                    os.replace(entry["stage"], entry["target"])
                else:
                    Path(entry["target"]).unlink(missing_ok=True)
                entry["committed"] = True
                atomic_write_json(journal, {"state": "COMMITTING", "packet": packet["id"], "attempt": attempt, "entries": entries})
        except BaseException:
            atomic_write_json(journal, {"state": "COMMITTING", "packet": packet["id"], "attempt": attempt, "entries": entries})
            recover(workspace, packet["id"])
            raise
        atomic_write_json(journal, {"state": "DONE", "packet": packet["id"], "attempt": attempt, "entries": entries})
    append_ledger(workspace, {"packet": packet["id"], "finding": packet["finding"], "file": packet.get("file"), "tier": packet["tier"], "runner": "agent",
                              "attempt": attempt, "outcome": "APPLIED", "reasons": [], "changed": changed, "classification": "REVIEW",
                              "auto_accepted": True, "auto_accept_checks": {c["check"]: c["status"] for c in assessment["checks"]},
                              "auto_accept_bindings": bound, "live_accepted": False}, now)
    return {"written": [{"path": e["path"], "backup": e["backup"]} for e in entries]}
