"""Reference cycles through a Memory inside a PCMarket in campaign.xml, and a repair on a COPY (ROADMAP 60g(3), 68; RC8-31).

Found in a real 1 GB Modpack 6.3 save: a planet's condition market (`cl="PCMarket"`, z=1) shares a Memory (`cl="Memory"`, z=2) with its
station's copy of the market. An object stored in that memory (Station Augments, key `$SA_stationAugmentListMemId`) leads the writer into
the station copy, whose `<memory cl="Memory" ref="2">` then refers to the memory still being read, and `PlanetConditionMarket.readResolve`
throws a NullPointerException at load.

Streaming, line by line: open elements are tracked with their `cl` and `z` ids. A `ref="N"` whose target is an OPEN Memory, met inside a
PCMarket that is itself nested in that Memory, is a cycle. Reported: the line, the memory id, the PCMarket id, and the entry keys
(`<e><st>$key</st>`) on the path between. `break_cycle` writes a COPY only: it replaces each such line
`<memory cl="Memory" ref="N"></memory>` with `<memory cl="Memory"><d></d></memory>` after checking the line's exact text, and the
original is never opened for writing.
"""
from __future__ import annotations

from .safeio import safe_rmtree

import re
import shutil
from pathlib import Path

from .save_reader import campaign_xml_path

_TAG = re.compile(r"<(/?)([A-Za-z_][\w.\-]*)([^<>]*?)(/?)>")
_ATTR = re.compile(r'([\w:.\-]+)="([^"]*)"')
_KEY = re.compile(r"<st>([^<]*)</st>")
_INNER = re.compile(r'^(\s*)<memory cl="Memory" ref="(\d+)"></memory>(\r?\n?)$')
REPLACEMENT = '<memory cl="Memory"><d></d></memory>'


class SaveCycleError(ValueError):
    pass


def _frame(tag: str, attrs: dict[str, str], line: int) -> dict:
    return {"tag": tag, "cl": attrs.get("cl"), "z": attrs.get("z"), "line": line, "key": None}


def find_cycles(save: Path) -> list[dict]:
    """[{line, memory, pcmarket, keys, text}] for every reference to an open Memory from inside a PCMarket nested in it."""
    return scan_cycles(save)[0]


def scan_cycles(save: Path) -> tuple[list[dict], dict]:
    """(cycles, base rate). The base rate counts how common the surrounding shape is in the same save: PCMarket elements and how many of
    them hold a `<memory ref=...>` shared with another market. Six memories were shared three ways in a 577-mod save and only two were
    fatal; naming a mod from the cycle alone, without this, blamed the wrong one (ROADMAP 68, 70 H3.4)."""
    path = campaign_xml_path(save)
    stack: list[dict] = []
    cycles: list[dict] = []
    rate = {"pcmarkets": 0, "pcmarkets_sharing_a_memory": 0}
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as handle:
        for number, line in enumerate(handle, 1):
            for match in _TAG.finditer(line):
                closing, tag, rest, selfclose = match.groups()
                if closing:
                    if stack and stack[-1]["tag"] == tag:
                        stack.pop()
                    continue
                attrs = dict(_ATTR.findall(rest))
                ref = attrs.get("ref")
                if attrs.get("cl") == "PCMarket" and not ref:
                    rate["pcmarkets"] += 1
                if ref and tag == "memory" and stack and stack[-1]["cl"] == "PCMarket":
                    rate["pcmarkets_sharing_a_memory"] += 1  # a PCMarket whose memory is a reference to another element's
                if ref:
                    cycle = _cycle_for(stack, ref, number, line)
                    if cycle:
                        cycles.append(cycle)
                if not selfclose:
                    stack.append(_frame(tag, attrs, number))
                if tag == "st" and len(stack) >= 2 and stack[-2]["tag"] == "e" and not closing:
                    key = _KEY.search(line, match.start())
                    if key:
                        stack[-2]["key"] = key.group(1)
    return cycles, rate


def _cycle_for(stack: list[dict], ref: str, number: int, line: str) -> dict | None:
    memory_at = next((i for i, f in enumerate(stack) if f["z"] == ref and f["cl"] == "Memory"), None)
    if memory_at is None:
        return None
    above = stack[memory_at + 1:]
    markets = [f for f in above if f["cl"] == "PCMarket"]
    if not markets:
        return None
    return {"line": number, "memory": ref, "memory_line": stack[memory_at]["line"], "pcmarket": markets[-1]["z"],
            "keys": [f["key"] for f in above if f["tag"] == "e" and f["key"]], "text": line.strip()}


def break_cycle(save: Path, out: Path) -> dict:
    """Copy the save folder to `out` (must not exist) and fix every cycle line in the copy's campaign.xml. Never writes the original."""
    save, out = Path(save).resolve(), Path(out).resolve()
    if out.exists():
        raise SaveCycleError(f"{out} already exists; --out must be a new folder (the original is never modified).")
    if out == save or save in out.parents:
        raise SaveCycleError("--out must not be inside the save.")
    cycles = find_cycles(save)
    if not cycles:
        raise SaveCycleError("no cycle found; nothing to repair.")
    wanted = {c["line"]: c for c in cycles}
    shutil.copytree(save, out)
    target = campaign_xml_path(out)
    temporary = target.with_name(target.name + ".part")
    changed = []
    try:
        with open(target, "r", encoding="utf-8", errors="surrogateescape", newline="") as source, \
                open(temporary, "w", encoding="utf-8", errors="surrogateescape", newline="") as sink:
            for number, line in enumerate(source, 1):
                if number in wanted:
                    found = _INNER.match(line)
                    if not found or found.group(2) != wanted[number]["memory"]:
                        raise SaveCycleError(f"line {number} is not the expected inner memory reference ({wanted[number]['text']!r}); nothing was repaired.")
                    line = f"{found.group(1)}{REPLACEMENT}{found.group(3)}"
                    changed.append({"line": number, "memory": found.group(2), "pcmarket": wanted[number]["pcmarket"]})
                sink.write(line)
        temporary.replace(target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        safe_rmtree(out, [out.parent])
        raise
    remaining = find_cycles(out)
    return {"schema_version": 1, "mode": "BREAK_CYCLE_ON_COPY", "original": str(save), "copy": str(out), "changed_lines": changed,
            "cycles_before": len(cycles), "cycles_after": len(remaining),
            "note": "The original save was not changed. Load the copy in the game to prove it (RC8-31)."}
