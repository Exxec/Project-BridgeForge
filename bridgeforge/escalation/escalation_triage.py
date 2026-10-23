"""`bridgeforge escalation triage`: the open decision packets of a queue, grouped by the decision they wait on (ROADMAP 80.7).

`escalation queue` counts what blocks each finding id and `escalation sheet` asks one question per shape. Triage groups
every open decision finding by (finding id, file pattern, normalized evidence): mods in one group wait on the same kind of
decision, so one ruling, or one `escalation accept` per mod, settles them. Per group it gives the mods the decision settles
(`decision_only`: all their open decisions are in this group; `cleared`: and no other packet still blocks them), the shared
evidence, earlier standing rulings that match or nearly match (ROADMAP 73 R4), and ready-to-run commands for the owner.
Commands are printed, never run. Read-only; `--write DIR` writes ESCALATION_TRIAGE.json and .md into DIR, not the queue.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path, PurePosixPath

from bridgeforge.baseline import finding_dict_baseline_key, mod_baseline_keys
from bridgeforge.escalation.escalation_precedent import invalid_ids, load_log, load_rulings, predicate_hash, predicate_problem, question_predicate, question_shape
from bridgeforge.report_status import is_closed
from bridgeforge.safeio import atomic_write_text

SCHEMA_VERSION = 1
RESULT_JSON = "ESCALATION_TRIAGE.json"
RESULT_MD = "ESCALATION_TRIAGE.md"
NEAR_THRESHOLD = 0.5  # Jaccard similarity of two rulings' evidence shapes
NEAR_LIMIT = 3
EVIDENCE_SHOWN = 5
SUMMARY_LINES = 10
NO_FILE_PATTERN = "(mod-wide)"
REASON_PLACEHOLDER = "<why it is right as written, with the evidence>"


def file_pattern(file: str) -> str:
    """`*.json` for `data/config/x.json`: the kind of file a finding sits in, not the mod's own path."""
    if not file:
        return NO_FILE_PATTERN
    suffix = PurePosixPath(file.replace("\\", "/")).suffix
    return f"*{suffix}" if suffix else "(no extension)"


def shape_set(items: list[str]) -> frozenset[str]:
    """Evidence items with ids, paths and numbers turned into placeholders (`weapon:<ID> (<N> file(s))`), so mods missing
    the same kind of thing share a group. The raw items stay in each mod's packet."""
    return frozenset(question_shape(str(item)) for item in items)


def _workspaces(queue: Path) -> list[Path]:
    return sorted(p for p in queue.iterdir() if p.is_dir() and not p.name.startswith("_")
                  and (p / "reports" / "revive" / "REVIVE.json").is_file() and not is_closed(p))


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _workspace_blockers(workspace: Path) -> dict | None:
    """An ESCALATED workspace's open decision findings by finding id, and whether it has a non-decision packet (which no
    decision clears). None when the workspace is not ESCALATED or its REVIVE.json cannot be read."""
    revive = _read_json(workspace / "reports" / "revive" / "REVIVE.json")
    if not revive or revive.get("status") != "ESCALATED":
        return None
    accepted = mod_baseline_keys(workspace / "working")
    buckets: dict[str, list[dict]] = defaultdict(list)
    for path in sorted((workspace / "reports" / "escalations").glob("*--*.json")):
        packet = _read_json(path)
        if not packet or packet.get("tier") != "decision":
            continue
        for finding in packet.get("findings") or []:
            if finding_dict_baseline_key(finding) not in accepted:
                buckets[finding["id"]].append(finding)
    other = any(p.get("tier") != "decision" for p in revive.get("packets") or [])
    return {"buckets": dict(buckets), "other": other}


def _group_key(finding_id: str, findings: list[dict]) -> tuple:
    patterns = tuple(sorted({file_pattern(f.get("file") or "") for f in findings}))
    evidence = tuple(sorted(shape_set(question_predicate(findings)["constraints"])))
    return finding_id, patterns, evidence


