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
import re
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


START_TREE_FILE = "START_TREE.json"


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


def resolve_agent_command(agent: str, home: Path | None = None) -> str:
    """`claude ...` with no `claude` on PATH: use the VS Code extension's bundled binary (ROADMAP P15 item 20.13).

    The first escalation run (2026-09-27) found `claude` missing from PATH on a machine where the extension
    ships `~/.vscode/extensions/anthropic.claude-code-<version>/resources/native-binary/claude(.exe)`. The newest
    extension folder wins. Any other command, or a `claude` already on PATH, is returned unchanged.
    """
    parts = agent.strip().split(None, 1)
    if not parts or parts[0].lower() not in ("claude", "claude.exe") or shutil.which(parts[0]):
        return agent
    extensions = (home or Path.home()) / ".vscode" / "extensions"
    binary = "claude.exe" if os.name == "nt" else "claude"
    def version(path: Path) -> tuple[int, ...]:
        match = re.match(r"anthropic\.claude-code-([\d.]+)", path.parents[2].name)
        return tuple(int(n) for n in match.group(1).split(".") if n) if match else ()

    found = sorted(extensions.glob(f"anthropic.claude-code-*/resources/native-binary/{binary}"), key=version) if extensions.is_dir() else []
    if not found:
        return agent
    return f'"{found[-1]}"' + (f" {parts[1]}" if len(parts) > 1 else "")


def _keep_line_endings(before: bytes, after: bytes) -> bytes:
    """The original's CRLF endings back on an agent's LF-only text edit (ROADMAP P15 item 20.14: the agent turned
    CRLF into LF, so every line showed as changed). Binary or undecodable content is returned unchanged."""
    if b"\r\n" not in before or b"\r\n" in after or b"\x00" in after[:8192]:
        return after
    try:
        text = after.decode("utf-8")
    except UnicodeDecodeError:
        return after
    return text.replace("\n", "\r\n").encode("utf-8")


def _copy_back(packet: dict, sandbox: Path, working: Path, changed: list[str]) -> list[dict]:
    written = []
    for name in changed:
        source, target = sandbox / name, working / name
        backup = None
        before = target.read_bytes() if target.is_file() else b""
        if target.is_file():
            backup = target.with_name(f"{target.name}.pre-bf-escalation-{packet['id']}.bak")
            shutil.copyfile(target, backup)
        if source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(_keep_line_endings(before, source.read_bytes()))
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
    if isinstance(agent, str):
        agent = resolve_agent_command(agent)
        # Windows parses its own command lines (backslashed paths); POSIX needs the split.
        command = [agent] if os.name == "nt" and agent.strip() else shlex.split(agent)
    else:
        command = list(agent)
    if not command:
        raise EscalationError("No agent command given.")
    attempts, feedback = [], ""
    for number in range(1, retries + 2):
        attempt_dir = workspace / "scratch" / "escalations" / packet["id"] / f"attempt-{number}"
        if attempt_dir.exists():
            shutil.rmtree(attempt_dir)
        sandbox = attempt_dir / "working"
        shutil.copytree(working, sandbox, ignore=shutil.ignore_patterns("*.pre-bf-*"))
        # The sandbox's starting state, so a later apply compares the attempt with its own start, not with a
        # working/ that other packets have changed since (ROADMAP P15 31.8, Angry Periphery 2026-09-28).
        (attempt_dir / START_TREE_FILE).write_text(json.dumps(_tree(sandbox)), encoding="utf-8")
        shown = {**packet, "verify": f'{packet["verify"]} --working "{sandbox}"'}
        prompt = render_packet(shown).replace(str(workspace / "working"), str(sandbox)) + feedback
        (attempt_dir / "PROMPT.md").write_text(prompt, encoding="utf-8")
        note = attempt_dir / "NOTE.md"
        env = {**os.environ, "BF_PACKET": str(packets_dir(workspace) / f"{packet['id']}.json"), "BF_PROMPT": str(attempt_dir / "PROMPT.md"),
               "BF_NOTE": str(note), "BF_WORKING": str(sandbox)}
        try:
            completed = subprocess.run(command[0] if os.name == "nt" and isinstance(agent, str) else command, cwd=sandbox, input=prompt, env=env, capture_output=True, text=True, timeout=timeout, check=False)
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


