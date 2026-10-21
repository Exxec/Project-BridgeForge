"""Per-repo gate registry (`gates.json`, schema 1) and the live-pending session plan (ROADMAP-3 items 80.6 and 80.2).

A gate is one claim that stays open until a person or a rig run settles it. `gates.json` sits at a repo's root:

    {"schema": 1, "repo": "NAME", "gates": [GATE, ...]}

GATE keys (all required unless marked optional):
  id          unique within the file, `[A-Za-z0-9][A-Za-z0-9._-]*`
  title       one line saying what the gate closes
  state       PASS | FAIL | NOT_TESTED | LIVE_PENDING | BLOCKED
  evidence    list of paths or run ids; must be non-empty when state is PASS
  needs       {"rig": bool (required); "mods": [mod ids]; "save": bool; "java": str|null; "launcher": str|null;
               "lunalib": bool|null; "scenario": str|null}  (absent keys mean [], false, null)
  commands    list of exact command lines, in order
  source_doc  {"path": repo-relative file, "anchor": text that must occur in that file,
               "status_line": optional text identifying the status line to lint}
  updated     ISO date YYYY-MM-DD

Lint rule (deliberately simple): when `source_doc.status_line` is given, the first line of the doc containing it must
contain the gate's state word (case-insensitive, `_` and a space are the same, so LIVE_PENDING matches "LIVE PENDING").
`anchor` and the doc itself must exist. Lint reads docs only and never edits them.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .safeio import atomic_write_json

SCHEMA = 1
GATES_FILE = "gates.json"
STATES = ("PASS", "FAIL", "NOT_TESTED", "LIVE_PENDING", "BLOCKED")
RECORDABLE = ("PASS", "FAIL", "NOT_TESTED")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
_NEEDS_TYPES = {"rig": bool, "save": bool, "mods": list, "java": str, "launcher": str, "lunalib": bool, "scenario": str}


def gates_path(repo: Path) -> Path:
    """`repo/gates.json`; a path that is itself a file (a draft gates file) is used as given."""
    path = Path(repo).expanduser().resolve()
    return path if path.is_file() else path / GATES_FILE


def _is_str_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) and item for item in value)


def validate_gates(data: object) -> list[str]:
    """Schema problems of a parsed gates.json, empty when valid."""
    if not isinstance(data, dict):
        return ["top level must be an object"]
    problems = []
    if data.get("schema") != SCHEMA:
        problems.append(f"schema must be {SCHEMA}")
    if not isinstance(data.get("repo"), str) or not data.get("repo"):
        problems.append("repo must be a non-empty string")
    gates = data.get("gates")
    if not isinstance(gates, list):
        return problems + ["gates must be a list"]
    seen: set[str] = set()
    for index, gate in enumerate(gates):
        label = f"gates[{index}]"
        if not isinstance(gate, dict):
            problems.append(f"{label}: must be an object")
            continue
        gate_id = gate.get("id")
        if not isinstance(gate_id, str) or not _ID.match(gate_id):
            problems.append(f"{label}: id must match {_ID.pattern}")
        else:
            label = f"gate {gate_id}"
            if gate_id in seen:
                problems.append(f"{label}: duplicate id")
            seen.add(gate_id)
        problems.extend(f"{label}: {text}" for text in _gate_problems(gate))
    return problems


def _gate_problems(gate: dict) -> list[str]:
    problems = []
    if not isinstance(gate.get("title"), str) or not gate["title"].strip():
        problems.append("title must be a non-empty string")
    if gate.get("state") not in STATES:
        problems.append(f"state must be one of {'|'.join(STATES)}")
    if not _is_str_list(gate.get("evidence")):
        problems.append("evidence must be a list of non-empty strings")
    elif gate.get("state") == "PASS" and not gate["evidence"]:
        problems.append("a PASS gate needs evidence")
    if not _is_str_list(gate.get("commands")):
        problems.append("commands must be a list of non-empty strings")
    if not isinstance(gate.get("updated"), str) or not _DATE.match(gate["updated"]):
        problems.append("updated must be YYYY-MM-DD")
    problems.extend(_needs_problems(gate.get("needs")))
    problems.extend(_source_doc_problems(gate.get("source_doc")))
    return problems


def _needs_problems(needs: object) -> list[str]:
    if not isinstance(needs, dict):
        return ["needs must be an object"]
    problems = [f"needs.{key} is unknown" for key in needs if key not in _NEEDS_TYPES]
    if not isinstance(needs.get("rig"), bool):
        problems.append("needs.rig must be a boolean")
    for key, kind in _NEEDS_TYPES.items():
        value = needs.get(key)
        if key == "rig" or value is None:
            continue
        if key == "mods":
            if not _is_str_list(value):
                problems.append("needs.mods must be a list of strings")
        elif not isinstance(value, kind):
            problems.append(f"needs.{key} must be {kind.__name__} or null")
    return problems


def _source_doc_problems(doc: object) -> list[str]:
    if not isinstance(doc, dict):
        return ["source_doc must be an object"]
    problems = []
    path = doc.get("path")
    if not isinstance(path, str) or not path or Path(path).is_absolute() or ".." in Path(path).parts:
        problems.append("source_doc.path must be a repo-relative path")
    if not isinstance(doc.get("anchor"), str) or not doc.get("anchor"):
        problems.append("source_doc.anchor must be a non-empty string")
    status_line = doc.get("status_line")
    if status_line is not None and (not isinstance(status_line, str) or not status_line):
        problems.append("source_doc.status_line must be a non-empty string when given")
    problems.extend(f"source_doc.{key} is unknown" for key in doc if key not in {"path", "anchor", "status_line"})
    return problems


def load_gates(repo: Path) -> dict:
    """The validated gates.json of `repo`; ValueError (with every problem) when missing or invalid."""
    path = gates_path(repo)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"{path} not found") from None
    except (OSError, ValueError) as exc:
        raise ValueError(f"{path}: {exc}") from None
    problems = validate_gates(data)
    if problems:
        raise ValueError(f"{path} is invalid:\n  " + "\n  ".join(problems))
    return data


def _state_matches(line: str, state: str) -> bool:
    def normal(text: str) -> str:
        return re.sub(r"[_\s]+", " ", text).lower()
    return normal(state) in normal(line)


def lint_gates(repo: Path, data: dict) -> list[str]:
    """Contradictions between each gate and the status line it cites (rule in the module docstring)."""
    root = Path(repo).expanduser().resolve()
    problems = []
    for gate in data["gates"]:
        doc = gate["source_doc"]
        target = (root / doc["path"]).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            problems.append(f"{gate['id']}: source doc {doc['path']} not found")
            continue
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        if not any(doc["anchor"] in line for line in lines):
            problems.append(f"{gate['id']}: anchor {doc['anchor']!r} not found in {doc['path']}")
        needle = doc.get("status_line")
        if needle is None:
            continue
        cited = next((line for line in lines if needle in line), None)
        if cited is None:
            problems.append(f"{gate['id']}: status line {needle!r} not found in {doc['path']}")
        elif not _state_matches(cited, gate["state"]):
            problems.append(f"{gate['id']}: state {gate['state']} but {doc['path']} says: {cited.strip()[:140]}")
    return problems


def record_gate(repo: Path, gate_id: str, state: str, evidence: list[str], today: str | None = None) -> dict:
    """Write a result back into gates.json (atomic, that file only). Returns the new gate."""
    if state not in RECORDABLE:
        raise ValueError(f"record accepts only {', '.join(RECORDABLE)}")
    data = load_gates(repo)
    if not any(gate["id"] == gate_id for gate in data["gates"]):
        raise ValueError(f"no gate {gate_id} in {gates_path(repo)}")
    if state == "PASS" and not evidence:
        raise ValueError("a PASS needs --evidence")
    stamp = today or date.today().isoformat()
    updated = [{**gate, "state": state, "evidence": list(evidence) or list(gate["evidence"]), "updated": stamp}
               if gate["id"] == gate_id else gate for gate in data["gates"]]
    result = {**data, "gates": updated}
    atomic_write_json(gates_path(repo), result)
    return next(gate for gate in updated if gate["id"] == gate_id)


# ---- live-pending session plan (80.2) ------------------------------------------------------------------------

@dataclass
class Block:
    """One rig launch configuration and the gates it closes."""
    mods: frozenset[str]
    java: str | None
    launcher: str | None
    lunalib: bool | None
    save: bool
    gates: list[tuple[str, dict]]


def _config(needs: dict) -> tuple:
    return (frozenset(needs.get("mods") or []), needs.get("java"), needs.get("launcher"),
            needs.get("lunalib"), bool(needs.get("save")))


def _compatible(host: Block, group: Block) -> bool:
    """A group rides a host launch when its mods are a subset, its pinned settings agree, and a save exists if needed."""
    pinned = ((host.java, group.java), (host.launcher, group.launcher), (host.lunalib, group.lunalib))
    return group.mods <= host.mods and all(want is None or have == want for have, want in pinned) and (host.save or not group.save)


def collect_open_gates(repos: list[Path]) -> tuple[list[tuple[str, dict]], list[tuple[str, dict]]]:
    """(rig gates to plan, blocked rig gates) over every repo, as (repo name, gate); PASS and no-rig gates are left out."""
    planned, blocked = [], []
    for repo in repos:
        data = load_gates(repo)
        for gate in data["gates"]:
            if gate["state"] == "PASS" or not gate["needs"]["rig"]:
                continue
            (blocked if gate["state"] == "BLOCKED" else planned).append((data["repo"], gate))
    return planned, blocked


def plan_blocks(gates: list[tuple[str, dict]]) -> list[Block]:
    """Group gates by configuration, fold subset configurations into a larger launch, biggest launches first."""
    groups: dict[tuple, Block] = {}
    for item in gates:
        key = _config(item[1]["needs"])
        groups.setdefault(key, Block(*key, gates=[])).gates.append(item)
    ordered = sorted(groups.values(), key=lambda b: (-len(b.mods), not b.save, -len(b.gates), sorted(b.mods)))
    hosts: list[Block] = []
    for group in ordered:
        host = next((h for h in hosts if _compatible(h, group)), None)
        if host is None:
            hosts.append(group)
        else:
            host.gates.extend(group.gates)
    return sorted(hosts, key=lambda b: (-len(b.gates), sorted(b.mods), str(b.java)))


def _setting(value: object) -> str:
    if value is None:
        return "any"
    return str(value).lower() if isinstance(value, bool) else str(value)


def render_plan(planned: list[tuple[str, dict]], blocked: list[tuple[str, dict]], repos: list[Path]) -> str:
    blocks = plan_blocks(planned)
    names = ", ".join(Path(repo).expanduser().resolve().name for repo in repos)
    lines = ["# Live-pending session plan", "",
             f"Repos: {names}. {len(planned)} open rig gate(s) in {len(blocks)} launch block(s); "
             f"{len(blocked)} blocked (not scheduled).", ""]
    for number, block in enumerate(blocks, 1):
        mods = ", ".join(sorted(block.mods)) or "(no specific mods)"
        lines += [f"## Block {number}: {mods}", "",
                  f"- java: {_setting(block.java)}; launcher: {_setting(block.launcher)}; lunalib: {_setting(block.lunalib)}; "
                  f"save: {'yes' if block.save else 'no'}", f"- closes {len(block.gates)} gate(s)", ""]
        for repo, gate in sorted(block.gates, key=lambda item: (item[0], item[1]["id"])):
            scenario = f" [scenario: {gate['needs']['scenario']}]" if gate["needs"].get("scenario") else ""
            lines += [f"### {repo}:{gate['id']} ({gate['state']}){scenario}", "", f"Closes: {gate['title']}", "",
                      f"Source: {gate['source_doc']['path']} ({gate['source_doc']['anchor']})", ""]
            if gate["commands"]:
                lines += ["```", *gate["commands"], "```", ""]
            lines += [f"Record: `python -m bridgeforge gates record {gate['id']} --repo <{repo} dir> "
                      "--state PASS --evidence <run id or path>`", ""]
    if blocked:
        lines += ["## Blocked (not scheduled)", ""]
        lines += [f"- {repo}:{gate['id']}: {gate['title']}" for repo, gate in sorted(blocked, key=lambda i: (i[0], i[1]["id"]))]
        lines.append("")
    return "\n".join(lines)


def live_pending_plan(repos: list[Path]) -> str:
    planned, blocked = collect_open_gates(repos)
    return render_plan(planned, blocked, repos)