def _collect(queue: Path) -> tuple[dict[tuple, dict], dict[str, set[tuple]], set[str], int]:
    """Groups by key (each with its mods' findings); the group keys each mod is open on; the mods with a non-decision
    blocker; and how many workspaces are ESCALATED."""
    groups: dict[tuple, dict] = {}
    open_on: dict[str, set[tuple]] = defaultdict(set)
    other_blockers: set[str] = set()
    escalated = 0
    for workspace in _workspaces(queue):
        record = _workspace_blockers(workspace)
        if record is None:
            continue
        escalated += 1
        if record["other"]:
            other_blockers.add(workspace.name)
        for finding_id, findings in sorted(record["buckets"].items()):
            key = _group_key(finding_id, findings)
            group = groups.setdefault(key, {"finding": finding_id, "patterns": list(key[1]), "evidence": list(key[2]),
                                            "predicate": question_predicate(findings), "mods": {}})
            group["mods"][workspace.name] = findings
            open_on[workspace.name].add(key)
    return groups, open_on, other_blockers, escalated


def _similarity(left: frozenset[str], right: frozenset[str]) -> float:
    return len(left & right) / len(left | right) if left | right else 1.0


def _near_rulings(rulings: list[dict], finding_id: str, predicate: dict, shapes: frozenset[str], invalid: set[str]) -> list[dict]:
    """Standing rulings on the same finding: the same predicate (`exact`) or most of the same evidence shapes (R4)."""
    target_hash = predicate_hash(predicate)
    matches = []
    for ruling in rulings:
        if ruling.get("finding") != finding_id or ruling.get("id") in invalid or ruling.get("derived_from"):
            continue
        ruled = ruling["predicate"]
        exact = predicate_hash(ruled) == target_hash
        score = 1.0 if exact else _similarity(shape_set(ruled.get("constraints") or []), shapes)
        if exact or score >= NEAR_THRESHOLD:
            matches.append({"id": ruling.get("id"), "answer": ruling.get("ruling"), "intent": ruling.get("intent") or "",
                            "date": ruling.get("date"), "exact": exact, "similarity": round(score, 2),
                            "problem": predicate_problem(ruling)})
    matches.sort(key=lambda m: -m["similarity"])
    return matches[:NEAR_LIMIT]


def _commands(queue: Path, group: dict, proposal: bool) -> list[str]:
    finding = group["finding"]
    lines = []
    for mod in sorted(group["mods"]):
        for file in sorted({f.get("file") or "" for f in group["mods"][mod]}):
            selector = f"{finding}:{file}" if file else finding
            lines.append(f'bridgeforge escalation accept "{queue / mod}" "{selector}" --reason "{REASON_PLACEHOLDER}"')
    if proposal:
        lines.append(f'bridgeforge escalation rule {finding} "{queue}" --accept --reason "{REASON_PLACEHOLDER}"')
    return lines


def _describe(queue: Path, key: tuple, group: dict, ctx: dict) -> dict:
    """One group as the owner reads it. `decision_only`: the mods whose open decisions are all in this group.
    `cleared`: those with no other open blocker either, so this decision is all that stands between them and a pass."""
    mods = set(group["mods"])
    decision_only = sorted(m for m in mods if ctx["open_on"][m] == {key})
    cleared = [m for m in decision_only if m not in ctx["other"]]
    proposal = mods == ctx["ids_mods"][group["finding"]] and bool(cleared)
    evidence = group["evidence"]
    return {"finding": group["finding"], "file_patterns": group["patterns"], "evidence": evidence, "evidence_total": len(evidence),
            "mods": sorted(mods), "cleared": cleared, "decision_only": decision_only,
            "blocked_elsewhere": sorted(m for m in decision_only if m in ctx["other"]),
            "near_rulings": _near_rulings(ctx["rulings"], group["finding"], group["predicate"], shape_set(evidence), ctx["invalid"]),
            "commands": _commands(queue, group, proposal), "ruling_proposal": proposal}


