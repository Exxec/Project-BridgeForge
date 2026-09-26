"""`bridgeforge escalation`: hand a packet to an AI agent in a throwaway copy, and trust only BridgeForge's verdict.

ROADMAP P15 item 3 (2026-09-26). `revive` writes the packets; this runs one:

1. Copy `<ws>/working` to `<ws>/scratch/escalations/<packet>/attempt-N/working` (the real copy is never
   touched while the agent works).
2. Run the agent command there with the packet as its prompt on stdin, and `BF_PACKET`, `BF_PROMPT`,
   `BF_NOTE` and `BF_WORKING` in its environment. Any agent works; for Claude Code, for example:
   `claude -p --permission-mode acceptEdits --allowedTools "Read,Edit,Write,Grep,Glob"`.
3. Judge the result without asking the agent:
   - every changed, added or deleted file must be in the packet's `allowed_files` (else REJECTED);
   - the agent must have written its note (what, why, evidence, behaviour change);
   - a fresh scan of the copy (with the compile check when the packet has a vanilla core) must show
     the packet's finding gone and no new finding of an actionable tier that wasn't there before.
4. Only a verified result is copied back, and only with `--apply` (backups kept as
   `.pre-bf-escalation-<packet>.bak`). A failure is retried with the failure text appended, up to
   `--retries` times. Every attempt goes into `reports/escalations/ledger.jsonl`, which
   `finding-stats` reads to find the fixes worth turning into deterministic fixers.

An agent-made change is REVIEW, never SAFE: it compiled and cleared the check, which is not proof of
behaviour. The live test stays the final gate.
"""
from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path

from .automation import ACTIONABLE, tier_for
from .revive import _scan, append_ledger, finding_key, render_packet

SCHEMA_VERSION = 1


class EscalationError(ValueError):
    """Raised for a missing workspace or packet, or a packet that cannot be run by an agent."""


def packets_dir(workspace: Path) -> Path:
    return Path(workspace).expanduser().resolve() / "reports" / "escalations"


def list_packets(workspace: Path) -> list[dict]:
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(packets_dir(workspace).glob("*.json"))]


def load_packet(workspace: Path, packet: str) -> dict:
    path = packets_dir(workspace) / f"{packet}.json"
    if not path.is_file():
        raise EscalationError(f"No packet {packet} under {packets_dir(workspace)} (run `bridgeforge revive` first).")
    return json.loads(path.read_text(encoding="utf-8"))


def _tree(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and ".pre-bf-" not in p.name}


def changed_files(before: Path, after: Path) -> list[str]:
    old, new = _tree(before), _tree(after)
    return sorted(name for name in set(old) | set(new) if old.get(name) != new.get(name))


def verify(packet: dict, working: Path) -> dict:
    """Did the packet's finding go away, without new actionable findings? Scans `working` afresh."""
    vanilla = Path(packet["vanilla_core"]) if packet.get("vanilla_core") else None
    findings = _scan(working, vanilla)
    target_file = packet.get("file") or ""
    remaining = [f for f in findings if f["id"] == packet["finding"] and (not target_file or (f.get("file") or "") == target_file)]
    baseline = set(packet.get("baseline_keys") or [])
    new = sorted({"|".join(finding_key(f)) for f in findings if tier_for(f["id"]) in ACTIONABLE} - baseline)
    stale = sorted(name for name, digest in (packet.get("file_sha256") or {}).items()
                   if working.joinpath(name).is_file() and digest and hashlib.sha256(working.joinpath(name).read_bytes()).hexdigest() != digest)
    reasons = []
    if remaining:
        reasons.append(f"{len(remaining)} `{packet['finding']}` finding(s) remain: " + "; ".join((f.get("evidence") or [f["explanation"]])[0] for f in remaining[:3]))
    if new:
        reasons.append("new findings appeared: " + ", ".join(new[:10]))
    return {"status": "PASS" if not reasons else "FAIL", "reasons": reasons, "remaining": len(remaining), "new_findings": new,
            "compile_checked": vanilla is not None, "changed_since_packet": stale}


def _copy_back(packet: dict, sandbox: Path, working: Path, changed: list[str]) -> list[dict]:
    written = []
    for name in changed:
        source, target = sandbox / name, working / name
        backup = None
        if target.is_file():
            backup = target.with_name(f"{target.name}.pre-bf-escalation-{packet['id']}.bak")
            shutil.copyfile(target, backup)
        if source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        elif target.is_file():
            target.unlink()
        written.append({"path": name, "backup": str(backup) if backup else None})
    return written