def apply_verified(workspace: Path, packet_name: str, *, attempt: int | None = None, now=None) -> dict:
    """Copy an attempt already VERIFIED into `working/` without re-running the agent (P15 item 20.12).

    `run --apply` re-runs the agent and applies whatever the new attempt produces, which nobody has
    reviewed (item 21: Yunru's reviewed attempt had to be copied by hand). This takes the newest attempt the
    ledger records as VERIFIED (or `attempt`), refuses when the packet's files changed since the packet or
    the attempt touched files outside it, re-verifies the attempt's copy, and copies back with backups.
    """
    import json

    workspace = Path(workspace).expanduser().resolve()
    packet = load_packet(workspace, packet_name)
    ledger = workspace / "reports" / "escalations" / "ledger.jsonl"
    verified = []
    if ledger.is_file():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("packet") == packet["id"] and entry.get("outcome") == "VERIFIED":
                verified.append(int(entry.get("attempt") or 0))
    if attempt is None:
        if not verified:
            raise EscalationError(f"{packet['id']} has no VERIFIED attempt in the ledger; run it first.")
        attempt = max(verified)
    elif attempt not in verified:
        raise EscalationError(f"attempt {attempt} of {packet['id']} is not recorded as VERIFIED.")
    sandbox = workspace / "scratch" / "escalations" / packet["id"] / f"attempt-{attempt}" / "working"
    if not sandbox.is_dir():
        raise EscalationError(f"{sandbox} is gone; run the packet again.")
    working = workspace / "working"
    stale = sorted(name for name, digest in (packet.get("file_sha256") or {}).items()
                   if working.joinpath(name).is_file() and digest and hashlib.sha256(working.joinpath(name).read_bytes()).hexdigest() != digest)
    if stale:
        raise EscalationError("working/ changed since the packet was made (" + ", ".join(stale) + "); run the packet again.")
    start_file = sandbox.parent / START_TREE_FILE
    if start_file.is_file():
        start, now_tree, current = json.loads(start_file.read_text(encoding="utf-8")), _tree(sandbox), _tree(working)
        changed = sorted(name for name in set(start) | set(now_tree) if start.get(name) != now_tree.get(name))
        moved_on = [name for name in changed if current.get(name) != start.get(name)]
        if moved_on:
            raise EscalationError("working/ changed these files since the attempt started (" + ", ".join(moved_on) + "); run the packet again.")
    else:
        changed = changed_files(working, sandbox)  # attempts made before START_TREE.json existed
    outside = [name for name in changed if name not in packet["allowed_files"]]
    if outside:
        raise EscalationError("the attempt changed files outside the packet: " + ", ".join(outside))
    if not changed:
        raise EscalationError("the attempt matches working/ already; nothing to apply.")
    check = verify(packet, sandbox)
    if check["status"] != "PASS":
        raise EscalationError("the attempt no longer verifies: " + "; ".join(check["reasons"]))
    written = _copy_back(packet, sandbox, working, changed)
    note = sandbox.parent / "NOTE.md"
    if note.is_file():
        shutil.copyfile(note, packets_dir(workspace) / f"{packet['id']}.NOTE.txt")
    append_ledger(workspace, {"packet": packet["id"], "finding": packet["finding"], "file": packet.get("file"), "tier": packet["tier"],
                              "runner": "agent", "attempt": attempt, "outcome": "APPLIED", "reasons": [], "changed": changed,
                              "classification": "REVIEW", "applied_without_rerun": True}, now)
    return {"schema_version": SCHEMA_VERSION, "mode": "ESCALATION_APPLY", "packet": packet["id"], "attempt": attempt,
            "written": written, "verify": check}
