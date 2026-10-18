"""Packet kind `recreation`: a plan skeleton for re-creating a feature a port dropped (ROADMAP item 73 E4, item 72).

The headings are those of docs/TEMPLAR_CRUSADE_PLAN.md, the worked example (Templars Holy Crusade, 2026-10-13), with the
feature-specific words generalised. `tests/test_scan_port.py` reads that document and fails if a section number goes
missing here. Whether a mod gets a plan is the owner's decision (AUTOMATION_PLAN decision 5): the skeleton is written
only for a `port-dropped-feature` packet, never over an existing file, and every section starts as a question to answer.
"""
from __future__ import annotations

from pathlib import Path

from .safeio import atomic_write_text

PLAN_FILE = "RECREATION_PLAN.md"

# (number, heading, what to write). Numbers follow docs/TEMPLAR_CRUSADE_PLAN.md.
SECTIONS = (
    ("1", "What the old version's feature did", "Read from the old version's sources: one row per behaviour, with the class and data file that implemented it."),
    ("2", "Why it stopped working, and the RC8 replacement for each part", "Per removed API or system: the evidence it is gone (javap, a vanilla file) and the RC8 mechanism that replaces it."),
    ("3", "Design", "The chosen design. Subsections below."),
    ("3.1", "Packaging", "Built into the mod, or a companion mod or jar; what each version lists and calls."),
    ("3.2", "Scheduler", "What starts the feature, how often, and how its state is saved."),
    ("3.3", "The feature itself", "The main class and the RC8 base it extends."),
    ("3.4", "Defenders and other actors", "Fleets, factions or markets that react, and how they are driven."),
    ("3.5", "Market effects", "Conditions, accessibility or stability changes, and how they are removed."),
    ("3.6", "Outcome and aftermath", "Endings, reports, reputation and lasting effects."),
    ("3.7", "Nexerelin", "What changes with Nexerelin present or absent."),
    ("3.8", "Save safety", "No live object references in saved state; what happens when a save is loaded mid-feature."),
    ("4", "Testing", "Offline tests, then the live runs that would prove it, and what each proves."),
    ("5", "Phases and effort", "Ordered phases, each with a done condition."),
    ("5a", "As built", "Filled in when built: what shipped, what differed from the design, the live evidence with dates."),
    ("6", "Owner decisions", "Each open question, the options, the recommendation and the owner's answer with its date."),
)


def section_numbers() -> tuple[str, ...]:
    return tuple(number for number, _, _ in SECTIONS)


def render_skeleton(workspace_name: str, packet: dict) -> str:
    lines = [f"# {workspace_name}: re-creation plan for dropped features (skeleton)", "",
             "Written by `bridgeforge revive` from a `port-dropped-feature` finding. Headings follow docs/TEMPLAR_CRUSADE_PLAN.md. "
             "Nothing here is decided: the owner chooses whether this mod gets a plan.", "",
             "## Dropped by the port", ""]
    for finding in packet.get("findings") or []:
        lines += [f"- {item}" for item in finding.get("evidence") or []]
    lines.append("")
    for number, heading, prompt in SECTIONS:
        marks = "###" if "." in number else "##"
        lines += [f"{marks} {number}. {heading}", "", f"_To write: {prompt}_", ""]
    return "\n".join(lines)


def write_skeleton(workspace: Path, packet: dict) -> Path | None:
    """`reports/RECREATION_PLAN.md` under the workspace, unless one exists already (a person's edits are never replaced)."""
    path = Path(workspace) / "reports" / PLAN_FILE
    if path.exists():
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, render_skeleton(Path(workspace).name, packet))
    return path
