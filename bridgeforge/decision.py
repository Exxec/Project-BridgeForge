"""`decision apply DRAFT` and `decision template KIND`: turn an owner's ticked decision draft into recorded changes (ROADMAP 80.4, 77.20).

A decision draft is a Markdown file with checkboxes (`- [x] Accept the core findings ...`) and one fenced `bf-decision` JSON block:

    ```bf-decision
    {"schema": 1, "actions": [
      {"when": "Accept the core findings", "type": "accept_findings", "workspace": ".", "selectors": ["dropped-feature"], "reason": "..."},
      {"when": "Record the removals", "type": "record_removals", "workspace": ".", "entries": [{"category": "classes", "item": "a.B", "reason": "...", "source": "owner"}]},
      {"when": "Schedule C4", "type": "schedule", "file": "ROADMAP.md", "anchor": "C4", "line": "Recreate player reputation texts"},
      {"when": "Add the live run", "type": "rig_step", "gates_repo": ".", "gate": {"id": "crusade-live", "status": "NOT_TESTED"}}]}
    ```

`when` is the text of the checkbox the action depends on (case and spacing ignored). Only actions whose box is ticked run. A `when` that
matches no checkbox refuses the whole draft before anything changes. Relative paths resolve against the draft's folder. Every action is
idempotent: a second run changes nothing and appends nothing. A run that changed something appends an "Applied <date>" section.

`gates.json` in `gates_repo` is `{"schema": 1, "gates": [...]}` (a bare list is also read); `rig_step` adds the gate unless an entry
with the same `id` exists (80.6 will own the schema; this only appends).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Callable

from .removals import validate_entry, add_removals, load_removals
from .safeio import atomic_write_json, atomic_write_text

ACTION_FIELDS: dict[str, tuple[str, ...]] = {
    "accept_findings": ("workspace", "selectors", "reason"),
    "record_removals": ("workspace", "entries"),
    "schedule": ("file", "anchor", "line"),
    "rig_step": ("gates_repo", "gate"),
}
GATES_FILE = "gates.json"
TEMPLATE_KINDS = ("port-dropped-feature",)
_BLOCK = re.compile(r"^```bf-decision[ \t]*\r?\n(.*?)^```[ \t]*$", re.DOTALL | re.MULTILINE)
_BOX = re.compile(r"^\s*[-*]\s+\[([ xX])\]\s+(.*?)\s*$")


class DecisionError(ValueError):
    """The draft is malformed, references a missing checkbox, or an action cannot run."""


def _norm(text: str) -> str:
    return " ".join(text.split()).casefold()


def parse_checkboxes(text: str) -> dict[str, bool]:
    """Normalised checkbox label -> ticked."""
    boxes: dict[str, bool] = {}
    for line in text.splitlines():
        match = _BOX.match(line)
        if match:
            boxes[_norm(match.group(2))] = match.group(1) in "xX"
    return boxes


def parse_actions(text: str) -> list[dict]:
    """The validated actions of the draft's single `bf-decision` block."""
    blocks = _BLOCK.findall(text)
    if len(blocks) != 1:
        raise DecisionError(f"expected exactly one ```bf-decision block, found {len(blocks)}")
    try:
        data = json.loads(blocks[0])
    except ValueError as exc:
        raise DecisionError(f"bf-decision block is not valid JSON: {exc}") from exc
    actions = data.get("actions") if isinstance(data, dict) else None
    if not isinstance(data, dict) or data.get("schema") != 1 or not isinstance(actions, list):
        raise DecisionError('bf-decision block must be {"schema": 1, "actions": [...]}')
    for index, action in enumerate(actions):
        where = f"actions[{index}]"
        if not isinstance(action, dict) or action.get("type") not in ACTION_FIELDS:
            raise DecisionError(f"{where}: `type` must be one of {', '.join(ACTION_FIELDS)}")
        if not isinstance(action.get("when"), str) or not action["when"].strip():
            raise DecisionError(f"{where}: `when` (the checkbox text) is required")
        missing = [field for field in ACTION_FIELDS[action["type"]] if not action.get(field)]
        if missing:
            raise DecisionError(f"{where} ({action['type']}): missing {', '.join(missing)}")
    return actions