def run_packet(workspace: Path, packet_name: str, agent: str | list[str], *, apply: bool = False, retries: int = 1,
               timeout: int = 1800, now=None) -> dict:
    workspace = Path(workspace).expanduser().resolve()
    packet = load_packet(workspace, packet_name)
    if packet["kind"] != "agent":
        raise EscalationError(f"{packet_name} is an owner packet ({packet['tier']}): it needs a decision, not an agent.")
    working = workspace / "working"
    command = shlex.split(agent) if isinstance(agent, str) else list(agent)
    if not command:
        raise EscalationError("No agent command given.")
    attempts, feedback = [], ""
    for number in range(1, retries + 2):
        attempt_dir = workspace / "scratch" / "escalations" / packet["id"] / f"attempt-{number}"
        if attempt_dir.exists():
            shutil.rmtree(attempt_dir)
        sandbox = attempt_dir / "working"
        shutil.copytree(working, sandbox, ignore=shutil.ignore_patterns("*.pre-bf-*"))
        shown = {**packet, "verify": f'{packet["verify"]} --working "{sandbox}"'}
        prompt = render_packet(shown).replace(str(workspace / "working"), str(sandbox)) + feedback
        (attempt_dir / "PROMPT.md").write_text(prompt, encoding="utf-8")
        note = attempt_dir / "NOTE.md"
        env = {**os.environ, "BF_PACKET": str(packets_dir(workspace) / f"{packet['id']}.json"), "BF_PROMPT": str(attempt_dir / "PROMPT.md"),
               "BF_NOTE": str(note), "BF_WORKING": str(sandbox)}
        try:
            completed = subprocess.run(command, cwd=sandbox, input=prompt, env=env, capture_output=True, text=True, timeout=timeout, check=False)
            agent_rc, agent_tail = completed.returncode, (completed.stdout + completed.stderr)[-4000:]
        except subprocess.TimeoutExpired:
            agent_rc, agent_tail = None, f"agent timed out after {timeout}s"
        except OSError as exc:
            raise EscalationError(f"Could not start the agent command {command[0]!r}: {exc}") from exc
        (attempt_dir / "AGENT_OUTPUT.txt").write_text(agent_tail, encoding="utf-8")
        changed = changed_files(working, sandbox)
        outside = [name for name in changed if name not in packet["allowed_files"]]
        reasons: list[str] = []
        check: dict = {}
        if outside:
            outcome = "REJECTED"
            reasons.append("changed files outside the packet: " + ", ".join(outside))
        elif not changed:
            outcome = "FAILED"
            reasons.append("the agent changed nothing" + (f" (exit {agent_rc})" if agent_rc else ""))
        else:
            check = verify(packet, sandbox)
            reasons += check["reasons"]
            if not note.is_file() or not note.read_text(encoding="utf-8", errors="replace").strip():
                reasons.append("no note written to $BF_NOTE (what changed, why, evidence, behaviour change)")
            outcome = "VERIFIED" if not reasons else "FAILED"
        written = _copy_back(packet, sandbox, working, changed) if outcome == "VERIFIED" and apply else []
        if written:
            outcome = "APPLIED"
            shutil.copyfile(note, packets_dir(workspace) / f"{packet['id']}.NOTE.txt")
        entry = {"packet": packet["id"], "finding": packet["finding"], "file": packet.get("file"), "tier": packet["tier"], "runner": "agent",
                 "attempt": number, "outcome": outcome, "reasons": reasons, "changed": changed, "agent_exit": agent_rc,
                 "classification": "REVIEW" if outcome in ("VERIFIED", "APPLIED") else None}
        append_ledger(workspace, entry, now)
        attempts.append({**entry, "attempt_dir": str(attempt_dir), "verify": check})
        if outcome in ("VERIFIED", "APPLIED", "REJECTED"):
            break
        feedback = "\n## Previous attempt failed\n\nBridgeForge rejected the last attempt:\n" + "".join(f"- {r}\n" for r in reasons) + "\nStart again from the unchanged files.\n"
    final = attempts[-1]
    return {"schema_version": SCHEMA_VERSION, "mode": "ESCALATION_RUN", "packet": packet["id"], "outcome": final["outcome"],
            "applied": final["outcome"] == "APPLIED", "attempts": attempts,
            "note": "Verified agent changes are REVIEW: they cleared the finding and the scan (and compile check, if any), not a live test."}
