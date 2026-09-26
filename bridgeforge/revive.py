"""`bridgeforge revive`: run the mechanical part of a revival unattended, and package the rest (ROADMAP P15 item 2).

Given a workspace (`<ws>/working/mod_info.json`), it loops: scan (with the loose-script compile check
when `--vanilla-core` is given), apply every fixer it is allowed to apply, rescan, until a round
changes nothing. What remains becomes **escalation packets** under `<ws>/reports/escalations/`:

- `agent` packets (tiers `code`, `mechanical`, `inspect`): one per finding id and file. Each holds the
  finding and its evidence, the only files that may change, a numbered excerpt of the file around
  the lines the evidence names, the vanilla/tooling hints for that finding family, and the exact
  check that decides "done" (`bridgeforge escalation verify`). They are written for an AI to work
  on without reading anything else, and BridgeForge, not the AI, decides whether the work passed.
- `owner` packets (tiers `decision`, `input`, and fixers awaiting approval): the question, the
  evidence, and for a fixer its dry-run diff.

What it may apply without asking: a fixer whose findings are all classified SAFE. Anything else
(REVIEW, MANUAL, UNKNOWN) needs approval, either per run (`--approve ID`) or standing, in the queue's
`AUTOMATION_POLICY.json` ("decide once, apply everywhere"). MANUAL and UNKNOWN findings are never
fixed without one of those. `working/` changes only with `--apply`; reports are always written.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict
from pathlib import Path

from .automation import ACTIONABLE, bucket, tier_for
from .fixers import SUPPORTED_FINDINGS, FixerError, apply_fix, compute_fix, unified_diff_for_change

SCHEMA_VERSION = 1
DEFAULT_TARGET = "0.98a-RC8"
POLICY_NAME = "AUTOMATION_POLICY.json"
AGENT_TIERS = {"code", "mechanical", "inspect", "unclassified"}
EXCERPT_CONTEXT = 40
EXCERPT_MAX_LINES = 400
_LINE_REFS = re.compile(r"(?::|\bline )(\d{1,6})\b")

# Where to look for evidence, per finding family. Packets carry these so an agent starts from the
# right BridgeForge command instead of guessing at the game's API.
HINTS = {
    "removed-api-call": "The replacement is named in the finding. `bridgeforge api-diff` lists what RC8 removed or changed; RevenantLib's bf.legacyfleets/bf.legacyworld hold shims for 0.6 world-gen and fleet calls.",
    "legacy-vanilla-class-import": "Find the RC8 successor with `bridgeforge api-diff` or `javap -cp starfarer.api.jar`; never guess a class name.",
    "loose-script-compile-error": "The javac errors are the evidence. Janino compiles loose scripts at runtime: no generics inference beyond Java 5-era, no lambdas, no enhanced switch.",
    "loose-script-janino-risk": "Janino (the game's runtime compiler for data/**.java) rejects generics use it cannot infer, lambdas and newer syntax; rewrite in Java 5-era syntax.",
    "target-interface-method-missing": "Add the RC8-required method with the base class's default behaviour; do not change existing bodies.",
    "configured-source-class-missing-from-jar": "A CSV/JSON names a class that is neither in a jar nor compiled loose. Check `bridgeforge verify-shadow` and the mod's own src/.",
    "content-reference-unresolved": "`bridgeforge dependency-substitutes` and `vendor-plan` show which mod defines the id; `content-diff` whether vanilla removed it.",
    "content-reference-removed-in-vanilla": "Vanilla removed these ids; choose a replacement id or drop the reference (an expected change).",
}
RULES = (
    "Edit only the files listed under 'Files you may change'. Anything else is rejected.",
    "Make the smallest change that resolves the finding. Do not delete or stub out behaviour to make a finding disappear; if removal is the right fix, say so in the note as an expected change.",
    "Every claim about the game or its API needs evidence (javap output, a vanilla file, a log line); cite it in the note.",
    "Write the note to the path in $BF_NOTE: what you changed, why, the evidence, and any behaviour change a player would notice.",
    "BridgeForge re-verifies your work: the finding must be gone and no new MANUAL/UNKNOWN finding may appear. Compiling is not proof of behaviour, so the result is labelled REVIEW.",
)


class ReviveError(ValueError):
    """Raised for a workspace without a working copy, or an unreadable policy file."""


def _now(now=None) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now if now is not None else time.time()))


def load_policy(path: Path | None) -> dict:
    if path is None or not path.is_file():
        return {"approved_fixers": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReviveError(f"{path}: {exc}") from exc
    return {"approved_fixers": dict(data.get("approved_fixers") or {})}


def _scan(working: Path, vanilla_core: Path | None) -> list[dict]:
    from .scanner import scan_mod

    return [asdict(f) for f in scan_mod(working, vanilla_core=vanilla_core, compile_check=vanilla_core is not None).findings]


def finding_key(finding: dict) -> tuple[str, str]:
    return finding["id"], finding.get("file") or ""


def packet_id(finding_id: str, file: str) -> str:
    suffix = hashlib.sha1(file.encode("utf-8")).hexdigest()[:8] if file else "mod"
    return f"{finding_id}--{suffix}"


def _fix_options(finding_id: str, working: Path, target: str, vanilla_core: Path | None, findings: list[dict]) -> list[dict]:
    base = {"target_game_version": target, "vanilla_core": vanilla_core}
    if finding_id == "faction-known-lists-missing":
        return [{**base, "faction_file": working / f["file"]} for f in findings if f.get("file")]
    return [base]


def _try_fixers(working: Path, findings: list[dict], *, target: str, vanilla_core: Path | None, approved: set[str], apply: bool) -> tuple[list[dict], list[dict]]:
    """Compute every supported fixer; apply the permitted ones. Returns (applied, not applied)."""
    applied, pending = [], []
    by_id: dict[str, list[dict]] = {}
    for finding in findings:
        by_id.setdefault(finding["id"], []).append(finding)
    for finding_id in sorted(by_id):
        if finding_id not in SUPPORTED_FINDINGS or tier_for(finding_id) != "auto":
            continue
        group = by_id[finding_id]
        classifications = sorted({f["classification"] for f in group})
        unattended = classifications == ["SAFE"]
        permitted = unattended or finding_id in approved
        for options in _fix_options(finding_id, working, target, vanilla_core, group):
            try:
                plan = compute_fix(working, finding_id, options)
            except FixerError as exc:
                pending.append({"finding": finding_id, "state": "FIXER_REFUSED", "reason": str(exc), "classifications": classifications})
                continue
            diff = "".join(unified_diff_for_change(change) for change in plan.changes)
            files = sorted(str(change.path.relative_to(working).as_posix()) for change in plan.changes)
            if permitted and apply:
                apply_fix(plan)
                applied.append({"finding": finding_id, "files": files, "why": "all SAFE" if unattended else "approved"})
            else:
                pending.append({"finding": finding_id, "state": "READY_NOT_APPLIED" if permitted else "AWAITING_APPROVAL",
                                "files": files, "diff": diff, "classifications": classifications})
    return applied, pending


def _excerpt(path: Path, evidence: list[str]) -> str:
    try:
        lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    except OSError:
        return ""
    wanted = sorted({int(n) for text in evidence for n in _LINE_REFS.findall(text) if 0 < int(n) <= len(lines)})
    if not wanted and len(lines) <= EXCERPT_MAX_LINES:
        shown = range(1, len(lines) + 1)
    else:
        keep = {n for line in (wanted or [1]) for n in range(max(1, line - EXCERPT_CONTEXT), min(len(lines), line + EXCERPT_CONTEXT) + 1)}
        shown = sorted(keep)[:EXCERPT_MAX_LINES]
    out, previous = [], 0
    for number in shown:
        if previous and number != previous + 1:
            out.append("     ...")
        out.append(f"{number:5d}  {lines[number - 1]}")
        previous = number
    return "\n".join(out)


def _sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def build_packets(workspace: Path, findings: list[dict], pending_fixes: list[dict], *, vanilla_core: Path | None, now=None) -> list[dict]:
    working = workspace / "working"
    baseline = sorted({"|".join(finding_key(f)) for f in findings})
    packets = []
    fixer_state = {item["finding"]: item for item in pending_fixes}
    groups: dict[tuple[str, str], list[dict]] = {}
    for finding in findings:
        tier = tier_for(finding["id"])
        if tier not in ACTIONABLE:
            continue
        per_file = tier in AGENT_TIERS and finding.get("file")
        groups.setdefault((finding["id"], (finding.get("file") or "") if per_file else ""), []).append(finding)
    for (finding_id, file), group in sorted(groups.items()):
        tier = tier_for(finding_id)
        fix = fixer_state.get(finding_id)
        files = sorted({f["file"] for f in group if f.get("file")})
        kind = "agent" if tier in AGENT_TIERS and files else "owner"
        if fix is not None and fix["state"] != "FIXER_REFUSED":
            kind = "owner"  # the fix exists; it needs a yes, not a new fix
        packet = {
            "schema_version": SCHEMA_VERSION, "id": packet_id(finding_id, file), "created": _now(now),
            "workspace": str(workspace), "finding": finding_id, "tier": tier, "kind": kind, "file": file or None,
            "findings": group, "allowed_files": files if kind == "agent" else [],
            "file_sha256": {name: _sha256(working / name) for name in files},
            "baseline_keys": baseline, "vanilla_core": str(vanilla_core) if vanilla_core else None,
            "hint": HINTS.get(finding_id), "fixer": fix,
            "verify": f'bridgeforge escalation verify "{workspace}" {packet_id(finding_id, file)}',
            "excerpts": {name: _excerpt(working / name, [e for f in group for e in f.get("evidence") or []]) for name in files} if kind == "agent" else {},
        }
        packets.append(packet)
    return packets


def render_packet(packet: dict) -> str:
    """The packet as a self-contained prompt (agent) or question (owner)."""
    head = packet["findings"][0]
    lines = [f"# Escalation {packet['id']}", "",
             f"- Finding: `{packet['finding']}` ({head['classification']}, {head['severity']}, confidence {head['confidence']}), tier `{packet['tier']}`",
             f"- For: {'an AI agent, verified by BridgeForge' if packet['kind'] == 'agent' else 'the owner'}",
             f"- Mod working copy: `{packet['workspace']}/working`", "", "## What the scanner found", "", head["explanation"], ""]
    for finding in packet["findings"]:
        if finding.get("file"):
            lines.append(f"- `{finding['file']}`")
        lines += [f"  - {item}" for item in (finding.get("evidence") or [])[:30]]
    if packet.get("hint"):
        lines += ["", "## Where to look", "", packet["hint"]]
    fix = packet.get("fixer")
    if fix and fix.get("diff"):
        state = {"AWAITING_APPROVAL": "A fixer can do this, but its findings are not all SAFE, so it needs your approval.",
                 "READY_NOT_APPLIED": "A permitted fixer is ready; rerun with --apply."}[fix["state"]]
        lines += ["", "## Proposed fix", "", state,
                  f"Approve once: `bridgeforge revive <ws> --apply --approve {packet['finding']}`, or for every mod, add it to `{POLICY_NAME}` in the queue folder.",
                  "", "```diff", fix["diff"].rstrip(), "```"]
    elif fix and fix["state"] == "FIXER_REFUSED":
        lines += ["", "## Fixer refused", "", fix["reason"]]
    if packet["kind"] == "agent":
        lines += ["", "## Files you may change", ""] + [f"- `{name}`" for name in packet["allowed_files"]]
        for name, excerpt in packet["excerpts"].items():
            if excerpt:
                lines += ["", f"## `{name}` (numbered excerpt)", "", "```java" if name.endswith(".java") else "```", excerpt, "```"]
        lines += ["", "## Rules", ""] + [f"{n}. {rule}" for n, rule in enumerate(RULES, 1)]
        lines += ["", "## Done means", "", f"`{packet['verify']}` passes: no `{packet['finding']}` finding remains"
                  + (f" on `{packet['file']}`" if packet["file"] else "") + ", and no new finding of tier decision/inspect/code appears."]
    else:
        lines += ["", "## Decision needed", "",
                  "Record the answer so it applies next time: a fixer approval in the queue's AUTOMATION_POLICY.json, a dependency or content choice in the mod's REVIVAL_PLAN.md, then rerun `bridgeforge revive`."]
    return "\n".join(lines) + "\n"


def _write_packets(workspace: Path, packets: list[dict]) -> Path:
    folder = workspace / "reports" / "escalations"
    folder.mkdir(parents=True, exist_ok=True)
    for old in list(folder.glob("*.json")) + list(folder.glob("*.md")):
        old.unlink()  # packets are regenerated each run; the ledger (jsonl) is history and stays
    for packet in packets:
        (folder / f"{packet['id']}.json").write_text(json.dumps(packet, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (folder / f"{packet['id']}.md").write_text(render_packet(packet), encoding="utf-8")
    return folder


def append_ledger(workspace: Path, entry: dict, now=None) -> None:
    ledger = workspace / "reports" / "escalations" / "ledger.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"at": _now(now), **entry}, ensure_ascii=False) + "\n")


def revive(workspace: Path, *, target: str = DEFAULT_TARGET, vanilla_core: Path | None = None, policy_path: Path | None = None,
           approve: list[str] | None = None, apply: bool = False, max_rounds: int = 5, write: bool = True, now=None) -> dict:
    workspace = Path(workspace).expanduser().resolve()
    working = workspace / "working"
    if not (working / "mod_info.json").is_file():
        raise ReviveError(f"{workspace} has no working/mod_info.json; revive works on a workspace copy, never the input mod.")
    if working.is_symlink():
        raise ReviveError(f"{working} is a link; revive edits only a physical working copy.")
    policy_path = policy_path if policy_path is not None else workspace.parent / POLICY_NAME
    policy = load_policy(policy_path)
    approved = set(approve or []) | set(policy["approved_fixers"])
    rounds, applied_all = [], []
    findings = _scan(working, vanilla_core)
    first = [dict(f) for f in findings]
    pending: list[dict] = []
    for number in range(1, max_rounds + 1):
        applied, pending = _try_fixers(working, findings, target=target, vanilla_core=vanilla_core, approved=approved, apply=apply)
        rounds.append({"round": number, "applied": applied, "findings": len(findings)})
        applied_all += applied
        if not applied:
            break
        findings = _scan(working, vanilla_core)
    remaining_tiers = [tier_for(f["id"]) for f in findings]
    packets = build_packets(workspace, findings, pending, vanilla_core=vanilla_core, now=now)
    hardest = bucket(remaining_tiers)
    if hardest in ("none",):
        status = "UNATTENDED_DONE"
    elif hardest == "auto":
        status = "FIXES_PENDING"  # only fixable findings left: approve them, or rerun with --apply
    else:
        status = "ESCALATED"
    result = {
        "schema_version": SCHEMA_VERSION, "mode": "REVIVE", "workspace": str(workspace), "apply": apply, "target": target,
        "compile_checked": vanilla_core is not None, "policy": str(policy_path), "approved": sorted(approved),
        "status": status, "hardest_tier": hardest, "rounds": rounds, "applied": applied_all,
        "findings_before": len(first), "findings_after": len(findings),
        "packets": [{"id": p["id"], "kind": p["kind"], "tier": p["tier"], "finding": p["finding"], "file": p["file"]} for p in packets],
        "next": "Live test (the probe) after UNATTENDED_DONE; `bridgeforge escalation run` for agent packets; owner packets need a decision.",
    }
    if write:
        from .report import write_artifacts
        from .scanner import scan_mod

        _write_packets(workspace, packets)
        for item in applied_all:
            append_ledger(workspace, {"packet": None, "finding": item["finding"], "files": item["files"], "runner": "fixer", "outcome": "APPLIED"}, now)
        stamp = time.strftime("%Y-%m-%d-%H%M%S", time.gmtime(now if now is not None else time.time()))
        if apply and applied_all:
            write_artifacts(scan_mod(working, vanilla_core=vanilla_core, compile_check=vanilla_core is not None), workspace / "reports" / f"scan-{stamp}-revive")
        run_dir = workspace / "reports" / "revive"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "REVIVE.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (run_dir / "REVIVE.md").write_text(render(result), encoding="utf-8")
    return result


def render(result: dict) -> str:
    lines = [f"# Revive: {Path(result['workspace']).name}", "", f"Status: **{result['status']}** (hardest remaining tier: {result['hardest_tier']})",
             f"Findings: {result['findings_before']} -> {result['findings_after']}; compile check: {'yes' if result['compile_checked'] else 'no (pass --vanilla-core)'}; "
             f"{'applied' if result['apply'] else 'dry run'}", ""]
    for item in result["applied"]:
        lines.append(f"- fixed `{item['finding']}` ({item['why']}): {', '.join(item['files'])}")
    agent = [p for p in result["packets"] if p["kind"] == "agent"]
    owner = [p for p in result["packets"] if p["kind"] == "owner"]
    if agent:
        lines += ["", f"## For an AI agent ({len(agent)})", ""] + [f"- {p['id']} ({p['tier']}): `{p['file']}`" for p in agent]
    if owner:
        lines += ["", f"## For the owner ({len(owner)})", ""] + [f"- {p['id']} ({p['tier']})" for p in owner]
    lines += ["", result["next"]]
    return "\n".join(lines) + "\n"