def _path(base: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (base / path).resolve()


def _accept(action: dict, base: Path, today: str, dry_run: bool, scan: Callable | None) -> tuple[bool, str]:
    from .baseline_accept_finding import accept_selected

    workspace = _path(base, action["workspace"])
    if scan is None:
        from bridgeforge.scan.scanner import scan_mod

        scan = lambda working: scan_mod(working).findings  # noqa: E731
    result = accept_selected(workspace, list(action["selectors"]), action["reason"], scan(workspace / "working"), today, dry_run)
    if not result["added"]:
        return False, f"{len(result['selected'])} finding key(s) already accepted"
    return True, f"{len(result['added'])} finding key(s) {'would be ' if dry_run else ''}accepted into {result['baseline']}"


def _removals(action: dict, base: Path, today: str, dry_run: bool, scan: Callable | None) -> tuple[bool, str]:
    working = _path(base, action["workspace"]) / "working"
    entries = [validate_entry({"date": today, **entry}, f"entries[{i}]") for i, entry in enumerate(action["entries"])]
    existing = load_removals(working)
    seen = [{k: v for k, v in r.items() if k != "date"} for r in existing]
    new = [e for e in entries if {k: v for k, v in e.items() if k != "date"} not in seen]
    if not new:
        return False, f"{len(entries)} removal(s) already recorded"
    if not dry_run:
        add_removals(working, new)
    return True, f"{len(new)} removal(s) {'would be ' if dry_run else ''}recorded in {working / 'reports' / 'REMOVALS.json'}"


def _schedule(action: dict, base: Path, today: str, dry_run: bool, scan: Callable | None) -> tuple[bool, str]:
    path = _path(base, action["file"])
    if not path.is_file():
        raise DecisionError(f"schedule: {path} does not exist")
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    text = action["line"].strip()
    if any(text in line for line in lines):
        return False, f"line already present in {path}"
    hits = [i for i, line in enumerate(lines) if action["anchor"] in line]
    if len(hits) != 1:
        raise DecisionError(f"schedule: anchor {action['anchor']!r} matches {len(hits)} line(s) in {path}, need exactly 1")
    newline = "\r\n" if lines[hits[0]].endswith("\r\n") else "\n"
    entry = f"- {today}: {text}{newline}"
    if not lines[hits[0]].endswith(("\n", "\r")):
        lines[hits[0]] += newline
    lines.insert(hits[0] + 1, entry)
    if not dry_run:
        atomic_write_text(path, "".join(lines), newline="")
    return True, f"line {'would be ' if dry_run else ''}added after the anchor in {path}"


def _rig_step(action: dict, base: Path, today: str, dry_run: bool, scan: Callable | None) -> tuple[bool, str]:
    path = _path(base, action["gates_repo"]) / GATES_FILE
    gate = action["gate"]
    if not isinstance(gate, dict) or not gate.get("id"):
        raise DecisionError("rig_step: `gate` must be an object with an `id`")
    data = json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else {"schema": 1, "gates": []}
    gates = data if isinstance(data, list) else data.get("gates")
    if not isinstance(gates, list):
        raise DecisionError(f"rig_step: {path} has no gates list")
    if any(isinstance(g, dict) and g.get("id") == gate["id"] for g in gates):
        return False, f"gate {gate['id']!r} already in {path}"
    if not dry_run:
        gates.append(gate)
        atomic_write_json(path, data, indent=2, ensure_ascii=False)
    return True, f"gate {gate['id']!r} {'would be ' if dry_run else ''}added to {path}"


HANDLERS = {"accept_findings": _accept, "record_removals": _removals, "schedule": _schedule, "rig_step": _rig_step}


def _applied_section(today: str, results: list[dict]) -> str:
    lines = [f"## Applied {today}", ""]
    for item in results:
        lines.append(f"- {item['status']}: {item['when']} ({item['type']}): {item['detail']}")
    return "\n".join(lines) + "\n"


def apply_draft(draft: Path, dry_run: bool = False, today: str | None = None, scan: Callable | None = None) -> dict:
    """Run the actions whose boxes are ticked. Refuses (DecisionError, nothing changed) on a missing box or a malformed block."""
    today = today or date.today().isoformat()
    draft = Path(draft).resolve()
    text = draft.read_text(encoding="utf-8")
    actions = parse_actions(text)
    boxes = parse_checkboxes(text)
    absent = [a["when"] for a in actions if _norm(a["when"]) not in boxes]
    if absent:
        raise DecisionError("no checkbox matches: " + "; ".join(repr(w) for w in absent))
    results = []
    for action in actions:
        item = {"when": action["when"], "type": action["type"]}
        if not boxes[_norm(action["when"])]:
            results.append({**item, "status": "skipped", "detail": "box not ticked"})
            continue
        try:
            changed, detail = HANDLERS[action["type"]](action, draft.parent, today, dry_run, scan)
        except (OSError, ValueError) as exc:
            raise DecisionError(f"{action['type']} for {action['when']!r}: {exc}") from exc
        results.append({**item, "status": "changed" if changed else "unchanged", "detail": detail})
    changed_any = any(r["status"] == "changed" for r in results)
    if changed_any and not dry_run:
        atomic_write_text(draft, text.rstrip() + "\n\n" + _applied_section(today, results))
    return {"draft": str(draft), "dry_run": dry_run, "date": today, "changed": changed_any, "results": results}


def template(kind: str) -> str:
    if kind not in TEMPLATE_KINDS:
        raise DecisionError(f"unknown template kind {kind!r} (one of {', '.join(TEMPLATE_KINDS)})")
    return TEMPLATE_PORT_DROPPED


TEMPLATE_PORT_DROPPED = """# <Mod version>: decision draft for the port-dropped-feature findings (DRAFT, owner to confirm)

Nothing below is accepted until the owner ticks a box and `bridgeforge decision apply` is run on this file.

## Item-by-item mapping

| Dropped in the port | Replacement | Proposed ruling |
|---|---|---|
| `<class or id>` | `<new name>` | Accept: re-created |

## Owner decision requested

- [ ] Accept the core findings with the reason above
- [ ] Record the removals as explained
- [ ] Schedule the recreation work
- [ ] Add the live run to the rig session

```bf-decision
{"schema": 1, "actions": [
  {"when": "Accept the core findings with the reason above", "type": "accept_findings", "workspace": "..",
   "selectors": ["dropped-feature"], "reason": "re-created for the new base as <name> (<plan reference>)"},
  {"when": "Record the removals as explained", "type": "record_removals", "workspace": "..",
   "entries": [{"category": "classes", "item": "<pkg.Name>", "reason": "replaced by <new class>", "source": "owner"}]},
  {"when": "Schedule the recreation work", "type": "schedule", "file": "../ROADMAP.md", "anchor": "<unique anchor text>",
   "line": "<recreation work to schedule>"},
  {"when": "Add the live run to the rig session", "type": "rig_step", "gates_repo": "..",
   "gate": {"id": "<gate-id>", "status": "NOT_TESTED", "what": "live run with <mods>"}}]}
```
"""


def add_parser(subcommands) -> None:
    decision = subcommands.add_parser("decision", help="'apply DRAFT' runs the ticked actions of an owner decision draft (bf-decision block); 'template KIND' prints a starter draft")
    sub = decision.add_subparsers(dest="decision_command", required=True)
    apply_cmd = sub.add_parser("apply", help="run the actions whose checkboxes are ticked; idempotent; appends an 'Applied <date>' section")
    apply_cmd.add_argument("draft", type=Path)
    apply_cmd.add_argument("--dry-run", action="store_true", help="report what would change and change nothing")
    apply_cmd.add_argument("--json", action="store_true")
    template_cmd = sub.add_parser("template", help="print a starter decision draft")
    template_cmd.add_argument("kind", choices=TEMPLATE_KINDS)


def run_cli(args: argparse.Namespace) -> int:
    try:
        if args.decision_command == "template":
            print(template(args.kind), end="")
            return 0
        result = apply_draft(args.draft, args.dry_run)
    except (OSError, ValueError) as exc:
        print(f"bridgeforge: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    for item in result["results"]:
        print(f"{item['status']:<9} {item['when']} ({item['type']}): {item['detail']}")
    if not result["changed"]:
        print("Nothing changed.")
    return 0