def triage(queue: Path) -> dict:
    queue = Path(queue).expanduser().resolve()
    groups, open_on, other, escalated = _collect(queue)
    rulings = [r for r in load_rulings(queue) if isinstance(r.get("predicate"), dict)]
    ids_mods: dict[str, set[str]] = defaultdict(set)
    for group in groups.values():
        ids_mods[group["finding"]] |= set(group["mods"])
    ctx = {"open_on": open_on, "other": other, "ids_mods": ids_mods, "rulings": rulings, "invalid": invalid_ids(load_log(queue))}
    described = [_describe(queue, key, group, ctx) for key, group in groups.items()]
    described.sort(key=lambda g: (-len(g["cleared"]), -len(g["decision_only"]), -len(g["mods"]), g["finding"], g["evidence"]))
    for number, group in enumerate(described, 1):
        group["id"] = f"T{number:03d}"
    return {"schema_version": SCHEMA_VERSION, "mode": "ESCALATION_TRIAGE", "queue": str(queue), "escalated": escalated,
            "open_decisions": sum(len(g["mods"]) for g in described), "groups": described,
            "result_json": RESULT_JSON, "result_md": RESULT_MD}


def _render_group(group: dict) -> list[str]:
    head = (f"### {group['id']} `{group['finding']}` ({', '.join(group['file_patterns'])}): clears {len(group['cleared'])}, "
            f"decision-only {len(group['decision_only'])} of {len(group['mods'])} mod(s)")
    shown = group["evidence"][:EVIDENCE_SHOWN]
    more = group["evidence_total"] - len(shown)
    lines = [head, "", "Shared evidence: " + "; ".join(f"`{e}`" for e in shown) + (f" (+{more} more)" if more > 0 else ""), ""]
    if group["blocked_elsewhere"]:
        lines += [f"Decision-only, not cleared (another packet still blocks): {', '.join(group['blocked_elsewhere'])}", ""]
    for near in group["near_rulings"]:
        kind = "same predicate" if near["exact"] else f"similar ({near['similarity']})"
        problem = f"; not standing: {near['problem']}" if near["problem"] else ""
        lines.append(f"- Earlier ruling {near['id']}: {near['answer']}, {kind}{problem}")
    lines += ["", "```powershell"] + group["commands"] + ["```", ""]
    return lines


def render(result: dict) -> str:
    lines = [f"# Escalation triage ({len(result['groups'])} group(s), {result['open_decisions']} open decision(s), "
             f"{result['escalated']} escalated mod(s))", "",
             "Each group is one kind of decision. The commands are for the owner to read and run; BridgeForge never runs them.",
             "Replace each `<why it is right as written...>` placeholder with the evidence before running.", "",
             "| Group | Finding | File pattern | Mods | Decision-only | Clears |", "|---|---|---|---|---|---|"]
    for group in result["groups"]:
        lines.append(f"| {group['id']} | `{group['finding']}` | {', '.join(group['file_patterns'])} | {len(group['mods'])} | "
                     f"{len(group['decision_only'])} | {len(group['cleared'])} |")
    lines.append("")
    for group in result["groups"]:
        lines += _render_group(group)
    return "\n".join(lines) + "\n"


def write_result(result: dict, directory: Path) -> dict:
    directory = Path(directory).expanduser().resolve()
    json_path = atomic_write_text(directory / RESULT_JSON, json.dumps(result, indent=2, ensure_ascii=False))
    md_path = atomic_write_text(directory / RESULT_MD, render(result))
    return {"json": str(json_path), "md": str(md_path)}


def summary(result: dict) -> str:
    return "\n".join(f"{g['id']}  clears {len(g['cleared']):3}  decision-only {len(g['decision_only']):3}/{len(g['mods']):3}  "
                     f"{g['finding']} ({', '.join(g['file_patterns'])})" for g in result["groups"][:SUMMARY_LINES])
